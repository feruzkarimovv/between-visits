"""Build the GxP-lite validation pack: requirement ↔ automated test ↔ latest result.

Runs the backend test suite with a small plugin that records @pytest.mark.req("REQ-xxx") markers, then writes
validation/traceability.md and validation/summary.json. `--check` exits 1 if any requirement has no test or a
failing test (CI runs this on every push). `--no-run` reuses the last raw results.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "validation"
RAW = VAL / ".last_results.json"


def commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "uncommitted"
    except OSError:
        return "uncommitted"


def run_tests() -> int:
    env = {**os.environ, "BV_REQ_OUT": str(RAW), "PYTHONPATH": f"{VAL}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "req_plugin", "-p", "no:cacheprovider"]
    return subprocess.run(cmd, cwd=ROOT / "backend", env=env).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()
    rc = 0 if args.no_run else run_tests()
    results = json.loads(RAW.read_text())
    reqs = yaml.safe_load((VAL / "requirements.yaml").read_text())["requirements"]
    # REQ-014 (equity split) is proven by the evaluation output as well as unit tests
    rows, problems = [], []
    for r in reqs:
        tests = [t for t in results if r["id"] in t["reqs"]]
        passed = sum(t["outcome"] == "passed" for t in tests)
        status = "PASS" if tests and passed == len(tests) else ("NO TEST" if not tests else "FAIL")
        if status != "PASS":
            problems.append(f"{r['id']}: {status}")
        rows.append({"id": r["id"], "title": r["title"], "risk": r.get("risk"), "text": r["text"],
                     "tests": [t["nodeid"] for t in tests], "passed": passed, "total": len(tests), "status": status})
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sha = commit()
    summary = {
        "generated_at": now, "commit": sha, "requirements": len(rows),
        "requirements_passing": sum(r["status"] == "PASS" for r in rows),
        "tests_total": len(results), "tests_passed": sum(t["outcome"] == "passed" for t in results),
        "tests_linked": sum(1 for t in results if t["reqs"]),
        "pytest_exit_code": rc, "rows": rows,
    }
    (VAL / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    md = [
        "# Validation traceability", "",
        f"Generated {now} at commit `{sha}` by `make validate`. Every requirement links to automated tests "
        "(`@pytest.mark.req`) and their latest result. Synthetic data; not a validated medical device.", "",
        f"**{summary['requirements_passing']}/{len(rows)} requirements passing** · "
        f"{summary['tests_passed']}/{summary['tests_total']} tests passing · {summary['tests_linked']} tests linked to requirements", "",
        "| Requirement | Risk | Tests | Result |", "|---|---|---|---|",
    ]
    for r in rows:
        tests = "<br>".join(f"`{t.split('::', 1)[-1]}`" for t in r["tests"]) or "—"
        md.append(f"| **{r['id']}** {r['title']}: {r['text']} | {r['risk']} | {tests} | {r['status']} ({r['passed']}/{r['total']}) |")
    (VAL / "traceability.md").write_text("\n".join(md) + "\n")
    print(f"validation: {summary['requirements_passing']}/{len(rows)} requirements passing, "
          f"{summary['tests_passed']}/{summary['tests_total']} tests passing")
    for p in problems:
        print("  " + p)
    if args.check and (problems or rc != 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
