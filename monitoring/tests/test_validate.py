"""S7: validate.py (docs/11 §12; REQ-023 quick check). SIMULATED, dev seed only.

No evaluation-seed run happens here: evaluation-seed code paths are exercised only up to their refusals.
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from bvsignal import REPO_ROOT
from bvsignal import indicators as ind
from bvsignal import seed as bvseed
from bvsignal import simulate as sim
from bvsignal import validate as val

PARAMS = bvseed.load_params()
DEV = int(PARAMS["seeds"]["dev"])
WORKERS = max(2, min(os.cpu_count() or 2, 8))


# ---- §14 math, §12.8 intervals ---------------------------------------------------------------------------------------


def test_mh_odds_ratio_and_rbg_variance_by_hand() -> None:
    """Two strata: a, b = group-1 matched/unmatched; c, d = group-0 matched/unmatched (docs/11 §14)."""
    a, b, c, d = np.array([3.0, 6.0]), np.array([5.0, 2.0]), np.array([10.0, 4.0]), np.array([2.0, 8.0])
    n = a + b + c + d  # 20, 20
    R_k, S_k = a * d / n, b * c / n  # [0.3, 2.4], [2.5, 0.4]
    P_k, Q_k = (a + d) / n, (b + c) / n
    R, S = R_k.sum(), S_k.sum()
    var = ((P_k * R_k).sum() / (2 * R * R) + (P_k * S_k + Q_k * R_k).sum() / (2 * R * S)
           + (Q_k * S_k).sum() / (2 * S * S))
    ln_or, v = val.mh_odds_ratio(a, b, c, d)
    assert float(ln_or) == pytest.approx(math.log(2.7 / 2.9), abs=1e-12)
    assert float(v) == pytest.approx(var, rel=1e-12)
    # R = 0 -> -inf, S = 0 -> +inf, both -> NaN; variance undefined in each case
    lo, vlo = val.mh_odds_ratio([0.0], [1.0], [1.0], [1.0])
    hi, vhi = val.mh_odds_ratio([1.0], [0.0], [1.0], [1.0])
    nan, _ = val.mh_odds_ratio([0.0], [0.0], [1.0], [1.0])
    assert float(lo) == -math.inf and float(hi) == math.inf and math.isnan(float(nan))
    assert math.isnan(float(vlo)) and math.isnan(float(vhi))


def test_clopper_pearson_and_percentiles() -> None:
    lo, hi = val.clopper_pearson(8, 8)
    assert hi == 1.0 and lo == pytest.approx(0.631, abs=5e-4)  # docs/11 §12.8 example
    assert val.clopper_pearson(0, 10)[0] == 0.0
    x = np.array([0.3, -1.2, 2.5, 0.0, 1.1, -0.4])
    for q in (0.025, 0.5, 0.975):
        assert val.percentile_linear(x, q) == pytest.approx(float(np.quantile(x, q, method="linear")), abs=1e-15)
    assert val.percentile_linear(np.array([-math.inf, 0.0, 1.0]), 0.25) == -math.inf
    assert val.percentile_linear(np.array([0.0, 1.0, math.inf]), 0.75) == math.inf
    assert val.percentile_linear(np.array([-math.inf, math.inf]), 0.5) != val.percentile_linear(np.array([0.0]), 0.5)


def test_clustered_rate_matches_the_sap_formula() -> None:
    F, K = np.array([1, 0, 2, 0]), np.array([10, 12, 9, 15])
    r = val.clustered_rate(F, K)
    a = F.sum() / K.sum()
    se = math.sqrt(float(np.sum((F - a * K) ** 2)) / (4 * 3)) / K.mean()
    assert r["rate"] == a and r["mc_se"] == pytest.approx(se, rel=1e-12)


def test_acceptance_reports_pass_conservative_and_failure() -> None:
    cfg = sim.default_model().signal_rules
    th = val.ThresholdSet("test", np.zeros(len(val.INDICATORS)), np.zeros(len(val.INDICATORS)),
                          {n: {"look": {"rate": 0.05, "mc_se": 0.005}, "watch": {"rate": 0.1, "mc_se": 0.007}}
                           for n in val.INDICATORS})

    def block(look: float, watch: float, tert: list[float]) -> dict:
        return {"look_per_site": {"rate": look, "mc_se": 0.004}, "watch_fwer": {"rate": watch, "mc_se": 0.0067},
                "look_per_site_by_e_tertile": [{"rate": t} for t in tert]}

    blocks = {n: block(0.052, 0.095, [0.04, 0.05, 0.06]) for n in val.INDICATORS}
    blocks["rate_kri"] = block(0.08, 0.2, [0.02, 0.05, 0.09])
    blocks["simaerep_classic"] = block(0.03, 0.04, [0.03, 0.03, 0.03])
    acc = val.acceptance(blocks, th, cfg)
    d = acc["by_indicator"]["discordance"]
    assert (d["look"]["status"], d["watch"]["status"], d["size_calibration"]["status"]) == ("pass", "conservative", "pass")
    assert d["look"]["bound"] == pytest.approx(0.05 + 2 * math.sqrt(0.005 ** 2 + 0.004 ** 2), rel=1e-15)
    k = acc["by_indicator"]["rate_kri"]
    assert (k["look"]["status"], k["watch"]["status"], k["size_calibration"]["status"]) == ("failure", "failure", "failure")
    assert acc["by_indicator"]["simaerep_classic"]["look"]["status"] == "conservative"
    assert acc["status"] == "pass"


# ---- tiers: validate's vectorized flags equal indicators.tiers ----------------------------------------------------------


def test_flags_equal_indicators_tiers() -> None:
    model = sim.default_model()
    study = sim.simulate(bvseed.key(0, 0, 0, 0, seed=DEV), model)
    res = ind.analyze_study(study)
    rec = val.study_record(study, res, val._labels(model.params))
    # served thresholds placed inside each indicator's observed range so every tier occurs
    served = {}
    for name in val.INDICATORS:
        s = res.results[name].statistic
        s = np.sort(s[~np.isnan(s)])
        if ind.FLAG_WHEN[name] == ind.AT_OR_ABOVE:
            served[name] = {"look": float(s[-3]), "watch": float(s[-1])}
        else:
            served[name] = {"look": float(s[2]), "watch": float(s[0])}
    th = val.thresholds_from_doc(served, "test")
    names = val.tier_names(rec, th)
    for name in val.INDICATORS:
        assert tuple(names[name]) == ind.tiers(res.results[name], served[name]), name


# ---- quick replicates, determinism and the check -------------------------------------------------------------------------


def _small_params() -> dict:
    p = copy.deepcopy(PARAMS)
    p["calibration"]["r_quick"] = 2
    p["grid"]["reps_quick"] = 1
    return p


def test_quick_jobs_are_the_first_replicates_of_the_same_keys() -> None:
    p = _small_params()
    sets, full = val.build_jobs(p, DEV, val.Plan(0.003, False, p))
    _, quick = val.build_jobs(p, DEV, val.Plan(0.003, True, p))
    by_id = {s.set_id: s for s in sets}
    assert quick == [j for j in full if val.is_quick(j, by_id, val.Plan(0.003, False, p))]
    assert len(quick) < len(full)
    ids = {s.set_id for s in sets}
    assert len([i for i in ids if i.startswith("sensitivity_null:")]) == 21
    assert {"null_validation", "design_row", "full_mix", "failure_a_null", "failure_a_power", "failure_b_null"} <= ids
    # every grid f, including 0.25 and 0.50, shares one key per replicate (common random numbers, §12.2)
    gp = [j for j in full if j.set_id.startswith("grid_power:")]
    assert all(j.fs == tuple(float(f) for f in PARAMS["grid"]["f"]) for j in gp)
    assert {0.25, 0.5} <= set(gp[0].fs)


def _sample_jobs() -> list[val.Job]:
    """One replicate key of each kind (equity, planted f, full mix, scenarios, committed re-runs)."""
    p = PARAMS
    _, jobs = val.build_jobs(p, DEV, val.Plan(0.002, False, p))
    seen, out = set(), []
    for j in jobs:
        kind = j.set_id.split(":")[0]
        if kind not in seen or j.set_id in ("committed:SE1", "sensitivity_mix:SE16", "grid_power:1"):
            seen.add(kind)
            out.append(j)
    return out


@pytest.mark.req("REQ-023")
def test_results_do_not_depend_on_the_worker_count() -> None:
    jobs = _sample_jobs()
    labels = val._labels(PARAMS)
    one = val.run_jobs(jobs, 1)
    two = val.run_jobs(jobs, WORKERS)
    a = [[val.record_json(r, labels) for r in recs] for recs, _ in one]
    b = [[val.record_json(r, labels) for r in recs] for recs, _ in two]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert any("equity" in r for recs in a for r in recs)
    assert any(len(recs) == len(PARAMS["grid"]["f"]) for recs in a)


@pytest.mark.req("REQ-023")
def test_quick_check_passes_on_equal_hashes_and_fails_after_tampering(tmp_path: Path,
                                                                       capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--seed", "dev", "--scale", "0.001", "--quick", "--workers", str(WORKERS)]
    assert val.main(args) == 0
    printed = capsys.readouterr().out
    hashes = {}
    for line in printed.splitlines():
        if line.strip().startswith("quick_hashes."):
            k, v = line.strip().removeprefix("quick_hashes.").split(" = ")
            hashes[k] = v
    assert set(hashes) == {"committed_study", "null_validation", "power_grid", "failure_and_sensitivity"}
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"seed": DEV, "scale": 0.001, "quick_hashes": hashes}), encoding="utf-8")
    assert val.main([*args, "--check", "--summary", str(summary)]) == 0
    assert "quick check passed" in capsys.readouterr().out
    tampered = dict(hashes, power_grid=hashes["power_grid"][:-1] + ("0" if hashes["power_grid"][-1] != "0" else "1"))
    summary.write_text(json.dumps({"seed": DEV, "scale": 0.001, "quick_hashes": tampered}), encoding="utf-8")
    assert val.main([*args, "--check", "--summary", str(summary)]) == 1
    assert "MISMATCH power_grid" in capsys.readouterr().out


# ---- refusals ---------------------------------------------------------------------------------------------------------------


def test_refusals(capsys: pytest.CaptureFixture[str]) -> None:
    assert val.main(["--seed", "dev", "--scale", "0.001", "--out", str(REPO_ROOT / "validation" / "site_signal")]) == 2
    assert "never reads or writes" in capsys.readouterr().err
    assert val.main(["--seed", "dev", "--scale", "0.001", "--out", str(REPO_ROOT / "monitoring" / "out" / "x")]) == 2
    assert val.main(["--seed", "dev", "--scale", "0.001"]) == 2
    assert "needs --out" in capsys.readouterr().err
    assert val.main(["--seed", "eval", "--scale", "0.5"]) == 2  # refused before any evaluation-seed draw
    assert "--scale 1" in capsys.readouterr().err
    assert val.main(["--check"]) == 2


def test_eval_study_lists_from_answer_key() -> None:
    """§12.7 illustration: caught / missed positives at Look with their tier, and the must-be-grey sites."""
    doc = {
        "answer_key": [{"site_id": "102", "label": "gross_under"}, {"site_id": "103", "label": "under_25"},
                       {"site_id": "104", "label": "under_50"}, {"site_id": "105", "label": "honest"}],
        "confusion": {"discordance": {"watch": {"tp": 1, "fp": 0, "fn": 2, "tn": 1}}},
        "flags": {"discordance": {"watch": {"caught": ["102"], "missed": ["103", "104"], "false_flags": []},
                                  "look": {"caught": ["102"], "missed": ["103", "104"], "false_flags": ["105"]},
                                  "not_computed_positives": ["104"]}},
        "must_be_grey": [{"site_id": "110", "label": "small_site",
                          "indicators": {"discordance": {"not_computed_reason": "insufficient_patients"}}}],
    }
    out = val.eval_study_lists(doc)
    assert out["confusion"] == doc["confusion"]
    assert out["caught"] == [{"indicator": "discordance", "site_id": "102", "label": "gross_under", "tier": "watch"}]
    assert [(m["site_id"], m["tier"]) for m in out["missed"]] == [("103", "none"), ("104", "not_computed")]
    assert out["false_flags"] == [{"indicator": "discordance", "site_id": "105", "label": "honest", "tier": "look"}]
    assert out["not_computed"][0]["reason"] == "insufficient_patients"
    assert val.eval_study_block("dev", DEV) is None  # the dev seed never reads monitoring/out/
