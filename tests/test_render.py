import copy
import datetime as dt

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import render
import validate


def sample():
    return {
        "fetched": "2026-11-06",
        "sections": [
            {"id": "a", "title": "Alpha benchmarks", "blurb": "First."},
            {"id": "b", "title": "Beta and gamma", "blurb": "Second."},
        ],
        "entries": [
            {"name": "Zed", "url": "https://github.com/o/z", "section": "a", "kind": "code",
             "year": 2024, "licence": "MIT", "summary": "Z thing.", "fetched": "2026-11-06"},
            {"name": "Aye", "url": "https://arxiv.org/abs/2101.00001", "section": "a", "kind": "paper",
             "year": 2021, "licence": "CC BY 4.0 (paper)", "venue": "ICLR 2022",
             "summary": "A | pipe.", "fetched": "2026-11-06"},
            {"name": "Bee", "url": "https://huggingface.co/datasets/o/b", "section": "b", "kind": "dataset",
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


def test_cli_reports_bad_input_in_one_line(tmp_path, capsys):
    import json
    data = tmp_path / "entries.json"
    data.write_text(json.dumps(sample()))
    readme = tmp_path / "README.md"
    readme.write_text("no markers\n")
    assert render.main(["--data", str(data), "--readme", str(readme)]) == 2
    assert "markers" in capsys.readouterr().err
    assert render.main(["--data", str(data), "--readme", str(tmp_path / "none.md")]) == 2
    assert "none.md" in capsys.readouterr().err
    data.write_text("{,}")
    readme.write_text(f"t\n{render.BEGIN}\n{render.END}\n")
    assert render.main(["--data", str(data), "--readme", str(readme)]) == 2
    assert "line 1 column 2" in capsys.readouterr().err


def test_cell_collapses_line_breaks_and_control_characters():
    assert render.cell("Foo\rbar.") == "Foo bar."
    assert render.cell("a\r\n\tb\x00c d\x85e") == "a b c d e"


def test_cell_keeps_a_backslash_before_a_pipe():
    # GitHub reads '\\|' as an escaped backslash then a cell boundary, and '\|' as a pipe, so
    # the backslash itself must be escaped too: 'Back \| slash.' must show as written.
    assert render.cell("Back \\| slash.") == "Back \\\\\\| slash."
    assert render.cell("a\\b") == "a\\\\b"


def unescaped_pipes(line):
    n, i = 0, 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        n += line[i] == "|"
        i += 1
    return n


@settings(max_examples=300, deadline=None)
@given(name=st.text(min_size=1, max_size=40), summary=st.text(min_size=1, max_size=150))
def test_any_text_that_passes_validation_renders_one_five_cell_row(name, summary):
    d = sample()
    d["entries"] = d["entries"][:1]
    d["entries"][0].update(name=name, summary=summary.rstrip() + ".")
    d["sections"] = d["sections"][:1]
    if validate.check_data(d, today=dt.date(2026, 11, 6)):
        return
    block = render.render_block(d)
    # splitlines breaks on \r, \x85 and \u2028 as well, as a Markdown renderer may
    rows = [line for line in block.splitlines() if line.startswith("| [")]
    assert len(rows) == 1
    assert unescaped_pipes(rows[0]) == 6
    readme = render.rendered_readme(d, f"x\n{render.BEGIN}\n{render.END}\ny\n")
    assert render.rendered_readme(d, readme) == readme
