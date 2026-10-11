"""S9: monitoring/bvsignal/equity.py (docs/11-site-signal-sap.md §14; REQ-031 Site Signal equity strata). SIMULATED.

* A hand-built 2-site table (Spanish vs English, matched vs unmatched) checks the Mantel-Haenszel odds ratio and the
  Robins-Breslow-Greenland variance against a hand computation written out with exact fractions, never by calling
  the code under test (agreement to 1e-12).
* The patient-cluster bootstrap is reproducible from its keys: the same key gives identical output, the resamples
  are recomputed here from ``SeedSequence(entropy, spawn_key=(*key.spawn_key, site_index))`` alone, the first B'
  resamples of a larger run are exactly the B' resamples (so validation quick mode stays a subset, §12.3), and the
  committed study's key is stream 0, ``role`` 2 (§1.3).
* The §14 rules: sites used (>= 5 per group), point estimate only below 10 per group, 0.5 added to every cell of a
  per-site table with a zero cell, "not computed: insufficient data", Breslow-Day.
* A dev-seed run of ``python -m bvsignal.run`` writes ``equity.json`` with ``language`` and ``pace`` blocks with
  ``ci95`` and one single-language counterfactual row per site, and adding equity changes no other output.

Development only: the dev seed, outputs under pytest's temporary directory, never the evaluation seed and never
``monitoring/out/`` or ``validation/site_signal/``. A reason to look, not a finding.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bvsignal import DATA_ORIGIN, REPO_ROOT
from bvsignal import equity as eq
from bvsignal import indicators as ind
from bvsignal import match as bvmatch
from bvsignal import run as bvrun
from bvsignal import seed as bvseed

pytestmark = pytest.mark.req("REQ-031")

PARAMS = bvseed.load_params()
DEV = int(PARAMS["seeds"]["dev"])
TERMS = ("Diarrhea", "Fever", "Dyspnea")
TOL = 1e-12

# Hand-built 2-site table, (a, b, c, d) = (Spanish matched, Spanish unmatched, English matched, English unmatched)
TWO_SITES = {"201": (6, 4, 3, 7), "202": (5, 5, 4, 8)}


def records_for(tables: dict[str, tuple[int, int, int, int]], per_patient: int = 2
                ) -> tuple[list[tuple[str, str, str, bool]], dict[str, dict[str, bool]]]:
    """Episode records realizing ``tables``: each group's episodes go to patients ``per_patient`` at a time
    (matched first), terms alternate Diarrhea / Dyspnea. Returns (records, exposure maps for language and pace)."""
    records: list[tuple[str, str, str, bool]] = []
    spanish: dict[str, bool] = {}
    for site, (a, b, c, d) in tables.items():
        for group, ys in (("es", [True] * a + [False] * b), ("en", [True] * c + [False] * d)):
            for n, y in enumerate(ys):
                subject = f"{site}-{group}{n // per_patient:02d}"
                spanish[subject] = group == "es"
                records.append((site, subject, TERMS[0] if n % 2 == 0 else TERMS[2], y))
    pace = {s: False for s in spanish}  # unused by the language checks
    return records, {eq.LANGUAGE.name: spanish, eq.PACE.name: pace}


def language_data(tables: dict[str, tuple[int, int, int, int]], per_patient: int = 2) -> eq.EquityData:
    records, exposed = records_for(tables, per_patient)
    return eq.build_data(list(tables), TERMS, records, exposed, groupings=(eq.LANGUAGE,))


# ---- the Mantel-Haenszel odds ratio and the RBG variance by hand ------------------------------------------------------


def hand_mh_and_rbg() -> tuple[Fraction, Fraction]:
    """docs/11 §14 formulas on TWO_SITES with exact fractions.

    Site 201: n = 20, R1 = 6*7/20 = 42/20, S1 = 4*3/20 = 12/20, P1 = (6+7)/20 = 13/20, Q1 = (4+3)/20 = 7/20.
    Site 202: n = 22, R2 = 5*8/22 = 40/22, S2 = 5*4/22 = 20/22, P2 = (5+8)/22 = 13/22, Q2 = (5+4)/22 = 9/22.
    R = R1 + R2 = 431/110, S = S1 + S2 = 166/110, OR_MH = R/S = 431/166 (about 2.5964).
    Var(ln OR_MH) = (P1 R1 + P2 R2)/(2 R^2) + (P1 S1 + Q1 R1 + P2 S2 + Q2 R2)/(2 R S) + (Q1 S1 + Q2 S2)/(2 S^2)."""
    F = Fraction
    R1, S1, P1, Q1 = F(42, 20), F(12, 20), F(13, 20), F(7, 20)
    R2, S2, P2, Q2 = F(40, 22), F(20, 22), F(13, 22), F(9, 22)
    R, S = R1 + R2, S1 + S2
    assert (R, S) == (F(431, 110), F(166, 110))
    var = ((P1 * R1 + P2 * R2) / (2 * R * R) + (P1 * S1 + Q1 * R1 + P2 * S2 + Q2 * R2) / (2 * R * S)
           + (Q1 * S1 + Q2 * S2) / (2 * S * S))
    return R / S, var


def test_tables_are_built_from_episode_records() -> None:
    data = language_data(TWO_SITES)
    point = data.point_tables()  # [S, G, 4, T]
    assert point.shape == (2, 1, 4, len(TERMS))
    assert point[:, 0].sum(axis=-1).tolist() == [list(map(float, t)) for t in TWO_SITES.values()]
    # patients are the clusters: 5 Spanish + 5 English patients at 201, 5 + 6 at 202 (two episodes each)
    assert [len(c) for c in data.clusters] == [10, 11]


def test_mh_odds_ratio_and_rbg_variance_match_the_hand_computation() -> None:
    or_hand, var_hand = hand_mh_and_rbg()
    data = language_data(TWO_SITES)
    tab = data.point_tables()[:, 0].sum(axis=-1)  # [2, 4]
    assert math.exp(float(eq.mh_log_or(tab))) == pytest.approx(float(or_hand), rel=TOL, abs=TOL)
    assert float(eq.rbg_variance(tab)) == pytest.approx(float(var_hand), rel=TOL, abs=TOL)
    # the same numbers through the block that equity.json serves
    block = eq.analyze_equity(data, eq.equity_key(DEV, 0, 0, 0, PARAMS), 200)[eq.LANGUAGE.name]
    assert block["n_sites_used"] == 2 and block["sites_used"] == ["201", "202"]
    assert block["mh_or"] == pytest.approx(float(or_hand), rel=TOL, abs=TOL)
    assert block["rbg_var_ln_or"] == pytest.approx(float(var_hand), rel=TOL, abs=TOL)
    z = 1.959963984540054  # standard normal 0.975 quantile
    half = z * math.sqrt(float(var_hand))
    lo, hi = math.log(float(or_hand)) - half, math.log(float(or_hand)) + half
    assert block["rbg_ci95"] == pytest.approx([math.exp(lo), math.exp(hi)], rel=1e-9)
    assert block["ci95_method"] == "patient_bootstrap" and len(block["ci95"]) == 2
    # with 5 patients per group some resamples have S = 0 (ln OR = +inf), so the upper bound may be unbounded (null)
    assert block["ci95"][0] < block["mh_or"] and (block["ci95"][1] is None or block["mh_or"] < block["ci95"][1])
    assert block["data_origin"] == DATA_ORIGIN


def test_per_site_odds_ratios_by_hand() -> None:
    data = language_data(TWO_SITES)
    rows = {r["site_id"]: r for r in eq.analyze_equity(data, eq.equity_key(DEV, 0, 0, 0, PARAMS), 200)["language"]
            ["per_site"]}
    # 201: 6*7/(4*3) = 3.5; 202: 5*8/(5*4) = 2; both have >= 10 episodes per group, so both get an interval
    assert rows["201"]["or"] == pytest.approx(3.5, rel=TOL)
    assert rows["202"]["or"] == pytest.approx(2.0, rel=TOL)
    assert (rows["201"]["n_es"], rows["201"]["n_en"], rows["202"]["n_es"], rows["202"]["n_en"]) == (10, 10, 10, 12)
    for r in rows.values():
        assert r["interval"] == "patient_bootstrap" and r["ci95"] is not None and not r["haldane"]
        assert r["ci95"][0] <= r["or"] <= r["ci95"][1]


# ---- the bootstrap is reproducible from its keys ------------------------------------------------------------------------


def manual_bootstrap_log_or(data: eq.EquityData, key: np.random.SeedSequence, B: int) -> np.ndarray:
    """ln OR_MH of each resample, recomputed from the documented keys with plain loops (no equity.py helpers)."""
    per_site = []
    for k, counts in enumerate(data.counts):
        n = counts.shape[0]
        child = np.random.SeedSequence(key.entropy, spawn_key=(*key.spawn_key, k), pool_size=key.pool_size)
        idx = np.random.Generator(np.random.PCG64(child)).integers(0, n, size=(B, n))
        cells = counts[:, 0].sum(axis=-1)  # [n, 4]: language a, b, c, d per patient
        per_site.append([cells[row].sum(axis=0) for row in idx])
    out = []
    for b in range(B):
        R = S = 0.0
        for site in per_site:
            a, bb, c, d = site[b]
            n = a + bb + c + d
            if n:
                R += a * d / n
                S += bb * c / n
        out.append(math.log(R / S))
    return np.array(out)


BOOT_SITES = {"201": (12, 8, 6, 14), "202": (10, 10, 8, 16)}  # larger, so no resample has R = 0 or S = 0


def test_bootstrap_is_reproducible_from_its_keys() -> None:
    data = language_data(BOOT_SITES)
    key = eq.equity_key(DEV, 0, 0, 0, PARAMS)
    B = 300
    first = eq.analyze_equity(data, key, B)
    assert eq.analyze_equity(data, eq.equity_key(DEV, 0, 0, 0, PARAMS), B) == first
    # recomputed from the keys alone
    logs = manual_bootstrap_log_or(data, key, B)
    assert np.isfinite(logs).all()
    lo, hi = np.quantile(logs, [0.025, 0.975], method="linear")
    assert first["language"]["ci95"] == pytest.approx([math.exp(lo), math.exp(hi)], rel=TOL)
    assert first["language"]["bootstrap"]["B"] == B
    assert first["language"]["bootstrap"]["key"]["entropy"] == DEV
    assert first["language"]["bootstrap"]["key"]["spawn_key"] == [0, 0, 2, 0]
    # another replicate's key gives other resamples
    other = eq.analyze_equity(data, eq.equity_key(DEV, 0, 0, 1, PARAMS), B)
    assert other["language"]["ci95"] != first["language"]["ci95"]
    assert other["language"]["mh_or"] == first["language"]["mh_or"]
    # the first B' resamples of a larger run are exactly the B' resamples (quick mode stays a subset, §12.3)
    big, small = eq.bootstrap_tables(data, key, 2000, [0, 1]), eq.bootstrap_tables(data, key, 1000, [0, 1])
    assert np.array_equal(big[:1000], small)
    # a site's resamples do not depend on which other sites are resampled
    assert np.array_equal(eq.bootstrap_tables(data, key, 50, [1])[:, 1], eq.bootstrap_tables(data, key, 50, [0, 1])[:, 1])


def test_committed_key_is_stream_0_role_2() -> None:
    key = eq.equity_key(DEV, int(PARAMS["streams"]["committed_study"]), int(PARAMS["cell_index"]["none"]), 0, PARAMS)
    assert key.entropy == DEV
    assert tuple(key.spawn_key) == (0, 0, int(PARAMS["roles"]["resampling"]), 0) == (0, 0, 2, 0)
    assert eq.B_COMMITTED == 2000


# ---- the other §14 rules ---------------------------------------------------------------------------------------------


def test_sites_used_point_estimate_only_and_haldane() -> None:
    tables = {
        "301": (6, 4, 3, 7),  # 10 / 10: used, interval
        "302": (5, 0, 2, 4),  # 5 / 6 with a zero cell: used, point estimate only, 0.5 added to every cell
        "303": (3, 1, 9, 9),  # 4 Spanish episodes: not used
    }
    block = eq.analyze_equity(language_data(tables), eq.equity_key(DEV, 0, 0, 0, PARAMS), 200)["language"]
    assert block["sites_used"] == ["301", "302"] and block["n_sites_used"] == 2
    rows = {r["site_id"]: r for r in block["per_site"]}
    assert set(rows) == {"301", "302"}
    assert rows["302"]["interval"] == "point_estimate_only" and rows["302"]["ci95"] is None
    assert rows["302"]["haldane"] is True
    assert rows["302"]["or"] == pytest.approx((5.5 * 4.5) / (0.5 * 2.5), rel=TOL)
    assert rows["301"]["interval"] == "patient_bootstrap" and rows["301"]["ci95"] is not None
    # the pooled MH estimate uses the raw counts of the sites used (no 0.5): R = 42/20 + 20/11, S = 12/20 + 0
    assert block["mh_or"] == pytest.approx((42 / 20 + 20 / 11) / (12 / 20), rel=TOL)


def test_no_site_with_enough_data_reads_not_computed() -> None:
    block = eq.analyze_equity(language_data({"401": (2, 2, 9, 9), "402": (5, 5, 1, 3)}),
                              eq.equity_key(DEV, 0, 0, 0, PARAMS), 100)["language"]
    assert block["n_sites_used"] == 0 and block["not_computed_reason"] == "insufficient_data"
    assert block["label"] == "not computed: insufficient data"
    assert block["mh_or"] is None and block["ci95"] is None and block["rbg_ci95"] is None
    assert eq.interval_contains_one(block) is None


def test_breslow_day() -> None:
    # identical odds ratios in both strata: X^2 = 0
    same = np.array([[4.0, 2.0, 2.0, 4.0], [8.0, 4.0, 4.0, 8.0]])
    psi = math.exp(float(eq.mh_log_or(same)))
    assert psi == pytest.approx(4.0, rel=TOL)
    res = eq.breslow_day(same, psi)
    assert res["statistic"] == pytest.approx(0.0, abs=1e-12) and res["df"] == 1 and res["p"] == pytest.approx(1.0)
    # psi = 1, one stratum each side of it: A_k = n1 m1 / n by hand
    tab = np.array([[6.0, 4.0, 4.0, 6.0], [4.0, 6.0, 6.0, 4.0]])
    res = eq.breslow_day(tab, 1.0)
    # each stratum: A = 10 * 10 / 20 = 5, Var = 1 / (4 / 5) = 5/4, (6 - 5)^2 / (5/4) = 4/5
    assert res["statistic"] == pytest.approx(1.6, rel=TOL) and res["df"] == 1


def test_percentile_interval_handles_infinite_and_undefined_resamples() -> None:
    bounds, n_undefined = eq.percentile_interval(np.array([-np.inf, -np.inf, 0.0, 1.0, np.nan]))
    assert n_undefined == 1
    assert bounds is not None and bounds[0] == -np.inf and math.isfinite(bounds[1])
    assert eq._or_interval(bounds)[0] == 0.0
    assert eq._or_interval((0.0, math.inf)) == [1.0, None]


# ---- a dev-seed run: equity.json, the counterfactual, and no effect on the other outputs ----------------------------------

R_CAL = 20  # development calibration size (never a result)


@pytest.fixture(scope="module")
def dev_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("s9_equity")
    proc = subprocess.run([sys.executable, "-m", "bvsignal.run", "--seed", "dev", "--out", str(out), "--r-cal",
                           str(R_CAL), "--workers", "1"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    return out


def walk_objects(x: Any, where: str = "equity.json") -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(x, dict):
        out.append((where, x))
        for k, v in x.items():
            out += walk_objects(v, f"{where}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out += walk_objects(v, f"{where}[{i}]")
    return out


def test_dev_run_writes_equity_json(dev_run: Path) -> None:
    doc = json.loads((dev_run / "equity.json").read_text(encoding="utf-8"))
    signal_run = json.loads((dev_run / "signal_run.json").read_text(encoding="utf-8"))
    site_ids = [s["site_id"] for s in signal_run["sites"]]
    assert doc["data_origin"] == DATA_ORIGIN and doc["seed_label"] == "dev" and doc["eval_seed"] is None
    for name in ("language", "pace"):
        block = doc[name]
        assert "ci95" in block and "mh_or" in block and "n_sites_used" in block
        assert block["ci95_method"] == "patient_bootstrap"
        if block["n_sites_used"]:
            assert block["ci95"] is not None and len(block["ci95"]) == 2
            assert block["bootstrap"]["B"] == eq.B_COMMITTED
            assert block["bootstrap"]["key"]["spawn_key"] == [0, 0, 2, 0]
            assert block["sensitivity_site_x_term"]["strata"] == "site x term"
        n_key = eq.LANGUAGE.n_exposed_key if name == "language" else eq.PACE.n_exposed_key
        for row in block["per_site"]:
            assert row[n_key] >= eq.MIN_PER_GROUP
    assert doc["pace"]["negative_control"] is True
    cf = doc["single_language_counterfactual"]
    assert [r["site_id"] for r in cf] == site_ids  # one row per site
    tiers_now = {r["site_id"]: r["tier"] for r in signal_run["rows"]}
    shares = {s["site_id"]: s["spanish_share"] for s in signal_run["sites"]}
    for r in cf:
        assert set(r) >= {"site_id", "tier_now", "tier_if_english_only", "reason", "share_no_reference_stream"}
        assert r["tier_now"] == tiers_now[r["site_id"]]
        assert r["tier_if_english_only"] in ind.TIER_VALUES
        assert (r["reason"] is None) == (r["tier_if_english_only"] != ind.NOT_COMPUTED)
        assert r["share_no_reference_stream"] == pytest.approx(shares[r["site_id"]], abs=1e-12)
        if r["n_patients_no_reference_stream"] == 0:
            assert r["n_episodes_evaluable_if_english_only"] == r["n_episodes_evaluable_now"]
    assert "power is low" in doc["note"]
    assert all(obj.get("data_origin") == DATA_ORIGIN for where, obj in walk_objects(doc)), \
        [where for where, obj in walk_objects(doc) if obj.get("data_origin") != DATA_ORIGIN]
    text = json.dumps(doc).lower()
    for word in ("under-report", "underreport", "fraud", "misconduct", "clean"):
        assert word not in text, word


def test_english_only_inputs_remove_every_spanish_call(dev_run: Path) -> None:
    src = bvrun.load_threshold_source(dev_run / "thresholds.json")
    ctx = bvrun.analyze(DEV, "dev", src)
    study = ctx.study
    es = {sid for sid, s in zip(study.subject_ids, study.roster.spanish.tolist(), strict=True) if s}
    before = {sd.site_id: sd for sd in bvmatch.site_inputs(study)}
    for sd in eq.english_only_inputs(study):
        assert not any(c["subject_id"] in es for c in sd.calls)
        assert sd.subject_ids == before[sd.site_id].subject_ids  # patients stay enrolled
        n_es_calls = sum(c["subject_id"] in es for c in before[sd.site_id].calls)
        assert before[sd.site_id].completed_calls - sd.completed_calls == n_es_calls
        assert 0 <= sd.completed_calls <= sd.scheduled_calls <= before[sd.site_id].scheduled_calls


def test_equity_changes_no_other_output_and_is_deterministic(dev_run: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = bvrun.load_threshold_source(dev_run / "thresholds.json")
    prov = bvrun.provenance("dev", DEV)
    ctx = bvrun.analyze(DEV, "dev", src)
    with monkeypatch.context() as m:
        m.setattr(bvrun, "equity_available", lambda: False)
        without = bvrun.build_documents(ctx, src, prov)
    assert bvrun.EQUITY not in without
    with_equity = bvrun.build_documents(ctx, src, prov)
    again = bvrun.build_documents(ctx, src, prov)  # after equity ran once on the same objects
    for name in without:
        assert bvrun.dumps(with_equity[name]) == bvrun.dumps(without[name]), name
        assert bvrun.dumps(again[name]) == bvrun.dumps(without[name]), name
    assert bvrun.dumps(with_equity[bvrun.EQUITY]) == bvrun.dumps(again[bvrun.EQUITY])
    # and the file the run wrote is this document
    assert (dev_run / bvrun.EQUITY).read_text(encoding="utf-8") == bvrun.dumps(again[bvrun.EQUITY])
