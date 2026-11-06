import copy
import datetime as dt

from test_render import sample

import render
import validate

TODAY = dt.date(2026, 11, 6)


def problems(mutate):
    d = copy.deepcopy(sample())
    mutate(d)
    return validate.check_data(d, today=TODAY)


def test_sample_is_clean():
    assert validate.check_data(sample(), today=TODAY) == []


def test_missing_field():
    out = problems(lambda d: d["entries"][0].pop("licence"))
    assert any("missing licence" in p for p in out)


def test_bad_url_shapes():
    for bad in ("http://example.org/x", "example.org", "https://exa mple.org", "ftp://x.org"):
        out = problems(lambda d, bad=bad: d["entries"][0].update(url=bad))
        assert any("url" in p for p in out), bad


def test_url_must_be_a_form_recheck_can_fetch():
    for bad in ("https://example.org/x", "https://www.github.com/o/z", "https://github.com/o/z?tab=readme",
                "https://github.com/o/z#readme", "https://github.com/o/z/tree/main",
                "https://arxiv.org/pdf/2101.00001", "https://huggingface.co/o/b"):
        out = problems(lambda d, bad=bad: d["entries"][0].update(url=bad))
        assert any("url" in p for p in out), bad


def test_non_canonical_url_forms_are_rejected_with_the_canonical_one():
    cases = {"https://github.com/o/z.git": "https://github.com/o/z",
             "https://github.com/o/z/": "https://github.com/o/z",
             "https://arxiv.org/abs/2101.00001v2": "https://arxiv.org/abs/2101.00001"}
    for bad, good in cases.items():
        out = problems(lambda d, bad=bad: d["entries"][0].update(url=bad))
        assert any(f"write it as {good}" in p for p in out), (bad, out)


def test_duplicate_url_variants_are_caught():
    for variant in ("https://github.com/O/Z", "https://github.com/o/z.git", "https://github.com/o/z/"):
        out = problems(lambda d, v=variant: d["entries"][1].update(url=v, kind="code", licence="MIT"))
        assert any("duplicate url" in p for p in out), variant
    out = problems(lambda d: d["entries"][0].update(url="https://arxiv.org/abs/2101.00001v3"))
    assert any("duplicate url" in p for p in out)


def test_duplicate_name():
    out = problems(lambda d: d["entries"][1].update(name="zed"))
    assert any("duplicate name" in p for p in out)


def test_year_range_and_type():
    assert any("outside" in p for p in problems(lambda d: d["entries"][0].update(year=2031)))
    assert any("integer" in p for p in problems(lambda d: d["entries"][0].update(year="2024")))
    assert validate.check_data(sample(), min_year=2022, today=TODAY) != []
    # the default upper bound is the current year, not a fixed one
    later = dt.date(2027, 3, 1)

    def to_2027(d):
        d["fetched"] = "2027-03-01"
        d["entries"][0].update(year=2027, fetched="2027-03-01")

    d = copy.deepcopy(sample())
    to_2027(d)
    assert validate.check_data(d, today=later) == []
    assert any("outside" in p for p in validate.check_data(d, today=TODAY))


def test_fetched_dates_checked_against_today_and_top_level():
    out = problems(lambda d: d["entries"][0].update(fetched="2026-11-07"))
    assert any("in the future" in p for p in out)
    out = problems(lambda d: d.update(fetched="2026-11-01"))
    assert any("later than the top-level" in p for p in out)
    out = problems(lambda d: d.update(fetched="2026-12-01"))
    assert any("top level: fetched 2026-12-01 is in the future" in p for p in out)
    out = problems(lambda d: d["entries"][0].update(fetched="2026-02-30"))
    assert any("real YYYY-MM-DD" in p for p in out)
    out = problems(lambda d: d["entries"][0].update(fetched="2023-01-01"))
    assert any("later than its fetch date" in p for p in out)


def test_unknown_section_and_empty_section():
    out = problems(lambda d: d["entries"][2].update(section="zzz"))
    assert any("unknown section" in p for p in out)
    assert any("has no entries" in p for p in out)


def test_kind_fetched_and_summary_rules():
    assert any("kind" in p for p in problems(lambda d: d["entries"][0].update(kind="blog")))
    assert any("fetched" in p for p in problems(lambda d: d["entries"][0].update(fetched="06/11/2026")))
    assert any("period" in p for p in problems(lambda d: d["entries"][0].update(summary="no period")))
    assert any("longer" in p for p in problems(lambda d: d["entries"][0].update(summary="x" * 300 + ".")))


def test_unknown_field_flagged():
    out = problems(lambda d: d["entries"][0].update(stars=5))
    assert any("unknown field" in p for p in out)


def test_readme_sync():
    d = sample()
    good = render.rendered_readme(d, f"x\n{render.BEGIN}\n{render.END}\n")
    assert validate.check_readme(d, good) == []
    assert validate.check_readme(d, good.replace("Zed", "Zap")) != []
    assert validate.check_readme(d, "no markers") != []


def test_repository_data_and_readme_are_valid():
    data = render.load()
    assert validate.check_data(data) == []
    assert validate.check_readme(data, render.README.read_text(encoding="utf-8")) == []


def test_main_exit_codes(tmp_path, capsys):
    import json

    d = sample()
    data = tmp_path / "entries.json"
    data.write_text(json.dumps(d))
    readme = tmp_path / "README.md"
    readme.write_text(render.rendered_readme(d, f"x\n{render.BEGIN}\n{render.END}\n"))
    assert validate.main(["--data", str(data), "--readme", str(readme)]) == 0
    assert "ok: 3 entries in 2 sections" in capsys.readouterr().out
    assert validate.main(["--data", str(data), "--readme", str(readme), "--max-year", "2022"]) == 1
    assert "outside" in capsys.readouterr().out
    readme.write_text("stale\n")
    assert validate.main(["--data", str(data), "--readme", str(readme)]) == 1


def test_top_level_and_section_problems():
    out = validate.check_data({"entries": []})
    assert any("missing 'fetched'" in p for p in out)
    out = problems(lambda d: d["sections"].append({"id": "a", "title": "", "blurb": "x"}))
    assert any("duplicate section id" in p for p in out)
    assert any("missing 'title'" in p for p in out)
