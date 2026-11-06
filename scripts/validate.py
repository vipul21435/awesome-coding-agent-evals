"""Check every record in data/entries.json and that README.md matches it.

    python scripts/validate.py [--data PATH] [--readme PATH] [--min-year N] [--max-year N]

Exits 0 when there are no problems, 1 when there are (one line per problem), and 2
when a file cannot be read or parsed.
No network access: links are checked for shape only, and must be one of the three
forms scripts/recheck.py can fetch (GitHub repository, arXiv abstract, Hugging Face dataset).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recheck  # noqa: E402
import render  # noqa: E402

REQUIRED = ("name", "url", "section", "kind", "year", "licence", "summary", "fetched")
STRING_FIELDS = ("name", "url", "section", "kind", "licence", "summary", "fetched", "venue")
KINDS = {"paper", "code", "dataset", "code+data"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SUMMARY = 220
# A period, '!' or '?', then space and a capital letter, means a second sentence has started,
# unless the period ends one of these abbreviations.
SECOND_SENTENCE_RE = re.compile(r"[.!?]\s+[A-Z]")
ABBREVIATIONS = ("e.g.", "i.e.", "et al.", "vs.", "cf.")
# Licences for code and data, spelled as in the data file. Papers use the arXiv licences in
# scripts/recheck.py with " (paper)" appended. A new licence is added here on purpose.
CODE_LICENCES = {
    "not stated",
    "MIT",
    "Apache-2.0",
    "BSD-3-Clause",
    "GPL-3.0",
    "CC BY 4.0",
    "CC BY-SA 4.0",
    "CC BY-NC 4.0",
    "CC BY-NC-SA 4.0",
    "CC0 1.0",
    "BSD 3-Clause License with Machine Learning Restriction",
    "SONAR Source-Available License v1.0",
}
PAPER_LICENCES = {f"{name} (paper)" for name in recheck.ARXIV_LICENCES.values()}
# Markup that GitHub would hide or that would end the generated block early.
MARKUP = ("<", "-->")
MIN_YEAR = 1990
# Anchors of the headings render.py writes itself.
RESERVED_ANCHORS = {render.anchor("Contents"), render.anchor("Licences at a glance")}


def parse_date(text: object) -> dt.date | None:
    """A real YYYY-MM-DD date, or None."""
    if not DATE_RE.match(str(text)):
        return None
    try:
        return dt.date.fromisoformat(str(text))
    except ValueError:
        return None


def check_data(
    data: dict, min_year: int = MIN_YEAR, max_year: int | None = None, today: dt.date | None = None
) -> list[str]:
    """Return one line per problem. max_year defaults to the current year; today is a
    parameter so tests can fix it."""
    today = today or dt.date.today()
    if max_year is None:
        max_year = today.year
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["top level: must be a JSON object"]
    for key in ("fetched", "sections", "entries"):
        if key not in data:
            problems.append(f"top level: missing '{key}'")
    for key in ("sections", "entries"):
        if key in data and not isinstance(data[key], list):
            problems.append(f"top level: {key} must be a list")
    if problems:
        return problems
    top_fetched = parse_date(data["fetched"])
    if top_fetched is None:
        problems.append("top level: fetched must be a real YYYY-MM-DD date")
    elif top_fetched > today:
        problems.append(f"top level: fetched {data['fetched']} is in the future")
    sections = []
    for j, s in enumerate(data["sections"]):
        if not isinstance(s, dict):
            problems.append(f"section {j}: must be an object")
            continue
        if s.get("id") is not None and not isinstance(s["id"], str):
            # skipped, so an unhashable id cannot break the duplicate check below
            problems.append(f"section {j}: id must be a string")
            continue
        sections.append(s)
        for key in ("id", "title", "blurb"):
            if s.get(key) is None or (isinstance(s[key], str) and not s[key].strip()):
                problems.append(f"section {s.get('id')!r}: missing '{key}'")
            elif not isinstance(s[key], str):
                problems.append(f"section {s.get('id')!r}: {key} must be a string")
            elif render.CONTROL_RE.search(s[key]):
                problems.append(f"section {s.get('id')!r}: {key} contains a line break or control character")
    section_ids = [s.get("id") for s in sections]
    # Compare anchors, not titles: titles that differ only in case or punctuation share one.
    anchors = [render.anchor(s["title"]) for s in sections if isinstance(s.get("title"), str)]
    if len(set(anchors)) != len(anchors):
        problems.append("sections: duplicate section title (two headings would share one anchor)")
    for s in sections:
        if isinstance(s.get("title"), str) and s["title"].strip():
            a = render.anchor(s["title"])
            if a in RESERVED_ANCHORS:
                problems.append(f"section {s.get('id')!r}: title anchor #{a} is used by a heading the "
                                "renderer writes")
            elif not a:
                problems.append(f"section {s.get('id')!r}: title gives an empty anchor")
    for s in sections:
        for key in ("title", "blurb"):
            if isinstance(s.get(key), str) and any(m in s[key] for m in MARKUP):
                problems.append(f"section {s.get('id')!r}: {key} must not contain '<' or '-->'")
    if len(set(section_ids)) != len(section_ids):
        problems.append("sections: duplicate section id")
    seen_urls: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    used_sections: set[str] = set()
    for i, e in enumerate(data["entries"]):
        if not isinstance(e, dict):
            problems.append(f"entry {i}: must be an object")
            continue
        label = f"entry {i} ({e.get('name', '?')})"
        missing = [k for k in REQUIRED if e.get(k) is None or (isinstance(e[k], str) and not e[k].strip())]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
            continue
        wrong = [k for k in STRING_FIELDS if k in e and not isinstance(e[k], str)]
        if wrong:
            problems += [f"{label}: {k} must be a string" for k in wrong]
            continue
        problems += [f"{label}: {k} contains a line break or control character"
                     for k in STRING_FIELDS if k in e and render.CONTROL_RE.search(e[k])]
        problems += [f"{label}: {k} must not contain '<' or '-->'"
                     for k in STRING_FIELDS if k in e and any(m in e[k] for m in MARKUP)]
        if "[" in e["name"] or "]" in e["name"]:
            problems.append(f"{label}: name must not contain '[' or ']' (it is the link text)")
        problems += check_licence(label, e)
        extra = set(e) - set(REQUIRED) - {"venue"}
        if extra:
            problems.append(f"{label}: unknown field(s) {', '.join(sorted(extra))}")
        canonical = recheck.canonical_url(e["url"])
        if canonical is None:
            problems.append(
                f"{label}: url must be https://github.com/OWNER/REPO, https://arxiv.org/abs/ID or "
                f"https://huggingface.co/datasets/OWNER/NAME: {e['url']}"
            )
        else:
            if canonical != e["url"]:
                problems.append(f"{label}: url {e['url']}: write it as {canonical}")
            norm = canonical.lower()
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
        fetched = parse_date(e["fetched"])
        if fetched is None:
            problems.append(f"{label}: fetched must be a real YYYY-MM-DD date")
        elif fetched > today:
            problems.append(f"{label}: fetched {e['fetched']} is in the future")
        elif top_fetched is not None and fetched > top_fetched:
            problems.append(f"{label}: fetched {e['fetched']} is later than the top-level {data['fetched']}")
        elif isinstance(e["year"], int) and e["year"] > fetched.year:
            problems.append(f"{label}: year {e['year']} is later than its fetch date")
        s = e["summary"]
        if len(s) > MAX_SUMMARY:
            problems.append(f"{label}: summary longer than {MAX_SUMMARY} characters")
        if not s.endswith(".") or has_second_sentence(s):
            problems.append(f"{label}: summary should be one sentence ending in a period")
    for sid in section_ids:
        if sid not in used_sections:
            problems.append(f"section {sid!r}: has no entries")
    return problems


def has_second_sentence(text: str) -> bool:
    """True when a sentence end is followed by a capital letter. A period that ends one of
    ABBREVIATIONS, written as a whole word, does not end a sentence."""
    for m in SECOND_SENTENCE_RE.finditer(text):
        before = text[: m.start() + 1]
        if not any(before.endswith(a) and (len(before) == len(a) or not before[-len(a) - 1].isalnum())
                   for a in ABBREVIATIONS):
            return True
    return False


def check_licence(label: str, e: dict) -> list[str]:
    """The licence must be a known spelling, with ' (paper)' on papers and only on papers."""
    lic, is_paper = e["licence"], e["kind"] == "paper"
    if lic.endswith(" (paper)") != is_paper:
        if is_paper:
            return [f"{label}: a paper's licence ends in ' (paper)', e.g. 'CC BY 4.0 (paper)'"]
        return [f"{label}: only papers have ' (paper)' in the licence"]
    known = PAPER_LICENCES if is_paper else CODE_LICENCES
    if lic in known:
        return []
    near = [k for k in known if k.lower() == lic.lower()]
    hint = f" (did you mean {near[0]!r}?)" if near else ""
    return [f"{label}: licence {lic!r} is not in the known list{hint}; "
            "a new licence is added to CODE_LICENCES in scripts/validate.py"]


def check_readme(data: dict, readme_text: str) -> list[str]:
    """One problem if the README's generated block differs from what the data renders to."""
    try:
        expected = render.rendered_readme(data, readme_text)
    except ValueError as exc:
        return [str(exc)]
    if expected != readme_text:
        return ["README.md is out of date with the data file; run: python scripts/render.py"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=render.DATA,
                    help="path to entries.json (default data/entries.json)")
    ap.add_argument("--readme", type=Path, default=render.README,
                    help="path to README.md (default README.md)")
    ap.add_argument("--min-year", type=int, default=MIN_YEAR,
                    help=f"earliest allowed year (default {MIN_YEAR})")
    ap.add_argument("--max-year", type=int, default=None,
                    help="latest allowed year (default: the current year)")
    args = ap.parse_args(argv)
    try:
        data = render.load(args.data)
    except (OSError, ValueError) as exc:
        print(render.describe_error(args.data, exc), file=sys.stderr)
        return 2
    problems = check_data(data, args.min_year, args.max_year)
    if not problems:
        try:
            readme_text = args.readme.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(render.describe_error(args.readme, exc), file=sys.stderr)
            return 2
        problems += check_readme(data, readme_text)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"ok: {len(data['entries'])} entries in {len(data['sections'])} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
