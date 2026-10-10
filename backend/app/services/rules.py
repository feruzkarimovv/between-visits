"""Deterministic rules engine: provisional CTCAE grades and red flags. Pure functions, no I/O.

Everything clinical comes from data/ctcae_rules.json and data/red_flags.json (via app.content); this
module only implements the condition DSL from docs/05-clinical-rules.md § 4:

- leaf: {"item": CODE, op: value} or {"derived": NAME, op: value}; ops eq | in | gte | gt | lte | lt (ANDed)
- combinators: {"any": [...]}, {"all": [...]}
- a leaf whose input is missing or `unknown` is false
- temperatures are normalized to Celsius before comparison
"""

from dataclasses import dataclass, field
from typing import Any

from app import content

LEVEL_RANK = {"none": 0, "callback": 1, "urgent": 2, "emergency": 3}
NON_VALUES = {"unknown", "not_measured", None}
# option codes that mean "symptom absent" on each scale; anything else on a symptom item means present
ABSENT_OPTIONS = {"never", "none", "no"}


@dataclass(frozen=True)
class AnswerInput:
    option_code: str | None = None
    numeric_value: float | None = None
    unit: str | None = None


Answers = dict[str, AnswerInput]


@dataclass
class GradeResult:
    term: str
    provisional_grade: int | None
    grade_basis: str  # rule | needs_clinician
    rule_id: str | None = None
    rule_text: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class RedFlagHit:
    id: str
    level: str
    source: str  # rule | report
    inputs: dict[str, Any] = field(default_factory=dict)


def to_celsius(value: float, unit: str | None) -> float:
    """Fahrenheit or Celsius → Celsius, rounded to 0.01 to avoid float noise at rule boundaries."""
    c = (value - 32.0) * 5.0 / 9.0 if unit == "fahrenheit" else value
    return round(c, 2)


def _item_value(code: str, answers: Answers) -> Any:
    a = answers.get(code)
    if a is None:
        return None
    if a.option_code in ("unknown", "not_measured"):
        return None
    if content.has_item(code) and content.is_numeric(code):
        if a.numeric_value is None:
            return None
        if content.item(code)["scale"] == "temperature":
            return to_celsius(a.numeric_value, a.unit)
        return a.numeric_value
    return a.option_code


def derived_value(name: str, answers: Answers, baseline: dict[str, Any] | None) -> float | None:
    if name == "stools_over_baseline":
        worst = _item_value("DIARRHEA_STOOLS_PER_DAY", answers)
        base = _item_value("DIARRHEA_BASELINE", answers)
        if base is None:
            base = (baseline or {}).get("stools_per_day")
        if worst is None or base is None:
            return None
        return float(worst) - float(base)
    raise ValueError(f"unknown derived input {name}")


def _compare(value: Any, cond: dict[str, Any]) -> bool:
    ops = {k: v for k, v in cond.items() if k in ("eq", "in", "gte", "gt", "lte", "lt")}
    if not ops:
        raise ValueError(f"leaf without operator: {cond}")
    for op, target in ops.items():
        if op == "eq" and value != target:
            return False
        if op == "in" and value not in target:
            return False
        if op in ("gte", "gt", "lte", "lt"):
            if not isinstance(value, int | float):
                return False
            if op == "gte" and not value >= target:
                return False
            if op == "gt" and not value > target:
                return False
            if op == "lte" and not value <= target:
                return False
            if op == "lt" and not value < target:
                return False
    return True


def evaluate(cond: dict[str, Any], answers: Answers, baseline: dict[str, Any] | None, used: dict[str, Any]) -> bool:
    """Evaluate a DSL condition; records every input it reads into `used`."""
    if "any" in cond:
        return any([evaluate(c, answers, baseline, used) for c in cond["any"]])
    if "all" in cond:
        return all([evaluate(c, answers, baseline, used) for c in cond["all"]])
    if "item" in cond:
        value = _item_value(cond["item"], answers)
        if value is None:
            return False
        used[_input_name(cond["item"])] = value
        return _compare(value, cond)
    if "derived" in cond:
        value = derived_value(cond["derived"], answers, baseline)
        if value is None:
            return False
        used[cond["derived"]] = _num(value)
        return _compare(value, cond)
    raise ValueError(f"bad condition {cond}")


def _input_name(code: str) -> str:
    return "temp_c" if code == "TEMP_HIGHEST" else code


def _num(v: float) -> float | int:
    return int(v) if float(v).is_integer() else v


def term_present(term: str, answers: Answers) -> bool:
    """True when any answer for the term reports the symptom (not absent, not unknown)."""
    for code in content.items_for_term(term):
        a = answers.get(code)
        if a is None:
            continue
        if content.is_numeric(code):
            if a.numeric_value is not None:
                return True
            continue
        if a.option_code not in ABSENT_OPTIONS and a.option_code not in NON_VALUES:
            return True
    return False


def grade(term: str, answers: Answers, baseline: dict[str, Any] | None) -> GradeResult:
    """First matching CTCAE rule for the term gives the provisional grade; otherwise needs clinician."""
    for rule in content.rules_for(term):
        used: dict[str, Any] = {}
        if evaluate(rule["when"], answers, baseline, used):
            return GradeResult(term, int(rule["grade"]), "rule", rule["id"], rule["ctcae_text"], used)
    inputs = {code: _item_value(code, answers) for code in content.items_for_term(term) if code in answers}
    return GradeResult(term, None, "needs_clinician", None, None, inputs)


def red_flags(
    answers: Answers,
    baseline: dict[str, Any] | None,
    reported_flag_ids: list[str] | None = None,
    day_after_dose: int | None = None,
    active_ids: list[str] | None = None,
) -> list[RedFlagHit]:
    """All red flags that are active: rule-based (from answers) and reported (by the agent or safety net).

    `active_ids` limits rule evaluation to the study plan's red flags. Reported flags are never
    second-guessed: an unknown reported ID still escalates at `urgent` (fail safe)."""
    hits: dict[str, RedFlagHit] = {}
    for rf in content.red_flags():
        if active_ids is not None and rf["id"] not in active_ids:
            continue
        if not rf.get("rule"):
            continue
        used: dict[str, Any] = {}
        if evaluate(rf["rule"], answers, baseline, used):
            hits[rf["id"]] = RedFlagHit(rf["id"], rf["level"], "rule", used)
    for fid in reported_flag_ids or []:
        if fid in hits:
            continue
        level = content.red_flag(fid)["level"] if content.has_red_flag(fid) else "urgent"
        hits[fid] = RedFlagHit(fid, level, "report", {})
    return list(hits.values())


def level_for(hits: list[RedFlagHit]) -> str:
    level = "none"
    for h in hits:
        if LEVEL_RANK[h.level] > LEVEL_RANK[level]:
            level = h.level
    return level


def max_level(*levels: str) -> str:
    return max(levels, key=lambda lv: LEVEL_RANK.get(lv, 0)) if levels else "none"


def _cond_items(cond: dict[str, Any]) -> set[str]:
    if "any" in cond or "all" in cond:
        out: set[str] = set()
        for c in cond.get("any", []) + cond.get("all", []):
            out |= _cond_items(c)
        return out
    if "item" in cond:
        return {cond["item"]}
    if cond.get("derived") == "stools_over_baseline":
        return {"DIARRHEA_STOOLS_PER_DAY", "DIARRHEA_BASELINE"}
    return set()


def flag_terms(flag_id: str, used_inputs: dict[str, Any] | None = None) -> set[str]:
    """Terms a rule-based red flag belongs to (the terms of the items its rule read)."""
    if not content.has_red_flag(flag_id):
        return set()
    rule = content.red_flag(flag_id).get("rule")
    if not rule:
        return set()
    codes = _cond_items(rule)
    if used_inputs is not None:
        used_codes = {("TEMP_HIGHEST" if k == "temp_c" else k) for k in used_inputs}
        if "stools_over_baseline" in used_inputs:
            used_codes |= {"DIARRHEA_STOOLS_PER_DAY"}
        codes = codes & used_codes or codes
    return {t for c in codes if (t := content.term_of(c))}
