"""REQ-030 SIMULATED / MEASURED labeling of the Site Signal outputs (docs/11-site-signal-sap.md §2.3, §15 rule 2;
docs/03-api-contracts.md §5.1; WS5 task S6).

* Every object in ``monitoring/out/*.json`` carries ``data_origin``: each document, the run block, and every object
  inside an array at any depth (sites, rows, episodes, site AE rows, answer-key rows, funnel points and limits, ...).
  Everything ``monitoring/`` writes is simulated, so the value is ``SIMULATED``.
* Synthetic quotes are labeled: every episode's evidence has ``source: "synthetic"``, no audio timestamp, and an
  English translation of a Spanish quote is marked AI-assisted (``translation_is_ai: true``).
* ``report.md`` and ``funnel.svg`` badge their numbers SIMULATED, the confusion is labeled "illustration only", and
  the report links the SAP and states the next step (§15 rules 7 and 8).

The committed outputs are checked when they exist; otherwise (before the lead's logged evaluation-seed run) a
dev-seed run into a temporary directory is checked. Never the evaluation seed in tests. SIMULATED.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from bvsignal import DATA_ORIGIN, MONITORING_DIR, REPO_ROOT

pytestmark = pytest.mark.req("REQ-030")

COMMITTED_OUT = MONITORING_DIR / "out"
COMMITTED_REPORT = REPO_ROOT / "validation" / "site_signal"
R_CAL = 20  # development calibration size for the fallback run (never a result)


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """{"json": [files], "report_dir": dir}: the committed outputs when `make site-signal` has written them, else a
    dev-seed run in a temporary directory (plus any committed monitoring/out/*.json, e.g. thresholds.json)."""
    committed = sorted(COMMITTED_OUT.glob("*.json")) if COMMITTED_OUT.is_dir() else []
    if (COMMITTED_OUT / "signal_run.json").is_file():
        return {"json": committed, "report_dir": COMMITTED_REPORT, "source": "committed"}
    out = tmp_path_factory.mktemp("s6_labels")
    proc = subprocess.run([sys.executable, "-m", "bvsignal.run", "--seed", "dev", "--out", str(out), "--r-cal",
                           str(R_CAL), "--workers", "1"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    return {"json": committed + sorted(out.glob("*.json")), "report_dir": out, "source": "dev"}


def records(doc: Any, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """The objects that must carry data_origin: the document itself, its run block, and every object inside an array
    (at any depth)."""
    def walk(x: Any, where: str, in_array: bool) -> Iterator[tuple[str, dict[str, Any]]]:
        if isinstance(x, dict):
            if in_array or where in (path, f"{path}.run"):
                yield where, x
            for k, v in x.items():
                yield from walk(v, f"{where}.{k}", False)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from walk(v, f"{where}[{i}]", True)

    yield from walk(doc, path, False)


def test_every_output_object_has_data_origin(outputs: dict[str, Any]) -> None:
    files = outputs["json"]
    names = {p.name for p in files}
    assert {"signal_run.json", "episodes.json", "site_ae.json", "answer_key.json"} <= names, sorted(names)
    bad: list[str] = []
    n = 0
    for p in files:
        for where, obj in records(json.loads(p.read_text(encoding="utf-8")), p.name):
            n += 1
            if obj.get("data_origin") != DATA_ORIGIN:
                bad.append(f"{where}: data_origin={obj.get('data_origin')!r}")
    assert n > 0
    assert not bad, f"{len(bad)} objects without data_origin {DATA_ORIGIN}: {bad[:10]}"


def test_top_level_documents_are_labeled(outputs: dict[str, Any]) -> None:
    for p in outputs["json"]:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            assert doc.get("data_origin") == DATA_ORIGIN, p.name
        else:
            assert isinstance(doc, list) and all(isinstance(x, dict) for x in doc), p.name


def test_synthetic_quotes_are_labeled(outputs: dict[str, Any]) -> None:
    path = next(p for p in outputs["json"] if p.name == "episodes.json")
    episodes = json.loads(path.read_text(encoding="utf-8"))
    quoted = [e for e in episodes if e.get("evidence") and e["evidence"].get("quote")]
    assert quoted, "no episode carries a synthetic quote"
    for e in quoted:
        ev = e["evidence"]
        assert ev["source"] == "synthetic", e["episode_id"]
        assert ev["t_s"] is None, e["episode_id"]
        if ev.get("translation_en"):
            assert ev["translation_is_ai"] is True, e["episode_id"]
        if ev["quote_lang"] == "es":
            assert ev.get("translation_en"), e["episode_id"]


def test_report_badges_every_number(outputs: dict[str, Any]) -> None:
    report = outputs["report_dir"] / "report.md"
    svg = outputs["report_dir"] / "funnel.svg"
    md = report.read_text(encoding="utf-8")
    # every section heading that carries numbers is badged, and every table with a Data column badges each row
    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith(("## Deviations", "## Next step")):
            assert "SIMULATED" in line, line
    tables = 0
    for block in re.split(r"\n\s*\n", md):
        lines = [x for x in block.splitlines() if x.startswith("|")]
        if len(lines) < 3 or "| Data |" not in lines[0]:
            continue
        tables += 1
        for row in lines[2:]:
            assert row.rstrip().endswith("| `SIMULATED` |"), row
    assert tables >= 5
    assert "illustration only" in md.lower()
    assert "docs/11-site-signal-sap.md" in md
    assert "paired patient-reported and clinician-reported" in md
    assert "a reason to look, not a finding" in md.lower()
    for banned in ("under-report", "underreport", "fraud", "misconduct", "clean"):
        assert banned not in md.lower(), banned
    text = svg.read_text(encoding="utf-8")
    assert text.startswith("<svg") and "SIMULATED" in text
