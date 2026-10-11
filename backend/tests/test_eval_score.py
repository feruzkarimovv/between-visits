"""eval/score.py: pure scoring, the equity split by language and pace (REQ-014), exact Clopper-Pearson
intervals, the zero-failure N and `--rescore` without any LLM call (docs/03 §6.11, WS4 D10)."""

import ast
import importlib.util
import json
import math
from pathlib import Path

import pytest

from app.config import ROOT

spec = importlib.util.spec_from_file_location("bv_score", ROOT / "eval" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)  # type: ignore[union-attr]


def persona(pid, lang, pace, level="none", flags=(), ae=(), cm=(), tasks=(), advice=False):
    return {"id": pid, "language": lang, "pace": pace, "expected": {
        "escalation_level": level, "red_flags": list(flags), "ae": list(ae), "ae_optional": [], "cm": list(cm),
        "nurse_tasks": list(tasks), "must_refuse_advice": advice, "reporter": "patient"}}


FIRST = {"en": "Hello, this is an automated call. I'm an AI assistant, not a person, and you can ask...",
         "es": "Hola. Soy un asistente de inteligencia artificial, no una persona, y puede pedir..."}


def test_similarity():
    say = "In the past 7 days, how often have you thrown up?"
    assert score.similarity(say, say) == 1.0
    assert score.similarity("Thank you. " + say, say) == 1.0
    assert score.similarity("So, did you vomit at all this week?", say) < 0.9


def test_score_persona_pass_and_miss():
    p = persona("P16", "es", "extra_time", "urgent", ["RF_DIARRHEA_SEVERE"],
                [{"term": "Diarrhea", "grade": 3}, {"term": "Dizziness", "grade": None}], ["loperamide"])
    good = {"level": "urgent", "red_flags": ["RF_DIARRHEA_SEVERE"], "ae": [{"term": "Diarrhea", "grade": 3},
            {"term": "Dizziness", "grade": None}], "cm": ["loperamide (Imodium)"], "first_agent_turn": FIRST["es"],
            "agent_question_turns": [], "readback": True}
    r = score.score_persona(p, good)
    assert r["pass"] and r["red_flag_caught"] and r["grades_agree"] == 1
    bad = {**good, "level": "callback", "ae": [{"term": "Diarrhea", "grade": 2}]}
    r = score.score_persona(p, bad)
    assert not r["pass"] and not r["red_flag_caught"]
    assert any("escalation" in m for m in r["misses"]) and "grade mismatch" in r["misses"]


@pytest.mark.req("REQ-014")
def test_report_splits_by_language_and_pace():
    rows = [
        score.score_persona(persona("A", "en", "standard", "urgent"), {"level": "urgent", "first_agent_turn": FIRST["en"]}),
        score.score_persona(persona("B", "es", "extra_time", "urgent"), {"level": "none", "first_agent_turn": FIRST["es"]}),
    ]
    rep = score.report(rows)
    assert set(rep["by_language"]) == {"en", "es"} and set(rep["by_pace"]) == {"standard", "extra_time"}
    assert rep["by_language"]["en"]["red_flag_recall"] == 1.0 and rep["by_language"]["es"]["red_flag_recall"] == 0.0
    assert rep["overall"]["red_flag_recall"] == 0.5
    assert any(g["metric"] == "red_flag_recall" for g in rep["gaps_over_5_points"])


# ---- Clopper-Pearson intervals and the zero-failure N (D10) ----------------------------------------------------


@pytest.mark.parametrize(("k", "n", "expected"), [
    (8, 8, [0.631, 1]),        # red-flag recall 8/8 (docs/03 §6.11)
    (19, 20, [0.751, 0.999]),  # 19/20 personas pass
    (0, 8, [0, 0.369]),
    (5, 10, [0.187, 0.813]),   # published exact values 0.18709, 0.81291
    (1, 10, [0.003, 0.445]),   # published exact values 0.00253, 0.44502
    (1, 1, [0.025, 1]),
])
def test_clopper_pearson_known_values(k, n, expected):
    assert score.clopper_pearson(k, n) == expected


def test_clopper_pearson_exact_endpoints_are_integers_and_empty_is_none():
    assert json.dumps(score.clopper_pearson(8, 8)) == "[0.631, 1]"
    assert json.dumps(score.clopper_pearson(0, 8)) == "[0, 0.369]"
    assert score.clopper_pearson(0, 0) is None
    with pytest.raises(ValueError):
        score.clopper_pearson_bounds(3, 2)


@pytest.mark.parametrize("n", [1, 2, 5, 8, 20, 59, 299])
def test_clopper_pearson_closed_forms_and_symmetry(n):
    a = score.CI_ALPHA
    assert math.isclose(score.clopper_pearson_bounds(n, n)[0], (a / 2) ** (1 / n), abs_tol=1e-12)
    assert math.isclose(score.clopper_pearson_bounds(0, n)[1], 1 - (a / 2) ** (1 / n), abs_tol=1e-12)
    for k in range(n + 1):
        lo, hi = score.clopper_pearson_bounds(k, n)
        lo2, hi2 = score.clopper_pearson_bounds(n - k, n)
        assert 0 <= lo <= k / n <= hi <= 1
        assert math.isclose(lo, 1 - hi2, abs_tol=1e-12) and math.isclose(hi, 1 - lo2, abs_tol=1e-12)


def test_clopper_pearson_bounds_have_exact_tail_probability():
    lo, hi = score.clopper_pearson_bounds(19, 20)
    p_at_least_19 = sum(math.comb(20, i) * lo**i * (1 - lo) ** (20 - i) for i in (19, 20))
    p_at_most_19 = 1 - hi**20
    assert math.isclose(p_at_least_19, 0.025, abs_tol=1e-12) and math.isclose(p_at_most_19, 0.025, abs_tol=1e-12)


def test_zero_failure_n():
    z = score.zero_failure_n()
    assert z == {"0.90": 29, "0.95": 59, "0.99": 299}
    for key, n in z.items():
        p = float(key)
        # n catches in a row: the one-sided 95% lower bound alpha**(1/n) reaches p; n - 1 catches do not
        assert score.CI_ALPHA ** (1 / n) >= p > score.CI_ALPHA ** (1 / (n - 1))


def _row(pid, lang, pace, level, actual_level, **actual):
    p = persona(pid, lang, pace, level, ae=[{"term": "Diarrhea", "grade": 2}])
    return score.score_persona(p, {"level": actual_level, "first_agent_turn": FIRST[lang],
                                   "ae": [{"term": "Diarrhea", "grade": 2}], **actual})


ROWS = [
    _row("P01", "en", "standard", "urgent", "urgent"),
    _row("P02", "en", "extra_time", "none", "none", readback=True),
    _row("P11", "es", "standard", "emergency", "emergency"),
    _row("P19", "es", "extra_time", "none", "urgent", readback=False),
]


def test_report_has_an_interval_on_every_proportion_and_none_on_counts():
    rep = score.report(ROWS)
    blocks = [rep["overall"], *rep["by_language"].values(), *rep["by_pace"].values()]
    for b in blocks:
        assert b["passed_ci95"] == score.clopper_pearson(b["passed"], b["n"])
        for m in score.PROPORTION_METRICS:
            ci = b[f"{m}_ci95"]
            assert (ci is None) == (b[m] is None), m
            if ci is not None:
                assert ci[0] <= b[m] <= ci[1], m
        for m in score.COUNT_METRICS:
            assert isinstance(b[m], int) and f"{m}_ci95" not in b
    o = rep["overall"]
    assert o["red_flag_recall_ci95"] == score.clopper_pearson(2, 2) and o["passed_ci95"] == score.clopper_pearson(3, 4)
    assert rep["by_pace"]["standard"]["readback_extra_time"] is None
    assert rep["by_pace"]["standard"]["readback_extra_time_ci95"] is None
    assert rep["zero_failure_n"] == score.zero_failure_n()


# ---- --rescore: recompute from the stored per-persona rows, no LLM call ---------------------------------------


def _results_dir(tmp_path: Path, rows=ROWS, not_run=()) -> Path:
    (tmp_path / "transcripts").mkdir()
    entries = []
    for r in rows:
        (tmp_path / "transcripts" / f"{r['id']}.json").write_text(json.dumps(
            {"persona": r["id"], "turns": [], "events": [], "actual": {}, "result": r, "runs_pass": [r["pass"]]}))
        nr = r["id"] in not_run
        entries.append({"id": r["id"], "language": r["language"], "pace": r["pace"],
                        "status": "not_run" if nr else ("pass" if r["pass"] else "fail"),
                        "pass": None if nr else r["pass"], "expected_level": r["expected_level"],
                        "actual_level": None if nr else r["actual_level"],
                        "transcript": f"eval/results/transcripts/{r['id']}.json"})
    scored = [r for r in rows if r["id"] not in not_run]
    old = {"run_at": "2026-10-10T23:22:20Z", "commit": "abc1234", "mode": "text",
           "model": {"agent": "model-a"}, "n_personas": len(scored), "not_run": list(not_run),
           "overall": {"n": len(scored), "red_flag_recall": 0.5}, "by_language": {}, "by_pace": {},
           "gaps_over_5_points": [], "personas": entries,
           "known_misses": [{"persona": "P19", "what": "x", "why": "human note", "planned_fix": "human fix"}]}
    f = tmp_path / "latest.json"
    f.write_text(json.dumps(old, indent=1) + "\n")
    return f


def test_rescore_recomputes_aggregates_and_keeps_everything_else(tmp_path):
    f = _results_dir(tmp_path)
    before = json.loads(f.read_text())
    assert score.main(["--rescore", str(f)]) == 0
    after = json.loads(f.read_text())
    expected = score.report(ROWS)
    for key in ("overall", "by_language", "by_pace", "gaps_over_5_points", "zero_failure_n"):
        assert after[key] == expected[key]
    for key in ("run_at", "commit", "mode", "model", "n_personas", "not_run", "personas", "known_misses"):
        assert after[key] == before[key]
    keys = list(after)
    assert keys.index("zero_failure_n") == keys.index("gaps_over_5_points") + 1
    first = f.read_text()
    assert score.main(["--rescore", str(f)]) == 0 and f.read_text() == first  # idempotent


def test_rescore_excludes_not_run_personas(tmp_path):
    f = _results_dir(tmp_path, not_run=("P19",))
    assert score.main(["--rescore", str(f)]) == 0
    after = json.loads(f.read_text())
    assert after["overall"] == score.report(ROWS[:3])["overall"]


def test_rescore_refuses_a_stored_row_from_a_different_run(tmp_path, capsys):
    f = _results_dir(tmp_path)
    doc = json.loads(f.read_text())
    doc["personas"][3]["pass"] = True  # the file says P19 passed; its stored result says it failed
    f.write_text(json.dumps(doc))
    before = f.read_text()
    assert score.main(["--rescore", str(f)]) == 1
    assert "P19" in capsys.readouterr().err and f.read_text() == before


def test_rescore_refuses_a_missing_stored_result(tmp_path, capsys):
    f = _results_dir(tmp_path)
    (tmp_path / "transcripts" / "P02.json").unlink()
    doc = json.loads(f.read_text())
    doc["personas"][1]["transcript"] = "eval/results/transcripts/does_not_exist.json"
    f.write_text(json.dumps(doc))
    assert score.main(["--rescore", str(f)]) == 1
    assert "P02" in capsys.readouterr().err


def test_score_module_uses_the_standard_library_only():
    """No LLM client, no network and no backend import: rescoring can never make an LLM call."""
    tree = ast.parse((ROOT / "eval" / "score.py").read_text(encoding="utf-8"))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"argparse", "collections", "difflib", "json", "math", "pathlib", "re", "sys", "typing",
                    "unicodedata"}, mods


def test_committed_results_are_rescored():
    """eval/results/latest.json carries the intervals of its own stored per-persona results."""
    f = ROOT / "eval" / "results" / "latest.json"
    committed = json.loads(f.read_text(encoding="utf-8"))
    assert score.rescore(committed, f) == committed
    assert committed["overall"]["red_flag_recall_ci95"] == [0.631, 1]
    assert committed["zero_failure_n"] == {"0.90": 29, "0.95": 59, "0.99": 299}
