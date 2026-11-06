# Changelog

## Unreleased

### Fixed

- The validator accepted GitHub and Hugging Face URLs with a space, `|` or `)` in them, so a URL with a trailing space listed the same page twice. Each URL part now allows only the characters the host allows in names, and a final newline no longer matches.

## 0.1.0 - 2026-11-06

### Added

- Data file `data/entries.json` with 99 entries in 7 sections (function-level benchmarks, repository-level and issue-resolution benchmarks, agent harnesses, training environments and datasets, terminal and tool-use benchmarks, evaluation methodology, contamination and leakage analyses). Each entry was fetched on 2026-11-06, with year and licence taken from its page.
- `scripts/render.py` writes the README entry tables, table of contents and licence counts table from the data file; `--check` reports a stale README.
- `scripts/validate.py` checks required fields and their types, control characters and markup, URL forms that `recheck.py` can fetch (written one way, so the same page cannot be listed twice), duplicate URLs and names, section titles, year and fetch-date ranges, one-sentence summaries, licence spellings with the ` (paper)` suffix for papers, and README sync. An unreadable file gives one line and exit code 2.
- `scripts/recheck.py` fetches every page again and reports licence, year, archived and moved differences, reads licence files when GitHub reports `NOASSERTION`, counts dropped connections as failed fetches, and reports a journal reference for a paper with no venue. It needs the network and is not run in CI.
- A recheck run over all 99 entries, with its output and the five differences explained in the README.
- Help text for every script option.
- Tests for the three scripts, run with pytest and hypothesis.
- A CI workflow that runs validation, the render check, ruff and the tests offline on Python 3.10 and 3.13.
- README sections on install and quickstart, how entries are chosen and checked, how the scripts work, re-checking the pages, related lists, the author's own tools (marked as such, each tied to a listed paper it relates to) and contributing.

### Known limitations

- Coverage is a selection, and the validator accepts only some URL forms; see [Limitations](README.md#limitations) in the README.
