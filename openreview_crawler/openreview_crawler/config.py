from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ICLRScraperConfig:
    """Configuration for the daily ICLR scraper."""

    venue_id: str = "ICLR.cc/2024/Conference"
    api_base_url: str = "https://api.openreview.net"
    blind_submission_invitation: Optional[str] = None
    output_dir: Path = field(default_factory=lambda: Path("data") / "iclr")
    page_size: int = 200
    max_notes: Optional[int] = None
    request_timeout: int = 20
    max_retries: int = 4
    incremental: bool = True
    state_file: Optional[Path] = None
    pdf_dirname: str = "pdf"
    manual_since: Optional[datetime] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_token: Optional[str] = None
    docling_use_granite: bool = False

    def __post_init__(self) -> None:
        if self.blind_submission_invitation is None:
            self.blind_submission_invitation = (
                f"{self.venue_id}/-/Blind_Submission"
            )
        if self.state_file is None:
            self.state_file = self.output_dir / "state.json"
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)

    @property
    def since(self) -> Optional[datetime]:
        """Load the last successful crawl timestamp if available."""

        if self.manual_since is not None:
            return self.manual_since
        if not self.incremental:
            return None
        if not self.state_file:
            return None
        if not self.state_file.exists():
            return None
        try:
            content = self.state_file.read_text("utf-8").strip()
        except OSError:
            return None
        if not content:
            return None
        try:
            ts = datetime.fromisoformat(content)
        except ValueError:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def update_state(self, now: Optional[datetime] = None) -> None:
        if not self.state_file:
            return
        now = now or datetime.now(timezone.utc)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(now.isoformat(), encoding="utf-8")

