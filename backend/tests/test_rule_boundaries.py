"""Grade-band boundary tests (WS4-D9): every numeric threshold of the grading and red-flag rules is pinned.

The expected edges are read from the committed data/ctcae_rules.json, data/red_flags.json and
data/symptom_items.json (the reviewed values); no threshold is written in this file. Each edge is tested at the
edge and one unit either side, where one unit is the precision the threshold is written with in the data file
(a stool count written as 7 steps by 1; a temperature written as 39.0 steps by 0.1 C).

- Grade boundaries (REQ-004): Diarrhea G1/G2 and G2/G3, Fever G1/G2 and G2/G3 (numeric bands), Dyspnea G1/G2
  and G2/G3 (adjacent options of its scale). Every tested value gets the expected grade from rules.grade() and
  matches exactly one rule of its term (none outside the bands), so no grade depends on rule order.
- Outer edges (REQ-004): the lower edge of each numeric term's lowest band (no grade below it), and the upper
  edge of its highest band when it has one.
- Red-flag thresholds (REQ-005): every numeric leaf of a red-flag rule, with the rest of the rule set so that
  the leaf decides the flag.
- Coverage: every numeric threshold in both rule files is exercised by one of the cases above.

BV_DATA_UNDER_TEST=<dir> points the rules engine (app.content) at another copy of data/ for this module only;
data/mutation_probe.py uses it to run these tests against temp copies with one threshold shifted by one unit.
The expected values always come from the repository's data/.
"""

import json
import os
from collections.abc import Iterator
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from app import content
from app.services import rules
from app.services.rules import AnswerInput

REVIEWED = Path(__file__).resolve().parents[2] / "data"
UNDER_TEST = os.environ.get("BV_DATA_UNDER_TEST")
LOWER, UPPER = ("gte", "gt"), ("lte", "lt")
CMP = LOWER + UPPER
BASELINE_STOOLS = 1  # fixture input (the patient's usual stools per day), not a threshold
# Items each derived input reads (rules.derived_value; `derived_inputs` in ctcae_rules.json).
DERIVED_ITEMS = {"stools_over_baseline": {"DIARRHEA_STOOLS_PER_DAY", "DIARRHEA_BASELINE"}}
SIX_BOUNDARIES = {f"{t} G{g}/G{g + 1}" for t in ("Diarrhea", "Fever", "Dyspnea") for g in (1, 2)}

Number = int | Decimal
Answers = dict[str, AnswerInput]
Threshold = tuple[str, str, tuple, str]  # (rule or flag id, json key of its condition, path to the leaf, op)


def _reviewed(name: str) -> dict[str, Any]:
    """A committed data file; decimals load as Decimal so each threshold keeps the precision it is written with."""
    return json.loads((REVIEWED / name).read_text(encoding="utf-8"), parse_float=Decimal)


CTCAE, FLAGS, ITEMS = (
    _reviewed("ctcae_rules.json"),
    _reviewed("red_flags.json"),
    _reviewed("symptom_items.json"),
)


@pytest.fixture(scope="module", autouse=True)
def engine_data() -> Iterator[Path]:
    """The data/ directory the rules engine reads: BV_DATA_UNDER_TEST when set, else the repository's."""
    if not UNDER_TEST:
        yield REVIEWED
        return
    under_test = Path(UNDER_TEST).resolve()
    mp = pytest.MonkeyPatch()
    mp.setattr(content, "DATA_DIR", under_test)
    content.reload()
    try:
        yield under_test
    finally:
        mp.undo()
        content.reload()


# ---- the reviewed rules (the oracle) ------------------------------------------------------------------------


def unit(t: Number) -> Decimal:
    """One unit at the precision the threshold is written with: 7 -> 1, 39.0 -> 0.1."""
    return Decimal(1) if isinstance(t, int) else Decimal(1).scaleb(t.as_tuple().exponent)


def around(thresholds: list[Number]) -> list[Decimal]:
    """Each threshold and one unit either side."""
    return sorted({Decimal(t) + d for t in thresholds for d in (-unit(t), Decimal(0), unit(t))})


def holds(op: str, v: Number, t: Number) -> bool:
    return {"gte": v >= t, "gt": v > t, "lte": v <= t, "lt": v < t}[op]


def is_numeric_leaf(c: dict[str, Any]) -> bool:
    return ("item" in c or "derived" in c) and any(op in c for op in CMP)


def leaf_input(c: dict[str, Any]) -> tuple[str, str]:
    return ("derived", c["derived"]) if "derived" in c else ("item", c["item"])


def leaf_holds(c: dict[str, Any], v: Any) -> bool:
    if "eq" in c:
        return v == c["eq"]
    if "in" in c:
        return v in c["in"]
    return all(holds(op, v, c[op]) for op in CMP if op in c)


def term_rules(term: str) -> list[dict[str, Any]]:
    return sorted((r for r in CTCAE["rules"] if r["term"] == term), key=lambda r: r["grade"])


def term_kind(term: str) -> str:
    """numeric: one gte/gt/lte/lt leaf per rule, all on one input; options: one eq leaf per rule, all on one item."""
    whens = [r["when"] for r in term_rules(term)]
    if all(is_numeric_leaf(w) and not {"eq", "in"} & set(w) for w in whens):
        if len({leaf_input(w) for w in whens}) == 1:
            return "numeric"
    if all(set(w) == {"item", "eq"} for w in whens) and len({w["item"] for w in whens}) == 1:
        return "options"
    return "other"


def expected_grade(term: str, v: Any) -> int | None:
    """Grade of the reviewed band that holds v; None outside every band. Reviewed bands must not overlap."""
    hits = [r["grade"] for r in term_rules(term) if leaf_holds(r["when"], v)]
    assert len(hits) <= 1, f"{term}: the reviewed bands overlap at {v} (grades {hits})"
    return hits[0] if hits else None


def scale_of(item: str) -> dict[str, Any]:
    return ITEMS["scales"][ITEMS["items"][item]["scale"]]


def numeric_answers(inp: tuple[str, str], v: Decimal) -> tuple[Answers, dict[str, Any] | None]:
    """Answers (and patient baseline) that give the input `inp` the value v."""
    kind, name = inp
    if kind == "derived":
        assert name == "stools_over_baseline", f"no answer builder for derived input {name}; extend this test"
        worst = AnswerInput(numeric_value=float(BASELINE_STOOLS + v))
        return {"DIARRHEA_STOOLS_PER_DAY": worst}, {"stools_per_day": BASELINE_STOOLS}
    units = scale_of(name).get("units", [])
    u = "celsius" if "celsius" in units else (units[0] if units else None)
    return {name: AnswerInput(numeric_value=float(v), unit=u)}, None


def numeric_leaves(cond: dict[str, Any] | None, path: tuple = ()) -> Iterator[tuple[tuple, dict[str, Any]]]:
    """(path, leaf) for every numeric leaf of a condition; the path is ((combinator, index), ...)."""
    for key in ("any", "all"):
        if cond and key in cond:
            for i, c in enumerate(cond[key]):
                yield from numeric_leaves(c, (*path, (key, i)))
            return
    if cond and is_numeric_leaf(cond):
        yield path, cond


def leaf_at(cond: dict[str, Any], path: tuple) -> dict[str, Any]:
    for key, i in path:
        cond = cond[key][i]
    return cond


# ---- cases, built from the reviewed rules -----------------------------------------------------------------


def _grade_cases() -> list[tuple[str, str, list[Any], tuple[int, int] | None, list[Threshold]]]:
    """(case id, term, values, the two grades an inter-grade boundary separates, thresholds exercised)."""
    cases = []
    for term in dict.fromkeys(r["term"] for r in CTCAE["rules"]):
        rs, kind = term_rules(term), term_kind(term)
        for a, b in pairwise(rs):
            name, pair = f"{term} G{a['grade']}/G{b['grade']}", (a["grade"], b["grade"])
            if kind == "numeric":
                edges = [(a, op) for op in UPPER if op in a["when"]] + [
                    (b, op) for op in LOWER if op in b["when"]
                ]
                values: list[Any] = around([r["when"][op] for r, op in edges])
                cases.append((name, term, values, pair, [(r["id"], "when", (), op) for r, op in edges]))
            elif kind == "options":
                opts = list(scale_of(a["when"]["item"]).get("options", []))
                ia, ib = opts.index(a["when"]["eq"]), opts.index(b["when"]["eq"])
                assert ib == ia + 1, (
                    f"{name}: {a['when']['eq']} and {b['when']['eq']} are not adjacent on the scale"
                )
                cases.append((name, term, opts[max(ia - 1, 0) : ib + 2], pair, []))
        if kind == "numeric":
            for r, ops, side in ((rs[0], LOWER, "below"), (rs[-1], UPPER, "above")):
                edges = [op for op in ops if op in r["when"]]
                if edges:
                    values = around([r["when"][op] for op in edges])
                    cases.append(
                        (
                            f"{term} {side} G{r['grade']}",
                            term,
                            values,
                            None,
                            [(r["id"], "when", (), op) for op in edges],
                        )
                    )
    return cases


def _flag_cases() -> list[tuple[str, str, tuple, list[Decimal], list[Threshold]]]:
    """(case id, flag id, path to the numeric leaf, values, thresholds exercised) per numeric red-flag leaf."""
    cases = []
    for rf in FLAGS["red_flags"]:
        for path, leaf in numeric_leaves(rf.get("rule")):
            ops = [op for op in CMP if op in leaf]
            name = f"{rf['id']} {leaf_input(leaf)[1]} {'/'.join(ops)}"
            values = around([leaf[op] for op in ops])
            cases.append((name, rf["id"], path, values, [(rf["id"], "rule", path, op) for op in ops]))
    return cases


GRADE_CASES = _grade_cases()
FLAG_CASES = _flag_cases()


def _inputs_of(cond: dict[str, Any]) -> set[str]:
    if "any" in cond or "all" in cond:
        return set().union(*(_inputs_of(c) for c in cond.get("any", []) + cond.get("all", [])))
    return set(DERIVED_ITEMS[cond["derived"]]) if "derived" in cond else {cond["item"]}


def _satisfy(cond: dict[str, Any]) -> Answers:
    """Answers that make a condition true (the first branch of an `any`, every branch of an `all`)."""
    if "any" in cond:
        return _satisfy(cond["any"][0])
    if "all" in cond:
        return {k: v for c in cond["all"] for k, v in _satisfy(c).items()}
    if "eq" in cond:
        return {cond["item"]: AnswerInput(option_code=cond["eq"])}
    if "in" in cond:
        return {cond["item"]: AnswerInput(option_code=cond["in"][0])}
    raise AssertionError(f"cannot build a context that satisfies {cond}; extend this test")


def _context(rule: dict[str, Any], path: tuple) -> Answers:
    """Answers that let the leaf at `path` decide the rule: `all` siblings true, `any` siblings unanswered
    (a leaf whose input is missing is false, docs/05 §4)."""
    ctx: Answers = {}
    unanswered: set[str] = set()
    node = rule
    for key, i in path:
        for j, sibling in enumerate(node[key]):
            if j == i:
                continue
            if key == "all":
                ctx.update(_satisfy(sibling))
            else:
                unanswered |= _inputs_of(sibling)
        node = node[key][i]
    clash = ((set(ctx) | unanswered) & _inputs_of(node)) | (set(ctx) & unanswered)
    assert not clash, (
        f"the leaf {node} shares inputs {sorted(clash)} with the rest of its rule; extend this test"
    )
    return ctx


def _check_grade(
    term: str, answers: Answers, baseline: dict[str, Any] | None, want: int | None, at: Any
) -> None:
    got = rules.grade(term, answers, baseline)
    assert got.provisional_grade == want, (
        f"{term} at {at}: rules.grade() gave {got.provisional_grade}, expected {want}"
    )
    assert got.grade_basis == ("rule" if want is not None else "needs_clinician")
    matching = [
        r["grade"] for r in content.rules_for(term) if rules.evaluate(r["when"], answers, baseline, {})
    ]
    assert matching == ([want] if want is not None else []), (
        f"{term} at {at}: rules of grades {matching} match, expected exactly {want} (bands must not overlap)"
    )


# ---- tests --------------------------------------------------------------------------------------------------


@pytest.mark.req("REQ-004")
def test_the_six_boundaries_come_from_the_data():
    names = {c[0] for c in GRADE_CASES}
    assert SIX_BOUNDARIES <= names, (
        f"boundaries missing from data/ctcae_rules.json: {sorted(SIX_BOUNDARIES - names)}"
    )


@pytest.mark.req("REQ-004")
def test_engine_reads_the_data_under_test(engine_data):
    assert content.data_path("ctcae_rules.json") == engine_data / "ctcae_rules.json"
    on_disk = json.loads((engine_data / "ctcae_rules.json").read_text(encoding="utf-8"))
    assert content.grading_rules() == on_disk["rules"]


@pytest.mark.req("REQ-004")
@pytest.mark.parametrize("name,term,values,pair,exercised", GRADE_CASES, ids=[c[0] for c in GRADE_CASES])
def test_grade_boundary(name, term, values, pair, exercised):
    want = {v: expected_grade(term, v) for v in values}
    if pair:  # the tested values cross the boundary: both of its grades occur
        assert set(pair) <= set(want.values()), f"{name}: the tested values give grades {set(want.values())}"
    first = term_rules(term)[0]["when"]
    for v, g in want.items():
        if term_kind(term) == "numeric":
            answers, baseline = numeric_answers(leaf_input(first), v)
        else:
            answers, baseline = {first["item"]: AnswerInput(option_code=v)}, None
        _check_grade(term, answers, baseline, g, v)


@pytest.mark.req("REQ-005")
@pytest.mark.parametrize("name,flag_id,path,values,exercised", FLAG_CASES, ids=[c[0] for c in FLAG_CASES])
def test_red_flag_threshold(name, flag_id, path, values, exercised):
    rule = next(rf["rule"] for rf in FLAGS["red_flags"] if rf["id"] == flag_id)
    leaf, ctx = leaf_at(rule, path), _context(rule, path)
    outcomes = set()
    for v in values:
        answers, baseline = numeric_answers(leaf_input(leaf), v)
        answers.update(ctx)
        want = leaf_holds(leaf, v)
        outcomes.add(want)
        got = flag_id in {h.id for h in rules.red_flags(answers, baseline)}
        assert got == want, f"{name} at {v}: flag {'raised' if got else 'not raised'}, expected {want}"
    assert outcomes == {True, False}, f"{name}: the tested values never cross the threshold"


@pytest.mark.req("REQ-004")
def test_every_numeric_threshold_is_exercised():
    """No numeric threshold in either rule file escapes the cases above."""
    every = {
        (r["id"], "when", p, op)
        for r in CTCAE["rules"]
        for p, leaf in numeric_leaves(r["when"])
        for op in CMP
        if op in leaf
    }
    every |= {
        (rf["id"], "rule", p, op)
        for rf in FLAGS["red_flags"]
        for p, leaf in numeric_leaves(rf.get("rule"))
        for op in CMP
        if op in leaf
    }
    exercised = {t for c in GRADE_CASES for t in c[-1]} | {t for c in FLAG_CASES for t in c[-1]}
    assert every, "no numeric thresholds found in the rule files"
    assert every <= exercised, f"thresholds that no boundary case exercises: {sorted(every - exercised)}"
