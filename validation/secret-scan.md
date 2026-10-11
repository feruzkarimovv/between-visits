# Secret scan record (WS0 R1)

Full-history scan of the repository for secrets and real phone numbers before any packaging step. The repository is
private; changing its visibility is a human decision, made only after a fresh scan of the final history.

## Result

| Field | Value |
|---|---|
| Date and time | 2026-10-11 01:51 EDT (05:51 UTC) |
| Secret scanner | gitleaks **8.30.1** (`gitleaks version`). Local run: the Homebrew build of 8.30.1 on macOS arm64. CI job `gitleaks`: the official release binary `gitleaks_8.30.1_linux_x64.tar.gz` (sha256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`), checked against the release's `gitleaks_8.30.1_checksums.txt` before use. |
| gitleaks config | `.gitleaks.toml`: the default rule set (`[extend] useDefault = true`) plus an allowlist for the documented placeholders only (`+1XXXXXXXXXX`, `+1555…` numbers, `change-me…` strings, `bv-change-me…` topics), each matched against the whole detected secret. |
| Number scanner | `validation/scan_numbers.py` (standard library only): every added line of `git log -p --all`, plus commit messages and changed paths, against the US number pattern in `docs/workstreams/WS0-readiness.md` R1; 555-exchange matches ignored. |
| Command | `make secret-scan` = `gitleaks git --redact --log-opts="--all" -v . && python3 validation/scan_numbers.py` |
| Refs scanned | `--all` in the build machine's clone after `git fetch origin`: every remote-tracking branch on `origin` (`main`, `site-signal-build`, `claude/vibrant-fermi-6vwzie`) and every local branch, including the in-progress agent worktree branches. |
| Commit range | 31 commits (`git rev-list --all --count`). First: `07f27736b714f3f6f885d67f0da669e63e3755dc` (2026-10-10 17:31 EDT, root commit, the only one). Last: the R1 commit on top of `origin/site-signal-build` at `ffe15799b1ecaab276dd6670de1dfe284bd463a4` (2026-10-11 01:49 EDT); the committed R1 version differs from the scanned one only by the scan details in this file. |
| gitleaks findings | **0**: `31 commits scanned.` `no leaks found` |
| Number findings | **0**: `numbers: 0 hits (31 commits, 59041 added lines; 12 fictional 555 matches ignored; 151 allowlisted)` |
| Self-test | PASS (below) |

The 151 allowlisted matches are 150 distinct digit runs, each reviewed in context before its sha256 went into
`validation/scan_numbers_allow.txt`:

| File | Distinct runs | What they are |
|---|---|---|
| `backend/uv.lock` | 149 | Digit runs inside 64-character package sha256 hashes and 60-character hex path segments of package URLs. |
| `docs/03-api-contracts.md` | 1 | The example `eval_seed` value in a JSON response example (in 2 commits). Not a phone number. |

**Update (S1 post-tag housekeeping, 2026-10-11):** lockfiles are no longer number-checked (next section), so the 149
`backend/uv.lock` entries above and the 1 `monitoring/uv.lock` entry added in S1 were removed from the allowlist. It
now holds 3 entries, none for a lockfile: the `docs/03` example above, the expected derived seed in
`monitoring/tests/test_seed.py`, and a digit run inside the `symptom_items_logic_sha256` digest in
`monitoring/params.yaml` and `monitoring/planning/planning_grid.json`. Re-run record: § Re-run after the lockfile change.

## Lines that are not checked

The number scanner checks every added line, every commit message and every changed path, except two kinds of added
lines. Both hold only hashes:

| Lines | Matched by | Reason |
|---|---|---|
| The digest lines of `validation/scan_numbers_allow.txt` | A line that is exactly one 64-hex sha256. Its `#` comment is still checked. | A hex digest has digit runs of its own. |
| Every added line of a lockfile | The file name, in any directory: `uv.lock`, `package-lock.json`, or any name ending in `.lock` (today `backend/uv.lock`, `monitoring/uv.lock` and `frontend/package-lock.json`). A name that only contains "lock", such as `agent/agents.lock.json`, is still checked. | uv and npm write lockfiles from registry metadata: package names, versions, URLs and sha256/sha512 hashes, never hand-written text. Their hash digit runs are NANP-shaped by chance (R1 allowlisted 149 of them in `backend/uv.lock`, one by one), and every re-lock adds new ones, so a per-hash allowlist broke on each dependency change without protecting anything. |

A lockfile's path is still checked (a number in a file name is found), and gitleaks still scans lockfile content for
secrets. The summary line reports the skipped lines as `N lockfile lines not checked`, and the self-test proves the
skip is by path and no wider.

## Self-test

`python3 validation/scan_numbers.py --self-test` clones the repository into a scratch directory under `$TMPDIR`
(outside the repository) and commits 7 generated NANP-shaped non-555 numbers and 1 fictional 555 number: 3 numbers in
3 formats and the 555 number in a text file, 1 in an allowlist comment, 1 in `selftest_deps/agents.lock.json` (not a
lockfile), and 1 in each of the lockfiles `selftest_deps/uv.lock` and `selftest_deps/web/package-lock.json`. It scans
the clone, expects exactly the 5 numbers outside lockfiles as hits and neither lockfile number, and deletes the clone.
The numbers are generated at run time and never written to this repository or printed. Result on 2026-10-11 07:27
EDT:

```
self-test: scan exit=1
self-test: exit 1 yes; last 4 digits of each planted number outside lockfiles shown yes; full numbers absent from output yes; exactly 5 hits (555 placeholder ignored, allowlist comment and selftest_deps/agents.lock.json checked) yes; lockfile numbers not reported yes; one allowlist sha256 suppresses one hit yes
self-test: PASS (scratch clone removed)
```

The R1 version of the self-test (3 numbers in a file, 1 in an allowlist comment, exactly 4 hits) passed on
2026-10-11 01:51 EDT.

Each hit line of the scan inside the clone reads `hit: commit <12 hex>  file <path>  last4 <4 digits>`; the full
number never appears. CI runs the same self-test after `make secret-scan` in the `gitleaks` job.

## How to re-run

```bash
make secret-scan; echo "exit=$?"                     # gitleaks prints "no leaks found", then "numbers: 0 hits ...", exit=0
python3 validation/scan_numbers.py --self-test       # PASS
```

`make secret-scan` refuses to run when `gitleaks version` is not the pinned 8.30.1 (`GITLEAKS_VERSION` in the
Makefile; the CI job pins the same version). To install the pinned release binary:

```bash
cd "$(mktemp -d)"
v=8.30.1; f=gitleaks_${v}_darwin_arm64.tar.gz        # Linux: gitleaks_${v}_linux_x64.tar.gz
curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v$v/$f"
curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v$v/gitleaks_${v}_checksums.txt"
grep " $f\$" "gitleaks_${v}_checksums.txt" | shasum -a 256 -c -   # Linux: sha256sum -c -
tar -xzf "$f" gitleaks && sudo install -m 0755 gitleaks /usr/local/bin/gitleaks && gitleaks version
```

Before making the repository public (a later human decision), re-run both commands on the final history, on a fresh
clone with every branch fetched, and add the result here.

## Re-run after the lockfile change

| Field | Value |
|---|---|
| Date and time | 2026-10-11 07:27 EDT (11:27 UTC) |
| Scanned | `--all` in the implementing session's agent worktree: `origin/site-signal-build` at `0aca721` plus the local and remote-tracking branches present there, with this change's `scan_numbers.py` and allowlist in the working tree (the commit that adds them differs from the scanned history only by this change). |
| gitleaks 8.30.1 | **0**: `102 commits scanned.` `no leaks found` |
| Number findings | **0**: `numbers: 0 hits (102 commits, 74025 added lines; 9809 lockfile lines not checked; 15 fictional 555 matches ignored; 5 allowlisted)` |
| Self-test | PASS (above) |

## When the scan finds something

- **gitleaks finding or a number hit that is real:** stop. Tell the team lead, rotate the credential first, then
  decide on history rewriting with the team. Nobody rewrites history alone, and nothing real goes into an allowlist.
- **Number hit that is a false positive** (for example a digit run inside a hash or a seed in a data file or test):
  look at each hit's context, then `python3 validation/scan_numbers.py --suggest-allow` prints one sha256 line per
  hit, labeled with its file, for `validation/scan_numbers_allow.txt`. Lockfiles never need an entry (§ Lines that are
  not checked), so a re-lock adds none; the digest lines of the allowlist itself are not scanned, its comments are.
