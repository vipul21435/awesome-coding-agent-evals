import copy

import pytest

import render


def sample():
    return {
        "fetched": "2026-11-06",
        "sections": [
            {"id": "a", "title": "Alpha benchmarks", "blurb": "First."},
            {"id": "b", "title": "Beta and gamma", "blurb": "Second."},
        ],
        "entries": [
            {"name": "Zed", "url": "https://example.org/z", "section": "a", "kind": "code",
             "year": 2024, "licence": "MIT", "summary": "Z thing.", "fetched": "2026-11-06"},
            {"name": "Aye", "url": "https://example.org/a", "section": "a", "kind": "paper",
             "year": 2021, "licence": "CC BY 4.0 (paper)", "venue": "ICLR 2022",
             "summary": "A | pipe.", "fetched": "2026-11-06"},
            {"name": "Bee", "url": "https://example.org/b", "section": "b", "kind": "dataset",
             "year": 2023, "licence": "not stated", "summary": "B thing.", "fetched": "2026-11-06"},
        ],
    }


def test_anchor_matches_github_style():
    assert render.anchor("Terminal and tool-use benchmarks") == "terminal-and-tool-use-benchmarks"
    assert render.anchor("Beta, and (gamma)") == "beta-and-gamma"


def test_block_has_toc_counts_and_rows_sorted_by_year():
    block = render.render_block(sample())
    assert "- [Alpha benchmarks](#alpha-benchmarks) (2)" in block
    assert "- [Beta and gamma](#beta-and-gamma) (1)" in block
    assert block.index("[Aye]") < block.index("[Zed]")
    assert "3 entries, all fetched on 2026-11-06." in block


def test_pipes_escaped_and_venue_appended():
    block = render.render_block(sample())
    assert "A \\| pipe." in block
    assert "CC BY 4.0 (paper); ICLR 2022" in block


def test_splice_replaces_only_marked_block():
    text = f"intro\n{render.BEGIN}\nold\n{render.END}\noutro\n"
    out = render.rendered_readme(sample(), text)
    assert out.startswith("intro\n") and out.endswith("\noutro\n")
    assert "old" not in out
    assert render.rendered_readme(sample(), out) == out


def test_splice_without_markers_raises():
    with pytest.raises(ValueError):
        render.splice("no markers here", "x")


def test_check_mode_reports_stale_readme(tmp_path):
    import json
    data = tmp_path / "entries.json"
    data.write_text(json.dumps(sample()))
    readme = tmp_path / "README.md"
    readme.write_text(f"t\n{render.BEGIN}\n{render.END}\n")
    assert render.main(["--check", "--data", str(data), "--readme", str(readme)]) == 1
    assert render.main(["--data", str(data), "--readme", str(readme)]) == 0
    assert render.main(["--check", "--data", str(data), "--readme", str(readme)]) == 0


def test_render_does_not_mutate_input():
    d = sample()
    before = copy.deepcopy(d)
    render.render_block(d)
    assert d == before


def test_licence_table_and_kind_line():
    block = render.render_block(sample())
    assert "| Licence as stated | Code and data | Papers |" in block
    assert "| CC BY 4.0 | 0 | 1 |" in block
    assert "| MIT | 1 | 0 |" in block
    assert "By kind: code 1, dataset 1, paper 1." in block
    assert "- [Licences at a glance](#licences-at-a-glance)" in block


def test_fetched_line_reports_a_range_when_dates_differ():
    entries = [{"fetched": "2026-11-01"}, {"fetched": "2026-11-06"}]
    line = render.fetched_line(entries, "2026-11-06")
    assert line == "2 entries, fetched between 2026-11-01 and 2026-11-06."
    same = [{"fetched": "2026-11-06"}, {"fetched": "2026-11-06"}]
    assert render.fetched_line(same, "2026-11-06") == "2 entries, all fetched on 2026-11-06."
