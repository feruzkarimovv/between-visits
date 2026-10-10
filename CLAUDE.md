# Between Visits

Voice agent that phones cancer-trial patients between clinic visits (English or Spanish, standard or extra-time pace), asks plain-language symptom questions (our own wording; NCI's official PRO-CTCAE items can be loaded locally by registered studies), grades answers with fixed CTCAE v5 rules, pages an on-call nurse for red flags, and turns calls into draft AE/medication entries with verbatim evidence for human review, plus a sponsor serious-event handoff with a 24-hour clock. Built at HackRU Fall 2026 for Regeneron's clinical-trial challenge. Synthetic data only. Not a medical device.

Specs live in `docs/`. Read the relevant ones before changing anything:
`00-overview` (scope, rules) · `01-architecture` · `02-data-model` · `03-api-contracts` (source of truth for every interface) · `04-voice-agent` · `05-clinical-rules` · `06-frontend` · `07-eval-and-validation` · `08-demo-and-pitch` · `09-timeline-and-workstreams` · `workstreams/WS1..WS4`.

## Non-negotiable rules (check every change against these)

1. **The LLM listens, rules grade, humans decide.** No grade, red-flag decision or escalation level may come from an LLM at runtime. LLMs map speech to enums/numbers; `backend/app/services/rules.py` decides, driven only by `data/ctcae_rules.json` and `data/red_flags.json`.
2. **Approved words only.** Anything clinical the agent says is assembled by the backend from `data/scripts.json` and `data/symptom_items.json` (or the gitignored local override `data/local/symptom_items.local.json`) in the call's language. Never hard-code clinical text or thresholds in code. Never machine-translate clinical questions at runtime.
3. **No medical advice** anywhere: agent, page messages, UI copy, generated narratives.
4. **Disclose and offer a human** in the agent's first turn, every call, every language.
5. **Fail safe:** if anything errors on a path that could involve a red flag, escalate. Never fail silent.
6. **Evidence on every draft** (verbatim quote in original language + timestamp + source). AI translations and AI drafts are always labeled in the UI.
7. **Nothing is final without a human**, and every human action writes an `AuditEvent` (append-only).
8. **Synthetic data only.** Never commit real phone numbers, keys or real patient data. Real numbers live in `.env` and `data/patients.local.json` (gitignored). Refer to the study drug by class only.
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

Only edit your workstream's folders unless your task says otherwise.

## Commands

```bash
make setup        # uv sync (backend) + npm install (frontend)
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
```

## Conventions

**Contracts first.** `docs/03-api-contracts.md` defines every endpoint, tool and webhook. If a change is needed, update the doc first, tell the team, then implement. Frontend types are generated; never hand-edit `api-types.ts`.

**Backend (Python 3.12, uv):** FastAPI routers stay thin; logic lives in `app/services/*` as plain functions that take a DB session. Pydantic models for every request/response. Type hints everywhere, `ruff` clean. IDs from `app/ids.py` (`pat_`, `ci_`, `ans_`, `fnd_`, `esc_`, `dr_`, `sae_`, `aud_`). UTC ISO-8601 timestamps. Errors: `{"error":{"code","message"}}`. Agent tools always return HTTP 200 with the `{ok, next:{action, item_code, say}, escalated}` envelope. One structured log line per tool call, page, ack and webhook, including `checkin_id`.

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
- Human setup still pending: ElevenLabs key + voice IDs, Twilio upgrade + number + Primary Compliance Profile, Gemini billing, ngrok domain, nurse phone subscribed to `NTFY_TOPIC`, real numbers in `data/patients.local.json`.
- Run locally: `make setup && make seed && make dev`; tests: `make test`; replay without keys: `make demo` → Today → Replay scenario.
