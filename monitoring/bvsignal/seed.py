"""Seeds, replicate keys, the run log and the frozen-input hashes (docs/11 §1.2, §1.3, §11.3, §15).

Evaluation seed (docs/11 §1.3)::

    int(sha256(("sap-v1:" + S + ":" + B).encode()).hexdigest()[:8], 16)

``S`` is the 40-hex output of ``git rev-parse sap-v1^{commit}``; ``B`` is the beacon randomness in
``monitoring/seed_beacon.json`` (the first drand mainnet round whose time is at least 10 minutes after
the sap-v1 tagger timestamp; NIST beacon v2 fallback; the empty string if neither is reachable). Every
replicate is keyed ``SeedSequence(seed, spawn_key=(stream, cell_index, role, i))``.

Command line, from the repository root::

    uv run --project monitoring python -m bvsignal.seed --show
    uv run --project monitoring python -m bvsignal.seed --fetch-beacon [--wait]
    uv run --project monitoring python -m bvsignal.seed --frozen-inputs | --write-frozen | --check-frozen

No LLM and no network access except ``--fetch-beacon`` (drand, then NIST).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from bvsignal import REPO_ROOT

TAG = "sap-v1"
PARAMS_REL = "monitoring/params.yaml"
BEACON_REL = "monitoring/seed_beacon.json"
RUN_LOG_REL = "validation/site_signal/run_log.jsonl"
SAP_REL = "docs/11-site-signal-sap.md"
SIGNAL_RULES_REL = "data/signal_rules.json"
RED_FLAGS_REL = "data/red_flags.json"
CTCAE_RULES_REL = "data/ctcae_rules.json"
RULES_PY_REL = "backend/app/services/rules.py"
EPISODES_PY_REL = "backend/app/services/episodes.py"
PENDING_EPISODES = "pending-B16"
BEACON_KEYS = ("source", "round", "randomness", "url", "fetched_at")
FROZEN_KEYS = ("red_flags_rule_level_sha256", "ctcae_rules_sha256", "rules_py_sha256", "episodes_py_sha256")

# docs/11 §15 rule 7: `code_commit` is the last commit that changed an analysis input.
ANALYSIS_INPUTS = (
    "monitoring/bvsignal",
    "monitoring/params.yaml",
    "monitoring/uv.lock",
    "data/signal_rules.json",
    "data/ctcae_rules.json",
    "data/red_flags.json",
    "backend/app/services/episodes.py",
    "backend/app/services/rules.py",
)

_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class SeedError(RuntimeError):
    """A seed, tag, beacon, run-log or frozen-input precondition is not met (message is user-facing)."""


class BeaconNotYetPublished(SeedError):
    """The selected round or pulse is in the future."""


class BeaconUnreachable(SeedError):
    """The beacon service could not be reached or returned an unusable answer."""


# ---- git -------------------------------------------------------------------------------------------


def _git(repo: Path, *args: str, strip: bool = True) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise SeedError("git is not installed: the evaluation seed needs `git rev-parse sap-v1^{commit}`") from e
    except NotADirectoryError as e:
        raise SeedError(f"{repo} is not a directory") from e
    if proc.returncode != 0:
        raise SeedError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.returncode}")
    return proc.stdout.strip() if strip else proc.stdout


def require_git_checkout(repo: Path = REPO_ROOT) -> None:
    """Raise unless `repo` is the top level of a git work tree (not, for example, a Docker copy)."""
    try:
        top = _git(repo, "rev-parse", "--show-toplevel")
    except SeedError as e:
        raise SeedError(
            f"{repo} is not a git checkout: the evaluation seed is derived from `git rev-parse {TAG}^{{commit}}` "
            "(docs/11 §1.3); run this from a clone of the repository with its tags"
        ) from e
    if Path(top).resolve() != Path(repo).resolve():
        raise SeedError(f"{repo} is not the top level of its git checkout ({top})")


def sap_tag_commit(repo: Path = REPO_ROOT) -> str:
    """40-hex commit of the annotated tag sap-v1 (`git rev-parse sap-v1^{commit}`)."""
    require_git_checkout(repo)
    try:
        sha = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{TAG}^{{commit}}")
    except SeedError as e:
        raise SeedError(
            f"tag {TAG} does not exist yet: there is no evaluation seed before the tag (docs/11 §1.2). "
            "Use the dev seed (params.yaml seeds.dev) until then; `git fetch --tags` if the tag was pushed"
        ) from e
    if not _HEX40.fullmatch(sha):
        raise SeedError(f"unexpected output of git rev-parse {TAG}^{{commit}}: {sha!r}")
    return sha


def tag_tagger_time(repo: Path = REPO_ROOT) -> int:
    """Tagger timestamp (Unix seconds) of the annotated tag sap-v1."""
    sap_tag_commit(repo)
    if _git(repo, "cat-file", "-t", f"refs/tags/{TAG}") != "tag":
        raise SeedError(f"{TAG} is a lightweight tag; docs/11 §1.2 requires an annotated tag (it has the tagger timestamp)")
    raw = _git(repo, "cat-file", "-p", f"refs/tags/{TAG}")
    m = re.search(r"^tagger .* (\d+) [+-]\d{4}$", raw, re.MULTILINE)
    if not m:
        raise SeedError(f"no tagger line in tag {TAG}")
    return int(m.group(1))


def git_dirty(repo: Path = REPO_ROOT, ignore: Iterable[str] = ()) -> list[str]:
    """Paths that make the working tree dirty (modified, staged or untracked), minus `ignore`.

    `ignore` holds repository-relative paths; a directory entry ignores everything below it."""
    ignored = [p.rstrip("/") for p in ignore]
    out = _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z", strip=False)  # " M path": keep the space
    paths: list[str] = []
    entries = out.split("\0")
    k = 0
    while k < len(entries):
        entry = entries[k]
        k += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            k += 1  # the next entry is the rename/copy source
        if any(path == ig or path.startswith(ig + "/") for ig in ignored):
            continue
        paths.append(path)
    return paths


def code_commit(repo: Path = REPO_ROOT) -> str:
    """Last commit that changed an analysis input (docs/11 §15 rule 7)."""
    sha = _git(repo, "log", "-1", "--format=%H", "--", *ANALYSIS_INPUTS)
    if not _HEX40.fullmatch(sha):
        raise SeedError("no commit touches the analysis inputs yet (docs/11 §15 rule 7)")
    return sha


def code_commit_time(repo: Path = REPO_ROOT) -> str:
    """Committer time (strict ISO 8601) of `code_commit()`; outputs use it as `generated_at`."""
    return _git(repo, "log", "-1", "--format=%cI", "--", *ANALYSIS_INPUTS)


# ---- params ----------------------------------------------------------------------------------------


def load_params(repo: Path = REPO_ROOT) -> dict[str, Any]:
    return yaml.safe_load((repo / PARAMS_REL).read_text(encoding="utf-8"))


def dev_seed(repo: Path = REPO_ROOT) -> int:
    return int(load_params(repo)["seeds"]["dev"])


def beacon_config(repo: Path = REPO_ROOT) -> dict[str, Any]:
    return load_params(repo)["seeds"]["beacon"]


# ---- evaluation seed and replicate keys ------------------------------------------------------------


def derive_eval_seed(sap_commit: str, beacon_randomness: str) -> int:
    """docs/11 §1.3: int(sha256(("sap-v1:" + S + ":" + B).encode()).hexdigest()[:8], 16)."""
    if not _HEX40.fullmatch(sap_commit):
        raise ValueError(f"S must be the 40-hex output of git rev-parse {TAG}^{{commit}}, got {sap_commit!r}")
    if not isinstance(beacon_randomness, str):
        raise ValueError("B must be a string (the beacon randomness hex, or the empty string)")
    digest = hashlib.sha256((TAG + ":" + sap_commit + ":" + beacon_randomness).encode()).hexdigest()
    return int(digest[:8], 16)


def load_beacon(repo: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo / BEACON_REL
    if not path.exists():
        raise SeedError(
            f"{BEACON_REL} does not exist yet: after the beacon round run "
            "`uv run --project monitoring python -m bvsignal.seed --fetch-beacon` (docs/11 §1.2 step 7)"
        )
    beacon = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in BEACON_KEYS if k not in beacon]
    if missing or not isinstance(beacon.get("randomness"), str):
        raise SeedError(f"{BEACON_REL} must hold {{{', '.join(BEACON_KEYS)}}} with a string randomness; missing {missing}")
    return beacon


def eval_seed(repo: Path = REPO_ROOT) -> int:
    """The evaluation seed: sap-v1 tag commit and the committed beacon value (docs/11 §1.3)."""
    return derive_eval_seed(sap_tag_commit(repo), load_beacon(repo)["randomness"])


def resolve_seed(label: str, repo: Path = REPO_ROOT) -> int:
    """`dev` -> params.yaml seeds.dev; `eval` -> the derived evaluation seed."""
    if label == "dev":
        return dev_seed(repo)
    if label == "eval":
        return eval_seed(repo)
    raise SeedError(f"unknown seed label {label!r} (use dev or eval)")


def key(stream: int, cell_index: int, role: int, i: int, *, seed: int | None = None,
        repo: Path = REPO_ROOT) -> np.random.SeedSequence:
    """Replicate key `SeedSequence(seed, spawn_key=(stream, cell_index, role, i))` (docs/11 §1.3).

    `seed` defaults to the evaluation seed; pass the dev seed explicitly before the tag."""
    for name, v in (("stream", stream), ("cell_index", cell_index), ("role", role), ("i", i)):
        if int(v) != v or v < 0:
            raise ValueError(f"{name} must be a non-negative integer, got {v!r}")
    s = eval_seed(repo) if seed is None else int(seed)
    return np.random.SeedSequence(s, spawn_key=(int(stream), int(cell_index), int(role), int(i)))


def rng(stream: int, cell_index: int, role: int, i: int, *, seed: int | None = None,
        repo: Path = REPO_ROOT) -> np.random.Generator:
    """`numpy.random.Generator` (PCG64) for one replicate key."""
    return np.random.Generator(np.random.PCG64(key(stream, cell_index, role, i, seed=seed, repo=repo)))


# ---- beacon round selection and fetch --------------------------------------------------------------


def drand_round_at_or_after(target: int, genesis_time: int, period: int) -> int:
    """First drand round whose time (genesis + (round - 1) * period) is >= target (Unix seconds)."""
    if target <= genesis_time:
        return 1
    return -(-(target - genesis_time) // period) + 1


def drand_round_time(round_: int, genesis_time: int, period: int) -> int:
    return genesis_time + (round_ - 1) * period


def nist_pulse_at_or_after(target: int, period: int = 60) -> int:
    """Time (Unix seconds) of the first NIST pulse >= target; pulses fall on whole periods."""
    return -(-target // period) * period


def _utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc_iso() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


HttpGet = Callable[[str], tuple[int, Any]]


def http_get_json(url: str, timeout: float = 15.0) -> tuple[int, Any]:
    """GET a JSON document: (status, body or None). Network failures raise BeaconUnreachable."""
    req = urllib.request.Request(url, headers={"User-Agent": "between-visits-bvsignal/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise BeaconUnreachable(f"{url}: {e}") from e


def _wait_until(when: float, *, wait: bool, what: str, now: Callable[[], float], sleep: Callable[[float], None]) -> None:
    remaining = when - now()
    if remaining <= 0:
        return
    if not wait:
        raise BeaconNotYetPublished(
            f"{what} is published at {_utc(when)} ({int(remaining)} s from now); rerun then, or pass --wait"
        )
    while (remaining := when - now()) > 0:
        print(f"waiting {int(remaining) + 1} s for {what} ({_utc(when)})", file=sys.stderr, flush=True)
        sleep(min(remaining + 1, 60))


def fetch_drand(target: int, cfg: dict[str, Any], *, wait: bool, http: HttpGet = http_get_json,
                now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                retries: int = 10) -> dict[str, Any]:
    """The first drand mainnet (default chain) round at or after `target`, verified."""
    status, info = http(cfg["info_url"])
    if status != 200 or not isinstance(info, dict):
        raise BeaconUnreachable(f"{cfg['info_url']} returned HTTP {status}")
    expected = (cfg["chain_hash"], int(cfg["genesis_time"]), int(cfg["period_seconds"]))
    got = (info.get("hash"), info.get("genesis_time"), info.get("period"))
    if got != expected:
        raise SeedError(f"drand chain info {got} differs from the pre-registered chain {expected} (params.yaml seeds.beacon.drand)")
    genesis, period = expected[1], expected[2]
    round_ = drand_round_at_or_after(target, genesis, period)
    _wait_until(drand_round_time(round_, genesis, period), wait=wait, what=f"drand round {round_}", now=now, sleep=sleep)
    url = cfg["round_url"].format(round=round_)
    for attempt in range(retries):
        status, body = http(url)
        if status == 200 and isinstance(body, dict):
            randomness, signature = str(body.get("randomness", "")), str(body.get("signature", ""))
            if body.get("round") != round_ or not _HEX64.fullmatch(randomness):
                raise SeedError(f"{url}: unexpected round or randomness in {body}")
            try:
                derived = hashlib.sha256(bytes.fromhex(signature)).hexdigest()
            except ValueError as e:
                raise SeedError(f"{url}: signature is not hex") from e
            if derived != randomness:
                raise SeedError(f"{url}: randomness is not sha256(signature)")
            return {"source": "drand", "round": round_, "randomness": randomness, "url": url, "fetched_at": now_utc_iso()}
        if status in (404, 425) and wait and attempt + 1 < retries:
            sleep(period)
            continue
        if status in (404, 425):
            raise BeaconNotYetPublished(f"{url} returned HTTP {status} (round not published yet); rerun later or pass --wait")
        raise BeaconUnreachable(f"{url} returned HTTP {status}")
    raise BeaconUnreachable(f"{url}: no answer after {retries} attempts")


def fetch_nist(target: int, cfg: dict[str, Any], *, wait: bool, http: HttpGet = http_get_json,
               now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
               retries: int = 10) -> dict[str, Any]:
    """The first NIST Randomness Beacon 2.0 pulse at or after `target` (fallback, docs/11 §1.3)."""
    period = int(cfg["period_seconds"])
    _wait_until(nist_pulse_at_or_after(target, period), wait=wait, what="the NIST beacon pulse", now=now, sleep=sleep)
    url = cfg["pulse_url"].format(timestamp_ms=target * 1000)
    for attempt in range(retries):
        status, body = http(url)
        if status == 200 and isinstance(body, dict) and isinstance(body.get("pulse"), dict):
            pulse = body["pulse"]
            ts = dt.datetime.fromisoformat(str(pulse["timeStamp"]).replace("Z", "+00:00")).timestamp()
            if not (target <= ts < target + period):
                raise SeedError(f"{url}: pulse at {pulse['timeStamp']} is not the first pulse at or after {_utc(target)}")
            value = str(pulse.get("outputValue", ""))
            if not re.fullmatch(r"[0-9A-Fa-f]{128}", value):
                raise SeedError(f"{url}: unexpected outputValue")
            return {"source": "nist-beacon-2.0", "round": int(pulse["pulseIndex"]), "randomness": value,
                    "url": str(pulse.get("uri") or url), "fetched_at": now_utc_iso()}
        if status == 404 and wait and attempt + 1 < retries:
            sleep(period)
            continue
        if status == 404:
            raise BeaconNotYetPublished(f"{url} returned HTTP 404 (pulse not published yet)")
        raise BeaconUnreachable(f"{url} returned HTTP {status}")
    raise BeaconUnreachable(f"{url}: no answer after {retries} attempts")


def select_beacon(tagger_time: int, cfg: dict[str, Any], *, wait: bool, http: HttpGet = http_get_json,
                  now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                  attempts: int = 3) -> dict[str, Any]:
    """drand first, NIST if drand is unreachable, the empty string if neither is (docs/11 §1.3)."""
    target = int(tagger_time) + int(cfg["delay_seconds"])
    errors: list[str] = []
    for name, fetch in (("drand", fetch_drand), ("nist", fetch_nist)):
        for attempt in range(attempts):
            try:
                return fetch(target, cfg[name], wait=wait, http=http, now=now, sleep=sleep)
            except BeaconUnreachable as e:
                errors.append(f"{name} attempt {attempt + 1}: {e}")
                if attempt + 1 < attempts:
                    sleep(5)
    print("WARNING: neither drand nor the NIST beacon was reachable; B is the empty string and a docs/11 §17 "
          "entry must say so (docs/11 §1.3):\n  " + "\n  ".join(errors), file=sys.stderr)
    return {"source": "none (drand and NIST unreachable)", "round": None, "randomness": "", "url": None,
            "fetched_at": now_utc_iso()}


def write_beacon(beacon: dict[str, Any], repo: Path = REPO_ROOT) -> Path:
    path = repo / BEACON_REL
    if path.exists():
        raise SeedError(f"{BEACON_REL} already exists; the beacon is fetched once and never replaced (docs/11 §1.4)")
    path.write_text(json.dumps({k: beacon[k] for k in BEACON_KEYS}, indent=2) + "\n", encoding="utf-8")
    return path


# ---- run log ---------------------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path, repo: Path) -> str:
    p = Path(path)
    p = p if p.is_absolute() else repo / p
    return p.resolve().relative_to(Path(repo).resolve()).as_posix()


def assert_committed_tree(repo: Path = REPO_ROOT, ignore: Iterable[str] = ()) -> None:
    """Evaluation-seed runs refuse a dirty working tree (docs/11 §1.2)."""
    dirty = git_dirty(repo, ignore)
    if dirty:
        shown = ", ".join(dirty[:10]) + (" ..." if len(dirty) > 10 else "")
        raise SeedError(f"refusing an evaluation-seed run on a dirty working tree ({len(dirty)} paths: {shown}); commit or discard the changes first")


def log_run(command: str | list[str], outputs: Iterable[str | Path], *, repo: Path = REPO_ROOT,
            log_path: Path | None = None) -> dict[str, Any]:
    """Append `{utc_time, code_commit, git_dirty, command, output_sha256}` to the run log (docs/11 §1.2).

    Refuses (SeedError) when the tree is dirty apart from the run's own outputs and the log itself."""
    log_path = Path(log_path) if log_path is not None else repo / RUN_LOG_REL
    rel_outputs = [_rel(Path(o), repo) for o in outputs]
    assert_committed_tree(repo, [*rel_outputs, _rel(log_path, repo)])
    entry = {
        "utc_time": now_utc_iso(),
        "code_commit": code_commit(repo),
        "git_dirty": False,
        "command": command if isinstance(command, str) else shlex.join(command),
        "output_sha256": {rel: file_sha256(repo / rel) for rel in sorted(rel_outputs)},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


# ---- frozen inputs (docs/11 §11.3) -----------------------------------------------------------------


def canonical_json_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def signal_rules_sha256(repo: Path = REPO_ROOT) -> str:
    return file_sha256(repo / SIGNAL_RULES_REL)


def frozen_inputs(repo: Path = REPO_ROOT) -> dict[str, str]:
    """The four `frozen_inputs` hashes of params.yaml, recomputed from the working tree."""
    red_flags = json.loads((repo / RED_FLAGS_REL).read_text(encoding="utf-8"))["red_flags"]
    ctcae = json.loads((repo / CTCAE_RULES_REL).read_text(encoding="utf-8"))["rules"]
    episodes = repo / EPISODES_PY_REL
    return {
        "red_flags_rule_level_sha256": canonical_json_sha256([{"level": e["level"], "rule": e.get("rule")} for e in red_flags]),
        "ctcae_rules_sha256": canonical_json_sha256(ctcae),
        "rules_py_sha256": file_sha256(repo / RULES_PY_REL),
        "episodes_py_sha256": file_sha256(episodes) if episodes.exists() else PENDING_EPISODES,
    }


def _replace_value(lines: list[str], key: str, value: str, *, indent: str, block: tuple[int, int]) -> str:
    pat = re.compile(rf"^{re.escape(indent)}{re.escape(key)}:(?P<sp>[ \t]*)(?P<val>[^\s#]*)(?P<tail>[ \t]*(#.*)?)$")
    hits = [k for k in range(*block) if pat.match(lines[k].rstrip("\n"))]
    if len(hits) != 1:
        raise SeedError(f"{PARAMS_REL}: expected exactly one `{indent}{key}:` line, found {len(hits)}")
    k = hits[0]
    m = pat.match(lines[k].rstrip("\n"))
    assert m is not None
    old = m.group("val").strip("\"'")
    tail = m.group("tail")
    if tail and not tail[0].isspace():
        tail = " " + tail
    lines[k] = f'{indent}{key}: "{value}"{tail}\n'
    return old


def write_frozen(repo: Path = REPO_ROOT) -> dict[str, tuple[str, str]]:
    """Rewrite `signal_rules_sha256` and `frozen_inputs` in params.yaml in place, keeping comments."""
    path = repo / PARAMS_REL
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    starts = [k for k, ln in enumerate(lines) if ln.startswith("frozen_inputs:")]
    if len(starts) != 1:
        raise SeedError(f"{PARAMS_REL}: expected one top-level `frozen_inputs:` block")
    start = starts[0] + 1
    end = next((k for k in range(start, len(lines)) if lines[k][:1] not in (" ", "\t", "#", "\n", "")), len(lines))
    changes: dict[str, tuple[str, str]] = {}
    new_sig = signal_rules_sha256(repo)
    changes["signal_rules_sha256"] = (_replace_value(lines, "signal_rules_sha256", new_sig, indent="", block=(0, len(lines))), new_sig)
    for k, v in frozen_inputs(repo).items():
        changes[k] = (_replace_value(lines, k, v, indent="  ", block=(start, end)), v)
    text = "".join(lines)
    parsed = yaml.safe_load(text)
    if parsed["signal_rules_sha256"] != new_sig or any(str(parsed["frozen_inputs"][k]) != v for k, (_, v) in changes.items() if k in FROZEN_KEYS):
        raise SeedError(f"{PARAMS_REL}: rewrite did not round-trip; file left unchanged")
    path.write_text(text, encoding="utf-8")
    return changes


def sap_deviations_text(repo: Path = REPO_ROOT) -> str:
    """The text of docs/11 §17 (Deviations), where a changed frozen hash must be cited."""
    text = (repo / SAP_REL).read_text(encoding="utf-8")
    m = re.search(r"^## 17\..*?(?=^## \d+\.|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(0) if m else ""


def check_frozen(repo: Path = REPO_ROOT) -> tuple[bool, list[str]]:
    """Compare params.yaml with the recomputed hashes; a mismatch passes only if docs/11 §17 cites the new hash."""
    params = load_params(repo)
    recorded = {"signal_rules_sha256": str(params.get("signal_rules_sha256")),
                **{k: str((params.get("frozen_inputs") or {}).get(k)) for k in FROZEN_KEYS}}
    current = {"signal_rules_sha256": signal_rules_sha256(repo), **frozen_inputs(repo)}
    deviations = sap_deviations_text(repo)
    ok, report = True, []
    for k in recorded:
        if recorded[k] == current[k]:
            report.append(f"ok        {k} = {current[k]}")
        elif current[k] != PENDING_EPISODES and current[k] in deviations:
            report.append(f"deviation {k} = {current[k]} (params.yaml {recorded[k]}; cited in docs/11 §17)")
        else:
            ok = False
            report.append(f"MISMATCH  {k}: params.yaml {recorded[k]} != current {current[k]} (no docs/11 §17 row cites it)")
    return ok, report


# ---- command line ----------------------------------------------------------------------------------


def _show(repo: Path) -> int:
    commit = sap_tag_commit(repo)
    beacon = load_beacon(repo)
    seed = derive_eval_seed(commit, beacon["randomness"])
    round_ = "none" if beacon["round"] is None else beacon["round"]
    print(f"sap_tag_commit={commit} beacon_round={round_} eval_seed={seed}")
    return 0


def _fetch(repo: Path, wait: bool) -> int:
    if (repo / BEACON_REL).exists():
        raise SeedError(f"{BEACON_REL} already exists; the beacon is fetched once and never replaced (docs/11 §1.4)")
    tagger = tag_tagger_time(repo)
    beacon = select_beacon(tagger, beacon_config(repo), wait=wait)
    path = write_beacon(beacon, repo)
    print(f"wrote {path.relative_to(repo)}: source={beacon['source']} round={beacon['round']} "
          f"(sap-v1 tagger time {_utc(tagger)}); commit it with a docs/11 §17 clarification")
    return 0


def main(argv: list[str] | None = None, *, repo: Path | None = None) -> int:
    repo = Path(repo) if repo is not None else REPO_ROOT
    ap = argparse.ArgumentParser(prog="python -m bvsignal.seed", description=__doc__.split("\n\n")[0])
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument("--show", action="store_true", help="print the sap-v1 commit, beacon round and evaluation seed")
    act.add_argument("--fetch-beacon", action="store_true", help="fetch the beacon round selected by docs/11 §1.3 and write monitoring/seed_beacon.json")
    act.add_argument("--frozen-inputs", action="store_true", help="print signal_rules_sha256 and the frozen_inputs hashes")
    act.add_argument("--write-frozen", action="store_true", help="write those hashes into monitoring/params.yaml (comments kept)")
    act.add_argument("--check-frozen", action="store_true", help="exit 1 if params.yaml differs and no docs/11 §17 row cites the new hash")
    ap.add_argument("--wait", action="store_true", help="with --fetch-beacon: sleep until the round is published")
    args = ap.parse_args(argv)
    if args.wait and not args.fetch_beacon:
        ap.error("--wait only applies to --fetch-beacon")
    try:
        if args.show:
            return _show(repo)
        if args.fetch_beacon:
            return _fetch(repo, args.wait)
        if args.frozen_inputs:
            print(f"signal_rules_sha256: {signal_rules_sha256(repo)}")
            print("frozen_inputs:")
            for k, v in frozen_inputs(repo).items():
                print(f"  {k}: {v}")
            return 0
        if args.write_frozen:
            for k, (old, new) in write_frozen(repo).items():
                print(f"{'unchanged' if old == new else 'updated'}  {k}: {new}")
            return 0
        ok, report = check_frozen(repo)
        print("\n".join(report))
        print("frozen inputs: OK" if ok else "frozen inputs: MISMATCH (add a docs/11 §17 row citing the new hash, or restore the input)")
        return 0 if ok else 1
    except SeedError as e:
        print(f"bvsignal.seed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
