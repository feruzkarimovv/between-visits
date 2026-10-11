"""Site Signal indicators on one study (docs/11-site-signal-sap.md §8, §9.3, §10). SIMULATED.

Four statistics are computed on the identical study object (REQ-028); three of them get tiers:

* **Capture discordance** (§8, primary). The leave-one-site-out expected capture by cell (term x grade band)
  with the term's pooled rate as fallback, O, E and the cluster-robust V floored at the binomial variance
  are the §8.1 sums of ``match.py`` (computed once there, never recomputed here; ``match.loso_rate``).
  This module adds z = (O - E)/sqrt(V), the winsorized dispersion phi over the computed sites
  (``numpy.quantile`` with ``method="linear"`` at ``signal_rules.json`` ``overdispersion.winsor``), the
  additive between-site variance tau^2 and z* = (O - E)/sqrt(V + tau^2 E^2) (§8.2), or z/sqrt(phi) when phi > 1
  under sensitivity SE21 (multiplicative).
* **gsm-style rate KRI** (§10.1): site-originated AE rows (symptomatic or not, entered by the data cut) per
  patient-day, pooled rate over the sites with at least ``comparators.rate_kri.min_days`` patient-days and
  ``min_patients`` patients (the site itself included, as gsm does), Poisson z, multiplicative winsorized phi.
* **simaerep classic (legacy)** (§10.2, ``simaerep_classic.py``) on the dose-visit table of the same study,
  resampling from the study's own comparator key (``Study.resampling_key``). Its tier statistic in the SAP is
  ``prob`` = -(1 - BH-adjusted prob_low), lower is more extreme, and that is what calibration uses
  (``IndicatorResult.calibration``). Rows, ``thresholds.json`` and docs/03 §5.1 serve simaerep's own
  orientation, ``prob`` = 1 - BH-adjusted prob_low, flagged when ``prob`` >= the threshold, with the threshold
  the negated calibrated value; both give the same tier for every site. ``p_value`` is the BH-adjusted
  two-sample Poisson p-value. The comparator guard ``min_patients`` decides whether a site gets a tier; its
  patients stay in the resampling pool and the BH family, as simaerep evaluates every site of a study.
* **AE-to-report ratio** (§10.3, ablation, validation and report.md only, never a UI column): site rows mapping
  to each primary term against the evaluable non-paged episodes of that term, leave-one-site-out, over the
  terms with a defined leave-one-site-out ratio (other sites have >= 1 such episode of the term), z =
  (U - E^U)/sqrt(E^U), multiplicative winsorized phi, same guards as discordance.

Tiers (§8.3, docs/03 §5.1) come from a thresholds dict, normally ``monitoring/out/thresholds.json`` written
only by ``calibrate.py``: discordance, the rate KRI and the ablation flag a site at statistic <= threshold,
simaerep classic at ``prob`` >= threshold; a site is ``watch`` only if it also passes ``look``; a null threshold
(calibrated value -inf, §9.3) is never assigned. Tier values are exactly ``watch``, ``look``, ``none`` and
``not_computed``; a site that is not computed always carries one of the §7 reasons (REQ-025), and ``none``
reads "No signal at this sample size". Rank is by z* ascending among the computed sites. The calibrated empirical
p-value p_s = (1 + #{null pooled z* <= z*_s})/(1 + M) from the §9.2 Look pool and its Benjamini-Hochberg
q-value across computed sites are a secondary column for report.md only, never used for tiers (§8.3).

Every constant comes from ``data/signal_rules.json``, ``monitoring/params.yaml`` or ``thresholds.json``; this
file holds no numeric literal other than 0, 1 and -1 (AST check, REQ-023). No LLM anywhere on this path
(CLAUDE.md rule 1, REQ-021). Capture discordance is a reason to look, not a finding.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import ArrayLike

from bvsignal import DATA_ORIGIN, MONITORING_DIR
from bvsignal import match as bvmatch
from bvsignal import simaerep_classic as sc
from bvsignal._backend import episodes

if TYPE_CHECKING:
    from bvsignal.simulate import Study

DISCORDANCE = "discordance"
RATE_KRI = "rate_kri"
SIMAEREP = sc.INDICATOR  # "simaerep_classic"
ABLATION = "ae_report_ratio"
INDICATORS = (DISCORDANCE, RATE_KRI, SIMAEREP, ABLATION)  # all calibrated on the same null studies (§9.2)
TIERED = (DISCORDANCE, RATE_KRI, SIMAEREP)  # shown with tiers; the ablation is report-only (§10.3)
COMPARATORS = (RATE_KRI, SIMAEREP)

WATCH, LOOK, NONE = "watch", "look", "none"
NOT_COMPUTED = bvmatch.NOT_COMPUTED
TIER_VALUES = (WATCH, LOOK, NONE, NOT_COMPUTED)
TIER_KEYS = (LOOK, WATCH)  # keys of one indicator's thresholds

AT_OR_BELOW, AT_OR_ABOVE = "<=", ">="
#: served flag direction per indicator (docs/03 §5.1); calibration always uses "lower is more extreme" (§9.3)
FLAG_WHEN = {DISCORDANCE: AT_OR_BELOW, RATE_KRI: AT_OR_BELOW, SIMAEREP: AT_OR_ABOVE, ABLATION: AT_OR_BELOW}
#: the statistic each indicator serves and is tiered on
STATISTIC = {DISCORDANCE: "z_adj", RATE_KRI: "z_adj", SIMAEREP: "prob", ABLATION: "z_adj"}

ADDITIVE, MULTIPLICATIVE = "additive", "multiplicative"
OVERDISPERSION_KEY = "overdispersion"  # scenario analysis setting (SE21), passed through by match.py
PATIENT_DAYS = "patient_days"

OUT_DIR = MONITORING_DIR / "out"
THRESHOLDS_FILE = OUT_DIR / "thresholds.json"
NULL_POOL_FILE = OUT_DIR / "null_pool.json"

ERROR = bvmatch.ERROR
INSUFFICIENT_PATIENTS = bvmatch.INSUFFICIENT_PATIENTS
INSUFFICIENT_EPISODES = bvmatch.INSUFFICIENT_EPISODES

Thresholds = dict[str, dict[str, float | None]]  # indicator -> {"look": c | None, "watch": c | None} (served)


# ---- overdispersion (§8.2, §10.1) ------------------------------------------------------------------------------


def winsor_quantiles(cfg: Mapping[str, Any]) -> tuple[float, float]:
    """``signal_rules.json`` ``overdispersion.winsor``: the lower and upper winsorizing quantiles."""
    lo, hi = (float(q) for q in cfg["overdispersion"]["winsor"])
    if not lo < hi:
        raise ValueError(f"overdispersion.winsor must be increasing, got {[lo, hi]}")
    return lo, hi


def winsorized_phi(z: np.ndarray, winsor: Sequence[float]) -> float:
    """phi = mean of z^2 after winsorizing z at its own quantiles (``numpy.quantile``, ``method="linear"``)."""
    z = np.asarray(z, dtype=float)
    if z.size == 0 or not np.all(np.isfinite(z)):
        raise ValueError("phi needs at least one finite z")
    lo, hi = np.quantile(z, [float(q) for q in winsor], method="linear")
    zw = np.clip(z, lo, hi)
    return float(np.mean(zw * zw))


def additive_tau2(phi: float, E: np.ndarray, V: np.ndarray) -> float:
    """tau^2 = max(0, (K phi - (K - 1)) / (sum w - sum w^2 / sum w)), w = E^2 / V (§8.2).

    Zero when K phi <= K - 1; also zero when the denominator is not positive (K = 1, or every weight but one
    is 0), where no between-site variance can be estimated."""
    E = np.asarray(E, dtype=float)
    V = np.asarray(V, dtype=float)
    K = E.size
    w = E * E / V
    sw = float(w.sum())
    if not sw > 0:
        return 0.0
    denom = sw - float((w * w).sum()) / sw
    if not denom > 0:
        return 0.0
    return max(0.0, (K * phi - (K - 1)) / denom)


def multiplicative(z: np.ndarray, phi: float) -> np.ndarray:
    """z / sqrt(phi) when phi > 1, else z (§10.1, SE21)."""
    z = np.asarray(z, dtype=float)
    return z / math.sqrt(phi) if phi > 1 else z.copy()


# ---- results ---------------------------------------------------------------------------------------------------


def _nan(n: int) -> np.ndarray:
    return np.full(n, np.nan)


@dataclass(frozen=True)
class IndicatorResult:
    """One indicator on one study, one entry per site in study order.

    ``statistic`` is the served statistic (z* or simaerep's ``prob``) and ``calibration`` the same ordering with
    lower always more extreme (§9.3); both are NaN where the site is not computed. ``reasons`` holds the §7
    reason of every site that is not computed (None when computed). ``columns`` are extra per-site values
    (NaN = null). ``phi`` and ``tau2`` are the study's dispersion and additive between-site variance."""

    indicator: str
    site_ids: tuple[str, ...]
    statistic: np.ndarray
    calibration: np.ndarray
    reasons: tuple[str | None, ...]
    phi: float | None = None
    tau2: float | None = None
    overdispersion: str | None = None
    columns: Mapping[str, np.ndarray] = field(default_factory=dict)
    errors: tuple[str | None, ...] = ()

    @property
    def computed(self) -> np.ndarray:
        return np.array([r is None for r in self.reasons], dtype=bool)

    @property
    def n_computed(self) -> int:
        return int(self.computed.sum())

    def null_values(self) -> np.ndarray:
        """The calibration statistic of every computed site, in site order (one null study's §9.2 input)."""
        return self.calibration[self.computed].astype(float)

    def value(self, name: str, k: int) -> float | None:
        """A per-site column value as a JSON number (None for NaN)."""
        v = float(self.columns[name][k]) if name in self.columns else float(getattr(self, name)[k])
        return None if math.isnan(v) else v


def _check_method(method: str) -> str:
    if method not in (ADDITIVE, MULTIPLICATIVE):
        raise ValueError(f"unknown overdispersion method {method!r} (docs/11 §8.2, SE21)")
    return method


def discordance(sm: bvmatch.StudyMatch, cfg: Mapping[str, Any], *, overdispersion: str | None = None
                ) -> IndicatorResult:
    """§8.2 on the §8.1 sums of ``match.py``: z, phi over the computed sites, tau^2 and z* (or SE21's z/sqrt(phi))."""
    method = _check_method(str(cfg["overdispersion"]["method"]) if overdispersion is None else overdispersion)
    ids = tuple(s.site_id for s in sm.sites)
    n = len(ids)
    O, E, V = _nan(n), _nan(n), _nan(n)  # noqa: E741 (the SAP's symbols)
    computed = np.array([s.computed for s in sm.sites], dtype=bool)
    for k, s in enumerate(sm.sites):
        if s.computed:
            O[k], E[k], V[k] = float(s.O), float(s.E), float(s.V)
    z = _nan(n)
    z_adj = _nan(n)
    phi = tau2 = None
    if computed.any():
        c = computed
        z[c] = (O[c] - E[c]) / np.sqrt(V[c])
        phi = winsorized_phi(z[c], winsor_quantiles(cfg))
        if method == ADDITIVE:
            tau2 = additive_tau2(phi, E[c], V[c])
            z_adj[c] = (O[c] - E[c]) / np.sqrt(V[c] + tau2 * E[c] * E[c])
        else:
            z_adj[c] = multiplicative(z[c], phi)
    oe = np.divide(O, E, out=_nan(n), where=computed & (E > 0))
    return IndicatorResult(
        indicator=DISCORDANCE, site_ids=ids, statistic=z_adj, calibration=z_adj,
        reasons=tuple(s.not_computed_reason for s in sm.sites), phi=phi, tau2=tau2, overdispersion=method,
        columns={"O": O, "E": E, "V": V, "oe_ratio": oe, "z_raw": z},
        errors=tuple(s.error for s in sm.sites),
    )


def rate_kri(site_ids: Sequence[str], x: ArrayLike, T: ArrayLike, n_patients: ArrayLike,
             cfg: Mapping[str, Any], params: Mapping[str, Any]) -> IndicatorResult:
    """§10.1, gsm ``kri0001`` style: z = (x/T - lambda)/sqrt(lambda/T), z* = z/sqrt(phi) when phi > 1.

    ``x``: site-originated AE rows (symptomatic or not) entered by the data cut; ``T``: patient-days on study up
    to the data cut; ``n_patients``: enrolled patients. C' = sites with T >= ``min_days`` and >= ``min_patients``
    patients (others: ``insufficient_patients``); lambda pools C', the site itself included."""
    spec = params["comparators"]["rate_kri"]
    if spec["exposure"] != PATIENT_DAYS or spec["overdispersion"] != MULTIPLICATIVE:
        raise ValueError(f"the rate KRI implements patient-day exposure and multiplicative phi; params.yaml has {spec}")
    min_days = float(spec["min_days"])
    min_patients = int(cfg["minimum_data"]["min_patients"])
    ids = tuple(str(s) for s in site_ids)
    x = np.asarray(x, dtype=float)
    T = np.asarray(T, dtype=float)
    npat = np.asarray(n_patients, dtype=float)
    n = len(ids)
    if not (x.shape == T.shape == npat.shape == (n,)):
        raise ValueError("site_ids, x, T and n_patients must have one entry per site")
    ok = (T >= min_days) & (npat >= min_patients)
    reasons: list[str | None] = [None if o else INSUFFICIENT_PATIENTS for o in ok.tolist()]
    z, z_adj, rate = _nan(n), _nan(n), np.divide(x, T, out=_nan(n), where=T > 0)
    lam = float(x[ok].sum() / T[ok].sum()) if ok.any() else math.nan
    phi = None
    if ok.any() and not lam > 0:  # no AE row at any site: no rate to compare with
        reasons = [INSUFFICIENT_EPISODES if r is None else r for r in reasons]
        ok = np.zeros(n, dtype=bool)
    if ok.any():
        z[ok] = (rate[ok] - lam) / np.sqrt(lam / T[ok])
        phi = winsorized_phi(z[ok], winsor_quantiles(cfg))
        z_adj[ok] = multiplicative(z[ok], phi)
    return IndicatorResult(
        indicator=RATE_KRI, site_ids=ids, statistic=z_adj, calibration=z_adj, reasons=tuple(reasons), phi=phi,
        overdispersion=MULTIPLICATIVE,
        columns={"x": x, "T": T, "rate": rate, "lambda": np.full(n, lam), "z_raw": z},
    )


def simaerep(site_ids: Sequence[str], n_patients: ArrayLike, visit_rows: Mapping[str, np.ndarray],
             cfg: Mapping[str, Any], params: Mapping[str, Any],
             rng: np.random.Generator | np.random.SeedSequence | int) -> IndicatorResult:
    """§10.2 on one study's dose-visit table (``visit_rows``: ``site_id``, ``patient_id``, ``visit``, ``n_ae``).

    Every site with visit rows is in the simaerep study (pool and BH family); a site with fewer than
    ``min_patients`` patients, or whose ``visit_med75`` no other site's patient reached, gets no tier
    (``insufficient_patients``). Served ``prob`` = 1 - BH-adjusted prob_low (flag at >=); calibration uses the
    SAP's ``prob`` = -(1 - BH-adjusted prob_low) (lower is more extreme), the same ordering negated."""
    min_patients = int(cfg["minimum_data"]["min_patients"])
    ids = tuple(str(s) for s in site_ids)
    npat = np.asarray(n_patients)
    n = len(ids)
    res = sc.simaerep_classic(visit_rows["site_id"], visit_rows["patient_id"], visit_rows["visit"],
                              visit_rows["n_ae"], rng=rng, params=sc.ClassicParams.from_params(params))
    by_site = res.by_site()
    served, cal = _nan(n), _nan(n)
    cols = {name: _nan(n) for name in ("prob_low", "prob_low_adj", "pval", "pval_adj", "visit_med75",
                                       "mean_ae_site_med75", "mean_ae_study_med75")}
    reasons: list[str | None] = []
    for k, sid in enumerate(ids):
        r = by_site.get(sid)
        if r is not None:
            for name, col in cols.items():
                col[k] = float(getattr(r, name))
        if (r is None or npat[k] < min_patients or r.not_computed_reason is not None
                or math.isnan(r.prob_low_adj)):
            reasons.append(INSUFFICIENT_PATIENTS)
            continue
        reasons.append(None)
        cal[k] = float(r.prob)  # -(1 - prob_low_adj): the SAP §10.2 statistic, lower is more extreme
        served[k] = -cal[k] + 0.0  # 1 - prob_low_adj, simaerep's orientation (docs/03 §5.1); + 0.0 avoids -0.0
    return IndicatorResult(indicator=SIMAEREP, site_ids=ids, statistic=served, calibration=cal,
                           reasons=tuple(reasons), columns=cols)


def ae_report_ratio(sm: bvmatch.StudyMatch, U: np.ndarray, terms: Sequence[str],
                    cfg: Mapping[str, Any]) -> IndicatorResult:
    """§10.3 ablation: U_s = site rows mapping to term t (entered by the data cut), N_s(t) = evaluable non-paged
    episodes of t, E^U_s = sum_t N_s(t) x sum_{s' != s} U_s'(t) / sum_{s' != s} N_s'(t) over the terms whose
    leave-one-site-out ratio is defined, z = (U_s - E^U_s)/sqrt(E^U_s), z* = z/sqrt(phi) when phi > 1.

    Same guards as discordance: only the sites discordance computes get a value, and sites not computed for
    ``error`` or ``integrated_mode`` add nothing to the other sites' ratios (as in §8.1). ``U`` is
    (sites x terms) in study site order. A computed site with E^U = 0 gets ``insufficient_episodes``."""
    ids = tuple(s.site_id for s in sm.sites)
    n, nt = len(ids), len(terms)
    U = np.asarray(U, dtype=float)
    if U.shape != (n, nt):
        raise ValueError(f"U must be (sites x terms) = {(n, nt)}, got {U.shape}")
    col = {t: j for j, t in enumerate(terms)}
    N = np.zeros((n, nt))
    for k, s in enumerate(sm.sites):
        for ep in s.episodes:
            if ep["status"] in episodes.ANALYSIS_SET_STATUSES:
                N[k, col[ep["term"]]] += 1
    included = np.array([s.not_computed_reason not in bvmatch.EXCLUDED_FROM_RATES for s in sm.sites], dtype=bool)
    tot_U = U[included].sum(axis=0)
    tot_N = N[included].sum(axis=0)
    reasons = [s.not_computed_reason for s in sm.sites]
    u_s, e_s, z = _nan(n), _nan(n), _nan(n)
    for k in range(n):
        if reasons[k] is not None:
            continue
        own = included[k]
        other_U = tot_U - (U[k] if own else 0)
        other_N = tot_N - (N[k] if own else 0)
        defined = other_N > 0
        e = float((N[k, defined] * other_U[defined] / other_N[defined]).sum())
        u = float(U[k, defined].sum())
        if not e > 0:
            reasons[k] = INSUFFICIENT_EPISODES
            continue
        u_s[k], e_s[k] = u, e
        z[k] = (u - e) / math.sqrt(e)
    ok = np.array([r is None for r in reasons], dtype=bool)
    z_adj = _nan(n)
    phi = None
    if ok.any():
        phi = winsorized_phi(z[ok], winsor_quantiles(cfg))
        z_adj[ok] = multiplicative(z[ok], phi)
    return IndicatorResult(indicator=ABLATION, site_ids=ids, statistic=z_adj, calibration=z_adj,
                           reasons=tuple(reasons), phi=phi, overdispersion=MULTIPLICATIVE,
                           columns={"U": u_s, "E_U": e_s, "z_raw": z})


# ---- comparator inputs from a simulated study (the same Study object, REQ-028) ----------------------------------


def rate_kri_inputs(study: Study) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """x (site-originated rows entered by the data cut), T (patient-days) and patients, per site."""
    S = study.sites.n
    in_log = study.ae_entered <= study.data_cut  # every simulated row has origin "site" (§2.4)
    x = np.bincount(study.pat_site[study.ae_pat[in_log]], minlength=S).astype(float)
    T = np.bincount(study.pat_site, weights=study.days_on_study().astype(float), minlength=S)
    npat = np.bincount(study.pat_site, minlength=S)
    return x, T, npat


def simaerep_visit_rows(study: Study) -> dict[str, np.ndarray]:
    """§10.2 Input: one row per patient dose visit k = 1, 2, ... (enrollment + (k - 1) x cycle <= data cut);
    ``n_ae`` = the patient's site-originated rows with AESTDTC <= the visit date and entered by the data cut."""
    cut, cycle = int(study.data_cut), int(study.model.cycle)
    enroll = study.roster.enroll_day.astype(np.int64)
    n_visits = (cut - enroll) // cycle + 1
    P = enroll.size
    width = int(n_visits.max())
    counts = np.zeros((P, width + 1), dtype=np.int64)
    in_log = study.ae_entered <= cut
    pat = study.ae_pat[in_log]
    aest = study.ae_aestdtc[in_log].astype(np.int64)
    # first visit index (0-based) whose date is >= AESTDTC; rows after the last visit fall in the spare column
    first = np.maximum(0, -((enroll[pat] - aest) // cycle))
    first = np.where(first >= n_visits[pat], width, first)
    np.add.at(counts, (pat, first), 1)
    cum = np.cumsum(counts[:, :width], axis=1)
    visit = np.arange(width)[None, :]
    keep = visit < n_visits[:, None]
    pi, vi = np.nonzero(keep)
    site_ids = np.asarray(study.sites.ids)
    subj = np.asarray(study.subject_ids)
    return {"site_id": site_ids[study.pat_site[pi]], "patient_id": subj[pi], "visit": vi + 1,
            "n_ae": cum[pi, vi]}


def ae_report_counts(study: Study, terms: Sequence[str], cfg: Mapping[str, Any]) -> np.ndarray:
    """U (sites x terms): site-originated rows entered by the data cut whose ``aeterm`` maps to each term through
    ``match.term_synonyms`` (lower-cased, trimmed, exact; unmapped rows count for no term)."""
    syn = {w.strip().lower(): t for t, words in cfg["match"]["term_synonyms"].items() for w in words}
    col = {t: j for j, t in enumerate(terms)}
    U = np.zeros((study.sites.n, len(terms)))
    in_log = (study.ae_entered <= study.data_cut).tolist()
    site = study.pat_site[study.ae_pat].tolist()
    for r, term in enumerate(study.ae_aeterm):
        t = syn.get(term.strip().lower())
        if in_log[r] and t in col:
            U[site[r], col[t]] += 1
    return U


# ---- tiers, rank and the secondary p-values -------------------------------------------------------------------


def _passes(value: float, threshold: float | None, flag_when: str) -> bool:
    if threshold is None:  # calibrated -inf (§9.3): never assigned
        return False
    return value <= threshold if flag_when == AT_OR_BELOW else value >= threshold


def check_thresholds(thresholds: Mapping[str, Mapping[str, float | None]],
                     indicators: Iterable[str] = TIERED) -> Thresholds:
    """Validated {indicator: {look, watch}} in the served orientation; Watch must be at least as extreme as Look."""
    out: Thresholds = {}
    for ind in indicators:
        t = thresholds[ind]
        look, watch = (None if t[k] is None else float(t[k]) for k in TIER_KEYS)
        for name, v in ((LOOK, look), (WATCH, watch)):
            if v is not None and not math.isfinite(v):
                raise ValueError(f"{ind} {name} threshold must be finite or null (never assigned), got {v}")
        if look is None and watch is not None:
            raise ValueError(f"{ind}: a Watch threshold without a Look threshold breaks the nesting (§8.3)")
        if look is not None and watch is not None:
            if (watch > look) if FLAG_WHEN[ind] == AT_OR_BELOW else (watch < look):
                raise ValueError(f"{ind}: Watch threshold {watch} is less extreme than Look {look} (§9.2 step 5)")
        out[ind] = {LOOK: look, WATCH: watch}
    return out


def tiers(result: IndicatorResult, thresholds: Mapping[str, float | None]) -> tuple[str, ...]:
    """§8.3: ``watch`` if the site passes Watch and Look, ``look`` if it passes Look, else ``none``; not computed
    sites are ``not_computed``. Discordance, rate KRI and ablation pass at <=, simaerep classic at >=."""
    flag_when = FLAG_WHEN[result.indicator]
    out = []
    for k, reason in enumerate(result.reasons):
        if reason is not None:
            out.append(NOT_COMPUTED)
            continue
        v = float(result.statistic[k])
        if _passes(v, thresholds[LOOK], flag_when):
            out.append(WATCH if _passes(v, thresholds[WATCH], flag_when) else LOOK)
        else:
            out.append(NONE)
    return tuple(out)


def rank(result: IndicatorResult) -> tuple[int | None, ...]:
    """1, 2, ... by the statistic ascending among computed sites (ties: lower site id); None elsewhere."""
    order = sorted((float(result.statistic[k]), result.site_ids[k], k)
                   for k, r in enumerate(result.reasons) if r is None)
    out: list[int | None] = [None] * len(result.site_ids)
    for pos, (_, _, k) in enumerate(order, start=1):
        out[k] = pos
    return tuple(out)


def empirical_p_values(result: IndicatorResult, null_pool: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """§8.3 secondary (report.md only): p_s = (1 + #{pool <= z*_s})/(1 + M) over the computed sites and the
    Benjamini-Hochberg q-values across them; NaN for sites that are not computed."""
    pool = np.sort(np.asarray(null_pool, dtype=float))
    n = len(result.site_ids)
    p, q = _nan(n), _nan(n)
    c = result.computed
    if c.any():
        hits = np.searchsorted(pool, result.calibration[c], side="right")
        p[c] = (hits + 1) / (pool.size + 1)
        q[c] = sc.p_adjust_bh(p[c])
    return p, q


# ---- one study --------------------------------------------------------------------------------------------------


@dataclass
class StudyIndicators:
    """Every indicator on one study, with tiers when thresholds are given (docs/03 §5.3 ``SiteSignalRow``)."""

    match: bvmatch.StudyMatch
    results: dict[str, IndicatorResult]
    thresholds: Thresholds | None = None
    null_pool: np.ndarray | None = None
    data_origin: str = DATA_ORIGIN

    @property
    def site_ids(self) -> tuple[str, ...]:
        return self.results[DISCORDANCE].site_ids

    @property
    def phi(self) -> float | None:
        return self.results[DISCORDANCE].phi

    @property
    def tau2(self) -> float | None:
        return self.results[DISCORDANCE].tau2

    def tiers(self, indicator: str) -> tuple[str, ...]:
        if self.thresholds is None or indicator not in self.thresholds:
            raise ValueError(f"no thresholds for {indicator}: tiers come only from thresholds.json (§8.3)")
        return tiers(self.results[indicator], self.thresholds[indicator])

    def rank(self) -> tuple[int | None, ...]:
        return rank(self.results[DISCORDANCE])

    def null_values(self) -> dict[str, np.ndarray]:
        """Per indicator, the calibration statistic of the computed sites (one null study's §9.2 input)."""
        return {ind: r.null_values() for ind, r in self.results.items()}

    def secondary(self) -> list[dict[str, Any]]:
        """§8.3 secondary column for report.md: calibrated empirical p-value and BH q-value per site."""
        if self.null_pool is None:
            raise ValueError("the secondary p-values need the calibration null pool (null_pool.json)")
        p, q = empirical_p_values(self.results[DISCORDANCE], self.null_pool)
        return [{"site_id": sid, "p_empirical": None if math.isnan(p[k]) else float(p[k]),
                 "q_bh": None if math.isnan(q[k]) else float(q[k]), "data_origin": self.data_origin}
                for k, sid in enumerate(self.site_ids)]

    def rows(self) -> list[dict[str, Any]]:
        """``SiteSignalRow`` (docs/02, docs/03 §5.3) per site in study order, tiers from the thresholds."""
        d = self.results[DISCORDANCE]
        kri, sim = self.results[RATE_KRI], self.results[SIMAEREP]
        tier = {ind: self.tiers(ind) for ind in TIERED}
        ranks = self.rank()
        out = []
        for k, base in enumerate(self.match.rows()):
            on = d.reasons[k] is None
            out.append({
                "site_id": base["site_id"],
                "n_patients": base["n_patients"],
                "n_episodes_evaluable": base["n_episodes_evaluable"],
                "n_pending": base["n_pending"],
                "n_paged": base["n_paged"],
                "call_completion": base["call_completion"],
                "O": int(d.columns["O"][k]) if on else None,
                "E": d.value("E", k),
                "V": d.value("V", k),
                "oe_ratio": d.value("oe_ratio", k),
                "z_raw": d.value("z_raw", k),
                "z_adj": d.value("statistic", k),
                "tier": tier[DISCORDANCE][k],
                "not_computed_reason": d.reasons[k],
                "comparators": {
                    RATE_KRI: {"z_adj": kri.value("statistic", k), "tier": tier[RATE_KRI][k]},
                    SIMAEREP: {"prob": sim.value("statistic", k),
                               "p_value": sim.value("pval_adj", k) if sim.reasons[k] is None else None,
                               "tier": tier[SIMAEREP][k]},
                },
                "rank": ranks[k],
                "data_origin": base["data_origin"],
            })
        return out


def overdispersion_of(study: Study, cfg: Mapping[str, Any]) -> str:
    """The study's discordance overdispersion method: signal_rules ``overdispersion.method`` unless its scenario
    sets SE21 (``overdispersion: multiplicative``, docs/11 §12.6)."""
    return str(dict(study.scenario.analysis).get(OVERDISPERSION_KEY, cfg["overdispersion"]["method"]))


def analyze_study(study: Study, sm: bvmatch.StudyMatch | None = None, *, thresholds: Mapping[str, Any] | None = None,
                  null_pool: np.ndarray | None = None, cfg: Mapping[str, Any] | None = None) -> StudyIndicators:
    """All four indicators on one simulated study (the identical ``Study`` object, REQ-028), with tiers when
    ``thresholds`` (served orientation, e.g. :func:`load_thresholds`) are given.

    ``sm`` is ``match.match_study(study)`` (computed here when omitted). Each comparator runs in its own
    ``try``: an exception marks every site ``error`` for that comparator, never silent."""
    cfg = study.model.signal_rules if cfg is None else cfg
    params = study.model.params
    sm = bvmatch.match_study(study, cfg) if sm is None else sm
    ids = tuple(study.sites.ids)
    if tuple(s.site_id for s in sm.sites) != ids:
        raise ValueError("the match result is not of this study")
    results = {DISCORDANCE: discordance(sm, cfg, overdispersion=overdispersion_of(study, cfg))}
    for name, run in (
        (RATE_KRI, lambda: rate_kri(ids, *rate_kri_inputs(study), cfg, params)),
        (SIMAEREP, lambda: simaerep(ids, np.bincount(study.pat_site, minlength=study.sites.n),
                                    simaerep_visit_rows(study), cfg, params, study.resampling_key(SIMAEREP))),
        (ABLATION, lambda: ae_report_ratio(sm, ae_report_counts(study, study.terms, cfg), study.terms, cfg)),
    ):
        try:
            results[name] = run()
        except Exception as exc:  # never silent: every site of this indicator is not computed for `error`
            msg = f"{type(exc).__name__}: {exc}"
            n = len(ids)
            results[name] = IndicatorResult(indicator=name, site_ids=ids, statistic=_nan(n), calibration=_nan(n),
                                            reasons=(ERROR,) * n, errors=(msg,) * n)
    checked = None if thresholds is None else check_thresholds(thresholds)
    return StudyIndicators(match=sm, results=results, thresholds=checked, null_pool=null_pool,
                           data_origin=study.data_origin)


# ---- thresholds.json and null_pool.json (written only by calibrate.py) ----------------------------------------------


def load_thresholds(path: Path = THRESHOLDS_FILE) -> Thresholds:
    """{indicator: {look, watch}} from thresholds.json, served orientation; null = never assigned (§9.3)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("data_origin") != DATA_ORIGIN:
        raise ValueError(f"{path}: thresholds must be labeled data_origin {DATA_ORIGIN}")
    for ind in INDICATORS:
        if ind in doc:
            never = doc[ind].get("never_assigned", {})
            for k in TIER_KEYS:
                if (doc[ind][k] is None) != bool(never.get(k, doc[ind][k] is None)):
                    raise ValueError(f"{path}: {ind}.{k} and never_assigned.{k} disagree")
    return check_thresholds(doc, [ind for ind in INDICATORS if ind in doc])


def load_null_pool(path: Path = NULL_POOL_FILE) -> np.ndarray:
    """The sorted §9.2 Look pool of discordance z* (calibration stream) for the §8.3 secondary p-values."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("data_origin") != DATA_ORIGIN or doc.get("indicator") != DISCORDANCE:
        raise ValueError(f"{path}: expected the {DATA_ORIGIN} discordance null pool")
    values = np.asarray(doc["values"], dtype=float)
    if values.size != int(doc["M"]):
        raise ValueError(f"{path}: M = {doc['M']} but {values.size} values")
    return values
