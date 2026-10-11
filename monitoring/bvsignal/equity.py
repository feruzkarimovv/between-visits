"""Equity analysis of Site Signal (docs/11-site-signal-sap.md §14; WS5 task S9). SIMULATED.

Question (§14): **within the same site**, are Spanish-speaking patients' episodes (or extra-time patients'
episodes) less often found in the site's AE log than other patients' episodes? An odds ratio below 1 means lower
capture for Spanish-speaking (or extra-time) patients within the same site. Power is low at these sample sizes,
and every output says so. Capture discordance is a reason to look, not a finding.

What is computed (§14, exactly as the SAP fixes it)
---------------------------------------------------
* **Data.** The evaluable non-paged episodes *A_s* (statuses ``not_evaluated``, ``matched``, ``unmatched``,
  ``episodes.ANALYSIS_SET_STATUSES``) of every site, computed by the discordance indicator or not, with
  *Y_e* = 1 when the episode is matched to a site-originated AE row (§5). Groups are patient-level: language
  ``es`` vs ``en`` and pace ``extra_time`` vs ``standard``. Per stratum *k*: *a_k*, *b_k* = exposed group
  (``es`` / ``extra_time``) matched / unmatched, *c_k*, *d_k* = reference group (``en`` / ``standard``).
* **Sites used.** Sites with >= :data:`MIN_PER_GROUP` (5) evaluable episodes in **each** group. With none, the
  block reads "not computed: insufficient data" (``not_computed_reason: insufficient_data``).
* **Pooled estimate.** Mantel-Haenszel odds ratio *R/S* over the sites used [15].
* **Interval (primary).** Patient-cluster bootstrap: the patients contributing at least one *A_s* episode at a site
  used are resampled with replacement within that site, *B* times; the percentile 95% interval of ln *OR_MH*,
  exponentiated. *B* = :data:`B_COMMITTED` (2000) in the committed study, drawn from the stream-0 ``role`` 2 key
  ``SeedSequence(seed, spawn_key=(0, 0, 2, 0))``; inside a validation replicate *B* = ``equity_validation.b`` and
  the replicate's own ``role`` 2 key (§12.3, :func:`equity_intervals`).
* **Interval (secondary).** Robins-Breslow-Greenland variance of ln *OR_MH* [16], Wald interval on the log scale.
* **Heterogeneity.** Breslow-Day test of a common odds ratio across the sites used [27] (uncorrected, evaluated at
  *OR_MH*), and the per-site odds ratios.
* **Per-site estimate.** For each site used: the odds ratio *ad/bc*, with 0.5 added to every cell of a table that
  has a zero cell [23], and the within-site patient bootstrap percentile interval (same resamples as the pooled
  interval); point estimate only (``ci95: null``) when the site has < :data:`MIN_PER_GROUP_INTERVAL` (10)
  evaluable episodes in either group.
* **Sensitivity.** Strata = site x term instead of site (term mix may differ by group), over the same sites used.
* **Pace** uses the same formulas; no pace effect is simulated, so pace is a built-in negative control.
* **Single-language counterfactual.** Spanish-speaking patients get no calls, scheduled or completed; guards (§7),
  episodes, matching, leave-one-site-out *E*, *V*, *z\\** (with *τ̂²* re-estimated within the counterfactual
  study) and tiers are recomputed with the ``sap-v1`` thresholds the run used. Reported per site: ``tier_now``,
  ``tier_if_english_only``, ``reason`` (the counterfactual ``not_computed_reason``) and
  ``share_no_reference_stream`` (share of the site's patients who are Spanish-speaking). An illustration only: it
  shows which sites lose the indicator and says nothing about the agent's accuracy by language (docs/07).

Choices the SAP leaves open (docs/11 §17 C6; none depends on any evaluation output)
-----------------------------------------------------------------------------------
* Bootstrap keys: each site draws from its own child of the equity key,
  ``SeedSequence(entropy, spawn_key=(*key.spawn_key, site_index))`` with ``site_index`` its position in the
  study's site order, as ``Generator(PCG64(child)).integers(0, n_clusters, size=(B, n_clusters))`` over the site's
  clusters sorted by subject id. A site's resamples therefore do not depend on which other sites are used, and
  the first *B'* resamples of a run with *B* > *B'* are exactly the *B'* resamples. Language and pace (and the
  site x term sensitivity and per-site intervals) use the same patient resamples.
* A resample in which the pooled *R* and *S* are both 0, or a per-site resample in which one group has no episode,
  has no defined log odds ratio; it is left out of the percentiles and counted in ``bootstrap.n_undefined``.
  ln *OR* = -inf (R = 0) or +inf (S = 0) are kept; the percentile is ``numpy.quantile``'s ``linear`` rule on the
  sorted values, taking the outer order statistic when a neighbour is infinite. A bound of +inf is served as null.
* Haldane-Anscombe 0.5 applies to per-site tables only (in each bootstrap resample too); the Mantel-Haenszel
  estimate and its variance use the raw counts.
* Breslow-Day: strata whose margins fix *a_k* (no variance) carry no information and are left out; df = the
  number of remaining strata - 1; no test with fewer than 2 such strata.
* Counterfactual: Spanish-speaking patients stay enrolled at their site (the site's patient count in §7 check 4 is
  unchanged) and the site AE log is unchanged; only their calls are removed (scheduled and completed).

Determinism and isolation: everything is a pure function of the study, its match result and the equity key, so the
same inputs give byte-identical JSON regardless of worker count; equity never draws from any other key and never
mutates the run's objects, so adding it changes no other output (docs/11 §1.3). numpy and scipy only; no LLM
anywhere on this path (CLAUDE.md rule 1).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import stats

from bvsignal import DATA_ORIGIN
from bvsignal import indicators as ind
from bvsignal import match as bvmatch
from bvsignal import roster as bvroster
from bvsignal import seed as bvseed
from bvsignal._backend import episodes

if TYPE_CHECKING:
    from bvsignal.run import RunContext
    from bvsignal.simulate import Study

# ---- constants fixed by docs/11 §14 (not in params.yaml; the SAP text fixes them) ---------------------------------

MIN_PER_GROUP = 5  # sites used: >= 5 evaluable episodes in each group (§14 "Sites used")
MIN_PER_GROUP_INTERVAL = 10  # per-site interval only with >= 10 evaluable episodes in each group (§14 "Per-site")
HALDANE = 0.5  # zero cells: 0.5 added to every cell of a per-site table [23] (§14 "Per-site")
B_COMMITTED = 2000  # bootstrap resamples in the committed study (§14 "Interval (primary)")
LEVEL = 0.95  # 95% intervals (§14)

INSUFFICIENT_DATA = "insufficient_data"  # §14: "not computed: insufficient data"
NOT_COMPUTED_LABEL = "not computed: insufficient data"
CI_METHOD = "patient_bootstrap"
NOTE = ("Within-site comparisons; power is low at these sample sizes. An odds ratio below 1 means that group's "
        "episodes were found in the site AE log less often than other patients' episodes at the same site. Pace is "
        "a built-in negative control (no pace effect is simulated). A reason to look, not a finding. SIMULATED")
COUNTERFACTUAL_METHOD = (
    "Single-language (English-only) collection tool, docs/11 §14: Spanish-speaking patients get no calls, scheduled "
    "or completed; they stay enrolled at their site and the site AE log is unchanged. Guards (§7), episodes, "
    "matching, leave-one-site-out E, V, z* (tau^2 re-estimated within the counterfactual study) and tiers are "
    "recomputed with the sap-v1 thresholds of this run. An illustration of which sites lose the indicator; it says "
    "nothing about the agent's accuracy by language (docs/07). SIMULATED")

CELLS = ("a", "b", "c", "d")  # exposed matched, exposed unmatched, reference matched, reference unmatched


@dataclass(frozen=True)
class Grouping:
    """One within-site comparison: ``exposed`` vs ``reference`` (patient-level), with the per-site count keys."""

    name: str
    exposed: str
    reference: str
    n_exposed_key: str
    n_reference_key: str


LANGUAGE = Grouping("language", bvroster.SPANISH, bvroster.ENGLISH, "n_es", "n_en")
PACE = Grouping("pace", bvroster.EXTRA_TIME, bvroster.STANDARD, "n_extra_time", "n_standard")
GROUPINGS = (LANGUAGE, PACE)


# ---- data ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EquityData:
    """Per-site cluster counts of the *A_s* episodes.

    ``clusters[k]``: the subject ids of site ``k``'s patients with at least one *A_s* episode, sorted (the bootstrap
    clusters). ``counts[k]``: float array ``[n_clusters, G, 4, T]`` with, per cluster, grouping, cell (a, b, c, d)
    and term, the number of episodes. ``groupings`` and ``terms`` give the G and T axes."""

    site_ids: tuple[str, ...]
    terms: tuple[str, ...]
    groupings: tuple[Grouping, ...]
    clusters: tuple[tuple[str, ...], ...]
    counts: tuple[np.ndarray, ...]

    @property
    def n_sites(self) -> int:
        return len(self.site_ids)

    def point_tables(self) -> np.ndarray:
        """``[S, G, 4, T]``: every site's observed tables (each cluster counted once)."""
        shape = (len(self.groupings), len(CELLS), len(self.terms))
        return np.stack([c.sum(axis=0) if c.shape[0] else np.zeros(shape) for c in self.counts]) if self.counts \
            else np.zeros((0, *shape))


def build_data(site_ids: Sequence[str], terms: Sequence[str], records: Iterable[tuple[str, str, str, bool]],
               exposed: Mapping[str, Mapping[str, bool]], groupings: Sequence[Grouping] = GROUPINGS) -> EquityData:
    """:class:`EquityData` from plain episode records ``(site_id, subject_id, term, matched)`` (only *A_s* episodes)
    and, per grouping name, ``subject_id -> True`` when the patient is in the exposed group."""
    site_ids = tuple(str(s) for s in site_ids)
    terms = tuple(terms)
    s_col = {s: k for k, s in enumerate(site_ids)}
    t_col = {t: j for j, t in enumerate(terms)}
    by_site: list[list[tuple[str, int, bool]]] = [[] for _ in site_ids]
    for site_id, subject_id, term, matched in records:
        by_site[s_col[str(site_id)]].append((str(subject_id), t_col[term], bool(matched)))
    G, T = len(groupings), len(terms)
    clusters, counts = [], []
    for eps in by_site:
        ids = tuple(sorted({sid for sid, _, _ in eps}))
        row = {sid: i for i, sid in enumerate(ids)}
        arr = np.zeros((len(ids), G, len(CELLS), T))
        for sid, t, y in eps:
            for g, grouping in enumerate(groupings):
                cell = (0 if exposed[grouping.name][sid] else 2) + (0 if y else 1)
                arr[row[sid], g, cell, t] += 1
        clusters.append(ids)
        counts.append(arr)
    return EquityData(site_ids=site_ids, terms=terms, groupings=tuple(groupings), clusters=tuple(clusters),
                      counts=tuple(counts))


def study_data(study: Study, sm: bvmatch.StudyMatch) -> EquityData:
    """The *A_s* episodes of a simulated study's match result, with the roster's language and pace."""
    if tuple(s.site_id for s in sm.sites) != tuple(study.sites.ids):
        raise ValueError("the match result is not of this study")
    exposed = {
        LANGUAGE.name: dict(zip(study.subject_ids, study.roster.spanish.tolist(), strict=True)),
        PACE.name: dict(zip(study.subject_ids, study.roster.extra_time.tolist(), strict=True)),
    }
    records = [(s.site_id, ep["subject_id"], ep["term"], ep["matched_site_ae_id"] is not None)
               for s in sm.sites for ep in s.episodes if ep["status"] in episodes.ANALYSIS_SET_STATUSES]
    return build_data(study.sites.ids, study.terms, records, exposed)


# ---- keys and bootstrap resamples ------------------------------------------------------------------------------------


def equity_key(seed: int, stream: int, cell_index: int, i: int, params: Mapping[str, Any]) -> np.random.SeedSequence:
    """``SeedSequence(seed, spawn_key=(stream, cell_index, roles.resampling, i))`` (docs/11 §1.3, §12.3, §14)."""
    return bvseed.key(stream, cell_index, int(params["roles"]["resampling"]), i, seed=seed)


def site_key(key: np.random.SeedSequence, site_index: int) -> np.random.SeedSequence:
    """The child of the equity key that site ``site_index`` (study site order) draws its resamples from."""
    return np.random.SeedSequence(key.entropy, spawn_key=(*tuple(key.spawn_key), int(site_index)),
                                  pool_size=key.pool_size)


def resample_weights(key: np.random.SeedSequence, site_index: int, n_clusters: int, B: int) -> np.ndarray:
    """``[B, n_clusters]``: how often each cluster appears in each of the site's B patient resamples."""
    if n_clusters == 0:
        return np.zeros((B, 0))
    rng = np.random.Generator(np.random.PCG64(site_key(key, site_index)))
    idx = rng.integers(0, n_clusters, size=(B, n_clusters))
    flat = (np.arange(B)[:, None] * n_clusters + idx).ravel()
    return np.bincount(flat, minlength=B * n_clusters).reshape(B, n_clusters).astype(float)


def bootstrap_tables(data: EquityData, key: np.random.SeedSequence, B: int, sites: Iterable[int]) -> np.ndarray:
    """``[B, S, G, 4, T]``: each resample's tables for the sites in ``sites`` (zeros for every other site)."""
    G, T = len(data.groupings), len(data.terms)
    out = np.zeros((B, data.n_sites, G, len(CELLS), T))
    for k in sorted(set(int(s) for s in sites)):
        c = data.counts[k]
        if c.shape[0] == 0:
            continue
        w = resample_weights(key, k, c.shape[0], B)
        out[:, k] = (w @ c.reshape(c.shape[0], -1)).reshape(B, G, len(CELLS), T)
    return out


# ---- Mantel-Haenszel, Robins-Breslow-Greenland, Breslow-Day, per-site odds ratios -----------------------------------


def _cells(tab: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    t = np.asarray(tab, dtype=float)
    return t[..., 0], t[..., 1], t[..., 2], t[..., 3]


def mh_components(tab: np.ndarray) -> tuple[np.ndarray, ...]:
    """Per stratum (last axis but one) R_k = a d/n, S_k = b c/n, P_k = (a + d)/n, Q_k = (b + c)/n (0 when n = 0)."""
    a, b, c, d = _cells(tab)
    n = a + b + c + d
    safe = np.where(n > 0, n, 1.0)
    on = n > 0
    return (np.where(on, a * d / safe, 0.0), np.where(on, b * c / safe, 0.0),
            np.where(on, (a + d) / safe, 0.0), np.where(on, (b + c) / safe, 0.0))


def mh_log_or(tab: np.ndarray) -> np.ndarray:
    """ln OR_MH = ln(R/S) over the strata on the last axis but one; -inf when R = 0 < S, +inf when S = 0 < R,
    NaN when both are 0."""
    R_k, S_k, _, _ = mh_components(tab)
    R, S = R_k.sum(axis=-1), S_k.sum(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(R) - np.log(S)


def rbg_variance(tab: np.ndarray) -> np.ndarray:
    """Robins-Breslow-Greenland [16] Var(ln OR_MH) = sum P R/(2 R^2) + sum (P S + Q R)/(2 R S) + sum Q S/(2 S^2);
    NaN when R or S is 0."""
    R_k, S_k, P_k, Q_k = mh_components(tab)
    R, S = R_k.sum(axis=-1), S_k.sum(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = ((P_k * R_k).sum(axis=-1) / (2 * R * R) + (P_k * S_k + Q_k * R_k).sum(axis=-1) / (2 * R * S)
             + (Q_k * S_k).sum(axis=-1) / (2 * S * S))
    return np.where((R > 0) & (S > 0), v, np.nan)


def breslow_day(tab: np.ndarray, psi: float) -> dict[str, Any]:
    """Breslow-Day test [27] of a common odds ratio ``psi`` (= OR_MH) over the strata ``tab`` ``[K, 4]``.

    For each stratum the expected *A_k* solves A (n0 - m1 + A) = psi (n1 - A)(m1 - A) inside the margins'
    range, Var_k = 1/(1/A + 1/(n1 - A) + 1/(m1 - A) + 1/(n0 - m1 + A)), X^2 = sum (a_k - A_k)^2 / Var_k on
    (informative strata - 1) df. Strata whose margins fix a_k are left out."""
    a, b, c, d = _cells(np.asarray(tab, dtype=float).reshape(-1, len(CELLS)))
    n1, n0, m1 = a + b, c + d, a + c
    lo, hi = np.maximum(0.0, m1 - n0), np.minimum(n1, m1)
    informative = lo < hi
    out: dict[str, Any] = {"statistic": None, "df": None, "p": None, "n_strata_informative": int(informative.sum()),
                           "data_origin": DATA_ORIGIN}
    if not (math.isfinite(psi) and psi > 0) or informative.sum() < 2:
        return out
    a, n1, n0, m1, lo, hi = (x[informative] for x in (a, n1, n0, m1, lo, hi))
    if psi == 1:
        A = n1 * m1 / (n1 + n0)
    else:
        qa = 1 - psi
        qb = n0 - m1 + psi * (n1 + m1)
        qc = -psi * n1 * m1
        root = np.sqrt(np.maximum(qb * qb - 4 * qa * qc, 0.0))
        q = -(qb + np.where(qb >= 0, root, -root)) / 2
        r1 = np.divide(q, qa)
        r2 = np.divide(qc, q, out=np.full_like(q, np.nan), where=q != 0)
        A = np.where((r1 >= lo) & (r1 <= hi), r1, r2)
    var = 1 / (1 / A + 1 / (n1 - A) + 1 / (m1 - A) + 1 / (n0 - m1 + A))
    stat = float(((a - A) ** 2 / var).sum())
    df = int(a.size - 1)
    out.update(statistic=stat, df=df, p=float(stats.chi2.sf(stat, df)))
    return out


def site_log_or(tab: np.ndarray) -> np.ndarray:
    """Per-table ln(ad/bc) with 0.5 added to every cell of a table with a zero cell [23]; NaN when a group is empty."""
    t = np.asarray(tab, dtype=float)
    t = t + HALDANE * (t == 0).any(axis=-1, keepdims=True)
    a, b, c, d = _cells(t)
    raw = np.asarray(tab, dtype=float)
    empty = (raw[..., 0] + raw[..., 1] == 0) | (raw[..., 2] + raw[..., 3] == 0)
    return np.where(empty, np.nan, np.log(a) + np.log(d) - np.log(b) - np.log(c))


# ---- intervals ---------------------------------------------------------------------------------------------------------


def _quantile_sorted(v: np.ndarray, q: float) -> float:
    """``numpy.quantile(..., method="linear")`` on sorted values, taking the outer order statistic when a neighbour
    of the interpolation point is infinite (so +-inf never turns into NaN)."""
    h = (v.size - 1) * q
    lo = int(math.floor(h))
    hi = min(lo + 1, v.size - 1)
    w = h - lo
    x0, x1 = float(v[lo]), float(v[hi])
    if w == 0 or x0 == x1:
        return x0
    if math.isfinite(x0) and math.isfinite(x1):
        return x0 + w * (x1 - x0)
    return x0 if q < 0.5 else x1


def percentile_interval(log_values: np.ndarray, level: float = LEVEL) -> tuple[tuple[float, float] | None, int]:
    """(lower, upper) percentile interval of the defined (non-NaN) log values, and the number left out as undefined."""
    x = np.asarray(log_values, dtype=float).ravel()
    defined = x[~np.isnan(x)]
    n_undefined = int(x.size - defined.size)
    if defined.size == 0:
        return None, n_undefined
    v = np.sort(defined)
    tail = (1 - level) / 2
    return (_quantile_sorted(v, tail), _quantile_sorted(v, 1 - tail)), n_undefined


def _exp(x: float) -> float | None:
    """exp of a log bound as a JSON number: exp(-inf) = 0, exp(+inf) and NaN are null."""
    if math.isnan(x) or x == math.inf:
        return None
    return float(math.exp(x))


def _or_interval(log_bounds: tuple[float, float] | None) -> list[float | None] | None:
    return None if log_bounds is None else [_exp(log_bounds[0]), _exp(log_bounds[1])]


def wald_interval(log_or: float, var: float, level: float = LEVEL) -> list[float | None] | None:
    """exp(ln OR -+ z sqrt(var)), z the (1 + level)/2 standard normal quantile; null when either is not finite."""
    if not (math.isfinite(log_or) and math.isfinite(var) and var >= 0):
        return None
    z = float(stats.norm.ppf((1 + level) / 2))
    half = z * math.sqrt(var)
    return [_exp(log_or - half), _exp(log_or + half)]


def _num(x: Any) -> float | None:
    if x is None:
        return None
    v = float(x)
    return v if math.isfinite(v) else None


# ---- one grouping ------------------------------------------------------------------------------------------------------


def sites_used(point: np.ndarray, g: int) -> np.ndarray:
    """Indices of the sites with >= MIN_PER_GROUP evaluable episodes in each group of grouping ``g``."""
    n_exp, n_ref = group_sizes(point, g)
    return np.flatnonzero((n_exp >= MIN_PER_GROUP) & (n_ref >= MIN_PER_GROUP))


def group_sizes(point: np.ndarray, g: int) -> tuple[np.ndarray, np.ndarray]:
    """Per site (exposed, reference) evaluable episodes of grouping ``g`` (point tables ``[S, G, 4, T]``)."""
    t = point[:, g].sum(axis=-1)
    return t[:, 0] + t[:, 1], t[:, 2] + t[:, 3]


def key_record(key: np.random.SeedSequence) -> dict[str, Any]:
    return {"entropy": int(key.entropy), "spawn_key": [int(x) for x in key.spawn_key],
            "per_site_child": "spawn_key + (site_index,)", "data_origin": DATA_ORIGIN}


def _pooled(tab_point: np.ndarray, tab_boot: np.ndarray) -> dict[str, Any]:
    """MH estimate, RBG and bootstrap intervals for strata on the last axis but one (point ``[K, 4]``, boot
    ``[B, K, 4]``)."""
    log_or = float(mh_log_or(tab_point))
    var = float(rbg_variance(tab_point))
    bounds, n_undefined = percentile_interval(mh_log_or(tab_boot))
    return {"log_or": log_or, "mh_or": _exp(log_or), "ci95": _or_interval(bounds), "rbg_var_ln_or": _num(var),
            "rbg_ci95": wald_interval(log_or, var), "n_undefined": n_undefined}


def grouping_block(data: EquityData, g: int, point: np.ndarray, boot: np.ndarray, key: np.random.SeedSequence,
                   *, per_site: bool = True, sensitivity: bool = True) -> dict[str, Any]:
    """The ``language`` or ``pace`` block of ``equity.json`` (docs/03 §5.3) for grouping ``g``."""
    grouping = data.groupings[g]
    B = int(boot.shape[0])
    used = sites_used(point, g)
    n_exp, n_ref = group_sizes(point, g)
    block: dict[str, Any] = {
        "comparison": f"{grouping.exposed} vs {grouping.reference}",
        "exposed": grouping.exposed,
        "reference": grouping.reference,
        "mh_or": None, "ci95": None, "ci95_method": CI_METHOD, "rbg_ci95": None, "rbg_var_ln_or": None,
        "breslow_day_p": None,
        "n_sites_used": int(used.size),
        "sites_used": [data.site_ids[k] for k in used.tolist()],
        "n_episodes": {grouping.exposed: int(n_exp[used].sum()), grouping.reference: int(n_ref[used].sum()),
                       "data_origin": DATA_ORIGIN},
        "not_computed_reason": None,
        "data_origin": DATA_ORIGIN,
    }
    if grouping is PACE:
        block["negative_control"] = True
    if used.size == 0:
        block.update(not_computed_reason=INSUFFICIENT_DATA, label=NOT_COMPUTED_LABEL)
        if per_site:
            block["per_site"] = []
        return block
    site_point = point[used, g].sum(axis=-1)  # [K, 4]
    site_boot = boot[:, used, g].sum(axis=-1)  # [B, K, 4]
    pooled = _pooled(site_point, site_boot)
    bd = breslow_day(site_point, math.exp(pooled["log_or"]) if math.isfinite(pooled["log_or"]) else math.nan)
    block.update(
        mh_or=pooled["mh_or"], ci95=pooled["ci95"], rbg_ci95=pooled["rbg_ci95"], rbg_var_ln_or=pooled["rbg_var_ln_or"],
        breslow_day_p=bd["p"], breslow_day=bd,
        bootstrap={"B": B, "n_undefined": pooled["n_undefined"], "level": LEVEL,
                   "method": ("patients with >= 1 evaluable non-paged episode resampled with replacement within each "
                              "site used; percentile interval of ln OR_MH"),
                   "key": key_record(key), "data_origin": DATA_ORIGIN},
    )
    if per_site:
        logs = site_log_or(site_point)
        boot_logs = site_log_or(site_boot)  # [B, K]
        rows = []
        for j, k in enumerate(used.tolist()):
            ne, nr = int(n_exp[k]), int(n_ref[k])
            interval = ne >= MIN_PER_GROUP_INTERVAL and nr >= MIN_PER_GROUP_INTERVAL
            bounds, n_undef = percentile_interval(boot_logs[:, j]) if interval else (None, None)
            cells = site_point[j]
            rows.append({
                "site_id": data.site_ids[k],
                "or": _exp(float(logs[j])),
                "ci95": _or_interval(bounds) if interval else None,
                grouping.n_exposed_key: ne,
                grouping.n_reference_key: nr,
                "interval": CI_METHOD if interval else "point_estimate_only",
                "haldane": bool((cells == 0).any()),
                "cells": {**{name: int(v) for name, v in zip(CELLS, cells.tolist(), strict=True)}, "data_origin": DATA_ORIGIN},
                "n_patients": int(len(data.clusters[k])),
                "bootstrap_n_undefined": n_undef,
                "data_origin": DATA_ORIGIN,
            })
        block["per_site"] = rows
    if sensitivity:
        T = len(data.terms)
        st_point = np.moveaxis(point[used, g], -1, 1).reshape(used.size * T, len(CELLS))  # [K*T, 4]
        st_boot = np.moveaxis(boot[:, used, g], -1, 2).reshape(B, used.size * T, len(CELLS))
        s = _pooled(st_point, st_boot)
        n_strata = int(((st_point[:, 0] + st_point[:, 1] > 0) & (st_point[:, 2] + st_point[:, 3] > 0)).sum())
        block["sensitivity_site_x_term"] = {
            "strata": "site x term", "n_strata_both_groups": n_strata, "mh_or": s["mh_or"], "ci95": s["ci95"],
            "ci95_method": CI_METHOD, "rbg_ci95": s["rbg_ci95"], "rbg_var_ln_or": s["rbg_var_ln_or"],
            "bootstrap_n_undefined": s["n_undefined"], "data_origin": DATA_ORIGIN,
        }
    return block


def analyze_equity(data: EquityData, key: np.random.SeedSequence, B: int, *, per_site: bool = True,
                   sensitivity: bool = True) -> dict[str, dict[str, Any]]:
    """``{grouping name: block}`` for every grouping, with ``B`` patient resamples from ``key``."""
    if int(B) < 1:
        raise ValueError(f"B must be >= 1, got {B}")
    point = data.point_tables()
    needed = sorted({int(k) for g in range(len(data.groupings)) for k in sites_used(point, g).tolist()})
    boot = bootstrap_tables(data, key, int(B), needed)
    return {grouping.name: grouping_block(data, g, point, boot, key, per_site=per_site, sensitivity=sensitivity)
            for g, grouping in enumerate(data.groupings)}


def equity_intervals(study: Study, sm: bvmatch.StudyMatch, key: np.random.SeedSequence, B: int
                     ) -> dict[str, dict[str, Any]]:
    """The language and pace blocks of one validation replicate (docs/11 §12.3): pooled estimate and intervals
    only (no per-site rows, no sensitivity, no counterfactual). ``key`` is the replicate's ``role`` 2 key
    (:func:`equity_key`) and ``B`` = ``equity_validation.b``."""
    return analyze_equity(study_data(study, sm), key, B, per_site=False, sensitivity=False)


def interval_contains_one(block: Mapping[str, Any], interval: str = "ci95") -> bool | None:
    """Whether a block's interval contains 1 (a null upper bound is +inf); None when the block is not computed."""
    ci = block.get(interval)
    if block.get("not_computed_reason") is not None or ci is None:
        return None
    lo, hi = ci
    return bool((lo is None or lo <= 1) and (hi is None or hi >= 1))


# ---- single-language counterfactual -----------------------------------------------------------------------------------


def english_only_inputs(study: Study) -> list[bvmatch.SiteData]:
    """Each site's §7 inputs with every Spanish-speaking patient's calls removed (scheduled and completed)."""
    spanish = study.roster.spanish
    S = study.sites.n
    es_call = spanish[study.call_pat]
    site = study.pat_site[study.call_pat]
    sched_es = np.bincount(site, weights=es_call.astype(float), minlength=S).astype(int)
    done_es = np.bincount(site, weights=(es_call & study.call_completed).astype(float), minlength=S).astype(int)
    es_subjects = frozenset(sid for sid, es in zip(study.subject_ids, spanish.tolist(), strict=True) if es)
    out = []
    for k, sd in enumerate(bvmatch.site_inputs(study)):
        if sd.load_error is not None:
            out.append(sd)
            continue
        out.append(replace(sd, calls=[c for c in sd.calls if c["subject_id"] not in es_subjects],
                           scheduled_calls=int(sd.scheduled_calls) - int(sched_es[k]),
                           completed_calls=int(sd.completed_calls) - int(done_es[k])))
    return out


def single_language_counterfactual(study: Study, sm_now: bvmatch.StudyMatch, tiers_now: Sequence[str],
                                   z_now: np.ndarray, thresholds: Mapping[str, float | None],
                                   cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-site rows and a study summary of the English-only counterfactual (docs/11 §14)."""
    sm_cf = bvmatch.analyze_sites(english_only_inputs(study), cfg, data_cut=study.data_cut,
                                  analysis=study.scenario.analysis, data_origin=study.data_origin)
    disc = ind.discordance(sm_cf, cfg, overdispersion=ind.overdispersion_of(study, cfg))
    tiers_cf = ind.tiers(disc, thresholds)
    S = study.sites.n
    n_pat = np.bincount(study.pat_site, minlength=S)
    n_es = np.bincount(study.pat_site, weights=study.roster.spanish.astype(float), minlength=S).astype(int)
    rows = []
    for k, sid in enumerate(study.sites.ids):
        now, cf = sm_now.sites[k], sm_cf.sites[k]
        rows.append({
            "site_id": sid,
            "tier_now": tiers_now[k],
            "tier_if_english_only": tiers_cf[k],
            "reason": cf.not_computed_reason,
            "reason_now": now.not_computed_reason,
            "share_no_reference_stream": float(n_es[k] / n_pat[k]) if n_pat[k] else 0.0,
            "n_patients": int(n_pat[k]),
            "n_patients_no_reference_stream": int(n_es[k]),
            "n_episodes_evaluable_now": now.n_episodes_evaluable,
            "n_episodes_evaluable_if_english_only": cf.n_episodes_evaluable,
            "call_completion_if_english_only": _num(cf.call_completion),
            "z_adj_now": _num(z_now[k]),
            "z_adj_if_english_only": _num(disc.statistic[k]),
            "loses_indicator": tiers_now[k] != ind.NOT_COMPUTED and tiers_cf[k] == ind.NOT_COMPUTED,
            "data_origin": DATA_ORIGIN,
        })
    summary = {
        "method": COUNTERFACTUAL_METHOD,
        "n_computed_sites_now": sm_now.n_computed_sites,
        "n_computed_sites_if_english_only": sm_cf.n_computed_sites,
        "study_not_computed_reason_if_english_only": sm_cf.study_not_computed_reason,
        "tau2_if_english_only": _num(disc.tau2),
        "phi_if_english_only": _num(disc.phi),
        "n_sites_losing_indicator": sum(r["loses_indicator"] for r in rows),
        "n_sites_tier_changed": sum(r["tier_now"] != r["tier_if_english_only"] for r in rows),
        "illustration_only": True,
        "data_origin": DATA_ORIGIN,
    }
    return rows, summary


# ---- the run.py hook ------------------------------------------------------------------------------------------------


def build_equity(ctx: RunContext, B: int = B_COMMITTED) -> dict[str, Any]:
    """``equity.json`` of the committed study (``run.py`` adds ``_about``, ``data_origin`` and provenance).

    The bootstrap key is the committed study's ``role`` 2 key on its stream, cell and replicate (docs/11 §1.3)."""
    i = int(ctx.key.spawn_key[-1])
    key = equity_key(ctx.seed, ctx.stream, ctx.cell_index, i, ctx.params)
    data = study_data(ctx.study, ctx.match)
    blocks = analyze_equity(data, key, B)
    disc = ctx.indicators.results[ind.DISCORDANCE]
    rows, summary = single_language_counterfactual(
        ctx.study, ctx.match, ctx.indicators.tiers(ind.DISCORDANCE), disc.statistic,
        ctx.thresholds[ind.DISCORDANCE], ctx.cfg)
    return {
        "method": {
            "sap_section": "docs/11-site-signal-sap.md §14",
            "data": ("evaluable non-paged episodes (A_s) of every site, computed or not; Y = matched to a "
                     "site-originated AE row"),
            "sites_used_rule": f">= {MIN_PER_GROUP} evaluable episodes in each group",
            "per_site_interval_rule": (f"within-site patient bootstrap when >= {MIN_PER_GROUP_INTERVAL} evaluable "
                                       "episodes in each group, else point estimate only"),
            "zero_cells": f"{HALDANE} added to every cell of a per-site table with a zero cell",
            "B": int(B),
            "level": LEVEL,
            "odds_ratio_direction": "below 1: the exposed group's episodes were matched less often within the site",
            "data_origin": DATA_ORIGIN,
        },
        "language": blocks[LANGUAGE.name],
        "pace": blocks[PACE.name],
        "single_language_counterfactual": rows,
        "counterfactual": summary,
        "power_is_low": True,
        "note": NOTE,
    }
