from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional

from .config import ICLRScraperConfig
from .docling_processor import DoclingOptions, DoclingProcessor, slugify

LOGGER = logging.getLogger(__name__)


@dataclass
class StorageManager:
    config: ICLRScraperConfig

    def __post_init__(self) -> None:
        self.root = self.config.output_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._docling_processor: Optional[DoclingProcessor] = None

    def paper_dir(self, forum_id: str) -> Path:
        safe_forum = forum_id.replace("/", "_")
        path = self.root / safe_forum
        path.mkdir(parents=True, exist_ok=True)
        (path / self.config.pdf_dirname).mkdir(parents=True, exist_ok=True)
        return path

    def save_submission(self, forum_id: str, submission: Dict) -> None:
        path = self.paper_dir(forum_id) / "submission.json"
        self._write_json(path, submission)

    def pdf_label_exists(self, forum_id: str, label: str) -> bool:
        index = self._load_pdf_index(forum_id)
        return any(entry.get("label") == label for entry in index)

    def save_forum(self, forum_id: str, notes: List[Dict]) -> None:
        path = self.paper_dir(forum_id) / "forum.json"
        self._write_json(path, notes)

    def record_pdf(self, forum_id: str, url: str, payload: bytes, *, label: str) -> bool:
        digest = sha256(payload).hexdigest()
        index = self._load_pdf_index(forum_id)
        if any(entry["sha256"] == digest for entry in index):
            LOGGER.debug("PDF for %s already stored (digest=%s)", forum_id, digest)
            return False
        pdf_dir = self.paper_dir(forum_id) / self.config.pdf_dirname
        filename = f"{label}_{digest[:10]}.pdf"
        filepath = pdf_dir / filename
        filepath.write_bytes(payload)
        entry = {"label": label, "sha256": digest, "url": url}
        index.append(entry)
        self._write_json(pdf_dir / "index.json", index)
        LOGGER.info("Stored new PDF for %s at %s", forum_id, filepath)
        self._generate_docling_artifacts(forum_id, filepath, label)
        return True

    def _load_pdf_index(self, forum_id: str) -> List[Dict]:
        index_path = self.paper_dir(forum_id) / self.config.pdf_dirname / "index.json"
        if not index_path.exists():
            return []
        try:
            return json.loads(index_path.read_text("utf-8"))
        except json.JSONDecodeError:  # pragma: no cover - corrupted file
            LOGGER.warning("PDF index corrupted for %s, starting fresh", forum_id)
            return []

    def _write_json(self, path: Path, data) -> None:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def _generate_docling_artifacts(self, forum_id: str, pdf_path: Path, label: str) -> None:
        destination = self._docling_destination(forum_id, label, pdf_path)
        if (destination / "paper.md").exists():
            return
        processor = self._get_docling_processor()
        processor.process_pdf(pdf_path, destination)

    def _get_docling_processor(self) -> DoclingProcessor:
        if self._docling_processor is None:
            options = DoclingOptions(use_granite=self.config.docling_use_granite)
            self._docling_processor = DoclingProcessor(options)
        return self._docling_processor

    def _docling_destination(self, forum_id: str, label: str, pdf_path: Path) -> Path:
        digest_hint = pdf_path.stem.rsplit("_", 1)[-1]
        safe_label = slugify(f"{label}-{digest_hint}")
        return self.paper_dir(forum_id) / "docling" / safe_label

