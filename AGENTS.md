# Agent Guidelines

## Project purpose
This repository contains a Python 3.11+ toolkit that scrapes OpenReview (starting with ICLR venues) on a daily basis. Because OpenReview exposes only the latest revision payloads and not the originally uploaded PDFs, the scraper must capture submission metadata, download the very first PDF before any revision is posted, and retain the full reviewer-author discussion with score changes.

## Coding conventions
- Prefer the official `openreview-py` client when communicating with the OpenReview API.
- Keep the storage format append-only so that original PDFs are never overwritten.
- Use standard library facilities and type hints where possible.

## Testing
- Run `python -m compileall openreview_crawler` before sending a change.

## Documentation
- Update `README.md` when user-facing behaviour changes or when new operational guidance (e.g., automation via GitHub Actions) is added.
