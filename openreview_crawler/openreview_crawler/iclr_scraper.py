from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .client import OpenReviewClient, OpenReviewClientError
from .config import ICLRScraperConfig
from .storage import StorageManager

LOGGER = logging.getLogger(__name__)


class ICLRScraper:
    """Scrape ICLR submissions and their discussion threads."""

    def __init__(self, config: Optional[ICLRScraperConfig] = None) -> None:
        self.config = config or ICLRScraperConfig()
        self.client = OpenReviewClient(self.config)
        self.storage = StorageManager(self.config)

    def run(self) -> None:
        LOGGER.info(
            "Starting crawl for %s (invitation=%s)",
            self.config.venue_id,
            self.config.blind_submission_invitation,
        )
        processed = 0
        for submission in self.client.iter_submissions():
            try:
                self._process_submission(submission)
                processed += 1
            except OpenReviewClientError as exc:
                LOGGER.error("Failed to process submission %s: %s", submission.get("id"), exc)
        self.config.update_state()
        LOGGER.info("Finished crawl. %d submissions processed.", processed)

    def _process_submission(self, submission: Dict) -> None:
        forum_id = submission.get("forum") or submission.get("id")
        if not forum_id:
            LOGGER.warning("Skipping submission without forum identifier: %s", submission)
            return
        LOGGER.info("Processing forum %s", forum_id)
        self.storage.save_submission(forum_id, submission)
        self._capture_note_pdf(forum_id, submission, label_prefix="submission")
        forum_notes = self.client.fetch_forum(forum_id)
        self.storage.save_forum(forum_id, forum_notes)
        self._capture_forum_pdfs(forum_id, forum_notes)
        score_history = self._extract_score_history(forum_notes)
        if score_history:
            path = self.storage.paper_dir(forum_id) / "score_history.json"
            path.write_text(score_history, encoding="utf-8")

    def _capture_forum_pdfs(self, forum_id: str, notes: List[Dict]) -> None:
        for note in notes:
            invitation = note.get("invitation", "")
            # Reviews and comments normally do not contain PDFs; skip them early.
            if "Revision" not in invitation and note.get("content", {}).get("pdf") is None:
                continue
            self._capture_note_pdf(forum_id, note, label_prefix="note")

    def _normalize_pdf_url(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("/"):
            return f"https://openreview.net{value}"
        if value.startswith("pdf?") or value.startswith("attachment?"):
            return f"https://openreview.net/{value}"
        return f"https://openreview.net/{value.lstrip('/')}"


    def _capture_note_pdf(self, forum_id: str, note: Dict, *, label_prefix: str) -> None:
        pdf_field = (note.get("content") or {}).get("pdf")
        if not pdf_field:
            return
        label = f"{label_prefix}_{note.get('id', 'unknown')}_{note.get('cdate', 0)}"
        if self.storage.pdf_label_exists(forum_id, label):
            return
        url = self._normalize_pdf_url(pdf_field)
        try:
            payload = self.client.download_file(url)
        except OpenReviewClientError as exc:
            LOGGER.error("Failed to download pdf %s: %s", url, exc)
            return
        self.storage.record_pdf(forum_id, url, payload, label=label)

    def _extract_score_history(self, notes: List[Dict]) -> str:
        history: List[Dict[str, object]] = []
        for note in notes:
            content = note.get("content") or {}
            rating = content.get("rating") or content.get("Recommendation")
            confidence = content.get("confidence") or content.get("Confidence")
            decision = content.get("decision") or content.get("Decision")
            if rating or decision:
                history.append(
                    {
                        "id": note.get("id"),
                        "cdate": note.get("cdate"),
                        "mdate": note.get("mdate"),
                        "signatures": note.get("signatures"),
                        "rating": rating,
                        "confidence": confidence,
                        "decision": decision,
                    }
                )
        if not history:
            return ""
        history.sort(key=lambda entry: entry.get("cdate") or 0)
        return json_dumps(history)


def json_dumps(data: object) -> str:
    import json

    return json.dumps(data, indent=2, sort_keys=True)

