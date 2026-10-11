"""Study generation and answer key for Site Signal (docs/11-site-signal-sap.md §11.2, §11.4). SIMULATED.

One simulated study is a pure function of ``(params, design, roles, scenario, key)``: every random draw
comes from the replicate key's study child, in a fixed order, so the same key gives a byte-identical study
(same sha256 of :meth:`Study.to_dict`). The steps follow SAP §11.2:

1. **Roster** (``roster.py``): sites 101-120 with fictional names, patients per site, Spanish share by site,
   age and pace, enrollment day. Planted roles (§11.4) go to distinct non-101 sites drawn from the study
   generator; site 101 (Hillside Cancer Center, fictional) is always honest.
2. **Schedule**: a dose every ``cycle_days`` from enrollment; calls on ``call_days_after_dose`` after each dose
   up to the data cut; per-patient completion probability, each scheduled call completed with it.
3. **Latent episodes**: Poisson count per patient (rate x case mix x frailty x share of the window), term mix,
   grade 3 share, start day uniform over days on study, geometric duration in scheduled calls; same-term
   overlaps merge at the higher grade.
4. **Answers**: on each completed call, each primary term's answer set is drawn uniformly among the
   enumerated candidates of the item domain that the real ``rules.grade()`` gives the latent grade, plus the
   ``answer_generation.secondary`` items; calls without an episode answer at the "none" level.
5. **Mapping error**: per patient error rate; each recorded primary-term answer moves to an adjacent value
   (``patient_stream.mapping_error_step``); follow-ups follow ``data/symptom_items.json`` (dropped when no
   longer opened, ``unknown`` when newly opened). Applied before grading.
6. **Grades, red flags and paging**: g_k per term by the §4.2 mapping (0 when ``rules.term_present`` is false,
   else ``rules.grade``), and the call's level from ``rules.red_flags(active_ids=plan red flags)`` and
   ``rules.level_for``. No grade, threshold or red-flag rule is re-coded here.
7. **Site capture** of each latent episode: (1 - f_s) x expit(logit p0 + u_s + v_i + delta), one site row per
   captured episode (random synonym, AESTDTC noise, entry lag from the next dose visit), ``aeseq`` by the
   §11.2 order.
8. **Other AEs**: non-symptomatic site rows for the comparators, dropped with probability f_s at planted sites.
9. **Evidence**: one synthetic quote per reporting call and term from ``monitoring/quote_bank.json``.
10. **Output**: the :class:`Study`, its answer key and JSON records, each object with ``data_origin`` SIMULATED.

Every number comes from ``monitoring/params.yaml``, ``data/signal_rules.json`` or the data files read through
``rules.py``; this file holds no numeric literal other than 0, 1 and -1 (AST check, REQ-023). Candidate
enumerations, transition tables and grades are built once per :class:`Model`; red-flag levels are cached per
answer tuple. No LLM anywhere on this path (CLAUDE.md rule 1). Capture discordance is a reason to look, not
a finding.

Command line (dev seed only; development output goes to a scratch directory, never to ``monitoring/out/``)::

    uv run --project monitoring python -m bvsignal.simulate --seed dev --studies 5 [--with-episodes] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import betaincinv, expit, logit, ndtr

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT
from bvsignal import roster as bvroster
from bvsignal import seed as bvseed
from bvsignal._backend import (
    ABSENT_OPTIONS,
    LEVEL_RANK,
    AnswerInput,
    content,
    grade,
    level_for,
    red_flags,
    term_present,
)

ABOUT = ("SIMULATED Site Signal study (docs/11-site-signal-sap.md §11.2, §11.4): both streams are simulated; "
         "grades and red flags come from the real rules.py; capture discordance is a reason to look, not a finding")
QUOTE_BANK_FILE = MONITORING_DIR / "quote_bank.json"
SOURCE = "synthetic"
COMPLETED = "completed"
MISSED = "no_answer"  # docs/02 CheckIn.status: a simulated call is completed or missed, never partial (§6.3)
SITE_ORIGIN = "site"
UNKNOWN = "unknown"
NON_VALUES = frozenset({"unknown", "not_measured"})
NULL = -1  # null grade, no state, no row, no quote
STUDY_CHILD, RESAMPLING_CHILD = 0, 1  # children of a replicate key (docs/11 §1.3)
BASELINE_KEY = "stools_per_day"  # the baseline dict rules.py reads (derived input stools_over_baseline)
COPULA = ("v", "pi", "eps")  # per-patient normals: capture effect, call completion, mapping error (§11.2, SE16)
LANGS = (bvroster.ENGLISH, bvroster.SPANISH)
USUBJID_PREFIX = "BVSIM"
# params.yaml answer_generation.secondary.diarrhea_episode: "DIZZINESS_SEV mild or worse with DIZZY_ON_STANDING yes"
DIZZY_KEY, DIZZY_SEV_KEY = "dizzy_on_standing", "dizziness_sev_when_dizzy"
DIZZY_GATE, DIZZY_ITEM = "DIZZINESS_SEV", "DIZZY_ON_STANDING"
# patient_stream.mapping_error_step key for each numeric scale
NUMERIC_STEP_KEY = {"count": "stools_per_day", "temperature": "temperature_c"}
# Simulated non-symptomatic site AE terms (labs and other events; comparators only, never matched: none maps to
# a primary term in data/signal_rules.json). CTCAE term names, no MedDRA codes or hierarchy.
OTHER_AE_TERMS = (
    "Anemia",
    "Platelet count decreased",
    "Alanine aminotransferase increased",
    "Creatinine increased",
    "Hypothyroidism",
    "Lymphocyte count decreased",
)
# planted role keys (params.yaml planted.*) this module understands
ROLE_KEYS = frozenset({"label", "count", "f", "casemix", "spanish_share", "spanish_capture_odds_ratio",
                       "u_s_between_site_sds", "call_completion_mean", "patients"})
LOSS_KEYS = ("f", "spanish_capture_odds_ratio")  # a role with a planted capture loss is a positive (§11.4)


# ---- design, roles and scenarios ------------------------------------------------------------------------


@dataclass(frozen=True)
class Design:
    """Study size: sites, patients per site (inclusive range) and the episode rate mu (docs/11 §11.3, §12.2)."""

    n_sites: int
    patients_per_site: tuple[int, int]
    mu: float

    def to_dict(self) -> dict[str, Any]:
        return {"n_sites": self.n_sites, "patients_per_site": list(self.patients_per_site), "mu": self.mu}


def sap_design(params: Mapping[str, Any]) -> Design:
    """The sap-v1 design: params.yaml design.n_sites, design.patients_per_site and episodes.mu (§11.5)."""
    d = params["design"]
    lo, hi = (int(v) for v in d["patients_per_site"])
    return Design(int(d["n_sites"]), (lo, hi), float(params["episodes"]["mu_g2plus_per_patient_window"]))


def grid_design(params: Mapping[str, Any], cell: int) -> Design:
    """The design of one power-grid cell (params.yaml cell_index.grid; exact patients per site, §12.2)."""
    for row in params["cell_index"]["grid"]:
        if int(row["cell"]) == int(cell):
            n = int(row["patients_per_site"])
            return Design(int(row["n_sites"]), (n, n), float(row["mu"]))
    raise KeyError(f"no grid cell {cell} in params.yaml cell_index.grid")


Role = tuple[str, Mapping[str, Any]]


def full_mix_roles(params: Mapping[str, Any]) -> tuple[Role, ...]:
    """The §11.4 planted truth, in params.yaml order, each role repeated `count` times (honest = the rest)."""
    out: list[Role] = []
    for spec in params["planted"].values():
        if spec["count"] == "rest":
            continue
        out.extend((str(spec["label"]), spec) for _ in range(int(spec["count"])))
    return tuple(out)


def planted_roles(params: Mapping[str, Any], f: float, k: int = 1, label: str | None = None) -> tuple[Role, ...]:
    """`k` sites with capture loss `f` and nothing else planted (power grid §12.2: k = 1; blind run §13)."""
    lab = str(params["planted"]["gross"]["label"]) if label is None else label
    return tuple((lab, {"label": lab, "f": float(f)}) for _ in range(int(k)))


@dataclass(frozen=True)
class Scenario:
    """Data-generating changes of the failure case (§12.5) and the sensitivity analyses (§12.6).

    ``None`` keeps the params.yaml value. Analysis-side settings (SE1, SE2, SE14, SE20, SE21) change nothing
    here and are carried in ``analysis`` for match.py and indicators.py."""

    name: str = "base"
    between_site_sd_logit: float | None = None
    casemix_sd_log: float | None = None
    patient_re_sd_logit: float | None = None
    call_completion_mean: float | None = None
    call_completion_kappa: float | None = None
    mapping_error_multiplier: float | None = None
    mapping_error_language: str | None = None  # None: every patient
    capture_boost_logit: float | None = None  # SE15
    capture_boost_within_days: int | None = None
    capture_boost_n_sites: int | None = None
    copula: tuple[float, float, float] | None = None  # SE16: corr(z_v, z_pi), corr(z_v, z_eps), corr(z_pi, z_eps)
    slow_entry_lag_mean_days: float | None = None  # SE17
    slow_entry_n_sites: int | None = None
    site_mapping_error: tuple[float, float] | None = None  # SE18: Beta(a, b) per site
    site_mapping_error_n_sites: int | None = None
    analysis: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name}
        for k, v in self.__dict__.items():
            if k == "name" or v is None or v == ():
                continue
            if k == "analysis":
                out[k] = dict(v)
            else:
                out[k] = list(v) if isinstance(v, tuple) else v
        return out


def failure_case_scenario(params: Mapping[str, Any]) -> Scenario:
    """§12.5: diligence-dominated heterogeneity (between-site SD and case-mix SD from params.yaml failure_case)."""
    fc = params["failure_case"]
    return Scenario(name="failure_case", between_site_sd_logit=float(fc["between_site_sd_logit"]),
                    casemix_sd_log=float(fc["casemix_sd_log"]))


def scenario_from_params(params: Mapping[str, Any], sid: str) -> Scenario:
    """The §12.6 scenario `sid` (SE1-SE21) from params.yaml sensitivity.scenarios."""
    spec = dict(params["sensitivity"]["scenarios"][sid])
    base_cc = params["patient_stream"]["call_completion"]
    kw: dict[str, Any] = {}
    analysis: list[tuple[str, Any]] = []
    take = spec.pop
    if "match_window_days" in spec:
        analysis += [("match_window_days", take("match_window_days")), ("lower_tolerance_days", take("lower_tolerance_days"))]
    if "mapping_error_multiplier" in spec:
        kw["mapping_error_multiplier"] = float(take("mapping_error_multiplier"))
        kw["mapping_error_language"] = str(take("language"))
    if "call_completion_mean" in spec:
        kw["call_completion_mean"] = float(take("call_completion_mean"))
        kw["call_completion_kappa"] = float(take("kappa"))
        low = take("low_coverage_mean")
        if float(low) != float(params["planted"]["low_coverage"]["call_completion_mean"]):
            raise ValueError(f"{sid}: the low_coverage site keeps its planted mean (docs/11 §12.6)")
    if "between_site_sd_logit" in spec:
        kw["between_site_sd_logit"] = float(take("between_site_sd_logit"))
        take("low_diligence_offset", None)  # the honest_low_diligence offset is always scaled by the scenario SD
    if "patient_re_sd_logit" in spec:
        kw["patient_re_sd_logit"] = float(take("patient_re_sd_logit"))
    take("thresholds", None)  # every scenario uses the sap-v1 thresholds (indicators.py)
    if "paged_rule" in spec:
        analysis.append(("paged_rule", take("paged_rule")))
    if "capture_boost_logit" in spec:
        if (take("paging_rate"), take("anchor"), take("boost_paged")) != (
                "share_completed_calls_urgent_or_emergency", "latent_start_day", True):
            raise ValueError(f"{sid}: unsupported capture boost construction (docs/11 §12.6 SE15)")
        kw["capture_boost_logit"] = float(take("capture_boost_logit"))
        kw["capture_boost_within_days"] = int(take("within_days"))
        kw["capture_boost_n_sites"] = int(take("n_sites_highest_paging"))
    if "copula" in spec:
        if take("copula") != "gaussian":
            raise ValueError(f"{sid}: only a Gaussian copula is specified (docs/11 §12.6 SE16)")
        kw["copula"] = (float(take("corr_v_pi")), float(take("corr_v_neg_eps")), float(take("corr_pi_neg_eps")))
    if "entry_lag_mean_days" in spec:
        if float(take("entry_lag_shape")) != float(params["site_capture"]["entry_lag_days"]["shape"]):
            raise ValueError(f"{sid}: the entry-lag shape must equal site_capture.entry_lag_days.shape")
        if take("eligible") != "non_101_label_honest":
            raise ValueError(f"{sid}: unsupported eligibility (docs/11 §12.6 SE17)")
        kw["slow_entry_lag_mean_days"] = float(take("entry_lag_mean_days"))
        kw["slow_entry_n_sites"] = int(take("n_sites"))
    if "site_mapping_error" in spec:
        dist = take("site_mapping_error")
        if dist["dist"] != "beta" or take("eligible") != "non_101_any_label" or (
                take("draw") != "one_per_site_replaces_patient_eps"):
            raise ValueError(f"{sid}: unsupported site mapping error construction (docs/11 §12.6 SE18)")
        kw["site_mapping_error"] = (float(dist["a"]), float(dist["b"]))
        kw["site_mapping_error_n_sites"] = int(take("n_random_sites"))
    if "casemix_sd_log" in spec:
        kw["casemix_sd_log"] = float(take("casemix_sd_log"))
    for k in ("next_visit_plus_days", "overdispersion"):
        if k in spec:
            analysis.append((k, take(k)))
    if spec:
        raise ValueError(f"{sid}: unknown scenario keys {sorted(spec)}")
    if "call_completion_kappa" in kw and kw["call_completion_kappa"] == float(base_cc["kappa"]):
        kw.pop("call_completion_kappa")
    return Scenario(name=sid, analysis=tuple(analysis), **kw)


# ---- answer model: candidates, mapping-error transitions, grades -----------------------------------------


@dataclass(frozen=True)
class Factor:
    """One independent secondary draw: choice k has probability probs[k] and sets the items in partials[k]."""

    probs: tuple[float, ...]
    partials: tuple[Mapping[str, Any], ...]

    @property
    def n(self) -> int:
        return len(self.probs)

    def choose(self, u: np.ndarray) -> np.ndarray:
        cum = np.cumsum(np.asarray(self.probs, dtype=float))
        return np.minimum(np.searchsorted(cum, u, side="right"), self.n - 1)


@dataclass
class TermSpec:
    """Everything the simulator needs to generate, perturb and grade one primary term's answers.

    A term's answer on one call is a *state*: a tuple over ``slots`` (the gate item, its follow-ups, then
    secondary items of other terms) of ``None`` (not asked), an option code, ``"unknown"``, or a numeric
    value as an integer count of the domain step (value = count / inv)."""

    term: str
    index: int
    slots: tuple[str, ...]
    numeric: tuple[bool, ...]
    options: tuple[tuple[str, ...], ...]
    inv: tuple[int, ...]
    unit: tuple[str | None, ...]
    err_step: tuple[int, ...]
    primary: tuple[int, ...]  # slots subject to mapping error (items of a primary term)
    followups: tuple[tuple[int, int, frozenset[Any]], ...]  # (gate slot, follow-up slot, opening values)
    factors: dict[int, tuple[Factor, ...]]  # grade band -> secondary factors
    factor_col: int = 0
    err_col: int = 0
    states: list[tuple[Any, ...]] = field(default_factory=list)
    ids: dict[tuple[Any, ...], int] = field(default_factory=dict)
    answer_dicts: list[dict[str, AnswerInput]] = field(default_factory=list)
    pre: dict[tuple[int, int], np.ndarray] = field(default_factory=dict)  # (band, baseline idx) -> state ids
    n_pre: int = 0
    rec_mask: np.ndarray | None = None
    trans: np.ndarray | None = None
    grade_tab: np.ndarray | None = None
    candidates: dict[tuple[int, int], int] = field(default_factory=dict)  # (band, baseline idx) -> count

    @property
    def n_factor_cols(self) -> int:
        return max((len(fs) for fs in self.factors.values()), default=0)

    @property
    def bit_weights(self) -> np.ndarray:
        return np.left_shift(1, np.arange(len(self.primary), dtype=np.int64))

    def state_id(self, state: tuple[Any, ...]) -> int:
        sid = self.ids.get(state)
        if sid is None:
            sid = self.ids[state] = len(self.states)
            self.states.append(state)
            self.answer_dicts.append(self.decode(state))
        return sid

    def decode(self, state: tuple[Any, ...]) -> dict[str, AnswerInput]:
        out: dict[str, AnswerInput] = {}
        for k, v in enumerate(state):
            if v is None:
                continue
            code = self.slots[k]
            if v == UNKNOWN:
                out[code] = AnswerInput(option_code=UNKNOWN)
            elif self.numeric[k]:
                out[code] = AnswerInput(numeric_value=v / self.inv[k], unit=self.unit[k])
            else:
                out[code] = AnswerInput(option_code=v)
        return out

    def readable(self, state_id: int) -> dict[str, Any]:
        """A state as {item: option code | "unknown" | number}, asked items only (for JSON and tests)."""
        out: dict[str, Any] = {}
        for k, v in enumerate(self.states[state_id]):
            if v is not None:
                out[self.slots[k]] = v / self.inv[k] if (self.numeric[k] and v != UNKNOWN) else v
        return out

    def neighbour(self, k: int, v: Any, up: bool) -> Any:
        """The adjacent value of §11.2 step 5: one step up or down, the only neighbour at a scale end; a numeric
        value never goes below 0 (stools +1 at 0)."""
        step = self.err_step[k]
        if self.numeric[k]:
            return v + step if (up or v - step < 0) else v - step
        opts = self.options[k]
        i = opts.index(v)
        if i - step < 0:
            return opts[i + step]
        if i + step > len(opts) - 1:
            return opts[i - step]
        return opts[i + step] if up else opts[i - step]

    def perturb(self, state: tuple[Any, ...], err: int, up: int) -> tuple[Any, ...]:
        """Mapping error (§11.2 step 5): primary slot q moves when bit q of `err` is set (up when bit q of `up`
        is set); then a follow-up the new gate no longer opens is dropped and one it newly opens is `unknown`."""
        vals = list(state)
        for q, k in enumerate(self.primary):
            if (err >> q) & 1 and vals[k] is not None and vals[k] != UNKNOWN:
                vals[k] = self.neighbour(k, vals[k], bool((up >> q) & 1))
        for gk, fk, opening in self.followups:
            opened = vals[gk] in opening
            asked = state[fk] is not None
            if opened and not asked:
                vals[fk] = UNKNOWN
            elif asked and not opened:
                vals[fk] = None
        return tuple(vals)

    def recorded_bits(self, state: tuple[Any, ...]) -> int:
        bits = 0
        for q, k in enumerate(self.primary):
            if state[k] is not None and state[k] != UNKNOWN:
                bits |= 1 << q
        return bits


def term_grade(term: str, answers: Mapping[str, AnswerInput], baseline: Mapping[str, Any] | None) -> int | None:
    """g_k of docs/11 §4.2 for one call: None when no item of the term was answered (or only `unknown` /
    `not_measured`); 0 when `rules.term_present` is false; else `rules.grade(...).provisional_grade`."""
    asked = [answers[c] for c in content.items_for_term(term) if c in answers]
    if not any(a.option_code not in NON_VALUES and (a.option_code is not None or a.numeric_value is not None)
               for a in asked):
        return None
    if not term_present(term, dict(answers)):
        return 0
    return grade(term, dict(answers), dict(baseline) if baseline is not None else None).provisional_grade


def _absent_option(code: str) -> str:
    opts = list(content.scale(code).get("options", []))
    hits = [o for o in opts if o in ABSENT_OPTIONS]
    if len(hits) != 1:
        raise ValueError(f"{code}: expected exactly one 'none' option among {opts}")
    return hits[0]


def _followups(code: str) -> list[dict[str, Any]]:
    return list(content.item(code).get("followups", []))


def _numeric_domain(spec: Mapping[str, Any]) -> tuple[int, int, int]:
    """(lo, hi, inv): the domain min..max in steps, as integer counts of the step (value = count / inv)."""
    step = float(spec["step"])
    inv = round(1 / step)
    if not math.isclose(step * inv, 1):
        raise ValueError(f"numeric step {step} must be 1/n for an integer n")
    lo, hi = round(float(spec["min"]) * inv), round(float(spec["max"]) * inv)
    if not (math.isclose(lo / inv, float(spec["min"])) and math.isclose(hi / inv, float(spec["max"]))):
        raise ValueError(f"numeric domain {spec} is not on its step grid")
    return lo, hi, inv


def _parse_factors(term: str, block: Mapping[str, Any], where: str) -> list[Factor]:
    """Secondary factors of one params.yaml answer_generation.secondary block."""
    factors: list[Factor] = []
    block = dict(block)
    if DIZZY_KEY in block or DIZZY_SEV_KEY in block:
        p = float(block.pop(DIZZY_KEY))
        sev = dict(block.pop(DIZZY_SEV_KEY))
        fu = [f for f in _followups(DIZZY_GATE) if f["item"] == DIZZY_ITEM]
        yes = [o for o in content.scale(DIZZY_ITEM)["options"] if o not in ABSENT_OPTIONS]
        if len(fu) != 1 or len(yes) != 1 or any(s not in fu[0]["when"]["in"] for s in sev):
            raise ValueError(f"{where}: {DIZZY_GATE} values must open {DIZZY_ITEM} (data/symptom_items.json)")
        probs = [p * float(q) for q in sev.values()] + [1 - p]
        partials: list[Mapping[str, Any]] = [{DIZZY_GATE: s, DIZZY_ITEM: yes[0]} for s in sev] + [{}]
        factors.append(Factor(tuple(probs), tuple(partials)))
    for code, dist in block.items():
        if not content.has_item(code):
            raise ValueError(f"{where}: unknown secondary item {code}")
        opts = list(content.scale(code)["options"])
        bad = [o for o in dist if o not in opts]
        if bad:
            raise ValueError(f"{where}: {code} has no options {bad}")
        factors.append(Factor(tuple(float(p) for p in dist.values()), tuple({code: o} for o in dist)))
    for fac in factors:
        if not math.isclose(sum(fac.probs), 1):
            raise ValueError(f"{where}: secondary probabilities sum to {sum(fac.probs)}, not 1")
    return factors


def _build_term(term: str, index: int, params: Mapping[str, Any], primary_terms: Sequence[str],
                bands: tuple[int, ...], baselines: tuple[int, ...], none_answers: Mapping[str, AnswerInput],
                used_blocks: set[str]) -> TermSpec:
    ag = params["answer_generation"]
    gi = ag["grading_items"][term]
    gate, graded = str(gi["gate"]), str(gi["graded"])
    own = [gate]
    for fu in _followups(gate):
        if "only_if" in fu:
            if fu["only_if"] != "baseline_stools_missing":
                raise ValueError(f"{gate}: unsupported follow-up condition {fu['only_if']}")
            continue  # every simulated patient has a baseline, so this follow-up is never asked (§11.2 step 4)
        own.append(str(fu["item"]))
    if graded not in own:
        raise ValueError(f"{term}: {graded} is not a follow-up of {gate}")
    sec = ag["secondary"]
    factors: dict[int, tuple[Factor, ...]] = {}
    extras: list[str] = []
    for g in bands:
        fs: list[Factor] = []
        for name in (f"{term.lower()}_episode", f"{term.lower()}_g{g}"):
            if name in sec:
                used_blocks.add(name)
                fs.extend(_parse_factors(term, sec[name], f"answer_generation.secondary.{name}"))
        factors[g] = tuple(fs)
        for fac in fs:
            for part in fac.partials:
                extras.extend(c for c in part if c not in own and c not in extras)
    slots = tuple(own + extras)
    numeric, options, inv, unit, err_step = [], [], [], [], []
    mes = params["patient_stream"]["mapping_error_step"]
    if mes["at_scale_end"] != "only_neighbour" or mes["yes_no"] != "flip":
        raise ValueError("patient_stream.mapping_error_step: only at_scale_end only_neighbour and yes_no flip are specified")
    for code in slots:
        sc = content.item(code)["scale"]
        if content.is_numeric(code):
            lo, hi, iv = _numeric_domain(ag["numeric_domains"][code])
            numeric.append(True)
            options.append(())
            inv.append(iv)
            unit.append(ag["numeric_domains"][code].get("unit") or content.item_units(code)[0])
            step = float(mes[NUMERIC_STEP_KEY[sc]]) * iv
            if not math.isclose(step, round(step)):
                raise ValueError(f"{code}: mapping-error step is not on the domain grid")
            err_step.append(round(step))
        else:
            numeric.append(False)
            options.append(tuple(content.scale(code)["options"]))
            inv.append(1)
            unit.append(None)
            err_step.append(int(mes["ordinal_options"]))
    primary = tuple(k for k, c in enumerate(slots) if content.term_of(c) in set(primary_terms))
    rel = []
    for gk, gcode in enumerate(slots):
        for fu in _followups(gcode):
            if fu["item"] in slots and "only_if" not in fu:
                rel.append((gk, slots.index(fu["item"]), frozenset(fu["when"]["in"])))
    spec = TermSpec(term=term, index=index, slots=slots, numeric=tuple(numeric), options=tuple(options),
                    inv=tuple(inv), unit=tuple(unit), err_step=tuple(err_step), primary=primary,
                    followups=tuple(rel), factors=factors)
    # the none state (§11.2 step 4): the gate at its none level, nothing else asked
    none_state = tuple(_absent_option(gate) if c == gate else None for c in slots)
    if any(none_state[gk] in opening for gk, _, opening in spec.followups):
        raise ValueError(f"{gate}: its none level opens a follow-up")
    spec.state_id(none_state)
    # candidates per (band, baseline): enumerate the item domain and keep what rules.grade() gives the band
    gk = slots.index(gate)
    xk = slots.index(graded)
    if numeric[xk]:
        lo, hi, _ = _numeric_domain(ag["numeric_domains"][graded])
        domain: list[Any] = list(range(lo, hi + 1))
    else:
        domain = list(options[xk])
    opening = next((op for g_, f_, op in spec.followups if g_ == gk and f_ == xk), None)
    if opening is None:
        raise ValueError(f"{gate} never opens {graded}")
    for g in bands:
        fs = factors[g]
        gate_facs = [fac for fac in fs if any(gate in part for part in fac.partials)]
        if any(gate not in part or part[gate] not in opening for fac in gate_facs for part in fac.partials):
            raise ValueError(f"{term}: a secondary {gate} value must always be set and open {graded}")
        gate_values: list[Any] = [None] if gate_facs else [o for o in options[gk] if o in opening]
        set_by_factor = {c for fac in fs for part in fac.partials for c in part}
        for b_idx, b in enumerate(baselines):
            cands: list[tuple[Any, ...]] = []
            for gv, x in product(gate_values, domain):
                base = list(none_state)
                if gv is not None:
                    base[gk] = gv
                base[xk] = x
                if gv is not None:
                    opened = {slots[f_] for g_, f_, op in spec.followups if g_ == gk and gv in op}
                    missing = opened - {graded} - set_by_factor
                    if missing:
                        raise ValueError(f"{term}: follow-ups {sorted(missing)} have no answer source")
                grades = set()
                for choice in product(*(range(fac.n) for fac in fs)):
                    st = list(base)
                    for fac, ci in zip(fs, choice, strict=True):
                        for code, val in fac.partials[ci].items():
                            st[slots.index(code)] = val
                    answers = {**none_answers, **spec.decode(tuple(st))}
                    grades.add(term_grade(term, answers, {BASELINE_KEY: b}))
                if grades == {g}:
                    cands.append(tuple(base))
                elif g in grades:
                    raise ValueError(f"{term}: a secondary item changes the grade of candidate {base}")
            if not cands:
                raise ValueError(f"{term}: no candidate answer grades {g} at baseline {b}")
            spec.candidates[(g, b_idx)] = len(cands)
            table = np.empty((len(cands), *(fac.n for fac in fs)), dtype=np.int64)
            for ci, cand in enumerate(cands):
                for choice in product(*(range(fac.n) for fac in fs)):
                    st = list(cand)
                    for fac, ch in zip(fs, choice, strict=True):
                        for code, val in fac.partials[ch].items():
                            st[slots.index(code)] = val
                    table[(ci, *choice)] = spec.state_id(tuple(st))
            spec.pre[(g, b_idx)] = table
    # mapping-error transitions from every pre-error state, then g_k of every reachable state
    spec.n_pre = len(spec.states)
    M = 1 << len(primary)
    spec.rec_mask = np.array([spec.recorded_bits(s) for s in spec.states], dtype=np.int64)
    trans = np.full((spec.n_pre, M, M), NULL, dtype=np.int64)
    for s in range(spec.n_pre):
        rec = int(spec.rec_mask[s])
        for e in range(M):
            if e & ~rec:
                continue
            for d in range(M):
                if d & ~e:
                    continue
                trans[s, e, d] = spec.state_id(spec.perturb(spec.states[s], e, d))
    spec.trans = trans
    tab = np.empty((len(spec.states), len(baselines)), dtype=np.int64)
    for s, ans in enumerate(spec.answer_dicts):
        for b_idx, b in enumerate(baselines):
            g = term_grade(term, {**none_answers, **ans}, {BASELINE_KEY: b})
            tab[s, b_idx] = NULL if g is None else g
    spec.grade_tab = tab
    return spec


# ---- model ------------------------------------------------------------------------------------------------


@dataclass
class Model:
    """Every constant of the data-generating mechanism, read once from params.yaml, data/signal_rules.json,
    the data files behind rules.py and the quote bank; plus the answer model and the red-flag level cache."""

    params: dict[str, Any]
    signal_rules: dict[str, Any]
    terms: tuple[str, ...]
    bands: tuple[int, ...]
    min_grade: int
    data_cut: int
    cycle: int
    call_offsets: np.ndarray
    study_start: date
    baselines: tuple[int, ...]
    baseline_probs: tuple[float, ...]
    specs: tuple[TermSpec, ...]
    n_factor_cols: int
    n_err_cols: int
    none_answers: dict[str, AnswerInput]
    active_red_flags: list[str]
    paged_ranks: tuple[int, ...]
    level_names: tuple[str, ...]
    base_logit: np.ndarray  # [T, max band + 1]
    synonyms: tuple[tuple[str, ...], ...]
    quotes: dict[str, dict[int, dict[str, list[dict[str, str]]]]]
    quote_counts: np.ndarray  # [T, max band + 1, len(LANGS)]
    quote_bank_sha256: str
    honest_label: str
    design: Design
    level_dims: tuple[int, ...] = ()
    level_cache: dict[int, int] = field(default_factory=dict)

    def term_index(self, term: str) -> int:
        return self.terms.index(term)

    def call_level(self, key: int) -> int:
        """Rank (rules.LEVEL_RANK) of the highest red-flag level on a call, cached per answer tuple."""
        rank = self.level_cache.get(key)
        if rank is None:
            parts = np.unravel_index(key, self.level_dims)
            answers = dict(self.none_answers)
            for spec, s in zip(self.specs, parts[:-1], strict=True):
                answers.update(spec.answer_dicts[int(s)])
            baseline = {BASELINE_KEY: self.baselines[int(parts[-1])]}
            hits = red_flags(answers, baseline, active_ids=self.active_red_flags)
            rank = self.level_cache[key] = LEVEL_RANK[level_for(hits)]
        return rank


# The text-valued choices of params.yaml this module implements (anything else is refused, never ignored).
SPECIFIED = {
    ("roster", "source"): "parametric",
    ("episodes", "start_day"): "uniform_over_days_on_study",
    ("episodes", "overlap"): "merge_same_term_max_grade",
    ("site_capture", "capture_unit"): "latent_episode",
    ("site_capture", "aeseq_order"): ["aestdtc", "entered_on", "symptomatic_first", "latent_start_day", "generation_order"],
    ("site_capture", "paged_capture_boost_logit"): 0,
    ("data_origin",): DATA_ORIGIN,
}


def _check_specified(params: Mapping[str, Any]) -> None:
    for path, want in SPECIFIED.items():
        got: Any = params
        for k in path:
            got = got[k]
        if got != want:
            raise ValueError(f"params.yaml {'.'.join(path)} = {got!r}; simulate.py implements {want!r} (docs/11 §11.2)")


def build_model(params: Mapping[str, Any] | None = None, repo: Path = REPO_ROOT) -> Model:
    """Build the data-generating model (deterministic: the same inputs give the same state ids and tables)."""
    params = dict(bvseed.load_params(repo) if params is None else params)
    signal_rules = json.loads((repo / bvseed.SIGNAL_RULES_REL).read_text(encoding="utf-8"))
    terms = tuple(signal_rules["primary_terms"])
    min_grade = int(signal_rules["min_grade"])
    sc = params["site_capture"]
    bands = tuple(sorted({int(g) for t in terms for g in sc["base_p"][t]}))
    if bands[0] != min_grade or len(bands) != len(range(bands[0], bands[-1] + 1)):
        raise ValueError(f"site_capture.base_p bands {bands} must be consecutive from min_grade {min_grade}")
    _check_specified(params)
    d = params["design"]
    cut, cycle = int(d["data_cut_day"]), int(d["cycle_days"])
    offsets = sorted(k * cycle + int(c) for k in range(cut // cycle + 1) for c in d["call_days_after_dose"])
    offsets_arr = np.array([o for o in offsets if o <= cut], dtype=np.int64)
    plan = content.plan_doc()
    if [int(x) for x in plan["schedule_days_after_dose"]] != [int(x) for x in d["call_days_after_dose"]]:
        raise ValueError("design.call_days_after_dose must equal data/plan.json schedule_days_after_dose")
    none_answers = {code: AnswerInput(option_code=_absent_option(code)) for code in plan["items"]}
    ag = params["answer_generation"]
    if ag["method"] != "enumerate_item_domain_grade_with_rules_py" or ag["non_episode_answer"] != "none_level":
        raise ValueError("answer_generation must enumerate the item domain and grade with rules.py (§11.2 step 4)")
    base = ag["baseline_stools"]
    baselines = tuple(int(b) for b in base["values"])
    baseline_probs = tuple(float(p) for p in base["p"])
    used: set[str] = set()
    specs = []
    fcol = ecol = 0
    for t, term in enumerate(terms):
        spec = _build_term(term, t, params, terms, bands, baselines, none_answers, used)
        spec.factor_col, spec.err_col = fcol, ecol
        fcol += spec.n_factor_cols
        ecol += len(spec.primary)
        specs.append(spec)
    unused = set(ag["secondary"]) - used
    if unused:
        raise ValueError(f"answer_generation.secondary blocks {sorted(unused)} match no term and grade")
    extra_items = [c for s in specs for c in s.slots if content.term_of(c) not in terms]
    if len(extra_items) != len(set(extra_items)):
        raise ValueError("two terms' secondary items set the same item")
    base_logit = np.full((len(terms), bands[-1] + 1), np.nan)
    for t, term in enumerate(terms):
        for g in bands:
            base_logit[t, g] = logit(float(sc["base_p"][term][g]))
    syn = signal_rules["match"]["term_synonyms"]
    synonyms = tuple(tuple(syn[t]) for t in terms)
    bank_raw = QUOTE_BANK_FILE.read_bytes()
    bank = json.loads(bank_raw.decode("utf-8"))
    if bank.get("data_origin") != DATA_ORIGIN or bank.get("source") != SOURCE:
        raise ValueError("quote_bank.json must be labeled data_origin SIMULATED and source synthetic")
    quotes: dict[str, dict[int, dict[str, list[dict[str, str]]]]] = {}
    counts = np.zeros((len(terms), bands[-1] + 1, len(LANGS)), dtype=np.int64)
    for t, term in enumerate(terms):
        for g in bands:
            for li, lang in enumerate(LANGS):
                entries = list(bank["quotes"][term][str(g)][lang])
                if not entries:
                    raise ValueError(f"quote_bank.json: no {lang} quote for {term} grade {g}")
                for e in entries:
                    if (lang != bvroster.ENGLISH) != ("translation_en" in e):
                        raise ValueError(f"quote_bank.json {term}/{g}/{lang}: a translation iff not English")
                quotes.setdefault(term, {}).setdefault(g, {})[lang] = entries
                counts[t, g, li] = len(entries)
    paged_levels = list(signal_rules["paged"]["levels"])
    level_names = tuple(sorted(LEVEL_RANK, key=LEVEL_RANK.__getitem__))
    honest = [s for s in params["planted"].values() if s["count"] == "rest"]
    if len(honest) != 1:
        raise ValueError("params.yaml planted needs exactly one role with count: rest (honest)")
    for spec in params["planted"].values():
        unknown = set(spec) - ROLE_KEYS
        if unknown:
            raise ValueError(f"planted role {spec['label']}: unknown keys {sorted(unknown)}")
    model = Model(
        params=params, signal_rules=signal_rules, terms=terms, bands=bands, min_grade=min_grade,
        data_cut=cut, cycle=cycle, call_offsets=offsets_arr, study_start=date.fromisoformat(str(d["study_start_date"])),
        baselines=baselines, baseline_probs=baseline_probs, specs=tuple(specs), n_factor_cols=fcol, n_err_cols=ecol,
        none_answers=none_answers, active_red_flags=list(plan["red_flag_ids"]),
        paged_ranks=tuple(LEVEL_RANK[lv] for lv in paged_levels), level_names=level_names,
        base_logit=base_logit, synonyms=synonyms, quotes=quotes, quote_counts=counts,
        quote_bank_sha256=hashlib.sha256(bank_raw).hexdigest(), honest_label=str(honest[0]["label"]),
        design=sap_design(params),
    )
    model.level_dims = tuple(len(s.states) for s in specs) + (len(baselines),)
    return model


@lru_cache(maxsize=1)
def default_model() -> Model:
    """The model of the committed params.yaml (built once per process)."""
    return build_model()


# ---- the study ----------------------------------------------------------------------------------------------


def children(key: np.random.SeedSequence) -> tuple[np.random.SeedSequence, np.random.SeedSequence]:
    """The replicate key's study child and comparator-resampling child (docs/11 §1.3).

    Built explicitly from ``spawn_key`` rather than ``key.spawn()``, which mutates the key, so a study stays a
    pure function of the key however often it is regenerated."""

    def child(c: int) -> np.random.SeedSequence:
        return np.random.SeedSequence(key.entropy, spawn_key=(*tuple(key.spawn_key), c), pool_size=key.pool_size)

    return child(STUDY_CHILD), child(RESAMPLING_CHILD)


@dataclass
class Study:
    """One simulated study (docs/11 §11.2 step 10), the single object every indicator reads (REQ-028).

    Site arrays have one entry per site (site-id order), patient arrays one per patient (site-major), call
    arrays one per scheduled call (scheduled date <= data cut), ordered by patient then date. Latent
    episodes are the data-generating episodes; site AE rows are the site's log, ordered by subject and
    ``aeseq``. Everything is SIMULATED."""

    model: Model = field(repr=False)
    key: np.random.SeedSequence
    resampling: np.random.SeedSequence
    design: Design
    scenario: Scenario
    roster: bvroster.Roster
    # sites
    role: tuple[str, ...]
    role_spec: tuple[Mapping[str, Any], ...]
    f: np.ndarray
    u: np.ndarray
    casemix: np.ndarray
    delta_es: np.ndarray
    completion_mean: np.ndarray
    slow_entry: np.ndarray
    site_eps: np.ndarray  # SE18 per-site error rate, nan where not drawn
    # patients
    baseline_stools: np.ndarray
    completion_p: np.ndarray
    patient_re: np.ndarray
    mapping_error: np.ndarray
    frailty: np.ndarray
    # scheduled calls
    call_pat: np.ndarray
    call_j: np.ndarray
    call_day: np.ndarray
    call_completed: np.ndarray
    call_state: np.ndarray  # [C, T] answer state id per term (NULL on a missed call)
    call_grade: np.ndarray  # [C, T] g_k (NULL = null)
    call_level: np.ndarray  # [C] rules.LEVEL_RANK of the call's level (NULL on a missed call)
    call_quote: np.ndarray  # [C, T] quote index (NULL unless g_k >= min_grade)
    call_n: np.ndarray  # [C] call number within the site (call_id sim_{site}_{nnnn})
    # latent episodes
    lat_pat: np.ndarray
    lat_term: np.ndarray
    lat_grade: np.ndarray
    lat_start: np.ndarray
    lat_k: np.ndarray
    lat_boost: np.ndarray
    lat_p: np.ndarray
    lat_captured: np.ndarray
    lat_row: np.ndarray  # site AE row index or NULL
    # site AE rows
    ae_pat: np.ndarray
    ae_aeseq: np.ndarray
    ae_aestdtc: np.ndarray
    ae_entered: np.ndarray
    ae_symptomatic: np.ndarray
    ae_term: np.ndarray  # primary term index, NULL for other AEs
    ae_grade: np.ndarray  # latent grade, NULL for other AEs
    ae_aeterm: tuple[str, ...]
    ae_source: np.ndarray  # latent episode index (symptomatic) or other-AE generation index
    ae_n: np.ndarray  # row number within the site (site_ae_id ae_{site}_{n})
    _cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # -- basic views --

    @property
    def data_origin(self) -> str:
        return DATA_ORIGIN

    @property
    def sites(self) -> bvroster.Sites:
        return self.roster.sites

    @property
    def terms(self) -> tuple[str, ...]:
        return self.model.terms

    @property
    def data_cut(self) -> int:
        return self.model.data_cut

    @property
    def pat_site(self) -> np.ndarray:
        return self.roster.pat_site

    @property
    def subject_ids(self) -> tuple[str, ...]:
        return self.roster.subject_ids

    def iso(self, day: int) -> str:
        return (self.model.study_start + timedelta(days=int(day))).isoformat()

    def days_on_study(self) -> np.ndarray:
        """Days from enrollment to the data cut per patient (x_i of §11.2 step 3 times data_cut_day)."""
        return self.data_cut - self.roster.enroll_day

    def dose_days(self) -> dict[str, list[int]]:
        """Every subject's dose visits (study days): enrollment + k x cycle up to the first one after the data
        cut, so the next dose visit of any episode dated up to the cut is known (docs/11 §6.1)."""
        out = self._cache.get("dose_days")
        if out is None:
            cyc, cut = self.model.cycle, self.data_cut
            out = {}
            for sid, e in zip(self.subject_ids, self.roster.enroll_day.tolist(), strict=True):
                days = list(range(e, cut + 1, cyc))
                days.append(days[-1] + cyc)
                out[sid] = days
            self._cache["dose_days"] = out
        return out

    def call_ids(self) -> list[str]:
        out = self._cache.get("call_ids")
        if out is None:
            site_ids = self.sites.ids
            sites = self.pat_site[self.call_pat].tolist()
            out = [f"sim_{site_ids[s]}_{n:04d}" for s, n in zip(sites, self.call_n.tolist(), strict=True)]
            self._cache["call_ids"] = out
        return out

    def site_ae_ids(self) -> list[str]:
        site_ids = self.sites.ids
        sites = self.pat_site[self.ae_pat].tolist()
        return [f"ae_{site_ids[s]}_{n}" for s, n in zip(sites, self.ae_n.tolist(), strict=True)]

    def level_name(self, rank: int) -> str | None:
        return None if rank < 0 else self.model.level_names[rank]

    # -- the answer key and sites --

    def answer_key(self) -> list[dict[str, Any]]:
        """§11.4: one row per site with its label, planted f (or null), honest-by-the-key, mechanism."""
        out = []
        for s, sid in enumerate(self.sites.ids):
            spec = self.role_spec[s]
            planted = {k: v for k, v in spec.items() if k not in ("label", "count")}
            out.append({
                "site_id": sid,
                "label": self.role[s],
                "f": float(spec["f"]) if "f" in spec else None,
                "honest": not any(k in spec for k in LOSS_KEYS),
                "planted": planted,
                "data_origin": DATA_ORIGIN,
            })
        return out

    def scheduled_and_completed(self) -> tuple[np.ndarray, np.ndarray]:
        """Scheduled calls (date <= data cut) and completed calls per site (the §7 coverage inputs)."""
        S = self.sites.n
        site = self.pat_site[self.call_pat]
        return (np.bincount(site, minlength=S), np.bincount(site, weights=self.call_completed, minlength=S))

    def site_records(self) -> list[dict[str, Any]]:
        """`Site` of docs/02 for every site (roster mix and call completion as realized in this study)."""
        S = self.sites.n
        n = np.bincount(self.pat_site, minlength=S)
        es = np.bincount(self.pat_site, weights=self.roster.spanish, minlength=S)
        xt = np.bincount(self.pat_site, weights=self.roster.extra_time, minlength=S)
        sched, done = self.scheduled_and_completed()
        out = []
        for s, sid in enumerate(self.sites.ids):
            out.append({
                "site_id": sid,
                "name": self.sites.names[s],
                "region": self.sites.regions[s],
                "n_patients": int(n[s]),
                "spanish_share": float(es[s] / n[s]) if n[s] else 0.0,
                "extra_time_share": float(xt[s] / n[s]) if n[s] else 0.0,
                "call_completion": float(done[s] / sched[s]) if sched[s] else 0.0,
                "is_live_site": s == self.sites.live_index,
                "data_origin": DATA_ORIGIN,
            })
        return out

    # -- inputs for app.services.episodes (plain lists) --

    def episode_calls(self) -> dict[str, list[dict[str, Any]]]:
        """Completed calls per subject in date order, in the `episodes.py` call shape (date = study day)."""
        out = self._cache.get("episode_calls")
        if out is None:
            comp = np.flatnonzero(self.call_completed)
            ids = self.call_ids()
            subj = self.subject_ids
            terms = self.terms
            names = self.model.level_names
            out = {}
            pats = self.call_pat[comp].tolist()
            days = self.call_day[comp].tolist()
            levels = self.call_level[comp].tolist()
            grades = self.call_grade[comp].tolist()
            for c, p, d, lv, gs in zip(comp.tolist(), pats, days, levels, grades, strict=True):
                sid = subj[p]
                calls = out.get(sid)
                if calls is None:
                    calls = out[sid] = []
                calls.append({
                    "call_id": ids[c], "subject_id": sid, "date": d, "status": COMPLETED,
                    "grades": {t: (g if g >= 0 else None) for t, g in zip(terms, gs, strict=True)},
                    "level": names[lv],
                })
            self._cache["episode_calls"] = out
        return out

    def site_ae_rows(self, *, iso_dates: bool = False) -> list[dict[str, Any]]:
        """The site AE log, one `SiteAE` (docs/02) per row; study-day dates unless `iso_dates`."""
        ids = self.site_ae_ids()
        subj = self.subject_ids
        site_ids = self.sites.ids
        sites = self.pat_site[self.ae_pat].tolist()
        conv = self.iso if iso_dates else (lambda x: x)
        rows = []
        for r, (p, seq, a, e, sym, g) in enumerate(zip(
                self.ae_pat.tolist(), self.ae_aeseq.tolist(), self.ae_aestdtc.tolist(), self.ae_entered.tolist(),
                self.ae_symptomatic.tolist(), self.ae_grade.tolist(), strict=True)):
            rows.append({
                "site_ae_id": ids[r], "site_id": site_ids[sites[r]], "subject_id": subj[p],
                "usubjid": f"{USUBJID_PREFIX}-{subj[p]}", "aeseq": seq, "aeterm": self.ae_aeterm[r],
                "aetoxgr": str(g) if g >= 0 else "", "aestdtc": conv(a), "entered_on": conv(e),
                "origin": SITE_ORIGIN, "symptomatic": bool(sym), "data_origin": DATA_ORIGIN,
            })
        return rows

    def site_aes_by_subject(self) -> dict[str, list[dict[str, Any]]]:
        """Site AE rows per subject (study-day dates), for per-subject calls of `episodes.py`."""
        out = self._cache.get("site_aes_by_subject")
        if out is None:
            out = {}
            for row in self.site_ae_rows():
                out.setdefault(row["subject_id"], []).append(row)
            self._cache["site_aes_by_subject"] = out
        return out

    # -- answers and evidence --

    def call_answers(self, c: int) -> tuple[dict[str, AnswerInput], dict[str, Any]]:
        """The generated answers of scheduled call `c` (every plan item and opened follow-up) and the baseline."""
        answers = dict(self.model.none_answers)
        for t, spec in enumerate(self.model.specs):
            answers.update(spec.answer_dicts[int(self.call_state[c, t])])
        return answers, {BASELINE_KEY: int(self.baseline_stools[self.call_pat[c]])}

    def evidence(self, checkin_id: str, term: str) -> dict[str, Any] | None:
        """§11.2 step 9: the synthetic quote of a reporting call and term (an episode uses its first call)."""
        index = self._cache.get("call_index")
        if index is None:
            index = self._cache["call_index"] = {cid: c for c, cid in enumerate(self.call_ids())}
        c = index[checkin_id]
        t = self.model.term_index(term)
        q = int(self.call_quote[c, t])
        if q < 0:
            return None
        lang = LANGS[int(self.roster.spanish[self.call_pat[c]])]
        entry = self.model.quotes[term][int(self.call_grade[c, t])][lang][q]
        return {
            "quote": entry["quote"], "quote_lang": lang, "translation_en": entry.get("translation_en"),
            "translation_is_ai": "translation_en" in entry, "t_s": None, "source": SOURCE, "checkin_id": None,
            "data_origin": DATA_ORIGIN,
        }

    def resampling_key(self, comparator: str) -> np.random.SeedSequence:
        """A comparator's own resampling key: a child of the replicate's resampling child, indexed by the
        comparator's position in params.yaml `comparators`, so adding or cutting a comparator never changes the
        study or another comparator's draws (docs/11 §1.3)."""
        names = list(self.model.params["comparators"])
        k = self.resampling
        return np.random.SeedSequence(k.entropy, spawn_key=(*tuple(k.spawn_key), names.index(comparator)),
                                      pool_size=k.pool_size)

    # -- serialization --

    def to_dict(self) -> dict[str, Any]:
        """The whole study as canonical JSON-able data (every object carries data_origin)."""
        m = self.model
        subj = self.subject_ids
        site_ids = self.sites.ids
        comp = self.call_completed
        terms = self.terms

        def col(a: np.ndarray) -> list[Any]:
            return a.tolist()

        def nullable(a: np.ndarray) -> list[Any]:
            return [None if x < 0 else x for x in a.tolist()]

        return {
            "_about": ABOUT,
            "data_origin": DATA_ORIGIN,
            "key": {"entropy": int(self.key.entropy), "spawn_key": [int(x) for x in self.key.spawn_key]},
            "design": self.design.to_dict(),
            "scenario": self.scenario.to_dict(),
            "study_start_date": m.study_start.isoformat(),
            "data_cut_day": self.data_cut,
            "data_cut_date": self.iso(self.data_cut),
            "quote_bank_sha256": m.quote_bank_sha256,
            "sites": self.site_records(),
            "answer_key": self.answer_key(),
            "site_params": {
                "data_origin": DATA_ORIGIN, "site_id": list(site_ids), "f": col(self.f), "u": col(self.u),
                "casemix": col(self.casemix), "delta_es": col(self.delta_es), "spanish_share": col(self.roster.spanish_share),
                "completion_mean": col(self.completion_mean), "slow_entry": col(self.slow_entry),
                "site_eps": [None if math.isnan(x) else x for x in self.site_eps.tolist()],
            },
            "subjects": {
                "data_origin": DATA_ORIGIN, "subject_id": list(subj), "site_id": [site_ids[s] for s in self.pat_site.tolist()],
                "language": self.roster.language(), "pace": self.roster.pace(), "age": col(self.roster.age),
                "enroll_day": col(self.roster.enroll_day), "baseline_stools": col(self.baseline_stools),
                "completion_p": col(self.completion_p), "patient_re": col(self.patient_re),
                "mapping_error": col(self.mapping_error), "frailty": col(self.frailty),
            },
            "calls": {
                "data_origin": DATA_ORIGIN, "call_id": self.call_ids(), "subject_id": [subj[p] for p in self.call_pat.tolist()],
                "day": col(self.call_day), "status": [COMPLETED if x else MISSED for x in comp.tolist()],
                "level": [self.level_name(x) for x in self.call_level.tolist()],
                "grades": {t: nullable(self.call_grade[:, i]) for i, t in enumerate(terms)},
                "answer_state": {t: nullable(self.call_state[:, i]) for i, t in enumerate(terms)},
                "quote": {t: nullable(self.call_quote[:, i]) for i, t in enumerate(terms)},
            },
            "answer_states": {
                spec.term: {"data_origin": DATA_ORIGIN, "slots": list(spec.slots),
                            "states": [spec.readable(s) for s in range(len(spec.states))]}
                for spec in m.specs
            },
            "latent_episodes": {
                "data_origin": DATA_ORIGIN, "subject_id": [subj[p] for p in self.lat_pat.tolist()],
                "term": [terms[t] for t in self.lat_term.tolist()], "grade": col(self.lat_grade),
                "start_day": col(self.lat_start), "duration_calls": col(self.lat_k), "boost": col(self.lat_boost),
                "p_capture": col(self.lat_p), "captured": col(self.lat_captured), "site_ae_row": nullable(self.lat_row),
            },
            "site_ae": self.site_ae_rows(iso_dates=True),
        }

    def digest(self) -> str:
        """sha256 of the canonical JSON of :meth:`to_dict` (the determinism check)."""
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _pick(u: np.ndarray, n: np.ndarray | int) -> np.ndarray:
    """Uniform index in [0, n) from a uniform draw."""
    return np.minimum(np.floor(u * n).astype(np.int64), np.asarray(n) - 1)


def _resolve_roles(model: Model, roles: str | Sequence[Role]) -> tuple[Role, ...]:
    if roles == "full_mix":
        return full_mix_roles(model.params)
    if roles == "null":
        return ()
    if isinstance(roles, str):
        raise ValueError(f"roles must be 'full_mix', 'null' or a sequence of (label, spec), got {roles!r}")
    out = tuple((str(label), dict(spec)) for label, spec in roles)
    for label, spec in out:
        unknown = set(spec) - ROLE_KEYS
        if unknown:
            raise ValueError(f"role {label}: unknown keys {sorted(unknown)}")
    return out


def simulate(key: np.random.SeedSequence, model: Model | None = None, *, design: Design | None = None,
             roles: str | Sequence[Role] = "full_mix", scenario: Scenario | None = None) -> Study:
    """One simulated study (docs/11 §11.2), a pure function of (params, design, roles, scenario, key).

    `roles`: "full_mix" (the §11.4 planted truth), "null" (every site honest, §9.1) or a sequence of
    (label, spec) roles planted on distinct random non-101 sites (e.g. :func:`planted_roles`). The planted
    sites are drawn first and every later draw is made whatever the roles, f or scenario, so studies with the
    same key share their random numbers (common random numbers across f, §12.2)."""
    m = default_model() if model is None else model
    design = m.design if design is None else design
    scenario = Scenario() if scenario is None else scenario
    p = m.params
    study_key, resampling_key = children(key)
    rng = np.random.Generator(np.random.PCG64(study_key))
    T, cut = len(m.terms), m.data_cut
    offsets = m.call_offsets
    J = offsets.size

    # 1. roster and planted roles (§11.2 step 1, §11.4)
    sites = bvroster.study_sites(p, design.n_sites)
    S = sites.n
    role_list = _resolve_roles(m, roles)
    non_live = np.array([s for s in range(S) if s != sites.live_index], dtype=np.int64)
    if len(role_list) > non_live.size:
        raise ValueError(f"{len(role_list)} planted roles need more than the {non_live.size} non-live sites")
    perm = rng.permutation(non_live)
    role = [m.honest_label] * S
    role_spec: list[Mapping[str, Any]] = [{}] * S
    for k, (label, spec) in enumerate(role_list):
        role[int(perm[k])] = label
        role_spec[int(perm[k])] = spec
    overrides = {s: {k: spec[k] for k in bvroster.ROSTER_OVERRIDES if k in spec}
                 for s, spec in enumerate(role_spec) if any(k in spec for k in bvroster.ROSTER_OVERRIDES)}
    roster = bvroster.draw_roster(rng, p, sites, design.patients_per_site, overrides)
    pat_site, enroll = roster.pat_site, roster.enroll_day
    P = roster.n_patients_total

    # site effects: case mix, honest capture variation, scenario site selections
    ep, sc, ps = p["episodes"], p["site_capture"], p["patient_stream"]
    z_casemix = rng.standard_normal(S)
    z_u = rng.standard_normal(S)
    u_slow = rng.random(S)
    u_site_eps_pick = rng.random(S)
    u_site_eps = rng.random(S)
    casemix_sd = float(ep["casemix_sd_log"]) if scenario.casemix_sd_log is None else scenario.casemix_sd_log
    between_sd = float(sc["between_site_sd_logit"]) if scenario.between_site_sd_logit is None else scenario.between_site_sd_logit
    casemix = np.exp(float(ep["casemix_meanlog"]) + casemix_sd * z_casemix)
    u_site = between_sd * z_u
    cc = ps["call_completion"]
    if cc["dist"] != "beta":
        raise ValueError("patient_stream.call_completion must be a beta distribution (docs/11 §11.3)")
    kappa = float(cc["kappa"]) if scenario.call_completion_kappa is None else scenario.call_completion_kappa
    base_mean = float(cc["mean"]) if scenario.call_completion_mean is None else scenario.call_completion_mean
    completion_mean = np.full(S, base_mean)
    f = np.zeros(S)
    delta = np.zeros(S)
    for s, spec in enumerate(role_spec):
        if "casemix" in spec:
            casemix[s] = float(spec["casemix"])
        if "u_s_between_site_sds" in spec:
            u_site[s] = float(spec["u_s_between_site_sds"]) * between_sd
        if "call_completion_mean" in spec:
            completion_mean[s] = float(spec["call_completion_mean"])
        if "f" in spec:
            f[s] = float(spec["f"])
        if "spanish_capture_odds_ratio" in spec:
            delta[s] = math.log(float(spec["spanish_capture_odds_ratio"]))
    eligible_slow = np.array([s != sites.live_index and role[s] == m.honest_label for s in range(S)])
    slow_entry = np.zeros(S, dtype=bool)
    if scenario.slow_entry_lag_mean_days is not None:
        cand = np.flatnonzero(eligible_slow)
        slow_entry[cand[np.argsort(u_slow[cand], kind="stable")][: scenario.slow_entry_n_sites]] = True
    site_eps = np.full(S, np.nan)
    if scenario.site_mapping_error is not None:
        cand = non_live[np.argsort(u_site_eps_pick[non_live], kind="stable")][: scenario.site_mapping_error_n_sites]
        a_s, b_s = scenario.site_mapping_error
        site_eps[cand] = betaincinv(a_s, b_s, u_site_eps[cand])

    # 2. patients: capture effect, completion and mapping error (Gaussian copula in SE16, independent otherwise)
    z = rng.standard_normal((P, len(COPULA)))
    if scenario.copula is not None:
        r_v_pi, r_v_eps, r_pi_eps = scenario.copula
        sigma = np.eye(len(COPULA))
        iv, ipi, ieps = (COPULA.index(n) for n in ("v", "pi", "eps"))
        sigma[iv, ipi] = sigma[ipi, iv] = r_v_pi
        sigma[iv, ieps] = sigma[ieps, iv] = r_v_eps
        sigma[ipi, ieps] = sigma[ieps, ipi] = r_pi_eps
        z = z @ np.linalg.cholesky(sigma).T
    z_v, z_pi, z_eps = (z[:, COPULA.index(n)] for n in ("v", "pi", "eps"))
    fr = ep["patient_frailty"]
    if fr["dist"] != "gamma":
        raise ValueError("episodes.patient_frailty must be a gamma distribution (docs/11 §11.3)")
    frailty = rng.gamma(float(fr["shape"]), float(fr["scale"]), size=P)
    u_base = rng.random(P)
    re_sd = float(sc["patient_re_sd_logit"]) if scenario.patient_re_sd_logit is None else scenario.patient_re_sd_logit
    v = re_sd * z_v
    cm = completion_mean[pat_site]
    pi = betaincinv(cm * kappa, (1 - cm) * kappa, ndtr(z_pi))
    me = ps["mapping_error_per_answer"]
    if me["dist"] != "beta":
        raise ValueError("patient_stream.mapping_error_per_answer must be a beta distribution (docs/11 §11.3)")
    eps = betaincinv(float(me["a"]), float(me["b"]), ndtr(-z_eps))
    has_site_eps = ~np.isnan(site_eps[pat_site])
    eps = np.where(has_site_eps, site_eps[pat_site], eps)
    if scenario.mapping_error_multiplier is not None:
        lang = np.array(roster.language())
        sel = np.ones(P, dtype=bool) if scenario.mapping_error_language is None else lang == scenario.mapping_error_language
        eps = np.where(sel, np.minimum(eps * scenario.mapping_error_multiplier, 1), eps)
    baseline_idx = np.minimum(np.searchsorted(np.cumsum(m.baseline_probs), u_base, side="right"), len(m.baselines) - 1)
    baseline_stools = np.asarray(m.baselines, dtype=np.int64)[baseline_idx]

    # 3. latent episodes (§11.2 step 3)
    days_on = cut - enroll
    x = days_on / cut
    n_lat = rng.poisson(design.mu * casemix[pat_site] * frailty * x)
    lat_pat = np.repeat(np.arange(P), n_lat)
    L = lat_pat.size
    u_term = rng.random(L)
    u_g3 = rng.random(L)
    u_start = rng.random(L)
    if ep["duration_dist"] != "geometric":
        raise ValueError("episodes.duration_dist must be geometric (docs/11 §11.2 step 3)")
    lat_k = rng.geometric(1 / float(ep["mean_duration_calls"]), size=L)
    u_cap = rng.random(L)
    lag_shape = float(sc["entry_lag_days"]["shape"])
    if sc["entry_lag_days"]["dist"] != "gamma":
        raise ValueError("site_capture.entry_lag_days must be a gamma distribution (docs/11 §11.3)")
    noise = rng.normal(0, float(sc["aestdtc_noise_days_sd"]), size=L)
    lag_lat = rng.standard_gamma(lag_shape, size=L)
    u_syn = rng.random(L)
    term_cum = np.cumsum([float(ep["term_mix"][t]) for t in m.terms])
    lat_term = np.minimum(np.searchsorted(term_cum, u_term, side="right"), T - 1)
    lat_grade = np.where(u_g3 < float(ep["g3_share"]), m.bands[-1], m.bands[0])
    lat_start = enroll[lat_pat] + np.floor(u_start * days_on[lat_pat]).astype(np.int64)

    # 2 (cont.). schedule and completion; 4-5. answers and mapping error (draws for every grid cell)
    valid = offsets[None, :] <= days_on[:, None]
    u_comp = rng.random((P, J))
    u_cand = rng.random((P, J, T))
    u_fac = rng.random((P, J, m.n_factor_cols))
    u_err = rng.random((P, J, m.n_err_cols))
    u_dir = rng.random((P, J, m.n_err_cols))
    u_quote = rng.random((P, J, T))
    completed = valid & (u_comp < pi[:, None])
    # latent grade per call and term: max over the patient's same-term episodes covering it (merge, §11.2 step 3)
    n_valid = valid.sum(axis=1)
    j0 = np.searchsorted(offsets, lat_start - enroll[lat_pat], side="left")
    kc = np.clip(np.minimum(lat_k, n_valid[lat_pat] - j0), 0, None)
    rep = np.repeat(np.arange(L), kc)
    jj = j0[rep] + (np.arange(rep.size) - np.repeat(np.cumsum(kc) - kc, kc))
    latent = np.zeros((P, J, T), dtype=np.int64)
    np.maximum.at(latent, (lat_pat[rep], jj, lat_term[rep]), lat_grade[rep])

    cp, cj = np.nonzero(completed)
    Cc = cp.size
    b_c = baseline_idx[cp]
    lat_c = latent[cp, cj]
    ucand, ufac, uq = u_cand[cp, cj], u_fac[cp, cj], u_quote[cp, cj]
    err_c = u_err[cp, cj] < eps[cp][:, None]
    p_up = float(ps["mapping_error_step"]["p_up"])
    up_c = u_dir[cp, cj] < p_up
    post = np.empty((Cc, T), dtype=np.int64)
    grades = np.empty((Cc, T), dtype=np.int64)
    for spec in m.specs:
        t = spec.index
        pre = np.zeros(Cc, dtype=np.int64)  # state 0 is the none state
        for (g, bi), table in spec.pre.items():
            sel = np.flatnonzero((lat_c[:, t] == g) & (b_c == bi))
            if not sel.size:
                continue
            idx = [_pick(ucand[sel, t], table.shape[0])]
            for fpos, fac in enumerate(spec.factors[g]):
                idx.append(fac.choose(ufac[sel, spec.factor_col + fpos]))
            pre[sel] = table[tuple(idx)]
        cols = slice(spec.err_col, spec.err_col + len(spec.primary))
        w = spec.bit_weights
        e = (err_c[:, cols] * w).sum(axis=1) & spec.rec_mask[pre]
        d = (up_c[:, cols] * w).sum(axis=1) & e
        post[:, t] = spec.trans[pre, e, d]
        grades[:, t] = spec.grade_tab[post[:, t], b_c]
    if (post < 0).any():
        raise RuntimeError("an answer state outside the enumerated transitions")
    # 6. red flags and paging, cached per answer tuple
    keys = np.ravel_multi_index((*(post[:, t] for t in range(T)), b_c), m.level_dims)
    uniq, inv_k = np.unique(keys, return_inverse=True)
    levels_c = np.array([m.call_level(int(k)) for k in uniq.tolist()], dtype=np.int64)[inv_k.ravel()]
    # 9. evidence: one quote per reporting call and term
    lang_idx = roster.spanish.astype(np.int64)[cp]
    quote_c = np.full((Cc, T), NULL, dtype=np.int64)
    for t in range(T):
        sel = np.flatnonzero(grades[:, t] >= m.min_grade)
        n_q = m.quote_counts[t, grades[sel, t], lang_idx[sel]]
        quote_c[sel, t] = _pick(uq[sel, t], n_q)

    # scheduled calls (patient-major, then date)
    sp, sj = np.nonzero(valid)
    C = sp.size
    comp_s = completed[sp, sj]
    call_state = np.full((C, T), NULL, dtype=np.int64)
    call_grade = np.full((C, T), NULL, dtype=np.int64)
    call_level = np.full(C, NULL, dtype=np.int64)
    call_quote = np.full((C, T), NULL, dtype=np.int64)
    call_state[comp_s], call_grade[comp_s], call_level[comp_s], call_quote[comp_s] = post, grades, levels_c, quote_c
    call_site = pat_site[sp]
    call_n = np.arange(C) - np.searchsorted(call_site, call_site, side="left") + 1
    call_day = enroll[sp] + offsets[sj]

    # 7. site capture of each latent episode (SE15 boost when the scenario asks for it)
    lat_site = pat_site[lat_pat]
    boost = np.zeros(L)
    if scenario.capture_boost_logit is not None:
        paged_c = np.isin(levels_c, m.paged_ranks)
        paged_grid = np.zeros((P, J), dtype=bool)
        paged_grid[cp, cj] = paged_c
        n_comp = np.bincount(pat_site[cp], minlength=S)
        n_paged = np.bincount(pat_site[cp], weights=paged_c, minlength=S)
        share = np.divide(n_paged, n_comp, out=np.zeros(S), where=n_comp > 0)
        top = np.lexsort((np.arange(S), -share))[: scenario.capture_boost_n_sites]  # ties: lower site id
        day_grid = enroll[:, None] + offsets[None, :]
        near = (np.abs(lat_start[:, None] - day_grid[lat_pat]) <= scenario.capture_boost_within_days) & paged_grid[lat_pat]
        boost = np.where(np.isin(lat_site, top) & near.any(axis=1), scenario.capture_boost_logit, 0)
    lin = (m.base_logit[lat_term, lat_grade] + u_site[lat_site] + v[lat_pat]
           + np.where(roster.spanish[lat_pat], delta[lat_site], 0) + boost)
    lat_p = (1 - f[lat_site]) * expit(lin)
    lat_captured = u_cap < lat_p
    lag_mean = float(sc["entry_lag_days"]["mean"])
    lag_scale = np.where(slow_entry, (scenario.slow_entry_lag_mean_days or lag_mean) / lag_shape, lag_mean / lag_shape)

    def entered_on(pat: np.ndarray, aest: np.ndarray, lag_std: np.ndarray) -> np.ndarray:
        e0 = enroll[pat]
        dose_on_after = e0 + m.cycle * np.maximum(0, -((e0 - aest) // m.cycle))
        return dose_on_after + np.ceil(lag_std * lag_scale[pat_site[pat]]).astype(np.int64)

    cap = np.flatnonzero(lat_captured)
    s_pat = lat_pat[cap]
    s_aest = lat_start[cap] + np.rint(noise[cap]).astype(np.int64)
    s_entered = entered_on(s_pat, s_aest, lag_lat[cap])
    s_aeterm = [m.synonyms[t][i] for t, i in zip(
        lat_term[cap].tolist(),
        _pick(u_syn[cap], np.array([len(m.synonyms[t]) for t in lat_term[cap].tolist()], dtype=np.int64)).tolist(),
        strict=True)]

    # 8. other (non-symptomatic) AEs, dropped with probability f_s at planted sites
    n_oth = rng.poisson(float(sc["other_aes_per_patient_window"]) * casemix[pat_site] * frailty * x)
    o_pat = np.repeat(np.arange(P), n_oth)
    n_other = o_pat.size
    u_ostart = rng.random(n_other)
    lag_oth = rng.standard_gamma(lag_shape, size=n_other)
    u_drop = rng.random(n_other)
    u_oterm = rng.random(n_other)
    keep = np.flatnonzero(~(u_drop < f[pat_site[o_pat]]))
    o_pat_k = o_pat[keep]
    o_aest = enroll[o_pat_k] + np.floor(u_ostart[keep] * days_on[o_pat_k]).astype(np.int64)
    o_entered = entered_on(o_pat_k, o_aest, lag_oth[keep])
    o_aeterm = [OTHER_AE_TERMS[i] for i in _pick(u_oterm[keep], len(OTHER_AE_TERMS)).tolist()]

    # site AE rows and aeseq (§11.2 step 7): by AESTDTC, entered_on, symptomatic first, latent start, generation
    r_pat = np.concatenate([s_pat, o_pat_k])
    r_aest = np.concatenate([s_aest, o_aest])
    r_entered = np.concatenate([s_entered, o_entered])
    r_sym = np.concatenate([np.ones(cap.size, dtype=bool), np.zeros(keep.size, dtype=bool)])
    r_start = np.concatenate([lat_start[cap], o_aest])
    r_gen = np.arange(r_pat.size)
    r_term = np.concatenate([lat_term[cap], np.full(keep.size, NULL, dtype=np.int64)])
    r_grade = np.concatenate([lat_grade[cap], np.full(keep.size, NULL, dtype=np.int64)])
    r_source = np.concatenate([cap, keep])
    r_aeterm = s_aeterm + o_aeterm
    order = np.lexsort((r_gen, r_start, ~r_sym, r_entered, r_aest, r_pat))
    sorted_pat = r_pat[order]
    aeseq = np.arange(order.size) - np.searchsorted(sorted_pat, sorted_pat, side="left") + 1
    sorted_site = pat_site[sorted_pat]
    ae_n = np.arange(order.size) - np.searchsorted(sorted_site, sorted_site, side="left") + 1
    lat_row = np.full(L, NULL, dtype=np.int64)
    sym_pos = np.flatnonzero(r_sym[order])
    lat_row[r_source[order][sym_pos]] = sym_pos

    return Study(
        model=m, key=key, resampling=resampling_key, design=design, scenario=scenario, roster=roster,
        role=tuple(role), role_spec=tuple(role_spec), f=f, u=u_site, casemix=casemix, delta_es=delta,
        completion_mean=completion_mean, slow_entry=slow_entry, site_eps=site_eps,
        baseline_stools=baseline_stools, completion_p=pi, patient_re=v, mapping_error=eps, frailty=frailty,
        call_pat=sp, call_j=sj, call_day=call_day, call_completed=comp_s, call_state=call_state,
        call_grade=call_grade, call_level=call_level, call_quote=call_quote, call_n=call_n,
        lat_pat=lat_pat, lat_term=lat_term, lat_grade=lat_grade, lat_start=lat_start, lat_k=lat_k,
        lat_boost=boost, lat_p=lat_p, lat_captured=lat_captured, lat_row=lat_row,
        ae_pat=sorted_pat, ae_aeseq=aeseq, ae_aestdtc=r_aest[order], ae_entered=r_entered[order],
        ae_symptomatic=r_sym[order], ae_term=r_term[order], ae_grade=r_grade[order],
        ae_aeterm=tuple(r_aeterm[i] for i in order.tolist()), ae_source=r_source[order], ae_n=ae_n,
    )


# ---- command line (dev seed only) ------------------------------------------------------------------------


def _refuse_committed_dir(out: Path) -> None:
    for rel in ("monitoring/out", "validation/site_signal"):
        target = (REPO_ROOT / rel).resolve()
        if out.resolve() == target or target in out.resolve().parents:
            raise SystemExit(f"simulate.py: development output never goes to {rel}/ (docs/11 §1.3); use a scratch directory")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Simulate Site Signal studies with the dev seed (docs/11 §11.2). SIMULATED.")
    ap.add_argument("--seed", default="dev", choices=["dev"], help="the dev seed only (params.yaml seeds.dev)")
    ap.add_argument("--studies", type=int, default=1, help="number of studies (replicate keys i = 0..n-1)")
    ap.add_argument("--with-episodes", action="store_true", help="also time app.services.episodes per subject")
    ap.add_argument("--out", type=Path, default=None, help="scratch directory for study JSON (never monitoring/out)")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    model = default_model()
    build_s = time.perf_counter() - t0
    params = model.params
    seed = bvseed.resolve_seed(args.seed)
    stream, cell, role = (int(params["streams"]["committed_study"]), int(params["cell_index"]["none"]),
                          int(params["roles"]["null_or_committed"]))
    if args.out is not None:
        _refuse_committed_dir(args.out)
        args.out.mkdir(parents=True, exist_ok=True)
    from bvsignal._backend import episodes  # timing only: match.py owns the episode analysis (S3)

    sim_s, ep_s = [], []
    for i in range(args.studies):
        t1 = time.perf_counter()
        st = simulate(bvseed.key(stream, cell, role, i, seed=seed), model)
        t2 = time.perf_counter()
        sim_s.append(t2 - t1)
        n_ep = None
        if args.with_episodes:
            cfg = model.signal_rules
            aes, doses = st.site_aes_by_subject(), st.dose_days()
            n_ep = 0
            for sid, calls in st.episode_calls().items():
                n_ep += len(episodes.analyze(calls, aes.get(sid, []), cfg, data_cut=st.data_cut,
                                             dose_dates={sid: doses[sid]}))
            ep_s.append(time.perf_counter() - t2)
        line = (f"study {i}: {sim_s[-1]:.3f} s simulate, {st.roster.n_patients_total} patients, "
                f"{int(st.call_completed.sum())} completed calls, {st.lat_pat.size} latent episodes, "
                f"{st.ae_pat.size} site AE rows")
        if n_ep is not None:
            line += f", {n_ep} episodes in {ep_s[-1]:.3f} s"
        print(line)
        if args.out is not None:
            path = args.out / f"study_{args.seed}_{i}.json"
            path.write_text(json.dumps(st.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                            encoding="utf-8")
            print(f"  wrote {path} (sha256 of the canonical study {st.digest()})")
    print(f"model build {build_s:.3f} s; mean simulate {np.mean(sim_s):.3f} s per study"
          + (f"; mean episodes.py {np.mean(ep_s):.3f} s per study" if ep_s else "")
          + f" ({DATA_ORIGIN}, dev seed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
