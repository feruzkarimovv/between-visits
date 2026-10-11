"""S3: table-driven tests of monitoring/bvsignal/match.py (docs/11 §5-§8.1; REQ-024, REQ-025). SIMULATED, dev seed.

Dates are integer study days (app.services.episodes accepts day numbers). Unless a row says otherwise a study
is ten filler sites, 101-110, plus the site under test, 120, with the data cut on day 120. Each filler site has
10 patients and 20 evaluable, non-paged Diarrhea grade 2 episodes on days 1 and 22 (each closed by a grade 0
call two days later; doses every 21 days from day 0), of which 15 are matched by a site row dated on the
episode date, so every leave-one-site-out Diarrhea rate the fillers give is 150/200 = 0.75.

The expected values restate the SAP's numbers (window +7, tolerance -2, gap 21 days, entry window 14 days,
next visit +8, minimum data 0.60 / 10 patients / 15 episodes / 10 sites) as test vectors;
`test_signal_rules_are_the_sap_values` pins them so the tables cannot drift from data/signal_rules.json.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from bvsignal import DATA_ORIGIN, MONITORING_DIR, match
from bvsignal import seed as bvseed
from bvsignal import simulate as sim
from bvsignal._backend import episodes

CFG = match.load_signal_rules()
PARAMS = bvseed.load_params()
MIN_SITES = int(CFG["minimum_data"]["min_sites"])
CUT = 120
Q21 = tuple(range(0, 253, 21))  # dose days
SLOTS = (1, 22, 43, 64)  # filler episode days (one per patient per slot)
FILLER_IDS = tuple(str(101 + k) for k in range(10))
TEST_SITE = "120"
S = "120-001"
SE = {sid: sim.scenario_from_params(PARAMS, sid).analysis for sid in ("SE1", "SE2", "SE14", "SE20", "SE21")}


def call(call_id: str, day: Any, level: str = "none", status: str = "completed", subject: str = S,
         **grades: int | None) -> dict[str, Any]:
    return {"call_id": call_id, "subject_id": subject, "date": day, "status": status, "level": level,
            "grades": grades}


def ae(site_ae_id: str, day: int, aeterm: str = "diarrhea", *, entered: int | None = None, origin: str = "site",
       aeseq: int | None = None, subject: str = S) -> dict[str, Any]:
    return {"site_ae_id": site_ae_id, "subject_id": subject, "usubjid": f"BVSIM-{subject}",
            "aeseq": int(site_ae_id.rsplit("a", 1)[-1]) if aeseq is None else aeseq, "aeterm": aeterm,
            "aetoxgr": "2", "aestdtc": day, "entered_on": day + 8 if entered is None else entered,
            "origin": origin, "symptomatic": True, "data_origin": DATA_ORIGIN}


def every_fourth(j: int) -> bool:
    return j % 4 == 3


def never(j: int) -> bool:
    return False


def always(j: int) -> bool:
    return True


def first_only(j: int) -> bool:
    return j == 0


@dataclass(frozen=True)
class Group:
    """`n` episodes of one term and band: episode j goes to patient j % patients on day days[j // patients],
    with a grade 0 call two days later; a site row dated on the episode date unless `unmatched(j)`."""

    term: str = "Diarrhea"
    grade: int = 2
    n: int = 20
    unmatched: Callable[[int], bool] = every_fourth
    level: str = "none"
    days: tuple[int, ...] = SLOTS


def site(site_id: str, *, patients: int = 10, groups: tuple[Group, ...] = (Group(),),
         coverage: tuple[int, int] | None = None, bv_row: bool = False, draft_roles: tuple[str, ...] = (),
         broken: bool = False, load_error: str | None = None) -> match.SiteData:
    subjects = [f"{site_id}-{i + 1:03d}" for i in range(patients)]
    calls: list[dict[str, Any]] = []
    aes: list[dict[str, Any]] = []
    seq: Counter[str] = Counter()
    for g in groups:
        for j in range(g.n):
            subject, day = subjects[j % patients], g.days[j // patients]
            calls.append(call(f"c{site_id}_{len(calls)}", day, g.level, subject=subject, **{g.term: g.grade}))
            calls.append(call(f"c{site_id}_{len(calls)}", day + 2, subject=subject, **{g.term: 0}))
            if not g.unmatched(j):
                seq[subject] += 1
                aes.append(ae(f"ae_{site_id}_a{len(aes) + 1}", day, g.term.lower(), aeseq=seq[subject],
                              subject=subject))
    if bv_row:  # a confirmed Between Visits draft in the site's log (docs/11 §2.4)
        aes.append(ae(f"ae_{site_id}_bv", 1, origin="between_visits", aeseq=seq[subjects[0]] + 1,
                      subject=subjects[0]))
    if broken:  # a UTC datetime instead of the local call date: episodes.py refuses it with TypeError
        calls.append(call(f"c{site_id}_bad", datetime(2026, 1, 6, tzinfo=UTC), subject=subjects[0], Diarrhea=0))
    scheduled, completed = coverage if coverage is not None else (len(calls), len(calls))
    return match.SiteData(site_id=site_id, subject_ids=tuple(subjects), calls=calls, site_aes=aes,
                          dose_dates={s: Q21 for s in subjects}, scheduled_calls=scheduled,
                          completed_calls=completed, draft_action_roles=draft_roles, load_error=load_error)


FILLERS = [site(i) for i in FILLER_IDS]


def test_signal_rules_are_the_sap_values() -> None:
    """The constants the tables restate (docs/11 §4.2, §5, §6.1, §6.2, §7)."""
    assert CFG["primary_terms"] == ["Diarrhea", "Fever", "Dyspnea"] and CFG["min_grade"] == 2
    assert CFG["episode"]["gap_days"] == 21
    m = CFG["match"]
    assert (m["window_days"], m["lower_tolerance_days"], m["exclude_origins"]) == (7, 2, ["between_visits"])
    assert {e["id"]: (e["window_days"], e["lower_tolerance_days"]) for e in m["sensitivity"]} == {
        "SE1": (3, 0), "SE2": (14, 7)}
    assert CFG["evaluability"] == {"entry_window_days": 14, "next_visit_plus_days": 8}
    assert CFG["paged"]["levels"] == ["urgent", "emergency"] and CFG["paged"]["proximity_days"] == 7
    assert CFG["minimum_data"] == {"min_sites": 10, "min_patients": 10, "min_evaluable_episodes": 15,
                                   "min_call_completion": 0.60}
    assert CFG["integrated_mode"]["site_roles"] == ["coordinator", "investigator"]
    # every reason match.py can set has a label, in the §7 order (docs/03 §5.3)
    assert match.REASONS == ("error", "integrated_mode", "low_coverage", "insufficient_patients",
                             "insufficient_episodes", "study_below_min_sites")
    assert set(match.REASONS) == set(CFG["labels"]["reasons"])
    assert dict(SE["SE20"]) == {"next_visit_plus_days": 19} and dict(SE["SE14"]) == {"paged_rule": "page_proximal"}


# ---- episode-level table: matching, evaluability, paging and not_evaluated through match.py -------------------


def run_subject(calls: list[dict[str, Any]], aes: tuple[dict[str, Any], ...] = (), *, doses: tuple[int, ...] = Q21,
                analysis: Any = None) -> match.StudyMatch:
    """The subject S alone at site 120 (insufficient_patients, so its episodes keep matched/unmatched), next to
    the ten fillers."""
    test = match.SiteData(site_id=TEST_SITE, subject_ids=(S,), calls=calls, site_aes=list(aes),
                          dose_dates={S: doses}, scheduled_calls=len(calls), completed_calls=len(calls))
    return match.analyze_sites([*FILLERS, test], CFG, data_cut=CUT, analysis=analysis)


def view(ep: dict[str, Any], p: float | None) -> dict[str, Any]:
    return {"term": ep["term"], "grade": ep["grade"], "kind": ep["kind"], "date": ep["episode_date"],
            "anchor": ep["anchor_date"], "status": ep["status"], "ae": ep["matched_site_ae_id"],
            "paged": ep["paged_level"], "p": p}


def erow(row_id: str, calls: list[dict[str, Any]], expected: list[dict[str, Any]], aes: tuple = (), **options: Any):
    return pytest.param(calls, aes, expected, options, id=row_id)


# D = 3 after a negative call on day 1: observation interval [1, 3], primary window [-1, 10]
NEG1_EP3 = [call("c1", 1, Diarrhea=0), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=0)]
# D = 1 (L = -20, window [-22, 8]) and D = 7 after the negative call on day 3 (L = 3, window [1, 14])
TWO_EPS = [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c7", 7, Diarrhea=2), call("c22", 22, Diarrhea=0)]
# new (D = 3, L = 1, band 2) then worsened (D = 7, band 3) anchored on the last lower-grade call, day 3
WORSENED = [call("c1", 1, Diarrhea=0), call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=3),
            call("c22", 22, Diarrhea=0)]
DOSES_112 = (0, 21, 42, 63, 84, 105, 112)
M = {"status": "matched", "p": 0.75}
U = {"status": "unmatched", "ae": None, "p": 0.75}
PENDING = {"status": "pending", "ae": None, "p": None}

EPISODE_ROWS = [
    # ---- §5 window edges ---------------------------------------------------------------------------------------
    erow("window: AESTDTC = D + 7 matches", NEG1_EP3, [{"date": 3, "anchor": 1, "ae": "a1", **M}], (ae("a1", 10),)),
    erow("window: AESTDTC = D + 8 does not match", NEG1_EP3, [{"date": 3, **U}], (ae("a1", 11),)),
    erow("window: AESTDTC = previous negative call - 2 matches", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", -1),)),
    erow("window: AESTDTC = previous negative call - 3 does not match", NEG1_EP3, [U], (ae("a1", -2),)),
    erow("no previous negative call: L = D - 21, so D - 23 matches",
         [call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=0)], [{"anchor": -18, "ae": "a1", **M}], (ae("a1", -20),)),
    erow("no previous negative call: D - 24 does not match",
         [call("c3", 3, Diarrhea=2), call("c7", 7, Diarrhea=0)], [{"anchor": -18, **U}], (ae("a1", -21),)),
    erow("a negative call more than 21 days before D is not the anchor: L = D - 21, D - 24 does not match",
         [call("c1", 1, Diarrhea=0), call("c30", 30, Diarrhea=2), call("c31", 31, Diarrhea=0)],
         [{"date": 30, "anchor": 9, **U}], (ae("a1", 6),)),
    erow("worsened episode anchored on the last lower-grade call: L - 2 matches", WORSENED,
         [{"kind": "new", "grade": 2, "date": 3, "anchor": 1, "ae": "a1", **M},
          {"kind": "worsened", "grade": 3, "date": 7, "anchor": 3, "ae": "a2", **M}],
         (ae("a1", 3, aeseq=1), ae("a2", 1, aeseq=2))),
    erow("worsened episode: L - 3 does not match", WORSENED,
         [{"kind": "new", "ae": "a1", **M}, {"kind": "worsened", "anchor": 3, **U}],
         (ae("a1", 3, aeseq=1), ae("a2", 0, aeseq=2))),
    erow("SE1 window: D + 3 matches", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", 6),), analysis=SE["SE1"]),
    erow("SE1 window: D + 4 does not match (the primary window would)", NEG1_EP3, [U], (ae("a1", 7),),
         analysis=SE["SE1"]),
    erow("SE1 window: tolerance 0, previous negative call - 1 does not match", NEG1_EP3, [U], (ae("a1", 0),),
         analysis=SE["SE1"]),
    erow("SE2 window: D + 14 matches", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", 17),), analysis=SE["SE2"]),
    erow("SE2 window: D + 15 does not match", NEG1_EP3, [U], (ae("a1", 18),), analysis=SE["SE2"]),
    erow("SE2 window: previous negative call - 7 matches", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", -6),),
         analysis=SE["SE2"]),
    erow("SE2 window: previous negative call - 8 does not match", NEG1_EP3, [U], (ae("a1", -7),),
         analysis=SE["SE2"]),
    # ---- §5 one-to-one greedy assignment ---------------------------------------------------------------------------
    erow("greedy: the nearest episode takes the row (distance 0 beats 5)", TWO_EPS,
         [{"date": 1, **U}, {"date": 7, "ae": "a1", **M}], (ae("a1", 6),)),
    erow("greedy: a tie on distance goes to the earlier episode date", TWO_EPS,
         [{"date": 1, "ae": "a1", **M}, {"date": 7, **U}], (ae("a1", 2),)),
    erow("greedy: a tie on distance and date goes to the lower aeseq", NEG1_EP3, [{"ae": "a2", **M}],
         (ae("a1", 2, aeseq=2), ae("a2", 3, aeseq=1))),
    erow("one-to-one: two rows and two episodes, each row used once", TWO_EPS,
         [{"date": 1, "ae": "a1", **M}, {"date": 7, "ae": "a2", **M}], (ae("a1", 2), ae("a2", 6))),
    # ---- §2.2 candidates: synonyms, unmapped terms, origin, entry date ------------------------------------------------
    erow("synonym, case and whitespace: '  Loose STOOLS  ' matches Diarrhea", NEG1_EP3, [{"ae": "a1", **M}],
         (ae("a1", 3, "  Loose STOOLS  "),)),
    erow("synonym: 'Diarrhoea' matches Diarrhea", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", 3, "Diarrhoea"),)),
    erow("an unmapped aeterm never matches", NEG1_EP3, [U], (ae("a1", 3, "loose stool"),)),
    erow("another term's synonym does not match", NEG1_EP3, [U], (ae("a1", 3, "pyrexia"),)),
    erow("origin between_visits never matches (and the site becomes integrated_mode: not_evaluated)", NEG1_EP3,
         [{"status": "not_evaluated", "ae": None, "p": None}], (ae("a1", 3, origin="between_visits"),)),
    erow("entered_on after the data cut: not in the log", NEG1_EP3, [U], (ae("a1", 3, entered=CUT + 1),)),
    erow("entered_on on the data cut: in the log", NEG1_EP3, [{"ae": "a1", **M}], (ae("a1", 3, entered=CUT),)),
    # ---- §6.1 evaluability (both terms) and SE20 ---------------------------------------------------------------------
    erow("evaluable on both edges: D + 14 = cut and next dose + 8 = cut", [call("c106", 106, Diarrhea=2)],
         [{"date": 106, **U}], doses=DOSES_112),
    erow("pending by the entry window: D + 14 > cut", [call("c107", 107, Diarrhea=2)], [PENDING], doses=DOSES_112),
    erow("pending by the next visit: next dose + 8 > cut", [call("c100", 100, Diarrhea=2)], [PENDING],
         doses=(0, 21, 42, 63, 84, 113)),
    erow("pending with no dose visit after the episode", [call("c100", 100, Diarrhea=2)], [PENDING],
         doses=(0, 21, 42, 63, 84)),
    erow("pending even when already matched (no early-match bias)", [call("c107", 107, Diarrhea=2)],
         [{"status": "pending", "ae": "a1", "p": None}], (ae("a1", 107, entered=CUT),), doses=DOSES_112),
    erow("SE20 (next visit + 19): next dose on day 101 is evaluable", [call("c100", 100, Diarrhea=2)], [U],
         doses=(0, 21, 42, 63, 84, 101), analysis=SE["SE20"]),
    erow("SE20 (next visit + 19): next dose on day 102 is pending", [call("c100", 100, Diarrhea=2)], [PENDING],
         doses=(0, 21, 42, 63, 84, 102), analysis=SE["SE20"]),
    # ---- §6.2 paged stratum and §6.4 precedence ----------------------------------------------------------------------
    erow("paged (urgent) takes precedence over pending", [call("c107", 107, "urgent", Diarrhea=2)],
         [{"status": "paged", "paged": "urgent", "p": None}], doses=DOSES_112),
    erow("paged (emergency) on a later folded call; still matched, descriptive only",
         [call("c1", 1, Diarrhea=2), call("c3", 3, "emergency", Diarrhea=2), call("c7", 7, Diarrhea=0)],
         [{"status": "paged", "paged": "emergency", "ae": "a1", "p": None}], (ae("a1", 1),)),
    erow("a callback is not a page", [call("c1", 1, "callback", Diarrhea=2), call("c3", 3, Diarrhea=0)],
         [{"paged": None, **U}]),
    erow("SE14 page-proximal: an urgent page 7 days after D on another call pages the episode",
         [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c8", 8, "urgent", Diarrhea=0)],
         [{"status": "paged", "paged": "urgent", "p": None}], analysis=SE["SE14"]),
    erow("SE14 page-proximal: a page 8 days away does not",
         [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c9", 9, "urgent", Diarrhea=0)], [U],
         analysis=SE["SE14"]),
    erow("primary paged rule: a page on a call not folded into the episode does not page it",
         [call("c1", 1, Diarrhea=2), call("c3", 3, Diarrhea=0), call("c8", 8, "urgent", Diarrhea=0)], [U]),
    # ---- §8.1 leave-one-site-out rate and not_evaluated (§6.4) ----------------------------------------------------------
    erow("no leave-one-site-out rate for the cell or the term: not_evaluated",
         [call("c1", 1, Fever=2), call("c3", 3, Fever=0)],
         [{"term": "Fever", "status": "not_evaluated", "ae": None, "p": None}]),
    erow("a cell with no episodes at the other sites uses the term's rate pooled over bands",
         [call("c1", 1, Diarrhea=3), call("c3", 3, Diarrhea=0)], [{"grade": 3, **U}]),
]


@pytest.mark.req("REQ-024")
@pytest.mark.parametrize(("calls", "aes", "expected", "options"), EPISODE_ROWS)
def test_episode_rows(calls: list, aes: tuple, expected: list[dict], options: dict) -> None:
    res = run_subject(calls, aes, **options)
    test = res.site(TEST_SITE)
    got = [view(ep, p) for ep, p in zip(test.episodes, test.p_hat, strict=True)]
    assert len(got) == len(expected), got
    for g, want in zip(got, expected, strict=True):
        assert {k: g[k] for k in want} == want, g
    for ep in test.episodes:
        assert ep["site_id"] == TEST_SITE and ep["data_origin"] == DATA_ORIGIN
        assert ep["episode_id"].startswith(f"ep_{TEST_SITE}_")
    # the subject's episodes never change the ten fillers' status
    assert all(res.site(f).computed for f in FILLER_IDS)


# ---- site-level table: the §7 checks in order, study minimum, not_evaluated, O/E/V ------------------------------------


def srow(row_id: str, sites: list[match.SiteData], reasons: dict[str, str | None], *, fillers: list | None = None,
         n_fillers: int = len(FILLER_IDS), filler_reason: str | None = None, study: str | None = None,
         check: Callable[[match.StudyMatch], None] | None = None, req024: bool = False):
    marks = [pytest.mark.req("REQ-024")] if req024 else []
    pool = (FILLERS if fillers is None else fillers)[:n_fillers]
    return pytest.param(pool, sites, reasons, filler_reason, study, check, id=row_id, marks=marks)


def statuses(res: match.StudyMatch, site_id: str) -> Counter[str]:
    return Counter(ep["status"] for ep in res.site(site_id).episodes)


def filler_e(value: float) -> Callable[[match.StudyMatch], None]:
    def check(res: match.StudyMatch) -> None:
        for f in FILLER_IDS:
            assert res.site(f).E == pytest.approx(value, rel=1e-12)
    return check


def check_counts(evaluable: int, pending: int, paged: int) -> Callable[[match.StudyMatch], None]:
    def check(res: match.StudyMatch) -> None:
        t = res.site(TEST_SITE)
        assert (t.n_episodes_evaluable, t.n_pending, t.n_paged) == (evaluable, pending, paged)
    return check


def check_error(res: match.StudyMatch) -> None:
    t = res.site(TEST_SITE)
    assert t.error is not None and t.error.startswith("TypeError") and t.episodes == []


def check_v(v: float, o: int, e: float) -> Callable[[match.StudyMatch], None]:
    def check(res: match.StudyMatch) -> None:
        t = res.site(TEST_SITE)
        assert (t.O, t.E, t.n_episodes_evaluable) == (o, pytest.approx(e), 15)
        assert t.V == pytest.approx(v, abs=1e-12)
        assert set(t.p_hat) == {1.0}
    return check


def check_low_coverage_keeps_status(res: match.StudyMatch) -> None:
    """§6.4: valid data at a low_coverage site keep matched/unmatched (citable in a query) and feed the other
    sites' rates (§8.1): 135 matched of 200 for every filler."""
    assert statuses(res, TEST_SITE) == Counter({"unmatched": 20})
    filler_e(20 * 135 / 200)(res)


def check_integrated_excluded(res: match.StudyMatch) -> None:
    """§2.4, §6.4, §8.1: the integrated site's evaluable episodes are not_evaluated and add nothing to the rates."""
    t = res.site(TEST_SITE)
    assert statuses(res, TEST_SITE) == Counter({"not_evaluated": 20})
    assert t.O is None and t.E is None and t.V is None and set(t.p_hat) == {None}
    filler_e(15.0)(res)


PRECEDENCE_GROUPS = (
    Group(n=15),  # evaluable, not paged: 3 unmatched (j = 3, 7, 11), 12 matched
    Group(n=2, level="urgent", days=(43,)),  # paged, evaluable
    Group(n=2, days=(110,)),  # pending (110 + 14 > 120)
    Group(n=2, level="emergency", days=(113,)),  # paged and pending
)


def check_precedence(integrated: bool) -> Callable[[match.StudyMatch], None]:
    def check(res: match.StudyMatch) -> None:
        t = res.site(TEST_SITE)
        if integrated:
            assert statuses(res, TEST_SITE) == Counter({"not_evaluated": 15, "paged": 4, "pending": 2})
        else:
            assert statuses(res, TEST_SITE) == Counter({"matched": 12, "unmatched": 3, "paged": 4, "pending": 2})
            assert (t.O, t.E) == (12, pytest.approx(15 * 0.75))  # paged and pending never enter O or E
        # reported separately (§6.2); the day-113 rows are entered after the data cut, so 2 of the 4 are matched
        assert t.paged_stratum == {"n": 4, "matched": 2}
        assert t.n_episodes_evaluable == 15
    return check


DYSPNEA_FILLERS = [site(i, groups=(Group(), Group("Dyspnea", n=10, unmatched=never, days=(43,)))) for i in FILLER_IDS]

SITE_ROWS = [
    # ---- §7 order 3: coverage --------------------------------------------------------------------------------------
    srow("coverage 0.59: low_coverage", [site(TEST_SITE, coverage=(100, 59))], {TEST_SITE: "low_coverage"}),
    srow("coverage 0.60: computed", [site(TEST_SITE, coverage=(100, 60))], {TEST_SITE: None}),
    srow("no scheduled call: coverage 0, low_coverage", [site(TEST_SITE, coverage=(0, 0))],
         {TEST_SITE: "low_coverage"}),
    # ---- order 4: patients ---------------------------------------------------------------------------------------------
    srow("9 patients: insufficient_patients", [site(TEST_SITE, patients=9, groups=(Group(n=18),))],
         {TEST_SITE: "insufficient_patients"}),
    srow("10 patients: computed", [site(TEST_SITE, groups=(Group(n=18),))], {TEST_SITE: None}),
    # ---- order 5: evaluable non-paged episodes and V_s = 0 ---------------------------------------------------------------
    srow("14 evaluable episodes: insufficient_episodes", [site(TEST_SITE, groups=(Group(n=14),))],
         {TEST_SITE: "insufficient_episodes"}),
    srow("15 evaluable episodes: computed", [site(TEST_SITE, groups=(Group(n=15),))], {TEST_SITE: None}),
    srow("pending and paged episodes do not count toward the 15",
         [site(TEST_SITE, groups=(Group(n=14), Group(n=3, level="urgent", days=(43,)), Group(n=3, days=(110,))))],
         {TEST_SITE: "insufficient_episodes"}, check=check_counts(14, 3, 3), req024=True),
    srow("V_s = 0 (every rate 1 and every episode matched): insufficient_episodes",
         [site(TEST_SITE, groups=(Group("Dyspnea", n=15, unmatched=never),))], {TEST_SITE: "insufficient_episodes"},
         fillers=DYSPNEA_FILLERS, check=check_v(0.0, 15, 15.0)),
    srow("rates all 1 but one episode unmatched: V_s = n/(n-1) > 0, computed",
         [site(TEST_SITE, groups=(Group("Dyspnea", n=15, unmatched=first_only),))], {TEST_SITE: None},
         fillers=DYSPNEA_FILLERS, check=check_v(10 / 9, 14, 15.0)),
    # ---- order 2: integrated mode (§2.4) ----------------------------------------------------------------------------------
    srow("an origin between_visits row: integrated_mode, excluded from the rates",
         [site(TEST_SITE, bv_row=True, groups=(Group(unmatched=always),))], {TEST_SITE: "integrated_mode"},
         check=check_integrated_excluded, req024=True),
    srow("a draft action by a coordinator: integrated_mode", [site(TEST_SITE, draft_roles=("coordinator",))],
         {TEST_SITE: "integrated_mode"}),
    srow("a draft action by an investigator: integrated_mode", [site(TEST_SITE, draft_roles=("investigator",))],
         {TEST_SITE: "integrated_mode"}),
    srow("draft actions by cra and sponsor roles are not site roles: computed",
         [site(TEST_SITE, draft_roles=("cra", "sponsor"))], {TEST_SITE: None}),
    # ---- order 1: errors ---------------------------------------------------------------------------------------------------
    srow("an exception while analysing the site: error with its message, the others computed",
         [site(TEST_SITE, broken=True)], {TEST_SITE: "error"}, check=check_error),
    srow("an exception while loading the site: error", [site(TEST_SITE, load_error="unreadable file")],
         {TEST_SITE: "error"}),
    # ---- the order of the checks ---------------------------------------------------------------------------------------------
    srow("error comes before integrated_mode", [site(TEST_SITE, broken=True, bv_row=True)], {TEST_SITE: "error"}),
    srow("integrated_mode comes before low coverage", [site(TEST_SITE, bv_row=True, coverage=(100, 10))],
         {TEST_SITE: "integrated_mode"}, req024=True),
    srow("low coverage comes before too few patients and episodes",
         [site(TEST_SITE, patients=5, groups=(Group(n=5),), coverage=(10, 5))], {TEST_SITE: "low_coverage"}),
    srow("too few patients comes before too few episodes", [site(TEST_SITE, patients=5, groups=(Group(n=5),))],
         {TEST_SITE: "insufficient_patients"}),
    # ---- order 6: the study minimum --------------------------------------------------------------------------------------------
    srow("study with 9 computed sites: study_below_min_sites; failing sites keep their reason",
         [site(TEST_SITE, coverage=(100, 59))], {TEST_SITE: "low_coverage"}, n_fillers=MIN_SITES - 1,
         filler_reason="study_below_min_sites", study="study_below_min_sites"),
    srow("study with 10 computed sites: computed", [site(TEST_SITE, coverage=(100, 59))],
         {TEST_SITE: "low_coverage"}, n_fillers=MIN_SITES),
    # ---- §6.4 status precedence and §8.1 rates ------------------------------------------------------------------------------------
    srow("an unmatched episode at a low_coverage site stays unmatched and feeds the other sites' rates",
         [site(TEST_SITE, groups=(Group(unmatched=always),), coverage=(100, 59))], {TEST_SITE: "low_coverage"},
         check=check_low_coverage_keeps_status),
    srow("status precedence at an integrated_mode site: paged > pending > not_evaluated",
         [site(TEST_SITE, bv_row=True, groups=PRECEDENCE_GROUPS)], {TEST_SITE: "integrated_mode"},
         check=check_precedence(True), req024=True),
    srow("status precedence at a computed site: paged > pending > matched/unmatched",
         [site(TEST_SITE, groups=PRECEDENCE_GROUPS)], {TEST_SITE: None}, check=check_precedence(False), req024=True),
]


@pytest.mark.req("REQ-025")
@pytest.mark.parametrize(("fillers", "sites", "reasons", "filler_reason", "study", "check"), SITE_ROWS)
def test_site_rows(fillers: list, sites: list, reasons: dict, filler_reason: str | None, study: str | None,
                   check: Callable[[match.StudyMatch], None] | None) -> None:
    res = match.analyze_sites([*fillers, *sites], CFG, data_cut=CUT)
    want = {f.site_id: filler_reason for f in fillers} | reasons
    assert {s.site_id: s.not_computed_reason for s in res.sites} == want
    assert res.study_not_computed_reason == study
    assert res.n_computed_sites == sum(r is None for r in want.values())
    assert res.n_computed_sites == 0 or res.n_computed_sites >= MIN_SITES
    for s in res.sites:  # never green: a reason always means tier not_computed and no statistic (REQ-025)
        row = s.row()
        assert row["not_computed_reason"] == s.not_computed_reason and row["data_origin"] == DATA_ORIGIN
        if s.computed:
            assert row["tier"] is None and None not in (row["O"], row["E"], row["V"]) and row["V"] > 0
        else:
            assert row["tier"] == "not_computed" and (row["O"], row["E"], row["V"]) == (None, None, None)
        if s.not_computed_reason in match.EXCLUDED_FROM_RATES:
            assert not any(ep["status"] in episodes.OE_STATUSES for ep in s.episodes)
    if check is not None:
        check(res)


# ---- analysis settings (docs/11 §12.6) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("sid", "window", "next_visit", "proximal"), [
    ("SE1", (3, 0), 8, False),
    ("SE2", (14, 7), 8, False),
    ("SE14", (7, 2), 8, True),
    ("SE20", (7, 2), 19, False),
    ("SE21", (7, 2), 8, False),  # overdispersion is indicators.py's; nothing changes here
])
def test_analysis_settings_follow_params_and_signal_rules(sid: str, window: tuple, next_visit: int,
                                                          proximal: bool) -> None:
    rules, page_proximal = match.analysis_config(CFG, SE[sid])
    assert (rules["match"]["window_days"], rules["match"]["lower_tolerance_days"]) == window
    assert rules["evaluability"]["next_visit_plus_days"] == next_visit and page_proximal is proximal
    assert CFG["match"]["window_days"] == 7 and CFG["evaluability"]["next_visit_plus_days"] == 8  # not mutated


@pytest.mark.parametrize("analysis", [
    {"match_window_days": 5, "lower_tolerance_days": 1},  # not an entry of match.sensitivity
    {"match_window_days": 3},  # half a window
    {"paged_rule": "any_call"},
    {"something_else": 1},
])
def test_unknown_analysis_settings_are_refused(analysis: dict) -> None:
    with pytest.raises(ValueError):
        match.analysis_config(CFG, analysis)


def test_study_level_failures_raise_instead_of_marking_one_site() -> None:
    """A bad rule file, data cut or duplicate site id fails the whole study (the backend's 503), never one site."""
    with pytest.raises(TypeError):
        match.analyze_sites(FILLERS, CFG, data_cut=datetime(2026, 5, 1, tzinfo=UTC))
    bad = {**CFG, "match": {**CFG["match"], "one_to_one": False}}
    with pytest.raises(ValueError):
        match.analyze_sites(FILLERS, bad, data_cut=CUT)
    with pytest.raises(ValueError):
        match.analyze_sites([*FILLERS, FILLERS[0]], CFG, data_cut=CUT)


# ---- the simulated study (dev seed) -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def simulated() -> tuple[sim.Study, match.StudyMatch]:
    p = PARAMS
    key = bvseed.key(int(p["streams"]["committed_study"]), int(p["cell_index"]["none"]),
                     int(p["roles"]["null_or_committed"]), 0, seed=int(p["seeds"]["dev"]))
    st = sim.simulate(key, sim.default_model())
    return st, match.match_study(st)


@pytest.mark.req("REQ-024")
@pytest.mark.req("REQ-025")
def test_simulated_study_uses_episodes_py_and_grey_sites_are_not_computed(
        simulated: tuple[sim.Study, match.StudyMatch]) -> None:
    st, res = simulated
    label = {a["site_id"]: a["label"] for a in st.answer_key()}
    reason = {s.site_id: s.not_computed_reason for s in res.sites}
    # the two must-be-grey sites of docs/11 §11.4
    assert [reason[s] for s in label if label[s] == "low_coverage"] == ["low_coverage"]
    assert [reason[s] for s in label if label[s] == "small_site"] == ["insufficient_patients"]
    assert not {"error", "integrated_mode"} & set(reason.values())  # no between_visits rows in a simulation
    assert (res.study_not_computed_reason is None) == (res.n_passing_sites >= MIN_SITES)
    inputs = {d.site_id: d for d in match.site_inputs(st)}
    rows_by_id = {r["site_ae_id"]: r for r in st.site_ae_rows()}
    synonyms = {t: {w.strip().lower() for w in ws} for t, ws in CFG["match"]["term_synonyms"].items()}
    completion = {r["site_id"]: r["call_completion"] for r in st.site_records()}
    for s in res.sites:
        d = inputs[s.site_id]
        assert s.n_patients == len(d.subject_ids) and s.call_completion == completion[s.site_id]
        # the shared implementation, not a re-implementation: identical episodes, matches and statuses
        shared = episodes.analyze(d.calls, d.site_aes, CFG, data_cut=st.data_cut, dose_dates=d.dose_dates)
        assert len(shared) == len(s.episodes)
        for n, (mine, ref) in enumerate(zip(s.episodes, shared, strict=True), start=1):
            assert mine["episode_id"] == f"ep_{s.site_id}_{n}" and mine["data_origin"] == DATA_ORIGIN
            assert {k: mine[k] for k in ref if k != "status"} == {k: v for k, v in ref.items() if k != "status"}
            want = ref["status"] if mine["status"] != "not_evaluated" else mine["status"]
            assert mine["status"] == want
            if mine["status"] == "not_evaluated":
                assert ref["status"] in episodes.OE_STATUSES
            if mine["matched_site_ae_id"] is not None:
                row = rows_by_id[mine["matched_site_ae_id"]]
                assert row["subject_id"] == mine["subject_id"] and row["origin"] == "site"
                assert row["entered_on"] <= st.data_cut and row["aeterm"].strip().lower() in synonyms[mine["term"]]
        assert s.paged_stratum == episodes.paged_stratum(shared) and s.paged_stratum["n"] == s.n_paged
        # O and E are sums over the episodes with a leave-one-site-out rate
        oe = [(ep, p) for ep, p in zip(s.episodes, s.p_hat, strict=True) if p is not None]
        assert all(ep["status"] in episodes.OE_STATUSES for ep, _ in oe)
        assert s.O == sum(ep["status"] == "matched" for ep, _ in oe)
        assert s.E == pytest.approx(sum(p for _, p in oe), rel=1e-12)
    assert sum(len(s.episodes) for s in res.sites) > 500


def test_leave_one_site_out_rates_on_the_simulated_study(simulated: tuple[sim.Study, match.StudyMatch]) -> None:
    """§8.1 by direct count: each rate is the other included sites' matched share in the cell (else the term)."""
    _, res = simulated
    count: dict[tuple[str, str, int], list[int]] = {}
    for s in res.sites:
        for ep in s.episodes:
            if ep["status"] in episodes.ANALYSIS_SET_STATUSES:
                c = count.setdefault((s.site_id, ep["term"], ep["grade"]), [0, 0])
                c[0] += ep["matched_site_ae_id"] is not None
                c[1] += 1

    def other(site_id: str, term: str, grade: int | None) -> tuple[int, int]:
        keys = [k for k in count if k[0] != site_id and k[1] == term and (grade is None or k[2] == grade)]
        return sum(count[k][0] for k in keys), sum(count[k][1] for k in keys)

    checked = 0
    for s in res.sites:
        for ep, p in zip(s.episodes, s.p_hat, strict=True):
            if ep["status"] not in episodes.OE_STATUSES:
                continue
            o, n = other(s.site_id, ep["term"], ep["grade"])
            if n == 0:
                o, n = other(s.site_id, ep["term"], None)
            assert p == o / n
            checked += 1
    assert checked > 100


def test_match_study_is_deterministic(simulated: tuple[sim.Study, match.StudyMatch]) -> None:
    st, res = simulated
    again = match.match_study(st)
    assert again.rows() == res.rows() and again.episodes() == res.episodes()
    assert [s.p_hat for s in again.sites] == [s.p_hat for s in res.sites]


def test_match_study_applies_the_scenario_window() -> None:
    """SE1 narrows the window on the identical study: matched episodes can only drop (§12.6 (iv))."""
    p = PARAMS
    key = bvseed.key(int(p["streams"]["committed_study"]), int(p["cell_index"]["none"]),
                     int(p["roles"]["null_or_committed"]), 1, seed=int(p["seeds"]["dev"]))
    base = match.match_study(sim.simulate(key, sim.default_model()))
    narrow = match.match_study(sim.simulate(key, sim.default_model(), scenario=sim.scenario_from_params(p, "SE1")))
    pairs = list(zip(base.episodes(), narrow.episodes(), strict=True))
    assert all(a["episode_id"] == b["episode_id"] for a, b in pairs)
    gained = sum(a["matched_site_ae_id"] is None and b["matched_site_ae_id"] is not None for a, b in pairs)
    lost = sum(a["matched_site_ae_id"] is not None and b["matched_site_ae_id"] is None for a, b in pairs)
    assert lost > gained >= 0


# ---- code rules -----------------------------------------------------------------------------------------------------------


MATCH_PY = MONITORING_DIR / "bvsignal" / "match.py"


def numeric_literals(source: str) -> list[tuple[int, object]]:
    """Every numeric literal other than 0 and 1 (-1 parses as minus 1)."""
    tree = ast.parse(source)
    return sorted((n.lineno, n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, int | float | complex)
                  and not isinstance(n.value, bool) and n.value not in (0, 1))


@pytest.mark.req("REQ-023")
def test_match_has_no_numeric_literal_other_than_0_1_and_minus_1() -> None:
    assert numeric_literals("x = [0, 1, -1, 0.0, True]\n") == []
    assert numeric_literals("x = 15\ny = 0.6\n") == [(1, 15), (2, 0.6)]
    bad = numeric_literals(MATCH_PY.read_text(encoding="utf-8"))
    assert bad == [], f"numeric literals in match.py (read them from data/signal_rules.json): {bad}"


def test_match_calls_episodes_py_and_reimplements_none_of_it() -> None:
    """Episodes, matching, evaluability, the paged stratum and status precedence come only from episodes.py."""
    tree = ast.parse(MATCH_PY.read_text(encoding="utf-8"))
    imported = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert ("bvsignal._backend", "episodes") in imported
    assert not any(module in ("bisect", "app.services.rules") for module, _ in imported)
    used = {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "episodes"}
    assert {"analyze", "status_of", "paged_stratum", "with_match_sensitivity"} <= used
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}  # module-level functions
    assert not defined & {"build_episodes", "match", "is_evaluable", "status_of", "classify", "analyze",
                          "paged_stratum", "_match", "_evaluable", "_term_episodes"}
    source = MATCH_PY.read_text(encoding="utf-8")
    for llm in ("anthropic", "google.genai", "app.services.llm", "gemini", "elevenlabs"):
        assert llm not in source
