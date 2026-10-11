# Between Visits

Voice agent that phones cancer-trial patients between clinic visits (English or Spanish, standard or extra-time pace), asks plain-language symptom questions (our own wording; NCI's official PRO-CTCAE items can be loaded locally by registered studies), grades answers with fixed CTCAE v5 rules, pages an on-call nurse for red flags, and turns calls into draft AE/medication entries with verbatim evidence for human review, plus a sponsor serious-event handoff with a 24-hour clock. Built at HackRU Fall 2026 for Regeneron's clinical-trial challenge. Synthetic data only. Not a medical device.

Specs live in `docs/`. Read the relevant ones before changing anything:
`00-overview` (scope, rules) · `01-architecture` · `02-data-model` · `03-api-contracts` (source of truth for every interface) · `04-voice-agent` · `05-clinical-rules` · `06-frontend` · `07-eval-and-validation` · `08-demo-and-pitch` · `09-timeline-and-workstreams` (current plan and checkpoints) · `10-site-signal` (Site Signal PRD) · `11-site-signal-sap` (Site Signal statistical analysis plan) · `workstreams/WS0..WS5` · `KICKOFF` (prompt for the implementing session). Background: `decisions/ADR-001-site-signal`, `research/site-signal-methods`, `research/synthea`, `backlog` (not-built items, source for GitHub issues).

## Non-negotiable rules (check every change against these)

1. **The LLM listens, rules grade, humans decide.** No grade, red-flag decision or escalation level may come from an LLM at runtime. LLMs map speech to enums/numbers; `backend/app/services/rules.py` decides, driven only by `data/ctcae_rules.json` and `data/red_flags.json`. Statistical site flags (Site Signal) come only from pre-specified code (`monitoring/`, `backend/app/services/site_signal.py`, `episodes.py`) driven by `data/signal_rules.json` and the `sap-v1` parameters, with no LLM anywhere on that path, and a human decides whether to act.
2. **Approved words only.** Anything clinical the agent says is assembled by the backend from `data/scripts.json` and `data/symptom_items.json` (or the gitignored local override `data/local/symptom_items.local.json`) in the call's language. Never hard-code clinical text or thresholds in code. Never machine-translate clinical questions at runtime.
3. **No medical advice** anywhere: agent, page messages, UI copy, generated narratives.
4. **Disclose and offer a human** in the agent's first turn, every call, every language.
5. **Fail safe:** if anything errors on a path that could involve a red flag, escalate. Never fail silent.
6. **Evidence on every draft** (verbatim quote in original language + timestamp + source). AI translations and AI drafts are always labeled in the UI.
7. **Nothing is final without a human**, and every human action writes an `AuditEvent` (append-only). The audit log is a hash chain (`GET /api/audit/verify`).
8. **Synthetic data only.** Never commit real phone numbers, keys or real patient data. Real numbers live in `.env` and `data/patients.local.json` (gitignored). Refer to the study drug by class only: drug class names are anti-PD-1 (CD3 bispecific in roadmap context only); no product brand name, product code or generic name anywhere in git (the product-name guard in `data/validate_data.py` enforces it with a sha256 denylist). The repository is private; changing visibility is a human decision after a fresh secret scan.
9. **No licensed content in git:** no PRO-CTCAE item wording, no MedDRA codes or hierarchy, no WHODrug. Pages and push notifications carry the subject ID only, never names.

## Repo map and ownership

| Folder | Owner | What |
|---|---|---|
| `backend/` | WS2 | FastAPI + SQLModel (SQLite), rules, interview engine, tools, webhooks, pipeline |
| `frontend/` | WS3 | Next.js App Router dashboard |
| `agent/` | WS1 | ElevenLabs agent config-as-code (`prompt.md`, `tools.json`, `sync_agent.py`) |
| `data/` | WS4 | clinical content + seed data (single source of truth) |
| `eval/`, `validation/` | WS4 | simulated-patient evaluation, requirement traceability |
| `scenarios/` | WS1+WS2 | recorded replays for demo mode |
| `monitoring/`, `validation/site_signal/` | WS5 | Site Signal statistics (planned, `docs/10`, `docs/11`): separate uv project (params, simulate, match, indicators, calibrate, simaerep classic, validate, blind run); committed outputs in `monitoring/out/`. numpy/scipy live only here. |
| repo-root infra (`Dockerfile`s, `render.yaml`, `docker-compose.prod.yml`, `.gitleaks.toml`, `SECURITY.md`, `e2e/`) | WS0 | Readiness (planned, `docs/workstreams/WS0-readiness.md`): secret scan, toolchain pins, deploy, security docs, end-to-end smoke |

Only edit your workstream's folders unless your task says otherwise.

## Commands

```bash
make setup        # uv sync (backend, Python 3.12 from .python-version) + npm ci (frontend; never rewrites package-lock.json)
make dev          # backend :8000 (reload) + frontend :3000
make seed         # reset DB and load data/*.json (+ data/patients.local.json)
make test         # pytest + data validation + frontend typecheck/lint
make tunnel       # ngrok http 8000 --url https://$NGROK_DOMAIN  (= PUBLIC_BASE_URL)
make sync-agent   # create/update the 4 ElevenLabs agent variants + tools, writes agent/agents.lock.json
                  # ARGS="--setup-webhook" (post-call webhook) · ARGS="--inbound es-extra_time" (call-in fallback)
make types        # regenerate frontend/src/lib/api-types.ts from /openapi.json
make eval         # run the 20-persona evaluation -> eval/results/latest.json
make validate     # build validation/traceability.md + summary.json
make demo         # DEMO_MODE=1: no external keys, replay scenarios
                  # /api/demo/* exists only under make demo (DEMO_MODE=1); outside it the backend refuses
                  # to start with an empty, placeholder or < 24-character TOOL_SHARED_SECRET
                  # DEMO_PROD=1 serves the production frontend build (next build && next start, no dev badge)
make up           # production images (docker-compose.prod.yml), DEMO_MODE=1 by default (BV_DEMO_MODE=0: live API),
                  # no Next dev badge; host ports API_PORT/WEB_PORT (default 8000/3000); health `commit` from GIT_COMMIT
make secret-scan  # gitleaks (pinned 8.30.1) over the full history of every ref + real-number grep (validation/secret-scan.md)
make planning-grid # S1: pre-tag planning grid (dev seed, docs/11 §11.5); picks the design and the gross planted capture loss
```

Planned (Sun Oct 11, `docs/09`); not in the Makefile until the named task lands, then move each line into the block above:

```bash
make site-signal           # S6: regenerate monitoring/out/* + validation/site_signal/report.md from the sap-v1 seed (< 60 s)
make site-signal-validate  # S7: operating characteristics (background, <= 45 min); ARGS="--quick --check" in CI
make blind-run SEED=...    # S8: command-line blind run; ARGS=--precompute writes the fallback seeds
make cohort                # S10 (optional): Synthea roster, language/age mix only
```

Planned changes to existing targets: `make setup` also syncs `monitoring/` (S1); `make test` adds the monitoring suite (S6).

## Conventions

**Contracts first.** `docs/03-api-contracts.md` defines every endpoint, tool and webhook. If a change is needed, update the doc first, tell the team, then implement. Frontend types are generated; never hand-edit `api-types.ts`.

**Backend (Python 3.12, uv):** FastAPI routers stay thin; logic lives in `app/services/*` as plain functions that take a DB session. Pydantic models for every request/response. Type hints everywhere, `ruff` clean. IDs from `app/ids.py` (`pat_`, `ci_`, `ans_`, `fnd_`, `esc_`, `dr_`, `sae_`, `aud_`). UTC ISO-8601 timestamps. Dates shown or exported as days use DISPLAY_TZ local dates (`timeutil.local_date`). Errors: `{"error":{"code","message"}}`. Roles (`X-BV-Role`) are coordinator, investigator, sponsor, cra (missing or unknown means coordinator); restricted routes use `require_role(*roles)` and a wrong role returns 403 `wrong_role`. Agent tools always return HTTP 200 with the `{ok, next:{action, item_code, say}, escalated}` envelope. One structured log line per tool call, page, ack and webhook, including `checkin_id`.

**External services** (ElevenLabs, Gemini, Twilio) are wrapped in `app/services/{elevenlabs,gemini,pager}.py`. Each has a deterministic fake used by tests and by `DEMO_MODE=1`. Tests never call real APIs.

**Frontend (TypeScript strict):** TanStack Query for all server state, `apiFetch()` for every request (adds `X-BV-User`/`X-BV-Role`), shadcn/ui components, Tailwind tokens from `docs/06-frontend.md`. No `any`. Every AI-produced string shows an `AiLabel`. Grades always say "provisional".

**Tests:** pytest in `backend/tests/`. Tag tests that prove a requirement: `@pytest.mark.req("REQ-005")` (list in `validation/requirements.yaml`). Rules and interview engine get table-driven tests.

**Commits:** one task per commit, message `WSn-Xn: summary`. Pull/rebase before pushing. Run `make test` first.

## Definition of done (every task)

The task's acceptance check in its workstream file passes and its output is shown; `make test` passes; no new contract drift; no secrets or real numbers in the diff; the non-negotiable rules above still hold.

## Don't

- Don't let an LLM decide grades, red flags, escalation levels or what question comes next.
- Don't paraphrase, translate or invent clinical wording; edit `data/` (WS4 owns it) instead.
- Don't add features that aren't in your workstream task list; propose them in the team chat.
- Don't add heavy dependencies (no ORMs besides SQLModel, no state libraries besides TanStack Query, no websockets; polling is intentional).
- Don't name real drug products or imply this is a real study's data.

## Status (update at each milestone in docs/09)

- **Sat Oct 10, 4:30 PM ET:** specs, contracts, clinical data, agent config, personas, requirements and replay fixtures complete.
- **Sat Oct 10, ~6:30 PM ET (solo build, one Claude Code session):** backend B0–B10 implemented (`backend/`, 82 tests, `make validate` 15/15 requirements); `agent/sync_agent.py` (dry-run verified, not yet run against the real API); eval harness `eval/run_eval.py` + `eval/score.py` + `eval/judge.py` (needs `GEMINI_API_KEY`); `validation/build_traceability.py`; Makefile, docker-compose, CI. Contract additions are in `docs/03-api-contracts.md` § 4. Frontend (`frontend/`, Next.js 16, all pages F0–F8) built and verified against the real backend: typecheck, lint, build pass; full replay → review → SAE → sponsor chain works. Not yet done: real ElevenLabs browser call (needs keys), protocol-to-plan stretch, `/sae` list page, 125% zoom pass and screenshots, phone-width polish. `.env` exists locally with generated `TOOL_SHARED_SECRET` and ntfy topics; API keys still empty.
- **Sat Oct 10, ~11:30 PM ET (planning only, no code changed):** a real ElevenLabs browser call works (confirmed by the team lead; not yet re-verified against a deployed backend, task V10). Direction decided: **Between Visits + Site Signal** (sponsor-side capture-discordance layer on simulated multi-site data, pre-registered under the `sap-v1` tag). Plan: `docs/10-site-signal.md`, `docs/11-site-signal-sap.md`, `docs/09-timeline-and-workstreams.md` (checkpoints SAP → A → B → C → packaging, in that order; no deadlines, no time-based cuts). Kickoff prompt for the implementing session: `docs/KICKOFF.md`. The repository stays private; changing visibility is a later human decision.
- Human setup still pending (updated Sat Oct 10 late; times in `docs/09` § Human actions): confirm ElevenLabs key, voice IDs, `ANTHROPIC_API_KEY` and `NTFY_TOPIC` in `.env`; nurse phone subscribed to `NTFY_TOPIC` and `NTFY_BACKUP_TOPIC`; agent LLM pin decision (V9); Render account, GitHub access and live secrets (R6); SAP review before the `sap-v1` tag. Phone calling through Twilio is not connected for the hackathon (browser calls only).
- Run locally: `make setup && make seed && make dev`; tests: `make test`; replay without keys: `make demo` → Today → Replay scenario.
