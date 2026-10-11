"""Build the GxP-lite validation pack: requirement ↔ automated test ↔ latest result.

Runs the backend test suite and the Site Signal monitoring suite (monitoring/, its own uv project with numpy and
scipy) with a small plugin that records @pytest.mark.req("REQ-xxx") markers, merges both result sets, then writes
validation/traceability.md and validation/summary.json. Node IDs carry their suite's directory (backend/tests/...,
monitoring/tests/...). `--check` exits 1 if any requirement has no test or a failing or skipped test, or if either
suite fails (CI runs this on every push). `--no-run` reuses the last raw results.
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

# (suite, working directory, pytest command). The backend suite runs in this interpreter (uv run --project backend);
# the monitoring suite runs in its own project environment and never rewrites monitoring/uv.lock (--frozen).
PYTEST_ARGS = ["-q", "-p", "req_plugin", "-p", "no:cacheprovider"]
SUITES = [
    ("backend", ROOT / "backend", [sys.executable, "-m", "pytest", *PYTEST_ARGS]),
    ("monitoring", ROOT / "monitoring",
     ["uv", "run", "--frozen", "--project", str(ROOT / "monitoring"), "pytest", *PYTEST_ARGS]),
]


def commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "uncommitted"
    except OSError:
        return "uncommitted"


def run_tests() -> None:
    """Run every suite with the req plugin and write the merged results and each suite's exit code to RAW."""
    merged: list[dict] = []
    codes: dict[str, int] = {}
    for name, cwd, cmd in SUITES:
        out = VAL / f".last_results.{name}.json"
        out.unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # uv picks each project's own environment
        env.update(BV_REQ_OUT=str(out), PYTHONPATH=f"{VAL}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")
        print(f"validation: running the {name} suite", flush=True)
        try:
            codes[name] = subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode
        except OSError as e:  # e.g. uv not on PATH: the suite fails, never a silent pass
            print(f"validation: could not run the {name} suite: {e}", file=sys.stderr)
            codes[name] = 1
        results = json.loads(out.read_text()) if out.exists() else []
        out.unlink(missing_ok=True)
        if not results and codes[name] == 0:
            codes[name] = 1  # a suite that reported no test is a failure, never a silent pass
        merged += [{**t, "nodeid": f"{name}/{t['nodeid']}", "suite": name} for t in results]
    RAW.write_text(json.dumps({"exit_codes": codes, "results": merged}, indent=1) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()
    if not args.no_run:
        run_tests()
    raw = json.loads(RAW.read_text())
    codes, results = raw["exit_codes"], raw["results"]
    rc = next((c for c in codes.values() if c != 0), 0)
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
    for name, code in codes.items():
        if code != 0:
            problems.append(f"{name} suite: pytest exit code {code}")
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sha = commit()
    summary = {
        "generated_at": now, "commit": sha, "requirements": len(rows),
        "requirements_passing": sum(r["status"] == "PASS" for r in rows),
        "tests_total": len(results), "tests_passed": sum(t["outcome"] == "passed" for t in results),
        "tests_linked": sum(1 for t in results if t["reqs"]),
        "pytest_exit_code": rc, "pytest_exit_codes": codes,
        "suites": {name: sum(t["suite"] == name for t in results) for name in codes},
        "rows": rows,
    }
    (VAL / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    md = [
        "# Validation traceability", "",
        f"Generated {now} at commit `{sha}` by `make validate`. Every requirement links to automated tests "
        "(`@pytest.mark.req`) in `backend/tests` and `monitoring/tests` and their latest result. "
        "Synthetic data; not a validated medical device.", "",
        f"**{summary['requirements_passing']}/{len(rows)} requirements passing** · "
        f"{summary['tests_passed']}/{summary['tests_total']} tests passing "
        f"({', '.join(f'{n} {c}' for n, c in summary['suites'].items())}) · {summary['tests_linked']} tests linked to requirements", "",
        "| Requirement | Risk | Tests | Result |", "|---|---|---|---|",
    ]
    for r in rows:
        tests = "<br>".join(f"`{t.split('/', 1)[0]}: {t.split('::', 1)[-1]}`" for t in r["tests"]) or "—"
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
