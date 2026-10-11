"""REQ-022 Pre-registration order, checked from git history and the run log exactly as docs/11-site-signal-sap.md
§1.2 lists it (WS5 task S6):

1. the tag ``sap-v1`` exists (annotated, so it has a tagger timestamp);
2. the tag commit is an ancestor of every commit that adds files under ``monitoring/out/`` or
   ``validation/site_signal/`` (and the tag commit itself has none, §1.2 step 3);
3. the evaluation seed equals the §1.3 derivation from the tag commit and ``monitoring/seed_beacon.json``, the beacon
   round is the one the rule selects, a NIST ``B`` is backed by failed drand attempts at or after round time + 30
   min, and an empty ``B`` by failed drand and NIST attempts at or after round time + 60 min (the beacon deadlines);
4. every committed evaluation output's sha256 appears in ``validation/site_signal/run_log.jsonl``, and no log line
   predates the tag.

Outside a git checkout (for example a Docker image) the whole module is skipped with a visible reason; in CI
(``CI`` set) it never skips: the CI jobs check out with ``fetch-depth: 0`` and ``fetch-tags: true``. A git checkout
without the tag fails with a hint (``git fetch --tags``). Never the evaluation seed for a run in tests: these
checks only read git, the beacon file and the run log.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bvsignal import REPO_ROOT
from bvsignal import seed as bvseed

pytestmark = pytest.mark.req("REQ-022")

OUTPUT_DIRS = ("monitoring/out", "validation/site_signal")
RUN_LOG = bvseed.RUN_LOG_REL
HEX40 = re.compile(r"[0-9a-f]{40}")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=check)


def git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, check=True).stdout


def _in_git_checkout() -> bool:
    try:
        top = git("rev-parse", "--show-toplevel", check=False)
    except FileNotFoundError:
        return False
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == REPO_ROOT.resolve()


@pytest.fixture(scope="module", autouse=True)
def git_checkout() -> None:
    if _in_git_checkout():
        return
    reason = (f"REQ-022 needs the git history: {REPO_ROOT} is not a git checkout (for example a Docker image); run "
              "the monitoring suite from a clone with its tags")
    if os.environ.get("CI"):
        pytest.fail(reason + " (never skipped in CI: check out with fetch-depth: 0 and fetch-tags: true)")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def tag_commit() -> str:
    found = git("rev-parse", "--verify", "--quiet", f"refs/tags/{bvseed.TAG}^{{commit}}", check=False)
    assert found.returncode == 0, (f"tag {bvseed.TAG} not found in this checkout; `git fetch --tags` (CI: "
                                   "actions/checkout with fetch-depth: 0 and fetch-tags: true)")
    sha = found.stdout.strip()
    assert HEX40.fullmatch(sha), sha
    return sha


@pytest.fixture(scope="module")
def tagger_time(tag_commit: str) -> int:
    return bvseed.tag_tagger_time(REPO_ROOT)


def utc_seconds(text: str) -> int:
    return int(dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


# ---- 1. the tag exists -----------------------------------------------------------------------------------------


def test_tag_exists_and_is_annotated(tag_commit: str, tagger_time: int) -> None:
    assert git("cat-file", "-t", f"refs/tags/{bvseed.TAG}").stdout.strip() == "tag"
    assert git("cat-file", "-t", tag_commit).stdout.strip() == "commit"
    assert tagger_time > 0


# ---- 2. tag ancestry of every commit that adds an evaluation output ---------------------------------------------


def test_tag_commit_has_no_evaluation_output(tag_commit: str) -> None:
    listed = git("ls-tree", "-r", "--name-only", tag_commit).stdout.splitlines()
    early = [p for p in listed if p.startswith(tuple(d + "/" for d in OUTPUT_DIRS))]
    assert not early, f"evaluation outputs exist at the tag commit (docs/11 §1.2 step 3): {early}"


def test_tag_is_ancestor_of_every_output_commit(tag_commit: str) -> None:
    adding = git("log", "--diff-filter=A", "--format=%H", "HEAD", "--", *OUTPUT_DIRS).stdout.split()
    not_after = [c for c in adding
                 if git("merge-base", "--is-ancestor", tag_commit, c, check=False).returncode != 0]
    assert not not_after, f"commits add evaluation outputs without descending from {bvseed.TAG}: {not_after}"


# ---- 3. evaluation seed, beacon round and beacon deadlines --------------------------------------------------------


@pytest.fixture(scope="module")
def beacon() -> dict[str, Any]:
    path = REPO_ROOT / bvseed.BEACON_REL
    assert path.is_file(), f"{bvseed.BEACON_REL} is missing; it is committed after the beacon round (docs/11 §1.2 step 7)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schedule(tagger_time: int) -> dict[str, int]:
    return bvseed.beacon_schedule(tagger_time, bvseed.beacon_config(REPO_ROOT))


def expected_eval_seed(tag_commit: str, randomness: str) -> int:
    """docs/11 §1.3, written out independently of seed.py: int(sha256("sap-v1:" + S + ":" + B)[:8], 16)."""
    return int(hashlib.sha256(f"sap-v1:{tag_commit}:{randomness}".encode()).hexdigest()[:8], 16)


def test_eval_seed_is_the_derivation(tag_commit: str, beacon: dict[str, Any]) -> None:
    assert isinstance(beacon["randomness"], str)
    seed = expected_eval_seed(tag_commit, beacon["randomness"])
    assert bvseed.eval_seed(REPO_ROOT) == seed


def test_beacon_round_is_the_selected_one(beacon: dict[str, Any], schedule: dict[str, int]) -> None:
    sel = beacon["selection"]
    for k in ("tagger_time", "target_time", "drand_round_time", "nist_allowed_from", "empty_allowed_from"):
        assert utc_seconds(sel[k]) == schedule[k], k
    assert sel["drand_round"] == schedule["drand_round"]
    # the target is at least 10 minutes after the tagger timestamp (params.yaml seeds.beacon.delay_seconds)
    assert schedule["target_time"] - schedule["tagger_time"] >= 600
    if beacon["source"] == "drand":
        assert beacon["round"] == schedule["drand_round"]
        assert re.fullmatch(r"[0-9a-f]{64}", beacon["randomness"]), "drand randomness is 64 hex characters"
        assert str(beacon["round"]) in str(beacon["url"])


def _failed(attempts: list[dict[str, Any]], source: str, not_before: int) -> list[dict[str, Any]]:
    return [a for a in attempts if a.get("source") == source and utc_seconds(a["utc_time"]) >= not_before]


def test_beacon_fallback_is_backed_by_failed_attempts(beacon: dict[str, Any], schedule: dict[str, int]) -> None:
    attempts = beacon["attempts"]
    assert isinstance(attempts, list)
    for a in attempts:
        assert {"utc_time", "source", "url", "error"} <= set(a), a
    if beacon["randomness"] == "":
        assert _failed(attempts, "drand", schedule["empty_allowed_from"]), \
            "an empty B needs a failed drand attempt at or after round time + 60 min"
        assert _failed(attempts, "nist", schedule["empty_allowed_from"]), \
            "an empty B needs a failed NIST attempt at or after round time + 60 min"
    elif str(beacon["source"]).lower().startswith("nist"):
        assert _failed(attempts, "drand", schedule["nist_allowed_from"]), \
            "a NIST B needs a failed drand attempt at or after round time + 30 min"
    else:
        assert beacon["source"] == "drand", beacon["source"]


# ---- 4. every committed evaluation output is in the run log; no log line predates the tag -----------------------


def committed_outputs() -> list[str]:
    listed = git("ls-files", "--", *OUTPUT_DIRS).stdout.splitlines()
    return sorted(p for p in listed if p != RUN_LOG and not Path(p).name.startswith("."))


def run_log_entries() -> list[dict[str, Any]]:
    if RUN_LOG not in git("ls-files", "--", RUN_LOG).stdout.splitlines():
        return []
    text = git_bytes("show", f"HEAD:{RUN_LOG}").decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_every_committed_output_is_logged() -> None:
    logged: dict[str, set[str]] = {}
    for entry in run_log_entries():
        for path, sha in entry["output_sha256"].items():
            logged.setdefault(path, set()).add(sha)
    unlogged = []
    for path in committed_outputs():
        sha = hashlib.sha256(git_bytes("cat-file", "blob", f"HEAD:{path}")).hexdigest()
        if sha not in logged.get(path, set()):
            unlogged.append(f"{path} ({sha})")
    assert not unlogged, f"committed evaluation outputs not in {RUN_LOG}: {unlogged}"


def test_no_log_line_predates_the_tag(tagger_time: int) -> None:
    for entry in run_log_entries():
        assert {"utc_time", "code_commit", "git_dirty", "command", "output_sha256"} <= set(entry), entry
        assert utc_seconds(entry["utc_time"]) >= tagger_time, entry["utc_time"]
        assert entry["git_dirty"] is False, entry
        assert HEX40.fullmatch(entry["code_commit"]), entry["code_commit"]


def test_committed_outputs_carry_the_tag_and_seed(tag_commit: str, beacon: dict[str, Any]) -> None:
    """Every committed JSON output that states sap_tag_commit or eval_seed states the tag commit and the seed."""
    seed = expected_eval_seed(tag_commit, beacon["randomness"])
    wrong = []
    for path in committed_outputs():
        if not path.endswith(".json"):
            continue
        doc = json.loads(git_bytes("cat-file", "blob", f"HEAD:{path}").decode("utf-8"))
        for block in (doc, doc.get("run")) if isinstance(doc, dict) else ():
            if not isinstance(block, dict):
                continue
            stated = block.get("sap_tag_commit")
            if "sap_tag_commit" in block and not (isinstance(stated, str) and len(stated) >= 7
                                                  and tag_commit.startswith(stated)):  # full or short sha
                wrong.append(f"{path}: sap_tag_commit {block['sap_tag_commit']}")
            if "eval_seed" in block and block["eval_seed"] != seed:
                wrong.append(f"{path}: eval_seed {block['eval_seed']}")
    assert not wrong, wrong
