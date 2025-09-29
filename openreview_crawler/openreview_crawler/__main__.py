from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import ICLRScraperConfig
from .iclr_scraper import ICLRScraper

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape ICLR data from OpenReview")
    parser.add_argument("--venue-id", default="ICLR.cc/2024/Conference")
    parser.add_argument("--blind-invitation")
    parser.add_argument("--output-dir", type=Path, default=Path("data/iclr"))
    parser.add_argument("--api-base-url", default="https://api.openreview.net")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--token")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--max-notes", type=int)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--since", type=str, help="ISO timestamp to override incremental state")
    parser.add_argument("--no-incremental", action="store_true")
    parser.add_argument(
        "--docling-use-granite",
        action="store_true",
        help="Enable Docling granite-based picture description pipeline",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> ICLRScraperConfig:
    manual_since: Optional[datetime] = None
    if args.since:
        manual_since = datetime.fromisoformat(args.since)
        if manual_since.tzinfo is None:
            manual_since = manual_since.replace(tzinfo=timezone.utc)
    config = ICLRScraperConfig(
        venue_id=args.venue_id,
        blind_submission_invitation=args.blind_invitation,
        output_dir=args.output_dir,
        api_base_url=args.api_base_url,
        page_size=args.page_size,
        max_notes=args.max_notes,
        incremental=not args.no_incremental,
        manual_since=manual_since,
        username=args.username,
        password=args.password,
        api_token=args.token,
        docling_use_granite=args.docling_use_granite,
    )
    if args.state_file:
        config.state_file = args.state_file
    return config


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format=DEFAULT_LOG_FORMAT)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_level)
    config = build_config(args)
    scraper = ICLRScraper(config)
    scraper.run()


if __name__ == "__main__":  # pragma: no cover
    main()
