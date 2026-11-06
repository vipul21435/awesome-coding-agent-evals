# Changelog

## 0.1.0 - 2026-11-06

- Data file `data/entries.json` with 67 entries in 7 sections, each fetched on 2026-11-06 with year and licence from its page.
- `scripts/render.py` renders the README tables and table of contents from the data file; `--check` reports a stale README.
- `scripts/validate.py` checks required fields, URL shape, year range, duplicate URLs and names, known sections and README sync.
- Tests for both scripts, and a CI workflow that runs them offline on Python 3.10 and 3.13.
- Section listing the author's own tools, marked as such.
