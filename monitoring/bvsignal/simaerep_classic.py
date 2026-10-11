"""simaerep classic (legacy): Python port of the original simaerep algorithm (docs/11 §10.2, task S5).

A port, under the MIT License, of the classic algorithm of openpharma/simaerep (docs/11 refs [10, 11]):
R `simaerep(inframe = FALSE, under_only = TRUE)`, i.e. `site_aggr(method = "med75_adj",
min_pat_pool = 0.2)` -> `sim_sites()` -> `eval_sites(method = "BH")`. It is labeled
**"simaerep classic (legacy)"** in every output. simaerep v1.0.0 changed its defaults to
`inframe = TRUE, visit_med75 = FALSE`; that inframe default is not ported (NOT_BUILT.md). Version claim:
a port of the legacy algorithm, fixture-tested against the regression data shipped in the v1.0.0
repository (`R/sysdata.rda`; `tests/test_simaerep_fixture.py`, REQ-028).
Algorithm copyright (c) 2020 F. Hoffmann-La Roche Ltd and simaerep authors; MIT license text in
`monitoring/tests/fixtures/SIMAEREP_LICENSE`.

Steps (docs/11 §10.2), for the sites passed in as one study:

1. Evaluation point `visit_med75` per site (`get_visit_med75`, method `med75_adj`): ceil(0.75 x median
   of the site's patients' last visits); then the smallest last visit among the site's patients who
   reached it; capped at the study's round(quantile(last visits of all patients, 1 - min_pat_pool))
   (R `quantile` type 7, R `round` half to even).
2. Site mean: mean cumulative `n_ae` at `visit_med75` over the site's patients who reached it.
3. Bootstrap: `prob_low` = (1 + #{resampled mean <= site mean}) / (1 + r) over r resamples of
   |site patients| patients drawn with replacement from the pool (the site's patients and the other
   sites' patients who reached the site's `visit_med75`); simaerep's own form #/r only behind
   `ClassicParams.simaerep_form` (fixture test). `prob_low` = 1 when the site mean exceeds the study mean
   (`under_only`). Vectorized: one (r x n) index draw per site, from the site's own child generator.
4. Poisson test: R `poisson.test(c(x_site, x_study), c(n_site * v, n_study * v))`, two-sided, i.e.
   R `binom.test(x_site, x_site + x_study, T_site / (T_site + T_study))`; 1 when the site mean exceeds
   the study mean, and 1 when R's test errors (no events at all; simaerep wraps it in `safely`).
5. Benjamini-Hochberg (R `p.adjust(method = "BH")`, NaN excluded) across the sites, on `prob_low` and on
   the p-value; `prob` = -(1 - BH-adjusted `prob_low`), so lower is more extreme (docs/11 §9.3, §10.2).

The sites passed in are the study: the resampling pool and the BH family. A site whose `visit_med75` no
other site's patient reached is not computed (NaN, reason `no_study_pool`; R returns NA). Comparator
guards such as `min_patients` (docs/11 §10) are the caller's (indicators.py). No LLM anywhere on this
path (CLAUDE.md rule 1); every Site Signal number is SIMULATED and a reason to look, not a finding.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats

from bvsignal import MONITORING_DIR
from bvsignal.seed import load_params

INDICATOR = "simaerep_classic"
#: simaerep `get_visit_med75`: the evaluation point starts at ceiling(median(last visit) * 0.75) ("med75").
MED75_FRACTION = 0.75
#: R `binom.test` two-sided p-value: densities within this relative error of d(x) count as "as extreme".
R_BINOM_REL_ERR = 1 + 1e-7
#: The ported configuration (params.yaml `comparators.simaerep_classic`); anything else is refused.
PORTED = {"visit_med75": True, "med75_method": "med75_adj", "under_only": True, "bh": True}
#: Regression fixture extracted from openpharma/simaerep v1.0.0 `R/sysdata.rda` (tests/fixtures/).
FIXTURE_DIR = MONITORING_DIR / "tests" / "fixtures"
NOT_COMPUTED_NO_STUDY_POOL = "no_study_pool"


@dataclass(frozen=True)
class ClassicParams:
    """Parameters of the port; `from_params()` reads params.yaml `comparators.simaerep_classic`."""

    r: int
    min_pat_pool: float
    label: str
    #: simaerep's own prob_low = #/r (fixture test only); False: (1 + #)/(1 + r) (docs/11 §10.2)
    simaerep_form: bool = False

    def __post_init__(self) -> None:
        if int(self.r) != self.r or self.r < 1:
            raise ValueError(f"r must be a positive integer, got {self.r!r}")
        if not 0 < self.min_pat_pool < 1:
            raise ValueError(f"min_pat_pool must lie in (0, 1), got {self.min_pat_pool!r}")

    @classmethod
    def from_params(cls, params: Mapping[str, Any] | None = None) -> ClassicParams:
        p = (load_params() if params is None else params)["comparators"]["simaerep_classic"]
        wrong = {k: p.get(k) for k, v in PORTED.items() if p.get(k) != v}
        if wrong:
            raise ValueError(f"simaerep classic (legacy) ports only {PORTED}; params.yaml has {wrong}")
        return cls(r=int(p["r"]), min_pat_pool=float(p["min_pat_pool"]), label=str(p["label"]))

    @property
    def prob_low_form(self) -> str:
        return "#/r (simaerep)" if self.simaerep_form else "(1 + #)/(1 + r)"


@dataclass(frozen=True)
class SiteResult:
    """One site's simaerep classic (legacy) result; the column names follow simaerep's df_eval."""

    site_id: str
    n_pat: int
    #: simaerep's column: site patients whose last visit reached the unadjusted ceil(0.75 x median)
    n_pat_with_med75: int
    visit_med75: int
    #: site patients who reached visit_med75: the site mean, the resample size and the Poisson time base
    n_pat_site_pool: int
    #: other sites' patients who reached the site's visit_med75 (with the site's own: the pool)
    n_pat_with_med75_study: int
    mean_ae_site_med75: float
    mean_ae_study_med75: float
    pval: float
    pval_adj: float
    prob_low: float
    prob_low_adj: float
    #: -(1 - prob_low_adj): lower is more extreme (docs/11 §10.2)
    prob: float
    not_computed_reason: str | None


@dataclass(frozen=True)
class ClassicResult:
    label: str
    r: int
    prob_low_form: str
    sites: tuple[SiteResult, ...]

    def column(self, name: str) -> np.ndarray:
        """One field for every site, in site order (NaN where not computed)."""
        return np.array([getattr(s, name) for s in self.sites])

    def by_site(self) -> dict[str, SiteResult]:
        return {s.site_id: s for s in self.sites}

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready (NaN -> null); the label is on the run and on every site row."""

        def json_value(v: Any) -> Any:
            return None if isinstance(v, float) and math.isnan(v) else v

        return {
            "indicator": INDICATOR,
            "label": self.label,
            "statistic": "prob",
            "direction": "lower is more extreme",
            "r": self.r,
            "prob_low_form": self.prob_low_form,
            "sites": [{"label": self.label, **{k: json_value(v) for k, v in asdict(s).items()}}
                      for s in self.sites],
        }


# ---- R semantics -------------------------------------------------------------------------------------


def r_quantile_type7(x: ArrayLike, prob: float) -> float:
    """R `quantile(x, probs = prob)` (type 7) for one probability, written as R computes it."""
    xs = np.sort(np.asarray(x, dtype=float))
    if xs.size == 0:
        raise ValueError("quantile of an empty vector")
    prob = min(1.0, max(0.0, prob))
    index = 1 + max(xs.size - 1, 0) * prob
    lo, hi = math.floor(index), math.ceil(index)
    qs = float(xs[lo - 1])
    if index > lo and xs[hi - 1] != qs:
        h = index - lo
        qs = (1 - h) * qs + h * float(xs[hi - 1])
    return qs


def p_adjust_bh(p: ArrayLike) -> np.ndarray:
    """R `p.adjust(p, method = "BH")`: NaN stays NaN and is left out of n (R's lazily evaluated default)."""
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = ~np.isnan(p)
    q = p[ok]
    n = q.size
    if n <= 1:
        out[ok] = q
        return out
    i = np.arange(n, 0, -1, dtype=float)
    o = np.argsort(-q, kind="stable")  # order(p, decreasing = TRUE)
    ro = np.argsort(o, kind="stable")
    out[ok] = np.minimum(1.0, np.minimum.accumulate((n / i) * q[o]))[ro]
    return out


def binom_test_two_sided(x: int, n: int, p: float) -> float:
    """R `binom.test(x, n, p)$p.value`, alternative two.sided (ValueError where R stops with an error)."""
    if n < 1 or x < 0 or x > n:
        raise ValueError("'n' must be a positive integer >= 'x'")
    if not 0 <= p <= 1:  # also NaN
        raise ValueError("'p' must be a single number between 0 and 1")
    if p == 0:
        return float(x == 0)
    if p == 1:
        return float(x == n)
    d = stats.binom.pmf(x, n, p)
    m = n * p
    if x == m:
        return 1.0
    if x < m:
        i = np.arange(math.ceil(m), n + 1)
        y = int(np.count_nonzero(stats.binom.pmf(i, n, p) <= d * R_BINOM_REL_ERR))
        pval = stats.binom.cdf(x, n, p) + stats.binom.sf(n - y, n, p)
    else:
        i = np.arange(0, math.floor(m) + 1)
        y = int(np.count_nonzero(stats.binom.pmf(i, n, p) <= d * R_BINOM_REL_ERR))
        pval = stats.binom.cdf(y - 1, n, p) + stats.binom.sf(x - 1, n, p)
    return float(min(1.0, pval))


def poisson_test_two_sample(x1: int, x2: int, t1: float, t2: float) -> float:
    """R `poisson.test(c(x1, x2), c(t1, t2))$p.value` (r = 1, two-sided): a conditional binomial test."""
    if t1 < 0 or t2 < 0:
        raise ValueError("'T' must be nonnegative")
    return binom_test_two_sided(int(x1), int(x1) + int(x2), (1 * t1) / (1 * t1 + t2))


# ---- input -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Table:
    site_keys: np.ndarray  # sorted unique site ids
    site_of_patient: np.ndarray  # site index per patient; patients ordered by (site, patient id)
    max_visit: np.ndarray  # last visit per patient
    cum_ae: np.ndarray  # (patients, highest visit): cumulative n_ae at visit v in column v - 1


def _as_int(name: str, a: ArrayLike, minimum: int) -> np.ndarray:
    arr = np.asarray(a)
    if arr.dtype.kind == "f":
        if not np.all(np.isfinite(arr)) or np.any(arr != np.round(arr)):
            raise ValueError(f"{name} must hold integers")
    elif arr.dtype.kind not in "iu":
        raise ValueError(f"{name} must be numeric, got dtype {arr.dtype}")
    arr = arr.astype(np.int64)
    if arr.size and arr.min() < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return arr


def _prepare(site_ids: ArrayLike, patient_ids: ArrayLike, visits: ArrayLike, n_ae: ArrayLike) -> _Table:
    """One row per patient visit -> per-patient last visit and a dense cumulative-count matrix.

    As simaerep's `check_df_visit`: patient ids must be site exclusive, visits start at 1, and an
    implicitly missing visit carries the patient's previous count forward (0 before the first visit).
    Duplicated (patient, visit) rows are refused."""
    site = np.asarray(site_ids).astype(str)
    patient = np.asarray(patient_ids).astype(str)
    visit = _as_int("visit", visits, 1)
    ae = _as_int("n_ae", n_ae, 0)
    if not (site.ndim == 1 and site.shape == patient.shape == visit.shape == ae.shape):
        raise ValueError("site_ids, patient_ids, visits and n_ae must be 1-D arrays of one length")
    if site.size == 0:
        raise ValueError("no visit rows")
    site_keys, site_idx = np.unique(site, return_inverse=True)
    patient_keys, patient_idx = np.unique(patient, return_inverse=True)
    pairs = np.unique(np.stack([patient_idx, site_idx], axis=1), axis=0)
    if pairs.shape[0] != patient_keys.size:
        raise ValueError("patient ids must be site exclusive")
    site_of = np.empty(patient_keys.size, dtype=np.int64)
    site_of[pairs[:, 0]] = pairs[:, 1]
    order = np.lexsort((np.arange(patient_keys.size), site_of))  # by site, then patient id
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    row_patient = rank[patient_idx]

    n_visits = int(visit.max())
    if np.unique(row_patient * n_visits + (visit - 1)).size != visit.size:
        raise ValueError("duplicated (patient, visit) rows")
    raw = np.full((patient_keys.size, n_visits), -1, dtype=np.int64)
    raw[row_patient, visit - 1] = ae
    max_visit = np.zeros(patient_keys.size, dtype=np.int64)
    np.maximum.at(max_visit, row_patient, visit)
    pos = np.where(raw >= 0, np.arange(n_visits), -1)
    np.maximum.accumulate(pos, axis=1, out=pos)
    cum = np.where(pos >= 0, np.take_along_axis(raw, np.maximum(pos, 0), axis=1), 0)
    return _Table(site_keys=site_keys, site_of_patient=site_of[order], max_visit=max_visit, cum_ae=cum)


# ---- algorithm ---------------------------------------------------------------------------------------


def get_visit_med75(site_of_patient: np.ndarray, max_visit: np.ndarray, n_sites: int,
                    min_pat_pool: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """simaerep `get_visit_med75(method = "med75_adj")`: (visit_med75, n_pat, n_pat_with_med75) per site."""
    qup8 = round(r_quantile_type7(max_visit, 1 - min_pat_pool))  # R round(): half to even
    visit_med75 = np.empty(n_sites, dtype=np.int64)
    n_pat = np.empty(n_sites, dtype=np.int64)
    n_with = np.empty(n_sites, dtype=np.int64)
    for s in range(n_sites):
        mv = max_visit[site_of_patient == s]
        start = math.ceil(float(np.median(mv)) * MED75_FRACTION)
        reached = mv >= start
        n_pat[s], n_with[s] = mv.size, int(np.count_nonzero(reached))
        smallest = int(mv[reached].min())  # never empty: ceil(0.75 x median) <= the site's highest last visit
        visit_med75[s] = qup8 if smallest > qup8 else smallest
    return visit_med75, n_pat, n_with


def _draw_indices(gen: np.random.Generator, pool_size: int, n_site: int, r: int) -> np.ndarray:
    """r resamples of n_site pool positions, with replacement (the fixture test replays R's draws here)."""
    return gen.integers(0, pool_size, size=(r, n_site))


def simaerep_classic(site_ids: ArrayLike, patient_ids: ArrayLike, visits: ArrayLike, n_ae: ArrayLike, *,
                     rng: np.random.Generator | np.random.SeedSequence | int,
                     params: ClassicParams | None = None) -> ClassicResult:
    """Run simaerep classic (legacy) on one study given one row per patient visit (docs/11 §10.2 Input).

    `visits` are dose-visit indices 1, 2, ... up to the data cut; `n_ae` is the patient's cumulative count
    of site-originated AE rows with AESTDTC <= the visit date and `entered_on <= data_cut`. `rng` seeds the
    bootstrap (each site resamples from its own child generator, `Generator.spawn`). `params` defaults to
    params.yaml (r = 1000, min_pat_pool 0.2, (1 + #)/(1 + r))."""
    p = ClassicParams.from_params() if params is None else params
    t = _prepare(site_ids, patient_ids, visits, n_ae)
    n_sites = t.site_keys.size
    visit_med75, n_pat, n_with = get_visit_med75(t.site_of_patient, t.max_visit, n_sites, p.min_pat_pool)
    gens = np.random.default_rng(rng).spawn(n_sites)

    rows: list[dict[str, Any]] = []
    for s in range(n_sites):
        v = int(visit_med75[s])
        reached = t.max_visit >= v
        at_site = t.site_of_patient == s
        site_vals = t.cum_ae[at_site & reached, v - 1]
        study_vals = t.cum_ae[~at_site & reached, v - 1]
        n_s, n_o = int(site_vals.size), int(study_vals.size)
        x_s, x_o = int(site_vals.sum()), int(study_vals.sum())
        row: dict[str, Any] = {
            "site_id": str(t.site_keys[s]), "n_pat": int(n_pat[s]), "n_pat_with_med75": int(n_with[s]),
            "visit_med75": v, "n_pat_site_pool": n_s, "n_pat_with_med75_study": n_o,
            "mean_ae_site_med75": x_s / n_s, "mean_ae_study_med75": x_o / n_o if n_o else math.nan,
            "not_computed_reason": None,
        }
        if n_o == 0:
            row.update(pval=math.nan, prob_low=math.nan, not_computed_reason=NOT_COMPUTED_NO_STUDY_POOL)
        elif x_s * n_o > x_o * n_s:  # site mean > study mean (exact, in integers): under_only
            row.update(pval=1.0, prob_low=1.0)
        else:
            try:
                pval = poisson_test_two_sample(x_s, x_o, float(n_s * v), float(n_o * v))
            except ValueError:
                pval = 1.0  # simaerep: purrr::safely(poisson.test), NULL -> 1
            pool = np.concatenate([site_vals, study_vals])
            # same resample size, so "resampled mean <= site mean" is "resampled sum <= site sum", exactly
            sums = pool[_draw_indices(gens[s], pool.size, n_s, p.r)].sum(axis=1)
            count = int(np.count_nonzero(sums <= x_s))
            prob_low = count / p.r if p.simaerep_form else (count + 1) / (p.r + 1)
            row.update(pval=pval, prob_low=prob_low)
        rows.append(row)

    pval_adj = p_adjust_bh([row["pval"] for row in rows])
    prob_low_adj = p_adjust_bh([row["prob_low"] for row in rows])
    sites = tuple(
        SiteResult(**row, pval_adj=float(pa), prob_low_adj=float(pla), prob=float(-(1.0 - pla) + 0.0))
        for row, pa, pla in zip(rows, pval_adj, prob_low_adj, strict=True)
    )
    return ClassicResult(label=p.label, r=p.r, prob_low_form=p.prob_low_form, sites=sites)


# ---- regression fixture (docs/11 §10.2; summary.json `simaerep_fixture`) ----------------------------


def load_fixture(fixture_dir: Path = FIXTURE_DIR) -> tuple[dict[str, np.ndarray], list[dict[str, str]]]:
    """The simaerep v1.0.0 regression fixture: visit rows (input) and the R site rows (expected)."""
    with (fixture_dir / "simaerep_visit_fixture.csv").open(newline="", encoding="utf-8") as f:
        visit_rows = list(csv.DictReader(f))
    with (fixture_dir / "simaerep_pval_fixture.csv").open(newline="", encoding="utf-8") as f:
        expected = list(csv.DictReader(f))
    visits = {k: np.array([r[k] for r in visit_rows]) for k in ("study_id", "site_number", "patnum")}
    visits |= {k: np.array([int(r[k]) for r in visit_rows]) for k in ("visit", "n_ae")}
    return visits, expected


def fixture_pvalue_check(fixture_dir: Path = FIXTURE_DIR,
                         params: ClassicParams | None = None) -> dict[str, Any]:
    """Reproduce the R poisson.test p-values (raw and BH-adjusted) of every fixture site.

    Each fixture study is run as its own study (simaerep groups by study_id). Returns the row count and
    the maximum relative difference over `pval` and `pval_adj` (docs/11 §10.2 requires < 1e-9)."""
    visits, expected = load_fixture(fixture_dir)
    got: dict[tuple[str, str], SiteResult] = {}
    for study in np.unique(visits["study_id"]):
        m = visits["study_id"] == study
        res = simaerep_classic(visits["site_number"][m], visits["patnum"][m], visits["visit"][m],
                               visits["n_ae"][m], rng=0, params=params)
        got |= {(str(study), s.site_id): s for s in res.sites}
    rel = []
    for row in expected:
        site = got[(row["study_id"], row["site_number"])]
        for ours, theirs in ((site.pval, float(row["pval"])), (site.pval_adj, float(row["pval_adj"]))):
            rel.append(abs(ours - theirs) / abs(theirs))
    return {"rows": len(expected), "max_rel_diff": float(max(rel))}
