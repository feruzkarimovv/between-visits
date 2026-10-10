"""eval/score.py: pure scoring, and the equity split by language and pace (REQ-014)."""

import importlib.util

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
