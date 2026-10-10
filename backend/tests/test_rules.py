"""Table-driven tests for every test vector in docs/05-clinical-rules.md § 5 (rules part)."""

import pytest

from app import content
from app.services import rules
from app.services.rules import AnswerInput as A

B1 = {"stools_per_day": 1}
NONE: dict = {}


def ans(**kw: A) -> dict[str, A]:
    return dict(kw)


GRADE_VECTORS = [
    # (name, term, answers, baseline, expected grade, expected basis)
    ("worst 4", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=4)), B1, 1, "rule"),
    ("worst 5", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=5)), B1, 2, "rule"),
    ("worst 7 (6 over)", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=7)), B1, 2, "rule"),
    ("worst 8", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=8)), B1, 3, "rule"),
    (
        "baseline answered 2, worst 9",
        "Diarrhea",
        ans(DIARRHEA_BASELINE=A(numeric_value=2), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=9)),
        NONE,
        3,
        "rule",
    ),
    ("no baseline at all", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=9)), NONE, None, "needs_clinician"),
    ("worst unknown", "Diarrhea", ans(DIARRHEA_STOOLS_PER_DAY=A(option_code="unknown")), B1, None, "needs_clinician"),
    (
        "blood, 2 over",
        "Diarrhea",
        ans(STOOL_BLOOD=A(option_code="yes"), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=3)),
        B1,
        1,
        "rule",
    ),
    ("37.9 C", "Fever", ans(TEMP_HIGHEST=A(numeric_value=37.9, unit="celsius")), NONE, None, "needs_clinician"),
    ("38.0 C", "Fever", ans(TEMP_HIGHEST=A(numeric_value=38.0, unit="celsius")), NONE, 1, "rule"),
    ("100.4 F", "Fever", ans(TEMP_HIGHEST=A(numeric_value=100.4, unit="fahrenheit")), NONE, 1, "rule"),
    ("102.2 F", "Fever", ans(TEMP_HIGHEST=A(numeric_value=102.2, unit="fahrenheit")), NONE, 1, "rule"),
    ("102.3 F", "Fever", ans(TEMP_HIGHEST=A(numeric_value=102.3, unit="fahrenheit")), NONE, 2, "rule"),
    ("40.0 C", "Fever", ans(TEMP_HIGHEST=A(numeric_value=40.0, unit="celsius")), NONE, 2, "rule"),
    ("40.1 C", "Fever", ans(TEMP_HIGHEST=A(numeric_value=40.1, unit="celsius")), NONE, 3, "rule"),
    ("not measured", "Fever", ans(TEMP_HIGHEST=A(option_code="not_measured")), NONE, None, "needs_clinician"),
    ("SOB at rest", "Dyspnea", ans(SOB_EXERTION=A(option_code="at_rest")), NONE, 3, "rule"),
    (
        "SOB severe + light",
        "Dyspnea",
        ans(SOB_SEV=A(option_code="severe"), SOB_EXERTION=A(option_code="light_activity")),
        NONE,
        2,
        "rule",
    ),
    ("fatigue rest helps", "Fatigue", ans(FATIGUE_REST_HELPS=A(option_code="yes")), NONE, 1, "rule"),
    ("dizziness mild", "Dizziness", ans(DIZZINESS_SEV=A(option_code="mild")), NONE, 1, "rule"),
    ("nausea often", "Nausea", ans(NAUSEA_FREQ=A(option_code="often")), NONE, None, "needs_clinician"),
]


@pytest.mark.req("REQ-004")
@pytest.mark.parametrize("name,term,answers,baseline,grade,basis", GRADE_VECTORS, ids=[v[0] for v in GRADE_VECTORS])
def test_grade_vectors(name, term, answers, baseline, grade, basis):
    r = rules.grade(term, answers, baseline)
    assert r.provisional_grade == grade
    assert r.grade_basis == basis
    if grade is not None:
        rule = next(x for x in content.grading_rules() if x["id"] == r.rule_id)
        assert r.rule_text == rule["ctcae_text"]  # grade text comes verbatim from the CTCAE rule table


FLAG_VECTORS = [
    ("worst 4", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=4)), B1, set()),
    ("worst 7", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=7)), B1, set()),
    ("worst 8", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=8)), B1, {"RF_DIARRHEA_SEVERE"}),
    (
        "baseline answered 2, worst 9",
        ans(DIARRHEA_BASELINE=A(numeric_value=2), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=9)),
        NONE,
        {"RF_DIARRHEA_SEVERE"},
    ),
    ("no baseline", ans(DIARRHEA_STOOLS_PER_DAY=A(numeric_value=9)), NONE, set()),
    ("worst unknown", ans(DIARRHEA_STOOLS_PER_DAY=A(option_code="unknown")), B1, set()),
    (
        "blood",
        ans(STOOL_BLOOD=A(option_code="yes"), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=3)),
        B1,
        {"RF_DIARRHEA_SEVERE"},
    ),
    ("37.9 C", ans(TEMP_HIGHEST=A(numeric_value=37.9, unit="celsius")), NONE, set()),
    ("38.0 C", ans(TEMP_HIGHEST=A(numeric_value=38.0, unit="celsius")), NONE, {"RF_FEVER"}),
    ("100.4 F", ans(TEMP_HIGHEST=A(numeric_value=100.4, unit="fahrenheit")), NONE, {"RF_FEVER"}),
    ("not measured", ans(TEMP_HIGHEST=A(option_code="not_measured")), NONE, set()),
    ("SOB at rest", ans(SOB_EXERTION=A(option_code="at_rest")), NONE, {"RF_BREATHING"}),
    (
        "SOB severe light",
        ans(SOB_SEV=A(option_code="severe"), SOB_EXERTION=A(option_code="light_activity")),
        NONE,
        {"RF_BREATHING"},
    ),
    ("fluids no", ans(FLUIDS_KEPT_DOWN=A(option_code="no")), NONE, {"RF_DEHYDRATION"}),
    (
        "dizzy + 3 over",
        ans(DIZZY_ON_STANDING=A(option_code="yes"), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=4)),
        B1,
        set(),
    ),
    (
        "dizzy + 4 over",
        ans(DIZZY_ON_STANDING=A(option_code="yes"), DIARRHEA_STOOLS_PER_DAY=A(numeric_value=5)),
        B1,
        {"RF_DEHYDRATION"},
    ),
    (
        "dizzy + vomiting sometimes",
        ans(DIZZY_ON_STANDING=A(option_code="yes"), VOMITING_FREQ=A(option_code="sometimes")),
        NONE,
        {"RF_DEHYDRATION"},
    ),
    ("neuro yes", ans(NEURO_CHANGE=A(option_code="yes")), NONE, {"RF_NEURO"}),
    ("skin blister", ans(SKIN_BLISTER=A(option_code="yes")), NONE, {"RF_SKIN_SEVERE"}),
]


@pytest.mark.req("REQ-005")
@pytest.mark.parametrize("name,answers,baseline,expected", FLAG_VECTORS, ids=[v[0] for v in FLAG_VECTORS])
def test_red_flag_vectors(name, answers, baseline, expected):
    hits = rules.red_flags(answers, baseline)
    assert {h.id for h in hits} == expected


@pytest.mark.req("REQ-005")
def test_reported_flags_and_levels():
    hits = rules.red_flags({}, None, ["RF_CHEST_PAIN"])
    assert [(h.id, h.level, h.source) for h in hits] == [("RF_CHEST_PAIN", "emergency", "report")]
    assert rules.level_for(hits) == "emergency"
    assert rules.level_for([]) == "none"
    # unknown reported IDs still escalate (fail safe)
    assert rules.level_for(rules.red_flags({}, None, ["RF_NOT_A_FLAG"])) == "urgent"


def test_term_present():
    assert not rules.term_present("Diarrhea", {"DIARRHEA_FREQ": A(option_code="never")})
    assert rules.term_present("Diarrhea", {"DIARRHEA_FREQ": A(option_code="rarely")})
    assert not rules.term_present("Fever", {"FEVER_CHILLS": A(option_code="unknown")})
    assert rules.term_present("Fever", {"TEMP_HIGHEST": A(numeric_value=37.9, unit="celsius")})


def test_flag_terms():
    assert rules.flag_terms("RF_DIARRHEA_SEVERE") == {"Diarrhea"}
    assert rules.flag_terms("RF_CHEST_PAIN") == set()
    assert rules.flag_terms("RF_DEHYDRATION", {"FLUIDS_KEPT_DOWN": "no"}) == {"Vomiting"}
