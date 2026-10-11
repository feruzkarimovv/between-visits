"""B16: table-driven tests of the shared Site Signal episode builder (docs/11 §4-§6, REQ-024).

Dates are study days from 2026-01-05 (docs/11 §11.2). Unless a row says otherwise: doses every 21 days from
day 0, calls on days 1, 3 and 7 after each dose (days 1, 3, 7, 22, 24, 28, ...), data cut on day 120.
`cfg` is data/signal_rules.json (app.content.signal_rules()); the expected values restate the SAP's numbers
(gap 21 days, window +7, tolerance -2, entry window 14 days, next visit +8) as test vectors, and
`test_signal_rules_are_the_sap_values` pins them so the table cannot drift from the file.
"""

import ast
import copy
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app import content
from app.services import episodes

CFG = content.signal_rules()
BASE = date(2026, 1, 5)  # study day 0
S1, S2 = "101-001", "101-002"
Q21 = list(range(0, 253, 21))  # dose days
CUT = 120


def d(n: int) -> date:
    return BASE + timedelta(days=n)


def call(call_id: str, on: int, status: str = "completed", level: str = "none", subject: str = S1, **grades):
    return {
        "call_id": call_id, "subject_id": subject, "date": d(on), "status": status, "level": level,
        "grades": grades,
    }


def ae(
    site_ae_id: str, on: int, aeterm: str = "diarrhea", *,
    entered: int | None = None, origin: str = "site", aeseq: int | None = None, subject: str = S1,
):
    return {
        "site_ae_id": site_ae_id, "site_id": "101", "subject_id": subject, "usubjid": f"BV-{subject}",
        "aeseq": int(site_ae_id[1:]) if aeseq is None else aeseq, "aeterm": aeterm, "aetoxgr": "2",
        "aestdtc": d(on), "entered_on": d(on + 8 if entered is None else entered), "origin": origin,
        "symptomatic": True, "data_origin": "SIMULATED",
    }


def run(calls, aes=(), *, cut=CUT, doses=None, ae_end=None, page_proximal=False, cfg=CFG):
    dose_days = doses if doses is not None else {S1: Q21, S2: Q21}
    return episodes.analyze(
        calls, list(aes), cfg,
        data_cut=d(cut),
        dose_dates={s: [d(n) for n in days] for s, days in dose_days.items()},
        ae_end={s: d(n) for s, n in (ae_end or {}).items()},
        page_proximal=page_proximal,
    )


def view(ep: dict) -> dict:
    """An output episode with dates as study days, under the short keys the table uses."""
    return {
        "subject": ep["subject_id"], "term": ep["term"], "grade": ep["grade"], "kind": ep["kind"],
        "date": (ep["episode_date"] - BASE).days, "anchor": (ep["anchor_date"] - BASE).days,
        "ids": ep["checkin_ids"], "paged": ep["paged_level"], "evaluable": ep["evaluable"],
        "ae": ep["matched_site_ae_id"], "status": ep["status"],
    }


def row(row_id: str, calls: list, expected: list[dict], aes: tuple = (), **options):
    return pytest.param(calls, aes, expected, options, id=row_id)


# One D=3 episode whose previous negative call is day 1: observation interval [1, 3], window [-1, 10].
NEG1_EP3 = [call("c1", 1, Diarrhea=0), call("c3", 3, Diarrhea=2)]
# One D=1 episode with no earlier call: L_e = 1 - 21 = -20, window [-22, 8].
EP1 = [call("c1", 1, Diarrhea=2)]

SCENARIOS = [
    # ---- §4.2 construction -------------------------------------------------------------------------------
    row("dedup: day 1, 3 and 7 calls fold into one episode",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=2),
         call("c22", 22, Diarrhea=0)],
        [{"term": "Diarrhea", "grade": 2, "kind": "new", "date": 1, "ids": ["c1", "c3", "c7"], "anchor": -20,
          "status": "unmatched"}]),
    row("a fall from grade 3 to 2 continues the episode and keeps band 3",
        [call("c1", 1, Diarrhea=3), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=0)],
        [{"grade": 3, "kind": "new", "ids": ["c1", "c3"]}]),
    row("a grade below 2 closes the episode; the next grade 2 opens a new one",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=1), call("c7", 7, Diarrhea=2)],
        [{"date": 1, "kind": "new", "ids": ["c1"]}, {"date": 7, "kind": "new", "ids": ["c7"], "anchor": 3}]),
    row("worsened opens new: a higher grade closes the open episode and opens a worsened one",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=3), call("c7", 7, Diarrhea=3),
         call("c22", 22, Diarrhea=0)],
        [{"grade": 2, "kind": "new", "ids": ["c1"]},
         {"grade": 3, "kind": "worsened", "date": 3, "ids": ["c3", "c7"]}]),
    row("the gap closes an episode: next graded call 23 days later opens a new one",
        [call("c1", 1, Diarrhea=2), call("c22", 22, "no_answer"), call("c24", 24, Diarrhea=2)],
        [{"date": 1, "ids": ["c1"]}, {"date": 24, "kind": "new", "ids": ["c24"], "anchor": 3}]),
    row("a gap of exactly 21 days continues the episode",
        [call("c1", 1, Diarrhea=2), call("c22", 22, Diarrhea=2)],
        [{"date": 1, "ids": ["c1", "c22"]}]),
    row("a null grade is skipped: it neither closes nor joins the episode",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=None), call("c7", 7, Diarrhea=2)],
        [{"ids": ["c1", "c7"]}]),
    row("incomplete calls contribute nothing (grades, closing, gap or page)",
        [call("c1", 1, "failed", "emergency", Diarrhea=2), call("c3", 3, Diarrhea=2),
         call("c7", 7, "cancelled", Diarrhea=0), call("c22", 22, "in_progress", Diarrhea=3),
         call("c24", 24, Diarrhea=2)],
        [{"date": 3, "grade": 2, "kind": "new", "ids": ["c3", "c24"], "paged": None, "status": "unmatched"}]),
    row("only primary terms open episodes; output by date, then primary-term order",
        [call("c1", 1, Dyspnea=2, Nausea=3, Diarrhea=2), call("c3", 3, Fever=2, Fatigue=3)],
        [{"term": "Diarrhea", "date": 1}, {"term": "Dyspnea", "date": 1}, {"term": "Fever", "date": 3}]),
    row("subjects are separate: interleaved calls, a row matches only its own subject",
        [call("c1", 1, Diarrhea=2), call("k1", 1, subject=S2, Diarrhea=2),
         call("k3", 3, subject=S2, Diarrhea=0)],
        [{"subject": S1, "ae": None}, {"subject": S2, "ids": ["k1"], "ae": "a1"}],
        aes=(ae("a1", 1, subject=S2),)),
    # ---- §5 candidates: origin, entry date, subject and term (REQ-024) ------------------------------------
    row("origin exclusion: a between_visits row never matches",
        EP1, [{"ae": None, "status": "unmatched"}],
        aes=(ae("a1", 1, origin="between_visits"),)),
    row("origin exclusion: the site row matches although a between_visits row is nearer",
        EP1, [{"ae": "a2", "status": "matched"}],
        aes=(ae("a1", 1, origin="between_visits"), ae("a2", 5))),
    row("origin: only site rows are candidates (an unknown origin never matches)",
        EP1, [{"ae": None, "status": "unmatched"}],
        aes=(ae("a1", 1, origin="unknown"),)),
    row("entered_on after the data cut: not yet in the log",
        EP1, [{"ae": None, "status": "unmatched"}],
        aes=(ae("a1", 1, entered=CUT + 1),)),
    row("entered_on on the data cut: in the log",
        EP1, [{"ae": "a1", "status": "matched"}],
        aes=(ae("a1", 1, entered=CUT),)),
    row("synonyms are matched after lower-casing and trimming",
        EP1, [{"ae": "a1"}],
        aes=(ae("a1", 1, "  Loose Stools "),)),
    row("unmapped terms and other terms never match",
        EP1, [{"ae": None}],
        aes=(ae("a1", 1, "diarrhea nos"), ae("a2", 1, "fever"), ae("a3", 1, "loose  stools"))),
    row("another subject's row never matches",
        EP1, [{"ae": None}],
        aes=(ae("a1", 1, subject=S2),)),
    # ---- §5 window edges and the lower anchor L_e ---------------------------------------------------------
    row("upper window edge: episode date + 7 matches",
        NEG1_EP3, [{"date": 3, "anchor": 1, "ae": "a1"}], aes=(ae("a1", 10),)),
    row("upper window edge: episode date + 8 does not",
        NEG1_EP3, [{"ae": None}], aes=(ae("a1", 11),)),
    row("lower window edge: previous negative call - 2 matches",
        NEG1_EP3, [{"ae": "a1"}], aes=(ae("a1", -1),)),
    row("lower window edge: previous negative call - 3 does not",
        NEG1_EP3, [{"ae": None}], aes=(ae("a1", -2),)),
    row("no previous negative call: L_e = episode date - 21, and - 2 more matches",
        EP1, [{"anchor": -20, "ae": "a1"}], aes=(ae("a1", -22),)),
    row("no previous negative call: episode date - 24 does not match",
        EP1, [{"ae": None}], aes=(ae("a1", -23),)),
    row("a negative call exactly 21 days earlier is L_e",
        [call("c1", 1, Diarrhea=0), call("c22", 22, Diarrhea=2)],
        [{"date": 22, "anchor": 1}]),
    row("a negative call more than 21 days earlier: L_e = episode date - 21",
        [call("c1", 1, Diarrhea=0), call("c24", 24, Diarrhea=2)],
        [{"date": 24, "anchor": 3, "ae": None}], aes=(ae("a1", 0),)),
    row("a negative call earlier on the same day is not before the episode date",
        [call("c1a", 1, Diarrhea=0), call("c1b", 1, Diarrhea=2)],
        [{"date": 1, "ids": ["c1b"], "anchor": -20}]),
    row("worsened episode anchored on the last lower-grade call; each episode gets its own row",
        [call("c1", 1, Diarrhea=1), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=3)],
        [{"kind": "new", "date": 3, "anchor": 1, "ae": "a1"},
         {"kind": "worsened", "date": 7, "anchor": 3, "ae": "a2"}],
        aes=(ae("a1", 1), ae("a2", 5))),
    # ---- §5 one-to-one greedy assignment ------------------------------------------------------------------
    row("one-to-one: the row goes to the nearer episode; the other stays unmatched",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c7", 7, Diarrhea=2)],
        [{"date": 1, "ae": None}, {"date": 7, "anchor": 3, "ae": "a1"}], aes=(ae("a1", 5),)),
    row("equal distance: the earlier episode wins; a worsened episode needs its own row",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=3)],
        [{"kind": "new", "ae": "a1"}, {"kind": "worsened", "ae": None, "status": "unmatched"}],
        aes=(ae("a1", 1),)),
    row("equal distance and date: the lower aeseq wins",
        NEG1_EP3, [{"ae": "a2"}], aes=(ae("a1", 2, aeseq=7), ae("a2", 3, aeseq=4))),
    row("a paged episode keeps its row; the neighbouring episode cannot reuse it",
        [call("c1", 1, level="urgent", Diarrhea=2), call("c3", 3, Diarrhea=0), call("c7", 7, Diarrhea=2)],
        [{"status": "paged", "paged": "urgent", "ae": "a1"}, {"status": "unmatched", "ae": None}],
        aes=(ae("a1", 1),)),
    # ---- §6.2 paged stratum -------------------------------------------------------------------------------
    row("paged beats pending",
        [call("c106", 106, level="urgent", Diarrhea=2)],
        [{"evaluable": False, "paged": "urgent", "status": "paged"}]),
    row("callback is not a paged level",
        [call("c1", 1, level="callback", Diarrhea=2)],
        [{"paged": None, "status": "unmatched"}]),
    row("paged level is the highest page on the folded calls",
        [call("c1", 1, level="urgent", Diarrhea=2), call("c3", 3, level="emergency", Diarrhea=2),
         call("c7", 7, level="urgent", Diarrhea=2)],
        [{"ids": ["c1", "c3", "c7"], "paged": "emergency", "status": "paged"}]),
    row("a page on a call with no gradable answer for the term does not page the episode",
        [call("c1", 1, Diarrhea=2), call("c3", 3, level="urgent", Diarrhea=None), call("c7", 7, Diarrhea=2)],
        [{"ids": ["c1", "c7"], "paged": None, "status": "unmatched"}]),
    # ---- §6.1 evaluability --------------------------------------------------------------------------------
    row("pending boundary: next dose visit (day 21) + 8 = day 29, cut 28 is pending",
        EP1, [{"evaluable": False, "status": "pending"}], cut=28),
    row("pending boundary: cut 29 is evaluable",
        EP1, [{"evaluable": True, "status": "unmatched"}], cut=29),
    row("pending boundary: episode date (7) + 14 = day 21 with a dose on day 10, cut 20 is pending",
        [call("c7", 7, Diarrhea=2)], [{"status": "pending"}], cut=20, doses={S1: [0, 10]}),
    row("pending boundary: cut 21 is evaluable",
        [call("c7", 7, Diarrhea=2)], [{"status": "unmatched"}], cut=21, doses={S1: [0, 10]}),
    row("a delayed dose is the next dose visit (day 30 + 8)",
        EP1, [{"status": "pending"}], cut=37, doses={S1: [0, 30]}),
    row("a dose visit on the episode date is not the next one (day 28 + 8)",
        [call("c7", 7, Diarrhea=2)], [{"status": "pending"}], cut=35, doses={S1: [0, 7, 28]}),
    row("no known dose visit after the episode: pending",
        EP1, [{"status": "pending"}], cut=252, doses={S1: [0]}),
    row("a pending episode is matched but stays pending",
        [call("c106", 106, Diarrhea=2)], [{"status": "pending", "ae": "a1"}],
        aes=(ae("a1", 106, entered=110),)),
    row("an episode after the end of AE collection is never evaluable",
        [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c7", 7, Diarrhea=2)],
        [{"date": 1, "status": "unmatched"}, {"date": 7, "status": "pending"}], ae_end={S1: 5}),
]


@pytest.mark.req("REQ-024")
@pytest.mark.parametrize(("calls", "aes", "expected", "options"), SCENARIOS)
def test_episode_table(calls, aes, expected, options):
    got = [view(ep) for ep in run(calls, aes, **options)]
    assert len(got) == len(expected), got
    assert [{key: g[key] for key in e} for g, e in zip(got, expected, strict=True)] == expected


STATUS_TABLE = [
    # paged_level, evaluable, matched_site_ae_id, not_evaluated -> status (§6.4 precedence)
    ("urgent", False, None, False, "paged"),
    ("emergency", True, "a1", True, "paged"),
    (None, False, "a1", True, "pending"),
    (None, False, None, False, "pending"),
    (None, True, "a1", True, "not_evaluated"),
    (None, True, None, True, "not_evaluated"),
    (None, True, "a1", False, "matched"),
    (None, True, None, False, "unmatched"),
]


@pytest.mark.req("REQ-024")
@pytest.mark.parametrize(("paged_level", "evaluable", "site_ae_id", "not_evaluated", "status"), STATUS_TABLE)
def test_status_precedence(paged_level, evaluable, site_ae_id, not_evaluated, status):
    ep = {"paged_level": paged_level, "evaluable": evaluable, "matched_site_ae_id": site_ae_id}
    assert episodes.status_of(ep, not_evaluated=not_evaluated) == status
    assert episodes.STATUSES == ("paged", "pending", "not_evaluated", "matched", "unmatched")


@pytest.mark.req("REQ-024")
def test_paged_episodes_are_a_separate_stratum_outside_oe():
    calls = [
        call("c1", 1, level="urgent", Diarrhea=2), call("c3", 3, Diarrhea=0),
        call("c7", 7, Diarrhea=2), call("c22", 22, Diarrhea=0),
        call("c24", 24, level="emergency", Dyspnea=3),
        call("c43", 43, Fever=2),
    ]
    aes = (ae("a1", 1), ae("a2", 7, origin="between_visits"), ae("a3", 24, "Shortness of breath"))
    eps = run(calls, aes)
    assert [(e["term"], e["status"], e["matched_site_ae_id"]) for e in eps] == [
        ("Diarrhea", "paged", "a1"), ("Diarrhea", "unmatched", None),
        ("Dyspnea", "paged", "a3"), ("Fever", "unmatched", None),
    ]
    assert episodes.paged_stratum(eps) == {"n": 2, "matched": 2}
    oe = [e for e in eps if e["status"] in episodes.OE_STATUSES]
    assert len(oe) == 2 and all(e["paged_level"] is None for e in oe)
    assert all(e["status"] not in episodes.ANALYSIS_SET_STATUSES for e in eps if e["paged_level"])


@pytest.mark.req("REQ-024")
def test_page_proximal_sensitivity_se14():
    """SE14: any page of the subject within paged.proximity_days (7) of the episode date pages it too."""
    calls = [
        call("c1", 1, level="urgent", Fever=None),  # a page 6 days before the day-7 episode, not folded in
        call("c7", 7, Diarrhea=2), call("c22", 22, Diarrhea=0),
        call("c24", 24, Dyspnea=2), call("c28", 28, Dyspnea=0),
        call("c32", 32, "failed", "emergency"),  # 8 days after day 24: outside the window
        call("c43", 43, Diarrhea=2),
        call("c50", 50, "failed", "emergency"),  # 7 days after day 43, on an incomplete call: inside
    ]
    primary = run(calls)
    assert [(e["date"], e["paged"]) for e in map(view, primary)] == [(7, None), (24, None), (43, None)]
    proximal = run(calls, page_proximal=True)
    assert [(e["date"], e["paged"], e["status"]) for e in map(view, proximal)] == [
        (7, "urgent", "paged"), (24, None, "unmatched"), (43, "emergency", "paged"),
    ]


SENSITIVITY_TABLE = [
    # sensitivity id, AESTDTC day for the NEG1_EP3 episode (L_e 1, D_e 3), matched?
    ("SE1", 6, True), ("SE1", 7, False), ("SE1", 1, True), ("SE1", 0, False),
    ("SE2", 17, True), ("SE2", 18, False), ("SE2", -6, True), ("SE2", -7, False),
]


@pytest.mark.req("REQ-024")
@pytest.mark.parametrize(("sensitivity_id", "aestdtc", "matched"), SENSITIVITY_TABLE)
def test_match_sensitivity_windows(sensitivity_id, aestdtc, matched):
    cfg = episodes.with_match_sensitivity(CFG, sensitivity_id)
    assert CFG["match"]["window_days"] == 7  # the shared cfg is not modified
    [ep] = run(NEG1_EP3, [ae("a1", aestdtc, entered=aestdtc + 1)], cfg=cfg)
    assert (ep["matched_site_ae_id"] == "a1") is matched


def test_date_kinds_give_the_same_episodes():
    """date objects, ISO strings and int day numbers are interchangeable; output dates keep the input type."""
    calls = [call("c1", 1, Diarrhea=1), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=3),
             call("c22", 22, Diarrhea=0)]
    aes = [ae("a1", 1), ae("a2", 5, "dyspnea"), ae("a3", 6, origin="between_visits")]

    def recast(record: dict, fn) -> dict:
        return {k: fn(v) if isinstance(v, date) else v for k, v in record.items()}

    def analyze(fn) -> list[dict]:
        return episodes.analyze(
            [recast(c, fn) for c in calls], [recast(a, fn) for a in aes], CFG,
            data_cut=fn(d(CUT)), dose_dates={S1: [fn(d(n)) for n in Q21]},
        )

    as_dates = analyze(lambda v: v)
    assert [(e["kind"], e["status"]) for e in as_dates] == [("new", "matched"), ("worsened", "unmatched")]
    for fn in (date.isoformat, lambda v: (v - BASE).days):
        assert [recast(e, fn) for e in as_dates] == analyze(fn)


def test_datetimes_are_refused():
    """A call's date is the DISPLAY_TZ local date (timeutil.local_date), never a UTC timestamp's date."""
    bad = call("c1", 1, Diarrhea=2) | {"date": datetime(2026, 1, 6, 3, 30, tzinfo=UTC)}
    with pytest.raises(TypeError, match="local date"):
        episodes.build_episodes([bad], CFG)


def test_inputs_are_not_mutated():
    calls = [call("c1", 1, level="urgent", Diarrhea=2), call("c3", 3, Diarrhea=3)]
    aes = [ae("a1", 1)]
    before = copy.deepcopy((calls, aes))
    eps = episodes.build_episodes(calls, CFG)
    snapshot = copy.deepcopy(eps)
    episodes.classify(eps, aes, CFG, data_cut=d(CUT), dose_dates={S1: [d(n) for n in Q21]})
    assert (calls, aes) == before and eps == snapshot


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("episode", "worsened_opens_new"), False),
        (("match", "lower_anchor"), "episode_date"),
        (("match", "one_to_one"), False),
        (("paged", "levels"), ["urgent", "page_me"]),
        (("match", "term_synonyms", "Fever"), ["fever", "Diarrhoea "]),
    ],
)
def test_unspecified_signal_rules_are_refused(path, value):
    cfg = copy.deepcopy(CFG)
    target = cfg
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="signal_rules"):
        episodes.build_episodes([call("c1", 1, Diarrhea=2)], cfg)


def test_signal_rules_are_the_sap_values():
    """The table above restates these docs/11 §4-§6 values; this keeps the table and the file in step."""
    assert CFG["primary_terms"] == ["Diarrhea", "Fever", "Dyspnea"] and CFG["min_grade"] == 2
    assert CFG["episode"] == {"gap_days": 21, "worsened_opens_new": True}
    m = CFG["match"]
    assert (m["window_days"], m["lower_tolerance_days"], m["lower_anchor"]) == (7, 2, "last_negative_call")
    assert m["exclude_origins"] == ["between_visits"] and m["one_to_one"] is True
    assert {s["id"]: (s["window_days"], s["lower_tolerance_days"]) for s in m["sensitivity"]} == {
        "SE1": (3, 0), "SE2": (14, 7),
    }
    assert CFG["evaluability"] == {"entry_window_days": 14, "next_visit_plus_days": 8}
    assert CFG["paged"]["levels"] == ["urgent", "emergency"] and CFG["paged"]["proximity_days"] == 7


def test_imports_are_standard_library_and_app_only():
    """Shared with monitoring/: no database, web, LLM or third-party import (docs/11 §4.2, rule 1)."""
    tree = ast.parse(Path(episodes.__file__).read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules == {"bisect", "collections.abc", "datetime", "operator", "typing", "app.services.rules"}
    assert all(m.split(".")[0] in sys.stdlib_module_names or m == "app.services.rules" for m in modules)
