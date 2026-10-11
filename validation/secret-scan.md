# Secret scan record (WS0 R1)

Full-history scan of the repository for secrets and real phone numbers before any packaging step. The repository is
private; changing its visibility is a human decision, made only after a fresh scan of the final history.

## Result

| Field | Value |
|---|---|
| Date and time | 2026-10-11 01:51 EDT (05:51 UTC) |
| Secret scanner | gitleaks **8.30.1** (`gitleaks version`). Local run: the Homebrew build of 8.30.1 on macOS arm64. CI job `gitleaks`: the official release binary `gitleaks_8.30.1_linux_x64.tar.gz` (sha256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`), checked against the release's `gitleaks_8.30.1_checksums.txt` before use. |
| gitleaks config | `.gitleaks.toml`: the default rule set (`[extend] useDefault = true`) plus an allowlist for the documented placeholders only (`+1XXXXXXXXXX`, `+1555…` numbers, `change-me…` strings, `bv-change-me…` topics), each matched against the whole detected secret. Two more allowlists were added after the final review, for 3 false positives: § Re-run after the final review. |
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

## Re-run after the final review

From f040644 on, `make secret-scan` and the CI job `gitleaks` failed with `leaks found: 3`, all from the default
`generic-api-key` rule and all false positives, so a real leak would have been lost in a red job. The hits are in
history, so editing the files would not remove them; `.gitleaks.toml` gained two allowlists instead, each matched
against the whole detected secret:

| Hit (commit, file, line) | What it is | Allowlist |
|---|---|---|
| 0c9dd43, `validation/site_signal/run_log.jsonl`, line 2 | sha256 digest of a committed output file (`output_sha256`) in the evaluation run log | "sha256 output digests in the evaluation run log": `condition = "AND"`, the path `^validation/site_signal/run_log\.jsonl$` and the secret `^[0-9a-f]{64}$` must both match, so a 64-hex value in any other file is still reported |
| d70cb6e, `validation/site_signal/run_log.jsonl`, line 3 | the same, for the determinism re-run | the same |
| 78de1f2, `PROGRESS.md`, line 62 | the site-query ID `sq_2YXWU7W3TZ` of a synthetic demo row, after the text "API after the run:" | "app IDs from app/ids.py": the secret `^(sq\|sr\|ci\|pat\|ans\|fnd\|esc\|dr\|sae\|aud)_[A-Z0-9]{10}$`, the record-ID shape of `backend/app/ids.py` (prefix plus 10 base32 characters), which is a random row identifier, not a credential |

A scratch-directory check (`gitleaks dir` with this config) still reports a 64-hex digest after the same
`answer_key.json` key in a file outside the run log.

| Field | Value |
|---|---|
| Date and time | 2026-10-11 10:47 EDT (14:47 UTC) |
| Scanned | `--all` in the implementing session's agent worktree: `origin/site-signal-build` at `5767cd0` plus the local and remote-tracking branches present there, with this change's `.gitleaks.toml` in the working tree (the commit that adds it differs from the scanned history only by this change). |
| gitleaks 8.30.1 | **0**: `159 commits scanned.` `no leaks found` (before this change: `leaks found: 3`) |
| Number findings | **0**: `numbers: 0 hits (159 commits, 213081 added lines; 9887 lockfile lines not checked; 15 fictional 555 matches ignored; 5 allowlisted)` |

## When the scan finds something

- **gitleaks finding or a number hit that is real:** stop. Tell the team lead, rotate the credential first, then
  decide on history rewriting with the team. Nobody rewrites history alone, and nothing real goes into an allowlist.
- **Number hit that is a false positive** (for example a digit run inside a hash or a seed in a data file or test):
  look at each hit's context, then `python3 validation/scan_numbers.py --suggest-allow` prints one sha256 line per
  hit, labeled with its file, for `validation/scan_numbers_allow.txt`. Lockfiles never need an entry (§ Lines that are
  not checked), so a re-lock adds none; the digest lines of the allowlist itself are not scanned, its comments are.

## Appendix: final fresh clone from GitHub (WS0 R12)

The implementing session ran this on the build machine, not on a second machine. It used a fresh clone of the pushed
branch, outside the repository. The key output line of each step is quoted verbatim.

| Field | Value |
|---|---|
| Date and time | 2026-10-11 10:34 to 10:46 EDT (14:34 to 14:46 UTC) |
| Clone | `gh repo clone feruzkarimovv/between-visits $TMPDIR/r12 -- --branch site-signal-build` (authenticated; the repository is private) |
| Commit | `5767cd06ab51b8a91e2be008f20832fd4ee8353b` (`origin/site-signal-build`, "Build: progress F19") |
| Tools | uv with CPython 3.12.12 (from `.python-version`), Node 24.18.0 (the README asks for Node 22), gitleaks 8.30.1, Playwright 1.63.0 (chromium) |
| Result | **Every step passes except `make secret-scan`.** gitleaks reports 3 findings, and all 3 are false positives (§ gitleaks findings below). When the number scanner runs on its own, it reports 0 hits. |

| # | Step (in the clone) | Time (EDT) | Result | Key line |
|---|---|---|---|---|
| 1 | `cp .env.example .env && make setup` | 10:34:57 | PASS | `Using CPython 3.12.12` (backend and monitoring); `added 402 packages, and audited 403 packages in 4s`; `git status --porcelain` empty afterwards |
| 2 | `make seed` | 10:35:10 | PASS | `{"patients": 6, "checkins_due_today": 6, "local_overrides": 0}` |
| 3 | `make test` | 10:35:10 to 10:36:49 | PASS (exit 0) | backend `661 passed in 40.13s`; `data OK: 25 items, 13 red flags, 11 grading rules, 20 personas`; agent scripts `Ran 29 tests`, `Ran 18 tests`, `Ran 27 tests`, each `OK`; frontend `tsc --noEmit` and `eslint` pass; monitoring `All checks passed!`, `391 passed, 1 skipped in 46.22s` |
| 4 | `make validate ARGS=--check` | 10:36:55 to 10:38:46 | PASS (exit 0) | `validation: 29/29 requirements passing, 1052/1053 tests passing` (the one test that does not pass is the monitoring skip `sap-v1 exists in this checkout`). The step rewrites the stamps in `validation/summary.json` and `validation/traceability.md`; `git restore` put both back before step 6. |
| 5 | `make secret-scan` | 10:39:02 | **FAIL** (gitleaks exit 1, make exit 2) | `155 commits scanned.` `leaks found: 3`, all `generic-api-key` false positives (below). `scan_numbers.py` did not run because the target chains with `&&`. Run on its own: `numbers: 0 hits (155 commits, 211172 added lines; 9887 lockfile lines not checked; 15 fictional 555 matches ignored; 5 allowlisted)` |
| 6 | `make site-signal`, then `git diff --exit-code monitoring/out validation/site_signal/report.md` | 10:39:53 | PASS | `committed study (eval seed, stream 0): 14 computed sites; discordance tiers {'watch': 0, 'look': 2, 'none': 12, 'not_computed': 6}; 0.4 s; SIMULATED. A reason to look, not a finding.`; diff exit 0 |
| 7 | Step 6 again | 10:40:05 | PASS | The same line; diff exit 0. Each run added one line to `validation/site_signal/run_log.jsonl` (`git_dirty: false`, code commit `9204a1e`). Neither line was committed, and the file was restored. |
| 8 | `make site-signal-validate ARGS="--quick --check"` | 10:40:17 to 10:41:13 | PASS (exit 0) | `quick check passed: every quick_hashes entry equals summary.json` |
| 9 | Demo: backend on port 8144, frontend on port 3144 (command below) | 10:41 | PASS | `/api/health`: `"ok":true,"demo_mode":true`, `"commit":"5767cd0"`, `site_signal.available: true`, `data_origin: "SIMULATED"`; the dashboard `/` returns 200 |
| 10 | `cd e2e && npm ci && npx playwright install chromium && BASE_URL=http://localhost:3144 npx playwright test` | 10:42:06 to 10:42:54 | PASS | `✓ serious event: replay, review, investigator, sign and send, sponsor inbox (44.9s)`; `✓ site signal: CRA query from a Look or Watch site, coordinator answers, CRA closes, five audit rows (1.2s)`; `2 passed (46.9s)` |
| 11 | Walkthrough screenshots | 10:43 to 10:45 | PASS | 16 full-page PNGs (below) |

**Demo command.** `make demo` binds ports 8000 and 3000, which other sessions on the build machine were using. The same
two processes ran on other ports instead, with the production frontend build (the `make demo DEMO_PROD=1` form, so no
Next.js dev badge):

```bash
(cd backend && DEMO_MODE=1 CORS_ORIGINS=http://localhost:3144 uv run python -m app.seed \
  && DEMO_MODE=1 CORS_ORIGINS=http://localhost:3144 uv run uvicorn app.main:app --port 8144)
(cd frontend && NEXT_PUBLIC_API_BASE_URL=http://localhost:8144 npm run build && npx next start -p 3144)
```

### gitleaks findings (step 5)

| Commit | File:line | What the flagged value is |
|---|---|---|
| `0c9dd432c57d` | `validation/site_signal/run_log.jsonl:2` | A sha256 hex digest (64 lowercase hex characters) under `output_sha256` for the key `monitoring/out/answer_key.json`. The word "key" in that file name sets off `generic-api-key`. |
| `d70cb6e655db` | `validation/site_signal/run_log.jsonl:3` | The same digest, in the line of the determinism re-run |
| `78de1f2282a1` | `PROGRESS.md:62` | A demo SiteQuery ID (`sq_` plus 10 characters) after the words "API after the run:" in the R10 smoke note |

None of the three is a credential, so there is nothing to rotate. The findings first appeared with the committed study
run (`0c9dd43`). Since then every scan of the full history fails on them, including the CI `gitleaks` job. Each future
logged `make site-signal` run adds another run log line with the same key, so ignoring the current fingerprints alone
would not hold.

The lead can apply the fix below. R12 only records results, so the fix is not committed here. It was checked in the
scratch clone: with the fix in place, `make secret-scan` prints `no leaks found` and
`numbers: 0 hits (155 commits, ...)`, and exits 0.

```toml
# .gitleaks.toml, appended
[[allowlists]]
description = "Site Signal run log: output_sha256 values are sha256 file digests (the key monitoring/out/answer_key.json trips generic-api-key)"
condition = "AND"
paths = ['''^validation/site_signal/run_log\.jsonl$''']
regexTarget = "secret"
regexes = ['''^[0-9a-f]{64}$''']
```

```text
# .gitleaksignore (new file)
78de1f2282a10cdd895a18df049c31145ef5963a:PROGRESS.md:generic-api-key:62
```

### Walkthrough screenshots (step 11)

The screenshots are in `$TMPDIR/r12-shots/`, outside the repository, and are not committed. Each is a full page at
1280 px wide. A scratch spec in the clone captured them: it repeats the two smoke journeys and takes a screenshot after
each step.

- Replay to sponsor: `1-01-today-replay`, `1-02-checkin-live`, `1-03-checkin-ended-drafts`, `1-04-review-queue`,
  `1-05-review-confirmed`, `1-06-investigator-assessment`, `1-07-sae-draft`, `1-08-sae-signed-sent`, `1-09-sponsor-inbox`.
- Site query: `2-01-sites`, `2-02-site-105`, `2-03-query-draft`, `2-04-query-approved`, `2-05-query-answered`,
  `2-06-query-closed`, `2-07-audit-rows`.

`docs/screenshots/` already has a screenshot for each stage (`today`, `call`, `review`, `sae`, `sponsor`, `sites-funnel`,
`site-drilldown`, `site-inbox`) except a closed query, so none was added. The scratch spec's first attempt failed on its
own last assertion. It expected five audit rows, but it skips the edit step, so its query has four: drafted, approved,
answered and closed. With the count set to 4 it passed. The R10 smoke does the edit step and checks all five rows (step 10).

Not covered by this run: R12 asks for a second machine and a person who did not build the product. This run used the
build machine, with uv and npm caches already filled.
