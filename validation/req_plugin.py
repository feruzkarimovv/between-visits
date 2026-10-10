"""pytest plugin: record requirement markers and outcomes to $BV_REQ_OUT (used by build_traceability.py)."""

import json
import os

import pytest

_results: list[dict] = []


def pytest_runtest_logreport(report):  # noqa: ANN001
    if report.when != "call" and not (report.when == "setup" and report.outcome != "passed"):
        return
    reqs = [m.args[0] for m in getattr(report, "_bv_markers", [])]
    _results.append({"nodeid": report.nodeid, "outcome": report.outcome, "reqs": reqs})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ANN001
    outcome = yield
    rep = outcome.get_result()
    rep._bv_markers = list(item.iter_markers(name="req"))


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    out = os.environ.get("BV_REQ_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(_results, f, indent=1)
