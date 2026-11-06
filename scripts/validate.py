"""Check every record in data/entries.json and that README.md matches it.

    python scripts/validate.py [--data PATH] [--readme PATH] [--min-year N] [--max-year N]

Exits 0 when there are no problems, 1 otherwise, printing one line per problem.
No network access: links are checked for shape only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

REQUIRED = ("name", "url", "section", "kind", "year", "licence", "summary", "fetched")
KINDS = {"paper", "code", "dataset", "code+data"}
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[^\s|()<>]*)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SUMMARY = 220


def check_data(data: dict, min_year: int = 1990, max_year: int = 2026) -> list[str]:
    problems: list[str] = []
    for key in ("fetched", "sections", "entries"):
        if key not in data:
            problems.append(f"top level: missing '{key}'")
    if problems:
        return problems
    section_ids = [s.get("id") for s in data["sections"]]
    for s in data["sections"]:
        for key in ("id", "title", "blurb"):
            if not s.get(key):
                problems.append(f"section {s.get('id')!r}: missing '{key}'")
    if len(set(section_ids)) != len(section_ids):
        problems.append("sections: duplicate section id")
    seen_urls: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    used_sections: set[str] = set()
    for i, e in enumerate(data["entries"]):
        label = f"entry {i} ({e.get('name', '?')})"
        missing = [k for k in REQUIRED if e.get(k) in (None, "")]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
            continue
        extra = set(e) - set(REQUIRED) - {"venue"}
        if extra:
            problems.append(f"{label}: unknown field(s) {', '.join(sorted(extra))}")
        if not URL_RE.match(e["url"]):
            problems.append(f"{label}: url is not a plain https URL: {e['url']}")
        norm = e["url"].rstrip("/").lower()
        if norm in seen_urls:
            problems.append(f"{label}: duplicate url, also used by {seen_urls[norm]}")
        seen_urls[norm] = e["name"]
        lname = e["name"].lower()
        if lname in seen_names:
            problems.append(f"{label}: duplicate name")
        seen_names[lname] = e["name"]
        if e["section"] not in section_ids:
            problems.append(f"{label}: unknown section {e['section']!r}")
        used_sections.add(e["section"])
        if e["kind"] not in KINDS:
            problems.append(f"{label}: kind must be one of {sorted(KINDS)}")
        if not isinstance(e["year"], int) or isinstance(e["year"], bool):
            problems.append(f"{label}: year must be an integer")
        elif not min_year <= e["year"] <= max_year:
            problems.append(f"{label}: year {e['year']} outside {min_year}-{max_year}")
        if not DATE_RE.match(str(e["fetched"])):
            problems.append(f"{label}: fetched must be YYYY-MM-DD")
        s = e["summary"]
        if len(s) > MAX_SUMMARY:
            problems.append(f"{label}: summary longer than {MAX_SUMMARY} characters")
        if not s.endswith("."):
            problems.append(f"{label}: summary should be one sentence ending in a period")
        if "\n" in s:
            problems.append(f"{label}: summary must not contain newlines")
    for sid in section_ids:
        if sid not in used_sections:
            problems.append(f"section {sid!r}: has no entries")
    return problems


def check_readme(data: dict, readme_text: str) -> list[str]:
    try:
        expected = render.rendered_readme(data, readme_text)
    except ValueError as exc:
        return [str(exc)]
    if expected != readme_text:
        return ["README.md is out of date with the data file; run: python scripts/render.py"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=render.DATA)
    ap.add_argument("--readme", type=Path, default=render.README)
    ap.add_argument("--min-year", type=int, default=1990)
    ap.add_argument("--max-year", type=int, default=2026)
    args = ap.parse_args(argv)
    data = render.load(args.data)
    problems = check_data(data, args.min_year, args.max_year)
    if not problems:
        problems += check_readme(data, args.readme.read_text(encoding="utf-8"))
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"ok: {len(data['entries'])} entries in {len(data['sections'])} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
