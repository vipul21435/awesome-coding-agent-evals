"""Offline tests for scripts/recheck.py: parsers and comparison only, no network."""

import base64
import json

import pytest

import recheck

ARXIV_PAGE = """
<meta name="citation_title" content="A Paper" /><meta name="citation_date" content="2023/10/10" />
<meta name="citation_online_date" content="2024/11/11" />
<td class="tablecell comments mathjax">Code at <a href="https://example.org">this URL</a> ICLR 2024</td>
<td class="tablecell jref">Proc. Example &amp; Co. 2024</td>
<div class="abs-license"><a href="http://creativecommons.org/licenses/by/4.0/" title="Rights">
"""


def entry(**kw):
    base = {"name": "X", "url": "https://github.com/a/b", "licence": "MIT", "year": 2024}
    base.update(kw)
    return base


def test_classify_sources():
    assert recheck.classify("https://github.com/SWE-bench/SWE-bench") == ("github", "SWE-bench/SWE-bench")
    assert recheck.classify("https://arxiv.org/abs/2310.06770") == ("arxiv", "2310.06770")
    assert recheck.classify("https://arxiv.org/abs/2310.06770v2") == ("arxiv", "2310.06770")
    assert recheck.classify("https://huggingface.co/datasets/a/b") == ("hf", "a/b")
    assert recheck.classify("https://example.org/x")[0] == "other"
    assert recheck.classify("https://github.com/a/b/tree/main")[0] == "other"
    assert recheck.classify("https://github.com/a/b.git") == ("github", "a/b")
    assert recheck.canonical_url("https://arxiv.org/abs/2310.06770v2/") == "https://arxiv.org/abs/2310.06770"
    assert recheck.canonical_url("https://www.github.com/a/b") is None


def test_norm_licence_equates_spellings():
    n = recheck.norm_licence
    assert n("CC-BY-SA-4.0") == n("CC BY-SA 4.0") == n("cc-by-sa-4.0")
    assert n("CC BY 4.0 (paper)") == n("CC BY 4.0")
    assert n("arXiv non-exclusive (paper)") == n("arxiv-nonexclusive")
    assert n(None) == n("not stated") == n("unknown")
    assert n("NOASSERTION") == "other"


def test_parse_arxiv_page():
    seen = recheck.parse_arxiv(ARXIV_PAGE)
    assert seen["year"] == 2023  # first version, not the latest
    assert seen["licence"] == "CC BY 4.0"
    assert "ICLR 2024" in seen["comments"]
    assert seen["jref"] == "Proc. Example & Co. 2024"


def test_parse_arxiv_unknown_licence_and_missing_fields():
    page = '<div class="abs-license"><a href="https://example.org/lic/">x</a>'
    seen = recheck.parse_arxiv(page)
    assert seen["licence"] == "example.org/lic"
    assert seen["year"] is None and seen["comments"] == "" and seen["jref"] == ""


def test_parse_github_and_hf():
    gh = recheck.parse_github({"license": {"spdx_id": "MIT"}, "created_at": "2023-10-01T00:00:00Z",
                               "archived": True, "full_name": "a/b"})
    assert gh == {"licence": "MIT", "year": 2023, "archived": True, "canonical": "a/b"}
    assert recheck.parse_github({"license": None})["licence"] is None
    hf = recheck.parse_hf({"id": "a/b", "createdAt": "2024-03-19T19:00:57.000Z",
                           "cardData": {"license": ["mit", "cc-by-4.0"]}})
    assert hf == {"licence": "mit, cc-by-4.0", "year": 2024, "canonical": "a/b"}
    assert recheck.parse_hf({})["licence"] is None


def test_compare_reports_each_kind_of_difference():
    seen = {"licence": "Apache-2.0", "year": 2022, "canonical": "c/d", "archived": True}
    notes = recheck.compare(entry(), "github", "a/b", seen)
    assert any(n.startswith("licence") for n in notes)
    assert any(n.startswith("year") for n in notes)
    assert any(n.startswith("moved") for n in notes)
    assert "archived" in notes
    same = {"licence": "mit", "year": 2024, "canonical": "a/b"}
    assert recheck.compare(entry(), "github", "A/B", same) == []


def test_licence_file_title_used_when_spdx_unknown():
    seen = {"licence": "NOASSERTION", "licence_title": "Attribution-NonCommercial 4.0 International"}
    assert recheck.licence_matches("CC BY-NC 4.0", seen)
    assert not recheck.licence_matches("CC BY-SA 4.0", seen)
    seen = {"licence": "NOASSERTION", "licence_title": "SONAR Source-Available License v1.0"}
    assert recheck.licence_matches("SONAR Source-Available License v1.0", seen)
    generic = {"licence": "NOASSERTION", "licence_title": "License"}
    assert not recheck.licence_matches("SONAR Source-Available License v1.0", generic)
    assert not recheck.licence_matches("MIT", generic)
    # whole words only: 'mit' inside 'limited' is not a match
    custom = {"licence": "NOASSERTION", "licence_title": "Limited Use License Agreement"}
    assert not recheck.licence_matches("MIT", custom)
    assert recheck.licence_matches("MIT", {"licence": "NOASSERTION", "licence_title": "The MIT License"})
    apache = {"licence": "NOASSERTION", "licence_title": "Apache License, Version 2.0"}
    assert recheck.licence_matches("Apache-2.0", apache)
    assert not recheck.licence_matches("MIT", apache)
    full = {"licence": "NOASSERTION",
            "licence_title": "Creative Commons Attribution-NonCommercial 4.0 International Public License"}
    assert recheck.licence_matches("CC BY-NC 4.0", full)
    assert not recheck.licence_matches("CC BY 4.0", full)
    assert recheck.licence_title("\n\n# Some Licence\nbody") == "Some Licence"
    assert recheck.licence_title("  \n") is None


def test_main_with_stubbed_fetch(tmp_path, monkeypatch, capsys):
    data = {"fetched": "2026-11-06", "sections": [], "entries": [
        entry(name="Repo", url="https://github.com/a/b"),
        entry(name="Odd", url="https://github.com/c/d", licence="CC BY-NC 4.0"),
        entry(name="Paper", url="https://arxiv.org/abs/2310.00001", licence="CC BY 4.0 (paper)", year=2023),
        entry(name="Set", url="https://huggingface.co/datasets/e/f", licence="not stated"),
        entry(name="Gone", url="https://huggingface.co/datasets/g/h"),
    ]}
    path = tmp_path / "entries.json"
    path.write_text(json.dumps(data))
    lic_file = base64.b64encode(b"Attribution-NonCommercial 4.0 International\n").decode()
    pages = {
        "https://api.github.com/repos/a/b": {"license": {"spdx_id": "MIT"}, "created_at": "2024-01-01",
                                             "full_name": "a/b"},
        "https://api.github.com/repos/c/d": {"license": {"spdx_id": "NOASSERTION"},
                                             "created_at": "2024-01-01", "full_name": "c/d"},
        "https://api.github.com/repos/c/d/license": {"content": lic_file},
        "https://arxiv.org/abs/2310.00001": ARXIV_PAGE,
        "https://huggingface.co/api/datasets/e/f": {"id": "e/f", "createdAt": "2024-05-01"},
    }

    def fake_fetch(url, timeout, headers=None):
        if url not in pages:
            raise recheck.urllib.error.URLError("404")
        body = pages[url]
        return (body if isinstance(body, str) else json.dumps(body)).encode()

    monkeypatch.setattr(recheck, "fetch", fake_fetch)
    out_json = tmp_path / "report.json"
    rc = recheck.main(["--data", str(path), "--delay", "0", "--json", str(out_json)])
    out = capsys.readouterr().out
    assert rc == 1  # one fetch failed
    assert "FAIL  Gone" in out
    assert "checked 5 entries (arxiv 1, github 2, hf 2); fetched 4, failed 1, with differences 0" in out
    report = json.loads(out_json.read_text())
    assert [r["ok"] for r in report] == [True, True, True, True, False]

    rc = recheck.main(["--data", str(path), "--delay", "0", "--only", "arxiv"])
    assert rc == 0
    assert "checked 1 entries" in capsys.readouterr().out


def test_observe_rejects_unknown_source():
    with pytest.raises(ValueError):
        recheck.observe("other", "https://example.org", 1.0)


def test_main_reports_bad_json_in_one_line(tmp_path, capsys):
    data = tmp_path / "entries.json"
    data.write_text("[1,")
    assert recheck.main(["--data", str(data), "--delay", "0"]) == 2
    assert "line 1 column" in capsys.readouterr().err
