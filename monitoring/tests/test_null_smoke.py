"""S4: calibrate.py (docs/11 §9.2-§9.3) and the null smoke test (REQ-023). SIMULATED, dev seed only.

The null smoke test checks the thresholds out of sample on 200 fresh null studies (dev seed, stream
``streams.null_validation``), never on the studies that set them:

* if ``monitoring/out/thresholds.json`` exists (the committed calibration, evaluation seed, stream 1), those
  thresholds are used as they are;
* until then, thresholds are calibrated in the test from ``R_CAL`` null studies of the dev seed on stream
  ``streams.calibration``, the procedure of ``calibrate.py`` with a smaller R.

Targets (one-sided): Look per-site rate <= 0.085 and Watch family-wise rate <= 0.16, for capture discordance
and for each comparator and the ablation. With 200 studies of about 15 computed sites the Look rate's Monte
Carlo SE is about 0.005 and the Watch rate's about 0.02, so the margins (0.035 and 0.06 above the nominal 0.05
and 0.10) are several SEs wide. Runtime is about 10 s on 8 cores and under 90 s on 2.

No evaluation-seed run happens in this module: the evaluation-seed code paths are only exercised up to their
refusals, or with the dev seed substituted.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bvsignal import DATA_ORIGIN, REPO_ROOT
from bvsignal import calibrate as cb
from bvsignal import indicators as ind
from bvsignal import seed as bvseed

PARAMS = bvseed.load_params()
DEV = int(PARAMS["seeds"]["dev"])
CALIBRATION_STREAM = int(PARAMS["streams"]["calibration"])
VALIDATION_STREAM = int(PARAMS["streams"]["null_validation"])
CELL = int(PARAMS["cell_index"]["none"])
ROLE = int(PARAMS["roles"]["null_or_committed"])
R_CAL = 500
N_EVAL = 200
LOOK_MAX = 0.085
WATCH_MAX = 0.16
WORKERS = max(1, min(os.cpu_count() or 1, 8))


# ---- §9.3 discreteness rule --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("values", "alpha", "expected"), [
    pytest.param(list(range(1, 21)), 0.10, 2.0, id="continuous: the floor(alpha |S|)-th order statistic"),
    pytest.param(list(range(1, 20)), 0.10, 1.0, id="floor: 19 values at 10% give the 1st"),
    pytest.param([1, 1, 2, 3, 4, 5, 6, 7, 8, 9], 0.10, -math.inf, id="a tie that would exceed alpha: -inf"),
    pytest.param([1, 2, 2, 2, 5, 6, 7, 8, 9, 10], 0.25, 1.0, id="ties never push the rate above alpha"),
    pytest.param([1, 2, 2, 2, 5, 6, 7, 8, 9, 10], 0.40, 2.0, id="a tie is taken whole when it fits"),
    pytest.param([-1.5, math.inf, math.inf, -3.0, 0.2], 0.40, -1.5, id="+inf minima (no computed site) count in |S|"),
    pytest.param([], 0.05, -math.inf, id="empty: -inf"),
])
def test_calibrated_threshold_discreteness_rule(values: list[float], alpha: float, expected: float) -> None:
    c = cb.calibrated_threshold(np.array(values, dtype=float), alpha)
    assert c == expected
    if values and math.isfinite(c):  # the achieved in-sample rate never exceeds alpha
        assert np.mean(np.array(values) <= c) <= alpha


def test_calibrate_indicator_by_hand() -> None:
    """§9.2 steps 3-5 and §12.8 on four tiny 'null studies' (values = computed sites' statistics)."""
    studies = [np.array([-3.0, 0.5, 1.0]), np.array([-1.0, -0.2]), np.array([]), np.array([-2.5, 0.1, 0.3, 2.0])]
    c = cb.calibrate_indicator("discordance", studies, 0.25, 0.25)
    pooled = sorted(v for s in studies for v in s)  # 9 values: Look = the 2nd smallest (2/9 <= 0.25 < 3/9)
    assert c.c_look == pooled[1] == -2.5
    # minima: -3.0, -1.0, +inf, -2.5 -> Watch at 25% is the smallest (1/4); min(c_watch, c_look) keeps -3.0
    assert c.c_watch_uncapped == -3.0 and c.c_watch == -3.0
    F, K = np.array([1, 0, 0, 1]), np.array([3, 2, 0, 4])
    assert np.array_equal(c.false_look_per_study, F) and np.array_equal(c.computed_per_study, K)
    rate = F.sum() / K.sum()
    assert c.look_rate == pytest.approx(rate)
    se = math.sqrt(float(np.sum((F - rate * K) ** 2)) / (4 * 3)) / K.mean()
    assert c.look_mc_se == pytest.approx(se)
    assert c.watch_rate == 0.25 and c.watch_mc_se == pytest.approx(math.sqrt(0.25 * 0.75 / 4))
    assert c.expected_false_look == 0.5 and c.expected_false_look_mc_se == pytest.approx(np.std(F, ddof=1) / 2)
    assert c.achieved()["studies_without_computed_site"] == 1


def test_watch_is_capped_at_look_and_minus_inf_is_never_assigned() -> None:
    # every study has one computed site: minima = pooled, so the 50% Watch threshold would exceed Look at 10%
    studies = [np.array([float(v)]) for v in range(10)]
    c = cb.calibrate_indicator("rate_kri", studies, 0.10, 0.50)
    assert c.c_look == 0.0 and c.c_watch_uncapped == 4.0 and c.c_watch == 0.0
    assert c.to_dict()["watch_capped_at_look"] is True
    # simaerep: served = the negated calibrated value; -inf -> null, never assigned
    tied = [np.array([-1.0, -1.0]), np.array([-1.0, 0.0])]
    s = cb.calibrate_indicator("simaerep_classic", tied, 0.05, 0.10)
    assert s.c_look == -math.inf and s.served() == {"look": None, "watch": None}
    d = s.to_dict()
    assert d["never_assigned"] == {"look": True, "watch": True} and d["flag_when"] == ">="
    sims = [np.array([-0.999, 0.0]), np.array([-0.5, 0.0]), np.array([-0.5, 0.0]), np.array([0.0, 0.0])]
    flipped = cb.calibrate_indicator("simaerep_classic", sims, 0.15, 0.30)
    assert (flipped.c_look, flipped.c_watch) == (-0.999, -0.999)
    assert flipped.served() == {"look": 0.999, "watch": 0.999}


# ---- determinism, outputs and the command line ----------------------------------------------------------------------


def test_results_do_not_depend_on_the_worker_count() -> None:
    one = cb.calibrate(DEV, 6, workers=1)
    two = cb.calibrate(DEV, 6, workers=2)
    prov = {"sap_tag_commit": None, "eval_seed": None, "seed_label": "dev", "seed": DEV}
    assert cb.documents(one, prov) == cb.documents(two, prov)
    assert np.array_equal(one.discordance_pool, two.discordance_pool)


def test_dev_run_writes_labeled_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "cal"
    assert cb.main(["--seed", "dev", "--r", "4", "--workers", "1", "--out", str(out)]) == 0
    assert "DEVELOPMENT OUTPUT" in capsys.readouterr().out
    doc = json.loads((out / "thresholds.json").read_text(encoding="utf-8"))
    pool_bytes = (out / "null_pool.json").read_bytes()
    pool = json.loads(pool_bytes)
    assert doc["data_origin"] == pool["data_origin"] == DATA_ORIGIN
    assert doc["_about"].startswith("DEVELOPMENT OUTPUT") and pool["_about"].startswith("DEVELOPMENT OUTPUT")
    assert doc["seed_label"] == "dev" and doc["seed"] == DEV and doc["eval_seed"] is None and doc["r_null"] == 4
    assert doc["keys"] == {"stream": CALIBRATION_STREAM, "cell_index": CELL, "role": ROLE, "replicates": [0, 3]}
    assert doc["alpha"] == {"look": 0.05, "watch": 0.10}
    for name in ind.INDICATORS:
        block = doc[name]
        assert block["flag_when"] == ind.FLAG_WHEN[name]
        assert {k: block[k] is None for k in ("look", "watch")} == block["never_assigned"]
        for tier in ("look", "watch"):
            assert set(doc["achieved"][name][tier]) == {"rate", "mc_se"}
    assert doc["expected_false_look_flags_per_study"] == doc["achieved"]["discordance"][
        "expected_false_look_flags_per_study"]["mean"]
    assert doc["null_pool"]["sha256"] == hashlib.sha256(pool_bytes).hexdigest()
    assert pool["M"] == len(pool["values"]) == doc["achieved"]["discordance"]["n_pooled"]
    assert pool["values"] == sorted(pool["values"])
    assert ind.load_thresholds(out / "thresholds.json").keys() == set(ind.INDICATORS)
    assert ind.load_null_pool(out / "null_pool.json").size == pool["M"]
    # a second run gives byte-identical files (generated_at is the code commit's time, not the clock)
    first = (out / "thresholds.json").read_bytes()
    assert cb.main(["--seed", "dev", "--r", "4", "--workers", "1", "--out", str(out)]) == 0
    assert (out / "thresholds.json").read_bytes() == first and (out / "null_pool.json").read_bytes() == pool_bytes


@pytest.fixture
def no_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any refusal test that got past its refusal would fail here instead of running a calibration."""

    def must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("calibration must not start")

    monkeypatch.setattr(cb, "calibrate", must_not_run)


@pytest.mark.parametrize("argv", [
    pytest.param(["--seed", "dev", "--out", "monitoring/out"], id="dev into monitoring/out"),
    pytest.param(["--seed", "dev", "--out", str(REPO_ROOT / "monitoring" / "out" / "dev")], id="dev below monitoring/out"),
    pytest.param(["--seed", "dev", "--out", str(REPO_ROOT / "validation" / "site_signal")], id="dev into validation"),
    pytest.param(["--seed", "dev"], id="dev without --out"),
    pytest.param(["--seed", "eval", "--r", "10"], id="eval with a development R"),
    pytest.param(["--r", "10"], id="eval is the default seed"),
    pytest.param(["--seed", "eval", "--out", "/tmp/elsewhere"], id="eval outside monitoring/out"),
])
def test_refusals(argv: list[str], no_run: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
                  tmp_path: Path) -> None:
    monkeypatch.chdir(REPO_ROOT)
    assert cb.main(argv) == 2
    assert "bvsignal.calibrate:" in capsys.readouterr().err
    assert not (REPO_ROOT / "monitoring" / "out" / "dev").exists()


def test_refuses_a_frozen_input_mismatch(no_run: None, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.setattr(bvseed, "check_frozen", lambda: (False, ["MISMATCH  rules_py_sha256: ..."]))
    assert cb.main(["--seed", "dev", "--out", str(tmp_path)]) == 2
    assert "frozen inputs" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_evaluation_mode_logs_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The eval branch writes the outputs and appends them to the run log. The seed is replaced by the dev seed
    and the log writer by a recorder, so no evaluation-seed run happens here."""
    committed = ind.THRESHOLDS_FILE.read_bytes() if ind.THRESHOLDS_FILE.exists() else None
    logged: list[tuple[list[str], list[Path]]] = []
    monkeypatch.setattr(cb, "resolve_run", lambda label, r, out, params: (DEV, 3, tmp_path))
    monkeypatch.setattr(cb, "provenance", lambda label, seed: {"seed_label": label, "seed": seed})
    monkeypatch.setattr(bvseed, "log_run", lambda command, outputs: logged.append((command, list(outputs))))
    assert cb.main(["--workers", "1"]) == 0
    assert logged == [(["python", "-m", "bvsignal.calibrate", "--workers", "1"],
                       [tmp_path / "thresholds.json", tmp_path / "null_pool.json"])]
    assert all((tmp_path / name).exists() for name in ("thresholds.json", "null_pool.json"))
    assert (ind.THRESHOLDS_FILE.read_bytes() if ind.THRESHOLDS_FILE.exists() else None) == committed


# ---- the null smoke test (REQ-023) -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def smoke() -> dict[str, Any]:
    if ind.THRESHOLDS_FILE.exists():
        served = ind.load_thresholds(ind.THRESHOLDS_FILE)
        source = "committed monitoring/out/thresholds.json"
        thresholds = {}
        for name, t in served.items():
            flip = -1.0 if ind.FLAG_WHEN[name] == ind.AT_OR_ABOVE else 1.0
            thresholds[name] = {k: -math.inf if t[k] is None else flip * t[k] for k in ind.TIER_KEYS}
    else:
        cal = cb.calibrate(DEV, R_CAL, workers=WORKERS)
        source = f"calibrated in the test: dev seed, stream {cal.stream}, R = {R_CAL}"
        thresholds = {name: {ind.LOOK: c.c_look, ind.WATCH: c.c_watch} for name, c in cal.indicators.items()}
    jobs = [cb.NullJob(DEV, VALIDATION_STREAM, CELL, ROLE, i) for i in range(N_EVAL)]
    studies = cb.run_null(jobs, WORKERS)
    rates = {}
    for name, t in thresholds.items():
        vals = [s[name] for s in studies]
        K = sum(v.size for v in vals)
        F = sum(int(np.count_nonzero(v <= t[ind.LOOK])) for v in vals)
        W = sum(bool(v.size) and float(v.min()) <= t[ind.WATCH] for v in vals)
        rates[name] = {"look_per_site": F / K, "watch_fwer": W / N_EVAL, "K": K}
    return {"source": source, "rates": rates, "thresholds": thresholds}


@pytest.mark.req("REQ-023")
def test_null_smoke_discordance(smoke: dict[str, Any]) -> None:
    """Out-of-sample null false-flag rates of capture discordance: Look per site <= 0.085, Watch FWER <= 0.16."""
    r = smoke["rates"][ind.DISCORDANCE]
    print(f"null smoke ({smoke['source']}; {N_EVAL} fresh dev-seed null studies, stream {VALIDATION_STREAM}): "
          f"discordance Look per site {r['look_per_site']:.4f} over {r['K']} computed sites, Watch FWER "
          f"{r['watch_fwer']:.4f} (SIMULATED, development check, not a result)")
    assert r["K"] >= N_EVAL * 10  # computed sites exist in (almost) every null study
    assert r["look_per_site"] <= LOOK_MAX
    assert r["watch_fwer"] <= WATCH_MAX


@pytest.mark.req("REQ-023")
@pytest.mark.parametrize("name", [ind.RATE_KRI, ind.SIMAEREP, ind.ABLATION])
def test_null_smoke_comparators_and_ablation(smoke: dict[str, Any], name: str) -> None:
    """The comparators and the ablation are calibrated by the same procedure on the same null studies."""
    r = smoke["rates"][name]
    assert r["K"] > 0
    assert r["look_per_site"] <= LOOK_MAX
    assert r["watch_fwer"] <= WATCH_MAX


def test_null_smoke_never_reads_an_evaluation_seed_stream() -> None:
    """The smoke test's keys are dev-seed keys on the calibration and validation streams."""
    assert DEV == 20261011
    assert (CALIBRATION_STREAM, VALIDATION_STREAM) == (1, 2)
    with pytest.raises(ValueError):
        cb.calibrate(DEV, 0)
