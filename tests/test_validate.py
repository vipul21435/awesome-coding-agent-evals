import copy

import render
import validate
from test_render import sample


def problems(mutate):
    d = copy.deepcopy(sample())
    mutate(d)
    return validate.check_data(d)


def test_sample_is_clean():
    assert validate.check_data(sample()) == []


def test_missing_field():
    out = problems(lambda d: d["entries"][0].pop("licence"))
    assert any("missing licence" in p for p in out)


def test_bad_url_shapes():
    for bad in ("http://example.org/x", "example.org", "https://exa mple.org", "ftp://x.org"):
        out = problems(lambda d, bad=bad: d["entries"][0].update(url=bad))
        assert any("url" in p for p in out), bad


def test_duplicate_url_ignores_case_and_trailing_slash():
    out = problems(lambda d: d["entries"][1].update(url="https://EXAMPLE.org/z/"))
    assert any("duplicate url" in p for p in out)


def test_duplicate_name():
    out = problems(lambda d: d["entries"][1].update(name="zed"))
    assert any("duplicate name" in p for p in out)


def test_year_range_and_type():
    assert any("outside" in p for p in problems(lambda d: d["entries"][0].update(year=2031)))
    assert any("integer" in p for p in problems(lambda d: d["entries"][0].update(year="2024")))
    assert validate.check_data(sample(), min_year=2022) != []


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
