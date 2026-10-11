"""simaerep classic (legacy) port against R reference values (docs/11 §10.2, task S5, REQ-028).

Reference data (R-computed, nothing invented here): the regression data shipped in openpharma/simaerep
v1.0.0 (MIT; tag v1.0.0, `R/sysdata.rda` sha256 e5badde7...52782f1), extracted once by
`fixtures/extract_simaerep_fixture.py` into
- `fixtures/simaerep_visit_fixture.csv`: `df_visit_test`, the input of simaerep's own
  `tests/testthat/test_regression.R`: two simulated studies (A, B), 5 sites x 20 patients each, one row
  per patient visit with the cumulative AE count (3890 rows);
- `fixtures/simaerep_pval_fixture.csv`: `df_eval_test`, the 10 site rows that R produced from it
  (`data-raw/generate_test_data.R`, "generated using simaerep v0.4.2"): `site_aggr()` (med75_adj,
  min_pat_pool 0.2), `sim_sites(r = 100)` (poisson.test `pval`; bootstrap `prob_low` with R seeds
  `set.seed(1)` .. `set.seed(100)`, one per resample) and `eval_sites(method = "BH")` (BH within each
  study: `pval_adj`, `prob_low_adj`; simaerep's v1.0.0 `prob` is -`prob_low_prob_ur` = -(1 - `prob_low_adj`)).
simaerep's v1.0.0 test asserts that its classic algorithm still reproduces these rows exactly.

Acceptance (docs/workstreams/WS5-site-signal.md S5): the 10/10 site p-values (`pval` and `pval_adj`)
match with maximum relative difference < 1e-9, and the bootstrap matches within the Monte Carlo
tolerance below.

Monte Carlo tolerance (test_bootstrap_prob_within_mc_tolerance). R's `prob_low` is a #/r estimate from
r_R = 100 resamples; the port, in simaerep's #/r form, uses r = 100000 resamples from numpy (seed
20261011, the dev seed). For each site with port estimate p (both estimate the same resampling
probability), R's value must satisfy

    |p - prob_low_R| <= 4 * sqrt(p * (1 - p) * (1/100 + 1/100000)) + 1/100,

i.e. four standard errors of the difference of two independent binomial proportions plus one count of
R's resolution (continuity allowance: a probability near 0 or 1 has a near-zero standard error but R
can still land one count away; site A/S0002 does, 1/100 against an exact probability of 0.000124).
Because BH-adjusted values are monotone non-decreasing in every input p-value, R's `prob` must then lie
in [-(1 - BH(p - tol)), -(1 - BH(p + tol))] with the bounds clipped to [0, 1]. Sites where the site mean
exceeds the study mean have `prob_low` = 1 exactly (under_only) and are compared exactly.

Beyond the tolerance: test_bootstrap_replays_r_exactly replays R's own draws (Mersenne-Twister
`set.seed(k)` and R >= 3.6 rejection sampling, emulated in this file) through the port's resampling
step and must reproduce `prob_low`, `prob_low_adj` and `prob` of all 10 sites exactly; and
test_production_form_matches_exact_resampling_probability checks the production form
(1 + #)/(1 + r), r = 1000 from params.yaml, against the exact resampling probability computed by
convolution.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest

from bvsignal import simaerep_classic as sc
from bvsignal.seed import load_params

DEV_SEED = 20261011
R_FIXTURE_R = 100  # df_eval_test was generated with r = 100 (test_regression.R)
R_PORT_MC = 100_000
Z = 4

# ---- helpers -------------------------------------------------------------------------------------


def _fixture() -> tuple[dict[str, np.ndarray], dict[tuple[str, str], dict[str, str]]]:
    visits, expected = sc.load_fixture()
    return visits, {(row["study_id"], row["site_number"]): row for row in expected}


def _run(visits: dict[str, np.ndarray], study: str, *, rng: int,
         params: sc.ClassicParams | None) -> sc.ClassicResult:
    m = visits["study_id"] == study
    return sc.simaerep_classic(visits["site_number"][m], visits["patnum"][m], visits["visit"][m],
                               visits["n_ae"][m], rng=rng, params=params)


def _run_all(params: sc.ClassicParams | None, rng: int = DEV_SEED) -> dict[tuple[str, str], sc.SiteResult]:
    visits, _ = _fixture()
    out: dict[tuple[str, str], sc.SiteResult] = {}
    for study in sorted(set(visits["study_id"].tolist())):
        out |= {(study, s.site_id): s for s in _run(visits, study, rng=rng, params=params).sites}
    return out


def _fixture_params(r: int) -> sc.ClassicParams:
    return dataclasses.replace(sc.ClassicParams.from_params(), r=r, simaerep_form=True)


class _RMersenneTwister:
    """R's default generator after `set.seed(seed)` (src/main/RNG.c): Mersenne-Twister with R's seeding
    (50 LCG scrambling steps, then 625 LCG words of which the first is the position, reset to 624), and
    `unif_rand()` = fixup(genrand_int32 * 2^-32)."""

    I2_32M1 = 2.328306437080797e-10

    def __init__(self, seed: int) -> None:
        s = seed & 0xFFFFFFFF
        for _ in range(50):
            s = (69069 * s + 1) & 0xFFFFFFFF
        words = []
        for _ in range(625):
            s = (69069 * s + 1) & 0xFFFFFFFF
            words.append(s)
        self._bg = np.random.MT19937(0)
        self._bg.state = {"bit_generator": "MT19937",
                          "state": {"key": np.array(words[1:], dtype=np.uint32), "pos": 624}}

    def unif_rand(self) -> float:
        u = int(self._bg.random_raw()) * 2.3283064365386963e-10
        if u <= 0.0:
            return 0.5 * self.I2_32M1
        if 1.0 - u <= 0.0:
            return 1.0 - 0.5 * self.I2_32M1
        return u

    def unif_index(self, dn: int) -> int:
        """R_unif_index(dn), sample.kind = "Rejection" (R >= 3.6.0): rbits(ceil(log2(dn))) until < dn."""
        bits = math.ceil(math.log2(dn))
        while True:
            v = 0
            for _ in range(0, bits + 1, 16):
                v = 65536 * v + math.floor(self.unif_rand() * 65536)
            dv = v & ((1 << bits) - 1)
            if dv < dn:
                return dv


def _r_draw_indices(gen: np.random.Generator, pool_size: int, n_site: int, r: int) -> np.ndarray:
    """simaerep `prob_lower_site_ae_vs_study_ae`: resample k is
    `set.seed(k); sample(pool, n, replace = TRUE)`."""
    out = np.empty((r, n_site), dtype=np.int64)
    for k in range(r):
        g = _RMersenneTwister(k + 1)
        out[k] = [g.unif_index(pool_size) for _ in range(n_site)]
    return out


def _exact_prob_low(pool: np.ndarray, n: int, site_sum: int) -> float:
    """P(sum of n draws with replacement from pool <= site_sum), by convolution (no Monte Carlo error)."""
    one = np.bincount(pool) / pool.size
    pmf = np.array([1.0])
    for _ in range(n):
        pmf = np.convolve(pmf, one)
    return float(pmf[: site_sum + 1].sum())


# ---- the acceptance checks -----------------------------------------------------------------------


@pytest.mark.req("REQ-028")
def test_site_pvalues_match_r_fixture() -> None:
    """10/10 site p-values (raw and BH-adjusted) with maximum relative difference < 1e-9."""
    _, expected = _fixture()
    got = _run_all(sc.ClassicParams.from_params())
    assert len(expected) == 10 and set(got) == set(expected)
    rel = []
    for key, row in expected.items():
        s = got[key]
        for ours, col in ((s.pval, "pval"), (s.pval_adj, "pval_adj")):
            theirs = float(row[col])
            rel.append(abs(ours - theirs) / abs(theirs))
    assert max(rel) < 1e-9, f"max relative difference {max(rel):.3e}"
    check = sc.fixture_pvalue_check()
    assert check["rows"] == 10 and check["max_rel_diff"] == pytest.approx(max(rel), rel=0, abs=1e-15)


@pytest.mark.req("REQ-028")
def test_evaluation_point_and_means_match_r_fixture() -> None:
    """visit_med75 (med75_adj), patient counts and the site and study means at visit_med75, exactly."""
    _, expected = _fixture()
    got = _run_all(sc.ClassicParams.from_params())
    for key, row in expected.items():
        s = got[key]
        assert (s.n_pat, s.n_pat_with_med75, s.n_pat_with_med75_study) == (
            int(row["n_pat"]), int(row["n_pat_with_med75"]), int(row["n_pat_with_med75_study"])), key
        assert s.visit_med75 == float(row["visit_med75"]), key
        assert s.mean_ae_site_med75 == pytest.approx(float(row["mean_ae_site_med75"]), rel=1e-12), key
        assert s.mean_ae_study_med75 == pytest.approx(float(row["mean_ae_study_med75"]), rel=1e-12), key


@pytest.mark.req("REQ-028")
def test_bootstrap_prob_within_mc_tolerance() -> None:
    """Port (#/r, r = 100000, numpy) vs R (#/r, r = 100): the tolerance in the module docstring."""
    _, expected = _fixture()
    got = _run_all(_fixture_params(R_PORT_MC))
    for study in ("A", "B"):
        keys = sorted(k for k in expected if k[0] == study)
        p = np.array([got[k].prob_low for k in keys])
        r_low = np.array([float(expected[k]["prob_low"]) for k in keys])
        r_prob = np.array([-float(expected[k]["prob_low_prob_ur"]) for k in keys])
        tol = Z * np.sqrt(p * (1 - p) * (1 / R_FIXTURE_R + 1 / R_PORT_MC)) + 1 / R_FIXTURE_R
        under_only = np.array([got[k].mean_ae_site_med75 > got[k].mean_ae_study_med75 for k in keys])
        assert np.all(p[under_only] == 1.0) and np.all(r_low[under_only] == 1.0)
        assert np.all(np.abs(p - r_low) <= tol), list(zip(keys, p, r_low, tol, strict=True))
        lo = -(1 - sc.p_adjust_bh(np.clip(p - tol, 0, 1)))
        hi = -(1 - sc.p_adjust_bh(np.clip(p + tol, 0, 1)))
        assert np.all((lo <= r_prob) & (r_prob <= hi)), list(zip(keys, lo, r_prob, hi, strict=True))
        ours = np.array([got[k].prob for k in keys])
        assert np.all((lo <= ours) & (ours <= hi))


@pytest.mark.req("REQ-028")
def test_bootstrap_replays_r_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    """With R's own resampling draws the port reproduces prob_low, prob_low_adj and prob of every site."""
    # the emulated generator first reproduces R's documented outputs:
    # set.seed(1); runif(5) and, in R >= 3.6.0, set.seed(1); sample(1:6, 10, replace = TRUE)
    g = _RMersenneTwister(1)
    runif = [round(g.unif_rand(), 7) for _ in range(5)]
    assert runif == [0.2655087, 0.3721239, 0.5728534, 0.9082078, 0.2016819]
    g = _RMersenneTwister(1)
    assert [g.unif_index(6) + 1 for _ in range(10)] == [1, 4, 1, 2, 5, 3, 6, 2, 3, 3]

    monkeypatch.setattr(sc, "_draw_indices", _r_draw_indices)
    _, expected = _fixture()
    got = _run_all(_fixture_params(R_FIXTURE_R))
    for key, row in expected.items():
        s = got[key]
        assert s.prob_low == float(row["prob_low"]), key
        assert s.prob_low_adj == pytest.approx(float(row["prob_low_adj"]), rel=1e-15, abs=1e-15), key
        assert s.prob == pytest.approx(-float(row["prob_low_prob_ur"]), rel=1e-15, abs=1e-15), key


def test_production_form_matches_exact_resampling_probability() -> None:
    """(1 + #)/(1 + r) with r = 1000 from params.yaml vs the exact resampling probability (convolution)."""
    params = sc.ClassicParams.from_params()
    assert (params.r, params.simaerep_form) == (1000, False)
    visits, _ = _fixture()
    for study in ("A", "B"):
        m = visits["study_id"] == study
        t = sc._prepare(visits["site_number"][m], visits["patnum"][m], visits["visit"][m], visits["n_ae"][m])
        res = _run(visits, study, rng=DEV_SEED, params=params)
        for s, site in enumerate(res.sites):
            assert 0 < site.prob_low <= 1 and -1 <= site.prob <= 0
            if site.mean_ae_site_med75 > site.mean_ae_study_med75:
                assert site.prob_low == 1.0
                continue
            v = site.visit_med75
            reached, at = t.max_visit >= v, t.site_of_patient == s
            own, other = t.cum_ae[at & reached, v - 1], t.cum_ae[~at & reached, v - 1]
            exact = _exact_prob_low(np.concatenate([own, other]), own.size, int(own.sum()))
            tol = Z * math.sqrt(exact * (1 - exact) / params.r) + 1 / (params.r + 1)
            assert abs(site.prob_low - exact) <= tol, (study, site.site_id, site.prob_low, exact)


# ---- unit checks of the port -----------------------------------------------------------------------


def _study(rows: list[tuple[str, str, int, int]]) -> tuple[np.ndarray, ...]:
    site, patient, visit, n_ae = zip(*rows, strict=True)
    return np.array(site), np.array(patient), np.array(visit), np.array(n_ae)


def _patients(site: str, n: int, last_visit: int, ae_per_visit: int) -> list[tuple[str, str, int, int]]:
    """n patients at `site`, each with visits 1..last_visit and ae_per_visit new AEs per visit."""
    return [(site, f"{site}-{i:03d}", v, ae_per_visit * v)
            for i in range(n) for v in range(1, last_visit + 1)]


def test_visit_med75_med75_adj_cap_and_no_study_pool() -> None:
    # 5 patients followed to visit 20 at site X; 20 patients to visit 5 at Y. Study quantile type 7 at 0.8 of
    # the 25 last visits: index 1 + 24 * 0.8 = 20.2 -> 0.8 * 5 + 0.2 * 20 = 8 -> X capped from 20 to 8.
    rows = _patients("X", 5, 20, 1) + _patients("Y", 20, 5, 1)
    res = sc.simaerep_classic(*_study(rows), rng=DEV_SEED, params=sc.ClassicParams.from_params())
    x, y = res.by_site()["X"], res.by_site()["Y"]
    assert (x.visit_med75, x.n_pat_with_med75, x.n_pat_site_pool) == (8, 5, 5)
    assert (y.visit_med75, y.n_pat_with_med75, y.n_pat_site_pool) == (5, 20, 20)  # ceil(0.75 * 5) = 4 -> 5
    # nobody at Y reached visit 8: X is not computed (R: NA) and stays out of the BH family
    assert x.not_computed_reason == sc.NOT_COMPUTED_NO_STUDY_POOL
    assert all(math.isnan(v) for v in (x.pval, x.pval_adj, x.prob_low, x.prob_low_adj, x.prob))
    assert y.not_computed_reason is None and y.n_pat_with_med75_study == 5


def test_under_only_zero_events_and_determinism() -> None:
    params = dataclasses.replace(sc.ClassicParams.from_params(), r=200)
    # site H reports more than the rest: under_only -> prob_low = 1, pval = 1 (prob = 0)
    rows = _patients("H", 10, 8, 2) + _patients("L1", 10, 8, 1) + _patients("L2", 10, 8, 1)
    res = sc.simaerep_classic(*_study(rows), rng=7, params=params)
    h = res.by_site()["H"]
    assert (h.prob_low, h.pval, h.prob) == (1.0, 1.0, 0.0)
    assert res.to_dict() == sc.simaerep_classic(*_study(rows), rng=7, params=params).to_dict()
    # no events anywhere: R's poisson.test errors (n = 0) and simaerep returns 1; every resample ties at 0
    rows0 = _patients("A", 10, 6, 0) + _patients("B", 10, 6, 0)
    for s in sc.simaerep_classic(*_study(rows0), rng=7, params=params).sites:
        assert (s.pval, s.prob_low, s.prob) == (1.0, 1.0, 0.0)
    # a site with half the events of four others: a resample sum <= the site's needs all 10 draws from the
    # site itself, probability (10/50)^10 ~ 1e-7, so # = 0 and the +1 keeps prob_low above 0
    rows2 = _patients("U", 10, 8, 1) + [row for k in range(1, 5) for row in _patients(f"O{k}", 10, 8, 2)]
    u = sc.simaerep_classic(*_study(rows2), rng=7, params=params).by_site()["U"]
    assert u.prob_low == 1 / (params.r + 1) and u.pval < 1e-6
    assert u.prob_low_adj == pytest.approx(5 / (params.r + 1)) and u.prob == -(1 - u.prob_low_adj)


def test_input_checks_and_implicit_missing_visits() -> None:
    t = sc._prepare(["S", "S", "S", "S"], ["p", "p", "q", "q"], [1, 4, 2, 3], [1, 3, 2, 5])
    # p: visits 2-3 carry visit 1 forward; q: visit 1 (before its first row) is 0 (simaerep check_df_visit)
    assert t.max_visit.tolist() == [4, 3]
    assert t.cum_ae.tolist() == [[1, 1, 1, 3], [0, 2, 5, 5]]
    with pytest.raises(ValueError, match="site exclusive"):
        sc._prepare(["S", "T"], ["p", "p"], [1, 2], [0, 0])
    with pytest.raises(ValueError, match="duplicated"):
        sc._prepare(["S", "S"], ["p", "p"], [1, 1], [0, 1])
    with pytest.raises(ValueError, match="visit must be >= 1"):
        sc._prepare(["S"], ["p"], [0], [0])
    with pytest.raises(ValueError, match="n_ae must be >= 0"):
        sc._prepare(["S"], ["p"], [1], [-1])


def test_r_helpers() -> None:
    # R p.adjust(..., "BH"): NA excluded from n; one value returned as is; ties share the adjusted value
    out = sc.p_adjust_bh([0.01, np.nan, 0.04])
    assert out[0] == pytest.approx(0.02) and math.isnan(out[1]) and out[2] == pytest.approx(0.04)
    assert sc.p_adjust_bh([0.3]).tolist() == [0.3]
    assert sc.p_adjust_bh([0.01, 0.02, 0.03, 0.04, 0.05]) == pytest.approx([0.05] * 5)
    # R quantile type 7 and binom.test edge cases
    assert sc.r_quantile_type7([5] * 20 + [20] * 5, 0.8) == pytest.approx(8.0)
    assert sc.r_quantile_type7([1, 2, 3, 4], 0.5) == 2.5
    assert sc.binom_test_two_sided(5, 10, 0.5) == 1.0
    assert sc.binom_test_two_sided(0, 10, 0.0) == 1.0 and sc.binom_test_two_sided(1, 10, 0.0) == 0.0
    with pytest.raises(ValueError):
        sc.binom_test_two_sided(0, 0, 0.5)


def test_params_and_labels() -> None:
    params = sc.ClassicParams.from_params()
    assert (params.r, params.min_pat_pool, params.label) == (1000, 0.2, "simaerep classic (legacy)")
    bad = load_params()
    bad["comparators"]["simaerep_classic"]["under_only"] = False
    with pytest.raises(ValueError, match="ports only"):
        sc.ClassicParams.from_params(bad)
    # C's patients alone reach visit 30 (C not computed: no study pool), so the JSON carries a null
    rows = _patients("A", 10, 6, 1) + _patients("B", 10, 6, 2) + _patients("C", 10, 30, 1)
    out = sc.simaerep_classic(*_study(rows), rng=DEV_SEED).to_dict()
    assert out["label"] == "simaerep classic (legacy)" and out["indicator"] == "simaerep_classic"
    assert out["r"] == 1000 and out["prob_low_form"] == "(1 + #)/(1 + r)"
    assert all(site["label"] == "simaerep classic (legacy)" for site in out["sites"])
    c = next(site for site in out["sites"] if site["site_id"] == "C")
    assert c["prob"] is None and c["not_computed_reason"] == sc.NOT_COMPUTED_NO_STUDY_POOL
    json.dumps(out, allow_nan=False)  # NaN serialized as null
