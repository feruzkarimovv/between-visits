"""The committed evaluation study: ``make site-signal`` (docs/11-site-signal-sap.md §11.4, §12.7, §15). SIMULATED.

Pipeline (WS5 task S6), one study on stream 0::

    seed -> simulate (key SeedSequence(seed, spawn_key=(streams.committed_study, cell_index.none,
            roles.null_or_committed, 0)), the §11.4 planted mix) -> match (episodes, matching, guards, §4-§8.1)
         -> indicators (discordance z*, gsm-style rate KRI, simaerep classic (legacy), the ablation), tiers read
            from thresholds.json (never computed here) -> equity (``bvsignal.equity``, task S9, when present)
         -> monitoring/out/{signal_run, episodes, site_ae, answer_key, report_only}.json (+ equity.json)
         -> report.py: validation/site_signal/report.md and funnel.svg

Shapes are those of docs/03 §5.3 and docs/02 § Files behind Site Signal: ``signal_run.json`` is ``{run, sites,
rows, funnel}`` (the run block of ``GET /api/sites``, rows ordered computed-by-rank then not-computed by site id),
``episodes.json`` is ``[Episode]`` with synthetic evidence, ``site_ae.json`` is ``[SiteAE]`` and
``answer_key.json`` holds the key and the per-indicator confusion (illustration only, §12.7: positives are the
planted capture losses, the two must-be-grey sites are reported separately and are in no cell). The two
top-level arrays cannot carry provenance, so ``signal_run.json`` ``run.outputs`` binds them by sha256 (docs/11
§17). ``report_only.json`` holds the numbers that only report.md shows: the §8.3 secondary calibrated p-values
with Benjamini-Hochberg q-values, the §10.3 ablation, the §6.2 paged stratum and the §4.1 ungraded primary-term
reports per site; none of them is ever used for a tier or shown as a UI column.

Every object carries ``data_origin`` SIMULATED (REQ-030); every output carries ``sap_tag_commit``,
``eval_seed`` and ``code_commit``; ``generated_at`` is the commit time of ``code_commit`` (§15 rule 7), so two
runs of one commit give byte-identical files. JSON stores unrounded float64 values (§15 rule 6).

Seeds (docs/11 §1.3) and refusals:

* ``--seed eval`` (default): the evaluation seed from the ``sap-v1`` tag and the beacon. Writes only to
  ``monitoring/out/`` and ``validation/site_signal/``, reads the committed evaluation-seed calibration
  (``monitoring/out/thresholds.json`` and ``null_pool.json``, checked against the tag, the seed, ``r_null`` and the
  design), refuses a working tree with changes other than its own outputs and the run log (commit the
  calibration first), and appends one line to ``validation/site_signal/run_log.jsonl``.
* ``--seed dev``: ``params.yaml`` ``seeds.dev``, development only. Needs ``--out DIR`` and refuses
  ``monitoring/out/`` and ``validation/site_signal/``; it never reads evaluation outputs. Thresholds come from
  ``--thresholds FILE`` (a ``calibrate.py`` output) or, by default, a development calibration on the dev seed
  (stream 1, ``--r-cal`` null studies, default ``calibration.r_quick``) written by ``calibrate.py``'s own writer
  into ``DIR``; the run then reads them back from that file. report.md and funnel.svg go into ``DIR`` too.
* Both refuse when the ``params.yaml`` ``frozen_inputs`` hashes do not match the working tree and no docs/11 §17
  row cites the new hash.

Equity hook (task S9): when ``bvsignal.equity`` exists, ``run.py`` calls ``equity.build_equity(ctx)`` with the
:class:`RunContext` of this run and writes the returned dict as ``equity.json``, adding ``_about``,
``data_origin`` and the provenance fields. Its bootstrap draws only from its own stream-0 ``role`` 2 keys, so it
changes no other output.

Command line, from the repository root::

    uv run --project monitoring python -m bvsignal.run                               # make site-signal
    uv run --project monitoring python -m bvsignal.run --seed dev --out "$TMPDIR/s6" [--r-cal N] [--workers N]

No LLM anywhere on this path (CLAUDE.md rule 1). Capture discordance is a reason to look, not a finding.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import importlib.util
import json
import math
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT
from bvsignal import calibrate as cb
from bvsignal import indicators as ind
from bvsignal import match as bvmatch
from bvsignal import report as bvreport
from bvsignal import seed as bvseed
from bvsignal import simulate as sim

OUT_DIR = MONITORING_DIR / "out"
REPORT_DIR = REPO_ROOT / "validation" / "site_signal"
COMMITTED_DIRS = ("monitoring/out", "validation/site_signal")
RUN_ID = "sr_committed"

SIGNAL_RUN = "signal_run.json"
EPISODES = "episodes.json"
SITE_AE = "site_ae.json"
ANSWER_KEY = "answer_key.json"
REPORT_ONLY = "report_only.json"
EQUITY = "equity.json"
OUTPUT_NAMES = (SIGNAL_RUN, EPISODES, SITE_AE, ANSWER_KEY, REPORT_ONLY, EQUITY)
THRESHOLDS = cb.THRESHOLDS_NAME
NULL_POOL = cb.NULL_POOL_NAME
EQUITY_MODULE = "bvsignal.equity"
EQUITY_HOOK = "build_equity"

TIERS = (ind.WATCH, ind.LOOK)  # confusion keys, in the docs/03 §5.3 order
FLAGGED = {ind.WATCH: frozenset({ind.WATCH}), ind.LOOK: frozenset({ind.WATCH, ind.LOOK})}  # Look counts Watch (§8.3)
CELLS = ("tp", "fp", "fn", "tn")
#: docs/11 §11.4 "Confusion-matrix role" of the two must-be-grey sites (params.yaml planted keys): the reason each
#: indicator must give. low_coverage only binds discordance (the comparators have no coverage guard, §10);
#: small_site binds every indicator (all apply min_patients). They are reported separately, in no confusion cell.
MUST_BE_GREY = {
    "low_coverage": {ind.DISCORDANCE: bvmatch.LOW_COVERAGE},
    "small_site": {name: bvmatch.INSUFFICIENT_PATIENTS for name in ind.TIERED},
}

ABOUT = ("Site Signal committed evaluation study (docs/11-site-signal-sap.md §11.4, §12.7): both streams are "
         "SIMULATED; grades and red flags come from the real rules.py; tiers use the sap-v1 thresholds from "
         "thresholds.json; capture discordance is a reason to look, not a finding")
DEV_PREFIX = "DEVELOPMENT OUTPUT (dev seed), not a result and never committed or quoted. "
ABOUT_KEY = ("Answer key of the committed study (docs/11 §11.4) and per-indicator confusion at both tiers: an "
             "illustration only, never evidence of performance (§12.7; the evidence is "
             "validation/site_signal/summary.json). Positives are the planted capture losses; a positive that is not "
             "computed is a false negative; the two must-be-grey sites are reported separately under must_be_grey "
             "and are in no confusion cell. SIMULATED")
ABOUT_REPORT_ONLY = ("Numbers shown only in validation/site_signal/report.md, never used for a tier and never a UI "
                     "column: the §8.3 secondary calibrated p-values with Benjamini-Hochberg q-values, the §10.3 "
                     "AE-to-report ratio ablation, the §6.2 paged stratum and the §4.1 ungraded primary-term reports "
                     "per site. SIMULATED")
ABOUT_EQUITY = ("Equity analysis of the committed study (docs/11 §14): within-site capture by language and pace; "
                "power is low. SIMULATED")
FUNNEL_NOTE = ("Lower limits L_t(E) = 1 + c_t sqrt((1 - p_bar)/E + tau2) of docs/11 §8.4 on a grid of E, floored at 0 "
               "because O/E >= 0; they approximate V by E(1 - p_bar) and are for display only: tiers always use each "
               "site's exact z*")
FUNNEL_GRID_POINTS = 41
FUNNEL_GRID_HEADROOM = 1.25
FUNNEL_GRID_MIN_TOP = 10.0


class RunError(RuntimeError):
    """A precondition of a run is not met (message is user-facing)."""


# ---- provenance and serialization -----------------------------------------------------------------------------


def utc_iso(when: str | None) -> str | None:
    """A git ISO-8601 time as UTC ``YYYY-MM-DDTHH:MM:SSZ`` (docs/03 §5.3)."""
    if when is None:
        return None
    t = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _optional(fn: Any) -> Any:
    try:
        return fn()
    except bvseed.SeedError:
        return None


def provenance(seed_label: str, seed: int) -> dict[str, Any]:
    """docs/11 §15 rule 7 and §11.3: tag commit, seed, beacon round, code commit and its time, numpy and scipy."""
    if seed_label == "eval":
        sap, code, when = bvseed.sap_tag_commit(), bvseed.code_commit(), bvseed.code_commit_time()
        beacon_round = bvseed.load_beacon()["round"]
    else:
        sap, code = _optional(bvseed.sap_tag_commit), _optional(bvseed.code_commit)
        when, beacon_round = _optional(bvseed.code_commit_time), None
    return {
        "sap_tag_commit": sap,
        "eval_seed": seed if seed_label == "eval" else None,
        "beacon_round": beacon_round,
        "seed_label": seed_label,
        "seed": seed,
        "code_commit": code,
        "generated_at": utc_iso(when),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
    }


def dumps(doc: Any) -> str:
    """JSON text of one output: an object indented, a top-level array one compact record per line (diff-friendly).
    Unrounded float64 values (docs/11 §15 rule 6); NaN is refused."""
    if isinstance(doc, list):
        if not doc:
            return "[]\n"
        lines = (json.dumps(x, ensure_ascii=False, allow_nan=False, separators=(",", ":")) for x in doc)
        return "[\n" + ",\n".join(lines) + "\n]\n"
    return json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _num(x: Any) -> float | None:
    """A JSON number or None (NaN and infinities become None)."""
    if x is None:
        return None
    v = float(x)
    return v if math.isfinite(v) else None


# ---- thresholds (read, never computed, at analysis time) -------------------------------------------------------


@dataclass(frozen=True)
class ThresholdSource:
    """A ``calibrate.py`` output: thresholds.json (served orientation) and its null pool, verified by sha256."""

    path: Path
    doc: dict[str, Any]
    thresholds: ind.Thresholds
    null_pool: np.ndarray
    sha256: str


def load_threshold_source(path: Path) -> ThresholdSource:
    """thresholds.json and the null_pool.json it names (same directory); refuses a pool whose sha256 differs."""
    path = Path(path)
    if not path.is_file():
        raise RunError(f"{path} does not exist")
    doc = json.loads(path.read_text(encoding="utf-8"))
    pool_ref = doc.get("null_pool") or {}
    pool_path = path.parent / str(pool_ref.get("file", NULL_POOL))
    if not pool_path.is_file():
        raise RunError(f"{pool_path} (the null pool of {path.name}) does not exist")
    if bvseed.file_sha256(pool_path) != pool_ref.get("sha256"):
        raise RunError(f"{pool_path} does not match the sha256 recorded in {path}")
    try:
        thresholds = ind.load_thresholds(path)
        pool = ind.load_null_pool(pool_path)
    except (ValueError, KeyError) as e:
        raise RunError(f"{path}: {e}") from e
    missing = [name for name in ind.INDICATORS if name not in thresholds]
    if missing:
        raise RunError(f"{path} has no thresholds for {missing}")
    return ThresholdSource(path=path, doc=doc, thresholds=thresholds, null_pool=pool, sha256=bvseed.file_sha256(path))


def check_design(src: ThresholdSource, design: sim.Design) -> None:
    if src.doc.get("design") != design.to_dict():
        raise RunError(f"{src.path} was calibrated at design {src.doc.get('design')}, not the sap-v1 design "
                       f"{design.to_dict()}")


def check_eval_thresholds(src: ThresholdSource, seed: int, params: Mapping[str, Any], design: sim.Design) -> None:
    """The committed study uses only the evaluation-seed calibration of the sap-v1 design (docs/11 §9.2)."""
    doc = src.doc
    expected = {
        "seed_label": "eval",
        "eval_seed": seed,
        "sap_tag_commit": bvseed.sap_tag_commit(),
        "r_null": int(params["calibration"]["r_null"]),
    }
    wrong = {k: doc.get(k) for k, v in expected.items() if doc.get(k) != v}
    if wrong:
        raise RunError(f"{src.path} is not the evaluation-seed calibration this run needs (expected {expected}, "
                       f"found {wrong}); run `uv run --project monitoring python -m bvsignal.calibrate` and commit it")
    keys = doc.get("keys") or {}
    if keys.get("stream") != int(params["streams"]["calibration"]):
        raise RunError(f"{src.path} was not calibrated on the calibration stream (docs/11 §1.3)")
    check_design(src, design)


def dev_thresholds(out: Path, seed: int, r: int, workers: int | None, params: Mapping[str, Any]) -> list[Path]:
    """A development calibration on the dev seed (calibrate.py's procedure and writer) into ``out``."""
    cal = cb.calibrate(seed, r, seed_label="dev", workers=workers, params=params)
    return cb.write_outputs(cal, out, cb.provenance("dev", seed))


# ---- the run ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunContext:
    """Everything one run computed, for the equity hook (task S9) and for tests.

    ``key`` is the committed study's replicate key; equity draws only from ``SeedSequence(seed, spawn_key=(stream,
    cell_index, roles.resampling, i))`` (docs/11 §1.3, §14)."""

    seed_label: str
    seed: int
    stream: int
    cell_index: int
    key: np.random.SeedSequence
    study: sim.Study
    match: bvmatch.StudyMatch
    indicators: ind.StudyIndicators
    thresholds: ind.Thresholds
    params: Mapping[str, Any]
    cfg: Mapping[str, Any]
    workers: int | None


def committed_key(seed: int, params: Mapping[str, Any]) -> tuple[int, int, np.random.SeedSequence]:
    """(stream, cell_index, key) of the committed study: stream 0, no cell, role 0, replicate 0 (docs/11 §1.3)."""
    stream = int(params["streams"]["committed_study"])
    cell = int(params["cell_index"]["none"])
    role = int(params["roles"]["null_or_committed"])
    return stream, cell, bvseed.key(stream, cell, role, 0, seed=seed)


def analyze(seed: int, seed_label: str, src: ThresholdSource, *, workers: int | None = None,
            model: sim.Model | None = None) -> RunContext:
    """Simulate the §11.4 planted mix on the committed key and run every indicator with ``src``'s thresholds."""
    model = sim.default_model() if model is None else model
    stream, cell, key = committed_key(seed, model.params)
    study = sim.simulate(key, model, roles="full_mix")
    sm = bvmatch.match_study(study)
    result = ind.analyze_study(study, sm, thresholds=src.thresholds, null_pool=src.null_pool)
    for name, r in result.results.items():
        if bvmatch.ERROR in r.reasons:  # a simulated study has no load error: an error here is a bug, never silent
            msg = next((e for e in r.errors if e), "unknown error")
            raise RunError(f"{name} failed on the committed study: {msg}")
    return RunContext(seed_label=seed_label, seed=seed, stream=stream, cell_index=cell, key=key, study=study,
                      match=sm, indicators=result, thresholds=src.thresholds, params=model.params,
                      cfg=model.signal_rules, workers=workers)


def equity_available() -> bool:
    """True once task S9 has added ``bvsignal.equity``."""
    return importlib.util.find_spec(EQUITY_MODULE) is not None


def equity_document(ctx: RunContext) -> dict[str, Any] | None:
    """``bvsignal.equity.build_equity(ctx)`` when task S9 has added the module, else None."""
    if not equity_available():
        return None
    module = importlib.import_module(EQUITY_MODULE)
    doc = getattr(module, EQUITY_HOOK)(ctx)
    if not isinstance(doc, dict):
        raise RunError(f"{EQUITY_MODULE}.{EQUITY_HOOK} must return a dict, got {type(doc).__name__}")
    return doc


# ---- documents --------------------------------------------------------------------------------------------------


def ordered_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """docs/03 §5.3: computed sites by rank (z_adj ascending), then not-computed sites by site id."""
    computed = sorted((r for r in rows if r["rank"] is not None), key=lambda r: r["rank"])
    rest = sorted((r for r in rows if r["rank"] is None), key=lambda r: r["site_id"])
    return [dict(r) for r in (*computed, *rest)]


def funnel(rows: Sequence[Mapping[str, Any]], thresholds: Mapping[str, float | None], tau2: float | None
           ) -> dict[str, Any]:
    """§8.4: computed sites at (E, O/E) and the Look and Watch lower limits on a geometric grid of E."""
    computed = [r for r in rows if r["tier"] != ind.NOT_COMPUTED]
    points = [{"site_id": r["site_id"], "E": r["E"], "oe_ratio": r["oe_ratio"], "tier": r["tier"],
               "data_origin": r["data_origin"]} for r in computed]
    n_a = sum(int(r["n_episodes_evaluable"]) for r in computed)
    p_bar = sum(int(r["O"]) for r in computed) / n_a if n_a else None
    limits: list[dict[str, Any]] = []
    if computed and p_bar is not None:
        top = max(FUNNEL_GRID_MIN_TOP, math.ceil(FUNNEL_GRID_HEADROOM * max(float(r["E"]) for r in computed)))
        t2 = float(tau2 or 0.0)

        def lower(c: float | None, e: float) -> float | None:
            return None if c is None else max(0.0, 1 + c * math.sqrt((1 - p_bar) / e + t2))

        for e in np.geomspace(1.0, float(top), FUNNEL_GRID_POINTS).tolist():
            limits.append({"E": e, "look_lower": lower(thresholds[ind.LOOK], e),
                           "watch_lower": lower(thresholds[ind.WATCH], e), "data_origin": DATA_ORIGIN})
    return {"data_origin": DATA_ORIGIN, "p_bar": p_bar, "tau2": tau2, "note": FUNNEL_NOTE, "points": points,
            "limits": limits}


def episode_records(ctx: RunContext) -> list[dict[str, Any]]:
    """``[Episode]`` (docs/02): ISO dates, the subject's language and pace, and the first reporting call's
    synthetic quote as evidence (§11.2 step 9)."""
    study = ctx.study
    lang = dict(zip(study.subject_ids, study.roster.language(), strict=True))
    pace = dict(zip(study.subject_ids, study.roster.pace(), strict=True))
    out = []
    for ep in ctx.match.episodes():
        sid = ep["subject_id"]
        out.append({
            "episode_id": ep["episode_id"],
            "site_id": ep["site_id"],
            "subject_id": sid,
            "language": lang[sid],
            "pace": pace[sid],
            "term": ep["term"],
            "grade": int(ep["grade"]),
            "kind": ep["kind"],
            "episode_date": study.iso(ep["episode_date"]),
            "checkin_ids": list(ep["checkin_ids"]),
            "status": ep["status"],
            "paged_level": ep["paged_level"],
            "matched_site_ae_id": ep["matched_site_ae_id"],
            "evidence": study.evidence(ep["checkin_ids"][0], ep["term"]),
            "data_origin": ep["data_origin"],
        })
    return out


def run_block(ctx: RunContext, src: ThresholdSource, prov: Mapping[str, Any], outputs: Mapping[str, str]
              ) -> dict[str, Any]:
    """The run block of ``GET /api/sites`` (docs/03 §5.3) plus provenance."""
    study, params, result = ctx.study, ctx.params, ctx.indicators
    d = params["design"]
    return {
        "id": RUN_ID,
        "data_origin": DATA_ORIGIN,
        "sap_tag_commit": prov["sap_tag_commit"],
        "eval_seed": prov["eval_seed"],
        "generated_at": prov["generated_at"],
        "code_commit": prov["code_commit"],
        "design": {
            "n_sites": study.design.n_sites,
            "window_weeks": int(d["window_weeks"]),
            "data_cut_date": study.iso(study.data_cut),
            "patients_per_site": list(study.design.patients_per_site),
            "mu": study.design.mu,
            "gross_f": float(params["planted"]["gross"]["f"]),
            "study_start_date": str(d["study_start_date"]),
        },
        "thresholds": {name: dict(ctx.thresholds[name]) for name in ind.TIERED},
        "expected_false_look_flags_per_study": _num(src.doc.get("expected_false_look_flags_per_study")),
        "phi": _num(result.phi),
        "tau2": _num(result.tau2),
        "n_computed_sites": ctx.match.n_computed_sites,
        "study_not_computed_reason": ctx.match.study_not_computed_reason,
        "seed_label": prov["seed_label"],
        "seed": prov["seed"],
        "beacon_round": prov["beacon_round"],
        "numpy_version": prov["numpy_version"],
        "scipy_version": prov["scipy_version"],
        "thresholds_sha256": src.sha256,
        "outputs": dict(outputs),
    }


def tiers_by_indicator(result: ind.StudyIndicators) -> dict[str, dict[str, str]]:
    """{indicator: {site_id: tier}} for the three tiered indicators."""
    return {name: dict(zip(result.site_ids, result.tiers(name), strict=True)) for name in ind.TIERED}


def reasons_by_indicator(result: ind.StudyIndicators) -> dict[str, dict[str, str | None]]:
    return {name: dict(zip(result.site_ids, result.results[name].reasons, strict=True)) for name in ind.TIERED}


def confusion(labels: Mapping[str, str], tiers: Mapping[str, Mapping[str, str]], positive: Iterable[str],
              excluded: Iterable[str] = ()) -> tuple[dict[str, Any], dict[str, Any]]:
    """Per indicator and tier ``{tp, fp, fn, tn}`` and the site lists behind them (docs/03 §5.3, docs/11 §12.7).

    ``labels``: site id -> answer-key label; ``positive``: the positive labels; sites whose label is in
    ``excluded`` are in no cell. A site is flagged at Watch if its tier is ``watch`` and at Look if it is ``look``
    or ``watch``; a not-computed site is never flagged, so a not-computed positive is a false negative."""
    pos, exc = frozenset(positive), frozenset(excluded)
    counted = sorted(s for s, lab in labels.items() if lab not in exc)
    matrix: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    for name, by_site in tiers.items():
        matrix[name], detail[name] = {}, {}
        for tier in TIERS:
            flagged = {s for s in counted if by_site[s] in FLAGGED[tier]}
            is_pos = {s for s in counted if labels[s] in pos}
            caught = sorted(flagged & is_pos)
            missed = sorted(is_pos - flagged)
            false_flags = sorted(flagged - is_pos)
            n_tn = len(counted) - len(caught) - len(missed) - len(false_flags)
            matrix[name][tier] = {"tp": len(caught), "fp": len(false_flags), "fn": len(missed), "tn": n_tn}
            detail[name][tier] = {"caught": caught, "missed": missed, "false_flags": false_flags}
        detail[name]["not_computed_positives"] = sorted(
            s for s in counted if labels[s] in pos and by_site[s] == ind.NOT_COMPUTED)
    return matrix, detail


def answer_key_document(ctx: RunContext, prov: Mapping[str, Any], about: str) -> dict[str, Any]:
    key = ctx.study.answer_key()
    labels = {row["site_id"]: row["label"] for row in key}
    positive = sorted({row["label"] for row in key if not row["honest"]})
    planted = ctx.params["planted"]
    grey = {str(planted[k]["label"]): expected for k, expected in MUST_BE_GREY.items() if k in planted}
    tiers = tiers_by_indicator(ctx.indicators)
    reasons = reasons_by_indicator(ctx.indicators)
    matrix, detail = confusion(labels, tiers, positive, grey)
    must_be_grey = []
    for row in key:
        if row["label"] not in grey:
            continue
        sid, expected = row["site_id"], grey[row["label"]]
        per = {}
        for name in ind.TIERED:
            exp = expected.get(name)
            per[name] = {"tier": tiers[name][sid], "not_computed_reason": reasons[name][sid], "expected_reason": exp,
                         "as_expected": None if exp is None else reasons[name][sid] == exp}
        must_be_grey.append({"site_id": sid, "label": row["label"], "indicators": per, "data_origin": DATA_ORIGIN})
    return {
        "_about": about,
        "data_origin": DATA_ORIGIN,
        **prov,
        "run_id": RUN_ID,
        "illustration_only": True,
        "positive_labels": positive,
        "must_be_grey_labels": sorted(grey),
        "answer_key": [{"site_id": row["site_id"], "label": row["label"], "f": row["f"], "data_origin": DATA_ORIGIN}
                       for row in key],
        "confusion": matrix,
        "flags": detail,
        "must_be_grey": must_be_grey,
    }


def report_only_document(ctx: RunContext, src: ThresholdSource, prov: Mapping[str, Any], about: str
                         ) -> dict[str, Any]:
    """report.md-only numbers (docs/11 §4.1, §6.2, §8.3, §10.3), unrounded."""
    study, result = ctx.study, ctx.indicators
    disc, abl = result.results[ind.DISCORDANCE], result.results[ind.ABLATION]
    secondary = result.secondary()
    abl_th = ind.check_thresholds(ctx.thresholds, [ind.ABLATION])[ind.ABLATION]
    abl_tiers = ind.tiers(abl, abl_th)
    # §4.1: completed calls whose primary-term answers reported the symptom without a gradable answer (g_k null)
    ungraded = (study.call_grade < 0) & study.call_completed[:, None]
    site_of_call = study.pat_site[study.call_pat]
    S = study.sites.n
    by_term = {t: np.bincount(site_of_call, weights=ungraded[:, j], minlength=S).astype(int)
               for j, t in enumerate(study.terms)}
    descriptive = []
    for k, s in enumerate(ctx.match.sites):
        terms = {t: int(by_term[t][k]) for t in study.terms}
        descriptive.append({"site_id": s.site_id, "paged_stratum": s.paged_stratum,
                            "ungraded_primary_term_reports": {"total": sum(terms.values()), "by_term": terms},
                            "data_origin": DATA_ORIGIN})
    return {
        "_about": about,
        "data_origin": DATA_ORIGIN,
        **prov,
        "run_id": RUN_ID,
        "calibration": {
            "file": THRESHOLDS,
            "sha256": src.sha256,
            "seed_label": src.doc.get("seed_label"),
            "r_null": src.doc.get("r_null"),
            "alpha": src.doc.get("alpha"),
            "achieved": src.doc.get("achieved"),
        },
        "secondary": {
            "method": ("calibrated empirical p_s = (1 + #{null pooled z* <= z*_s}) / (1 + M) from the §9.2 Look pool, "
                       "Benjamini-Hochberg q-values across computed sites (docs/11 §8.3); report.md only, never tiers"),
            "M": int(src.null_pool.size),
            "null_pool_sha256": src.doc["null_pool"]["sha256"],
            "sites": [{"site_id": row["site_id"], "z_adj": _num(disc.statistic[k]), "p_empirical": row["p_empirical"],
                       "q_bh": row["q_bh"], "data_origin": DATA_ORIGIN} for k, row in enumerate(secondary)],
        },
        "ablation": {
            "indicator": ind.ABLATION,
            "method": ("AE-to-report ratio (docs/11 §10.3): site rows mapping to each primary term against the "
                       "evaluable non-paged episodes of the term, leave-one-site-out; validation and report.md only"),
            "phi": _num(abl.phi),
            "thresholds": dict(abl_th),
            "sites": [{"site_id": sid, "U": abl.value("U", k), "E_U": abl.value("E_U", k),
                       "z_raw": abl.value("z_raw", k), "z_adj": abl.value("statistic", k), "tier": abl_tiers[k],
                       "not_computed_reason": abl.reasons[k], "data_origin": DATA_ORIGIN}
                      for k, sid in enumerate(abl.site_ids)],
        },
        "descriptive": {"sites": descriptive},
    }


def build_documents(ctx: RunContext, src: ThresholdSource, prov: Mapping[str, Any]
                    ) -> dict[str, dict[str, Any] | list[Any]]:
    """Every JSON output of the run, keyed by file name (equity.json only when the hook exists)."""
    dev = ctx.seed_label != "eval"
    prefix = DEV_PREFIX if dev else ""
    episodes = episode_records(ctx)
    site_ae = ctx.study.site_ae_rows(iso_dates=True)
    outputs = {EPISODES: sha256_text(dumps(episodes)), SITE_AE: sha256_text(dumps(site_ae))}
    rows = ordered_rows(ctx.indicators.rows())
    docs: dict[str, dict[str, Any] | list[Any]] = {
        SIGNAL_RUN: {
            "_about": prefix + ABOUT,
            "data_origin": DATA_ORIGIN,
            "run": run_block(ctx, src, prov, outputs),
            "sites": ctx.study.site_records(),
            "rows": rows,
            "funnel": funnel(rows, ctx.thresholds[ind.DISCORDANCE], ctx.indicators.tau2),
        },
        EPISODES: episodes,
        SITE_AE: site_ae,
        ANSWER_KEY: answer_key_document(ctx, prov, prefix + ABOUT_KEY),
        REPORT_ONLY: report_only_document(ctx, src, prov, prefix + ABOUT_REPORT_ONLY),
    }
    equity = equity_document(ctx)
    if equity is not None:
        docs[EQUITY] = {"_about": prefix + ABOUT_EQUITY, "data_origin": DATA_ORIGIN, **prov, **equity}
    return docs


def write_documents(docs: Mapping[str, Any], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, doc in docs.items():
        path = out / name
        path.write_text(dumps(doc), encoding="utf-8")
        paths.append(path)
    return paths


# ---- command line -----------------------------------------------------------------------------------------------


def _inside(path: Path, rel: str) -> bool:
    target = (REPO_ROOT / rel).resolve()
    p = Path(path).resolve()
    return p == target or target in p.parents


def check_frozen() -> None:
    ok, report = bvseed.check_frozen()
    if not ok:
        raise RunError("frozen inputs differ from params.yaml frozen_inputs and no docs/11 §17 row cites the new "
                       "hash; refusing to run:\n  " + "\n  ".join(report))


def resolve_dirs(seed_label: str, out: Path | None) -> tuple[Path, Path]:
    """(JSON output directory, report directory) after the docs/11 §1.3 rules for this seed label."""
    if seed_label == "eval":
        if out is not None and Path(out).resolve() != OUT_DIR.resolve():
            raise RunError("an evaluation-seed run writes only to monitoring/out/ (committed, logged)")
        return OUT_DIR, REPORT_DIR
    if seed_label != "dev":
        raise RunError(f"unknown seed label {seed_label!r} (dev or eval)")
    if out is None:
        raise RunError("--seed dev never writes into monitoring/out/ (docs/11 §1.3); pass --out DIR, a scratch "
                       "directory (development output is never committed)")
    for rel in COMMITTED_DIRS:
        if _inside(out, rel):
            raise RunError(f"--seed dev never writes into {rel}/ (docs/11 §1.3); use a scratch directory")
    return Path(out), Path(out)


def eval_ignored_paths() -> list[str]:
    """Paths an evaluation-seed run may find changed: its own outputs and the run log (docs/11 §1.2)."""
    out_rel = OUT_DIR.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    rep_rel = REPORT_DIR.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    return ([f"{out_rel}/{n}" for n in OUTPUT_NAMES] + [f"{rep_rel}/{n}" for n in bvreport.OUTPUT_NAMES]
            + [bvseed.RUN_LOG_REL])


def assert_committed_tree() -> None:
    try:
        bvseed.assert_committed_tree(ignore=eval_ignored_paths())
    except bvseed.SeedError as e:
        hint = ""
        if any(f"monitoring/out/{n}" in str(e) for n in (THRESHOLDS, NULL_POOL)):
            hint = ("; commit the calibration outputs (monitoring/out/thresholds.json, null_pool.json) and the run log "
                    "before make site-signal")
        raise RunError(f"{e}{hint}") from e


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bvsignal.run",
                                 description="Committed Site Signal study: simulate, match, indicators, outputs and "
                                             "report (docs/11 §12.7). SIMULATED.")
    ap.add_argument("--seed", choices=["dev", "eval"], default="eval",
                    help="eval (default): the evaluation seed, monitoring/out/, validation/site_signal/ and the run "
                         "log; dev: params.yaml seeds.dev into --out, development only")
    ap.add_argument("--out", type=Path, default=None, help="output directory (dev: a scratch directory, required)")
    ap.add_argument("--thresholds", type=Path, default=None,
                    help="dev only: a calibrate.py thresholds.json (with its null_pool.json) instead of a development "
                         "calibration")
    ap.add_argument("--r-cal", type=int, default=None,
                    help="dev only: null studies of the development calibration (default calibration.r_quick)")
    ap.add_argument("--workers", type=int, default=None,
                    help="worker processes for the development calibration (default: all cores; results do not "
                         "depend on it)")
    args = ap.parse_args(argv)
    argv_used = sys.argv[1:] if argv is None else list(argv)
    t0 = time.perf_counter()
    try:
        check_frozen()
        if args.seed == "eval" and (args.thresholds is not None or args.r_cal is not None):
            raise RunError("--thresholds and --r-cal are for development with --seed dev; an evaluation-seed run reads "
                           "monitoring/out/thresholds.json")
        out, report_dir = resolve_dirs(args.seed, args.out)
        model = sim.default_model()
        params = model.params
        cal_paths: list[Path] = []
        if args.seed == "eval":
            assert_committed_tree()
            seed = bvseed.eval_seed()
            src = load_threshold_source(OUT_DIR / THRESHOLDS)
            check_eval_thresholds(src, seed, params, model.design)
        else:
            seed = bvseed.dev_seed()
            if args.thresholds is not None:
                src = load_threshold_source(args.thresholds)
            else:
                r = int(params["calibration"]["r_quick"]) if args.r_cal is None else int(args.r_cal)
                if r < 1:
                    raise RunError(f"--r-cal must be >= 1, got {r}")
                cal_paths = dev_thresholds(out, seed, r, args.workers, params)
                src = load_threshold_source(out / THRESHOLDS)
            check_design(src, model.design)
        prov = provenance(args.seed, seed)
        ctx = analyze(seed, args.seed, src, workers=args.workers, model=model)
        docs = build_documents(ctx, src, prov)
        paths = write_documents(docs, out)
        paths += bvreport.write_report(out, report_dir)
        if args.seed == "eval":
            bvseed.log_run(["python", "-m", "bvsignal.run", *argv_used], paths)
    except (RunError, bvseed.SeedError, cb.CalibrationError, bvreport.ReportError) as e:
        print(f"bvsignal.run: {e}", file=sys.stderr)
        return 2
    elapsed = time.perf_counter() - t0
    rows = docs[SIGNAL_RUN]["rows"]  # type: ignore[index]
    counts = {t: sum(r["tier"] == t for r in rows) for t in ind.TIER_VALUES}
    print(f"committed study ({args.seed} seed, stream {ctx.stream}): {ctx.match.n_computed_sites} computed sites; "
          f"discordance tiers {counts}; {elapsed:.1f} s; {DATA_ORIGIN}"
          + ("; DEVELOPMENT OUTPUT, not a result" if args.seed == "dev" else "")
          + ". A reason to look, not a finding.")
    for p in [*cal_paths, *paths]:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
