# OpenReview Crawler

This repository provides a command line tool for scraping the OpenReview API,
building on the official `openreview-py` client library to stay compatible with
upstream changes. The scraper focuses on capturing the full review lifecycle of
ICLR submissions and is designed to run daily so that it can store the very
first version of uploaded PDFs before they are overwritten during the rebuttal
phase. OpenReview's revision feed only exposes updated notes, so we must fetch
and preserve the originally uploaded PDF before the first revision replaces it.

## Features

* Downloads metadata for every submission under a given ICLR venue.
* Captures the discussion history, including reviews, author responses and
  decisions, together with score changes across time.
* Persists all assets (JSON, PDFs and Docling-generated Markdown bundles) in an
  append-only file structure to preserve the earliest available revisions.
* Supports incremental daily runs by keeping track of the last successful
  execution timestamp.

## Quick start

```bash
pip install -e .
iclr-scrape --venue-id ICLR.cc/2024/Conference --output-dir data/iclr2024
# or
python -m openreview_crawler --venue-id ICLR.cc/2024/Conference --output-dir data/iclr2024
```

Pass `--docling-use-granite` if you need Docling to generate multimodal
descriptions for detected figures.

If you prefer GitHub Actions for scheduling, you can wrap the CLI in a simple
workflow that runs on a nightly cron trigger and commits the generated data back
to the repository.

You can schedule the command with cron (for example `0 6 * * *`) to run it once
per day.

## Development

The project targets Python 3.11+. Run the standard library syntax check before
submitting a change:

```bash
python -m compileall openreview_crawler
```


## Data layout

Each run creates a directory per forum (submission) that contains:

* `submission.json` – the submission metadata and the latest revision payload returned by the API.
* `forum.json` – the full discussion thread including reviews, comments, rebuttals and decisions.
* `score_history.json` – a condensed timeline of score/decision changes extracted from the forum notes.
* `pdf/` – an append-only collection of PDFs; every stored file is annotated with the originating note id and timestamp and tracked via `index.json`.
* `docling/<label>/` – Markdown exports for each stored PDF produced by Docling.
  Each directory contains `paper.md`, extracted tables in `tables/`, referenced
  images in `figures/`, optional page renders under `page_images/`, and
  `references.md` when the bibliography can be isolated.

The scraper keeps an ISO8601 timestamp in `state.json` to resume from the last successful run.
