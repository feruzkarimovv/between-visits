# WS0 · Readiness (clean clone, security, deploy, packaging)

Owner: the readiness lane (one Claude Code agent, plus a human for the steps marked **Human**). Folders and files: repo-root infrastructure (`.gitleaks.toml`, `.python-version`, `.dockerignore`, `docker-compose.prod.yml`, `render.yaml`, `SECURITY.md`), `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/next.config.ts` (`output` only), `e2e/`, `.github/workflows/ci.yml` (jobs `gitleaks`, `quickstart`, `e2e`), `.github/ISSUE_TEMPLATE/`, `docs/deploy.md`, `docs/privacy-security.md`, `validation/secret-scan.md`, and README pass 1 (WS4 owns the final README, D16). R3 and R4 edit `backend/` and one line of `frontend/` by explicit task; coordinate with WS2 and WS3 in the team chat before starting them.

Read first: `CLAUDE.md`, `docs/03-api-contracts.md` §6 (readiness contract changes), `docs/01-architecture.md`, `docs/07-eval-and-validation.md`, `docs/09-timeline-and-workstreams.md` (checkpoints, cut rules), this file.

Added in the planning round on Sat Oct 10, late. All times are Sun Oct 11, ET. Checkpoint A (target 03:30) belongs to this workstream: it is today's product, correct, packaged and deployed, before any Site Signal code merges.

## Why this workstream exists

On Sat Oct 10 (evening) a fresh clone was set up on a separate machine, following only the README, with `.env` copied from `.env.example`. It worked end to end in demo mode. A real ElevenLabs call could not be tested there (no keys); the team has since confirmed a real browser call works on the build laptop.

What passed:

| Step | Result |
|---|---|
| `make setup` | Pass (20.7 s) |
| `make seed` | Pass: 6 patients, 6 due |
| `make test` | Pass: ruff, 86 pytest, data validation, 7 agent-sync tests, tsc, eslint (18.4 s) |
| `make validate` and `--check` | Pass: 15/15 requirements, 86/86 tests |
| `npm run build`, `npm ci` on the committed lockfile | Pass |
| `make demo`, 13 read-only GET endpoints | All 200, each under 11 ms |
| Replay `rosa_es_urgent` | Pass: grade 3 from `CTCAE5_DIARRHEA_G3`, urgent page at about 91 s, acknowledged, 3 drafts with Spanish quotes and labeled AI translations (167 s, real time) |
| Review → investigator → SAE sign → send → sponsor inbox | Pass; send before sign correctly returns 409 `not_signed` |
| Security probes | Tool call without secret 401; unsigned webhook 401; bad ntfy ack token 401; foreign-origin CORS request gets no allow header |

What needs fixing, ranked by how much it gets in the way of a first-time reader. Each line names the task that fixes it.

| # | Finding | Task |
|---|---|---|
| 1 | The GitHub repository is private, with no description, homepage, topics or issues (MIT license detected). Reviewer access is a human decision (see § Human actions); this plan keeps the repository private and makes the history safe for either choice. | R1, R12, human |
| 2 | README gaps: video and deck are `_TODO_`, team is empty, no screenshots, no hosted demo URL, no prerequisites (uv, Python 3.12, Node 22, make). | R8, D16 |
| 3 | **Timezone bug.** `list_checkins` in `backend/app/routers/api.py` compares the UTC date of a check-in with the local (`DISPLAY_TZ`) "today". From 8 PM to midnight ET a live replay shows "Live now 0" and "Completed 0" and the patient stays "Due". The SAE onset and `AESTDTC` also take the UTC date (Oct 11 while the site became aware on Oct 10, 9:39 PM EDT). | R3 |
| 4 | No cloud deploy path: no Dockerfile, the compose file runs dev servers with source mounts, no deploy doc, no hosted demo instance. | R5, R6 |
| 5 | Security gaps: the `.env.example` default `TOOL_SHARED_SECRET` is accepted; `APP_ENV=dev` (the `.env.example` default) opens `/api/demo/*`, including reset; every `/api/*` route is unauthenticated, so any caller can set `X-BV-Role` and read patient names; `make tunnel` puts that backend on the public internet; there is no security or privacy document. | R4, R6, R7 |
| 6 | Only one replay scenario. In demo mode the other "Call in browser" buttons show a toast and log a 503. | V11, F10 |
| 7 | The replay takes 167 s. `REPLAY_SPEED` is documented only in `docs/03`; the UI has no speed control. | B15, F10 |
| 8 | The AE/CM export has no UI link; its first line is a `#` comment, which `csv.DictReader` takes as the header; `AEOUT=UNKNOWN` while the narrative says "not recovered". | B14, F10 |
| 9 | Spanish grammar error in the AI disclosure of every Spanish call: "de el equipo" instead of "del equipo". | D8 |
| 10 | The README says the voice agent runs on the evaluated Claude model, but `.env.example`, `agent/variants.json` and the config default select a Gemini model, so a fresh `make sync-agent` deploys a model that was not evaluated. | V9 |
| 11 | SAE narrative punctuation: doubled periods, ".;" and a nested parenthesis in the drug-class string, visible in the SAE report and sponsor inbox. | B14 |
| 12 | `make demo` runs `next dev`, so the Next.js dev badge appears in every screenshot and recording. | R5 |
| 13 | At phone width (390 px) Today scrolls sideways (499 px of content); the check-in "Conversation" header is squeezed. | F19 |
| 14 | The sidebar background stops at the bottom of the window on long pages (check-in, SAE, report card). | F19 |
| 15 | `/sae` returns 404 and the nav highlights "Review" on it; the sponsor page has no `h1`. | F10 |
| 16 | The committed traceability file is stamped two commits behind HEAD. | D12 |
| 17 | No GitHub issues track unfinished scope. | R11 |
| 18 | Setup hygiene: uv picked the system Python 3.13 although the project targets 3.12; `npm install` rewrites `frontend/package-lock.json`, so the tree is dirty right after setup; `npm audit` reports 5 high findings in dev-only packages. | R2, R7 |
| 19 | Rule 8: the product brand name appears in `data/red_flags.json` source citations and the product code in `data/study.json` (`registry_title`). | D8 |

Screenshots and step logs from that run are kept outside the repository.

## Kickoff prompt for Claude Code

> You are implementing workstream WS0 (readiness) of Between Visits. Read CLAUDE.md, docs/03-api-contracts.md §6, docs/01-architecture.md, docs/09-timeline-and-workstreams.md and docs/workstreams/WS0-readiness.md. Checkpoint A is due Sun 03:30 ET. Start R1 and R2 now, then R3 and R4 (they edit backend/ files owned by WS2: announce it in the team chat first and keep the diff to what the task lists), then R5, R6, R9, R7, R8. Use plan mode for any task touching more than two files. After each task, run its acceptance check exactly as written, show the output, run `make test`, and commit as "WS0-Rn: <summary>". Never change the repository's visibility, never print or commit a secret or a real phone number, and never write a product brand name or product code into any file (refer to the drug by class only). Live secrets go into the hosting provider's environment settings by a human, never into git. If a contract in docs/03 seems wrong, stop and ask.

## Human actions (whole plan)

These need a person. The agent prepares everything around them and waits; it never enters secrets on the person's behalf.

| When (Sun ET) | Who | Action |
|---|---|---|
| ~01:45 (before kickoff) | Team lead | Commit and push the planning docs to `claude/vibrant-fermi-6vwzie` and merge to `main`. |
| 02:00 | Team lead | Confirm the ElevenLabs key, voice IDs, Anthropic key and `NTFY_TOPIC` in the local `.env` (the browser call already works). The nurse phone is subscribed to `NTFY_TOPIC` and `NTFY_BACKUP_TOPIC`. Give the D8 agent the sha256 of the study drug's lower-case generic name (`printf %s '<name>' \| sha256sum`); the name itself is never written to a file. Confirm the STUDYID decision (`docs/09` § Human actions). |
| 02:10 | Team lead | Decide the agent LLM pin for V9: the evaluated model (`claude-sonnet-5-5`), or the model the working call uses with a background re-evaluation. |
| 02:10 | Team lead | Create or confirm the Render account; grant its GitHub app access to the private repository; approve paid always-on instances (pricing UNVERIFIED); enter the live secrets on `bv-live-api` as `sync: false` environment variables (`TOOL_SHARED_SECRET` equal to the local `.env` value, `ELEVENLABS_*`, `ANTHROPIC_API_KEY`, `NTFY_*`, `AGENTS_LOCK_JSON`, `BV_DASHBOARD_TOKEN`). |
| 02:45 | Team lead (or a teammate the team lead names) | Review the SAP diff before the `sap-v1` tag is pushed (WS5 S1). The agent creates and pushes the tag after the OK; without an OK by 03:15 it tags anyway and says so (`docs/09` cut rules). |
| 02:45–02:55 | Team lead | Publish the tag sha externally: a GitHub Release on `sap-v1`, and a line in the Devpost draft or the organizer channel (`docs/11` §1.2 step 6). |
| 03:00–03:30 | Teammate + nurse | A teammate plays the patient for 3 real browser calls on the live instance (V10); the nurse acknowledges each page on the phone. The teammate gives written consent for use of the recorded audio. |
| 05:50 | Team | Review the deck draft (D14); assign table-demo roles (patient, nurse, CRA, presenter). |
| 07:40–08:30 | Team | Record the hero call (V12) and the 3:00 video (D15) on the production build; upload unlisted. |
| 09:00 | A teammate who did not build the product | Run the final clean clone on a second laptop (R12). |
| 09:30 | Team lead | Submit on Devpost with all contributors and links; arrange reviewer access to the private repository (collaborator invites, or another option the team chooses). |
| After the event (not part of this plan) | Team | Decide whether to make the repository public. If yes, re-run `make secret-scan` on the final history first. |

Open questions that block a task until a human answers: the LLM pin (V9), reviewer access to the private repository (D16), hosting spend (R6), consent to serve recorded call audio from the public demo (V11; without consent, recorded scenarios ship transcript-only).

## Tasks

### R1 · Full-history secret scan (target 02:10, Checkpoint A)
- Install a pinned gitleaks v8 release binary (record the exact version from `gitleaks version`). Add `.gitleaks.toml`: `[extend] useDefault = true`, plus an allowlist for the documented placeholders only (`+1XXXXXXXXXX`, `+1555…` numbers, `change-me…` strings, `bv-change-me…` topics).
- `validation/scan_numbers.py` (stdlib only): reads `git log -p --all` and, on every added line, finds US-style numbers written with or without `+1` and with spaces, dashes, dots or parentheses between the groups: `(?<![0-9])(?:\+?1[ .-]?)?\(?[2-9][0-9]{2}\)?[ .-]?[2-9][0-9]{2}[ .-]?[0-9]{4}(?![0-9])`. It strips the separators from each match and ignores only matches whose exchange (digits 4–6 of the 10-digit number) is `555`, the fictional range every committed placeholder uses. Any other match prints the commit, the file and the last 4 digits only, and the script exits 1. Known false positives (for example a digit run inside a hash) go in `validation/scan_numbers_allow.txt` as the sha256 of the matched digits, never the digits.
- `Makefile` target `secret-scan`: `gitleaks git --redact --log-opts="--all" -v . && python3 validation/scan_numbers.py`. gitleaks stays the primary check.
- CI job `gitleaks` in `.github/workflows/ci.yml`: `actions/checkout@v4` with `fetch-depth: 0`, download the same pinned binary (no third-party action), run `make secret-scan`.
- Write `validation/secret-scan.md`: tool and version, date and time, commit range (`git rev-list --all --count` and the first and last sha), findings (0), and how to re-run.
- If anything is found: stop, tell the team lead, rotate the credential first, then decide on history rewriting with the team. Do not rewrite history on your own.
- No visibility change. Going public is a later human decision.
- **Files:** `.gitleaks.toml`, `validation/scan_numbers.py`, `validation/scan_numbers_allow.txt`, `Makefile`, `.github/workflows/ci.yml`, `validation/secret-scan.md`.
- **Accept:**
  ```bash
  make secret-scan; echo "exit=$?"
  ```
  gitleaks prints `no leaks found`, `scan_numbers.py` prints `numbers: 0 hits`, and the last line is `exit=0`. A self-test: a temporary commit in a scratch clone containing a NANP-shaped, non-555 number generated at test time (never written to this repo or its docs) makes the scan exit 1 and print only the last 4 digits. `validation/secret-scan.md` records the version, date, commit range and 0 findings. The CI `gitleaks` job is green on the pushed commit.

### R2 · Toolchain pins and clean setup (target 02:10, Checkpoint A)
- Add `.python-version` (`3.12`). `backend/pyproject.toml`: `requires-python = ">=3.12,<3.13"`; re-lock.
- `make setup` runs `npm ci` instead of `npm install`; commit a lockfile that `npm ci` leaves unchanged. Once WS5 S1 lands, `make setup` also runs `cd monitoring && uv sync`.
- README Prerequisites (short block, merged into R8): uv, Python 3.12, Node 22, make; Docker optional.
- **Files:** `.python-version`, `backend/pyproject.toml`, `backend/uv.lock`, `Makefile` (`setup`), `frontend/package-lock.json`, `README.md` (Prerequisites).
- **Depends on:** nothing.
- **Accept:** in a fresh clone of the pushed branch:
  ```bash
  cp .env.example .env && make setup && git status --porcelain
  cd backend && uv run python -V
  ```
  `git status --porcelain` prints nothing; the second command prints `Python 3.12.x`.

### R3 · Timezone fix: local dates (target 02:30, Checkpoint A)
Contract: `docs/03` §6.4. CAPA-002.
- `backend/app/timeutil.py`: add `local_date(dt) -> date` (UTC-aware datetime → `DISPLAY_TZ` date).
- `GET /api/checkins?date=`: a check-in is listed when `local_date(started_at, else scheduled_for, else created_at)` or `local_date(created_at)` equals the requested local day (default: today local).
- Patient timeline point dates, ae.csv `AESTDTC` fallback (`export.py`) and SAE `reaction.onset_date` fallback and last-dose lookup (`sae.py`) use the local call date. Response shapes do not change.
- `backend/tests/test_local_dates.py`: freeze the clock at `2026-10-11T03:30:00Z` (23:30 ET on Oct 10) without a clock library (method in `docs/03` §6.4: monkeypatch `utcnow` on `app.timeutil` and on every loaded `app.*` module that imported it; `models.py` fields with `default_factory=utcnow` become `default_factory=lambda: timeutil.utcnow()`), run the Rosa replay synchronously (`replay.start(..., speed=1000, run_async=False)`), assert: listed under Oct 10 as `in_progress` or `completed`; `AESTDTC == 2026-10-10`; SAE onset `2026-10-10`. Tag `@pytest.mark.req("REQ-016")`.
- Add REQ-016 to `validation/requirements.yaml` in the same commit as the test (text in `docs/07` §6). Add CAPA-002 to `validation/capa.md` (found, root cause, correction, prevention = the test ID, commit).
- **Files:** `backend/app/timeutil.py`, `backend/app/models.py` (default factories only), `backend/app/routers/api.py`, `backend/app/services/export.py`, `backend/app/services/sae.py`, `backend/tests/test_local_dates.py`, `validation/requirements.yaml`, `validation/capa.md`.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_local_dates.py
  cd .. && make validate ARGS=--check
  ```
  The test passes; the traceability check exits 0 and lists `REQ-016 PASS`.

### R4 · Default-secret refusal and demo routes only in DEMO_MODE (target 02:30, Checkpoint A)
Contract: `docs/03` §6.2–6.3.
- `backend/app/config.py`: `demo_controls_enabled` returns `demo_mode` only (`APP_ENV=dev` no longer opens `/api/demo/*`). Add `assert_safe_startup()`: with `DEMO_MODE=0`, exit non-zero with a clear message when `TOOL_SHARED_SECRET` is empty, equals the `.env.example` placeholder, or is shorter than 24 characters; log a warning when `NTFY_TOPIC` is shorter than 16 characters.
- `backend/app/main.py`: call it at startup. `backend/app/routers/demo.py`: 404 `demo_disabled` unless demo mode.
- `backend/tests/conftest.py`: the test `TOOL_SHARED_SECRET` becomes a string of at least 24 characters (today it is `test-secret`, which the guard would refuse); add a `demo_mode` fixture that sets `DEMO_MODE=1` and calls `get_settings.cache_clear()` (and restores both afterwards) for tests that call `/api/demo/*`. `backend/tests/test_review.py` calls `/api/demo/scenarios` and uses that fixture. `backend/tests/test_security_guards.py`, tagged REQ-017; add REQ-017 to `requirements.yaml` in the same commit.
- `.env.example`: comment above `TOOL_SHARED_SECRET` showing how to generate one (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`).
- Frontend: Today shows replay controls only when `GET /api/health` returns `demo_mode: true` (one condition in `frontend/src/app/page.tsx`; do this before WS3 starts F10 on the same file).
- `docs/03` §1 "Demo controls" heading already says "enabled only when `DEMO_MODE=1`"; the README says local replay development uses `make demo`.
- **Files:** `backend/app/config.py`, `backend/app/main.py`, `backend/app/routers/demo.py`, `backend/tests/conftest.py`, `backend/tests/test_review.py`, `backend/tests/test_security_guards.py`, `.env.example`, `frontend/src/app/page.tsx`, `validation/requirements.yaml`.
- **Accept:**
  ```bash
  cd backend && DEMO_MODE=0 TOOL_SHARED_SECRET=change-me-long-random-string uv run uvicorn app.main:app; echo "exit=$?"
  ```
  The process prints the refusal message and `exit=` is non-zero.
  ```bash
  make demo        # starts; Today shows Replay scenario
  ```
  ```bash
  cd backend && APP_ENV=dev DEMO_MODE=0 TOOL_SHARED_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))') uv run uvicorn app.main:app --port 8000 &
  curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/demo/scenarios
  ```
  prints `404`. `uv run pytest -q tests/test_security_guards.py` passes.

### R5 · Production Dockerfiles and compose (target 02:45, Checkpoint A)
- `backend/Dockerfile`, build context = repo root: `python:3.12-slim` plus uv; copies `backend/`, `data/`, `scenarios/`, `agent/variants.json`, `eval/results/`, `validation/`; from Checkpoint B also `monitoring/` (project and `out/`, synced by B19). Start command: seed when the database file is absent, then `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Health `commit` without a `.git` directory: `git_commit()` in `backend/app/main.py` already reads `GIT_COMMIT`; add `RENDER_GIT_COMMIT` as a second fallback (Render's variable name is UNVERIFIED; check the Render docs), shortened to 7 characters. `docker-compose.prod.yml` passes `GIT_COMMIT=$(git rev-parse --short HEAD)`.
- `frontend/Dockerfile`: Node 22, `npm ci`, `ARG NEXT_PUBLIC_API_BASE_URL` (inlined at build time), `next build`, standalone output, `next start`. `frontend/next.config.ts`: `output: "standalone"`.
- `docker-compose.prod.yml` (both images, `DEMO_MODE=1` by default) and `make up` (`docker compose -f docker-compose.prod.yml up --build`). `.dockerignore` excludes `.env`, `.env.*` (except `.env.example`), `node_modules`, `.venv`, `*.db`, `scenarios/audio/`, `.git`, and the gitignored local files that must never enter an image: `data/patients.local.json` (real phone numbers, rule 8), `data/local/` (licensed PRO-CTCAE override, rule 9), `agent/agents.lock.json` and `eval/results/*.local*`.
- `make demo` gains `DEMO_PROD=1`: the frontend is served by `next build && next start`, so recordings have no dev badge.
- **Files:** `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/next.config.ts`, `docker-compose.prod.yml`, `.dockerignore`, `Makefile` (`up`, `demo`), `backend/app/main.py` (commit fallback).
- **Depends on:** R2, R4.
- **Accept:**
  ```bash
  make up    # in another terminal
  curl -fsS localhost:8000/api/health | jq -e '.ok and .demo_mode'
  curl -fsS localhost:3000 | grep -q 'Between Visits' && echo web-ok
  ```
  ```bash
  docker run --rm --entrypoint sh <backend-image> -c 'test ! -e /app/data/patients.local.json && test ! -d /app/data/local && test ! -e /app/.env && echo local-files-excluded'
  ```
  prints `true`, `web-ok` and `local-files-excluded` (run with `data/patients.local.json` and `data/local/` present on the build machine). A screenshot of `localhost:3000` shows no Next.js dev badge.

### R6 · Render blueprint, deploy doc, public demo and private live instances (target 03:00 live API, 03:15 demo pair; Checkpoint A)
- `render.yaml`, one blueprint, Docker runtime, `healthCheckPath: /api/health`, plan `starter` (always-on; pricing UNVERIFIED):

  | Service | Settings |
  |---|---|
  | `bv-demo-api` | `DEMO_MODE=1`, public URL, `CORS_ORIGINS` = the `bv-demo-web` URL |
  | `bv-demo-web` | build arg `NEXT_PUBLIC_API_BASE_URL` = the `bv-demo-api` URL |
  | `bv-live-api` | `DEMO_MODE=0`, `APP_ENV=prod`, `PUBLIC_BASE_URL` = its own URL, `CORS_ORIGINS=http://localhost:3000` (the dashboard for live calls runs locally against it, see V10), secrets as `sync: false` env vars entered by a human |

- `backend/app/services/elevenlabs.py` and `config.py`: when `agent/agents.lock.json` is absent, read the variant map from `AGENTS_LOCK_JSON` (a JSON string).
- Optional dashboard token (`docs/03` §6.8): when `BV_DASHBOARD_TOKEN` is set, every `/api/*` request except `GET /api/health` needs `X-BV-Token`, else 401 `invalid_token`. Set it only on `bv-live-api`. In the same task, `apiFetch()` in `frontend/src/lib/api.ts` sends `X-BV-Token` when `NEXT_PUBLIC_BV_DASHBOARD_TOKEN` is set (one line; announce it to WS3), so the V10 calls work before F10.
- `render.yaml` services auto-deploy from `main` (`autoDeploy: true`, branch `main`); that is how each checkpoint reaches the public URL.
- `docs/deploy.md`: Render steps; env table per service; how `PUBLIC_BASE_URL` and `make sync-agent ARGS="--setup-webhook"` point at `bv-live-api`; how to copy `agent/agents.lock.json` into `AGENTS_LOCK_JSON`; SQLite is single-instance and the container disk is ephemeral (state resets on restart; a persistent disk is optional, pricing UNVERIFIED); Cloud Run alternative with `--min-instances 1 --max-instances 1 --no-cpu-throttling` (the re-page loop and replay threads run outside requests). If the deploy is not up by 03:30, mark the doc "verified locally only" (cut rule) and use the tunnel for live calls.
- README: the public demo URL.
- **Files:** `render.yaml`, `backend/app/services/elevenlabs.py`, `backend/app/config.py`, `backend/app/main.py` (token middleware), `frontend/src/lib/api.ts` (token header line), `docs/deploy.md`, `README.md`.
- **Depends on:** R5. **Human:** Render account, GitHub app access to the private repository, billing, secrets.
- **Accept:**
  ```bash
  curl -fsS $DEMO_API/api/health | jq -e '.demo_mode==true and .commit=="'$(git rev-parse --short HEAD)'"'
  curl -fsS $LIVE_API/api/health | jq -e '.demo_mode==false and .browser_calls_enabled'
  curl -s -o /dev/null -w '%{http_code}\n' $LIVE_API/api/patients     # 401 (no X-BV-Token)
  BASE_URL=$DEMO_WEB npx playwright test --config e2e smoke    # once R10 exists; before that, the manual path below
  ```
  The first two print `true`, the third prints `401`. In an incognito window on `$DEMO_WEB`: Replay → confirm drafts → Investigator assessment → SAE sign → send → the report appears in the sponsor inbox.

### R7 · SECURITY.md and docs/privacy-security.md (target 03:15, Checkpoint A)
- `SECURITY.md`: how to report a problem, supported scope (demo code, synthetic data only), how secrets are handled (`.env` and host env vars only; `make secret-scan`).
- `docs/privacy-security.md`:
  - Data flows (table): ElevenLabs (call audio, transcripts); Anthropic (post-call text: extraction, safety net, translation, narratives); ntfy (subject ID, level and finding labels only; topic names act as shared secrets); sponsor views and site queries (subject IDs only).
  - Controls in place: tool secret, HMAC post-call webhook, ack tokens, CORS, startup guard (R4), demo-only routes (R4), 403 roles (B12), audit hash chain (B13), optional dashboard token (R6).
  - Gaps: no real authentication or RBAC (demo identity headers), no rate limiting, SQLite single instance, dev-only npm audit findings, audit chain not anchored outside the database.
  - Compliance gap table: HIPAA and 21 CFR Part 11 (e-signatures, audit trail, validation), not assessed. ElevenLabs BAA availability and data-retention settings: UNVERIFIED.
  - Regulatory limits: shadow mode only; investigator control of ePRO source data (EMA/INS/GCP/112288/2023) and the sponsor's safety-awareness implications of an unfiltered patient stream are open questions, marked UNVERIFIED.
- No GAMP 5 text (section numbers only, if any). Drug by class only.
- **Files:** `SECURITY.md`, `docs/privacy-security.md`, `README.md` (links).
- **Depends on:** R4.
- **Accept:**
  ```bash
  grep -c UNVERIFIED docs/privacy-security.md                 # >= 3
  grep -n 'SECURITY.md\|privacy-security' README.md             # both linked
  uv run --project backend python data/validate_data.py         # product-name guard (D8): 0 hits
  make secret-scan
  ```
  All four succeed as described.

### R8 · README pass 1: reviewer path, prerequisites, links (target 03:30, Checkpoint A)
- A 3-minute reviewer path on the public demo URL (what to click, in order, and what each screen proves).
- Local quickstart: `make setup && make seed && make demo`. Prerequisites from R2. `REPLAY_SPEED` and the 1x/2x/4x control.
- Links: SECURITY, privacy and security, deploy, specs. Model line that matches `agent/deployed_snapshot.json` (V9). Results with Clopper-Pearson intervals from `eval/results/latest.json` (D10).
- Video and deck stay `_TODO_` with the note "added at submission" (D16 fills them).
- **Files:** `README.md`.
- **Depends on:** R6, V9, D10.
- **Accept:** a teammate who did not build it follows only the README from the public URL and reaches the sponsor inbox in under 3 minutes (time it). `grep -n '_TODO_' README.md` returns only the video and deck lines.

### R9 · Quickstart CI job (target 03:15, Checkpoint A)
- Job `quickstart` in `.github/workflows/ci.yml`, on a clean runner: `cp .env.example .env`; `make setup`; `make seed`; `make test`; `make demo` in the background; wait for `/api/health`; `POST /api/demo/replay/rosa_es_urgent?speed=4`; poll `GET /api/checkins/{id}` until `drafts` has 3 items (timeout 120 s).
- **Files:** `.github/workflows/ci.yml`.
- **Depends on:** R2, R4, B15 (speed parameter; until it lands, use `REPLAY_SPEED=4`).
- **Accept:** CI job `quickstart` is green on the Checkpoint A commit; its log shows `drafts=3` for `rosa_es_urgent`.

### R10 · Playwright smoke, including Site Signal (target 06:00, Checkpoint B)
- `e2e/` has its own `package.json` (Playwright is not a frontend dependency), `playwright.config.ts` and `smoke.spec.ts`:
  1. Replay → review confirm → investigator → SAE sign → send → sponsor inbox.
  2. As CRA: `/sites` → a site at Look or Watch → select unmatched episodes → draft query → approve. As coordinator: `/site-inbox` → respond with a code. As CRA: close. `/audit` shows the five `site_query.*` rows.
- CI job `e2e` runs it against `make demo`.
- **Files:** `e2e/package.json`, `e2e/package-lock.json`, `e2e/playwright.config.ts`, `e2e/smoke.spec.ts`, `.github/workflows/ci.yml`.
- **Depends on:** F12, F13, F14, B18.
- **Accept:**
  ```bash
  cd e2e && npm ci && BASE_URL=http://localhost:3000 npx playwright test
  BASE_URL=$DEMO_WEB npx playwright test
  ```
  Both runs pass (local `make demo`, then the public URL).

### R11 · GitHub issues backlog (target 06:45, Checkpoint C)
- `.github/ISSUE_TEMPLATE/not-built.md`. Create one issue per entry in `docs/backlog.md` §3–§4 (BL-01..BL-20) plus one per cut recorded in the root `NOT_BUILT.md` (titles from `docs/backlog.md` §5), with `gh`, using the labels and template in `docs/backlog.md` §1–§2. Each `NOT_BUILT.md` item links its issue number; the README Roadmap links the issue list.
- **Files:** `.github/ISSUE_TEMPLATE/not-built.md`, `NOT_BUILT.md` (issue links), `README.md` (Roadmap).
- **Depends on:** D13; `docs/backlog.md`.
- **Accept:**
  ```bash
  gh issue list --state open --label not-built --json number | jq length     # >= 20 plus the number of cuts
  ```
  Every `NOT_BUILT.md` item ends with `#<number>`.

### R12 · Final clean clone from GitHub (09:00, Packaging)
- On a second machine, authenticated (the repository is private).
- **Files:** none; record the result (commit, time, pass/fail per step) in an appendix of `validation/secret-scan.md`, or link the CI run.
- **Depends on:** all Checkpoint C tasks.
- **Accept:**
  ```bash
  gh repo clone <owner>/between-visits && cd between-visits
  cp .env.example .env && make setup && make seed && make test && make demo   # then, in another terminal:
  cd e2e && npm ci && BASE_URL=http://localhost:3000 npx playwright test
  make secret-scan
  ```
  Every step passes at the submission commit.

## Checkpoint A gate (Sun 03:30)

Run in order and paste the output in the team chat:

```bash
make test
make validate ARGS=--check            # REQ-001..020 PASS (REQ-016..020 added with their tests)
make secret-scan
curl -fsS $DEMO_API/api/health | jq '{ok, demo_mode, commit}'
curl -fsS $LIVE_API/api/health | jq '{ok, demo_mode, browser_calls_enabled}'
jq '.calls|length' eval/results/voice_checks.json      # 3 (V10)
```

Definition of done (from `docs/09`): `make test` green including REQ-016..020; secret scan clean (repository stays private); `.python-version` and `npm ci` give a clean setup; timezone fix with the frozen 23:30 ET test; default-secret refusal; demo routes only in demo mode; 403 for the wrong role; audit hash chain and `/api/audit/verify`; CSV/AEOUT fix and CAPA log; Spanish "del" fix and product-name leaks removed from `data/`; agent LLM pinned or documented, with `agent/deployed_snapshot.json`; production Dockerfiles; `render.yaml` with the public demo pair live and the private live API; replay → review → SAE → sponsor works in an incognito window on the public URL; 3 real browser calls against the live backend paged ntfy and are logged in `eval/results/voice_checks.json`; report card shows Clopper-Pearson intervals; `SECURITY.md` and `docs/privacy-security.md`; README reviewer path with the demo URL; traceability regenerated.

## Cut rules for WS0

- 03:30, deploy: if the Render pair is not up, use the tunnel for live calls and `make up` locally; keep `render.yaml` and `docs/deploy.md`, marked "verified locally only"; retry the deploy at Checkpoint C.
- Checkpoint A slips past 02:30: WS5 and WS2 start Checkpoint B work anyway (S2–S6, B16–B17 do not depend on the deploy); open A items move to Checkpoint C.
- Never cut: the secret scan before any packaging step, the README, the startup guard and demo-only routes.
