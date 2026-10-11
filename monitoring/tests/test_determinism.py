"""Determinism of ``make site-signal`` (docs/11-site-signal-sap.md §11, §15 rule 7; WS5 task S6).

Two full dev-seed runs of ``python -m bvsignal.run`` (development calibration, simulate, match, indicators, outputs,
report.md and funnel.svg) into two temporary directories must give byte-identical files. The two runs use
different worker counts, so the outputs also do not depend on the number of worker processes. ``code_commit`` and
``generated_at`` come from git (the last commit that changed an analysis input and its commit time), never from the
clock, so a rerun of the same commit reproduces every byte.

Never the evaluation seed in tests: development runs only (``--seed dev``), outputs only under pytest's temporary
directory, never in ``monitoring/out/`` or ``validation/site_signal/``. SIMULATED.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from bvsignal import MONITORING_DIR, REPO_ROOT
from bvsignal import run as bvrun

# Null studies of the development calibration inside each run: enough to exercise calibrate.py's procedure and
# writer end to end while keeping the test fast. Development thresholds are never a result.
R_CAL = 20
COMMITTED_DIRS = (MONITORING_DIR / "out", REPO_ROOT / "validation" / "site_signal")


def dev_run(out: Path, workers: int) -> subprocess.CompletedProcess[str]:
    """One full dev-seed run in a fresh interpreter, as `make site-signal` would run it (but with --seed dev)."""
    cmd = [sys.executable, "-m", "bvsignal.run", "--seed", "dev", "--out", str(out), "--r-cal", str(R_CAL),
           "--workers", str(workers)]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=False)


def digests(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def snapshot_committed() -> dict[str, dict[str, str]]:
    return {str(d): digests(d) if d.is_dir() else {} for d in COMMITTED_DIRS}


def test_two_dev_runs_are_byte_identical(tmp_path: Path) -> None:
    before = snapshot_committed()
    a, b = tmp_path / "a", tmp_path / "b"
    first = dev_run(a, workers=1)
    assert first.returncode == 0, first.stderr
    second = dev_run(b, workers=2)
    assert second.returncode == 0, second.stderr

    da, db = digests(a), digests(b)
    expected = {*bvrun.OUTPUT_NAMES, *bvrun.bvreport.OUTPUT_NAMES, bvrun.THRESHOLDS, bvrun.NULL_POOL}
    if not bvrun.equity_available():
        expected.discard(bvrun.EQUITY)
    assert set(da) == expected, f"unexpected output set {sorted(da)}"
    assert da == db, {name: (da.get(name), db.get(name)) for name in sorted(set(da) | set(db))
                      if da.get(name) != db.get(name)}
    assert "DEVELOPMENT OUTPUT" in first.stdout and "SIMULATED" in first.stdout
    # development runs never touch the committed output directories
    assert snapshot_committed() == before


@pytest.mark.parametrize("out", [None, "monitoring/out", "monitoring/out/sub", "validation/site_signal"])
def test_dev_seed_refuses_committed_directories(out: str | None, capsys: pytest.CaptureFixture[str]) -> None:
    before = snapshot_committed()
    argv = ["--seed", "dev"] + ([] if out is None else ["--out", str(REPO_ROOT / out)])
    assert bvrun.main(argv) == 2
    err = capsys.readouterr().err
    assert "--seed dev never writes into" in err
    assert snapshot_committed() == before
