# Changelog

## Unreleased

- Author tools section regrouped by topic, each tool tied to the listed paper it relates to; contamscan linked.
- Entry tables now follow the selection rules directly; Quickstart, Re-checking and Limitations moved below them.
- Agentless and SWE-agent papers moved to the harness section, Benchmarks as Software to methodology.
- `recheck.py` counts a licence-file title as a match only when it contains the whole stated licence.
- `validate.py` defaults the year bound to the current year and checks per-entry fetch dates.
- Help text for every script option; pyproject version set to 0.2.0.

## 0.2.0 - 2026-11-06

- 22 more entries (89 in all): MultiPL-E, ClassEval, the Aider polyglot benchmark, Commit0, FEA-Bench, SWT-Bench, SWE-Bench Pro, the OpenHands paper, SWE-ReX, Inspect, Inspect Evals, Terminal-Bench 2.0 and its maintenance paper, AppWorld, MLE-bench, Cybench, and six papers on variance, harnesses, patch correctness, weak tests, reward hacking and leakage.
- `scripts/recheck.py` re-fetches every page and reports licence, year, archived and moved differences; not run in CI.
- Licence counts table rendered from the data file.
- Ruff lint in CI; Limitations section in the README.

## 0.1.0 - 2026-11-06

- Data file `data/entries.json` with 67 entries in 7 sections, each fetched on 2026-11-06 with year and licence from its page.
- `scripts/render.py` renders the README tables and table of contents from the data file; `--check` reports a stale README.
- `scripts/validate.py` checks required fields, URL shape, year range, duplicate URLs and names, known sections and README sync.
- Tests for both scripts, and a CI workflow that runs them offline on Python 3.10 and 3.13.
- Section listing the author's own tools, marked as such.
