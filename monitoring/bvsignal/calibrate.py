"""Look and Watch thresholds from the pre-registered null (docs/11-site-signal-sap.md §9.2-§9.3). SIMULATED.

Procedure (§9.2), on stream 1 (``params.yaml`` ``streams.calibration``), cell ``cell_index.none``, role
``roles.null_or_committed``, replicates i = 0 .. R - 1 with R = ``calibration.r_null``:

1. Simulate the null study of replicate i at the ``sap-v1`` design (every site honest, §9.1; ``simulate.py``).
2. Run the full analysis on it: episodes, matching and guards (``match.py``), then every indicator on the
   identical study (``indicators.py``): capture discordance (z*), the gsm-style rate KRI, simaerep classic
   (legacy) and the AE-to-report ratio ablation.
3. **Look**: pool the statistic over every computed site of every null study (M values) and take the per-site
   one-sided threshold at ``signal_rules.json`` ``tiers.look.per_site_alpha``.
4. **Watch**: per null study the minimum statistic over its computed sites (+inf when none is computed), and
   the threshold at ``tiers.watch.family_wise_alpha`` of those minima.
5. Discreteness rule (§9.3): c = max{t in S : (1/|S|) sum 1[x <= t] <= alpha}, -inf when no t qualifies (the
   tier is then never assigned, flagged ``never_assigned`` and written as null). Then c_watch := min(c_watch,
   c_look).
6. Write ``thresholds.json`` (thresholds per indicator and the ablation; achieved in-sample rates with their
   Monte Carlo SE, §12.8: the Look per-site rate with the cluster-aware SE, the Watch family-wise rate with the
   binomial SE; ``expected_false_look_flags_per_study``, the mean number of computed sites at Look or Watch per
   null study, for discordance at the top level and per indicator under ``achieved``) and ``null_pool.json``
   (the sorted discordance Look pool, for the §8.3 secondary calibrated p-values in report.md).

Every statistic is calibrated in the "lower is more extreme" orientation of §9.3. For simaerep classic that is
the SAP's ``prob`` = -(1 - BH-adjusted prob_low); ``thresholds.json`` serves simaerep's own orientation
(``prob`` = 1 - BH-adjusted prob_low, flagged at >=, docs/03 §5.1), i.e. the negated calibrated value, so the
tier of every site is the same either way. In-sample rates match the nominal ones by construction; the
evidence is the out-of-sample check of §12.1 (``validate.py``) and the null smoke test.

Replicates run in worker processes (``--workers``, default all cores). Each replicate is a pure function of its
key ``SeedSequence(seed, spawn_key=(stream, cell_index, role, i))`` and results are collected in replicate
order, so the output is byte-identical for any worker count. ``generated_at`` is the commit time of
``code_commit`` (docs/11 §15 rule 7), never the wall clock.

Command line::

    uv run --project monitoring python -m bvsignal.calibrate             # evaluation seed: monitoring/out/, run log
    uv run --project monitoring python -m bvsignal.calibrate --seed dev --out "$TMPDIR/cal" [--r N] [--workers N]

Both refuse when the ``params.yaml`` ``frozen_inputs`` hashes do not match the working tree and no docs/11 §17
row cites the new hash. The evaluation seed refuses a dirty tree, writes only to ``monitoring/out/``, always
uses R = ``r_null`` and appends one line to ``validation/site_signal/run_log.jsonl`` (docs/11 §1.2). The dev
seed refuses to write into ``monitoring/out/`` or ``validation/site_signal/``: development output goes to a
scratch directory and is never committed. No LLM anywhere on this path (CLAUDE.md rule 1). Thresholds mark
capture discordance: a reason to look, not a finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT
from bvsignal import indicators as ind
from bvsignal import match as bvmatch
from bvsignal import seed as bvseed
from bvsignal import simulate as sim

OUT_DIR = MONITORING_DIR / "out"
THRESHOLDS_NAME = "thresholds.json"
NULL_POOL_NAME = "null_pool.json"
COMMITTED_DIRS = ("monitoring/out", "validation/site_signal")
ABOUT = ("Look and Watch thresholds calibrated once from the pre-registered null (docs/11-site-signal-sap.md "
         "§9.2-9.3); every number is SIMULATED; a tier marks capture discordance, a reason to look, not a finding")
ABOUT_DEV = ("DEVELOPMENT OUTPUT (dev seed), not a result and never committed or quoted. " + ABOUT)
POOL_ABOUT = ("Discordance z* of every computed site of every null calibration study, sorted (docs/11 §9.2 "
              "Look pool), for the §8.3 secondary calibrated p-values in report.md only; SIMULATED")
SIMAEREP_NOTE = ("calibrated on the SAP statistic prob = -(1 - BH-adjusted prob_low) (docs/11 §10.2, lower is more "
                 "extreme); served as simaerep's prob = 1 - BH-adjusted prob_low, flagged at >= the negated "
                 "threshold (docs/03 §5.1), which gives every site the same tier")


class CalibrationError(RuntimeError):
    """A precondition of a calibration run is not met (message is user-facing)."""


# ---- one null replicate (runs in a worker process) -------------------------------------------------------------


@dataclass(frozen=True)
class NullJob:
    """One null study: key ``SeedSequence(seed, spawn_key=(stream, cell_index, role, i))`` at ``design``
    (None: the sap-v1 design) under ``scenario`` (None: the base null of §9.1)."""

    seed: int
    stream: int
    cell_index: int
    role: int
    i: int
    design: sim.Design | None = None
    scenario: sim.Scenario | None = None


def null_replicate(job: NullJob) -> tuple[int, dict[str, np.ndarray]]:
    """§9.2 steps 1-2 for one replicate: the calibration statistic of every computed site, per indicator.

    A simulated study has no load errors and no integrated mode, so any ``error`` reason is a bug and aborts the
    calibration instead of silently lowering the computed-site counts."""
    model = sim.default_model()
    key = bvseed.key(job.stream, job.cell_index, job.role, job.i, seed=job.seed)
    study = sim.simulate(key, model, design=job.design, roles="null", scenario=job.scenario)
    result = ind.analyze_study(study)
    for name, r in result.results.items():
        if bvmatch.ERROR in r.reasons:
            msg = next((e for e in r.errors if e), "unknown error")
            raise RuntimeError(f"replicate {job.i}: {name} failed on a simulated null study: {msg}")
    return job.i, result.null_values()


def run_null(jobs: Sequence[NullJob], workers: int | None = None) -> list[dict[str, np.ndarray]]:
    """Every job's statistics in job order; identical for any ``workers`` (1 runs in this process)."""
    w = default_workers() if workers is None else int(workers)
    if w < 1:
        raise ValueError(f"workers must be >= 1, got {w}")
    if w == 1 or len(jobs) <= 1:
        out = [null_replicate(j) for j in jobs]
    else:
        # imported by name so the worker function pickles as bvsignal.calibrate.null_replicate under `python -m`
        from bvsignal import calibrate as this

        chunk = max(1, len(jobs) // (w * 8))
        with ProcessPoolExecutor(max_workers=w, mp_context=mp.get_context("spawn")) as ex:
            out = list(ex.map(this.null_replicate, jobs, chunksize=chunk))
    if [i for i, _ in out] != [j.i for j in jobs]:
        raise RuntimeError("replicate results came back out of order")
    return [values for _, values in out]


def default_workers() -> int:
    return max(1, os.cpu_count() or 1)


# ---- thresholds (§9.2 steps 3-5, §9.3) ---------------------------------------------------------------------------


def calibrated_threshold(values: np.ndarray | Sequence[float], alpha: float) -> float:
    """§9.3: c = max{t in S : (1/|S|) sum_{x in S} 1[x <= t] <= alpha}; -inf if no t qualifies (or S is empty)."""
    s = np.sort(np.asarray(values, dtype=float))
    if np.isnan(s).any():
        raise ValueError("null statistics must not be NaN")
    if s.size == 0:
        return -math.inf
    ok = np.searchsorted(s, s, side="right") / s.size <= alpha
    return float(s[ok][-1]) if ok.any() else -math.inf


def _float_or_none(x: float) -> float | None:
    return None if not math.isfinite(x) else float(x)


@dataclass(frozen=True)
class IndicatorCalibration:
    """One indicator's calibrated thresholds (lower is more extreme) and achieved in-sample null rates."""

    indicator: str
    c_look: float
    c_watch: float
    c_watch_uncapped: float
    r: int
    n_pooled: int
    computed_per_study: np.ndarray  # K_r
    false_look_per_study: np.ndarray  # F_r: computed sites at Look or Watch
    watch_studies: np.ndarray  # bool per study: >= 1 site at Watch

    @property
    def look_rate(self) -> float:
        k = int(self.computed_per_study.sum())
        return float(self.false_look_per_study.sum() / k) if k else math.nan

    @property
    def look_mc_se(self) -> float:
        """§12.8 cluster-aware SE: (1/K_bar) sqrt(sum_r (F_r - alpha K_r)^2 / (R (R - 1)))."""
        R, kbar = self.r, float(self.computed_per_study.mean()) if self.r else math.nan
        if R < 2 or not kbar > 0:
            return math.nan
        resid = self.false_look_per_study - self.look_rate * self.computed_per_study
        return float(math.sqrt(float(np.sum(resid * resid)) / (R * (R - 1))) / kbar)

    @property
    def watch_rate(self) -> float:
        return float(self.watch_studies.mean()) if self.r else math.nan

    @property
    def watch_mc_se(self) -> float:
        p = self.watch_rate
        return float(math.sqrt(p * (1 - p) / self.r)) if self.r else math.nan

    @property
    def expected_false_look(self) -> float:
        return float(self.false_look_per_study.mean()) if self.r else math.nan

    @property
    def expected_false_look_mc_se(self) -> float:
        if self.r < 2:
            return math.nan
        return float(np.std(self.false_look_per_study, ddof=1) / math.sqrt(self.r))

    def served(self) -> dict[str, float | None]:
        """Thresholds in the served orientation (docs/03 §5.1); None = never assigned (calibrated -inf)."""
        flip = ind.FLAG_WHEN[self.indicator] == ind.AT_OR_ABOVE
        out: dict[str, float | None] = {}
        for k, c in ((ind.LOOK, self.c_look), (ind.WATCH, self.c_watch)):
            out[k] = None if not math.isfinite(c) else (-c + 0.0 if flip else c)
        return out

    def to_dict(self) -> dict[str, Any]:
        served = self.served()
        block: dict[str, Any] = {
            ind.LOOK: served[ind.LOOK],
            ind.WATCH: served[ind.WATCH],
            "never_assigned": {k: served[k] is None for k in ind.TIER_KEYS},
            "statistic": ind.STATISTIC[self.indicator],
            "flag_when": ind.FLAG_WHEN[self.indicator],
            "watch_capped_at_look": self.c_watch_uncapped > self.c_look,
        }
        if self.indicator == ind.SIMAEREP:
            block["calibration"] = SIMAEREP_NOTE
        return block

    def achieved(self) -> dict[str, Any]:
        return {
            ind.LOOK: {"rate": _float_or_none(self.look_rate), "mc_se": _float_or_none(self.look_mc_se)},
            ind.WATCH: {"rate": _float_or_none(self.watch_rate), "mc_se": _float_or_none(self.watch_mc_se)},
            "expected_false_look_flags_per_study": {"mean": _float_or_none(self.expected_false_look),
                                                    "mc_se": _float_or_none(self.expected_false_look_mc_se)},
            "n_pooled": self.n_pooled,
            "mean_computed_sites": _float_or_none(float(self.computed_per_study.mean()) if self.r else math.nan),
            "studies_without_computed_site": int(np.sum(self.computed_per_study == 0)),
        }


def calibrate_indicator(indicator: str, values: Sequence[np.ndarray], alpha_look: float,
                        alpha_watch: float) -> IndicatorCalibration:
    """§9.2 steps 3-5 for one indicator from the per-study statistics of its computed sites."""
    vals = [np.asarray(v, dtype=float) for v in values]
    R = len(vals)
    K = np.array([v.size for v in vals], dtype=np.int64)
    pooled = np.concatenate(vals) if vals else np.empty(0)
    minima = np.array([v.min() if v.size else math.inf for v in vals], dtype=float)
    c_look = calibrated_threshold(pooled, alpha_look)
    c_watch_raw = calibrated_threshold(minima, alpha_watch)
    c_watch = min(c_watch_raw, c_look)
    F = np.array([int(np.count_nonzero(v <= c_look)) for v in vals], dtype=np.int64)
    return IndicatorCalibration(indicator=indicator, c_look=c_look, c_watch=c_watch, c_watch_uncapped=c_watch_raw,
                                r=R, n_pooled=int(pooled.size), computed_per_study=K, false_look_per_study=F,
                                watch_studies=minima <= c_watch)


def alphas(cfg: Mapping[str, Any]) -> tuple[float, float]:
    """Nominal per-site Look and family-wise Watch rates from ``signal_rules.json`` ``tiers``."""
    t = cfg["tiers"]
    return float(t["look"]["per_site_alpha"]), float(t["watch"]["family_wise_alpha"])


@dataclass(frozen=True)
class Calibration:
    """Thresholds of every indicator from one set of null studies (the identical studies for all of them)."""

    seed_label: str
    seed: int
    stream: int
    cell_index: int
    role: int
    r: int
    design: sim.Design
    alpha_look: float
    alpha_watch: float
    indicators: dict[str, IndicatorCalibration]
    discordance_pool: np.ndarray  # sorted Look pool of discordance z*

    def thresholds(self) -> ind.Thresholds:
        """{indicator: {look, watch}} in the served orientation, as indicators.py reads them."""
        return {name: c.served() for name, c in self.indicators.items()}


def calibrate(seed: int, r: int, *, seed_label: str = "dev", stream: int | None = None, cell_index: int | None = None,
              role: int | None = None, design: sim.Design | None = None, scenario: sim.Scenario | None = None,
              workers: int | None = None, params: Mapping[str, Any] | None = None,
              cfg: Mapping[str, Any] | None = None) -> Calibration:
    """§9.2 on ``r`` null studies; defaults are the committed calibration's keys (stream 1, no cell, role 0) and
    the sap-v1 design. ``validate.py`` reuses it for per-design and failure-case calibration (§12.2, §12.5)."""
    model = sim.default_model()
    params = model.params if params is None else params
    cfg = model.signal_rules if cfg is None else cfg
    if int(r) != r or r < 1:
        raise ValueError(f"r must be a positive integer, got {r!r}")
    stream = int(params["streams"]["calibration"]) if stream is None else int(stream)
    cell_index = int(params["cell_index"]["none"]) if cell_index is None else int(cell_index)
    role = int(params["roles"]["null_or_committed"]) if role is None else int(role)
    jobs = [NullJob(int(seed), stream, cell_index, role, i, design, scenario) for i in range(int(r))]
    per_study = run_null(jobs, workers)
    a_look, a_watch = alphas(cfg)
    cals = {name: calibrate_indicator(name, [s[name] for s in per_study], a_look, a_watch) for name in ind.INDICATORS}
    pool = np.sort(np.concatenate([s[ind.DISCORDANCE] for s in per_study]))
    return Calibration(seed_label=seed_label, seed=int(seed), stream=stream, cell_index=cell_index, role=role,
                       r=int(r), design=model.design if design is None else design, alpha_look=a_look,
                       alpha_watch=a_watch, indicators=cals, discordance_pool=pool)


# ---- output -------------------------------------------------------------------------------------------------------


def _optional(fn: Any) -> Any:
    try:
        return fn()
    except bvseed.SeedError:
        return None


def provenance(seed_label: str, seed: int) -> dict[str, Any]:
    """docs/11 §9.2 step 6, §15 rule 7: tag commit, seed, code commit and its time, numpy and scipy versions."""
    if seed_label == "eval":
        sap, code, when = bvseed.sap_tag_commit(), bvseed.code_commit(), bvseed.code_commit_time()
        beacon_round = bvseed.load_beacon()["round"]
    else:
        sap, code, when = _optional(bvseed.sap_tag_commit), _optional(bvseed.code_commit), _optional(bvseed.code_commit_time)
        beacon_round = None
    return {
        "sap_tag_commit": sap,
        "eval_seed": seed if seed_label == "eval" else None,
        "beacon_round": beacon_round,
        "seed_label": seed_label,
        "seed": seed,
        "code_commit": code,
        "generated_at": when,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
    }


def _dumps(doc: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(doc, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    return json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def documents(cal: Calibration, prov: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(thresholds.json, null_pool.json) as JSON-ready dicts; unrounded float64 values (docs/11 §15 rule 6)."""
    pool_doc = {
        "_about": POOL_ABOUT if cal.seed_label == "eval" else "DEVELOPMENT OUTPUT (dev seed), not a result. " + POOL_ABOUT,
        "data_origin": DATA_ORIGIN,
        **prov,
        "r_null": cal.r,
        "indicator": ind.DISCORDANCE,
        "statistic": ind.STATISTIC[ind.DISCORDANCE],
        "M": int(cal.discordance_pool.size),
        "values": [float(v) for v in cal.discordance_pool],
    }
    pool_sha = hashlib.sha256(_dumps(pool_doc, compact=True).encode("utf-8")).hexdigest()
    d = cal.indicators[ind.DISCORDANCE]
    doc: dict[str, Any] = {
        "_about": ABOUT if cal.seed_label == "eval" else ABOUT_DEV,
        "data_origin": DATA_ORIGIN,
        **prov,
        "r_null": cal.r,
        "keys": {"stream": cal.stream, "cell_index": cal.cell_index, "role": cal.role, "replicates": [0, cal.r - 1]},
        "design": cal.design.to_dict(),
        "alpha": {ind.LOOK: cal.alpha_look, ind.WATCH: cal.alpha_watch},
    }
    for name in ind.INDICATORS:
        doc[name] = cal.indicators[name].to_dict()
    doc["achieved"] = {name: cal.indicators[name].achieved() for name in ind.INDICATORS}
    doc["expected_false_look_flags_per_study"] = _float_or_none(d.expected_false_look)
    doc["null_pool"] = {"file": NULL_POOL_NAME, "indicator": ind.DISCORDANCE, "M": int(cal.discordance_pool.size),
                        "sha256": pool_sha}
    return doc, pool_doc


def write_outputs(cal: Calibration, out_dir: Path, prov: Mapping[str, Any]) -> list[Path]:
    doc, pool_doc = documents(cal, prov)
    out_dir.mkdir(parents=True, exist_ok=True)
    thresholds_path, pool_path = out_dir / THRESHOLDS_NAME, out_dir / NULL_POOL_NAME
    pool_path.write_text(_dumps(pool_doc, compact=True), encoding="utf-8")
    thresholds_path.write_text(_dumps(doc), encoding="utf-8")
    return [thresholds_path, pool_path]


# ---- command line ---------------------------------------------------------------------------------------------------


def _inside(path: Path, rel: str) -> bool:
    target = (REPO_ROOT / rel).resolve()
    p = path.resolve()
    return p == target or target in p.parents


def check_frozen() -> None:
    ok, report = bvseed.check_frozen()
    if not ok:
        raise CalibrationError("frozen inputs differ from params.yaml frozen_inputs and no docs/11 §17 row cites "
                               "the new hash; refusing to calibrate:\n  " + "\n  ".join(report))


def resolve_run(seed_label: str, r: int | None, out: Path | None, params: Mapping[str, Any]) -> tuple[int, int, Path]:
    """(seed, R, output directory) after the docs/11 §1.2-§1.3 checks for this seed label."""
    r_null = int(params["calibration"]["r_null"])
    if seed_label == "eval":
        if r is not None and int(r) != r_null:
            raise CalibrationError(f"evaluation-seed calibration always uses R = calibration.r_null = {r_null}; "
                                   "--r is for development with --seed dev")
        if out is not None and out.resolve() != OUT_DIR.resolve():
            raise CalibrationError("evaluation-seed calibration writes only to monitoring/out/ (committed, logged)")
        bvseed.assert_committed_tree(ignore=[f"monitoring/out/{THRESHOLDS_NAME}", f"monitoring/out/{NULL_POOL_NAME}",
                                             bvseed.RUN_LOG_REL])
        return bvseed.eval_seed(), r_null, OUT_DIR
    if seed_label != "dev":
        raise CalibrationError(f"unknown seed label {seed_label!r} (dev or eval)")
    if out is None:
        raise CalibrationError("--seed dev needs --out DIR, a scratch directory (development output is never committed)")
    for rel in COMMITTED_DIRS:
        if _inside(out, rel):
            raise CalibrationError(f"--seed dev never writes into {rel}/ (docs/11 §1.3); use a scratch directory")
    return bvseed.dev_seed(), r_null if r is None else int(r), out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bvsignal.calibrate",
                                 description="Calibrate Look and Watch thresholds from the pre-registered null "
                                             "(docs/11 §9.2-9.3). SIMULATED.")
    ap.add_argument("--seed", choices=["dev", "eval"], default="eval",
                    help="eval (default): the evaluation seed, monitoring/out/ and the run log; dev: params.yaml "
                         "seeds.dev, development only")
    ap.add_argument("--r", type=int, default=None, help="null studies (development only; default calibration.r_null)")
    ap.add_argument("--out", type=Path, default=None, help="output directory (dev: a scratch directory, required)")
    ap.add_argument("--workers", type=int, default=None, help="worker processes (default: all cores; results do not "
                                                              "depend on it)")
    args = ap.parse_args(argv)
    argv_used = sys.argv[1:] if argv is None else list(argv)
    try:
        check_frozen()
        params = bvseed.load_params()
        seed, r, out = resolve_run(args.seed, args.r, args.out, params)
        prov = provenance(args.seed, seed)
        t0 = time.perf_counter()
        cal = calibrate(seed, r, seed_label=args.seed, workers=args.workers, params=params)
        elapsed = time.perf_counter() - t0
        paths = write_outputs(cal, out, prov)
        if args.seed == "eval":
            bvseed.log_run(["python", "-m", "bvsignal.calibrate", *argv_used], paths)
    except (CalibrationError, bvseed.SeedError) as e:
        print(f"bvsignal.calibrate: {e}", file=sys.stderr)
        return 2
    print(f"calibrated {len(ind.INDICATORS)} indicators on r_null={cal.r} null studies ({args.seed} seed, stream "
          f"{cal.stream}, {args.workers or default_workers()} workers) in {elapsed:.1f} s; {DATA_ORIGIN}"
          + ("; DEVELOPMENT OUTPUT, not a result" if args.seed == "dev" else ""))
    for name in ind.INDICATORS:
        c = cal.indicators[name]
        s = c.served()
        print(f"  {name:17s} look={s[ind.LOOK]} watch={s[ind.WATCH]} ({ind.FLAG_WHEN[name]}); achieved look "
              f"{c.look_rate:.4f} (MC SE {c.look_mc_se:.4f}), watch {c.watch_rate:.4f} (MC SE {c.watch_mc_se:.4f}); "
              f"false Look flags per study {c.expected_false_look:.3f}; mean computed sites "
              f"{float(c.computed_per_study.mean()):.2f}")
    for p in paths:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
