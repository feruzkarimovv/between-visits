"""monitoring/bvsignal/simulate.py and roster.py: the simulated study (docs/11 §11.2, §11.4). SIMULATED, dev seed."""

from __future__ import annotations

import ast
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from scipy.special import expit, logit

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT
from bvsignal import roster as bvroster
from bvsignal import seed as bvseed
from bvsignal import simulate as sim
from bvsignal._backend import LEVEL_RANK, content, episodes, grade, level_for, red_flags, term_present

PARAMS = bvseed.load_params()
SIGNAL_RULES = json.loads((REPO_ROOT / "data" / "signal_rules.json").read_text(encoding="utf-8"))
DEV = int(PARAMS["seeds"]["dev"])
STREAM = int(PARAMS["streams"]["committed_study"])
CELL = int(PARAMS["cell_index"]["none"])
ROLE = int(PARAMS["roles"]["null_or_committed"])
MODEL = sim.default_model()
TERMS = tuple(SIGNAL_RULES["primary_terms"])
SMALL = sim.Design(n_sites=12, patients_per_site=(10, 12), mu=1.5)


def key(i: int = 0, *, stream: int = STREAM, cell: int = CELL, role: int = ROLE) -> np.random.SeedSequence:
    return bvseed.key(stream, cell, role, i, seed=DEV)


@pytest.fixture(scope="module")
def study() -> sim.Study:
    return sim.simulate(key(0), MODEL)


# ---- determinism and keys --------------------------------------------------------------------------------


def test_same_seed_gives_identical_sha256_of_the_serialized_study(study: sim.Study) -> None:
    again = sim.simulate(key(0), MODEL)
    assert again.digest() == study.digest()
    # a fresh model whose caches were filled by other studies first gives the same bytes
    fresh = sim.build_model()
    sim.simulate(key(7), fresh, roles="null")
    assert sim.simulate(key(0), fresh).digest() == study.digest()
    # the same SeedSequence object regenerates the same study (simulate never calls key.spawn())
    k = key(3)
    assert sim.simulate(k, MODEL).digest() == sim.simulate(k, MODEL).digest()
    assert k.n_children_spawned == 0
    assert sim.simulate(key(1), MODEL).digest() != study.digest()
    blob = json.dumps(study.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert json.loads(blob)["data_origin"] == DATA_ORIGIN


def test_study_and_comparator_resampling_use_separate_children(study: sim.Study) -> None:
    base = tuple(key(0).spawn_key)
    study_child, resampling_child = sim.children(key(0))
    assert tuple(study_child.spawn_key) == (*base, sim.STUDY_CHILD)
    assert tuple(resampling_child.spawn_key) == (*base, sim.RESAMPLING_CHILD)
    assert tuple(study.resampling.spawn_key) == tuple(resampling_child.spawn_key)
    names = list(PARAMS["comparators"])
    keys = {tuple(study.resampling_key(n).spawn_key) for n in names}
    assert len(keys) == len(names) and all(k[:-1] == tuple(resampling_child.spawn_key) for k in keys)


@pytest.mark.req("REQ-028")
def test_one_study_object_feeds_every_indicator(study: sim.Study) -> None:
    """Discordance (episode inputs), the rate KRI (site AE rows, patient-days) and simaerep classic (dose visits,
    site AE rows) all read the same Study; comparator resampling never changes it."""
    before = study.digest()
    calls, aes, doses = study.episode_calls(), study.site_aes_by_subject(), study.dose_days()
    assert set(calls) <= set(study.subject_ids) and set(aes) <= set(study.subject_ids)
    assert set(doses) == set(study.subject_ids)
    assert study.days_on_study().shape == (study.roster.n_patients_total,)
    rows = study.site_ae_rows()
    assert len(rows) == study.ae_pat.size and {r["origin"] for r in rows} == {"site"}
    np.random.default_rng(study.resampling_key("simaerep_classic")).random(1000)
    assert study.digest() == before


# ---- grades, red flags and answers come from rules.py ------------------------------------------------------


def _expected_g(term: str, answers: dict, baseline: dict) -> int | None:
    """docs/11 §4.2 g_k from the real rules engine."""
    asked = [answers[c] for c in content.items_for_term(term) if c in answers]
    if not any(a.option_code not in ("unknown", "not_measured") and (a.option_code or a.numeric_value is not None)
               for a in asked):
        return None
    if not term_present(term, answers):
        return 0
    return grade(term, answers, baseline).provisional_grade


def test_every_simulated_grade_equals_rules_grade_on_the_generated_answers(study: sim.Study) -> None:
    active = list(content.plan_doc()["red_flag_ids"])
    memo: dict = {}
    n = 0
    for c in range(study.call_pat.size):
        if not study.call_completed[c]:
            assert (study.call_grade[c] == sim.NULL).all() and (study.call_state[c] == sim.NULL).all()
            assert study.call_level[c] == sim.NULL
            continue
        answers, baseline = study.call_answers(c)
        assert set(content.plan_doc()["items"]) <= set(answers)  # every plan item is answered on a completed call
        k = (tuple(sorted((code, a.option_code, a.numeric_value, a.unit) for code, a in answers.items())),
             baseline["stools_per_day"])
        if k not in memo:
            memo[k] = ([_expected_g(t, answers, baseline) for t in TERMS],
                       LEVEL_RANK[level_for(red_flags(answers, baseline, active_ids=active))])
        want, level = memo[k]
        got = [None if g < 0 else int(g) for g in study.call_grade[c]]
        assert got == want, (study.call_ids()[c], got, want)
        assert int(study.call_level[c]) == level
        n += 1
    assert n == int(study.call_completed.sum()) and len(memo) > 50


def test_answers_follow_the_item_domains_and_follow_ups(study: sim.Study) -> None:
    for c in np.flatnonzero(study.call_completed)[:: max(1, int(study.call_completed.sum()) // 3000)]:
        answers, _ = study.call_answers(int(c))
        for code, a in answers.items():
            item = content.item(code)
            if content.is_numeric(code):
                assert a.option_code == "unknown" or a.numeric_value is not None
            else:
                assert a.option_code in content.item_options(code)
            for fu in item.get("followups", []):
                if "only_if" in fu:
                    assert fu["item"] not in answers  # every simulated patient has a baseline
                elif a.option_code in fu["when"]["in"]:
                    assert fu["item"] in answers
                elif fu["item"] in answers:
                    pytest.fail(f"{fu['item']} answered although {code}={a.option_code} does not open it")


def _latent_grid(st: sim.Study) -> np.ndarray:
    """Latent grade per scheduled call and term, recomputed per latent episode (§11.2 step 3)."""
    offsets = MODEL.call_offsets
    first = {}
    for c, p in enumerate(st.call_pat.tolist()):
        first.setdefault(p, c)
    out = np.zeros((st.call_pat.size, len(TERMS)), dtype=int)
    for p, t, g, start, k in zip(st.lat_pat.tolist(), st.lat_term.tolist(), st.lat_grade.tolist(),
                                 st.lat_start.tolist(), st.lat_k.tolist(), strict=True):
        enroll = int(st.roster.enroll_day[p])
        n_sched = int((offsets <= MODEL.data_cut - enroll).sum())
        j0 = int(np.searchsorted(offsets, start - enroll, side="left"))
        for j in range(j0, min(j0 + k, n_sched)):
            out[first[p] + j, t] = max(out[first[p] + j, t], g)
    return out


def test_without_mapping_error_the_recorded_grade_is_the_latent_grade() -> None:
    st = sim.simulate(key(2), MODEL, scenario=sim.Scenario(name="no_error", mapping_error_multiplier=0.0))
    assert (st.mapping_error == 0).all()
    lat = _latent_grid(st)
    comp = st.call_completed
    assert np.array_equal(st.call_grade[comp], lat[comp])
    assert (lat[comp] >= SIGNAL_RULES["min_grade"]).any()


def test_secondary_items_and_paging_follow_the_red_flag_rules(study: sim.Study) -> None:
    """docs/11 §4.4: every Fever and every grade 3 call pages (when recorded as such); a call with no
    primary-term symptom never pages; Diarrhea and Dyspnea grade 2 page only sometimes."""
    comp = study.call_completed
    paged = np.isin(study.call_level, [LEVEL_RANK[lv] for lv in SIGNAL_RULES["paged"]["levels"]]) & comp
    g = study.call_grade
    fever = TERMS.index("Fever")
    assert paged[comp & (g[:, fever] >= 2)].all()
    assert paged[comp & (g >= 3).any(axis=1)].all()
    quiet = comp & (g <= 0).all(axis=1)
    assert not paged[quiet].any()
    for term in ("Diarrhea", "Dyspnea"):
        only = comp & (g[:, TERMS.index(term)] == 2) & (np.delete(g, TERMS.index(term), axis=1) <= 0).all(axis=1)
        share = paged[only].mean()
        assert 0 < share < 0.5, (term, share)


def test_mapping_error_moves_one_step_and_respects_follow_ups() -> None:
    spec = MODEL.specs[TERMS.index("Diarrhea")]
    fq, st_k = spec.slots.index("DIARRHEA_FREQ"), spec.slots.index("DIARRHEA_STOOLS_PER_DAY")
    base = list(spec.states[0])
    assert base[fq] == "never"
    q_fq, q_st = spec.primary.index(fq), spec.primary.index(st_k)
    # never has one neighbour (rarely), which opens no follow-up
    moved = spec.perturb(tuple(base), 1 << q_fq, 0)
    assert moved[fq] == "rarely" and moved[st_k] is None
    s = list(base)
    s[fq], s[st_k] = "sometimes", 0
    assert spec.perturb(tuple(s), 1 << q_st, 0)[st_k] == 1  # stools +1 at 0
    s[st_k] = 6
    assert spec.perturb(tuple(s), 1 << q_st, 1 << q_st)[st_k] == 7
    assert spec.perturb(tuple(s), 1 << q_st, 0)[st_k] == 5
    dropped = spec.perturb(tuple(s), 1 << q_fq, 0)  # sometimes -> rarely: the stool count is no longer asked
    assert dropped[fq] == "rarely" and dropped[st_k] is None
    fever = MODEL.specs[TERMS.index("Fever")]
    opened = fever.perturb(fever.states[0], 1 << fever.primary.index(0), 0)  # no -> yes opens TEMP_HIGHEST
    assert opened == ("yes", sim.UNKNOWN)
    t = fever.slots.index("TEMP_HIGHEST")
    hot = ("yes", 395)
    assert fever.perturb(hot, 1 << fever.primary.index(t), 0)[t] == 390  # -0.5 C in tenths
    assert fever.readable(fever.state_id(("yes", 395)))["TEMP_HIGHEST"] == pytest.approx(39.5)


# ---- the numeric-literal rule (REQ-023) ---------------------------------------------------------------------


def numeric_literals(source: str) -> list[tuple[int, object]]:
    """Every numeric literal other than 0 and 1 (-1 parses as minus 1)."""
    tree = ast.parse(source)
    return sorted((n.lineno, n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, int | float | complex)
                  and not isinstance(n.value, bool) and n.value not in (0, 1))


@pytest.mark.req("REQ-023")
def test_simulate_has_no_numeric_literal_other_than_0_1_and_minus_1() -> None:
    assert numeric_literals("x = [0, 1, -1, 0.0, True]\n") == []
    assert numeric_literals("x = 2\ny = round(z, 10)\nw = 0.5\n") == [(1, 2), (2, 10), (3, 0.5)]
    bad = numeric_literals((MONITORING_DIR / "bvsignal" / "simulate.py").read_text(encoding="utf-8"))
    assert bad == [], f"numeric literals in simulate.py (read them from params.yaml or signal_rules.json): {bad}"


# ---- planted truth and the roster ---------------------------------------------------------------------------


def test_answer_key_counts_equal_the_planted_counts_in_params(study: sim.Study) -> None:
    key_rows = study.answer_key()
    labels = Counter(r["label"] for r in key_rows)
    planted = PARAMS["planted"]
    n_sites = int(PARAMS["design"]["n_sites"])
    fixed = 0
    for spec in planted.values():
        if spec["count"] == "rest":
            continue
        assert labels[spec["label"]] == int(spec["count"]), spec["label"]
        fixed += int(spec["count"])
    assert labels[planted["honest"]["label"]] == n_sites - fixed
    assert len(key_rows) == n_sites and sum(labels.values()) == n_sites
    positives = {r["label"] for r in key_rows if not r["honest"]}
    assert positives == {"gross_under", "under_50", "under_25", "language_gap"}
    assert all(r["data_origin"] == DATA_ORIGIN for r in key_rows)
    f_of = {r["label"]: r["f"] for r in key_rows}
    assert f_of["gross_under"] == planted["gross"]["f"] and f_of["under_50"] == planted["under_50"]["f"]
    assert f_of["under_25"] == planted["under_25"]["f"] and f_of["honest"] is None


@pytest.mark.parametrize("i", range(25))
def test_site_101_is_always_honest(i: int) -> None:
    st = sim.simulate(key(i), MODEL, design=SMALL)
    live = st.sites.live_index
    assert st.sites.ids[live] == str(PARAMS["design"]["live_site"]) == "101"
    assert st.role[live] == "honest"
    row = next(r for r in st.answer_key() if r["site_id"] == "101")
    assert row["label"] == "honest" and row["honest"] and row["f"] is None and row["planted"] == {}
    assert st.f[live] == 0 and st.delta_es[live] == 0


def test_planted_mechanisms_are_applied(study: sim.Study) -> None:
    planted = PARAMS["planted"]
    site_of = {}
    for s, r in enumerate(study.role):
        site_of.setdefault(r, []).append(s)
    assert len({s for ss in site_of.values() for s in ss}) == study.sites.n
    (small,) = site_of["small_site"]
    assert study.roster.n_patients[small] == planted["small_site"]["patients"]
    (lg,) = site_of["language_gap"]
    assert study.roster.spanish_share[lg] == planted["language_gap"]["spanish_share"]
    assert study.delta_es[lg] == pytest.approx(math.log(planted["language_gap"]["spanish_capture_odds_ratio"]))
    (u50,) = site_of["under_50"]
    (decoy,) = site_of["decoy_healthy_casemix"]
    assert study.casemix[u50] == planted["under_50"]["casemix"] and study.casemix[decoy] == planted["decoy_healthy_casemix"]["casemix"]
    (low,) = site_of["honest_low_diligence"]
    sd = PARAMS["site_capture"]["between_site_sd_logit"]
    assert study.u[low] == pytest.approx(planted["honest_low_diligence"]["u_s_between_site_sds"] * sd)
    (cov,) = site_of["low_coverage"]
    assert study.completion_mean[cov] == planted["low_coverage"]["call_completion_mean"]
    for s in site_of["gross_under"]:
        assert study.f[s] == planted["gross"]["f"]
    honest = [s for s, r in enumerate(study.role) if r == "honest"]
    assert (study.f[honest] == 0).all() and (study.delta_es[honest] == 0).all()


def test_roster_follows_params(study: sim.Study) -> None:
    r = study.roster
    lo, hi = PARAMS["design"]["patients_per_site"]
    small = study.role.index("small_site")
    others = np.delete(r.n_patients, small)
    assert others.min() >= lo and others.max() <= hi
    assert r.enroll_day.min() >= 0 and r.enroll_day.max() <= PARAMS["design"]["enrollment_spread_days"]
    assert np.array_equal(r.extra_time, r.age >= PARAMS["roster"]["extra_time"]["min_age"])
    assert len(set(r.subject_ids)) == r.n_patients_total
    for sid, s in zip(r.subject_ids, r.pat_site.tolist(), strict=True):
        assert re.fullmatch(rf"{study.sites.ids[s]}-\d{{3}}", sid)
    names = study.sites.names
    assert names[study.sites.live_index] == "Hillside Cancer Center (fictional)"
    assert all(n.endswith(bvroster.FICTIONAL_SUFFIX) for n in names) and len(set(names)) == len(names)
    assert set(study.sites.regions) <= {"Northeast", "Midwest", "South", "West"}
    assert list(study.sites.ids) == [str(s) for s in PARAMS["design"]["site_ids"]]
    assert set(bvroster.SITE_DIRECTORY) == {str(s) for s in PARAMS["design"]["site_ids"]}


def test_schedule_is_q3w_with_calls_on_days_1_3_7_up_to_the_data_cut(study: sim.Study) -> None:
    cut, cycle = PARAMS["design"]["data_cut_day"], PARAMS["design"]["cycle_days"]
    days_after = PARAMS["design"]["call_days_after_dose"]
    enroll = study.roster.enroll_day[study.call_pat]
    rel = study.call_day - enroll
    assert {int(x % cycle) for x in rel.tolist()} <= {d % cycle for d in days_after}
    assert study.call_day.max() <= cut
    for p in range(0, study.roster.n_patients_total, 97):
        e = int(study.roster.enroll_day[p])
        want = sorted(e + k * cycle + d for k in range(cut // cycle + 1) for d in days_after if e + k * cycle + d <= cut)
        assert study.call_day[study.call_pat == p].tolist() == want
        doses = study.dose_days()[study.subject_ids[p]]
        assert doses[0] == e and all(b - a == cycle for a, b in zip(doses, doses[1:], strict=False))
        assert doses[-2] <= cut < doses[-1]
    sched, done = study.scheduled_and_completed()
    assert sched.sum() == study.call_pat.size and done.sum() == study.call_completed.sum()


# ---- the site AE log ------------------------------------------------------------------------------------------


def test_capture_probability_and_site_rows_follow_the_capture_model(study: sim.Study) -> None:
    sc = PARAMS["site_capture"]
    site = study.pat_site[study.lat_pat]
    p0 = np.array([sc["base_p"][TERMS[t]][g] for t, g in zip(study.lat_term.tolist(), study.lat_grade.tolist(), strict=True)])
    lin = logit(p0) + study.u[site] + study.patient_re[study.lat_pat] + np.where(
        study.roster.spanish[study.lat_pat], study.delta_es[site], 0.0)
    assert np.allclose(study.lat_p, (1 - study.f[site]) * expit(lin), rtol=0, atol=1e-12)
    assert (study.lat_boost == 0).all()
    # one symptomatic row per captured latent episode, linked both ways
    sym = np.flatnonzero(study.ae_symptomatic)
    assert sym.size == int(study.lat_captured.sum())
    assert (study.lat_row[~study.lat_captured] == sim.NULL).all()
    linked = study.lat_row[study.lat_captured]
    assert np.array_equal(np.sort(linked), sym)
    assert np.array_equal(study.ae_source[linked], np.flatnonzero(study.lat_captured))
    syn = SIGNAL_RULES["match"]["term_synonyms"]
    cycle = PARAMS["design"]["cycle_days"]
    rows = study.site_ae_rows()
    for r in sym.tolist():
        e = int(study.ae_source[r])
        term = TERMS[int(study.lat_term[e])]
        assert study.ae_aeterm[r] in syn[term] and rows[r]["aetoxgr"] == str(int(study.lat_grade[e]))
        assert study.pat_site[study.ae_pat[r]] == study.pat_site[study.lat_pat[e]]
    # entered_on = (first dose visit on or after AESTDTC) + ceil(lag) with lag > 0
    enroll = study.roster.enroll_day[study.ae_pat]
    dose = enroll + cycle * np.maximum(0, -((enroll - study.ae_aestdtc) // cycle))
    assert (study.ae_entered >= dose + 1).all() and (dose >= enroll).all()
    other = ~study.ae_symptomatic
    assert other.any() and (study.ae_term[other] == sim.NULL).all()
    all_syn = {w.lower() for ws in syn.values() for w in ws}
    assert not {t.lower() for t in sim.OTHER_AE_TERMS} & all_syn
    assert all(r["origin"] == "site" and r["data_origin"] == DATA_ORIGIN for r in rows)


def test_aeseq_and_ids(study: sim.Study) -> None:
    rows = study.site_ae_rows(iso_dates=True)
    ids = [r["site_ae_id"] for r in rows]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"ae_1[0-2]\d_\d+", i) for i in ids)
    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        by_subject.setdefault(r["subject_id"], []).append(r)
    for rs in by_subject.values():
        assert [r["aeseq"] for r in rs] == list(range(1, len(rs) + 1))
        keys = [(r["aestdtc"], r["entered_on"], not r["symptomatic"]) for r in rs]
        assert keys == sorted(keys)
    call_ids = study.call_ids()
    assert len(set(call_ids)) == len(call_ids) and all(re.fullmatch(r"sim_1[0-2]\d_\d{4}", c) for c in call_ids)
    assert rows[0]["aestdtc"].startswith("2026-") and rows[0]["usubjid"].endswith(rows[0]["subject_id"])


def test_common_random_numbers_across_f() -> None:
    """§12.2: the same key and a different planted f change only the planted site's capture."""
    low = sim.simulate(key(4), MODEL, roles=sim.planted_roles(PARAMS, 0.25))
    high = sim.simulate(key(4), MODEL, roles=sim.planted_roles(PARAMS, 0.90))
    assert low.role == high.role and low.role.count("gross_under") == 1
    for name in ("call_day", "call_completed", "call_state", "call_grade", "call_level", "call_quote",
                 "lat_pat", "lat_term", "lat_grade", "lat_start"):
        assert np.array_equal(getattr(low, name), getattr(high, name)), name
    planted = low.role.index("gross_under")

    def rows(st: sim.Study, at_planted: bool) -> set[tuple]:
        site = st.pat_site[st.ae_pat]
        sel = (site == planted) if at_planted else (site != planted)
        return {(bool(s), int(src), int(a), int(e)) for s, src, a, e in zip(
            st.ae_symptomatic[sel], st.ae_source[sel], st.ae_aestdtc[sel], st.ae_entered[sel], strict=True)}

    assert rows(low, False) == rows(high, False)
    assert rows(high, True) < rows(low, True)


# ---- labels and evidence --------------------------------------------------------------------------------------


def test_every_record_is_labeled_simulated(study: sim.Study) -> None:
    d = study.to_dict()
    assert d["data_origin"] == DATA_ORIGIN
    for block in ("site_params", "subjects", "calls", "latent_episodes"):
        assert d[block]["data_origin"] == DATA_ORIGIN, block
    for spec in d["answer_states"].values():
        assert spec["data_origin"] == DATA_ORIGIN
    for block in ("sites", "answer_key", "site_ae"):
        assert d[block] and all(r["data_origin"] == DATA_ORIGIN for r in d[block]), block
    for rec in study.site_records():
        assert rec["data_origin"] == DATA_ORIGIN


def test_quote_bank_is_synthetic_and_complete() -> None:
    bank = json.loads((MONITORING_DIR / "quote_bank.json").read_text(encoding="utf-8"))
    assert bank["_about"].startswith(
        "synthetic patient phrasings, AI-assisted, not clinical wording; English translations are AI-assisted")
    assert bank["data_origin"] == DATA_ORIGIN and bank["source"] == "synthetic"
    banned = json.loads((REPO_ROOT / "data" / "site_queries.json").read_text(encoding="utf-8"))["banned_phrases_en"]
    bands = sorted({int(g) for t in TERMS for g in PARAMS["site_capture"]["base_p"][t]})
    for term in TERMS:
        assert sorted(int(g) for g in bank["quotes"][term]) == bands
        for g in bands:
            for lang in sim.LANGS:
                entries = bank["quotes"][term][str(g)][lang]
                assert len(entries) >= 3
                for e in entries:
                    text = " ".join([e["quote"], e.get("translation_en", "")]).lower()
                    assert not [b for b in banned if b in text], e
                    assert ("translation_en" in e) == (lang != "en")


def test_reporting_calls_carry_synthetic_evidence(study: sim.Study) -> None:
    ids = study.call_ids()
    seen = Counter()
    for c in np.flatnonzero(study.call_completed).tolist():
        for t, term in enumerate(TERMS):
            g = int(study.call_grade[c, t])
            ev = study.evidence(ids[c], term)
            if g < SIGNAL_RULES["min_grade"]:
                assert ev is None
                continue
            assert ev["source"] == "synthetic" and ev["t_s"] is None and ev["data_origin"] == DATA_ORIGIN
            es = bool(study.roster.spanish[study.call_pat[c]])
            assert ev["quote_lang"] == ("es" if es else "en")
            assert ev["translation_is_ai"] is es and (ev["translation_en"] is not None) is es
            assert ev["quote"] in [q["quote"] for q in MODEL.quotes[term][g][ev["quote_lang"]]]
            seen[ev["quote_lang"]] += 1
    assert seen["en"] and seen["es"]


def test_episodes_py_runs_on_the_study_and_every_episode_has_evidence(study: sim.Study) -> None:
    """Integration with the shared app.services.episodes (B16), called per subject with plain lists."""
    cfg = SIGNAL_RULES
    aes, doses = study.site_aes_by_subject(), study.dose_days()
    eps = []
    for sid, calls in study.episode_calls().items():
        eps += episodes.analyze(calls, aes.get(sid, []), cfg, data_cut=study.data_cut, dose_dates={sid: doses[sid]})
    assert len(eps) > 500
    status = Counter(e["status"] for e in eps)
    assert status["paged"] and status["matched"] and status["unmatched"] and status["pending"]
    index = {cid: c for c, cid in enumerate(study.call_ids())}
    for e in eps:
        first = index[e["checkin_ids"][0]]
        assert int(study.call_grade[first, TERMS.index(e["term"])]) == e["grade"]
        ev = study.evidence(e["checkin_ids"][0], e["term"])
        assert ev is not None and ev["source"] == "synthetic"
        if e["paged_level"] is not None:
            assert any(study.call_level[index[c]] >= LEVEL_RANK["urgent"] for c in e["checkin_ids"])


# ---- designs, roles and scenarios ------------------------------------------------------------------------------


def test_null_studies_and_grid_designs() -> None:
    null = sim.simulate(key(5), MODEL, roles="null", design=sim.grid_design(PARAMS, 1))
    assert set(null.role) == {"honest"} and (null.f == 0).all()
    assert null.sites.n == 12 and list(null.sites.ids) == [str(s) for s in range(101, 113)]
    assert set(null.roster.n_patients.tolist()) == {10}
    assert sim.sap_design(PARAMS) == MODEL.design == sim.Design(20, (40, 80), 1.5)
    with pytest.raises(ValueError):
        sim.simulate(key(5), MODEL, roles=sim.planted_roles(PARAMS, 0.5, k=12), design=sim.grid_design(PARAMS, 1))


@pytest.mark.parametrize("sid", list(PARAMS["sensitivity"]["scenarios"]))
def test_every_sensitivity_scenario_builds_and_simulates(sid: str) -> None:
    sc = sim.scenario_from_params(PARAMS, sid)
    st = sim.simulate(key(6, stream=int(PARAMS["streams"]["failure_and_sensitivity"]),
                          cell=int(PARAMS["cell_index"]["sensitivity"][sid])), MODEL, design=SMALL, scenario=sc)
    assert st.scenario.name == sid and st.to_dict()["scenario"]["name"] == sid
    spec = PARAMS["sensitivity"]["scenarios"][sid]
    non_live = [s for s in range(st.sites.n) if s != st.sites.live_index]
    if "patient_re_sd_logit" in spec:
        assert np.std(st.patient_re) == pytest.approx(spec["patient_re_sd_logit"], abs=0.1)
    if "site_mapping_error" in spec:
        has = np.flatnonzero(~np.isnan(st.site_eps))
        assert has.size == spec["n_random_sites"] and st.sites.live_index not in has
        assert np.array_equal(st.mapping_error[np.isin(st.pat_site, has)], st.site_eps[st.pat_site[np.isin(st.pat_site, has)]])
    if "entry_lag_mean_days" in spec:
        (slow,) = np.flatnonzero(st.slow_entry)
        assert slow in non_live and st.role[slow] == "honest"
    if "capture_boost_logit" in spec:
        boosted = np.unique(st.pat_site[st.lat_pat[st.lat_boost > 0]])
        assert 0 < boosted.size <= spec["n_sites_highest_paging"]
    if "call_completion_mean" in spec:
        cov = st.role.index("low_coverage")
        assert st.completion_mean[cov] == spec["low_coverage_mean"]
        assert (np.delete(st.completion_mean, cov) == spec["call_completion_mean"]).all()
    if "mapping_error_multiplier" in spec:
        base = sim.simulate(key(6, stream=int(PARAMS["streams"]["failure_and_sensitivity"]),
                                cell=int(PARAMS["cell_index"]["sensitivity"][sid])), MODEL, design=SMALL)
        lang = np.array(st.roster.language())
        hit = lang == spec["language"]
        assert np.allclose(st.mapping_error[hit], np.minimum(base.mapping_error[hit] * spec["mapping_error_multiplier"], 1))
        assert np.array_equal(st.mapping_error[~hit], base.mapping_error[~hit])
    if set(spec) <= {"match_window_days", "lower_tolerance_days", "paged_rule", "next_visit_plus_days", "overdispersion"}:
        assert st.scenario.analysis  # analysis-side only: the data are the base study
        base = sim.simulate(key(6, stream=int(PARAMS["streams"]["failure_and_sensitivity"]),
                                cell=int(PARAMS["cell_index"]["sensitivity"][sid])), MODEL, design=SMALL)
        assert np.array_equal(base.call_grade, st.call_grade) and np.array_equal(base.ae_aestdtc, st.ae_aestdtc)


def test_copula_and_failure_case() -> None:
    sc = sim.scenario_from_params(PARAMS, "SE16")
    st = sim.simulate(key(8), MODEL, roles="null", scenario=sc)
    rank = lambda a: np.argsort(np.argsort(a))  # noqa: E731
    v, pi, eps = rank(st.patient_re), rank(st.completion_p), rank(st.mapping_error)
    assert np.corrcoef(v, pi)[0, 1] > 0.3 and np.corrcoef(v, eps)[0, 1] < -0.3
    fc = sim.failure_case_scenario(PARAMS)
    assert (fc.between_site_sd_logit, fc.casemix_sd_log) == (
        PARAMS["failure_case"]["between_site_sd_logit"], PARAMS["failure_case"]["casemix_sd_log"])
    a = sim.simulate(key(8), MODEL, roles="null")
    b = sim.simulate(key(8), MODEL, roles="null", scenario=fc)
    assert np.allclose(b.u / a.u, fc.between_site_sd_logit / PARAMS["site_capture"]["between_site_sd_logit"])


def test_simulation_speed_at_the_sap_v1_design(capsys: pytest.CaptureFixture[str]) -> None:
    """Report seconds per study at the chosen design (S4 calibrates on 2000 studies, S7 validates on ~1e5)."""
    n = 5
    t0 = time.perf_counter()
    for i in range(n):
        sim.simulate(key(100 + i), MODEL)
    per_study = (time.perf_counter() - t0) / n
    with capsys.disabled():
        print(f"\nsimulate: {per_study:.3f} s per study at {MODEL.design} (single core, dev seed)")
    assert per_study < 0.5


def test_cli_refuses_committed_output_dirs(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        sim.main(["--studies", "1", "--out", str(REPO_ROOT / "monitoring" / "out")])
    with pytest.raises(SystemExit):
        sim.main(["--studies", "1", "--out", str(REPO_ROOT / "validation" / "site_signal" / "x")])
    assert sim.main(["--studies", "1", "--out", str(tmp_path)]) == 0
    (f,) = tmp_path.glob("study_dev_0.json")
    assert json.loads(f.read_text(encoding="utf-8"))["data_origin"] == DATA_ORIGIN
