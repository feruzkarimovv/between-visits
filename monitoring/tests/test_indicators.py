"""S4: monitoring/bvsignal/indicators.py (docs/11 §8, §9.3, §10; REQ-023, REQ-028). SIMULATED, dev seed.

The centerpiece is a hand-computed 3-site example (sites A, B, C) that runs through ``match.analyze_sites``
(episodes, matching, evaluability and the §8.1 sums) and ``indicators.discordance`` (§8.2), with the minimum
data lowered to 3 sites, 2 patients and 3 evaluable episodes so that three tiny sites are computed. Every
expected value below is written out from the SAP formulas with exact fractions, never by calling the code
under test, and must agree to 1e-9.

Episodes of the example (each is a grade call followed two days later by a grade 0 call; "M" = a site row
dated on the episode date, so matched; doses every 21 days from day 0; data cut day 120):

    A1  Diarrhea G2 day 1 M, day 22 M, day 43 M
    A2  Diarrhea G2 day 1 M, day 22 unmatched; Dyspnea G2 day 1 M
    A3  Dyspnea G2 day 22 M, day 43 M; Diarrhea G2 day 64 M; Diarrhea G2 day 1 on an urgent call (paged: out)
    B1  Diarrhea G2 day 1, day 22 (unmatched), day 43 M
    B2  Diarrhea G2 day 1 unmatched; Dyspnea G2 day 22 and day 43 unmatched
    B3  Dyspnea G2 day 1 M; Diarrhea G2 day 22 unmatched; Diarrhea G2 day 107 M (pending at the cut: out)
    C1  Diarrhea G3 day 1 M (no Diarrhea G3 at A or B: the term's rate pooled over bands); Diarrhea G2 day 22
        unmatched; Dyspnea G2 day 43 M
    C2  Diarrhea G2 day 1 M, day 22 unmatched; Dyspnea G2 day 1 unmatched

C's cluster term is below its binomial variance, so V_C is the floor; A and B use the cluster-robust term.
"""

from __future__ import annotations

import ast
import math
from collections import Counter
from fractions import Fraction
from typing import Any

import numpy as np
import pytest

from bvsignal import DATA_ORIGIN, MONITORING_DIR, match
from bvsignal import indicators as ind
from bvsignal import seed as bvseed
from bvsignal import simulate as sim
from bvsignal._backend import episodes

CFG = match.load_signal_rules()
PARAMS = bvseed.load_params()
DEV = int(PARAMS["seeds"]["dev"])
TOL = 1e-9
WINSOR = (0.10, 0.90)  # signal_rules.json overdispersion.winsor (pinned below)
CFG3 = {**CFG, "minimum_data": {**CFG["minimum_data"], "min_sites": 3, "min_patients": 2, "min_evaluable_episodes": 3}}
CUT = 120
Q21 = tuple(range(0, 253, 21))

# (subject, term, grade, day, matched, level)
EXAMPLE: dict[str, list[tuple[str, str, int, int, int, str]]] = {
    "A": [("A1", "Diarrhea", 2, 1, 1, "none"), ("A1", "Diarrhea", 2, 22, 1, "none"), ("A1", "Diarrhea", 2, 43, 1, "none"),
          ("A2", "Diarrhea", 2, 1, 1, "none"), ("A2", "Diarrhea", 2, 22, 0, "none"), ("A2", "Dyspnea", 2, 1, 1, "none"),
          ("A3", "Dyspnea", 2, 22, 1, "none"), ("A3", "Dyspnea", 2, 43, 1, "none"), ("A3", "Diarrhea", 2, 64, 1, "none"),
          ("A3", "Diarrhea", 2, 1, 0, "urgent")],
    "B": [("B1", "Diarrhea", 2, 1, 0, "none"), ("B1", "Diarrhea", 2, 22, 0, "none"), ("B1", "Diarrhea", 2, 43, 1, "none"),
          ("B2", "Diarrhea", 2, 1, 0, "none"), ("B2", "Dyspnea", 2, 22, 0, "none"), ("B2", "Dyspnea", 2, 43, 0, "none"),
          ("B3", "Dyspnea", 2, 1, 1, "none"), ("B3", "Diarrhea", 2, 22, 0, "none"), ("B3", "Diarrhea", 2, 107, 1, "none")],
    "C": [("C1", "Diarrhea", 3, 1, 1, "none"), ("C1", "Diarrhea", 2, 22, 0, "none"), ("C1", "Dyspnea", 2, 43, 1, "none"),
          ("C2", "Diarrhea", 2, 1, 1, "none"), ("C2", "Diarrhea", 2, 22, 0, "none"), ("C2", "Dyspnea", 2, 1, 0, "none")],
}


def site_data(site_id: str, eps: list[tuple[str, str, int, int, int, str]]) -> match.SiteData:
    calls: list[dict[str, Any]] = []
    aes: list[dict[str, Any]] = []
    seq: Counter[str] = Counter()
    for subject, term, grade, day, matched, level in eps:
        calls.append({"call_id": f"c{site_id}{len(calls)}", "subject_id": subject, "date": day, "status": "completed",
                      "level": level, "grades": {term: grade}})
        calls.append({"call_id": f"c{site_id}{len(calls)}", "subject_id": subject, "date": day + 2,
                      "status": "completed", "level": "none", "grades": {term: 0}})
        if matched:
            seq[subject] += 1
            aes.append({"site_ae_id": f"ae_{site_id}_{len(aes) + 1}", "subject_id": subject, "usubjid": subject,
                        "aeseq": seq[subject], "aeterm": term.lower(), "aetoxgr": str(grade), "aestdtc": day,
                        "entered_on": day + 8, "origin": "site", "symptomatic": True, "data_origin": DATA_ORIGIN})
    calls.sort(key=lambda c: (c["subject_id"], c["date"]))
    subjects = tuple(sorted({e[0] for e in eps}))
    return match.SiteData(site_id=site_id, subject_ids=subjects, calls=calls, site_aes=aes,
                          dose_dates={s: Q21 for s in subjects}, scheduled_calls=len(calls),
                          completed_calls=len(calls))


@pytest.fixture(scope="module")
def example() -> match.StudyMatch:
    return match.analyze_sites([site_data(k, v) for k, v in EXAMPLE.items()], CFG3, data_cut=CUT)


# ---- the hand computation (exact fractions; floats only for square roots) ---------------------------------------

F = Fraction
# §8.1 leave-one-site-out rates by direct count of evaluable, non-paged episodes (matched / total):
#   Diarrhea G2: A 5/6, B 1/5, C 1/3     Diarrhea G3: C 1/1     Dyspnea G2: A 3/3, B 1/3, C 1/2
P_HAT = {
    ("A", "Diarrhea", 2): F(1 + 1, 5 + 3), ("A", "Dyspnea", 2): F(1 + 1, 3 + 2),
    ("B", "Diarrhea", 2): F(5 + 1, 6 + 3), ("B", "Dyspnea", 2): F(3 + 1, 3 + 2),
    ("C", "Diarrhea", 2): F(5 + 1, 6 + 5), ("C", "Dyspnea", 2): F(3 + 1, 3 + 3),
    # A and B have no Diarrhea G3 episode: Diarrhea pooled over bands at A and B, (5 + 1) / (6 + 5)
    ("C", "Diarrhea", 3): F(5 + 1, 6 + 5),
}


def hand_oev(site_id: str) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    """O, E, V = max(cluster, binomial), and both terms, from the episode list (paged and pending left out)."""
    observed = expected = binomial = F(0)
    residual: dict[str, Fraction] = {}
    for subject, term, grade, day, matched, level in EXAMPLE[site_id]:
        if level == "urgent" or day + 14 > CUT:  # paged stratum (§6.2) / pending (§6.1)
            continue
        p = P_HAT[(site_id, term, grade)]
        observed += matched
        expected += p
        binomial += p * (1 - p)
        residual[subject] = residual.get(subject, F(0)) + (matched - p)
    n = len(residual)
    cluster = F(n, n - 1) * sum(r * r for r in residual.values())
    return observed, expected, max(cluster, binomial), cluster, binomial


def hand_winsorized_phi(z: list[float], lo: float, hi: float) -> float:
    """numpy.quantile method="linear" by hand: position h = (n - 1) q, x[floor h] + (h - floor h) x gap."""
    s = sorted(z)

    def q(p: float) -> float:
        h = (len(s) - 1) * p
        j = math.floor(h)
        return s[j] + (h - j) * (s[min(j + 1, len(s) - 1)] - s[j])

    ql, qh = q(lo), q(hi)
    return sum(min(max(v, ql), qh) ** 2 for v in z) / len(z)


def test_signal_rules_values_used_here() -> None:
    """The constants this module reads (docs/11 §8.2, §8.3, §9.2) as the tests restate them."""
    assert CFG["overdispersion"] == {"method": "additive", "winsor": [0.10, 0.90]}
    assert tuple(CFG["overdispersion"]["winsor"]) == WINSOR
    assert CFG["tiers"] == {"look": {"per_site_alpha": 0.05}, "watch": {"family_wise_alpha": 0.10}}
    assert PARAMS["comparators"]["rate_kri"] == {"exposure": "patient_days", "min_days": 30,
                                                 "overdispersion": "multiplicative"}
    assert ind.FLAG_WHEN == {"discordance": "<=", "rate_kri": "<=", "simaerep_classic": ">=", "ae_report_ratio": "<="}
    assert ind.TIER_VALUES == ("watch", "look", "none", "not_computed")
    assert set(ind.INDICATORS) == set(PARAMS["comparators"]) | {"discordance"}


@pytest.mark.req("REQ-023")
def test_hand_computed_three_site_example(example: match.StudyMatch) -> None:
    """O, E, V, z and phi (and tau^2 and z*) of §8.1-§8.2 reproduce the hand computation to 1e-9."""
    assert [s.site_id for s in example.sites] == ["A", "B", "C"]
    assert all(s.computed for s in example.sites), [s.not_computed_reason for s in example.sites]
    # §8.1 rates per episode: every episode with a rate is evaluable, not paged, and has the hand rate
    statuses = Counter(ep["status"] for s in example.sites for ep in s.episodes)
    assert statuses == {"matched": 13, "unmatched": 10, "paged": 1, "pending": 1}
    for s in example.sites:
        for ep, p in zip(s.episodes, s.p_hat, strict=True):
            if ep["status"] in episodes.OE_STATUSES:
                assert abs(p - float(P_HAT[(s.site_id, ep["term"], ep["grade"])])) < TOL, (s.site_id, ep)
            else:
                assert p is None
    hand = {k: hand_oev(k) for k in EXAMPLE}
    # which variance term binds: the cluster term at A and B, the binomial floor at C
    assert hand["A"][3] > hand["A"][4] and hand["B"][3] > hand["B"][4] and hand["C"][3] < hand["C"][4]
    assert (hand["A"][0], hand["B"][0], hand["C"][0]) == (8, 2, 3)

    d = ind.discordance(example, CFG3)
    O = [float(hand[k][0]) for k in EXAMPLE]  # noqa: E741
    E = [float(hand[k][1]) for k in EXAMPLE]
    V = [float(hand[k][2]) for k in EXAMPLE]
    z = [(o - e) / math.sqrt(v) for o, e, v in zip(O, E, V, strict=True)]
    phi = hand_winsorized_phi(z, *WINSOR)
    K = len(z)
    w = [e * e / v for e, v in zip(E, V, strict=True)]
    tau2 = max(0.0, (K * phi - (K - 1)) / (sum(w) - sum(x * x for x in w) / sum(w)))
    z_adj = [(o - e) / math.sqrt(v + tau2 * e * e) for o, e, v in zip(O, E, V, strict=True)]
    assert tau2 > 0  # K phi > K - 1 in this example, so the additive adjustment is exercised
    for k in range(K):
        assert abs(d.columns["O"][k] - O[k]) < TOL
        assert abs(d.columns["E"][k] - E[k]) < TOL
        assert abs(d.columns["V"][k] - V[k]) < TOL
        assert abs(d.columns["z_raw"][k] - z[k]) < TOL
        assert abs(d.statistic[k] - z_adj[k]) < TOL
        assert abs(d.columns["oe_ratio"][k] - O[k] / E[k]) < TOL
    assert abs(d.phi - phi) < TOL
    assert abs(d.tau2 - tau2) < TOL
    # the same numbers through match.py's own §8.1 sums
    for s, (o, e, v, _, _) in zip(example.sites, hand.values(), strict=True):
        assert s.O == o and abs(s.E - float(e)) < TOL and abs(s.V - float(v)) < TOL
    # SE21: multiplicative adjustment z / sqrt(phi) only when phi > 1 (here phi < 1, so z* = z)
    mult = ind.discordance(example, CFG3, overdispersion="multiplicative")
    assert phi < 1 and np.allclose(mult.statistic, z, rtol=0, atol=TOL) and mult.tau2 is None


def test_overdispersion_helpers_by_hand() -> None:
    """phi, tau^2 and z* on given O, E, V: K phi > K - 1 gives tau^2 > 0; K phi <= K - 1 gives 0."""
    O = np.array([10.0, 30.0, 18.0, 25.0])  # noqa: E741
    E = np.array([18.0, 22.0, 20.0, 21.0])
    V = np.array([6.0, 7.5, 6.5, 7.0])
    z = (O - E) / np.sqrt(V)
    phi = hand_winsorized_phi(list(z), *WINSOR)
    assert ind.winsorized_phi(z, WINSOR) == pytest.approx(phi, abs=TOL)
    w = E * E / V
    tau2 = (4 * phi - 3) / (w.sum() - (w * w).sum() / w.sum())
    assert tau2 > 0 and ind.additive_tau2(phi, E, V) == pytest.approx(tau2, abs=TOL)
    assert ind.additive_tau2(0.5, E, V) == 0.0  # K phi = 2 <= K - 1 = 3
    assert ind.additive_tau2(2.0, E[:1], V[:1]) == 0.0  # one site: no between-site variance
    assert np.allclose(ind.multiplicative(z, 4.0), z / 2.0) and np.allclose(ind.multiplicative(z, 0.9), z)
    with pytest.raises(ValueError):
        ind.winsorized_phi(np.array([]), WINSOR)


def test_rate_kri_by_hand() -> None:
    """§10.1: C' = sites with >= min_days patient-days and >= min_patients; lambda pools C' (the site included)."""
    ids = ["S1", "S2", "S3", "S4", "S5"]
    x = [60, 10, 20, 5, 9]
    T = [3000.0, 2000.0, 2500.0, 400.0, 29.0]
    n = [12, 10, 15, 3, 12]  # S4: 3 patients; S5: 29 patient-days < 30
    r = ind.rate_kri(ids, x, T, n, CFG, PARAMS)
    assert r.reasons == (None, None, None, "insufficient_patients", "insufficient_patients")
    lam = (60 + 10 + 20) / (3000 + 2000 + 2500)
    z = [(xi / ti - lam) / math.sqrt(lam / ti) for xi, ti in zip(x[:3], T[:3], strict=True)]
    phi = hand_winsorized_phi(z, *WINSOR)
    assert phi > 1  # the multiplicative adjustment applies
    for k in range(3):
        assert abs(r.columns["z_raw"][k] - z[k]) < TOL
        assert abs(r.statistic[k] - z[k] / math.sqrt(phi)) < TOL
    assert abs(r.phi - phi) < TOL and np.isnan(r.statistic[3:]).all()
    # no AE row anywhere: no rate to compare with, never a silent tier
    empty = ind.rate_kri(ids[:3], [0, 0, 0], T[:3], n[:3], CFG, PARAMS)
    assert empty.reasons == ("insufficient_episodes",) * 3


def test_ae_report_ratio_by_hand(example: match.StudyMatch) -> None:
    """§10.3 on the 3-site example: Fever has no evaluable non-paged episode anywhere, so its rows count for no
    site; E^U is leave-one-site-out per term; z* = z/sqrt(phi) when phi > 1."""
    terms = ("Diarrhea", "Fever", "Dyspnea")
    U = np.array([[6.0, 2.0, 3.0], [2.0, 1.0, 1.0], [3.0, 0.0, 1.0]])
    N = {"A": (6, 0, 3), "B": (5, 0, 3), "C": (4, 0, 2)}  # evaluable non-paged episodes by term
    r = ind.ae_report_ratio(example, U, terms, CFG3)
    rows = dict(zip("ABC", U.tolist(), strict=True))
    z = []
    for s in "ABC":
        others = [o for o in "ABC" if o != s]
        e = sum(N[s][t] * sum(rows[o][t] for o in others) / sum(N[o][t] for o in others) for t in (0, 2))
        u = rows[s][0] + rows[s][2]
        z.append((u - e) / math.sqrt(e))
    phi = hand_winsorized_phi(z, *WINSOR)
    want = [v / math.sqrt(phi) for v in z] if phi > 1 else z
    assert np.allclose(r.columns["z_raw"], z, rtol=0, atol=TOL)
    assert np.allclose(r.statistic, want, rtol=0, atol=TOL) and abs(r.phi - phi) < TOL


# ---- tiers, rank and the secondary p-values -------------------------------------------------------------------------


def result(indicator: str, values: list[float | None]) -> ind.IndicatorResult:
    stat = np.array([np.nan if v is None else v for v in values], dtype=float)
    reasons = tuple("insufficient_episodes" if v is None else None for v in values)
    return ind.IndicatorResult(indicator=indicator, site_ids=tuple(f"{101 + k}" for k in range(len(values))),
                               statistic=stat, calibration=-stat if indicator == ind.SIMAEREP else stat,
                               reasons=reasons)


TIER_ROWS = [
    pytest.param("discordance", {"look": -1.7, "watch": -2.5}, [-3.0, -2.5, -2.4, -1.7, -1.69, 0.0, None],
                 ["watch", "watch", "look", "look", "none", "none", "not_computed"], id="discordance: <= at both edges"),
    pytest.param("rate_kri", {"look": -1.7, "watch": None}, [-9.0, -1.7, -1.6],
                 ["look", "look", "none"], id="watch never assigned (calibrated -inf)"),
    pytest.param("discordance", {"look": None, "watch": None}, [-9.0, None], ["none", "not_computed"],
                 id="look never assigned: no flag at all"),
    pytest.param("simaerep_classic", {"look": 0.99, "watch": 0.996}, [0.999, 0.996, 0.995, 0.99, 0.98, None],
                 ["watch", "watch", "look", "look", "none", "not_computed"], id="simaerep: >= at both edges"),
    pytest.param("discordance", {"look": -2.5, "watch": -2.5}, [-2.5, -2.4], ["watch", "none"],
                 id="watch capped at look: equal thresholds"),
]


@pytest.mark.parametrize(("indicator", "thresholds", "values", "expected"), TIER_ROWS)
def test_tiers(indicator: str, thresholds: dict, values: list, expected: list) -> None:
    r = result(indicator, values)
    got = ind.tiers(r, ind.check_thresholds({indicator: thresholds}, [indicator])[indicator])
    assert list(got) == expected
    # every watch site also passes look (§8.3 nesting) and tiers use only the four values
    assert set(got) <= set(ind.TIER_VALUES)


@pytest.mark.parametrize(("indicator", "thresholds"), [
    ("discordance", {"look": -2.5, "watch": -1.7}),
    ("simaerep_classic", {"look": 0.996, "watch": 0.99}),
    ("rate_kri", {"look": None, "watch": -3.0}),
    ("discordance", {"look": float("-inf"), "watch": None}),
])
def test_misordered_or_infinite_thresholds_are_refused(indicator: str, thresholds: dict) -> None:
    with pytest.raises(ValueError):
        ind.check_thresholds({indicator: thresholds}, [indicator])


def test_rank_and_calibrated_empirical_p_values() -> None:
    r = result("discordance", [0.5, -2.0, None, -2.0, 1.0])
    assert ind.rank(r) == (3, 1, None, 2, 4)  # ties by site id
    pool = np.array([-3.0, -2.0, -2.0, -1.0, 0.0, 0.5, 2.0])
    p, q = ind.empirical_p_values(r, pool)
    M = pool.size
    want = {0: (1 + 6) / (1 + M), 1: (1 + 3) / (1 + M), 3: (1 + 3) / (1 + M), 4: (1 + 6) / (1 + M)}
    for k, v in want.items():
        assert p[k] == pytest.approx(v, abs=TOL)
    assert math.isnan(p[2]) and math.isnan(q[2])
    # BH across the 4 computed sites: sorted p = 4/8, 4/8, 7/8, 7/8
    assert q[1] == pytest.approx(min(4 / 8 * 4 / 2, 7 / 8), abs=TOL) and q[0] == pytest.approx(7 / 8, abs=TOL)


# ---- the simulated study: one Study object feeds every indicator (REQ-028) ------------------------------------------


@pytest.fixture(scope="module")
def simulated() -> tuple[sim.Study, ind.StudyIndicators]:
    p = PARAMS
    key = bvseed.key(int(p["streams"]["committed_study"]), int(p["cell_index"]["none"]),
                     int(p["roles"]["null_or_committed"]), 0, seed=DEV)
    st = sim.simulate(key, sim.default_model())
    # placeholder thresholds for the shape checks only (development, not results)
    thresholds = {"discordance": {"look": -1.7, "watch": -2.5}, "rate_kri": {"look": -1.7, "watch": -2.5},
                  "simaerep_classic": {"look": 0.99, "watch": 0.996}}
    return st, ind.analyze_study(st, thresholds=thresholds, null_pool=np.linspace(-4.0, 4.0, 101))


SITE_SIGNAL_ROW_KEYS = {"site_id", "n_patients", "n_episodes_evaluable", "n_pending", "n_paged", "call_completion",
                        "O", "E", "V", "oe_ratio", "z_raw", "z_adj", "tier", "not_computed_reason", "comparators",
                        "rank", "data_origin"}


@pytest.mark.req("REQ-028")
def test_rows_follow_site_signal_row(simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    """docs/02 SiteSignalRow: exact keys; not computed sites are grey with a reason and null statistics."""
    st, si = simulated
    rows = si.rows()
    label = {a["site_id"]: a["label"] for a in st.answer_key()}
    assert [r["site_id"] for r in rows] == list(st.sites.ids)
    computed = [r for r in rows if r["not_computed_reason"] is None]
    assert sorted(r["rank"] for r in computed) == list(range(1, len(computed) + 1))
    for r in rows:
        assert set(r) == SITE_SIGNAL_ROW_KEYS and r["data_origin"] == DATA_ORIGIN
        assert r["tier"] in ind.TIER_VALUES
        assert set(r["comparators"]) == {"rate_kri", "simaerep_classic"}
        assert set(r["comparators"]["rate_kri"]) == {"z_adj", "tier"}
        assert set(r["comparators"]["simaerep_classic"]) == {"prob", "p_value", "tier"}
        if r["not_computed_reason"] is None:
            assert r["tier"] != "not_computed" and r["z_adj"] is not None and isinstance(r["O"], int)
            assert r["oe_ratio"] == pytest.approx(r["O"] / r["E"])
        else:
            assert r["tier"] == "not_computed" and r["rank"] is None
            assert r["O"] is r["E"] is r["V"] is r["z_raw"] is r["z_adj"] is None
    by_label = {label[r["site_id"]]: r for r in rows}
    assert by_label["low_coverage"]["not_computed_reason"] == "low_coverage"
    assert by_label["small_site"]["not_computed_reason"] == "insufficient_patients"
    # comparators use only the AE log: the low-coverage site still gets them; the 6-patient site does not
    assert by_label["low_coverage"]["comparators"]["rate_kri"]["tier"] != "not_computed"
    assert by_label["small_site"]["comparators"]["rate_kri"]["tier"] == "not_computed"
    assert by_label["small_site"]["comparators"]["simaerep_classic"]["tier"] == "not_computed"
    ranked = sorted(computed, key=lambda r: r["rank"])
    assert [r["z_adj"] for r in ranked] == sorted(r["z_adj"] for r in computed)
    sec = si.secondary()
    assert [s["site_id"] for s in sec] == list(st.sites.ids)
    assert all((s["p_empirical"] is None) == (r["not_computed_reason"] is not None) for s, r in zip(sec, rows, strict=True))


def test_every_indicator_reads_the_identical_study(simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    """REQ-028: the study is unchanged by the analysis, and a rerun (resampling included) is identical."""
    st, si = simulated
    before = st.digest()
    again = ind.analyze_study(st, thresholds=si.thresholds)
    assert st.digest() == before
    for name in ind.INDICATORS:
        a, b = si.results[name], again.results[name]
        assert a.reasons == b.reasons and np.array_equal(a.statistic, b.statistic, equal_nan=True)
    assert again.rows() == si.rows()


def test_simaerep_served_orientation_gives_the_same_tiers(simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    """Served prob = 1 - BH-adjusted prob_low = -(SAP prob); prob >= -c flags exactly the sites with SAP prob <= c."""
    _, si = simulated
    r = si.results[ind.SIMAEREP]
    c = r.computed
    assert c.sum() >= 15
    assert np.allclose(r.statistic[c], 1 - r.columns["prob_low_adj"][c], rtol=0, atol=1e-15)
    assert np.array_equal(r.statistic[c], -r.calibration[c])
    tiers = si.tiers(ind.SIMAEREP)
    for k in np.flatnonzero(c):
        look, watch = r.calibration[k] <= -0.99, r.calibration[k] <= -0.996
        assert tiers[k] == ("watch" if watch else "look" if look else "none")
    assert all(t == "not_computed" for k, t in enumerate(tiers) if not c[k])


def test_comparator_inputs_by_brute_force(simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    """Rate-KRI x, T and the simaerep visit table from the site AE rows by direct loops."""
    st, _ = simulated
    rows = st.site_ae_rows()
    enroll = dict(zip(st.subject_ids, st.roster.enroll_day.tolist(), strict=True))
    site_of = dict(zip(st.subject_ids, [st.sites.ids[s] for s in st.pat_site.tolist()], strict=True))
    x, T, npat = ind.rate_kri_inputs(st)
    for k, sid in enumerate(st.sites.ids):
        assert x[k] == sum(1 for r in rows if site_of[r["subject_id"]] == sid and r["entered_on"] <= st.data_cut)
        subjects = [s for s in st.subject_ids if site_of[s] == sid]
        assert T[k] == sum(st.data_cut - enroll[s] for s in subjects) and npat[k] == len(subjects)
    vr = ind.simaerep_visit_rows(st)
    cycle = st.model.cycle
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_subject.setdefault(r["subject_id"], []).append(r)
    checked = 0
    for sid, pid, v, n_ae in zip(vr["site_id"].tolist(), vr["patient_id"].tolist(), vr["visit"].tolist(),
                                 vr["n_ae"].tolist(), strict=True):
        visit_day = enroll[pid] + (v - 1) * cycle
        assert visit_day <= st.data_cut and site_of[pid] == sid
        assert n_ae == sum(1 for r in by_subject.get(pid, ()) if r["aestdtc"] <= visit_day
                           and r["entered_on"] <= st.data_cut)
        checked += 1
    assert checked == sum((st.data_cut - e) // cycle + 1 for e in enroll.values())


def test_a_failing_comparator_is_never_silent(monkeypatch: pytest.MonkeyPatch,
                                              simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    st, si = simulated

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(ind, "simaerep", boom)
    out = ind.analyze_study(st, si.match, thresholds=si.thresholds)
    r = out.results[ind.SIMAEREP]
    assert r.reasons == ("error",) * len(st.sites.ids) and all("synthetic failure" in e for e in r.errors)
    assert set(out.tiers(ind.SIMAEREP)) == {"not_computed"}
    assert out.tiers(ind.DISCORDANCE) == si.tiers(ind.DISCORDANCE)


def test_se21_scenario_switches_discordance_to_multiplicative_overdispersion(
        simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    """SE21 (docs/11 §12.6) is an analysis setting of the scenario: z* = z/sqrt(phi) when phi > 1 on the same study."""
    st, si = simulated
    se21 = sim.simulate(st.key, sim.default_model(), scenario=sim.scenario_from_params(PARAMS, "SE21"))
    assert ind.overdispersion_of(se21, CFG) == "multiplicative" and ind.overdispersion_of(st, CFG) == "additive"
    d = ind.analyze_study(se21).results[ind.DISCORDANCE]
    base = si.results[ind.DISCORDANCE]
    assert d.overdispersion == "multiplicative" and d.tau2 is None and base.overdispersion == "additive"
    assert np.array_equal(d.columns["z_raw"], base.columns["z_raw"], equal_nan=True)  # same study, same z
    c = d.computed
    want = d.columns["z_raw"][c] / math.sqrt(d.phi) if d.phi > 1 else d.columns["z_raw"][c]
    assert np.allclose(d.statistic[c], want, rtol=0, atol=TOL)


def test_tiers_need_thresholds(simulated: tuple[sim.Study, ind.StudyIndicators]) -> None:
    st, si = simulated
    bare = ind.analyze_study(st, si.match)
    with pytest.raises(ValueError, match="thresholds"):
        bare.rows()
    with pytest.raises(ValueError, match="null pool"):
        bare.secondary()


# ---- code rules ----------------------------------------------------------------------------------------------------


INDICATORS_PY = MONITORING_DIR / "bvsignal" / "indicators.py"


def numeric_literals(source: str) -> list[tuple[int, object]]:
    """Every numeric literal other than 0 and 1 (-1 parses as minus 1)."""
    tree = ast.parse(source)
    return sorted((n.lineno, n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, int | float | complex)
                  and not isinstance(n.value, bool) and n.value not in (0, 1))


@pytest.mark.req("REQ-023")
def test_indicators_has_no_numeric_literal_other_than_0_1_and_minus_1() -> None:
    assert numeric_literals("x = [0, 1, -1, 0.0, True]\n") == []
    assert numeric_literals("x = 0.05\ny = z ** 2\n") == [(1, 0.05), (2, 2)]
    bad = numeric_literals(INDICATORS_PY.read_text(encoding="utf-8"))
    assert bad == [], f"numeric literals in indicators.py (read them from signal_rules.json or params.yaml): {bad}"


def test_indicators_reads_o_e_v_from_match_and_thresholds_from_a_file() -> None:
    """§8.1 sums are match.py's; indicators.py never writes thresholds (only calibrate.py does, REQ-023)."""
    source = INDICATORS_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert not defined & {"loso_rate", "_moments", "_cell_totals", "calibrated_threshold"}
    assert ".write_text(" not in source and "open(" not in source
