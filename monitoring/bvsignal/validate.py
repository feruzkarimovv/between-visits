"""Operating characteristics of Site Signal (docs/11-site-signal-sap.md §12). SIMULATED.

Writes ``validation/site_signal/{summary.json, null_rate.json, power_grid.json, failure_case.json,
sensitivity.json}``. ``summary.json`` (§12.9) is the single source of every Site Signal number quoted anywhere;
the other four files hold the same blocks with more detail (per-design thresholds, per-site committed tiers).

Replicate sets, every replicate keyed ``SeedSequence(seed, spawn_key=(stream, cell_index, role, i))`` (§1.3)
with the ``params.yaml`` streams, cell indices and roles:

* ``null_validation`` (stream 2, cell 0, role 0, ``calibration.r_validation``): fresh null studies at the sap-v1
  design and the sap-v1 thresholds (§12.1). The first ``equity_validation.r`` also run the §14 equity analysis
  with a patient-cluster bootstrap of ``equity_validation.b`` resamples from role-2 keys (§12.3).
* ``grid_null:<cell>`` / ``grid_power:<cell>`` (stream 3, cells 1-24, roles 0/1): per-design calibration from
  ``grid.null_reps_per_design`` null studies (thresholds reused across f) and ``grid.reps`` studies with one
  planted site per grid f; the f values share each replicate's key (common random numbers, §12.2).
* ``design_row`` (stream 3, cell 25, role 1): the sap-v1 design with the committed thresholds (§12.2).
* ``full_mix`` (stream 3, cell 26, role 1, ``r_validation``): the §11.4 mix, roles re-drawn per replicate, with
  the pace equity analysis (§12.3).
* ``failure_a_null`` / ``failure_a_power`` (stream 4, cell 27) and ``failure_b_null`` (stream 4, cell 28):
  the §12.5 failure case.
* ``sensitivity_null:SEk`` / ``sensitivity_mix:SEk`` (stream 4, the SE cell, roles 0/1): §12.6 (ii) and (iii).
* ``committed`` (stream 0, cell 0, role 0, i = 0): the committed study re-run under each scenario (§12.6 (i), (iv)).

Every per-replicate result (the calibration-orientation statistic, §7 reason and discordance E of every site
for every indicator, the role of every site, the equity intervals) is independent of any threshold. Tiers are
assigned afterwards (§8.3: at or below the threshold, lower always more extreme, §9.3), so one pass over all
replicates serves every threshold set. Replicates run in worker processes (``--workers``); each is a pure function
of its key and results are collected in job order, so every output is identical for any worker count.

``quick_hashes``: for each stream, the sha256 of the canonical JSON of the per-replicate results of the first
``calibration.r_quick`` replicates of the ``r_validation``-sized sets and the first ``grid.reps_quick`` of every
other set (all of the committed re-runs). ``--quick`` runs exactly those replicates (an exact subset of the full
run, §1.3); ``--quick --check`` exits non-zero unless every hash equals ``summary.json`` ``quick_hashes``.

Unrounded float64 everywhere in the JSON (§15 rule 6); the REQ-023 acceptance (§12.1) uses unrounded values and
reports pass, conservative or failure, never hidden. No LLM anywhere on this path (CLAUDE.md rule 1). Capture
discordance is a reason to look, not a finding.

Command line::

    uv run --project monitoring python -m bvsignal.validate                    # evaluation seed, logged
    uv run --project monitoring python -m bvsignal.validate --quick --check    # CI
    uv run --project monitoring python -m bvsignal.validate --seed dev --scale 0.02 --out "$TMPDIR/val"
    uv run --project monitoring python -m bvsignal.validate --seed dev --scale 0.02 --out "$TMPDIR/val" --quick --check

The evaluation seed refuses a dirty working tree and a ``frozen_inputs`` mismatch, reads the committed
``monitoring/out/thresholds.json``, writes only to ``validation/site_signal/`` with scale 1 and appends to the run
log (docs/11 §1.2). The dev seed refuses ``monitoring/out/`` and ``validation/site_signal/`` as output and uses
``--thresholds`` or an in-process dev calibration of ``scale x r_null`` null studies (stream 1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import beta as beta_dist
from scipy.stats import norm

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT
from bvsignal import calibrate as cb
from bvsignal import indicators as ind
from bvsignal import match as bvmatch
from bvsignal import seed as bvseed
from bvsignal import simaerep_classic as sc
from bvsignal import simulate as sim
from bvsignal._backend import episodes

OUT_REL = "validation/site_signal"
OUT_DIR = REPO_ROOT / OUT_REL
SUMMARY, NULL_RATE, POWER_GRID, FAILURE_CASE, SENSITIVITY = (
    "summary.json", "null_rate.json", "power_grid.json", "failure_case.json", "sensitivity.json")
OUTPUT_FILES = (SUMMARY, NULL_RATE, POWER_GRID, FAILURE_CASE, SENSITIVITY)
THRESHOLDS_FILE = MONITORING_DIR / "out" / "thresholds.json"
ANSWER_KEY_FILE = MONITORING_DIR / "out" / "answer_key.json"
PLANNING_GRID_FILE = MONITORING_DIR / "planning" / "planning_grid.json"
COMMITTED_DIRS = ("monitoring/out", OUT_REL)

INDICATORS = ind.INDICATORS  # discordance, rate_kri, simaerep_classic, ae_report_ratio (§9.2, §10)
COMPARATORS = tuple(name for name in INDICATORS if name != ind.DISCORDANCE)  # head-to-head incl. the ablation
TIERS = (ind.LOOK, ind.WATCH)
REASONS = bvmatch.REASONS
K_BINS = (("<=12", None, 12), ("13-16", 13, 16), (">=17", 17, None))  # computed sites per study (§12.1)
N_TERTILES = 3  # E_s tertiles (§12.1)
SIZE_TOLERANCE = 0.02  # every E_s tertile's Look rate within nominal +/- 0.02 (§12.1 size calibration)
ACCEPT_SE_MULTIPLIER = 2  # rate <= nominal + 2 sqrt(SE_cal^2 + SE_val^2) (§12.1, REQ-023)
CI_LEVEL = 0.95  # Clopper-Pearson (§12.8)
EQUITY_MIN_EPISODES = 5  # sites with >= 5 evaluable non-paged episodes in each group (§14)
LANGUAGE, PACE = "language", "pace"
MATCH_WINDOW_SCENARIOS = ("SE1", "SE2")  # §12.6 (iv)
FULL_MIX_NOTE = "includes two scenarios constructed to defeat a rate-based KRI"  # §12.4
EVAL_STUDY_NOTE = "Illustration only, not evidence of performance (docs/11 section 12.7)."
ABOUT = ("Site Signal operating characteristics (docs/11-site-signal-sap.md §12). Every number is SIMULATED; "
         "capture discordance is a reason to look, not a finding. Values are unrounded; round only for display.")
ABOUT_DEV = "DEVELOPMENT OUTPUT (dev seed), not a result and never committed or quoted. " + ABOUT
STREAM_NAMES = {0: "committed_study", 2: "null_validation", 3: "power_grid", 4: "failure_and_sensitivity"}
SCENARIO_CHANGE = {  # docs/11 §12.6 table, for the reader of sensitivity rows (parameters are in `scenario`)
    "SE1": "Match window: upper bound 3 days with lower tolerance 0",
    "SE2": "Match window: upper bound 14 days with lower tolerance 7",
    "SE3": "Mapping error x2, English only",
    "SE4": "Mapping error x4, English only",
    "SE5": "Mapping error x2, Spanish only",
    "SE6": "Mapping error x4, Spanish only",
    "SE7": "Call completion mean 0.60 (the low_coverage site keeps 0.50)",
    "SE8": "Call completion mean 0.95 (the low_coverage site keeps 0.50)",
    "SE9": "Misspecified null: between-site SD 0.2, sap-v1 thresholds",
    "SE10": "Misspecified null: between-site SD 0.5, sap-v1 thresholds",
    "SE11": "Misspecified null: between-site SD 0.6, sap-v1 thresholds",
    "SE12": "Misspecified null: patient random-effect SD 0.0",
    "SE13": "Misspecified null: patient random-effect SD 1.0",
    "SE14": "Page-proximal paged stratum (7 days)",
    "SE15": "Capture boost near urgent or emergency calls at the 5 sites with the most such calls",
    "SE16": "Reporting propensity correlated across streams (Gaussian copula)",
    "SE17": "One honest site with entry lag mean 25 days",
    "SE18": "Three sites with a site-level mapping error Beta(2, 18)",
    "SE19": "Case-mix SD 0.6",
    "SE20": "Evaluability with next visit + 19 days",
    "SE21": "Multiplicative overdispersion instead of additive tau^2",
}


class ValidationError(RuntimeError):
    """A precondition of a validation run is not met (message is user-facing)."""


# ---- replicate jobs ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    """One replicate key and what to simulate on it. ``fs`` non-empty: one study per planted f, same key
    (common random numbers, §12.2); ``roles`` is then the planted role label."""

    set_id: str
    seed: int
    stream: int
    cell: int
    role: int
    i: int
    design: sim.Design
    roles: str = "null"  # "null" | "full_mix" | "planted"
    fs: tuple[float, ...] = ()
    scenario: sim.Scenario | None = None
    equity: tuple[str, ...] = ()
    detail: bool = False  # committed study: also the per-episode statuses (§12.6 (iv))


def _labels(params: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(spec["label"]) for spec in params["planted"].values())


def _equity_groups(study: sim.Study, kind: str) -> np.ndarray:
    """Per patient: True for the group whose capture odds are the numerator (Spanish-speaking, extra time)."""
    return study.roster.spanish.astype(bool) if kind == LANGUAGE else study.roster.extra_time.astype(bool)


def run_job(job: Job) -> tuple[list[dict[str, Any]], float]:
    """Simulate and analyze one replicate key (all planted f when ``job.fs``); returns per-study records and the
    CPU seconds spent (timing only, never written)."""
    t0 = time.process_time()
    model = sim.default_model()
    params = model.params
    labels = _labels(params)
    key = bvseed.key(job.stream, job.cell, job.role, job.i, seed=job.seed)
    if job.roles == "planted":
        role_sets: list[Any] = [sim.planted_roles(params, f) for f in job.fs]
    else:
        role_sets = [job.roles]
    out = []
    for roles in role_sets:
        study = sim.simulate(key, model, design=job.design, roles=roles, scenario=job.scenario)
        result = ind.analyze_study(study)
        rec = study_record(study, result, labels)
        if job.equity:
            res_key = bvseed.key(job.stream, job.cell, int(params["roles"]["resampling"]), job.i, seed=job.seed)
            rng = np.random.Generator(np.random.PCG64(res_key))
            b = int(params["equity_validation"]["b"])
            rec["equity"] = {kind: equity_interval(study, result.match, _equity_groups(study, kind), rng, b)
                             for kind in job.equity}
        if job.detail:
            rec["episodes"] = [[ep["episode_id"], ep["status"]] for ep in result.match.episodes()]
            rec["site_ids"] = list(study.sites.ids)
        out.append(rec)
    return out, time.process_time() - t0


def study_record(study: sim.Study, result: ind.StudyIndicators, labels: Sequence[str]) -> dict[str, Any]:
    """The threshold-free per-replicate result of one study: per indicator and site the calibration statistic
    (lower is more extreme; NaN when not computed) and the §7 reason code (-1 computed); discordance E, phi and
    tau^2; and each site's planted label. A simulated study never has reason ``error`` (that would be a bug, so it
    aborts the run instead of silently lowering the computed counts)."""
    S = study.sites.n
    stat = np.full((len(INDICATORS), S), np.nan)
    reason = np.full((len(INDICATORS), S), -1, dtype=np.int8)
    for j, name in enumerate(INDICATORS):
        r = result.results[name]
        if bvmatch.ERROR in r.reasons:
            msg = next((e for e in r.errors if e), "unknown error")
            raise RuntimeError(f"{name} failed on a simulated study (key {study.key.spawn_key}): {msg}")
        stat[j] = r.calibration
        reason[j] = [-1 if x is None else REASONS.index(x) for x in r.reasons]
    d = result.results[ind.DISCORDANCE]
    return {
        "stat": stat,
        "reason": reason,
        "E": np.asarray(d.columns["E"], dtype=float).copy(),
        "phi": math.nan if d.phi is None else float(d.phi),
        "tau2": math.nan if d.tau2 is None else float(d.tau2),
        "role": np.array([labels.index(lab) for lab in study.role], dtype=np.int8),
    }


# ---- equity (§14 math, used inside validation replicates; equity.py may duplicate it) -----------------------------


def mh_odds_ratio(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mantel-Haenszel ln OR and its Robins-Breslow-Greenland variance over the last axis (strata) (§14).

    a, b: group-1 matched / unmatched; c, d: group-0 matched / unmatched. ln OR is -inf when R = 0, +inf when
    S = 0 and NaN when both are 0; the variance is NaN unless R > 0 and S > 0."""
    a, b, c, d = (np.asarray(x, dtype=float) for x in (a, b, c, d))
    n = a + b + c + d
    with np.errstate(divide="ignore", invalid="ignore"):
        Rk = np.where(n > 0, a * d / n, 0.0)
        Sk = np.where(n > 0, b * c / n, 0.0)
        Pk = np.where(n > 0, (a + d) / n, 0.0)
        Qk = np.where(n > 0, (b + c) / n, 0.0)
        R, S = Rk.sum(axis=-1), Sk.sum(axis=-1)
        ln_or = np.log(R) - np.log(S)
        var = ((Pk * Rk).sum(axis=-1) / (2 * R * R) + (Pk * Sk + Qk * Rk).sum(axis=-1) / (2 * R * S)
               + (Qk * Sk).sum(axis=-1) / (2 * S * S))
    var = np.where((R > 0) & (S > 0), var, np.nan)
    return ln_or, var


def percentile_linear(values: np.ndarray, q: float) -> float:
    """``numpy.quantile(method="linear")`` that also accepts +/-inf: interpolating towards an infinite neighbour
    gives that infinity; NaN only between -inf and +inf."""
    x = np.sort(np.asarray(values, dtype=float))
    if x.size == 0 or np.isnan(x).any():
        return math.nan
    h = (x.size - 1) * q
    lo = math.floor(h)
    g = h - lo
    if g == 0 or lo + 1 >= x.size:
        return float(x[lo])
    a, b = float(x[lo]), float(x[lo + 1])
    if a == b:
        return a
    if math.isinf(a) and math.isinf(b):
        return math.nan
    if math.isinf(a):
        return a
    if math.isinf(b):
        return b
    return a + g * (b - a)


def equity_interval(study: sim.Study, sm: bvmatch.StudyMatch, group: np.ndarray, rng: np.random.Generator,
                    n_boot: int) -> dict[str, Any]:
    """§14 inside one validation replicate: MH ln OR over the sites with >= 5 evaluable non-paged episodes in each
    group (computed or not; sites excluded for error or integrated mode are left out, as in §8.1), and its
    percentile 95% interval from a patient-cluster bootstrap: for each included site in site order,
    ``rng.integers(0, n_k, size=(B, n_k))`` resamples its n_k patients with >= 1 episode in A_s. Resamples with an
    undefined OR (R = S = 0) are left out of the percentiles and counted."""
    pindex = {sid: p for p, sid in enumerate(study.subject_ids)}
    strata = []
    for s in sm.sites:
        if s.not_computed_reason in bvmatch.EXCLUDED_FROM_RATES:
            continue
        pats: dict[int, list[int]] = {}
        for ep in s.episodes:
            if ep["status"] in episodes.ANALYSIS_SET_STATUSES:
                p = pindex[ep["subject_id"]]
                cell = pats.setdefault(p, [0, 0])
                cell[0 if ep["matched_site_ae_id"] is not None else 1] += 1
        if not pats:
            continue
        order = sorted(pats)
        g = group[order]
        mu = np.array([pats[p] for p in order], dtype=float)  # [n_k, 2]: matched, unmatched
        M = np.column_stack([mu[:, 0] * g, mu[:, 1] * g, mu[:, 0] * ~g, mu[:, 1] * ~g])  # a, b, c, d per patient
        n1, n0 = M[:, :2].sum(), M[:, 2:].sum()
        if n1 >= EQUITY_MIN_EPISODES and n0 >= EQUITY_MIN_EPISODES:
            strata.append(M)
    if not strata:
        return {"n_sites_used": 0, "computed": False}
    tables = np.array([m.sum(axis=0) for m in strata])  # [K, 4]
    ln_or, var = mh_odds_ratio(*tables.T)
    boot = np.empty((n_boot, len(strata), 4))
    for k, M in enumerate(strata):
        nk = M.shape[0]
        idx = rng.integers(0, nk, size=(n_boot, nk))
        W = np.bincount((np.arange(n_boot)[:, None] * nk + idx).ravel(), minlength=n_boot * nk).reshape(n_boot, nk)
        boot[:, k, :] = W @ M
    b_ln, _ = mh_odds_ratio(boot[..., 0], boot[..., 1], boot[..., 2], boot[..., 3])
    defined = b_ln[~np.isnan(b_ln)]
    lo, hi = percentile_linear(defined, (1 - CI_LEVEL) / 2), percentile_linear(defined, (1 + CI_LEVEL) / 2)
    ok = defined.size > 0 and not (math.isnan(lo) or math.isnan(hi))
    return {
        "n_sites_used": len(strata),
        "computed": bool(ok),
        "ln_or": float(ln_or),
        "rbg_var": float(var),
        "ln_ci": [lo, hi],
        "n_undefined_resamples": int(n_boot - defined.size),
        "covers_1": bool(ok and lo <= 0 <= hi),
        "excludes_1": bool(ok and (lo > 0 or hi < 0)),
    }


# ---- job lists -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """Replicate counts after ``--scale`` and ``--quick`` (quick: the first replicates of the same keys)."""

    scale: float
    quick: bool
    params: Mapping[str, Any]

    def full(self, n: int) -> int:
        return max(1, int(round(n * self.scale)))

    def count(self, n: int, *, validation_sized: bool) -> int:
        """Replicates of a set of nominal size ``n``: scaled, then capped at the quick count in quick mode."""
        m = self.full(n)
        if not self.quick:
            return m
        p = self.params
        q = int(p["calibration"]["r_quick"]) if validation_sized else int(p["grid"]["reps_quick"])
        return min(q, m)

    def quick_count(self, n: int, *, validation_sized: bool) -> int:
        return Plan(self.scale, True, self.params).count(n, validation_sized=validation_sized)


@dataclass(frozen=True)
class SetSpec:
    set_id: str
    stream: int
    cell: int
    role: int
    n_nominal: int
    validation_sized: bool
    design: sim.Design
    roles: str = "null"
    fs: tuple[float, ...] = ()
    scenario: sim.Scenario | None = None
    equity_first: int = 0  # equity on the first n replicates
    equity: tuple[str, ...] = ()


def replicate_sets(params: Mapping[str, Any], plan: Plan) -> list[SetSpec]:
    """Every replicate set in the fixed job order."""
    st, ci, roles = params["streams"], params["cell_index"], params["roles"]
    r0, r1 = int(roles["null_or_committed"]), int(roles["planted"])
    r_val = int(params["calibration"]["r_validation"])
    grid, fc, sens = params["grid"], params["failure_case"], params["sensitivity"]
    model_design = sim.sap_design(params)
    fs = tuple(float(f) for f in grid["f"])
    out = [SetSpec("null_validation", int(st["null_validation"]), int(ci["none"]), r0, r_val, True, model_design,
                   equity_first=plan.full(int(params["equity_validation"]["r"])), equity=(LANGUAGE, PACE))]
    for row in ci["grid"]:
        cell = int(row["cell"])
        d = sim.grid_design(params, cell)
        out.append(SetSpec(f"grid_null:{cell}", int(st["power_grid"]), cell, r0, int(grid["null_reps_per_design"]),
                           False, d))
        out.append(SetSpec(f"grid_power:{cell}", int(st["power_grid"]), cell, r1, int(grid["reps"]), False, d,
                           roles="planted", fs=fs))
    out.append(SetSpec("design_row", int(st["power_grid"]), int(ci["sap_v1_design"]), r1, int(grid["reps"]), False,
                       model_design, roles="planted", fs=fs))
    out.append(SetSpec("full_mix", int(st["power_grid"]), int(ci["full_mix"]), r1, r_val, True, model_design,
                       roles="full_mix", equity_first=r_val, equity=(PACE,)))
    fsc = sim.failure_case_scenario(params)
    s4 = int(st["failure_and_sensitivity"])
    out.append(SetSpec("failure_a_null", s4, int(ci["failure_case_a"]), r0, int(fc["r_null"]), False, model_design,
                       scenario=fsc))
    out.append(SetSpec("failure_a_power", s4, int(ci["failure_case_a"]), r1, int(fc["reps"]), False, model_design,
                       roles="planted", fs=fs, scenario=fsc))
    out.append(SetSpec("failure_b_null", s4, int(ci["failure_case_b"]), r0, int(fc["r_null_b"]), False, model_design,
                       scenario=fsc))
    for sid, cell in ci["sensitivity"].items():
        scen = sim.scenario_from_params(params, sid)
        out.append(SetSpec(f"sensitivity_null:{sid}", s4, int(cell), r0, int(sens["r_null"]), False, model_design,
                           scenario=scen))
        out.append(SetSpec(f"sensitivity_mix:{sid}", s4, int(cell), r1, int(sens["r_full_mix"]), False, model_design,
                           roles="full_mix", scenario=scen))
    return out


def committed_jobs(params: Mapping[str, Any], seed: int) -> list[Job]:
    """The committed study (stream 0, cell 0, role 0, i 0) as is and under each §12.6 scenario."""
    st, ci = params["streams"], params["cell_index"]
    design = sim.sap_design(params)
    base = dict(set_id="committed:base", seed=seed, stream=int(st["committed_study"]), cell=int(ci["none"]),
                role=int(params["roles"]["null_or_committed"]), i=0, design=design, roles="full_mix", detail=True)
    jobs = [Job(**base)]
    for sid in ci["sensitivity"]:
        jobs.append(Job(**{**base, "set_id": f"committed:{sid}", "scenario": sim.scenario_from_params(params, sid)}))
    return jobs


def build_jobs(params: Mapping[str, Any], seed: int, plan: Plan) -> tuple[list[SetSpec], list[Job]]:
    sets = replicate_sets(params, plan)
    jobs: list[Job] = []
    for s in sets:
        n = plan.count(s.n_nominal, validation_sized=s.validation_sized)
        for i in range(n):
            jobs.append(Job(set_id=s.set_id, seed=seed, stream=s.stream, cell=s.cell, role=s.role, i=i,
                            design=s.design, roles=s.roles, fs=s.fs, scenario=s.scenario,
                            equity=s.equity if i < s.equity_first else ()))
    jobs.extend(committed_jobs(params, seed))
    return sets, jobs


def is_quick(job: Job, sets: Mapping[str, SetSpec], plan: Plan) -> bool:
    if job.set_id.startswith("committed:"):
        return True
    s = sets[job.set_id]
    return job.i < plan.quick_count(s.n_nominal, validation_sized=s.validation_sized)


def run_jobs(jobs: Sequence[Job], workers: int, *, log: Callable[[str], None] | None = None
             ) -> list[tuple[list[dict[str, Any]], float]]:
    """Every job's records in job order; identical for any ``workers`` (1 runs in this process)."""
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if workers == 1 or len(jobs) <= 1:
        return [run_job(j) for j in jobs]
    from bvsignal import validate as this  # pickles as bvsignal.validate.run_job under `python -m`

    chunk = max(1, min(8, len(jobs) // (workers * 32)))
    out = []
    step = max(1, len(jobs) // 20)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        for k, r in enumerate(ex.map(this.run_job, jobs, chunksize=chunk), start=1):
            out.append(r)
            if log is not None and (k % step == 0 or k == len(jobs)):
                log(f"  {k}/{len(jobs)} replicate keys ({time.perf_counter() - t0:.0f} s)")
    return out


# ---- canonical per-replicate JSON and quick hashes ---------------------------------------------------------------------


def _num(x: float) -> Any:
    x = float(x)
    if math.isnan(x):
        return None
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return x


def record_json(rec: Mapping[str, Any], labels: Sequence[str]) -> dict[str, Any]:
    """A per-study record as canonical JSON-able data (floats unrounded, NaN as null)."""
    out: dict[str, Any] = {
        "stat": {name: [_num(v) for v in rec["stat"][j].tolist()] for j, name in enumerate(INDICATORS)},
        "reason": {name: [None if c < 0 else REASONS[c] for c in rec["reason"][j].tolist()]
                   for j, name in enumerate(INDICATORS)},
        "E": [_num(v) for v in rec["E"].tolist()],
        "phi": _num(rec["phi"]),
        "tau2": _num(rec["tau2"]),
        "role": [labels[c] for c in rec["role"].tolist()],
    }
    if "equity" in rec:
        out["equity"] = {k: {kk: ([_num(x) for x in vv] if isinstance(vv, list) else
                                  (_num(vv) if isinstance(vv, float) else vv)) for kk, vv in v.items()}
                         for k, v in rec["equity"].items()}
    if "episodes" in rec:
        out["episodes"] = rec["episodes"]
    return out


def quick_hashes(jobs: Sequence[Job], results: Sequence[tuple[list[dict[str, Any]], float]],
                 sets: Sequence[SetSpec], plan: Plan, labels: Sequence[str]) -> dict[str, str]:
    """Per stream: sha256 of the canonical JSON of the quick replicates' records, in job order."""
    by_id = {s.set_id: s for s in sets}
    buckets: dict[int, list[Any]] = {}
    for job, (recs, _) in zip(jobs, results, strict=True):
        if is_quick(job, by_id, plan):
            buckets.setdefault(job.stream, []).append(
                {"set": job.set_id, "i": job.i, "records": [record_json(r, labels) for r in recs]})
    out = {}
    for stream in sorted(buckets):
        blob = json.dumps(buckets[stream], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        out[STREAM_NAMES.get(stream, f"stream_{stream}")] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return out


# ---- thresholds ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThresholdSet:
    """Look and Watch thresholds per indicator in the calibration orientation (flag at <=; -inf never assigned),
    with each one's achieved in-sample null rate and its MC SE."""

    source: str
    look: np.ndarray
    watch: np.ndarray
    achieved: Mapping[str, Mapping[str, Mapping[str, float | None]]]

    def never(self, j: int, tier: str) -> bool:
        return not math.isfinite(float((self.look if tier == ind.LOOK else self.watch)[j]))

    def achieved_rate(self, name: str, tier: str) -> float | None:
        return self.achieved.get(name, {}).get(tier, {}).get("rate")

    def achieved_se(self, name: str, tier: str) -> float | None:
        return self.achieved.get(name, {}).get(tier, {}).get("mc_se")


def thresholds_from_doc(doc: Mapping[str, Any], source: str) -> ThresholdSet:
    """A thresholds.json document (served orientation, docs/03 §5.1) in the calibration orientation."""
    served = ind.check_thresholds(doc, INDICATORS)
    look, watch = np.empty(len(INDICATORS)), np.empty(len(INDICATORS))
    for j, name in enumerate(INDICATORS):
        flip = ind.FLAG_WHEN[name] == ind.AT_OR_ABOVE
        for arr, tier in ((look, ind.LOOK), (watch, ind.WATCH)):
            v = served[name][tier]
            arr[j] = -math.inf if v is None else (-float(v) if flip else float(v))
    return ThresholdSet(source=source, look=look, watch=watch, achieved=doc.get("achieved", {}))


def thresholds_from_calibration(cals: Mapping[str, cb.IndicatorCalibration], source: str) -> ThresholdSet:
    look = np.array([cals[name].c_look for name in INDICATORS])
    watch = np.array([cals[name].c_watch for name in INDICATORS])
    return ThresholdSet(source=source, look=look, watch=watch,
                        achieved={name: cals[name].achieved() for name in INDICATORS})


def calibrate_set(records: Sequence[dict[str, Any]], cfg: Mapping[str, Any]) -> dict[str, cb.IndicatorCalibration]:
    """§9.2-9.3 on a set of null records (per-design or failure-case calibration, §12.2, §12.5)."""
    a_look, a_watch = cb.alphas(cfg)
    out = {}
    for j, name in enumerate(INDICATORS):
        values = [r["stat"][j][r["reason"][j] < 0] for r in records]
        out[name] = cb.calibrate_indicator(name, values, a_look, a_watch)
    return out


# ---- statistics helpers ----------------------------------------------------------------------------------------------


def clopper_pearson(x: int, n: int, level: float = CI_LEVEL) -> list[float] | None:
    """Exact binomial interval (§12.8): lo = 0 when x = 0, hi = 1 when x = n."""
    if n <= 0:
        return None
    a = 1 - level
    lo = 0.0 if x == 0 else float(beta_dist.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta_dist.ppf(1 - a / 2, x + 1, n - x))
    return [lo, hi]


def binomial(x: np.ndarray | Sequence[bool], *, ci: bool = False) -> dict[str, Any]:
    """Share with MC SE sqrt(p(1-p)/R) (§12.8) and, for a fixed-sample proportion, the Clopper-Pearson 95% CI."""
    x = np.asarray(x, dtype=bool)
    R = int(x.size)
    if R == 0:
        out: dict[str, Any] = {"rate": None, "mc_se": None, "n": 0}
        if ci:
            out["ci95"] = None
        return out
    p = float(x.mean())
    out = {"rate": p, "mc_se": math.sqrt(p * (1 - p) / R), "n": R}
    if ci:
        out["ci95"] = clopper_pearson(int(x.sum()), R)
    return out


def mean_se(v: np.ndarray | Sequence[float]) -> dict[str, Any]:
    """Mean with MC SE sd/sqrt(R)."""
    v = np.asarray(v, dtype=float)
    R = int(v.size)
    if R == 0:
        return {"rate": None, "mc_se": None, "n": 0}
    se = float(np.std(v, ddof=1) / math.sqrt(R)) if R > 1 else None
    return {"rate": float(v.mean()), "mc_se": se, "n": R}


def clustered_rate(F: np.ndarray, K: np.ndarray) -> dict[str, Any]:
    """Per-site rate sum F / sum K with the cluster-aware MC SE (§12.8):
    (1/K_bar) sqrt(sum_r (F_r - alpha K_r)^2 / (R (R - 1))), and a normal 95% interval from it."""
    F, K = np.asarray(F, dtype=float), np.asarray(K, dtype=float)
    R = int(F.size)
    tot = float(K.sum())
    if R == 0 or tot == 0:
        return {"rate": None, "mc_se": None, "ci95": None, "n_sites": int(tot), "n_studies": R}
    a = float(F.sum()) / tot
    kbar = tot / R
    se = math.sqrt(float(np.sum((F - a * K) ** 2)) / (R * (R - 1))) / kbar if R > 1 else None
    z = float(norm.ppf((1 + CI_LEVEL) / 2))
    ci = None if se is None else [max(0.0, a - z * se), min(1.0, a + z * se)]
    return {"rate": a, "mc_se": se, "ci95": ci, "ci95_method": "normal, cluster-aware MC SE", "n_sites": int(tot),
            "n_studies": R}


@dataclass
class Stack:
    """A replicate set's records stacked: stat/reason [R, n_ind, S], E [R, S], role [R, S]."""

    stat: np.ndarray
    reason: np.ndarray
    E: np.ndarray
    role: np.ndarray

    @classmethod
    def of(cls, records: Sequence[dict[str, Any]]) -> Stack:
        if not records:
            raise ValueError("an empty replicate set")
        return cls(stat=np.stack([r["stat"] for r in records]), reason=np.stack([r["reason"] for r in records]),
                   E=np.stack([r["E"] for r in records]), role=np.stack([r["role"] for r in records]))

    @property
    def R(self) -> int:
        return int(self.stat.shape[0])

    @property
    def computed(self) -> np.ndarray:
        return self.reason < 0

    def flags(self, th: ThresholdSet) -> dict[str, np.ndarray]:
        """[R, n_ind, S] bool per tier: computed and at or below the tier's threshold (Watch implies Look)."""
        c = self.computed
        with np.errstate(invalid="ignore"):
            look = c & (self.stat <= th.look[None, :, None])
            watch = look & (self.stat <= th.watch[None, :, None])
        return {ind.LOOK: look, ind.WATCH: watch}


# ---- §12.1 null false-flag rates -------------------------------------------------------------------------------------


def null_block(stack: Stack, th: ThresholdSet, cfg: Mapping[str, Any], j: int, *, full: bool = True) -> dict[str, Any]:
    """§12.1 for indicator j on null studies (every site honest)."""
    name = INDICATORS[j]
    fl = stack.flags(th)
    comp = stack.computed[:, j, :]
    K = comp.sum(axis=1)
    F = fl[ind.LOOK][:, j, :].sum(axis=1)
    W = fl[ind.WATCH][:, j, :].any(axis=1)
    out: dict[str, Any] = {
        "indicator": name,
        "look_per_site": clustered_rate(F, K),
        "look_per_study": mean_se(F),
        "watch_fwer": binomial(W, ci=True),
    }
    if not full:
        return out
    # E_s tertiles: cut points from the discordance E of every discordance-computed site, pooled over studies
    dj = INDICATORS.index(ind.DISCORDANCE)
    has_e = stack.computed[:, dj, :] & np.isfinite(stack.E)
    pool = stack.E[has_e]
    tertiles = []
    if pool.size:
        cuts = np.quantile(pool, [k / N_TERTILES for k in range(1, N_TERTILES)], method="linear")
        edges = [-math.inf, *cuts.tolist(), math.inf]
        for t in range(N_TERTILES):
            m = has_e & comp & (stack.E > edges[t]) & (stack.E <= edges[t + 1])
            row = clustered_rate((fl[ind.LOOK][:, j, :] & m).sum(axis=1), m.sum(axis=1))
            e_range = [None if math.isinf(x) else float(x) for x in (edges[t], edges[t + 1])]  # null = open end
            tertiles.append({"tertile": t + 1, "e_range": e_range, **row})
    out["look_per_site_by_e_tertile"] = tertiles
    bins = []
    for label, lo, hi in K_BINS:
        sel = (K >= (lo if lo is not None else 0)) & (K <= (hi if hi is not None else np.iinfo(np.int64).max))
        bins.append({"k_bin": label, "n_studies": int(sel.sum()), "look_per_site": clustered_rate(F[sel], K[sel]),
                     "look_per_study": mean_se(F[sel]), "watch_fwer": binomial(W[sel], ci=True)})
    out["by_k_bin"] = bins
    min_sites = int(cfg["minimum_data"]["min_sites"])
    reasons = stack.reason[:, j, :]
    n_site_studies = int(reasons.size)
    out["computability"] = {
        "mean_computed_sites": float(K.mean()),
        "mean_computed_sites_mc_se": mean_se(K)["mc_se"],
        "share_below_min_sites": binomial(K < min_sites),
        "not_computed_reasons": {r: float(np.count_nonzero(reasons == k) / n_site_studies)
                                 for k, r in enumerate(REASONS)},
        "not_computed_reason_counts": {r: int(np.count_nonzero(reasons == k)) for k, r in enumerate(REASONS)},
        "n_site_studies": n_site_studies,
    }
    out["r"] = stack.R
    return out


def acceptance(blocks: Mapping[str, Mapping[str, Any]], th: ThresholdSet, cfg: Mapping[str, Any]) -> dict[str, Any]:
    """REQ-023 (§12.1) on unrounded values: per indicator, Look per-site and Watch family-wise rates against
    nominal + 2 sqrt(SE_cal^2 + SE_val^2) (pass, conservative below nominal, or failure), and the size calibration
    (every E_s tertile's Look rate within nominal +/- SIZE_TOLERANCE)."""
    a_look, a_watch = cb.alphas(cfg)
    out: dict[str, Any] = {"nominal": {ind.LOOK: a_look, ind.WATCH: a_watch},
                           "rule": "rate <= nominal + 2 * sqrt(SE_cal^2 + SE_val^2), unrounded; below nominal is "
                                   "conservative, not a failure (docs/11 §12.1)",
                           "size_rule": f"every E_s tertile's Look rate within nominal +/- {SIZE_TOLERANCE}",
                           "by_indicator": {}}
    for name in INDICATORS:
        b = blocks[name]
        res: dict[str, Any] = {}
        for tier, key, nominal in ((ind.LOOK, "look_per_site", a_look), (ind.WATCH, "watch_fwer", a_watch)):
            rate, se_val = b[key]["rate"], b[key]["mc_se"]
            se_cal = th.achieved_se(name, tier)
            if rate is None or se_val is None or se_cal is None:
                res[tier] = {"rate": rate, "status": "not_computed"}
                continue
            bound = nominal + ACCEPT_SE_MULTIPLIER * math.sqrt(se_cal * se_cal + se_val * se_val)
            status = "failure" if rate > bound else ("conservative" if rate < nominal else "pass")
            res[tier] = {"rate": rate, "se_cal": se_cal, "se_val": se_val, "bound": bound, "status": status}
        tert = [t["rate"] for t in b.get("look_per_site_by_e_tertile", [])]
        lo, hi = a_look - SIZE_TOLERANCE, a_look + SIZE_TOLERANCE
        size_ok = bool(tert) and all(t is not None and lo <= t <= hi for t in tert)
        res["size_calibration"] = {"tertile_rates": tert, "within": [lo, hi],
                                   "status": "pass" if size_ok else "failure"}
        out["by_indicator"][name] = res
    d = out["by_indicator"][ind.DISCORDANCE]
    statuses = [d[ind.LOOK]["status"], d[ind.WATCH]["status"]]
    if "failure" in statuses:
        out["status"] = "failure"
    elif "not_computed" in statuses:
        out["status"] = "not_computed"
    elif all(x == "conservative" for x in statuses):
        out["status"] = "conservative"
    else:
        out["status"] = "pass"
    out["status_note"] = "discordance (primary); every indicator is in by_indicator"
    out["size_calibration_status"] = d["size_calibration"]["status"]
    return out


# ---- §12.2 power, §12.4 head-to-head ------------------------------------------------------------------------------------


def planted_flags(stacks: Sequence[Stack], th: ThresholdSet, label_code: int
                  ) -> list[tuple[dict[str, np.ndarray], np.ndarray]]:
    """Per f: ({tier: [R, n_ind] flagged at the planted site}, [R, n_ind] planted site computed)."""
    out = []
    for st in stacks:
        site = st.role == label_code
        if not np.all(site.sum(axis=1) == 1):
            raise RuntimeError("a power replicate must have exactly one planted site")
        col = np.argmax(site, axis=1)
        rows = np.arange(st.R)
        fl = st.flags(th)
        out.append(({t: fl[t][rows, :, col] for t in TIERS}, st.computed[rows, :, col]))
    return out


def power_rows(stacks: Sequence[Stack], fs: Sequence[float], th: ThresholdSet, label_code: int,
               design: sim.Design, *, exact_patients: bool, design_row: bool, cell: int,
               null_rates: Mapping[str, Mapping[str, float | None]], planning: Mapping[float, Mapping[str, float]] | None,
               gross_f: float | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """§12.2 power rows (both tiers, every indicator) and §12.4 paired head-to-head rows for one design."""
    rows, h2h = [], []
    pps: Any = design.patients_per_site[0] if exact_patients else list(design.patients_per_site)
    dj = INDICATORS.index(ind.DISCORDANCE)
    for f, (flags, comp) in zip(fs, planted_flags(stacks, th, label_code), strict=True):
        R = comp.shape[0]
        for j, name in enumerate(INDICATORS):
            for tier in TIERS:
                hit = flags[tier][:, j]
                b = binomial(hit)
                row = {"indicator": name, "tier": tier, "design_row": design_row, "cell": cell,
                       "n_sites": design.n_sites, "patients_per_site": pps, "mu": design.mu, "f": float(f),
                       "power": b["rate"], "mc_se": b["mc_se"], "reps": R, "p_computed": float(comp[:, j].mean()),
                       "null_rate_achieved": null_rates.get(name, {}).get(tier),
                       "threshold_never_assigned": th.never(j, tier)}
                if design_row:
                    row["thresholds"] = "sap-v1"
                    # the gross-f discordance row only, next to its planning value (§12.2; planning only, not a result)
                    plan_p = (planning or {}).get(float(f), {}).get(tier)
                    row["planning_power"] = plan_p if (name == ind.DISCORDANCE and gross_f is not None
                                                       and float(f) == gross_f) else None
                    if row["planning_power"] is not None:
                        row["planning_label"] = "planning (simplified) vs final"
                rows.append(row)
        for j, name in enumerate(INDICATORS):
            if j == dj:
                continue
            for tier in TIERS:
                d = flags[tier][:, dj].astype(float) - flags[tier][:, j].astype(float)
                ms = mean_se(d)
                h2h.append({"comparator": name, "tier": tier, "design_row": design_row, "cell": cell,
                            "n_sites": design.n_sites, "patients_per_site": pps, "mu": design.mu, "f": float(f),
                            "power_diff": ms["rate"], "paired_mc_se": ms["mc_se"], "reps": R,
                            "power_discordance": float(flags[tier][:, dj].mean()),
                            "power_comparator": float(flags[tier][:, j].mean()),
                            "comparator_null_rate_achieved": null_rates.get(name, {}).get(tier),
                            "comparator_never_assigned": th.never(j, tier),
                            "discordance_never_assigned": th.never(dj, tier)})
    return rows, h2h


def achieved_rates(th: ThresholdSet) -> dict[str, dict[str, float | None]]:
    return {name: {tier: th.achieved_rate(name, tier) for tier in TIERS} for name in INDICATORS}


# ---- §12.3 full planted mix -----------------------------------------------------------------------------------------------


def full_mix_block(stack: Stack, th: ThresholdSet, params: Mapping[str, Any], *, detail: bool = True
                   ) -> dict[str, Any]:
    labels = _labels(params)
    planted = params["planted"]
    positive = {str(s["label"]) for s in planted.values() if any(k in s for k in sim.LOSS_KEYS)}
    pos_codes = np.array([lab in positive for lab in labels])
    is_pos = pos_codes[stack.role]
    fl = stack.flags(th)
    detection, false_flags, per_study, nc_rows = [], [], [], []
    expected_reason = {str(planted["low_coverage"]["label"]): bvmatch.LOW_COVERAGE,
                       str(planted["small_site"]["label"]): bvmatch.INSUFFICIENT_PATIENTS}
    for j, name in enumerate(INDICATORS):
        for tier in TIERS:
            f = fl[tier][:, j, :]
            for code, lab in enumerate(labels):
                m = stack.role == code
                n_per = m.sum(axis=1)
                if not n_per.any():
                    continue
                hits = (f & m).sum(axis=1)
                if np.all(n_per == 1):
                    b = binomial(hits.astype(bool))
                    row = {"rate": b["rate"], "mc_se": b["mc_se"]}
                else:
                    cr = clustered_rate(hits, n_per)
                    row = {"rate": cr["rate"], "mc_se": cr["mc_se"]}
                row = {"indicator": name, "tier": tier, "label": lab, **row,
                       "n_sites": int(n_per.sum()), "p_computed": float(stack.computed[:, j, :][m].mean())}
                (detection if lab in positive else false_flags).append(row)
            if not detail:
                continue
            flags = f.sum(axis=1)
            tp = (f & is_pos).sum(axis=1)
            fp = (f & ~is_pos).sum(axis=1)
            per_study.append({"indicator": name, "tier": tier, "mean_flags": mean_se(flags),
                              "mean_true_flags": mean_se(tp), "mean_false_flags": mean_se(fp),
                              "fdr": mean_se(fp / np.maximum(flags, 1))})
        if detail:
            for lab, reason in expected_reason.items():
                m = stack.role == labels.index(lab)
                if not m.any():
                    continue
                rs = stack.reason[:, j, :][m]
                nc = binomial(rs >= 0)
                ok = binomial(rs == REASONS.index(reason))
                nc_rows.append({"indicator": name, "label": lab, "expected_reason": reason,
                                "rate": ok["rate"], "mc_se": ok["mc_se"],
                                "not_computed_any_reason": {"rate": nc["rate"], "mc_se": nc["mc_se"]}})
    out: dict[str, Any] = {"r": stack.R, "note": FULL_MIX_NOTE, "detection": detection, "false_flags": false_flags}
    if detail:
        out["not_computed_correct"] = nc_rows
        out["per_study"] = per_study
    return out


def full_mix_h2h(stack: Stack, th: ThresholdSet, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """§12.4 full-mix rows: per label, the paired per-study difference (discordance - comparator) of the share of
    the label's sites flagged, with paired MC SE."""
    labels = _labels(params)
    positive = {str(s["label"]) for s in params["planted"].values() if any(k in s for k in sim.LOSS_KEYS)}
    fl = stack.flags(th)
    dj = INDICATORS.index(ind.DISCORDANCE)
    out = []
    for j, name in enumerate(INDICATORS):
        if j == dj:
            continue
        for tier in TIERS:
            for code, lab in enumerate(labels):
                m = stack.role == code
                n_per = m.sum(axis=1)
                if not n_per.any():
                    continue
                denom = np.maximum(n_per, 1)
                share_d = (fl[tier][:, dj, :] & m).sum(axis=1) / denom
                share_c = (fl[tier][:, j, :] & m).sum(axis=1) / denom
                ms = mean_se(share_d - share_c)
                out.append({"comparator": name, "tier": tier, "label": lab,
                            "kind": "detection" if lab in positive else "false_flag",
                            "detection_diff": ms["rate"], "paired_mc_se": ms["mc_se"], "note": FULL_MIX_NOTE})
    return out


def equity_share(recs: Sequence[dict[str, Any]], kind: str, field_name: str, b: int) -> dict[str, Any]:
    vals = [r["equity"][kind] for r in recs if "equity" in r and kind in r["equity"]]
    used = [v for v in vals if v["computed"]]
    out = binomial(np.array([v[field_name] for v in used], dtype=bool))
    return {"rate": out["rate"], "mc_se": out["mc_se"], "n_used": len(used), "n_not_computed": len(vals) - len(used),
            "b": b}


# ---- the committed study under each scenario (§12.6 (i), (iv)) -----------------------------------------------------------


def tier_names(rec: Mapping[str, Any], th: ThresholdSet) -> dict[str, list[str]]:
    st = Stack.of([rec])
    fl = st.flags(th)
    out = {}
    for j, name in enumerate(INDICATORS):
        row = []
        for k in range(st.stat.shape[2]):
            if st.reason[0, j, k] >= 0:
                row.append(ind.NOT_COMPUTED)
            elif fl[ind.WATCH][0, j, k]:
                row.append(ind.WATCH)
            elif fl[ind.LOOK][0, j, k]:
                row.append(ind.LOOK)
            else:
                row.append(ind.NONE)
        out[name] = row
    return out


def committed_block(rec: Mapping[str, Any], base: Mapping[str, Any], th: ThresholdSet, labels: Sequence[str],
                    match_window: bool) -> dict[str, Any]:
    tiers, base_tiers = tier_names(rec, th), tier_names(base, th)
    sites = rec["site_ids"]
    roles = [labels[c] for c in rec["role"].tolist()]
    by_ind = {}
    for name in INDICATORS:
        t = tiers[name]
        by_ind[name] = {
            ind.WATCH: [s for s, x in zip(sites, t, strict=True) if x == ind.WATCH],
            ind.LOOK: [s for s, x in zip(sites, t, strict=True) if x == ind.LOOK],
            "n_sites_tier_changed": sum(a != b for a, b in zip(t, base_tiers[name], strict=True)),
        }
    out: dict[str, Any] = {
        "committed_tiers": {k: by_ind[ind.DISCORDANCE][k] for k in (ind.WATCH, ind.LOOK)},
        "committed_by_indicator": by_ind,
        "committed_sites": [{"site_id": s, "label": roles[k], "tiers": {n: tiers[n][k] for n in INDICATORS},
                             "tiers_base": {n: base_tiers[n][k] for n in INDICATORS}} for k, s in enumerate(sites)],
        "matched_status_changes": None,
    }
    if match_window:
        before = dict(base["episodes"])
        after = dict(rec["episodes"])
        if set(before) != set(after):
            raise RuntimeError("a match-window scenario changed the committed study's episodes, not only matches")
        oe = episodes.OE_STATUSES
        m2u = sum(before[e] == episodes.MATCHED and after[e] != episodes.MATCHED for e in before)
        u2m = sum(before[e] != episodes.MATCHED and after[e] == episodes.MATCHED for e in before)
        out["matched_status_changes"] = m2u + u2m
        out["status_changes_detail"] = {
            "matched_to_other": m2u, "other_to_matched": u2m,
            "any_status_change": sum(before[e] != after[e] for e in before),
            "n_episodes": len(before), "n_matched_or_unmatched_base": sum(before[e] in oe for e in before)}
    return out


# ---- the eval study confusion (from run.py's answer_key.json) ---------------------------------------------------------------


def eval_study_block(seed_label: str, seed: int) -> dict[str, Any] | None:
    """§12.7: the committed study's confusion, read from monitoring/out/answer_key.json (written by run.py before
    the full validation run) and labeled illustration only; null with a note otherwise (dev seed, or not yet run)."""
    if seed_label != "eval" or not ANSWER_KEY_FILE.exists():
        return None
    raw = ANSWER_KEY_FILE.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("eval_seed") not in (None, seed):
        raise ValidationError(f"{ANSWER_KEY_FILE} is from evaluation seed {doc.get('eval_seed')}, not {seed}")
    return {"note": EVAL_STUDY_NOTE, "source": "monitoring/out/answer_key.json",
            "source_sha256": hashlib.sha256(raw).hexdigest(), **eval_study_lists(doc)}


def eval_study_lists(doc: Mapping[str, Any]) -> dict[str, Any]:
    """``confusion`` as run.py wrote it, and the caught / missed positives (at Look, with each site's tier) and the
    must-be-grey sites as lists (docs/03 §5.3)."""
    labels = {row["site_id"]: row["label"] for row in doc.get("answer_key", [])}
    caught, missed, false_flags = [], [], []
    for name, d in (doc.get("flags") or {}).items():
        look, watch = d.get(ind.LOOK, {}), d.get(ind.WATCH, {})
        nc = set(d.get("not_computed_positives", []))
        for sid in look.get("caught", []):
            tier = ind.WATCH if sid in watch.get("caught", []) else ind.LOOK
            caught.append({"indicator": name, "site_id": sid, "label": labels.get(sid), "tier": tier})
        for sid in look.get("missed", []):
            missed.append({"indicator": name, "site_id": sid, "label": labels.get(sid),
                           "tier": ind.NOT_COMPUTED if sid in nc else ind.NONE})
        for sid in look.get("false_flags", []):
            tier = ind.WATCH if sid in watch.get("false_flags", []) else ind.LOOK
            false_flags.append({"indicator": name, "site_id": sid, "label": labels.get(sid), "tier": tier})
    not_computed = [{"site_id": g["site_id"], "label": g["label"],
                     "reason": (g.get("indicators", {}).get(ind.DISCORDANCE) or {}).get("not_computed_reason"),
                     "indicators": g.get("indicators")} for g in doc.get("must_be_grey", [])]
    return {"confusion": doc.get("confusion"), "caught": caught, "missed": missed, "false_flags": false_flags,
            "not_computed": not_computed}


def planning_values() -> tuple[dict[str, Any], dict[float, dict[str, float]]]:
    """planning_grid.json gate outcome and P2 planning power (planning only, never a result)."""
    doc = json.loads(PLANNING_GRID_FILE.read_text(encoding="utf-8"))
    chosen = doc["chosen"]
    power = {float(r["f"]): {ind.LOOK: float(r["look_power"]), ind.WATCH: float(r["watch_power"])}
             for r in doc["p2"]["power"]["rows"]}
    return chosen, power


# ---- assembling the outputs ------------------------------------------------------------------------------------------------


def summarize(sets: Sequence[SetSpec], jobs: Sequence[Job], results: Sequence[tuple[list[dict[str, Any]], float]],
              th: ThresholdSet, params: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Every §12 block from the per-replicate records (no simulation here)."""
    labels = _labels(params)
    gross_code = labels.index(str(params["planted"]["gross"]["label"]))
    recs: dict[str, list[list[dict[str, Any]]]] = {}
    for job, (r, _) in zip(jobs, results, strict=True):
        recs.setdefault(job.set_id, []).append(r)

    def single(set_id: str) -> list[dict[str, Any]]:
        return [r[0] for r in recs[set_id]]

    def per_f(set_id: str, n_f: int) -> list[Stack]:
        return [Stack.of([r[k] for r in recs[set_id]]) for k in range(n_f)]

    fs = tuple(float(f) for f in params["grid"]["f"])
    by_id = {s.set_id: s for s in sets}
    chosen, planning = planning_values()

    # §12.1
    null_recs = single("null_validation")
    null_stack = Stack.of(null_recs)
    blocks = {name: null_block(null_stack, th, cfg, j) for j, name in enumerate(INDICATORS)}
    null = {**blocks[ind.DISCORDANCE], "comparators": {n: blocks[n] for n in COMPARATORS},
            "thresholds": "sap-v1", "acceptance": acceptance(blocks, th, cfg)}

    # §12.2 grid and the sap-v1 design row, §12.4 head-to-head
    power, h2h_grid, designs = [], [], []
    for row in params["cell_index"]["grid"]:
        cell = int(row["cell"])
        cals = calibrate_set(single(f"grid_null:{cell}"), cfg)
        gth = thresholds_from_calibration(cals, f"per-design calibration, cell {cell}")
        rates = achieved_rates(gth)
        p_rows, h_rows = power_rows(per_f(f"grid_power:{cell}", len(fs)), fs, gth, gross_code,
                                    by_id[f"grid_power:{cell}"].design, exact_patients=True, design_row=False,
                                    cell=cell, null_rates=rates, planning=None)
        power += p_rows
        h2h_grid += h_rows
        designs.append({"cell": cell, **by_id[f"grid_null:{cell}"].design.to_dict(),
                        "r_null": cals[ind.DISCORDANCE].r,
                        "thresholds": {n: cals[n].served() for n in INDICATORS},
                        "never_assigned": {n: {t: gth.never(j, t) for t in TIERS} for j, n in enumerate(INDICATORS)},
                        "achieved": {n: cals[n].achieved() for n in INDICATORS}})
    p_rows, h_rows = power_rows(per_f("design_row", len(fs)), fs, th, gross_code, by_id["design_row"].design,
                                exact_patients=False, design_row=True, cell=by_id["design_row"].cell,
                                null_rates=achieved_rates(th), planning=planning,
                                gross_f=float(params["planted"]["gross"]["f"]))
    power += p_rows
    h2h_grid += h_rows

    # §12.3 full mix with equity, §12.4 full-mix rows
    mix_recs = single("full_mix")
    mix_stack = Stack.of(mix_recs)
    b = int(params["equity_validation"]["b"])
    full_mix = full_mix_block(mix_stack, th, params)
    full_mix["equity"] = {
        "b": b,
        "resampling_unit": "patients with >= 1 evaluable non-paged episode at each included site",
        "language_ci_covers_1_null": equity_share(null_recs, LANGUAGE, "covers_1", b),
        "pace_ci_excludes_1_null": equity_share(null_recs, PACE, "excludes_1", b),
        "pace_ci_excludes_1_full_mix": equity_share(mix_recs, PACE, "excludes_1", b),
        "null_studies": by_id["null_validation"].equity_first,
    }
    head_to_head = {"full_mix_note": FULL_MIX_NOTE, "primary": "grid (one planted site, no traps, honest case mix)",
                    "grid": h2h_grid, "full_mix": full_mix_h2h(mix_stack, th, params)}

    # §12.5 failure case
    fc = params["failure_case"]
    fa_cals = calibrate_set(single("failure_a_null"), cfg)
    fa_th = thresholds_from_calibration(fa_cals, "failure-case calibration (cell 27)")
    fa_rows, fa_h2h = power_rows(per_f("failure_a_power", len(fs)), fs, fa_th, gross_code, by_id["design_row"].design,
                                 exact_patients=False, design_row=False, cell=by_id["failure_a_power"].cell,
                                 null_rates=achieved_rates(fa_th), planning=None)
    fb_stack = Stack.of(single("failure_b_null"))
    failure_case = {
        "between_site_sd_logit": float(fc["between_site_sd_logit"]), "casemix_sd_log": float(fc["casemix_sd_log"]),
        "a": {"r_null": len(recs["failure_a_null"]), "reps": len(recs["failure_a_power"]),
              "thresholds": {n: fa_cals[n].served() for n in INDICATORS},
              "achieved": {n: fa_cals[n].achieved() for n in INDICATORS},
              "power": fa_rows, "head_to_head": fa_h2h},
        "b": {"r_null": fb_stack.R, "thresholds": "sap-v1",
              "null": [null_block(fb_stack, th, cfg, j, full=False) for j in range(len(INDICATORS))]},
    }

    # §12.6 sensitivity
    committed = {job.set_id.split(":", 1)[1]: r[0] for job, (r, _) in zip(jobs, results, strict=True)
                 if job.set_id.startswith("committed:")}
    base = committed["base"]
    sensitivity = []
    for sid in params["cell_index"]["sensitivity"]:
        n_stack = Stack.of(single(f"sensitivity_null:{sid}"))
        m_stack = Stack.of(single(f"sensitivity_mix:{sid}"))
        nb = {name: null_block(n_stack, th, cfg, j, full=False) for j, name in enumerate(INDICATORS)}
        mix = full_mix_block(m_stack, th, params, detail=False)
        cblock = committed_block(committed[sid], base, th, labels, sid in MATCH_WINDOW_SCENARIOS)
        sensitivity.append({
            "id": sid, "cell": by_id[f"sensitivity_null:{sid}"].cell, "change": SCENARIO_CHANGE.get(sid, sid),
            "scenario": dict(params["sensitivity"]["scenarios"][sid]),
            "committed_tiers": cblock["committed_tiers"],
            "null": {k: nb[ind.DISCORDANCE][k] for k in ("look_per_site", "look_per_study", "watch_fwer")},
            "null_by_indicator": nb, "r_null": n_stack.R,
            "full_mix_detection": mix["detection"], "full_mix_false_flags": mix["false_flags"], "r_full_mix": m_stack.R,
            "matched_status_changes": cblock["matched_status_changes"],
            **({"status_changes_detail": cblock["status_changes_detail"]} if "status_changes_detail" in cblock else {}),
            "committed_by_indicator": cblock["committed_by_indicator"],
            "committed_sites": cblock["committed_sites"],
        })

    design = sim.sap_design(params)
    return {
        "design": {**design.to_dict(), "gross_f": float(params["planted"]["gross"]["f"]),
                   "gate": "shortfall" if "shortfall" in (chosen.get("p1"), chosen.get("p2")) else "passed",
                   "gate_p1": chosen.get("p1"), "gate_p2": chosen.get("p2"),
                   "planning_note": "planning only, not a result (monitoring/planning/planning_grid.json)"},
        "null": null,
        "power": power,
        "power_designs": designs,
        "full_mix": full_mix,
        "head_to_head": head_to_head,
        "failure_case": failure_case,
        "sensitivity": sensitivity,
        "base_tiers_committed": tier_names(base, th),
    }


def documents(blocks: Mapping[str, Any], prov: Mapping[str, Any], th: ThresholdSet, th_meta: Mapping[str, Any],
              hashes: Mapping[str, str], counts: Mapping[str, int], seed_label: str, scale: float,
              eval_study: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    head = {"_about": ABOUT if seed_label == "eval" else ABOUT_DEV, "data_origin": DATA_ORIGIN, **prov,
            "scale": scale}
    th_block = {"source": th.source, **th_meta,
                "served": {n: {t: (None if th.never(j, t) else
                                   (-float((th.look if t == ind.LOOK else th.watch)[j]) + 0.0
                                    if ind.FLAG_WHEN[n] == ind.AT_OR_ABOVE else
                                    float((th.look if t == ind.LOOK else th.watch)[j]))) for t in TIERS}
                           for j, n in enumerate(INDICATORS)},
                "achieved": th.achieved}
    power_rows_summary = blocks["power"]
    summary = {
        **head,
        "design": blocks["design"],
        "thresholds": th_block,
        "null": blocks["null"],
        "power": power_rows_summary,
        "full_mix": blocks["full_mix"],
        "head_to_head": blocks["head_to_head"],
        "failure_case": blocks["failure_case"],
        "sensitivity": [{k: v for k, v in s.items() if k != "committed_sites"} for s in blocks["sensitivity"]],
        "eval_study": eval_study,
        "simaerep_fixture": sc.fixture_pvalue_check(),
        "replicates": dict(counts),
        "quick_hashes": dict(hashes),
    }
    if eval_study is None:
        summary["eval_study_note"] = ("null: monitoring/out/answer_key.json (run.py, evaluation seed) was not available "
                                      "to this run; " + EVAL_STUDY_NOTE)
    return {
        SUMMARY: summary,
        NULL_RATE: {**head, "thresholds": th_block, "null": blocks["null"]},
        POWER_GRID: {**head, "thresholds": th_block, "power": power_rows_summary, "designs": blocks["power_designs"],
                     "head_to_head": blocks["head_to_head"]},
        FAILURE_CASE: {**head, "failure_case": blocks["failure_case"]},
        SENSITIVITY: {**head, "thresholds": th_block, "base_tiers_committed": blocks["base_tiers_committed"],
                      "sensitivity": blocks["sensitivity"]},
    }


def _dumps(doc: Any) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


# ---- command line ------------------------------------------------------------------------------------------------------------


def _inside(path: Path, rel: str) -> bool:
    target = (REPO_ROOT / rel).resolve()
    p = path.resolve()
    return p == target or target in p.parents


def resolve_thresholds(seed_label: str, seed: int, path: Path | None, plan: Plan, workers: int,
                       params: Mapping[str, Any]) -> tuple[ThresholdSet, dict[str, Any]]:
    """The sap-v1 thresholds: evaluation seed -> the committed thresholds.json (checked against the seed and tag);
    dev -> ``--thresholds`` or an in-process dev calibration of scale x r_null null studies (stream 1)."""
    if seed_label == "eval":
        if path is not None and path.resolve() != THRESHOLDS_FILE.resolve():
            raise ValidationError("the evaluation seed uses the committed monitoring/out/thresholds.json only")
        if not THRESHOLDS_FILE.exists():
            raise ValidationError("monitoring/out/thresholds.json is missing: run calibrate.py (evaluation seed) first")
        raw = THRESHOLDS_FILE.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if doc.get("eval_seed") != seed or doc.get("sap_tag_commit") != bvseed.sap_tag_commit():
            raise ValidationError("monitoring/out/thresholds.json is not from this evaluation seed and sap-v1 tag")
        return thresholds_from_doc(doc, "monitoring/out/thresholds.json"), {
            "file": "monitoring/out/thresholds.json", "sha256": hashlib.sha256(raw).hexdigest(),
            "r_null": doc.get("r_null")}
    if path is not None:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if doc.get("seed_label") == "eval" or doc.get("eval_seed") is not None:
            raise ValidationError("--seed dev never reads evaluation-seed thresholds")
        return thresholds_from_doc(doc, str(path)), {"file": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                                                     "r_null": doc.get("r_null")}
    r = plan.full(int(params["calibration"]["r_null"]))
    cal = cb.calibrate(seed, r, seed_label="dev", workers=workers, params=params)
    doc, _ = cb.documents(cal, {"seed_label": "dev", "seed": seed})
    return thresholds_from_doc(doc, f"in-process dev calibration (stream 1, r_null {r})"), {
        "file": None, "sha256": None, "r_null": r}


def resolve_run(args: argparse.Namespace, params: Mapping[str, Any]) -> tuple[int, Path | None]:
    if args.seed == "eval":
        if args.scale != 1:
            raise ValidationError("the evaluation seed always runs every replicate (--scale 1)")
        if args.out is not None and args.out.resolve() != OUT_DIR.resolve():
            raise ValidationError(f"the evaluation seed writes only to {OUT_REL}/ (committed, logged)")
        if args.thresholds is not None and args.thresholds.resolve() != THRESHOLDS_FILE.resolve():
            raise ValidationError("the evaluation seed uses the committed monitoring/out/thresholds.json only")
        if not args.quick:
            bvseed.assert_committed_tree(ignore=[f"{OUT_REL}/{f}" for f in OUTPUT_FILES] + [bvseed.RUN_LOG_REL])
        return bvseed.eval_seed(), OUT_DIR
    if args.seed != "dev":
        raise ValidationError(f"unknown seed label {args.seed!r} (dev or eval)")
    if not 0 < args.scale <= 1:
        raise ValidationError("--scale must be in (0, 1]")
    if args.out is None and not args.quick:  # --quick writes nothing
        raise ValidationError("--seed dev needs --out DIR, a scratch directory (development output is never committed)")
    if args.check and args.out is None and args.summary is None:
        raise ValidationError("--seed dev --quick --check needs --summary PATH or --out DIR (its summary.json)")
    for p in (args.out, args.summary):
        for rel in COMMITTED_DIRS:
            if p is not None and _inside(p, rel):
                raise ValidationError(f"--seed dev never reads or writes {rel}/ (docs/11 §1.3); use a scratch directory")
    return bvseed.dev_seed(), args.out


def _print(msg: str) -> None:
    print(msg, flush=True)


def projection(sets: Sequence[SetSpec], jobs: Sequence[Job], results: Sequence[tuple[list[dict[str, Any]], float]],
               params: Mapping[str, Any], wall: float, workers: int) -> dict[str, Any]:
    """Projected full evaluation runtime from this run's CPU seconds per replicate key, per set kind."""
    full = Plan(1.0, False, params)
    cpu: dict[str, list[float]] = {}
    for job, (_, t) in zip(jobs, results, strict=True):
        cpu.setdefault(job.set_id.split(":")[0], []).append(t)
    n_full: dict[str, int] = {}
    for s in sets:
        n_full[s.set_id.split(":")[0]] = n_full.get(s.set_id.split(":")[0], 0) + full.count(
            s.n_nominal, validation_sized=s.validation_sized)
    n_full["committed"] = len(cpu.get("committed", []))
    total_cpu = sum(cpu_t for v in cpu.values() for cpu_t in v)
    eff = total_cpu / (wall * workers) if wall > 0 else 1.0
    proj_cpu = sum(n_full[k] * float(np.mean(v)) for k, v in cpu.items())
    return {"measured_wall_s": wall, "measured_cpu_s": total_cpu, "workers": workers, "parallel_efficiency": eff,
            "cpu_s_per_key": {k: float(np.mean(v)) for k, v in cpu.items()}, "full_keys": n_full,
            "projected_full_cpu_s": proj_cpu, "projected_full_wall_s": proj_cpu / (workers * max(eff, 1e-9))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bvsignal.validate",
                                 description="Site Signal operating characteristics (docs/11 §12). SIMULATED.")
    ap.add_argument("--seed", choices=["dev", "eval"], default="eval")
    ap.add_argument("--out", type=Path, default=None, help="output directory (dev: a scratch directory, required)")
    ap.add_argument("--scale", type=float, default=1.0, help="dev only: multiply every replicate count (>= 1 each)")
    ap.add_argument("--workers", type=int, default=None, help="worker processes (default all cores; results do not "
                                                              "depend on it)")
    ap.add_argument("--thresholds", type=Path, default=None, help="dev only: a dev thresholds.json (default: an "
                                                                  "in-process dev calibration)")
    ap.add_argument("--quick", action="store_true", help="only the quick replicates (first r_quick / reps_quick)")
    ap.add_argument("--check", action="store_true", help="with --quick: exit 1 unless quick_hashes equal summary.json")
    ap.add_argument("--summary", type=Path, default=None, help="summary.json for --check (default: <out>/summary.json)")
    ap.add_argument("--timing", action="store_true", help="print a runtime projection for the full evaluation run")
    args = ap.parse_args(argv)
    argv_used = sys.argv[1:] if argv is None else list(argv)
    if args.check and not args.quick:
        print("bvsignal.validate: --check needs --quick", file=sys.stderr)
        return 2
    workers = cb.default_workers() if args.workers is None else int(args.workers)
    try:
        ok, report = bvseed.check_frozen()
        if not ok:
            raise ValidationError("frozen inputs differ from params.yaml frozen_inputs and no docs/11 §17 row cites "
                                  "the new hash; refusing to validate:\n  " + "\n  ".join(report))
        model = sim.default_model()
        params, cfg = model.params, model.signal_rules
        seed, out = resolve_run(args, params)
        labels = _labels(params)
        plan = Plan(float(args.scale), bool(args.quick), params)
        sets, jobs = build_jobs(params, seed, plan)
        _print(f"bvsignal.validate: {args.seed} seed, {'quick, ' if args.quick else ''}scale {args.scale}, "
               f"{len(jobs)} replicate keys, {workers} workers ({DATA_ORIGIN})")
        if args.quick:
            t0 = time.perf_counter()
            results = run_jobs(jobs, workers, log=_print)
            hashes = quick_hashes(jobs, results, sets, plan, labels)
            _print(f"quick run: {time.perf_counter() - t0:.1f} s")
            for k, v in hashes.items():
                _print(f"  quick_hashes.{k} = {v}")
            if not args.check:
                return 0
            spath = args.summary or ((out or OUT_DIR) / SUMMARY)
            if not spath.exists():
                raise ValidationError(f"{spath} does not exist: nothing to check against")
            summary = json.loads(spath.read_text(encoding="utf-8"))
            if summary.get("scale") != args.scale or summary.get("seed") != seed:
                _print(f"  note: summary.json has seed {summary.get('seed')} scale {summary.get('scale')}; this run "
                       f"seed {seed} scale {args.scale}")
            want = summary.get("quick_hashes")
            _secondary(summary, jobs, results, cfg)
            if want != hashes:
                for k in sorted(set(want or {}) | set(hashes)):
                    mark = "ok" if (want or {}).get(k) == hashes.get(k) else "MISMATCH"
                    _print(f"  {mark:8s} {k}: summary {(want or {}).get(k)} vs quick {hashes.get(k)}")
                _print("quick check FAILED: per-replicate results differ from summary.json quick_hashes "
                       "(nondeterminism or a code change)")
                return 1
            _print("quick check passed: every quick_hashes entry equals summary.json")
            return 0
        th, th_meta = resolve_thresholds(args.seed, seed, args.thresholds, plan, workers, params)
        prov = cb.provenance(args.seed, seed)
        t0 = time.perf_counter()
        results = run_jobs(jobs, workers, log=_print)
        wall = time.perf_counter() - t0
        hashes = quick_hashes(jobs, results, sets, plan, labels)
        blocks = summarize(sets, jobs, results, th, params, cfg)
        counts = {s.set_id: plan.count(s.n_nominal, validation_sized=s.validation_sized) for s in sets}
        counts["committed"] = len(committed_jobs(params, seed))
        docs = documents(blocks, prov, th, th_meta, hashes, counts, args.seed, float(args.scale),
                         eval_study_block(args.seed, seed))
        assert out is not None
        out.mkdir(parents=True, exist_ok=True)
        paths = []
        for name in OUTPUT_FILES:
            p = out / name
            p.write_text(_dumps(docs[name]), encoding="utf-8")
            paths.append(p)
        if args.seed == "eval":
            bvseed.log_run(["python", "-m", "bvsignal.validate", *argv_used], paths)
    except (ValidationError, bvseed.SeedError) as e:
        print(f"bvsignal.validate: {e}", file=sys.stderr)
        return 2
    _report(docs[SUMMARY], wall, len(jobs))
    if args.timing:
        proj = projection(sets, jobs, results, params, wall, workers)
        _print(f"timing: {proj['measured_wall_s']:.1f} s wall, {proj['measured_cpu_s']:.0f} CPU-s on {workers} workers "
               f"(efficiency {proj['parallel_efficiency']:.2f}); projected full evaluation run "
               f"{proj['projected_full_cpu_s']:.0f} CPU-s, about {proj['projected_full_wall_s'] / 60:.1f} min wall "
               f"on {workers} workers")
        for k, v in proj["cpu_s_per_key"].items():
            _print(f"  {k:18s} {v * 1000:8.1f} CPU-ms per key x {proj['full_keys'][k]} keys")
    for p in paths:
        _print(f"wrote {p}")
    return 0


def _report(summary: Mapping[str, Any], wall: float, n_jobs: int) -> None:
    acc = summary["null"]["acceptance"]
    _print(f"validated {n_jobs} replicate keys in {wall:.1f} s ({DATA_ORIGIN}"
           + ("; DEVELOPMENT OUTPUT, not a result)" if summary.get("seed_label") == "dev" else ")"))
    for name, a in acc["by_indicator"].items():
        lk, wt = a[ind.LOOK], a[ind.WATCH]
        _print(f"  REQ-023 {name:17s} look {lk.get('rate')} <= {lk.get('bound')}: {lk['status']}; watch "
               f"{wt.get('rate')} <= {wt.get('bound')}: {wt['status']}; size calibration "
               f"{a['size_calibration']['status']}")
    _print(f"  REQ-023 acceptance (discordance): {acc['status']}; size calibration {acc['size_calibration_status']}")


def _secondary(summary: Mapping[str, Any], jobs: Sequence[Job], results: Sequence[tuple[list[dict[str, Any]], float]],
               cfg: Mapping[str, Any]) -> None:
    """Secondary line (not a gate): quick null rates at the summary's sap-v1 thresholds vs the committed rates."""
    try:
        th = thresholds_from_doc({**summary["thresholds"]["served"], "achieved": summary["thresholds"]["achieved"]},
                                 "summary.json")
        null_recs = [r[0] for job, (r, _) in zip(jobs, results, strict=True) if job.set_id == "null_validation"]
        st = Stack.of(null_recs)
        for j, name in enumerate(INDICATORS):
            q = null_block(st, th, cfg, j, full=False)
            c = summary["null"] if name == ind.DISCORDANCE else summary["null"]["comparators"][name]
            _print(f"  secondary (not a gate) {name}: quick look {q['look_per_site']['rate']} vs committed "
                   f"{c['look_per_site']['rate']}; quick watch {q['watch_fwer']['rate']} vs committed "
                   f"{c['watch_fwer']['rate']} ({st.R} quick null studies)")
    except (KeyError, TypeError, ValueError) as e:
        _print(f"  secondary line unavailable: {e}")


if __name__ == "__main__":
    sys.exit(main())
