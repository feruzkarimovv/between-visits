"""monitoring/planning/plan_power.py: the pre-tag planning grid (docs/11 §11.5). Planning only, not a result."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys

import numpy as np
import pytest

from bvsignal import MONITORING_DIR, REPO_ROOT
from bvsignal import seed as bvseed

_spec = importlib.util.spec_from_file_location("plan_power", MONITORING_DIR / "planning" / "plan_power.py")
assert _spec and _spec.loader
pp = importlib.util.module_from_spec(_spec)
sys.modules["plan_power"] = pp
_spec.loader.exec_module(pp)

PARAMS = bvseed.load_params()
SIGNAL_RULES = json.loads((REPO_ROOT / "data" / "signal_rules.json").read_text())
SHARES = pp.paged_shares(PARAMS, SIGNAL_RULES)
MODEL = pp.build_model(PARAMS, SIGNAL_RULES, SHARES)


def test_paged_shares_come_from_the_rules_engine() -> None:
    sec = PARAMS["answer_generation"]["secondary"]
    blood, dizzy = sec["diarrhea_episode"]["STOOL_BLOOD"]["yes"], sec["diarrhea_episode"]["dizzy_on_standing"]
    cells = SHARES["cells"]
    # Diarrhea G2 pages on blood in stool (RF_DIARRHEA_SEVERE) or dizziness on standing (RF_DEHYDRATION)
    assert cells["Diarrhea"]["2"]["paged_share"] == pytest.approx(blood + (1 - blood) * dizzy, abs=1e-12)
    # Dyspnea G2 pages when severity is severe or very severe (RF_BREATHING)
    g2 = sec["dyspnea_g2"]["SOB_SEV"]
    assert cells["Dyspnea"]["2"]["paged_share"] == pytest.approx(g2["severe"] + g2["very_severe"], abs=1e-12)
    # docs/11 §4.4: every Fever episode and every grade 3 episode is paged
    for term, g in [("Fever", "2"), ("Fever", "3"), ("Diarrhea", "3"), ("Dyspnea", "3")]:
        assert cells[term][g]["paged_share"] == 1.0
    assert all(c["candidates"] > 0 for t in cells.values() for c in t.values())


OFFSETS = [1, 3, 7, 22, 24, 28, 43, 45, 49]


@pytest.mark.parametrize(
    ("obs", "expected"),
    [
        ([2, 2, 0], [(1, -20, 2, False)]),                               # new; no earlier call -> L = D - 21
        ([2, 3, 2, 0], [(1, -20, 2, False), (3, 1, 3, True)]),           # worsen; L = last call below 3; fall 3->2 continues
        ([0, 2, -1, 2, 0], [(3, 1, 2, False)]),                          # a missed call is skipped
        ([2, -1, -1, -1, -1, -1, 2], [(1, -20, 2, False), (43, 22, 2, False)]),  # gap of 42 days > 21 closes
        ([2, -1, -1, 2], [(1, -20, 2, False)]),                          # gap of exactly 21 days continues
        ([0, -1, -1, -1, -1, -1, 2], [(43, 22, 2, False)]),              # last negative call 42 days earlier -> D - 21
        ([3, 2, 2, 0], [(1, -20, 3, False)]),                            # band stays 3
        ([2, 0, 3, 0], [(1, -20, 2, False), (7, 3, 3, False)]),          # a closed episode reopens as new, not worsened
        ([1, 2, 1, 2], [(3, 1, 2, False), (22, 7, 2, False)]),           # grade 1 closes; L = last call below 2
        ([-1, -1, -1], []),
    ],
)
def test_episode_construction(obs: list[int], expected: list[tuple[int, int, int, bool]]) -> None:
    o = np.array([obs + [-1] * (len(OFFSETS) - len(obs))])
    day = np.array([OFFSETS])
    eps = pp.build_episodes(o, day, min_grade=2, bands=(2, 3), gap_days=21)
    got = list(zip(eps.date.tolist(), eps.lower.tolist(), eps.band.tolist(), eps.worsened.tolist(), strict=True))
    assert got == expected
    for j, g in enumerate(o[0]):
        assert (eps.at_call[0, j] >= 0) == (g >= 2)


def _greedy_reference(pair_ep, pair_row, dist, date, aeseq, n_ep):
    matched, used = np.zeros(n_ep, bool), set()
    for k in np.lexsort((aeseq, date, dist)):
        if not matched[pair_ep[k]] and pair_row[k] not in used:
            matched[pair_ep[k]] = True
            used.add(int(pair_row[k]))
    return matched


def test_vectorized_greedy_equals_sequential_greedy() -> None:
    rng = np.random.default_rng(20261011)
    for _ in range(300):
        n_ep, n_row = rng.integers(1, 8), rng.integers(1, 8)
        n_pairs = rng.integers(0, n_ep * n_row + 1)
        pairs = rng.permutation(n_ep * n_row)[:n_pairs]
        pe, pr = pairs // n_row, pairs % n_row
        ep_date = rng.permutation(100)[:n_ep]
        aeseq = rng.permutation(100)[:n_row]
        dist = rng.integers(0, 4, size=n_pairs)
        got = pp.greedy_match(pe, pr, dist, ep_date[pe], aeseq[pr], n_ep)
        assert np.array_equal(got, _greedy_reference(pe, pr, dist, ep_date[pe], aeseq[pr], n_ep))


def test_episodes_and_match_agree_with_the_shared_b16_implementation() -> None:
    """The planning grid's vectorized §4.2 builder and §5 matcher give what backend/app/services/episodes.py
    (B16, the one implementation that S2 onwards must call) gives on the same random calls and AE rows."""
    b16 = pytest.importorskip("app.services.episodes")  # backend/ is on sys.path through bvsignal._backend
    rng = np.random.default_rng(20261011)
    terms, offsets, cut = MODEL.terms, MODEL.call_offsets, MODEL.data_cut
    n_subj, J, T = 80, MODEL.call_offsets.size, len(MODEL.terms)
    enroll = rng.integers(0, 85, size=n_subj)
    completed = rng.random((n_subj, J)) < 0.8
    grades = rng.choice([-1, 0, 1, 2, 3], size=(n_subj, T, J), p=[0.15, 0.35, 0.1, 0.28, 0.12])
    obs = np.where(completed[:, None, :], grades, -1)
    day = enroll[:, None] + offsets[None, :]
    calls = [{"call_id": f"c{p}_{j}", "subject_id": f"s{p}", "date": int(day[p, j]),
              "status": "completed" if completed[p, j] else "no_answer",
              "grades": {t: (None if grades[p, k, j] < 0 else int(grades[p, k, j])) for k, t in enumerate(terms)}}
             for p in range(n_subj) for j in range(J) if day[p, j] <= cut]
    ref = b16.build_episodes(calls, SIGNAL_RULES)
    valid = offsets[None, :] <= (cut - enroll)[:, None]
    mine = pp.build_episodes(np.where(valid[:, None, :], obs, -1).reshape(n_subj * T, J), np.repeat(day, T, axis=0),
                             min_grade=MODEL.min_grade, bands=MODEL.bands, gap_days=MODEL.gap_days)
    as_tuples = sorted((f"s{s // T}", terms[s % T], int(d), int(lo), int(b), "worsened" if w else "new")
                       for s, d, lo, b, w in zip(mine.series, mine.date, mine.lower, mine.band, mine.worsened, strict=True))
    assert as_tuples == sorted((e["subject_id"], e["term"], e["episode_date"], e["anchor_date"], e["grade"], e["kind"]) for e in ref)
    assert len(ref) > 100
    # §5 match on random site rows (some entered after the data cut)
    rows = []
    for p in range(n_subj):
        for k, t in enumerate(terms):
            for _ in range(rng.integers(0, 4)):
                rows.append({"subject_id": f"s{p}", "series": p * T + k, "aeterm": t.lower(), "origin": "site",
                             "aestdtc": int(enroll[p] + rng.integers(-10, 260)), "entered_on": int(rng.integers(0, 300))})
    for p in range(n_subj):  # aeseq: per subject, in AESTDTC order
        own = sorted((r for r in rows if r["subject_id"] == f"s{p}"), key=lambda r: r["aestdtc"])
        for n, r in enumerate(own, start=1):
            r["aeseq"] = n
    ref_match = b16.match(ref, rows, SIGNAL_RULES, data_cut=cut)
    ref_pairs = sorted((e["subject_id"], e["term"], e["episode_date"], rows[j]["aestdtc"])
                       for e, j in zip(ref, ref_match, strict=True) if j is not None)
    in_log = [r for r in rows if r["entered_on"] <= cut]
    order = sorted(range(len(in_log)), key=lambda i: (in_log[i]["subject_id"], in_log[i]["aeseq"]))
    rank = np.empty(len(in_log), np.int64)
    rank[order] = np.arange(len(in_log))
    matched = pp.match_episodes(mine, np.array([r["series"] for r in in_log]), np.array([r["aestdtc"] for r in in_log]), rank,
                                lower_tol=MODEL.lower_tol, window_days=MODEL.window_days)
    assert matched.sum() == len(ref_pairs) > 50
    mine_matched = sorted((f"s{s // T}", terms[s % T], int(d)) for s, d, mm in zip(mine.series, mine.date, matched, strict=True) if mm)
    assert mine_matched == sorted(x[:3] for x in ref_pairs)


def test_discreteness_rule() -> None:
    vals = np.arange(1, 101, dtype=float)
    assert pp.calibrated_threshold(vals, 0.05) == 5.0
    assert pp.calibrated_threshold(vals, 0.10) == 10.0
    assert pp.calibrated_threshold(np.array([1.0, 1.0, 1.0, 2.0]), 0.5) == float("-inf")  # ties never push above alpha
    assert pp.calibrated_threshold(np.array([1.0, 2.0, 2.0, 3.0]), 0.5) == 1.0
    assert pp.calibrated_threshold(np.array([1.0, np.inf, np.inf, np.inf]), 0.25) == 1.0


def test_full_mix_roles_and_live_site() -> None:
    st = pp.simulate(bvseed.rng(3, 51, 1, 0, seed=bvseed.dev_seed()), MODEL, patients=(30, 60), mu=1.5, composition="full_mix")
    planted = {k: int(v["count"]) for k, v in PARAMS["planted"].items() if v["count"] != "rest"}
    assert {r: st.role.count(r) for r in planted} == planted
    assert st.role[MODEL.live_index] == "honest"
    assert st.n_pat[st.role.index("small_site")] == PARAMS["planted"]["small_site"]["patients"]


def test_batches_do_not_change_results() -> None:
    gens = [bvseed.rng(3, 55, 0, i, seed=bvseed.dev_seed()) for i in range(3)]
    studies = [pp.simulate(g, MODEL, patients=(30, 60), mu=1.5, composition="null") for g in gens]
    together = pp.analyze(pp.prepare(studies, MODEL), MODEL)
    for b, st in enumerate(studies):
        alone = pp.analyze(pp.prepare([st], MODEL), MODEL)
        assert np.array_equal(alone.computed[0], together.computed[b])
        assert np.allclose(alone.z_adj[0], together.z_adj[b], equal_nan=True, rtol=0, atol=1e-12)


def test_small_run_is_deterministic_and_labeled() -> None:
    a = pp.run_planning(REPO_ROOT, p1_studies=4, p2_null=12, p2_per_f=4)
    b = pp.run_planning(REPO_ROOT, p1_studies=4, p2_null=12, p2_per_f=4)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["_about"] == "planning only, not a result" and a["data_origin"] == "SIMULATED"
    assert set(a["chosen"]) == {"patients_per_site", "gross_f", "p1", "p2"}
    assert a["chosen"]["gross_f"] in PARAMS["planning"]["p2"]["f"]
    assert a["chosen"]["patients_per_site"] in PARAMS["planning"]["p1"]["ranges"]
    assert {a["chosen"]["p1"], a["chosen"]["p2"]} <= {"passed", "shortfall"}
    assert a["fever_and_grade3_always_paged"] is True


def test_planning_refuses_the_evaluation_seed() -> None:
    with pytest.raises(SystemExit):
        pp.run_planning(REPO_ROOT, "eval")


def test_committed_planning_grid_matches_params_and_script() -> None:
    path = MONITORING_DIR / "planning" / "planning_grid.json"
    grid = json.loads(path.read_text())
    assert grid["_about"] == "planning only, not a result"
    assert grid["seed"]["value"] == PARAMS["seeds"]["dev"]
    assert grid["provenance"]["plan_power_sha256"] == hashlib.sha256((MONITORING_DIR / "planning" / "plan_power.py").read_bytes()).hexdigest()
    assert grid["chosen"]["patients_per_site"] == PARAMS["design"]["patients_per_site"]
    assert grid["chosen"]["gross_f"] == PARAMS["planted"]["gross"]["f"]
    p1, p2 = PARAMS["planning"]["p1"], PARAMS["planning"]["p2"]
    assert [r["studies"] for r in grid["p1"]["ranges"]] == [p1["studies_per_range"]] * len(p1["ranges"])
    assert grid["p2"]["null"]["studies"] == p2["null_studies"]
    assert [r["studies"] for r in grid["p2"]["power"]["rows"]] == [p2["studies_per_f"]] * len(p2["f"])
    # the rules applied exactly as written
    first = next((r for r in grid["p1"]["ranges"] if r["passed"]), None)
    assert grid["chosen"]["patients_per_site"] == (first["patients_per_site"] if first else p1["fallback"])
    smallest = next((r for r in grid["p2"]["power"]["rows"] if r["qualifies"]), None)
    assert grid["chosen"]["gross_f"] == (smallest["f"] if smallest else p2["fallback_f"])
    for r in grid["p2"]["power"]["rows"]:
        p = r["watch_power"]
        lb = p - p2["lower_bound_z"] * np.sqrt(p * (1 - p) / p2["studies_per_f"])
        assert r["watch_lower_bound_80"] == pytest.approx(lb, abs=1e-6)
        assert r["qualifies"] == (lb >= p2["min_lower_bound"])


def test_planning_grid_path_is_not_an_evaluation_output() -> None:
    rel = (MONITORING_DIR / "planning" / "planning_grid.json").relative_to(REPO_ROOT).as_posix()
    assert not rel.startswith(("monitoring/out/", "validation/site_signal/"))
    # monitoring/out/ holds the logged evaluation-seed outputs since the sap-v1 tag; the planning grid is
    # never one of them (docs/11 §11.5: planning only, not a result).
    assert not (REPO_ROOT / "monitoring" / "out" / "planning_grid.json").exists()
