"""Pre-tag planning grid for Site Signal (docs/11-site-signal-sap.md §11.5). Planning only, not a result.

Runs the simplified model of SAP §11.5 with the dev seed and applies, in this order:

* Rule P1 (design feasibility): for each patients-per-site range in params.yaml ``planning.p1.ranges``
  (15-30, 20-40, 30-60, 40-80), 200 studies with the §11.4 composition at mu = 1.5; the first range whose
  mean number of computed sites is >= 15 of the 18 sites not designed to be grey AND whose share of
  studies below the 10-site minimum is <= 0.02 is chosen (else 40-80, shortfall recorded).
* Rule P2 (gross capture loss): at the chosen design, planning Look and Watch thresholds from 1000 null
  studies (§9.2-9.3), then 500 studies per f in {0.75, 0.80, 0.85, 0.90} with one planted site and
  common random numbers across f; the smallest f whose one-sided 80% lower bound
  p - 0.842 * sqrt(p(1 - p) / 500) of Watch power is >= 0.80 is chosen (else 0.90, shortfall recorded).

Simplified model (§11.5): roster, schedule, call completion, latent episodes, site capture, AESTDTC noise,
entry lag, episode construction (§4.2), evaluability (§6.1), the §5 match rule, the §7 guards and the §8
indicator are as in the SAP. Paging is decided per cell (term x grade) from paged shares computed once by
running the real ``rules.red_flags()`` over the enumerated candidate answers (graded by the real
``rules.grade()``) with the params.yaml secondary-item probabilities; Fever and grade 3 come out always
paged (§4.4). An episode is paged if any of its calls paged for any term. There is no mapping error and
no comparator. In P1 the planted capture losses (f, the language gap and the low-diligence offset) are
ignored, as §11.5 allows, because they do not change computability.

Every number comes from monitoring/params.yaml or data/signal_rules.json. Replicate keys are
``SeedSequence(dev_seed, spawn_key=(planning.stream, cell_index, role, i))`` with the planning cells of
params.yaml ``cell_index.planning``. Output: ``planning_grid.json``, labeled "planning only, not a
result"; it is never quoted as a result (docs/11 §15 rule 1). SIMULATED data only; no LLM.

Usage (Makefile target ``planning-grid``)::

    uv run --project monitoring python monitoring/planning/plan_power.py --seed dev --out monitoring/planning/planning_grid.json
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.special import expit, logit

from bvsignal import REPO_ROOT
from bvsignal import seed as bvseed

ABOUT = "planning only, not a result"
REASONS = ("computed", "error", "integrated_mode", "low_coverage", "insufficient_patients",
           "insufficient_episodes", "study_below_min_sites")
COMPUTED, LOW_COVERAGE, INSUFFICIENT_PATIENTS, INSUFFICIENT_EPISODES, STUDY_BELOW = (
    REASONS.index("computed"), REASONS.index("low_coverage"), REASONS.index("insufficient_patients"),
    REASONS.index("insufficient_episodes"), REASONS.index("study_below_min_sites"))
NO_DAY = -(10**6)  # "no such call" sentinel for the match lower anchor


# ---- inputs ----------------------------------------------------------------------------------------


def paged_shares(params: dict[str, Any], signal_rules: dict[str, Any]) -> dict[str, Any]:
    """Per-call paged share per (term, grade) from the real rules engine (docs/11 §11.5).

    For each primary term and grade band: enumerate the item domain (the gate options that open the
    grading follow-up x the graded item's domain, each baseline stools value), keep the candidates that
    `rules.grade()` gives that grade, combine each with the secondary-item answers and their
    probabilities, and run `rules.red_flags()` (the plan's active red flags) on the full call, every
    other item answered at its "none" level. Candidates are equally likely (§11.2 step 4)."""
    from bvsignal._backend import ABSENT_OPTIONS, AnswerInput, content, grade, level_for, red_flags

    ag = params["answer_generation"]
    items = content.items_doc()["items"]
    plan = content.plan_doc()
    active = list(plan["red_flag_ids"])
    paged_levels = set(signal_rules["paged"]["levels"])
    terms = list(signal_rules["primary_terms"])
    min_grade = int(signal_rules["min_grade"])

    def options(code: str) -> list[str]:
        return list(content.scale(code).get("options", []))

    def absent(code: str) -> str:
        return next(o for o in options(code) if o in ABSENT_OPTIONS)

    none_answers = {code: AnswerInput(absent(code)) for code in plan["items"]}

    def numeric_domain(code: str) -> list[float]:
        d = ag["numeric_domains"][code]
        n = int(round((d["max"] - d["min"]) / d["step"])) + 1
        return [round(d["min"] + k * d["step"], 10) for k in range(n)]

    def graded_answers(code: str) -> list[AnswerInput]:
        if content.is_numeric(code):
            unit = ag["numeric_domains"][code].get("unit") or content.item_units(code)[0]
            return [AnswerInput(numeric_value=x, unit=unit) for x in numeric_domain(code)]
        return [AnswerInput(o) for o in options(code)]

    def gate_values(term: str) -> list[str]:
        gi = ag["grading_items"][term]
        fu = next(f for f in items[gi["gate"]].get("followups", []) if f["item"] == gi["graded"])
        return list(fu["when"]["in"])

    sec = ag["secondary"]

    def secondary_combos(term: str, g: int) -> list[tuple[float, dict[str, AnswerInput]]]:
        """(probability, answers) for the items that do not set the grade but can page."""
        if term == "Diarrhea":
            d = sec["diarrhea_episode"]
            blood = [(float(p), {"STOOL_BLOOD": AnswerInput(str(o))}) for o, p in d["STOOL_BLOOD"].items()]
            p_dizzy = float(d["dizzy_on_standing"])
            dizzy = [(p_dizzy * float(p), {"DIZZINESS_SEV": AnswerInput(str(o)), "DIZZY_ON_STANDING": AnswerInput("yes")})
                     for o, p in d["dizziness_sev_when_dizzy"].items()]
            dizzy.append((1.0 - p_dizzy, {}))
            return [(pb * pd, {**ab, **ad}) for (pb, ab), (pd, ad) in itertools.product(blood, dizzy)]
        if term == "Dyspnea":
            dist = sec[f"dyspnea_g{g}"]["SOB_SEV"]
            return [(float(p), {"SOB_SEV": AnswerInput(str(o))}) for o, p in dist.items()]
        return [(1.0, {})]

    base = ag["baseline_stools"]
    out: dict[str, Any] = {"active_red_flags": active, "paged_levels": sorted(paged_levels), "cells": {}}
    # sanity: a call with no episode never pages
    for b in base["values"]:
        hits = red_flags(none_answers, {"stools_per_day": b}, active_ids=active)
        if level_for(hits) in paged_levels:
            raise RuntimeError("a call with every item at its none level pages; the paged-share model does not apply")
    for term in terms:
        gi = ag["grading_items"][term]
        gate_is_secondary = term == "Dyspnea"
        grades_seen: dict[int, dict[str, float]] = {}
        for b, pb in zip(base["values"], base["p"], strict=True):
            baseline = {"stools_per_day": b}
            cands: dict[int, list[dict[str, AnswerInput]]] = {}
            gates = [None] if gate_is_secondary else gate_values(term)
            for gv, ans in itertools.product(gates, graded_answers(gi["graded"])):
                a = dict(none_answers)
                if gv is not None:
                    a[gi["gate"]] = AnswerInput(gv)
                a[gi["graded"]] = ans
                g = grade(term, a, baseline).provisional_grade
                if g is not None and g >= min_grade:
                    cands.setdefault(g, []).append(a)
            for g, cs in cands.items():
                share = 0.0
                for a in cs:
                    for p, extra in secondary_combos(term, g):
                        lv = level_for(red_flags({**a, **extra}, baseline, active_ids=active))
                        share += p * (lv in paged_levels) / len(cs)
                cell = grades_seen.setdefault(g, {"share": 0.0, "candidates": 0})
                cell["share"] += pb * share
                cell["candidates"] += len(cs)
        for g, cell in sorted(grades_seen.items()):
            out["cells"].setdefault(term, {})[str(g)] = {"paged_share": round(cell["share"], 12), "candidates": cell["candidates"]}
    return out


@dataclass(frozen=True)
class Model:
    """Every model constant, read from params.yaml and data/signal_rules.json."""

    terms: tuple[str, ...]
    bands: tuple[int, ...]
    min_grade: int
    n_sites: int
    live_index: int
    data_cut: int
    cycle: int
    call_offsets: np.ndarray
    enroll_spread: int
    spanish_ab: tuple[float, float]
    age_mean_sd: tuple[float, float]
    term_mix: np.ndarray
    g3_share: float
    geo_p: float
    frailty: tuple[float, float]
    casemix: tuple[float, float]
    base_logit: np.ndarray
    between_sd: float
    patient_sd: float
    noise_sd: float
    lag_shape_scale: tuple[float, float]
    completion: tuple[float, float]
    gap_days: int
    window_days: int
    lower_tol: int
    entry_window: int
    next_visit_plus: int
    min_sites: int
    min_patients: int
    min_episodes: int
    min_completion: float
    winsor: tuple[float, float]
    paged_share: np.ndarray
    roles: tuple[tuple[str, dict[str, Any]], ...]
    planted: dict[str, Any] = field(default_factory=dict)


def build_model(params: dict[str, Any], signal_rules: dict[str, Any], shares: dict[str, Any]) -> Model:
    d, ep, sc, ps = params["design"], params["episodes"], params["site_capture"], params["patient_stream"]
    terms = tuple(signal_rules["primary_terms"])
    min_grade = int(signal_rules["min_grade"])
    max_grade = max(int(g) for t in terms for g in sc["base_p"][t])
    bands = tuple(range(min_grade, max_grade + 1))
    cycle, cut = int(d["cycle_days"]), int(d["data_cut_day"])
    offsets = sorted(k * cycle + int(c) for k in range(cut // cycle + 1) for c in d["call_days_after_dose"])
    offsets = np.array([o for o in offsets if o <= cut], dtype=np.int64)
    base_logit = np.array([[logit(float(sc["base_p"][t][g])) for g in bands] for t in terms])
    share = np.zeros((len(terms), max_grade + 1))
    for ti, t in enumerate(terms):
        for g, cell in shares["cells"][t].items():
            share[ti, int(g)] = cell["paged_share"]
    lag = sc["entry_lag_days"]
    cc = ps["call_completion"]
    roles = tuple((name, spec) for name, spec in params["planted"].items() if spec["count"] != "rest")
    return Model(
        terms=terms, bands=bands, min_grade=min_grade, n_sites=int(d["n_sites"]),
        live_index=list(d["site_ids"]).index(int(d["live_site"])), data_cut=cut, cycle=cycle, call_offsets=offsets,
        enroll_spread=int(d["enrollment_spread_days"]),
        spanish_ab=(float(params["roster"]["spanish_share_by_site"]["a"]), float(params["roster"]["spanish_share_by_site"]["b"])),
        age_mean_sd=(float(params["roster"]["age"]["mean"]), float(params["roster"]["age"]["sd"])),
        term_mix=np.array([float(ep["term_mix"][t]) for t in terms]), g3_share=float(ep["g3_share"]),
        geo_p=1.0 / float(ep["mean_duration_calls"]),
        frailty=(float(ep["patient_frailty"]["shape"]), float(ep["patient_frailty"]["scale"])),
        casemix=(float(ep["casemix_meanlog"]), float(ep["casemix_sd_log"])),
        base_logit=base_logit, between_sd=float(sc["between_site_sd_logit"]), patient_sd=float(sc["patient_re_sd_logit"]),
        noise_sd=float(sc["aestdtc_noise_days_sd"]),
        lag_shape_scale=(float(lag["shape"]), float(lag["mean"]) / float(lag["shape"])),
        completion=(float(cc["mean"]), float(cc["kappa"])),
        gap_days=int(signal_rules["episode"]["gap_days"]), window_days=int(signal_rules["match"]["window_days"]),
        lower_tol=int(signal_rules["match"]["lower_tolerance_days"]),
        entry_window=int(signal_rules["evaluability"]["entry_window_days"]),
        next_visit_plus=int(signal_rules["evaluability"]["next_visit_plus_days"]),
        min_sites=int(signal_rules["minimum_data"]["min_sites"]), min_patients=int(signal_rules["minimum_data"]["min_patients"]),
        min_episodes=int(signal_rules["minimum_data"]["min_evaluable_episodes"]),
        min_completion=float(signal_rules["minimum_data"]["min_call_completion"]),
        winsor=(float(signal_rules["overdispersion"]["winsor"][0]), float(signal_rules["overdispersion"]["winsor"][1])),
        paged_share=share, roles=roles, planted=params["planted"],
    )


# ---- one simulated study ---------------------------------------------------------------------------


@dataclass
class Study:
    role: list[str]
    n_pat: np.ndarray
    u: np.ndarray
    f: np.ndarray
    delta_es: np.ndarray
    site_of: np.ndarray
    enroll: np.ndarray
    es: np.ndarray
    v: np.ndarray
    completed: np.ndarray
    page_u: np.ndarray
    ep_pat: np.ndarray
    ep_term: np.ndarray
    ep_grade: np.ndarray
    ep_start: np.ndarray
    ep_k: np.ndarray
    cap_u: np.ndarray
    noise: np.ndarray
    lag: np.ndarray


def simulate(rng: np.random.Generator, m: Model, *, patients: tuple[int, int], mu: float, composition: str,
             capture_effects: bool = True) -> Study:
    """One simulated study (docs/11 §11.2 steps 1-3 and 7; answers enter only through paging).

    composition: "null" (all honest), "one_planted" (one random non-live site, f set at analysis time) or
    "full_mix" (the §11.4 roles on distinct random non-live sites). The draw order is fixed, so the same
    key gives the same honest sites for every f (common random numbers)."""
    S, T, J = m.n_sites, len(m.terms), m.call_offsets.size
    non_live = np.array([s for s in range(S) if s != m.live_index])
    perm = rng.permutation(non_live)
    role = ["honest"] * S
    if composition == "full_mix":
        k = 0
        for name, spec in m.roles:
            for _ in range(int(spec["count"])):
                role[int(perm[k])] = name
                k += 1
    elif composition == "one_planted":
        role[int(perm[0])] = "planted"
    elif composition != "null":
        raise ValueError(composition)
    n_pat = rng.integers(patients[0], patients[1] + 1, size=S)
    spanish = rng.beta(*m.spanish_ab, size=S)
    casemix = np.exp(rng.normal(m.casemix[0], m.casemix[1], size=S))
    u = rng.normal(0.0, m.between_sd, size=S)
    completion_mean = np.full(S, m.completion[0])
    f = np.zeros(S)
    delta = np.zeros(S)
    for s, r in enumerate(role):
        spec = m.planted.get(r, {})
        if "patients" in spec:
            n_pat[s] = int(spec["patients"])
        if "spanish_share" in spec:
            spanish[s] = float(spec["spanish_share"])
        if "casemix" in spec:
            casemix[s] = float(spec["casemix"])
        if "call_completion_mean" in spec:
            completion_mean[s] = float(spec["call_completion_mean"])
        if capture_effects:
            if "u_s_between_site_sds" in spec:
                u[s] = float(spec["u_s_between_site_sds"]) * m.between_sd
            if spec.get("f") is not None:
                f[s] = float(spec["f"])
            if "spanish_capture_odds_ratio" in spec:
                delta[s] = np.log(float(spec["spanish_capture_odds_ratio"]))
    site_of = np.repeat(np.arange(S), n_pat)
    P = site_of.size
    enroll = rng.integers(0, m.enroll_spread + 1, size=P)
    rng.normal(*m.age_mean_sd, size=P)  # age (pace); drawn to keep the roster's draw order, unused here
    es = rng.random(P) < spanish[site_of]
    cm = completion_mean[site_of]
    pi = rng.beta(cm * m.completion[1], (1.0 - cm) * m.completion[1])
    frailty = rng.gamma(m.frailty[0], m.frailty[1], size=P)
    v = rng.normal(0.0, m.patient_sd, size=P)
    valid = m.call_offsets[None, :] <= (m.data_cut - enroll)[:, None]
    completed = (rng.random((P, J)) < pi[:, None]) & valid
    days_on = m.data_cut - enroll
    n_ep = rng.poisson(mu * casemix[site_of] * frailty * days_on / m.data_cut)
    ep_pat = np.repeat(np.arange(P), n_ep)
    E = ep_pat.size
    ep_term = rng.choice(T, size=E, p=m.term_mix)
    ep_grade = np.where(rng.random(E) < m.g3_share, m.bands[-1], m.bands[0])
    ep_start = enroll[ep_pat] + np.floor(rng.random(E) * days_on[ep_pat]).astype(np.int64)
    ep_k = rng.geometric(m.geo_p, size=E)
    cap_u = rng.random(E)
    noise = rng.normal(0.0, m.noise_sd, size=E)
    lag = rng.gamma(m.lag_shape_scale[0], m.lag_shape_scale[1], size=E)
    page_u = rng.random((P, T, J))
    return Study(role, n_pat, u, f, delta, site_of, enroll, es, v, completed, page_u,
                 ep_pat, ep_term, ep_grade, ep_start, ep_k, cap_u, noise, lag)


# ---- episodes (docs/11 §4.2), vectorized over series --------------------------------------------------


@dataclass
class Episodes:
    series: np.ndarray
    date: np.ndarray
    lower: np.ndarray
    band: np.ndarray
    worsened: np.ndarray
    at_call: np.ndarray  # [n_series, J] episode id folding each call, -1 otherwise


def build_episodes(obs: np.ndarray, day: np.ndarray, *, min_grade: int, bands: tuple[int, ...], gap_days: int) -> Episodes:
    """Episode construction of docs/11 §4.2 on observed grades (-1 = no completed call / null grade).

    Also returns the match lower anchor L_e of §5: the last completed call before the episode date with a
    non-null grade below the band (below min_grade for a new episode), or date - gap_days if there is none
    or it is more than gap_days earlier."""
    ns, J = obs.shape
    n_max = int((obs >= min_grade).sum())
    series = np.empty(n_max, np.int64)
    date = np.empty(n_max, np.int64)
    lower = np.empty(n_max, np.int64)
    band_rec = np.empty(n_max, np.int64)
    worsened_rec = np.empty(n_max, bool)
    at_call = np.full((ns, J), -1, np.int64)
    is_open = np.zeros(ns, bool)
    band = np.zeros(ns, np.int64)
    last_rep = np.zeros(ns, np.int64)
    cur = np.full(ns, -1, np.int64)
    last_below = np.full((len(bands), ns), NO_DAY, np.int64)  # row b: last call day with grade < bands[b]
    nxt = 0
    for j in range(J):
        o, d = obs[:, j], day[:, j]
        nn = o >= 0
        is_open &= ~(nn & (d - last_rep > gap_days))  # gap rule
        ge = nn & (o >= min_grade)
        wors = is_open & ge & (o > band)
        is_open &= ~(wors | (nn & (o < min_grade)))  # worsen closes; a call below min_grade closes
        idx = np.flatnonzero(ge & ~is_open)
        if idx.size:
            ids = np.arange(nxt, nxt + idx.size)
            nxt += idx.size
            ob, dd, w = o[idx], d[idx], wors[idx]
            row = np.where(w, ob - bands[0], 0)
            low = last_below[row, idx]
            series[ids], date[ids], band_rec[ids], worsened_rec[ids] = idx, dd, ob, w
            lower[ids] = np.where(dd - low > gap_days, dd - gap_days, low)
            is_open[idx], band[idx], cur[idx] = True, ob, ids
        last_rep[ge] = d[ge]
        cur[~is_open] = -1
        at_call[:, j] = np.where(ge, cur, -1)
        for b, g in enumerate(bands):
            upd = nn & (o < g)
            last_below[b, upd] = d[upd]
    return Episodes(series[:nxt], date[:nxt], lower[:nxt], band_rec[:nxt], worsened_rec[:nxt], at_call)


def greedy_match(pair_ep: np.ndarray, pair_row: np.ndarray, dist: np.ndarray, ep_date: np.ndarray,
                 aeseq: np.ndarray, n_ep: int) -> np.ndarray:
    """One-to-one greedy assignment of docs/11 §5: pairs sorted by (distance, episode date, aeseq), taken
    in order, skipping used episodes and rows. Vectorized in rounds: a pair that comes first for both its
    episode and its row among the remaining pairs is exactly a pair the sequential greedy takes."""
    matched = np.zeros(n_ep, bool)
    if pair_ep.size == 0:
        return matched
    order = np.lexsort((aeseq, ep_date, dist))
    pe, pr = pair_ep[order], pair_row[order]
    used_row = np.zeros(int(pr.max()) + 1, bool)
    alive = np.ones(pe.size, bool)
    while alive.any():
        idx = np.flatnonzero(alive)
        e, r = pe[idx], pr[idx]
        first_e = np.zeros(idx.size, bool)
        first_e[np.unique(e, return_index=True)[1]] = True
        first_r = np.zeros(idx.size, bool)
        first_r[np.unique(r, return_index=True)[1]] = True
        take = first_e & first_r
        matched[e[take]] = True
        used_row[r[take]] = True
        alive[idx] = ~(matched[e] | used_row[r])
    return matched


def match_episodes(eps: Episodes, row_series: np.ndarray, row_aest: np.ndarray, row_aeseq: np.ndarray, *,
                   lower_tol: int, window_days: int) -> np.ndarray:
    """§5 match: candidate pairs are a row and an episode of the same subject and term with AESTDTC in
    [L_e - lower_tol, D_e + window_days]; distance to [L_e, D_e]; then `greedy_match`. Every episode takes
    part (paged, pending and evaluable alike). Returns a matched flag per episode."""
    ep_order = np.argsort(eps.series, kind="stable")
    ser_sorted = eps.series[ep_order]
    lo = np.searchsorted(ser_sorted, row_series, side="left")
    cnt = np.searchsorted(ser_sorted, row_series, side="right") - lo
    pair_row = np.repeat(np.arange(row_series.size), cnt)
    pair_ep = ep_order[np.repeat(lo, cnt) + (np.arange(pair_row.size) - np.repeat(np.cumsum(cnt) - cnt, cnt))]
    a = row_aest[pair_row]
    L, D = eps.lower[pair_ep], eps.date[pair_ep]
    ok = (a >= L - lower_tol) & (a <= D + window_days)
    pair_row, pair_ep, a, L, D = pair_row[ok], pair_ep[ok], a[ok], L[ok], D[ok]
    dist = np.where(a < L, L - a, np.where(a > D, a - D, 0))
    return greedy_match(pair_ep, pair_row, dist, D, row_aeseq[pair_row], eps.series.size)


# ---- batch analysis ----------------------------------------------------------------------------------


@dataclass
class Prepared:
    """The f-independent part of a batch of studies (patient stream, episodes, paging, coverage)."""

    n_studies: int
    pat_site: np.ndarray
    enroll: np.ndarray
    es: np.ndarray
    v: np.ndarray
    u: np.ndarray
    delta: np.ndarray
    f_default: np.ndarray
    ep_pat: np.ndarray
    ep_term: np.ndarray
    ep_grade: np.ndarray
    ep_start: np.ndarray
    cap_u: np.ndarray
    noise: np.ndarray
    lag: np.ndarray
    episodes: Episodes
    ep_patient: np.ndarray
    ep_term_obs: np.ndarray
    paged: np.ndarray
    evaluable: np.ndarray
    latent_link: np.ndarray  # observed episode containing each latent episode's first completed call, -1 if unobserved
    coverage: np.ndarray
    n_patients: np.ndarray
    role: list[str]


def prepare(studies: list[Study], m: Model) -> Prepared:
    S, T = m.n_sites, len(m.terms)
    pat_off = np.cumsum([0] + [st.site_of.size for st in studies])
    pat_site = np.concatenate([st.site_of + b * S for b, st in enumerate(studies)])
    enroll = np.concatenate([st.enroll for st in studies])
    completed = np.concatenate([st.completed for st in studies])
    page_u = np.concatenate([st.page_u for st in studies])
    ep_pat = np.concatenate([st.ep_pat + pat_off[b] for b, st in enumerate(studies)])
    ep_term = np.concatenate([st.ep_term for st in studies])
    ep_grade = np.concatenate([st.ep_grade for st in studies])
    ep_start = np.concatenate([st.ep_start for st in studies])
    ep_k = np.concatenate([st.ep_k for st in studies])
    P, J = completed.shape
    valid = m.call_offsets[None, :] <= (m.data_cut - enroll)[:, None]
    n_valid = valid.sum(axis=1)
    # latent grade per call: max over the patient's same-term episodes covering it (§11.2 step 3)
    j0 = np.searchsorted(m.call_offsets, ep_start - enroll[ep_pat], side="left")
    kc = np.clip(np.minimum(ep_k, n_valid[ep_pat] - j0), 0, None)
    rep = np.repeat(np.arange(ep_pat.size), kc)
    jj = j0[rep] + (np.arange(rep.size) - np.repeat(np.cumsum(kc) - kc, kc))
    latent = np.zeros((P, T, J), np.int64)
    for g in m.bands:  # ascending, so the higher grade wins
        sel = ep_grade[rep] == g
        latent[ep_pat[rep][sel], ep_term[rep][sel], jj[sel]] = g
    obs = np.where(completed[:, None, :], latent, -1)
    # paging per call and term from the per-cell paged share; a paged call pages every episode containing it
    share = m.paged_share[np.arange(T)[None, :, None], np.clip(obs, 0, None)]
    paged_call = ((obs >= m.min_grade) & (page_u < share)).any(axis=1)
    day = enroll[:, None] + m.call_offsets[None, :]
    eps = build_episodes(obs.reshape(P * T, J), np.repeat(day, T, axis=0), min_grade=m.min_grade,
                         bands=m.bands, gap_days=m.gap_days)
    n_ep = eps.series.size
    at = eps.at_call.ravel()
    folded = at >= 0
    paged = np.bincount(at[folded], weights=np.repeat(paged_call, T, axis=0).ravel()[folded], minlength=n_ep) > 0
    ep_patient = eps.series // T
    e = enroll[ep_patient]
    next_dose = e + m.cycle * ((eps.date - e) // m.cycle + 1)
    evaluable = m.data_cut >= np.maximum(eps.date + m.entry_window, next_dose + m.next_visit_plus)
    # latent -> observed link (for the outside-window fact)
    comp_entry = completed[ep_pat[rep], jj]
    first = np.unique(rep[comp_entry], return_index=True)
    latent_link = np.full(ep_pat.size, -1, np.int64)
    sel_rep, sel_j = rep[comp_entry][first[1]], jj[comp_entry][first[1]]
    latent_link[sel_rep] = eps.at_call[ep_pat[sel_rep] * T + ep_term[sel_rep], sel_j]
    n_site = len(studies) * S
    scheduled = np.bincount(pat_site, weights=valid.sum(axis=1), minlength=n_site)
    done = np.bincount(pat_site, weights=completed.sum(axis=1), minlength=n_site)
    return Prepared(
        n_studies=len(studies), pat_site=pat_site, enroll=enroll,
        es=np.concatenate([st.es for st in studies]), v=np.concatenate([st.v for st in studies]),
        u=np.concatenate([st.u for st in studies]), delta=np.concatenate([st.delta_es for st in studies]),
        f_default=np.concatenate([st.f for st in studies]),
        ep_pat=ep_pat, ep_term=ep_term, ep_grade=ep_grade, ep_start=ep_start,
        cap_u=np.concatenate([st.cap_u for st in studies]), noise=np.concatenate([st.noise for st in studies]),
        lag=np.concatenate([st.lag for st in studies]),
        episodes=eps, ep_patient=ep_patient, ep_term_obs=eps.series % T, paged=paged, evaluable=evaluable,
        latent_link=latent_link, coverage=np.divide(done, scheduled, out=np.zeros(n_site), where=scheduled > 0),
        n_patients=np.bincount(pat_site, minlength=n_site), role=[r for st in studies for r in st.role],
    )


@dataclass
class Analysis:
    computed: np.ndarray  # [n_studies, S]
    reason: np.ndarray
    z_adj: np.ndarray
    n_eval: np.ndarray  # |A_s|
    n_passing: np.ndarray  # sites passing checks 1-5, per study
    n_episodes: int
    n_paged: int
    captured_linked: int
    captured_outside_window: int


def analyze(prep: Prepared, m: Model, f_site: np.ndarray | None = None) -> Analysis:
    """Site capture, the §5 match, the §6-§7 rules and the §8 indicator for a prepared batch."""
    S, T = m.n_sites, len(m.terms)
    NB, C = len(m.bands), len(m.terms) * len(m.bands)
    n_site = prep.n_studies * S
    f_site = prep.f_default if f_site is None else f_site
    eps = prep.episodes
    n_ep = eps.series.size
    # site capture of each latent episode (§11.2 step 7)
    s_lat = prep.pat_site[prep.ep_pat]
    lin = (m.base_logit[prep.ep_term, prep.ep_grade - m.min_grade] + prep.u[s_lat] + prep.v[prep.ep_pat]
           + np.where(prep.es[prep.ep_pat], prep.delta[s_lat], 0.0))
    captured = prep.cap_u < (1.0 - f_site[s_lat]) * expit(lin)
    aest = prep.ep_start + np.rint(prep.noise).astype(np.int64)
    e_lat = prep.enroll[prep.ep_pat]
    dose_on_after = e_lat + m.cycle * np.maximum(0, -((e_lat - aest) // m.cycle))
    entered = dose_on_after + np.ceil(prep.lag).astype(np.int64)
    in_log = captured & (entered <= m.data_cut)
    # outside-window share among captured latent episodes that the patient stream observed
    linked = captured & (prep.latent_link >= 0)
    lk = prep.latent_link[linked]
    a_l = aest[linked]
    outside = (a_l < eps.lower[lk] - m.lower_tol) | (a_l > eps.date[lk] + m.window_days)
    # site rows in the log at the data cut; aeseq orders each subject's rows by AESTDTC, then entered_on, then
    # latent start day, then generation order (docs/11 §11.2 step 7; the planning model has no other-AE rows)
    rows = np.flatnonzero(in_log)
    row_series = prep.ep_pat[rows] * T + prep.ep_term[rows]
    row_aest = aest[rows]
    aeseq = np.empty(rows.size, np.int64)
    aeseq[np.lexsort((rows, prep.ep_start[rows], entered[rows], row_aest, prep.ep_pat[rows]))] = np.arange(rows.size)
    matched = match_episodes(eps, row_series, row_aest, aeseq, lower_tol=m.lower_tol, window_days=m.window_days)
    # analysis set A_s, leave-one-site-out expected capture (§6, §8.1)
    A = prep.evaluable & ~prep.paged
    gs = prep.pat_site[prep.ep_patient]
    cell = prep.ep_term_obs * NB + (eps.band - m.min_grade)
    keyc = gs * C + cell
    N_sc = np.bincount(keyc, weights=A, minlength=n_site * C).reshape(n_site, C)
    O_sc = np.bincount(keyc, weights=A & matched, minlength=n_site * C).reshape(n_site, C)
    N_tot = np.repeat(N_sc.reshape(prep.n_studies, S, C).sum(axis=1), S, axis=0)
    O_tot = np.repeat(O_sc.reshape(prep.n_studies, S, C).sum(axis=1), S, axis=0)
    den, num = N_tot - N_sc, O_tot - O_sc
    p_cell = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
    den_t = den.reshape(n_site, T, NB).sum(axis=2)
    num_t = num.reshape(n_site, T, NB).sum(axis=2)
    p_term = np.divide(num_t, den_t, out=np.full_like(num_t, np.nan), where=den_t > 0)
    p_hat = np.where(np.isfinite(p_cell), p_cell, np.repeat(p_term, NB, axis=1))
    p_e = p_hat[gs, cell]
    used = A & np.isfinite(p_e)
    pe0 = np.where(used, p_e, 0.0)
    y = (matched & used).astype(float)
    o_s = np.bincount(gs, weights=y, minlength=n_site)
    e_s = np.bincount(gs, weights=pe0, minlength=n_site)
    n_eval = np.bincount(gs, weights=A, minlength=n_site)
    n_pat_total = prep.pat_site.size
    r_i = np.bincount(prep.ep_patient, weights=np.where(used, y - pe0, 0.0), minlength=n_pat_total)
    has_i = np.bincount(prep.ep_patient, weights=used, minlength=n_pat_total) > 0
    n_s = np.bincount(prep.pat_site, weights=has_i, minlength=n_site)
    ss = np.bincount(prep.pat_site, weights=r_i**2, minlength=n_site)
    v_clu = np.divide(n_s * ss, n_s - 1, out=np.zeros(n_site), where=n_s >= 2)
    v_bin = np.bincount(gs, weights=pe0 * (1.0 - pe0), minlength=n_site)
    v_s = np.maximum(v_clu, v_bin)
    # guards in the §7 order (no errors and no integrated mode in a simulated study)
    reason = np.full(n_site, COMPUTED)
    reason[prep.coverage < m.min_completion] = LOW_COVERAGE
    reason[(reason == COMPUTED) & (prep.n_patients < m.min_patients)] = INSUFFICIENT_PATIENTS
    reason[(reason == COMPUTED) & ((n_eval < m.min_episodes) | (v_s <= 0))] = INSUFFICIENT_EPISODES
    reason = reason.reshape(prep.n_studies, S)
    n_passing = (reason == COMPUTED).sum(axis=1)
    reason[(n_passing < m.min_sites)[:, None] & (reason == COMPUTED)] = STUDY_BELOW
    computed = reason == COMPUTED
    o_s, e_s, v_s = o_s.reshape(-1, S), e_s.reshape(-1, S), v_s.reshape(-1, S)
    z_adj = np.full((prep.n_studies, S), np.nan)
    for b in np.flatnonzero(computed.any(axis=1)):
        c = computed[b]
        o_b, e_b, v_b = o_s[b, c], e_s[b, c], v_s[b, c]
        z = (o_b - e_b) / np.sqrt(v_b)
        q_lo, q_hi = np.quantile(z, m.winsor, method="linear")
        phi = float(np.mean(np.clip(z, q_lo, q_hi) ** 2))
        K = int(c.sum())
        w = e_b**2 / v_b
        dn = w.sum() - (w**2).sum() / w.sum()
        tau2 = max(0.0, (K * phi - (K - 1)) / dn) if dn > 0 else 0.0
        z_adj[b, c] = (o_b - e_b) / np.sqrt(v_b + tau2 * e_b**2)
    return Analysis(computed, reason, z_adj, n_eval.reshape(-1, S), n_passing, int(n_ep), int(prep.paged.sum()),
                    int(linked.sum()), int(outside.sum()))


# ---- thresholds (docs/11 §9.2-9.3) --------------------------------------------------------------------


def calibrated_threshold(values: np.ndarray, alpha: float) -> float:
    """§9.3: c = max{t in S : (1/|S|) sum 1[x <= t] <= alpha}; -inf if no t qualifies."""
    s = np.sort(np.asarray(values, dtype=float))
    if s.size == 0:
        return float("-inf")
    ok = np.searchsorted(s, s, side="right") / s.size <= alpha
    return float(s[ok][-1]) if ok.any() else float("-inf")


# ---- driver ------------------------------------------------------------------------------------------


def _rngs(seed: int, stream: int, cell: int, role: int, n: int, start: int = 0) -> list[np.random.Generator]:
    return [bvseed.rng(stream, cell, role, i, seed=seed) for i in range(start, start + n)]


def _r(x: float, nd: int = 6) -> float:
    return round(float(x), nd)


def run_p1(m: Model, plan: dict[str, Any], cells: dict[str, int], seed: int, *, studies: int | None = None) -> dict[str, Any]:
    p1 = plan["p1"]
    R = int(studies if studies is not None else p1["studies_per_range"])
    grey = set(p1["grey_by_design"])
    batch = int(plan["batch_studies"])
    rows = []
    for lo, hi in p1["ranges"]:
        cell = cells[f"p1_{lo}_{hi}"]
        comp_ng, below, comp_all, n_eval_ng = [], [], [], []
        reasons: Counter[str] = Counter()
        n_ep = n_paged = 0
        for start in range(0, R, batch):
            gens = _rngs(seed, plan["stream"], cell, 1, min(batch, R - start), start)
            studies_b = [simulate(g, m, patients=(lo, hi), mu=float(plan["mu"]), composition="full_mix",
                                  capture_effects=False) for g in gens]
            prep = prepare(studies_b, m)
            res = analyze(prep, m)
            ng = ~np.isin(np.array(prep.role).reshape(-1, m.n_sites), list(grey))
            comp_ng.extend((res.computed & ng).sum(axis=1).tolist())
            comp_all.extend(res.computed.sum(axis=1).tolist())
            below.extend((res.n_passing < m.min_sites).tolist())
            n_eval_ng.extend(res.n_eval[ng].tolist())
            reasons.update(REASONS[k] for k in res.reason[ng].ravel())
            n_ep += res.n_episodes
            n_paged += res.n_paged
        mean_c = float(np.mean(comp_ng))
        share_below = float(np.mean(below))
        passed = mean_c >= float(p1["min_mean_computed_sites"]) and share_below <= float(p1["max_share_below_min_sites"])
        rows.append({
            "patients_per_site": [lo, hi], "cell_index": cell, "studies": R,
            "mean_computed_sites_of_non_grey": _r(mean_c), "mc_se_mean_computed": _r(np.std(comp_ng, ddof=1) / np.sqrt(R)),
            "non_grey_sites": m.n_sites - sum(int(m.planted[g]["count"]) for g in grey),
            "share_studies_below_min_sites": _r(share_below), "mc_se_share_below": _r(np.sqrt(share_below * (1 - share_below) / R)),
            "mean_computed_sites_all": _r(np.mean(comp_all)),
            "mean_evaluable_nonpaged_episodes_per_non_grey_site": _r(np.mean(n_eval_ng)),
            "paged_share_of_episodes": _r(n_paged / max(n_ep, 1)),
            "not_computed_reason_share_non_grey": {k: _r(v / sum(reasons.values())) for k, v in sorted(reasons.items())},
            "passed": bool(passed),
        })
    chosen = next((r for r in rows if r["passed"]), None)
    shortfall = None
    if chosen is None:
        fb = next(r for r in rows if r["patients_per_site"] == list(p1["fallback"]))
        failed = []
        if fb["mean_computed_sites_of_non_grey"] < float(p1["min_mean_computed_sites"]):
            failed.append(f"mean computed sites {fb['mean_computed_sites_of_non_grey']} of {fb['non_grey_sites']} "
                          f"(needs >= {p1['min_mean_computed_sites']})")
        if fb["share_studies_below_min_sites"] > float(p1["max_share_below_min_sites"]):
            failed.append(f"share of studies below the {m.min_sites}-site minimum {fb['share_studies_below_min_sites']} "
                          f"(needs <= {p1['max_share_below_min_sites']})")
        shortfall = (f"no range passes; at the fallback {fb['patients_per_site'][0]}-{fb['patients_per_site'][1]}: "
                     + "; ".join(failed))
    return {
        "rule": ("first range (in order) with mean computed sites >= {} of the {} sites not designed to be grey and share of "
                 "studies below the {}-site minimum <= {}; else {} (shortfall)").format(
                     p1["min_mean_computed_sites"], rows[0]["non_grey_sites"], m.min_sites, p1["max_share_below_min_sites"],
                     "-".join(map(str, p1["fallback"]))),
        "mu": plan["mu"], "composition": "docs/11 §11.4 (planted capture losses ignored for computability)",
        "role": 1, "ranges": rows,
        "chosen": chosen["patients_per_site"] if chosen else list(p1["fallback"]),
        "outcome": "passed" if chosen else "shortfall",
        "shortfall": shortfall,
    }


def run_p2(m: Model, plan: dict[str, Any], cells: dict[str, int], seed: int, patients: tuple[int, int], *,
           null_studies: int | None = None, studies_per_f: int | None = None) -> dict[str, Any]:
    p2 = plan["p2"]
    R0 =int(null_studies if null_studies is not None else p2["null_studies"])
    R1 = int(studies_per_f if studies_per_f is not None else p2["studies_per_f"])
    fs = [float(f) for f in p2["f"]]
    batch, mu, cell = int(plan["batch_studies"]), float(plan["mu"]), cells["p2"]
    pooled, minima, n_eval, computed_n = [], [], [], []
    n_ep = n_paged = cap_linked = cap_out = 0
    for start in range(0, R0, batch):
        gens = _rngs(seed, plan["stream"], cell, 0, min(batch, R0 - start), start)
        prep = prepare([simulate(g, m, patients=patients, mu=mu, composition="null") for g in gens], m)
        res = analyze(prep, m)
        for b in range(prep.n_studies):
            zc = res.z_adj[b, res.computed[b]]
            pooled.extend(zc.tolist())
            minima.append(float(zc.min()) if zc.size else float("inf"))
        n_eval.extend(res.n_eval.ravel().tolist())
        computed_n.extend(res.computed.sum(axis=1).tolist())
        n_ep, n_paged = n_ep + res.n_episodes, n_paged + res.n_paged
        cap_linked, cap_out = cap_linked + res.captured_linked, cap_out + res.captured_outside_window
    sr_tiers = plan["_tiers"]
    alpha_look, alpha_watch = float(sr_tiers["look"]["per_site_alpha"]), float(sr_tiers["watch"]["family_wise_alpha"])
    c_look = calibrated_threshold(np.array(pooled), alpha_look)
    c_watch = min(calibrated_threshold(np.array(minima), alpha_watch), c_look)
    look_rate = float(np.mean(np.array(pooled) <= c_look)) if pooled else 0.0
    watch_fwer = float(np.mean(np.array(minima) <= c_watch))
    hits_w = {f: [] for f in fs}
    hits_l = {f: [] for f in fs}
    comp = {f: [] for f in fs}
    for start in range(0, R1, batch):
        gens = _rngs(seed, plan["stream"], cell, 1, min(batch, R1 - start), start)
        studies_b = [simulate(g, m, patients=patients, mu=mu, composition="one_planted") for g in gens]
        prep = prepare(studies_b, m)
        planted = np.array([st.role.index("planted") for st in studies_b]) + np.arange(len(studies_b)) * m.n_sites
        for f in fs:
            f_site = np.zeros(prep.n_studies * m.n_sites)
            f_site[planted] = f
            res = analyze(prep, m, f_site)
            pc = res.computed.ravel()[planted]
            pz = res.z_adj.ravel()[planted]
            comp[f].extend(pc.tolist())
            hits_w[f].extend((pc & (pz <= c_watch)).tolist())
            hits_l[f].extend((pc & (pz <= c_look)).tolist())
    z = float(p2["lower_bound_z"])
    rows = []
    for f in fs:
        p = float(np.mean(hits_w[f]))
        lb = p - z * np.sqrt(p * (1 - p) / R1)
        pl = float(np.mean(hits_l[f]))
        rows.append({"f": f, "studies": R1, "watch_power": _r(p), "mc_se_watch": _r(np.sqrt(p * (1 - p) / R1)),
                     "watch_lower_bound_80": _r(lb), "look_power": _r(pl), "mc_se_look": _r(np.sqrt(pl * (1 - pl) / R1)),
                     "p_planted_computed": _r(np.mean(comp[f])),
                     "qualifies": bool(lb >= float(p2["min_lower_bound"]))})
    chosen = next((r for r in rows if r["qualifies"]), None)
    shortfall = None
    if chosen is None:
        fb = next(r for r in rows if r["f"] == float(p2["fallback_f"]))
        shortfall = (f"no f qualifies; at the fallback f = {fb['f']}: Watch power {fb['watch_power']}, lower bound "
                     f"{fb['watch_lower_bound_80']} (needs >= {p2['min_lower_bound']}); the planted site was computed in "
                     f"{fb['p_planted_computed']} of studies (a not-computed planted site is a miss)")
    return {
        "rule": ("smallest f in {} whose one-sided 80% lower bound p - {} * sqrt(p(1 - p) / {}) of Watch power is >= {}; "
                 "else {} (shortfall)").format(fs, z, R1, p2["min_lower_bound"], p2["fallback_f"]),
        "design": {"n_sites": m.n_sites, "patients_per_site": list(patients), "mu": mu},
        "cell_index": cell,
        "null": {"studies": R0, "role": 0, "c_look": _r(c_look), "c_watch": _r(c_watch),
                 "achieved_look_per_site": _r(look_rate), "achieved_watch_fwer": _r(watch_fwer),
                 "pooled_site_values": len(pooled), "mean_computed_sites": _r(np.mean(computed_n)),
                 "share_studies_below_min_sites": _r(np.mean(np.isinf(minima)))},
        "power": {"role": 1, "common_random_numbers": True, "planted_sites_per_study": 1, "rows": rows},
        "chosen_f": chosen["f"] if chosen else float(p2["fallback_f"]),
        "outcome": "passed" if chosen else "shortfall",
        "shortfall": shortfall,
        "design_facts": {
            "source": "the P2 null studies at the chosen design",
            "mean_evaluable_nonpaged_episodes_per_site": _r(np.mean(n_eval)),
            "paged_share_of_episodes": _r(n_paged / max(n_ep, 1)),
            "share_captured_episodes_outside_match_window": _r(cap_out / max(cap_linked, 1)),
            "outside_window_definition": ("captured latent episodes whose site AESTDTC falls outside [L_e - lower_tolerance_days, "
                                          "D_e + window_days] of the patient-stream episode containing their first completed call; "
                                          "denominator = captured latent episodes observed on at least one completed call"),
        },
    }


def run_planning(repo: Path = REPO_ROOT, seed_label: str = "dev", *, p1_studies: int | None = None,
                 p2_null: int | None = None, p2_per_f: int | None = None) -> dict[str, Any]:
    if seed_label != "dev":
        raise SystemExit("plan_power.py: the pre-tag planning grid uses the dev seed only (docs/11 §1.3, §11.5)")
    params = bvseed.load_params(repo)
    signal_rules = json.loads((repo / bvseed.SIGNAL_RULES_REL).read_text(encoding="utf-8"))
    seed = bvseed.resolve_seed("dev", repo)
    shares = paged_shares(params, signal_rules)
    m = build_model(params, signal_rules, shares)
    plan = dict(params["planning"])
    plan["_tiers"] = signal_rules["tiers"]
    cells = params["cell_index"]["planning"]
    p1 = run_p1(m, plan, cells, seed, studies=p1_studies)
    lo, hi = p1["chosen"]
    p2 = run_p2(m, plan, cells, seed, (int(lo), int(hi)), null_studies=p2_null, studies_per_f=p2_per_f)
    always = all(shares["cells"][t][str(g)]["paged_share"] == 1.0 for t in m.terms for g in m.bands
                 if t == "Fever" or g == m.bands[-1])
    return {
        "_about": ABOUT,
        "data_origin": "SIMULATED",
        "sap": "docs/11-site-signal-sap.md §11.5 (rules P1 and P2); simplified model, never quoted as a result (§15 rule 1)",
        "seed": {"label": "dev", "value": seed, "stream": plan["stream"],
                 "keys": "numpy.random.SeedSequence(seed, spawn_key=(stream, cell_index, role, i)) -> PCG64",
                 "cell_index": dict(cells)},
        "model": {
            "simplifications": ["paging per cell from paged shares (rules.red_flags over enumerated candidates)",
                                "no mapping error", "no comparators", "P1 ignores planted capture losses"],
            "n_sites": m.n_sites, "data_cut_day": m.data_cut, "calls_per_patient_max": int(m.call_offsets.size),
            "mu": plan["mu"], "between_site_sd_logit": m.between_sd, "patient_re_sd_logit": m.patient_sd,
            "casemix_sd_log": m.casemix[1], "call_completion": {"mean": m.completion[0], "kappa": m.completion[1]},
        },
        "paged_shares": shares,
        "fever_and_grade3_always_paged": bool(always),
        "p1": p1,
        "p2": p2,
        "chosen": {"patients_per_site": [int(lo), int(hi)], "gross_f": p2["chosen_f"], "p1": p1["outcome"], "p2": p2["outcome"]},
        "provenance": {
            "numpy_version": np.__version__, "scipy_version": scipy.__version__, "python_version": platform.python_version(),
            "plan_power_sha256": bvseed.file_sha256(Path(__file__)),
            "signal_rules_sha256": bvseed.signal_rules_sha256(repo),
            "frozen_inputs": bvseed.frozen_inputs(repo),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-tag planning grid (docs/11 §11.5). Planning only, not a result.")
    ap.add_argument("--seed", default="dev", choices=["dev"], help="the dev seed only (params.yaml seeds.dev)")
    ap.add_argument("--out", type=Path, required=True, help="output JSON, normally monitoring/planning/planning_grid.json")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    grid = run_planning(REPO_ROOT, args.seed)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    out.write_text(json.dumps(grid, indent=2) + "\n", encoding="utf-8")
    took = time.perf_counter() - t0
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"planning grid ({ABOUT}): chosen {json.dumps(grid['chosen'])}")
    print(f"wrote {out} (sha256 {digest}) in {took:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
