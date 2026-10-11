"""bvsignal.seed: evaluation-seed derivation, replicate keys, beacon round selection, run log and
frozen-input hashes (docs/11 §1.2, §1.3, §11.3, §15 rule 7). Fake shas and beacons only; no network."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from bvsignal import REPO_ROOT
from bvsignal import seed as s

FAKE_S = "0123456789abcdef0123456789abcdef01234567"
FAKE_B = "ce54ca4ea8ba575b19bb8fec6519cde80a28c44d2a3d6e3111c3bc8837d76e35"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}
DRAND = {"chain_hash": "ab" * 32, "genesis_time": 1_595_431_050, "period_seconds": 30,
         "info_url": "https://drand.invalid/info", "round_url": "https://drand.invalid/public/{round}"}
NIST = {"pulse_url": "https://nist.invalid/pulse/time/{timestamp_ms}", "period_seconds": 60}
CFG = {"delay_seconds": 600, "retry_seconds": 30, "nist_after_seconds": 1800, "empty_after_seconds": 3600,
       "drand": DRAND, "nist": NIST}


def git(repo: Path, *args: str, date: int | None = None) -> str:
    env = {**os.environ, **GIT_ENV}
    if date is not None:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"@{date} +0000"
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp: Path, *, tag: bool, beacon: dict | None = None, tagger_time: int = 1_790_000_000,
              annotated: bool = True) -> Path:
    repo = tmp / "repo"
    (repo / "monitoring" / "bvsignal").mkdir(parents=True)
    (repo / "monitoring" / "bvsignal" / "x.py").write_text("x = 1\n")
    (repo / "README.md").write_text("fake\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init", date=tagger_time - 100)
    if tag:
        if annotated:
            git(repo, "tag", "-a", s.TAG, "-m", "Site Signal SAP v1", date=tagger_time)
        else:
            git(repo, "tag", s.TAG)
    if beacon is not None:
        (repo / s.BEACON_REL).write_text(json.dumps(beacon))
    return repo


# ---- derivation ------------------------------------------------------------------------------------


def test_derivation_matches_the_sap_formula() -> None:
    expected = int(hashlib.sha256(("sap-v1:" + FAKE_S + ":" + FAKE_B).encode()).hexdigest()[:8], 16)
    assert s.derive_eval_seed(FAKE_S, FAKE_B) == expected == 3273873816
    assert s.derive_eval_seed(FAKE_S, "") == 1613808149  # B = "" when no beacon was reachable


@pytest.mark.parametrize("bad", ["0123", FAKE_S.upper(), FAKE_S + "0", "g" * 40])
def test_derivation_rejects_anything_but_40_hex(bad: str) -> None:
    with pytest.raises(ValueError):
        s.derive_eval_seed(bad, FAKE_B)


def test_eval_seed_from_tag_commit_and_beacon_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    beacon = {"source": "drand", "round": 123, "randomness": FAKE_B, "url": "u", "fetched_at": "t", "selection": {},
              "attempts": []}
    repo = make_repo(tmp_path, tag=True, beacon=beacon)
    commit = git(repo, "rev-parse", "sap-v1^{commit}")
    assert s.sap_tag_commit(repo) == commit
    assert s.eval_seed(repo) == s.derive_eval_seed(commit, FAKE_B)
    assert s.main(["--show"], repo=repo) == 0
    assert capsys.readouterr().out.strip() == f"sap_tag_commit={commit} beacon_round=123 eval_seed={s.derive_eval_seed(commit, FAKE_B)}"


def test_show_with_empty_beacon(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path, tag=True, beacon={"source": "none", "round": None, "randomness": "", "url": None, "fetched_at": "t",
                                                 "selection": {}, "attempts": [{"utc_time": "t", "source": "drand", "url": "u", "error": "e"}]})
    assert s.main(["--show"], repo=repo) == 0
    out = capsys.readouterr().out
    assert "beacon_round=none" in out and f"eval_seed={s.derive_eval_seed(git(repo, 'rev-parse', 'HEAD'), '')}" in out


@pytest.mark.parametrize(
    ("setup", "message"),
    [("no_git", "is not a git checkout"), ("no_tag", "tag sap-v1 does not exist yet"),
     ("no_beacon", "seed_beacon.json does not exist yet")],
)
def test_show_refuses_before_tag_or_beacon_or_outside_git(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                          setup: str, message: str) -> None:
    if setup == "no_git":
        repo = tmp_path / "plain"
        repo.mkdir()
    else:
        repo = make_repo(tmp_path, tag=setup != "no_tag")
    assert s.main(["--show"], repo=repo) == 2
    assert message in capsys.readouterr().err


def test_lightweight_tag_is_refused_for_the_beacon(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, tag=True, annotated=False)
    with pytest.raises(s.SeedError, match="annotated"):
        s.tag_tagger_time(repo)


def test_tagger_time_is_read_from_the_annotated_tag(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, tag=True, tagger_time=1_790_000_123)
    assert s.tag_tagger_time(repo) == 1_790_000_123


def test_real_checkout_has_no_eval_seed_before_the_tag() -> None:
    proc = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/sap-v1"], cwd=REPO_ROOT,
                          capture_output=True, check=False)
    if proc.returncode == 0:
        pytest.skip("sap-v1 exists in this checkout")
    with pytest.raises(s.SeedError, match="does not exist yet"):
        s.key(0, 0, 0, 0)


# ---- replicate keys --------------------------------------------------------------------------------


def test_key_is_seedsequence_with_spawn_key() -> None:
    k = s.key(3, 55, 1, 7, seed=20261011)
    ref = np.random.SeedSequence(20261011, spawn_key=(3, 55, 1, 7))
    assert k.entropy == 20261011 and k.spawn_key == (3, 55, 1, 7)
    assert np.array_equal(k.generate_state(8), ref.generate_state(8))


def test_key_determinism_and_independence() -> None:
    a = s.rng(3, 55, 1, 7, seed=20261011).random(5)
    b = s.rng(3, 55, 1, 7, seed=20261011).random(5)
    assert np.array_equal(a, b)
    others = [s.rng(*k, seed=20261011).random(5) for k in [(3, 55, 1, 8), (3, 55, 0, 7), (3, 54, 1, 7), (4, 55, 1, 7)]]
    others.append(s.rng(3, 55, 1, 7, seed=20261012).random(5))
    assert all(not np.array_equal(a, o) for o in others)


def test_dev_seed_from_params() -> None:
    assert s.dev_seed() == 20261011 == s.resolve_seed("dev")
    with pytest.raises(ValueError):
        s.key(-1, 0, 0, 0, seed=1)


# ---- beacon round selection ------------------------------------------------------------------------


def test_drand_round_selection_boundaries() -> None:
    g, p = 1_595_431_050, 30
    t = s.drand_round_time(6_542_245, g, p)
    assert s.drand_round_at_or_after(t, g, p) == 6_542_245  # a round exactly at the target counts
    assert s.drand_round_at_or_after(t + 1, g, p) == 6_542_246
    assert s.drand_round_at_or_after(t - 29, g, p) == 6_542_245
    assert s.drand_round_at_or_after(t - 30, g, p) == 6_542_244
    assert s.drand_round_at_or_after(g - 5, g, p) == 1
    for target in range(t - 61, t + 61):
        r = s.drand_round_at_or_after(target, g, p)
        assert s.drand_round_time(r, g, p) >= target > s.drand_round_time(r - 1, g, p)


def test_nist_pulse_selection_boundaries() -> None:
    assert s.nist_pulse_at_or_after(1_791_698_160) == 1_791_698_160
    assert s.nist_pulse_at_or_after(1_791_698_161) == 1_791_698_220
    assert s.nist_pulse_at_or_after(1_791_698_219) == 1_791_698_220


class FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, d: float) -> None:
        self.slept.append(d)
        self.t += d


def _drand_body(round_: int) -> dict:
    sig = hashlib.sha256(f"sig{round_}".encode()).hexdigest() * 3
    return {"round": round_, "randomness": hashlib.sha256(bytes.fromhex(sig)).hexdigest(), "signature": sig}


class FakeNet:
    """drand and NIST stand-ins on a fake clock; `drand_up`/`nist_up` may be a bool or a function of the time.
    `requests` records (time, url) of every request."""

    def __init__(self, clock: FakeClock, *, drand_up=True, nist_up=True, published_until: float = float("inf")) -> None:
        self.clock, self.drand_up, self.nist_up, self.published_until = clock, drand_up, nist_up, published_until
        self.requests: list[tuple[float, str]] = []

    @staticmethod
    def _is(up, t: float) -> bool:
        return up(t) if callable(up) else bool(up)

    def __call__(self, url: str) -> tuple[int, object]:
        now = self.clock.now()
        self.requests.append((now, url))
        if url.startswith("https://drand.invalid"):
            if not self._is(self.drand_up, now):
                raise s.BeaconUnreachable(f"{url}: connection refused")
            if url.endswith("/info"):
                return 200, {"hash": DRAND["chain_hash"], "genesis_time": DRAND["genesis_time"], "period": DRAND["period_seconds"]}
            r = int(url.rsplit("/", 1)[1])
            if s.drand_round_time(r, DRAND["genesis_time"], DRAND["period_seconds"]) > min(now, self.published_until):
                return 425, None
            return 200, _drand_body(r)
        if not self._is(self.nist_up, now):
            raise s.BeaconUnreachable(f"{url}: connection refused")
        ts_ms = int(url.rsplit("/", 1)[1])
        pulse_t = s.nist_pulse_at_or_after(ts_ms // 1000)
        if pulse_t > now:
            return 404, None
        stamp = s._utc(pulse_t).replace("Z", ".000Z")
        return 200, {"pulse": {"timeStamp": stamp, "pulseIndex": 42, "outputValue": "AB" * 64, "uri": "https://nist.invalid/chain/2/pulse/42"}}

    def times(self, prefix: str) -> list[float]:
        return [t for t, url in self.requests if url.startswith(prefix)]


TAGGER = 1_790_000_007


def _round_time() -> int:
    return s.beacon_schedule(TAGGER, CFG)["drand_round_time"]


def test_fetch_selects_first_drand_round_ten_minutes_after_the_tag() -> None:
    clock = FakeClock(TAGGER + 3600)
    b = s.select_beacon(TAGGER, CFG, wait=False, http=FakeNet(clock), now=clock.now, sleep=clock.sleep)
    expected = s.drand_round_at_or_after(TAGGER + 600, DRAND["genesis_time"], DRAND["period_seconds"])
    assert b["source"] == "drand" and b["round"] == expected
    assert b["url"] == f"https://drand.invalid/public/{expected}" and len(b["randomness"]) == 64
    assert s.drand_round_time(expected, DRAND["genesis_time"], DRAND["period_seconds"]) >= TAGGER + 600
    assert set(b) == set(s.BEACON_KEYS) and b["attempts"] == []
    t_round = _round_time()
    assert b["selection"] == {"tagger_time": s._utc(TAGGER), "target_time": s._utc(TAGGER + 600), "drand_round": expected,
                              "drand_round_time": s._utc(t_round), "nist_allowed_from": s._utc(t_round + 1800),
                              "empty_allowed_from": s._utc(t_round + 3600)}


def test_fetch_before_the_round_refuses_without_wait_and_sleeps_with_wait() -> None:
    clock = FakeClock(TAGGER + 60)
    with pytest.raises(s.BeaconNotYetPublished):
        s.select_beacon(TAGGER, CFG, wait=False, http=FakeNet(clock), now=clock.now, sleep=clock.sleep)
    b = s.select_beacon(TAGGER, CFG, wait=True, http=FakeNet(clock), now=clock.now, sleep=clock.sleep)
    assert b["source"] == "drand" and clock.t >= _round_time() and clock.slept and max(clock.slept) <= 60


def test_fetch_falls_back_to_nist_then_to_the_empty_string() -> None:
    """docs/11 §1.3: NIST only from round time + 30 min, the empty string only from round time + 60 min; a
    failure before a deadline raises (no beacon, so no file) instead of falling back."""
    t_round = _round_time()

    def attempt(at: float, **net: object) -> tuple[dict | None, FakeNet, list[dict]]:
        clock = FakeClock(at)
        http, log = FakeNet(clock, **net), []
        try:
            return s.select_beacon(TAGGER, CFG, wait=False, http=http, now=clock.now, sleep=clock.sleep, attempts=log), http, log
        except s.BeaconUnreachable:
            return None, http, log

    # drand down, NIST up: before round time + 30 min NIST is not even asked
    b, http, log = attempt(t_round + 1799, drand_up=False)
    assert b is None and http.times("https://nist.invalid") == []
    assert log == [{"utc_time": s._utc(t_round + 1799), "source": "drand", "url": DRAND["info_url"],
                    "error": f"{DRAND['info_url']}: connection refused"}]
    b, http, log = attempt(t_round + 1800, drand_up=False)
    assert b is not None and b["source"] == "nist-beacon-2.0" and b["round"] == 42 and b["randomness"] == "AB" * 64
    assert [a["source"] for a in b["attempts"]] == ["drand"] and b["attempts"] is log
    # both down: no empty string before round time + 60 min
    b, http, log = attempt(t_round + 3599, drand_up=False, nist_up=False)
    assert b is None and [a["source"] for a in log] == ["drand", "nist"]
    b, http, log = attempt(t_round + 3600, drand_up=False, nist_up=False)
    assert b is not None and b["randomness"] == "" and b["round"] is None and b["source"].startswith("none")
    assert [(a["source"], a["url"]) for a in b["attempts"]] == [
        ("drand", DRAND["info_url"]), ("nist", NIST["pulse_url"].format(timestamp_ms=(TAGGER + 600) * 1000))]
    # drand back before the deadline: drand wins even after the NIST deadline
    b, _, _ = attempt(t_round + 3000, drand_up=True, nist_up=True)
    assert b is not None and b["source"] == "drand"


def test_fetch_with_wait_retries_drand_every_minute_until_each_deadline() -> None:
    t_round = _round_time()
    # both down from the round time: drand at least once a minute, NIST only from + 30 min, empty from + 60 min
    clock = FakeClock(TAGGER)
    http = FakeNet(clock, drand_up=False, nist_up=False)
    b = s.select_beacon(TAGGER, CFG, wait=True, http=http, now=clock.now, sleep=clock.sleep)
    assert b["randomness"] == "" and t_round + 3600 <= clock.t < t_round + 3600 + 60
    drand_t = http.times(DRAND["info_url"])
    assert t_round <= drand_t[0] <= t_round + 1 and max(y - x for x, y in zip(drand_t, drand_t[1:], strict=False)) <= 60
    assert drand_t[-1] >= t_round + 3600
    nist_t = http.times("https://nist.invalid")
    assert nist_t and min(nist_t) >= t_round + 1800 and max(nist_t) >= t_round + 3600
    assert len(b["attempts"]) == len(drand_t) + len(nist_t)
    assert max(clock.slept) <= 60
    # drand down, NIST up: NIST at the first attempt at or after round time + 30 min
    clock = FakeClock(t_round)
    http = FakeNet(clock, drand_up=False)
    b = s.select_beacon(TAGGER, CFG, wait=True, http=http, now=clock.now, sleep=clock.sleep)
    assert b["source"] == "nist-beacon-2.0" and t_round + 1800 <= clock.t < t_round + 1800 + 60
    assert len(http.times("https://nist.invalid")) == 1 and all(a["source"] == "drand" for a in b["attempts"])
    # a transient drand outage (2 minutes) or a late round (HTTP 425) never switches to NIST
    clock = FakeClock(t_round)
    http = FakeNet(clock, drand_up=lambda t: t >= t_round + 120)
    b = s.select_beacon(TAGGER, CFG, wait=True, http=http, now=clock.now, sleep=clock.sleep)
    assert b["source"] == "drand" and len(b["attempts"]) >= 4 and http.times("https://nist.invalid") == []
    clock = FakeClock(t_round)
    http = FakeNet(clock, published_until=t_round - 1)  # drand stalls: the round is never published
    b = s.select_beacon(TAGGER, CFG, wait=True, http=http, now=clock.now, sleep=clock.sleep)
    assert b["source"] == "nist-beacon-2.0" and all("HTTP 425" in a["error"] for a in b["attempts"])


def test_fetch_refuses_a_different_drand_chain() -> None:
    clock = FakeClock(1_790_010_000)
    cfg = {**CFG, "drand": {**DRAND, "chain_hash": "cd" * 32}}
    with pytest.raises(s.SeedError, match="pre-registered chain"):
        s.select_beacon(1_790_000_000, cfg, wait=False, http=FakeNet(clock), now=clock.now, sleep=clock.sleep)


def test_fetch_refuses_a_retry_interval_above_a_minute() -> None:
    clock = FakeClock(1_790_010_000)
    with pytest.raises(s.SeedError, match="once a minute"):
        s.select_beacon(1_790_000_000, {**CFG, "retry_seconds": 61}, wait=False, http=FakeNet(clock), now=clock.now,
                        sleep=clock.sleep)


def test_fetch_beacon_cli_keeps_failed_attempts_and_writes_the_file_once(tmp_path: Path,
                                                                        capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path, tag=True, tagger_time=TAGGER)
    (repo / s.PARAMS_REL).write_text(yaml.safe_dump({"seeds": {"beacon": CFG}}))
    t_round = _round_time()
    clock = FakeClock(t_round + 60)
    io = {"now": clock.now, "sleep": clock.sleep}
    # drand down, no --wait: refused, nothing written, the failed attempt is kept
    assert s.main(["--fetch-beacon"], repo=repo, http=FakeNet(clock, drand_up=False), **io) == 2
    assert "allowed only from" in capsys.readouterr().err
    assert not (repo / s.BEACON_REL).exists()
    assert [a["source"] for a in s.load_pending_attempts(repo)] == ["drand"]
    # drand back: the beacon file carries the earlier failure, the pending file is gone
    clock.t += 90
    assert s.main(["--fetch-beacon"], repo=repo, http=FakeNet(clock), **io) == 0
    beacon = s.load_beacon(repo)
    assert beacon["source"] == "drand" and [a["utc_time"] for a in beacon["attempts"]] == [s._utc(t_round + 60)]
    assert beacon["selection"]["drand_round_time"] == s._utc(t_round)
    assert not (repo / s.BEACON_ATTEMPTS_REL).exists()
    assert list(json.loads((repo / s.BEACON_REL).read_text())) == list(s.BEACON_KEYS)
    # never replaced
    assert s.main(["--fetch-beacon"], repo=repo, http=FakeNet(clock), **io) == 2
    assert "already exists" in capsys.readouterr().err
    assert s.main(["--show"], repo=repo) == 0
    assert f"beacon_round={beacon['round']}" in capsys.readouterr().out


def test_beacon_file_is_written_once(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "monitoring").mkdir()
    b = {"source": "drand", "round": 1, "randomness": FAKE_B, "url": "u", "fetched_at": "t", "selection": {}, "attempts": []}
    s.write_beacon(b, repo)
    assert json.loads((repo / s.BEACON_REL).read_text()) == b
    with pytest.raises(s.SeedError, match="already exists"):
        s.write_beacon(b, repo)


def test_beacon_file_without_attempts_is_refused(tmp_path: Path) -> None:
    beacon = {"source": "drand", "round": 1, "randomness": FAKE_B, "url": "u", "fetched_at": "t", "selection": {}}
    repo = make_repo(tmp_path, tag=True, beacon=beacon)
    with pytest.raises(s.SeedError, match="attempts"):
        s.load_beacon(repo)


def test_params_preregister_the_drand_default_chain() -> None:
    cfg = s.beacon_config()
    assert cfg["delay_seconds"] == 600
    assert cfg["drand"]["round_url"] == "https://api.drand.sh/public/{round}"
    assert cfg["drand"]["info_url"] == "https://api.drand.sh/info"
    # docs/11 §1.3: retried at least once a minute; NIST from round time + 30 min; empty B from + 60 min
    assert 0 < cfg["retry_seconds"] <= 60
    assert cfg["nist_after_seconds"] == 30 * 60 and cfg["empty_after_seconds"] == 60 * 60


# ---- run log and code commit -----------------------------------------------------------------------


def test_log_run_appends_and_refuses_a_dirty_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, tag=False)
    out = repo / "monitoring" / "out" / "a.json"
    out.parent.mkdir(parents=True)
    out.write_text('{"x": 1}\n')
    log = repo / s.RUN_LOG_REL
    entry = s.log_run(["python", "-m", "bvsignal.run"], [out], repo=repo, log_path=log)
    assert set(entry) == {"utc_time", "code_commit", "git_dirty", "command", "output_sha256"}
    assert entry["git_dirty"] is False and entry["command"] == "python -m bvsignal.run"
    assert entry["code_commit"] == git(repo, "rev-parse", "HEAD")
    assert entry["output_sha256"] == {"monitoring/out/a.json": hashlib.sha256(out.read_bytes()).hexdigest()}
    assert json.loads(log.read_text().splitlines()[-1]) == entry
    # a committed output that a later run rewrites is the run's own output, not a dirty tree
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "outputs")
    out.write_text('{"x": 2}\n')
    assert s.git_dirty(repo) == ["monitoring/out/a.json"]
    assert s.log_run("again", [out], repo=repo, log_path=log)["output_sha256"]["monitoring/out/a.json"] == hashlib.sha256(b'{"x": 2}\n').hexdigest()
    (repo / "README.md").write_text("modified\n")
    assert s.git_dirty(repo, ["monitoring/out", s.RUN_LOG_REL]) == ["README.md"]
    git(repo, "checkout", "--", "README.md")
    (repo / "stray.txt").write_text("dirty\n")
    with pytest.raises(s.SeedError, match="dirty"):
        s.log_run("x", [out], repo=repo, log_path=log)
    assert len(log.read_text().splitlines()) == 2


def test_code_commit_is_the_last_commit_touching_an_analysis_input(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, tag=False)
    first = git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("changed\n")
    git(repo, "commit", "-qam", "docs only")
    assert s.code_commit(repo) == first
    (repo / "monitoring" / "params.yaml").write_text("a: 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "params")
    assert s.code_commit(repo) == git(repo, "rev-parse", "HEAD")


def test_the_real_run_log_is_not_created_before_the_tag() -> None:
    assert not (REPO_ROOT / s.RUN_LOG_REL).exists() or subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/tags/sap-v1"], cwd=REPO_ROOT, capture_output=True, check=False).returncode == 0


# ---- frozen inputs (docs/11 §11.3) -----------------------------------------------------------------


def _canon(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_frozen_hashes_follow_the_sap_definition() -> None:
    rf = json.loads((REPO_ROOT / "data/red_flags.json").read_text())["red_flags"]
    ct = json.loads((REPO_ROOT / "data/ctcae_rules.json").read_text())["rules"]
    got = s.frozen_inputs()
    assert got["red_flags_rule_level_sha256"] == _canon([{"level": e["level"], "rule": e["rule"]} for e in rf])
    assert got["ctcae_rules_sha256"] == _canon(ct)
    assert got["rules_py_sha256"] == hashlib.sha256((REPO_ROOT / s.RULES_PY_REL).read_bytes()).hexdigest()
    ep = REPO_ROOT / s.EPISODES_PY_REL
    assert got["episodes_py_sha256"] == (hashlib.sha256(ep.read_bytes()).hexdigest() if ep.exists() else "pending-B16")
    assert s.signal_rules_sha256() == hashlib.sha256((REPO_ROOT / "data/signal_rules.json").read_bytes()).hexdigest()


def _copy_inputs(dst: Path) -> Path:
    for rel in (s.PARAMS_REL, s.SAP_REL, s.SIGNAL_RULES_REL, s.RED_FLAGS_REL, s.CTCAE_RULES_REL, s.RULES_PY_REL):
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dst / rel)
    return dst


def test_red_flag_hash_ignores_sources_but_not_rules_or_levels(tmp_path: Path) -> None:
    repo = _copy_inputs(tmp_path)
    base = s.frozen_inputs(repo)["red_flags_rule_level_sha256"]
    doc = json.loads((repo / s.RED_FLAGS_REL).read_text())
    doc["red_flags"][0]["sources"] = ["a corrected citation"]
    doc["red_flags"][0]["label_en"] = "edited label"
    (repo / s.RED_FLAGS_REL).write_text(json.dumps(doc))
    assert s.frozen_inputs(repo)["red_flags_rule_level_sha256"] == base
    doc["red_flags"][0]["level"] = "emergency"
    (repo / s.RED_FLAGS_REL).write_text(json.dumps(doc))
    assert s.frozen_inputs(repo)["red_flags_rule_level_sha256"] != base


def test_write_frozen_keeps_comments_and_check_frozen_needs_a_section_17_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _copy_inputs(tmp_path)
    params = repo / s.PARAMS_REL
    params.write_text(re.sub(r'^signal_rules_sha256: "[0-9a-f]*"', 'signal_rules_sha256: "stale"', params.read_text(), flags=re.M))
    assert yaml.safe_load(params.read_text())["signal_rules_sha256"] == "stale"
    before = params.read_text().splitlines()
    assert s.main(["--write-frozen"], repo=repo) == 0
    after = params.read_text().splitlines()
    assert len(before) == len(after)

    def comments(lines: list[str]) -> list[str | None]:
        return [ln.split(" #", 1)[1] if " #" in ln else (ln if ln.lstrip().startswith("#") else None) for ln in lines]

    assert comments(before) == comments(after)
    loaded = yaml.safe_load(params.read_text())
    assert loaded["signal_rules_sha256"] == s.signal_rules_sha256(repo)
    assert loaded["frozen_inputs"] == s.frozen_inputs(repo)
    assert loaded["frozen_inputs"]["episodes_py_sha256"] == "pending-B16"  # the copy has no episodes.py
    assert s.main(["--check-frozen"], repo=repo) == 0
    # a changed grading input fails the check until a docs/11 §17 row cites the new hash
    (repo / s.RULES_PY_REL).write_text((repo / s.RULES_PY_REL).read_text() + "\n# changed\n")
    capsys.readouterr()
    assert s.main(["--check-frozen"], repo=repo) == 1
    assert "MISMATCH" in capsys.readouterr().out
    new = s.frozen_inputs(repo)["rules_py_sha256"]
    sap = repo / s.SAP_REL
    sap.write_text(sap.read_text().replace("| | | | | | | | | |", f"| D1 | now | abc | §11.3 | deviation | rules.py {new} | test | no | none |"))
    assert s.main(["--check-frozen"], repo=repo) == 0
    # B16 landing after the tag: the pending entry needs the same treatment
    (repo / s.EPISODES_PY_REL).write_text("# episodes\n")
    assert s.main(["--check-frozen"], repo=repo) == 1


def test_committed_params_carry_the_current_frozen_hashes() -> None:
    ok, report = s.check_frozen()
    assert ok, "\n".join(report) + "\nrun: uv run --project monitoring python -m bvsignal.seed --write-frozen"
