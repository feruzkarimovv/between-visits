"""validation/render_numbers.py (WS4 D13-D16): Site Signal number tokens in the story documents are filled only from
the source JSON files, rounded by docs/11 §15 rule 6, with a provenance table, and fail loudly on a missing path.
Rendered copies go to tmp_path only; fixture numbers are never written into the repository."""

import importlib.util
import json
import shutil
import sys

import pytest

from app.config import ROOT

spec = importlib.util.spec_from_file_location("bv_render_numbers", ROOT / "validation" / "render_numbers.py")
rn = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rn  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(rn)  # type: ignore[union-attr]

FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "site_signal"
STORY = ["WHAT_IT_GETS_WRONG.md", "README.md", "docs/pitch/deck.html", "docs/08-demo-and-pitch.md"]


def tok(inner: str) -> str:
    return "{{ss:" + inner + "}}"


@pytest.mark.parametrize(("fmt", "value", "shown"), [
    ("p2", 0.125, "0.13"),          # half-up on the decimal repr, not banker's rounding
    ("p2", 0.0, "0.00"),
    ("p2", 1, "1.00"),
    ("pct2", 0.234, "23%"),
    ("pct2", 0.235, "24%"),
    ("f1", 1.25, "1.3"),
    ("f2", -0.004, "0.00"),         # no "-0.00"
    ("f3", 0.0105, "0.011"),
    ("ci3", [0.6305, 1], "[0.631, 1.000]"),
    ("int", 14.0, "14"),
    ("text", "met", "met"),
])
def test_formats(fmt, value, shown):
    assert rn.FORMATS[fmt](value) == shown


@pytest.mark.parametrize(("fmt", "value"), [
    ("p2", 1.2), ("pct2", -0.1), ("f2", None), ("f2", True), ("f3", float("nan")), ("int", 1.5),
    ("ci3", [0.1]), ("text", 3),
])
def test_formats_refuse_wrong_values(fmt, value):
    with pytest.raises(rn.RenderError):
        rn.FORMATS[fmt](value)


DOC = {"power": [
    {"indicator": "discordance", "tier": "watch", "design_row": False, "f": 0.25, "power": 0.1},
    {"indicator": "discordance", "tier": "watch", "design_row": True, "f": 0.9, "power": 0.8},
    {"indicator": "rate_kri", "tier": "watch", "design_row": False, "f": 0.25, "power": 0.05},
    {"indicator": "rate_kri", "tier": "watch", "design_row": False, "f": 0.25, "power": 0.06},
], "null": {"look_per_site": {"rate": 0.049, "ci95": [0.04, 0.06]}}}


def test_paths_select_exactly_one_element():
    assert rn.walk(DOC, "null.look_per_site.rate") == 0.049
    assert rn.walk(DOC, ".null.look_per_site.ci95[1]") == 0.06
    assert rn.walk(DOC, "power[indicator=discordance,design_row=true].power") == 0.8
    assert rn.walk(DOC, "power[indicator=discordance,f=0.25].power") == 0.1
    with pytest.raises(rn.Missing):
        rn.walk(DOC, "power[indicator=discordance,f=0.5].power")
    with pytest.raises(rn.Missing):
        rn.walk(DOC, "null.watch_fwer.rate")
    with pytest.raises(rn.RenderError, match="2 elements match"):
        rn.walk(DOC, "power[indicator=rate_kri,f=0.25].power")


def test_alternative_is_tried_only_when_the_first_path_is_missing():
    value, used, fallback = rn.resolve(DOC, "power[design_row=true,f=0.25].power // power[indicator=discordance,f=0.25].power")
    assert (value, fallback) == (0.1, True) and used.startswith("power[indicator=discordance")
    with pytest.raises(rn.RenderError, match="2 elements match"):  # ambiguity never falls through
        rn.resolve(DOC, "power[indicator=rate_kri,f=0.25].power // null.look_per_site.rate")
    with pytest.raises(rn.RenderError, match="missing path"):
        rn.resolve(DOC, "a.b // c[0]")


def test_render_and_check_on_fixtures(tmp_path):
    doc = tmp_path / "src" / "WHAT_IT_GETS_WRONG.md"
    doc.parent.mkdir()
    doc.write_text(
        f"Watch false flags {tok('summary:null.watch_fwer.rate:p2')} (MC SE {tok('summary:null.watch_fwer.mc_se:f3')}).\n"
        f"Computed sites {tok('signal_run:run.n_computed_sites:int')}; REQ-023 Look {tok('derived:req023.look.outcome:text')}.\n"
        f"Gross {tok('summary:power[indicator=discordance,tier=watch,design_row=true,f=0.9].power:p2')}.\n"
        f"{rn.PROV_START}\nplaceholder\n{rn.PROV_END}\n", encoding="utf-8")
    out = tmp_path / "out"
    assert rn.main(["--source", str(FIXTURES), "--out", str(out), str(doc)]) == 0
    text = (out / doc.name).read_text(encoding="utf-8")
    assert "{{ss:" not in text and "placeholder" not in text
    assert "Computed sites 18;" in text  # signal_run.json fixture: run.n_computed_sites
    assert "| 5 | `WHAT_IT_GETS_WRONG.md`:3 | `0.00` |" in text
    assert rn.main(["--check", str(out / doc.name)]) == 0
    assert rn.main(["--check", str(doc)]) == 1  # tokens left in the unrendered source
    tampered = out / "tampered" / doc.name
    tampered.parent.mkdir()
    tampered.write_text(text.replace("Computed sites 18;", "Computed sites 19;"), encoding="utf-8")
    assert rn.main(["--check", str(tampered)]) == 1


def test_render_fails_loudly_and_writes_nothing(tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text(f"{tok('summary:null.no_such.rate:p2')} and {tok('nope:a:p2')} and {tok('summary:design.mu:p9')}\n",
                   encoding="utf-8")
    out = tmp_path / "out"
    assert rn.main(["--source", str(FIXTURES), "--out", str(out), str(doc)]) == 1
    err = capsys.readouterr().err
    assert "3 token(s) failed" in err and "missing path" in err and "unknown file" in err and "unknown format" in err
    assert not out.exists()


def test_derived_req023_outcome_uses_unrounded_values(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(FIXTURES, src)
    summary = json.loads((src / "summary.json").read_text())
    summary["null"]["look_per_site"].update(rate=0.0549, mc_se=0.002)
    summary["null"]["watch_fwer"].update(rate=0.13, mc_se=0.001)
    (src / "summary.json").write_text(json.dumps(summary))
    thresholds = json.loads((src / "thresholds.json").read_text())
    thresholds["achieved"]["discordance"]["look"]["mc_se"] = 0.002
    (src / "thresholds.json").write_text(json.dumps(thresholds))
    derived = rn.Sources(src).get("derived")
    assert derived["req023"]["look"]["outcome"] == "met"          # 0.0549 <= 0.05 + 2*sqrt(2)*0.002
    assert derived["req023"]["watch"]["outcome"] == "not met"
    assert derived["size"]["outcome"].startswith("not met")       # fixture tertile rates are 0.0


def test_story_documents_render_from_the_fixtures(tmp_path):
    files = [str(ROOT / f) for f in STORY]
    assert rn.main(["--list", *files]) == 0
    assert rn.main(["--source", str(FIXTURES), "--out", str(tmp_path), *files]) == 0
    assert rn.main(["--check", *(str(tmp_path / (ROOT / f).name) for f in STORY)]) == 0
    assert "_TODO_" not in (ROOT / "README.md").read_text(encoding="utf-8")
