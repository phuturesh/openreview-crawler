from __future__ import annotations

import logging
from typing import Dict, Iterator, List, Optional

import requests
from openreview import OpenReviewException
from openreview import api as openreview_api
from requests import Response
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import ICLRScraperConfig

LOGGER = logging.getLogger(__name__)


class OpenReviewClientError(RuntimeError):
    pass


class OpenReviewClient:
    """Lightweight wrapper around the OpenReview REST API."""

    def __init__(self, config: ICLRScraperConfig) -> None:
        self._config = config
        client_kwargs: Dict[str, Optional[str]] = {"baseurl": config.api_base_url}
        if config.api_token:
            client_kwargs["token"] = config.api_token
        elif config.username:
            client_kwargs["username"] = config.username
            if config.password:
                client_kwargs["password"] = config.password
        self._client = openreview_api.OpenReviewClient(**client_kwargs)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "openreview-crawler/0.1",
                "Accept": "application/json",
            }
        )

    def close(self) -> None:
        self._session.close()

    def iter_submissions(self) -> Iterator[Dict]:
        """Yield submissions for the configured venue."""

        invitation = self._config.blind_submission_invitation
        offset = 0
        fetched = 0
        since_ms: Optional[int] = None
        since = self._config.since
        if since:
            since_ms = int(since.timestamp() * 1000)
        max_notes = self._config.max_notes

        while True:
            try:
                notes = self._client.get_notes(
                    invitation=invitation,
                    offset=offset,
                    limit=self._config.page_size,
                    details="replyCount,overriding",
                    sort="number:asc",
                )
            except OpenReviewException as exc:  # pragma: no cover - network
                raise OpenReviewClientError(str(exc)) from exc
            if not notes:
                break
            for note in notes:
                note_json = note.to_json() if hasattr(note, "to_json") else note
                fetched += 1
                if since_ms is not None and note_json.get("cdate") and note_json["cdate"] < since_ms:
                    continue
                yield note_json
                if max_notes is not None and fetched >= max_notes:
                    return
            offset += len(notes)
            if max_notes is not None and fetched >= max_notes:
                break

    def fetch_forum(self, forum_id: str) -> List[Dict]:
        offset = 0
        notes: List[Dict] = []
        while True:
            try:
                batch = self._client.get_notes(
                    forum=forum_id,
                    offset=offset,
                    limit=1000,
                    details="replyto,signatures,parent",
                    sort="cdate:asc",
                )
            except OpenReviewException as exc:  # pragma: no cover - network
                raise OpenReviewClientError(str(exc)) from exc
            if not batch:
                break
            for note in batch:
                notes.append(note.to_json() if hasattr(note, "to_json") else note)
            offset += len(batch)
        notes.sort(key=lambda n: n.get("cdate", 0))
        return notes

    def fetch_note(self, note_id: str) -> Dict:
        try:
            note = self._client.get_note(note_id)
        except OpenReviewException as exc:  # pragma: no cover - network
            raise OpenReviewClientError(str(exc)) from exc
        if note is None:
            raise OpenReviewClientError(f"Note {note_id} not found")
        return note.to_json() if hasattr(note, "to_json") else note

    def download_file(self, url: str) -> bytes:
        retrying = Retrying(
            reraise=True,
            retry=retry_if_exception_type(OpenReviewClientError),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            stop=stop_after_attempt(self._config.max_retries or 5),
        )
        for attempt in retrying:
            with attempt:
                response = self._request("GET", url, absolute=True)
                return response.content
        raise OpenReviewClientError("Retrying finished without success")

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, object]] = None,
        absolute: bool = False,
    ) -> Response:
        url = path if absolute else f"{self._config.api_base_url}{path}"
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                timeout=self._config.request_timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            raise OpenReviewClientError(str(exc)) from exc
        if response.status_code >= 400:
            raise OpenReviewClientError(
                f"OpenReview API error {response.status_code}: {response.text[:200]}"
            )
        return response

