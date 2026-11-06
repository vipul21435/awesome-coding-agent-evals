"""Re-fetch every entry's page and compare its licence and year with the data file.

This is the only script here that uses the network, and it is not run in CI.

    python scripts/recheck.py [--data PATH] [--only github|arxiv|hf] [--delay SECONDS]
                              [--timeout SECONDS] [--json PATH]

Sources, by URL:
  github.com/OWNER/REPO          -> the GitHub REST API (licence SPDX id, created_at, archived,
                                    and the canonical name, to spot moved repositories)
  arxiv.org/abs/ID               -> the arXiv abstract page (licence link, first-version date)
  huggingface.co/datasets/ID     -> the Hugging Face dataset API (card licence, createdAt)

Set GITHUB_TOKEN to raise the GitHub API rate limit. The exit code is 0 when every page
was fetched, 1 when any fetch failed. Licence and year differences are reported, not
treated as errors, because a repository's creation date is not always its first release.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

USER_AGENT = "awesome-coding-agent-evals-recheck/0.1 (+https://github.com/vipul21435/awesome-coding-agent-evals)"

GITHUB_RE = re.compile(r"^https://github\.com/([^/#?]+)/([^/#?]+?)(?:\.git)?/?$")
ARXIV_RE = re.compile(r"^https://arxiv\.org/abs/(\d{4}\.\d{4,5})(v\d+)?/?$")
HF_RE = re.compile(r"^https://huggingface\.co/datasets/([^/#?]+/[^/#?]+)/?$")
CANONICAL = {
    "github": "https://github.com/{}",
    "arxiv": "https://arxiv.org/abs/{}",
    "hf": "https://huggingface.co/datasets/{}",
}

# Licence URLs that arXiv links from an abstract page, mapped to the wording in the data file.
ARXIV_LICENCES = {
    "arxiv.org/licenses/nonexclusive-distrib/1.0": "arXiv non-exclusive",
    "creativecommons.org/licenses/by/4.0": "CC BY 4.0",
    "creativecommons.org/licenses/by-sa/4.0": "CC BY-SA 4.0",
    "creativecommons.org/licenses/by-nc/4.0": "CC BY-NC 4.0",
    "creativecommons.org/licenses/by-nc-sa/4.0": "CC BY-NC-SA 4.0",
    "creativecommons.org/licenses/by-nc-nd/4.0": "CC BY-NC-ND 4.0",
    "creativecommons.org/publicdomain/zero/1.0": "CC0 1.0",
}


def classify(url: str) -> tuple[str, str]:
    """Return (source, key) for a URL: github, arxiv, hf or other."""
    if m := GITHUB_RE.match(url):
        return "github", f"{m.group(1)}/{m.group(2)}"
    if m := ARXIV_RE.match(url):
        return "arxiv", m.group(1)
    if m := HF_RE.match(url):
        return "hf", m.group(1)
    return "other", url


def canonical_url(url: str) -> str | None:
    """The one spelling of a URL that the list uses: no arXiv version, no trailing slash or
    '.git'. None when the URL is not a form this script can fetch."""
    source, key = classify(url)
    return CANONICAL[source].format(key) if source in CANONICAL else None


def norm_licence(text: str | None) -> str:
    """Reduce a licence string to a comparable token: 'CC-BY-SA-4.0' == 'CC BY-SA 4.0'."""
    if not text:
        return "not stated"
    t = text.lower().replace("(paper)", "").strip()
    t = re.sub(r"[\s_-]+", "-", t).strip("-")
    aliases = {
        "noassertion": "other",
        "unknown": "not stated",
        "none": "not stated",
        "not-stated": "not stated",
        "arxiv-non-exclusive": "arxiv-nonexclusive",
        "cc0-1.0": "cc0-1.0",
    }
    return aliases.get(t, t)


def parse_github(payload: dict) -> dict:
    lic = payload.get("license") or {}
    spdx = lic.get("spdx_id")
    return {
        "licence": None if spdx in (None, "") else spdx,
        "year": int(payload["created_at"][:4]) if payload.get("created_at") else None,
        "archived": bool(payload.get("archived")),
        "canonical": payload.get("full_name"),
    }


def parse_arxiv(page: str) -> dict:
    m = re.search(r'<meta name="citation_date" content="(\d{4})/', page)
    year = int(m.group(1)) if m else None
    licence = None
    lm = re.search(r'<div class="abs-license">\s*<a href="([^"]+)"', page)
    if lm:
        href = re.sub(r"^https?://", "", lm.group(1)).rstrip("/")
        licence = ARXIV_LICENCES.get(href, href)
    cm = re.search(r'<td class="tablecell comments[^"]*">(.*?)</td>', page, re.S)
    comments = html.unescape(re.sub(r"<[^>]+>", "", cm.group(1))).strip() if cm else ""
    jm = re.search(r'<td class="tablecell jref">(.*?)</td>', page, re.S)
    jref = html.unescape(re.sub(r"<[^>]+>", "", jm.group(1))).strip() if jm else ""
    return {"licence": licence, "year": year, "comments": comments, "jref": jref}


def parse_hf(payload: dict) -> dict:
    card = payload.get("cardData") or {}
    lic = card.get("license")
    if isinstance(lic, list):
        lic = ", ".join(lic) if lic else None
    created = payload.get("createdAt") or ""
    return {
        "licence": lic,
        "year": int(created[:4]) if created[:4].isdigit() else None,
        "canonical": payload.get("id"),
    }


def licence_title(text: str) -> str | None:
    """First non-blank line of a licence file, used when GitHub cannot name the licence."""
    for line in text.splitlines():
        line = line.strip().strip("#").strip()
        if line:
            return line
    return None


def licence_matches(stated: str, seen: dict) -> bool:
    if norm_licence(stated) == norm_licence(seen.get("licence")):
        return True
    title = seen.get("licence_title")
    if title:
        # The title must contain the whole stated licence, never the other way round:
        # a generic first line such as "License" would otherwise match anything.
        a, b = norm_licence(stated), norm_licence(title)
        return a in b or _cc_words(a) in b
    return False


def _cc_words(token: str) -> str:
    """Spell a short CC token the way a licence file's title does: cc-by-nc-4.0 ->
    attribution-noncommercial-4.0-international."""
    m = re.fullmatch(r"cc-(by(?:-nc)?(?:-sa|-nd)?)-(\d\.\d)", token)
    if not m:
        return token
    words = {"by": "attribution", "nc": "noncommercial", "sa": "sharealike", "nd": "noderivatives"}
    parts = [words[p] for p in m.group(1).split("-")]
    return "-".join(parts) + f"-{m.group(2)}-international"


def compare(entry: dict, source: str, key: str, seen: dict) -> list[str]:
    """Return the differences between a data record and what its page shows."""
    notes = []
    stated = entry["licence"]
    if not licence_matches(stated, seen):
        notes.append(f"licence: data {stated!r}, page {seen.get('licence') or 'not stated'!r}")
    if seen.get("year") is not None and seen["year"] != entry["year"]:
        notes.append(f"year: data {entry['year']}, page {seen['year']}")
    canonical = seen.get("canonical")
    if canonical and canonical.lower() != key.lower():
        notes.append(f"moved: now {canonical}")
    if seen.get("archived"):
        notes.append("archived")
    return notes


def fetch(url: str, timeout: float, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def observe(source: str, key: str, timeout: float) -> dict:
    if source == "github":
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        seen = parse_github(json.loads(fetch(f"https://api.github.com/repos/{key}", timeout, headers)))
        if seen["licence"] == "NOASSERTION":
            # GitHub found a licence file but could not match it to an SPDX id; read its title.
            raw = json.loads(fetch(f"https://api.github.com/repos/{key}/license", timeout, headers))
            text = base64.b64decode(raw.get("content", "")).decode("utf-8", "replace")
            seen["licence_title"] = licence_title(text)
        return seen
    if source == "arxiv":
        return parse_arxiv(fetch(f"https://arxiv.org/abs/{key}", timeout).decode("utf-8", "replace"))
    if source == "hf":
        return parse_hf(json.loads(fetch(f"https://huggingface.co/api/datasets/{key}", timeout)))
    raise ValueError(f"no fetcher for {key}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=render.DATA,
                    help="path to entries.json (default data/entries.json)")
    ap.add_argument("--only", choices=("github", "arxiv", "hf"), help="check only entries from this source")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-request timeout (default 30)")
    ap.add_argument("--json", type=Path, help="also write the full report to this file")
    args = ap.parse_args(argv)

    data = render.load(args.data)
    report = []
    failed = 0
    for entry in data["entries"]:
        source, key = classify(entry["url"])
        if args.only and source != args.only:
            continue
        row = {"name": entry["name"], "url": entry["url"], "source": source}
        try:
            seen = observe(source, key, args.timeout)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            failed += 1
            row.update(ok=False, error=str(exc))
            print(f"FAIL  {entry['name']}: {exc}")
        else:
            notes = compare(entry, source, key, seen)
            row.update(ok=True, seen=seen, notes=notes)
            status = "DIFF " if notes else "same "
            print(f"{status} {entry['name']}" + (f": {'; '.join(notes)}" if notes else ""))
        report.append(row)
        time.sleep(args.delay)

    by_source: dict[str, int] = {}
    for row in report:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    differing = sum(1 for r in report if r.get("notes"))
    print(
        f"checked {len(report)} entries ({', '.join(f'{k} {v}' for k, v in sorted(by_source.items()))}); "
        f"fetched {len(report) - failed}, failed {failed}, with differences {differing}"
    )
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
