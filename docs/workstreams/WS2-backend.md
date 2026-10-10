# WS2 · Backend (FastAPI)

Owner: teammate 2. Folders: `backend/`, `Makefile`, `docker-compose.yml`, `.env.example`, `.github/`.
Read first: `CLAUDE.md`, `docs/01-architecture.md`, `docs/02-data-model.md`, `docs/03-api-contracts.md`, `docs/05-clinical-rules.md`, `docs/04-voice-agent.md` (sections on dynamic variables, tools and webhooks).

## Kickoff prompt for Claude Code

> You are implementing workstream WS2 (backend) of Between Visits. Read CLAUDE.md, docs/01-architecture.md, docs/02-data-model.md, docs/03-api-contracts.md, docs/05-clinical-rules.md and docs/workstreams/WS2-backend.md. Implement tasks B0 to B4 in order. Use plan mode for each task, then implement it with tests. After each task, run its acceptance check, show me the output, and commit with the message "WS2-Bn: <summary>". Do not edit files outside backend/, Makefile, docker-compose.yml, .env.example and .github/ unless a task says so. If a contract in docs/03-api-contracts.md seems wrong, stop and ask me instead of changing it.

## Stack

Python 3.12, `uv`, FastAPI, Uvicorn, SQLModel (SQLite), pydantic-settings, httpx, `google-genai`, `twilio`, python-multipart, pytest, pytest-asyncio, ruff. Layout:

```
backend/
  pyproject.toml
  app/
    main.py            app factory, CORS, lifespan (starts re-page loop), routers
    config.py          Settings (pydantic-settings) from .env
    db.py              engine, session dependency, create_all
    models.py          SQLModel tables (docs/02)
    schemas.py         request/response models (docs/03)
    ids.py             prefixed ID generator
    content.py         loads data/*.json once; text helpers
    seed.py            `python -m app.seed` resets and seeds
    audit.py           write_audit(actor, role, action, entity, before, after)
    routers/  api.py  agent_tools.py  webhooks.py  demo.py
    services/ rules.py  interview.py  escalation.py  pager.py  elevenlabs.py  gemini.py  postcall.py  sae.py  export.py  replay.py  plan.py
  tests/
```

## Tasks

### B0 · Scaffold (target 5:15 PM)
- `uv init`, dependencies above, ruff config, pytest config with marker `req(id)` registered.
- `config.py` reads every variable in `.env.example`. `main.py` serves `GET /api/health` and `/openapi.json`, CORS from `CORS_ORIGINS`.
- `Makefile` targets: `setup` (uv sync + npm install), `dev` (backend with reload on :8000 and frontend on :3000 together), `seed`, `test`, `tunnel` (`ngrok http --url=$NGROK_DOMAIN 8000`), `types` (openapi-typescript into `frontend/src/lib/api-types.ts`), `sync-agent` (`uv run python agent/sync_agent.py $(ARGS)`, e.g. `ARGS="--setup-webhook"` or `ARGS="--inbound es-extra_time"`), `eval`, `validate`, `demo` (`DEMO_MODE=1` dev).
- `docker-compose.yml` with `backend` and `frontend` services and a volume for `backend/data/`.
- **Accept:** `make setup && make dev`, then `curl localhost:8000/api/health` returns `{"ok":true,...}`; `make test` runs (0 tests is fine).

### B1 · Models and seed (target 6:00 PM)
- Tables exactly as `docs/02-data-model.md`.
- `seed.py` loads `data/study.json`, `data/plan.json`, `data/patients.json`, merges `data/patients.local.json` if present (phone numbers), and creates today's due check-ins from `dose_dates` + `schedule_days_after_dose` (status `scheduled`).
- **Accept:** `make seed` then `GET /api/patients` returns all seeded patients; `GET /api/plan/active` returns items with `text.en` and `text.es`.

### B2 · Content helpers (target 6:15 PM)
- `content.py`: `item(code)`, `question_say(code, lang, pace)` (question + spoken options from `data/symptom_items.json`, overridden item by item by `data/local/symptom_items.local.json` when that file exists), `script(key, lang, **vars)` from `data/scripts.json` with `{placeholders}`, `red_flag(id)`, `rules_for(term)`.
- **Accept:** tests (tag REQ-003) assert every plan item and follow-up has `en` and `es` text and options, every script key exists in both languages, and no `say` ever contains an unfilled `{placeholder}`.

### B3 · Rules engine (target 7:00 PM)
- `services/rules.py`, pure functions, no I/O:
  - `grade(term, answers, baseline) -> GradeResult(provisional_grade, grade_basis, rule_id, rule_text, inputs)`
  - `red_flags(answers, baseline, reported_flag_ids, day_after_dose) -> list[RedFlagHit(id, level, inputs)]`
  - `level_for(hits) -> "none" | "callback" | "urgent" | "emergency"`
- Driven entirely by `data/ctcae_rules.json` and `data/red_flags.json` (no thresholds hard-coded in Python).
- Temperature: accept °F or °C, convert to °C rounded to 0.1.
- **Accept:** table-driven tests (tags REQ-004, REQ-005) covering every rule boundary in `docs/05-clinical-rules.md` § Test vectors, all passing.

### B4 · Interview engine and agent tools (target 7:30 PM, unblocks WS1)
- `services/interview.py`: `start(checkin)`, `apply_answer(checkin, item_code, option_code, numeric, quote, lang)`, `next_step(checkin) -> Next(action, item_code, say)` as described in `docs/03-api-contracts.md` § interview engine. Follow-ups come from `data/symptom_items.json`; the condition DSL and derived inputs are in `docs/05-clinical-rules.md` § Rules engine.
- After every answer: recompute findings for that term, evaluate red flags, and if the level rises to urgent or emergency create an `Escalation` and call `escalation.page()` **before** returning to the agent.
- `routers/agent_tools.py`: `record_answer`, `report_red_flag`, `record_medication_change`, `request_human`, `set_speaker`. Check `X-BV-Tool-Secret` (401 otherwise). Always 200 with the envelope; errors return an approved re-ask or fallback `say`. Log one line per call.
- **Accept:** `tests/test_rosa_flow.py` replays Rosa's tool calls (IDENTITY yes → CALL_CONSENT yes → DIARRHEA_FREQ almost_always → DIARRHEA_STOOLS_PER_DAY 8 → report_red_flag RF_DEHYDRATION → MEDS_NEW yes → record_medication_change → ANYTHING_ELSE no) and asserts: each `say` equals the approved text; grade 3 finding; one urgent escalation created and `page()` called exactly once; queue jumps to `MEDS_NEW`; invalid option re-asks; missing secret returns 401 (REQ-005, REQ-013).

### B5 · Starting calls (target 8:30 PM)
- `services/elevenlabs.py`: read `agent/agents.lock.json` (written by WS1's sync script) to map variant `"{language}-{pace}"` → `agent_id`; `start_phone_call(checkin)` calls the ElevenLabs Twilio outbound endpoint with `dynamic_variables` (see `docs/04-voice-agent.md`); stores `el_conversation_id` and call SID; `web_session(checkin)` calls `GET /v1/convai/conversation/token?agent_id=...`, stores the returned `conversation_id`, and returns `agent_id` + `conversation_token` + dynamic variables. Exact request bodies: `docs/04-voice-agent.md`.
- Endpoints: `POST /api/patients/{id}/checkins`, `POST /api/checkins/{id}/web-started`, `POST /api/checkins/{id}/cancel`, `GET /api/checkins`, `GET /api/checkins/{id}`.
- **Accept:** with real keys, creating a phone check-in rings the patient's configured phone and the agent speaks the right language variant; in `DEMO_MODE=1` phone returns 503 `telephony_unavailable`.

### B5b · Inbound fallback endpoint (target 12:30 AM, 30 minutes of work)
- `POST /webhooks/elevenlabs/inbound-init` per `docs/03-api-contracts.md`: secret header check, caller-ID lookup, check-in creation, dynamic variables + `first_message_inbound` from `data/scripts.json`; unknown callers get defaults and `first_message_inbound_unknown`; tools called with `checkin_id: "unknown"` return `action: "close"`. Always 200, under 1 s.
- **Accept:** unit tests for known caller, unknown caller and bad secret (all 200); one real inbound call from Rosa's verified phone starts a check-in that the live page shows.

### B6 · Paging and acknowledgment (target 9:30 PM, M1 gate)
- `services/pager.py`: channel interface `page(escalation) -> page_ref`; implementations `ntfy` (default), `twilio_voice` (optional), `console` (demo mode). Page text comes from `data/scripts.json` `page_templates_en` + each red flag's `page_phrase_en`, never from an LLM, and includes level, **subject ID only (no names)**, findings, and preferred language.
- `ntfy`: JSON publish to `NTFY_SERVER` root with `topic`, `title`, `message`, `priority: 5`, and an `http` action button that POSTs `PUBLIC_BASE_URL/webhooks/ntfy/ack/{escalation_id}` with `Authorization: Bearer {ack_token}` (example in `docs/04-voice-agent.md` § Paging). Generate `ack_token` with `secrets.token_urlsafe(24)` when the escalation is created.
- `POST /webhooks/ntfy/ack/{escalation_id}`: constant-time compare of the bearer token, acknowledge with `ack_method:"push_button"`, idempotent.
- `twilio_voice` (optional, only after Twilio compliance approval): create a call to `ONCALL_NURSE_PHONE` with inline TwiML: `<Gather numDigits="1" action="{PUBLIC_BASE_URL}/webhooks/twilio/page-ack?escalation_id=..." method="POST" timeout="10"><Say>...</Say></Gather><Say>No input received. We will call again.</Say>`.
- `POST /webhooks/twilio/page-ack`: validate signature (`RequestValidator`, URL = `PUBLIC_BASE_URL` + path + query), `Digits=="1"` → acknowledge.
- Re-page loop (asyncio task started in lifespan, every 10 s): open escalations with no ack after `ACK_TIMEOUT_SECONDS` → re-page; after 2 re-pages also page the backup (`NTFY_BACKUP_TOPIC`, or `BACKUP_INVESTIGATOR_PHONE` with `twilio_voice`).
- **Accept:** a test with a fake pager and fake clock covers page, ack, re-page and backup (REQ-005, REQ-006); manual check: an urgent answer puts a push on the nurse's phone within 10 s and tapping Acknowledge turns the dashboard green.

### B7 · Post-call webhook and pipeline (target 12:30 AM)
- `POST /webhooks/elevenlabs/post-call`: verify HMAC (`ElevenLabs-Signature: t=..,v0=..`, see `docs/04-voice-agent.md`), 401 on failure, 200 immediately, background processing; idempotent by `conversation_id`. Handle `post_call_transcription`, `call_initiation_failure` (check-in → `no_answer`/`failed`) and `post_call_audio` (save MP3 under `scenarios/audio/` when the check-in is flagged for recording).
- `services/postcall.py`: store transcript turns with `t_s`; fill `t_s` on answers by matching quotes; call `gemini.extract()`, `gemini.safety_net()`, `gemini.translate()`; merge; create drafts with evidence; escalate safety-net misses; mark check-in `completed`; audit.
- `services/gemini.py` uses `google-genai>=2.29` `client.models.generate_content(model=..., config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=PydanticModel))` and reads `resp.parsed` (None means validation failed: retry once, then fail safe). Models: `GEMINI_MODEL_FAST` (`gemini-3.5-flash-lite`) for extraction and translation, `GEMINI_MODEL_LONG` (`gemini-3.8-flash`, thinking level `low`) for the safety net, narratives and PDFs. Don't set `temperature` (ignored from Gemini 3.6 on) and never prefill model turns (400). Every function has a deterministic fake used in tests and in `DEMO_MODE`.
- **Accept:** posting `scenarios/fixtures/post_call_rosa.json` with a valid signature (and fake Gemini) creates: AE Diarrhea (grade 3, evidence in Spanish with translation label), AE Dizziness, CM loperamide; `scenarios/fixtures/post_call_missed_red_flag.json` (chest pressure mentioned, no tool call) creates an emergency escalation with reason `post_call_safety_net` (REQ-008, REQ-009, REQ-012). Both fixtures are already in the repo, unsigned; tests sign them with a test secret.

### B8 · Review, SAE, sponsor, exports, audit (target 3:30 AM)
- Draft endpoints (confirm, PATCH edit, reject, investigator). Investigator actions require `X-BV-Role: investigator` (409 otherwise).
- `services/sae.py`: create on serious with `aware_at` = earliest acknowledgment of a linked escalation, else confirmation time; `due_at = aware_at + 24h`; payload per `docs/05-clinical-rules.md` § Sponsor notification; narrative from `gemini.draft_narrative()` labeled AI draft (template fallback); sign; send; sponsor inbox with valid-case checks.
- Exports: AE/CM CSV with SDTM-style columns from `docs/05-clinical-rules.md`; SAE JSON.
- Audit list endpoint; eval and validation JSON passthrough.
- **Accept:** API tests: every mutation writes an audit event (REQ-010); serious AE → report with `due_at - aware_at == 24h` (REQ-011); CSV columns match the spec.

### B9 · Demo replay (target 4:30 AM, M3 gate)
- `services/replay.py`: load `scenarios/<id>.json` (sequence of `{"t": seconds, "type": "tool"|"page_ack"|"post_call", "body": {...}}`), create a check-in with `channel:"replay"`, and run each event through the same service functions at its time offset. `DEMO_MODE=1` uses fake Gemini and console pager.
- **Accept:** with no API keys in `.env`, `make demo` + `POST /api/demo/replay/rosa_es_urgent` runs the full story in the UI (REQ-015).

### B10 · CI (target 4:30 AM)
- `.github/workflows/ci.yml` per `docs/07-eval-and-validation.md` § CI.
- **Accept:** CI green on main.

### B11 · Stretch: protocol-to-plan
- `POST /api/plan/propose` with Gemini PDF input and a Pydantic schema whose item codes and red-flag IDs are enums built from `data/`. Return citations with page numbers. `POST /api/plan/{id}/approve`.
