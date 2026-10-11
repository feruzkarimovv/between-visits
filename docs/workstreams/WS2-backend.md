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

---

## Site Signal plan (Sat Oct 10, late)

Added in the planning round on Sat Oct 10, late. Tasks B0–B11 above are the original Saturday plan and stay as history. This section continues the B series. Times are Sun Oct 11, ET. Checkpoints and cut rules: `docs/09-timeline-and-workstreams.md`.

Contracts are already written: `docs/03-api-contracts.md` §5 (Site Signal routes, payloads, errors, audit actions) and §6 (readiness changes at Checkpoint A); tables and file-backed models in `docs/02-data-model.md` § Site Signal; statistics in `docs/11-site-signal-sap.md`, which wins on any statistical detail. The safety path is not touched: `rules.py`, `interview.py`, `escalation.py`, `postcall.py` and the agent tools keep their behavior, and nothing in Site Signal can delay a page.

Shared files: WS0 edits `backend/` in R3 (local dates), R4 (startup guard, demo-only routes), R5 (commit fallback) and R6 (`AGENTS_LOCK_JSON`, dashboard token); WS1 V11 adds the scenario audio route in `routers/demo.py`. Agree on the order in the team chat before two agents touch the same file.

New rules for this section:
- **No numpy or scipy in `backend/`.** The backend reads `monitoring/out/*.json` and shells out to the `monitoring/` CLI only for the blind run. `services/episodes.py` is stdlib only because `monitoring/` imports it.
- **No LLM** in `services/site_signal.py`, `episodes.py` or `site_queries.py` (REQ-021 import scan).
- **No thresholds computed in the backend**; tiers and thresholds are read from `monitoring/out/`. No numeric threshold literal in `site_signal.py` (REQ-023).
- **Fail safe:** any load or schema error on Site Signal data returns 503 `site_signal_unavailable`; the UI renders every site grey, never green (REQ-025).
- **One `require_role(*roles)` helper** gates every restricted route; wrong role is 403 `wrong_role`.
- **Requirements:** add each REQ to `validation/requirements.yaml` only in the commit that adds its passing test.

### Kickoff prompt for this section

> You are continuing workstream WS2 (backend) of Between Visits. Read CLAUDE.md, docs/03-api-contracts.md §5 and §6, docs/02-data-model.md § Site Signal and § AuditEvent, docs/11-site-signal-sap.md §2–§8 and §13, and the section "Site Signal plan (Sat Oct 10, late)" at the end of docs/workstreams/WS2-backend.md. Implement B12–B15 for Checkpoint A (Sun 03:30 ET), and B16 and B16b as soon as D11 lands (B16 may land before the sap-v1 tag), then B17–B20 for Checkpoint B (06:15), then B21. Use plan mode for each task, then implement it with tests tagged @pytest.mark.req. After each task, run its acceptance check, show the output, run `make test`, and commit as "WS2-Bn: <summary>". Do not change rules.py, interview.py, escalation.py, postcall.py or agent_tools.py behavior. If a contract in docs/03 seems wrong, stop and ask instead of changing it.

### B12 · 403 for wrong role, and the `cra` role (target 02:20, Checkpoint A)
Contract: `docs/03` §6.1.
- `require_role(*roles)` dependency in `backend/app/routers/api.py`; `POST /api/drafts/{id}/investigator`, `PATCH /api/sae/{id}` and `POST /api/sae/{id}/sign` return 403 `wrong_role` (was 409) for any role but `investigator`. Missing or unknown `X-BV-Role` still means `coordinator`.
- Role enum in `backend/app/schemas.py` adds `cra`; `AuditEvent.role` accepts it.
- `backend/tests/test_roles.py`: a parametrized `(method, path, role) → status` table, tagged REQ-018. Site Signal rows are added to the same table in B17–B19 as those routes land. Add REQ-018 to `requirements.yaml` in this commit.
- **Files:** `backend/app/routers/api.py`, `backend/app/schemas.py`, `backend/tests/test_roles.py`, `validation/requirements.yaml`.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_roles.py
  ```
  Passes: coordinator → `POST /api/drafts/{id}/investigator` is 403 with `error.code == "wrong_role"`; investigator → 200.

### B13 · Audit hash chain and verify endpoint (target 02:45, Checkpoint A)
Contract: `docs/03` §6.6.
- `AuditEvent` gains `seq` (unique, contiguous from 1), `prev_hash` (64 zeros for the first event) and `hash` = sha256(`prev_hash` + canonical JSON exactly as written in §6.6).
- `write_audit` assigns all three under one process-wide lock; a `seq` collision is retried, never raised, so a safety-path write can never fail or wait on the chain (rule 5). Still append-only; the database is reseeded, so no migration.
- `GET /api/audit` returns the new fields ordered by `seq` descending. New `GET /api/audit/verify` (any role, always 200): `{ok, n_events, head_hash, first_bad_id, first_bad_seq}`.
- `backend/tests/test_audit_chain.py` (REQ-019): write 5 events, verify `ok:true`; change one row's `note` through raw SQL, verify returns `ok:false` with that event's ID and `seq`; empty log is `ok:true` with a zero head hash.
- **Files:** `backend/app/models.py`, `backend/app/audit.py`, `backend/app/routers/api.py`, `backend/app/schemas.py`, `backend/tests/test_audit_chain.py`, `validation/requirements.yaml`.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_audit_chain.py
  make demo        # replay rosa_es_urgent from Today, confirm a draft, then:
  curl -s localhost:8000/api/audit/verify | jq -e .ok
  ```
  Tests pass; the last command prints `true`.

### B14 · Export and narrative fixes, CAPA-001 (target 03:00, Checkpoint A)
Contract: `docs/03` §6.5.
- `services/export.py`: no `#` line, header on line 1; the note moves to the `X-BV-Note` response header (CORS exposes `X-BV-Note` and `Content-Disposition`); ae.csv gains the trailing `ORIGIN` column (`between_visits`); `AEOUT` from a shared `outcome_of(payload)` helper.
- `services/sae.py` uses `outcome_of()` for `reaction.outcome`; the narrative template has no doubled periods, no ".;" and no nested parentheses in the drug-class string.
- `DraftOut` gains the computed `origin: "between_visits"` (`backend/app/serialize.py`).
- `backend/tests/test_exports.py` (REQ-020): `csv.DictReader` yields `STUDYID` as the first field; `AEOUT` equals the SAE outcome for the same draft; `ORIGIN` on every row; the narrative contains none of `..`, `.;` or `((`. Add REQ-020 and CAPA-001 (`validation/capa.md`: found, root cause, correction, prevention test ID, commit).
- `docs/05-clinical-rules.md` §8: replace the planned-change note with the shipped behavior: header row first; the note in `X-BV-Note` (exact strings in `docs/03` §6.5); the trailing sponsor-defined `ORIGIN` column (SUPPAE QNAM `ORIGIN` in a real submission); `AEOUT` from `outcome_of()`.
- **Files:** `backend/app/services/export.py`, `backend/app/services/sae.py`, `backend/app/routers/api.py`, `backend/app/main.py` (CORS `expose_headers`), `backend/app/serialize.py`, `backend/tests/test_exports.py`, `validation/capa.md`, `validation/requirements.yaml`, `docs/05-clinical-rules.md` (§8).
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_exports.py
  curl -s -D - -o ae.csv localhost:8000/api/export/ae.csv | grep -i '^x-bv-note'
  python3 -c "import csv; r=csv.DictReader(open('ae.csv')); print(r.fieldnames[0], r.fieldnames[-1])"
  ```
  Tests pass; the header line prints; the last command prints `STUDYID ORIGIN`. (Run the curl in a scratch directory; do not commit the file.)

### B15 · Replay speed, scenario provenance, health.site_signal, voice-checks route (target 03:15, Checkpoint A)
Contract: `docs/03` §6.2, §6.7, §6.11.
- `POST /api/demo/replay/{scenario_id}?speed=1|2|4`: precedence query parameter, then `REPLAY_SPEED`, then 2 in demo mode; anything else 422 `validation_error`.
- `GET /api/demo/scenarios` items add `recorded`, `recorded_at`, `label` and `audio_url` (`audio_url` only when `scenarios/audio/<id>.mp3` exists). The audio route itself is WS1 V11.
- `GET /api/health` adds `site_signal: {available, sap_tag_commit, generated_at, data_origin: "SIMULATED"}`; `available` is false until `monitoring/out/signal_run.json` exists and loads.
- New `GET /api/eval/voice-checks` (any role): `eval/results/voice_checks.json` plus `data_origin: "MEASURED"`; 404 `no_voice_checks` when the file is absent.
- `backend/tests/test_demo_contract.py`.
- **Files:** `backend/app/routers/demo.py`, `backend/app/services/replay.py`, `backend/app/schemas.py`, `backend/app/routers/api.py`, `backend/tests/test_demo_contract.py`.
- **Depends on:** R4.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_demo_contract.py
  make demo     # then:
  time curl -s -XPOST 'localhost:8000/api/demo/replay/rosa_es_urgent?speed=4'
  curl -s localhost:8000/api/demo/scenarios | jq '.[0]|{recorded, label, audio_url}'
  curl -s localhost:8000/api/health | jq .site_signal.available
  ```
  The replay returns a `checkin_id` and finishes in about a quarter of the 1x time (drafts appear within about 45 s); scenario items carry the three fields; `false` before Checkpoint B.

### B16 · Pure episode builder shared with monitoring (target 03:55, Checkpoint B)
SAP §4–§6. B16 is the one piece of analysis code that may be written before the `sap-v1` tag: it implements §4–§6 exactly and touches no simulated study (SAP §1.2).
- `backend/app/services/episodes.py`, stdlib only: `build_episodes(calls, cfg)` (new or worsened grade ≥ 2 episodes of the primary terms; gap 21 days; a higher grade opens a new `worsened` episode; repeats at the same grade fold in; episode date = `DISPLAY_TZ` local date of the first call), `match(episodes, calls, site_aes, cfg)` (same subject, term through `term_synonyms`, AESTDTC in [*L_e* − `lower_tolerance_days`, episode date + `window_days`] where *L_e* is the subject's last completed call before the episode with a grade for the term below the episode's band, else episode date − `gap_days`; one-to-one greedy by distance to [*L_e*, episode date], then episode date, then `aeseq`; `origin = between_visits` and `entered_on` after the data cut excluded; SAP §5), evaluability and pending, the paged stratum, and status precedence (`paged`, `pending`, `not_evaluated`, `matched`/`unmatched`; `not_evaluated` is set by the caller that knows the leave-one-site-out rates). Every constant from `data/signal_rules.json`.
- `backend/app/content.py`: `signal_rules()` and `site_queries()` loaders.
- `backend/tests/test_episodes.py`, table-driven (≥ 14 rows): dedup across day 1/3/7 calls, worsened opens new, the gap closes an episode, incomplete calls contribute nothing, origin exclusion, `entered_on` after cut, paged beats pending, pending boundary, upper window edge (+7 matches, +8 does not), lower window edge (previous negative call − 2 matches, − 3 does not), no previous negative call (episode date − 21), worsened episode anchored on the last lower-grade call. Tag REQ-024.
- WS5 reviews the test table against the SAP; `monitoring/` imports this module and must not re-implement it.
- **Files:** `backend/app/services/episodes.py`, `backend/app/content.py`, `backend/tests/test_episodes.py`.
- **Depends on:** D11.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_episodes.py
  uv run python -c "import ast,sys; t=ast.parse(open('app/services/episodes.py').read()); print(sorted({(n.module or '').split('.')[0] for n in ast.walk(t) if isinstance(n, ast.ImportFrom)} | {a.name.split('.')[0] for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names}))"
  ```
  ≥ 14 rows pass; the import list contains only standard-library modules and `app` (`app.content`, `app.services.rules`).

### B16b · Site Signal fixtures for development (target 04:05, Checkpoint B)
- Hand-write `backend/tests/fixtures/site_signal/{signal_run,episodes,site_ae,answer_key,equity,thresholds}.json` and `summary.json` in exactly the shapes of `docs/03` §5.3 and `docs/02` § Files behind Site Signal: 20 sites, at least one `watch` site with ≥ 2 `unmatched` episodes (one Spanish quote with `translation_is_ai: true`), one `pending` and one `paged` episode, the `low_coverage` and `small_site` grey sites, and site 101 honest. Every file carries `"_about": "fixture, not a result"` and placeholder numbers only (zeros or round values); none is ever quoted.
- B17's tests run against these (`MONITORING_OUT=backend/tests/fixtures/site_signal`, `SITE_SIGNAL_SUMMARY=backend/tests/fixtures/site_signal/summary.json`, `docs/03` §6.9), and WS3 develops against them by starting `make demo` with the same two variables until WS5 commits `monitoring/out/` (~05:10). WS5 reviews the shapes.
- **Files:** `backend/tests/fixtures/site_signal/*.json`.
- **Depends on:** D11 (label keys).
- **Accept:** `python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('backend/tests/fixtures/site_signal/*.json')]; print('ok')"` prints `ok`; `grep -L 'fixture, not a result' backend/tests/fixtures/site_signal/*.json` prints nothing.

### B17 · Site Signal service and read router (target 05:25, Checkpoint B)
Contract: `docs/03` §5.1–5.3, §6.1.
- `backend/app/services/site_signal.py`: load `monitoring/out/{signal_run,episodes,site_ae,answer_key,equity}.json` and `validation/site_signal/summary.json` with `lru_cache` plus an mtime check; validate against Pydantic models (for `summary.json`, typed top-level keys from SAP §12.9 and nested blocks passed through as dicts); on any error raise the 503 path. `answer_key.json` already holds the confusion counts; the backend counts nothing. For site 101, build **MEASURED** episodes from DB Findings and Escalations through `episodes.py` (data cut = the request's local date) and list them on top of the drill-down; they never enter any statistic and never pool with simulated episodes.
- `backend/app/routers/site_signal.py`: `GET /api/sites`, `GET /api/sites/{site_id}`, `GET /api/site-signal/answer-key`, `GET /api/site-signal/validation`, `GET /api/site-signal/equity`, with roles from §6.1 and labels passed through from `data/signal_rules.json` (`labels`, including the footer template and the answer-key display labels; `en` strings flattened). Include the router in `main.py`; `monitoring_out` and `site_signal_summary` settings (`MONITORING_OUT`, `SITE_SIGNAL_SUMMARY`).
- Until WS5 commits `monitoring/out/` (about 05:10), develop and test against the B16b fixtures (`MONITORING_OUT=backend/tests/fixtures/site_signal`). Never commit dev-seed outputs.
- `backend/tests/test_site_signal_api.py`: REQ-021 (import scan of the three services), REQ-023 (`test_no_threshold_literals`: an AST check that `site_signal.py` has no numeric literal other than 0, 1 and −1), REQ-025 (missing outputs → 503; small and low-coverage sites `not_computed`; tier enum), REQ-026 (every Look or Watch row has ≥ 1 unmatched evaluable episode with a non-empty `evidence.quote`, `quote_lang`, date, `source` in {`live_call`, `replay`, `synthetic`}), REQ-030 (schema walk: `data_origin` on every object; live 101 episodes are MEASURED); role rows added to `test_roles.py`.
- **Files:** `backend/app/services/site_signal.py`, `backend/app/routers/site_signal.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/schemas.py`, `backend/tests/test_site_signal_api.py`, `backend/tests/test_roles.py`.
- **Depends on:** B12, B16, B16b (development and tests); S6 (acceptance on the committed outputs).
- **Accept:**
  ```bash
  make demo     # then:
  curl -s -H 'X-BV-Role: cra' localhost:8000/api/sites | jq -e '.run.data_origin=="SIMULATED" and (.sites|length)==20'
  curl -s -o /dev/null -w '%{http_code}\n' -H 'X-BV-Role: coordinator' localhost:8000/api/sites
  ```
  `true`, then `403`. After a Rosa replay, `GET /api/sites/101` (as `cra`) contains a MEASURED episode with status `pending` or `paged`. With `MONITORING_OUT` pointing at a missing directory, `GET /api/sites` returns 503 `site_signal_unavailable`. `cd backend && uv run pytest -q tests/test_site_signal_api.py` passes.

### B18 · Site query flow (target 05:25, Checkpoint B)
Contract: `docs/03` §5.4, §5.6, §5.7.
- `SiteQuery` table (`docs/02`); `sq_` and `sr_` documented in `backend/app/ids.py`.
- `backend/app/services/site_queries.py`: render from `data/site_queries.json` (no unfilled placeholder); episodes must be evaluable, unmatched and at that site (422 `episode_not_eligible`); only `sr_committed` is queryable (422 `run_not_queryable`); PATCH text is rejected with 422 `contains_identifier` when it contains any seeded patient's first or last name, and 422 `banned_phrase` for any entry of `banned_phrases_en`; state machine draft → sent (approve) → answered (coordinator) → closed (CRA); each step calls `write_audit` with the §5.7 action and before/after.
- Routes in `routers/site_signal.py`: `POST/GET /api/site-queries`, `GET/PATCH /api/site-queries/{id}`, `/approve`, `/respond`, `/close`. A coordinator sees `sent`, `answered` and `closed` queries at every site (the mock inbox stands in for the queried site's coordinator, `docs/03` §5.4), with an optional `site_id` filter; a draft requested by a coordinator is 404.
- `backend/tests/test_site_queries.py` (REQ-027): the full flow writes exactly `site_query.drafted`, `.edited`, `.approved`, `.answered`, `.closed`; coordinator list excludes drafts and includes a sent query for site 112; an unmatched episode at a `low_coverage` site can be cited, a `pending` one cannot (422 `episode_not_eligible`); PATCH containing "Rosa" → 422 `contains_identifier`; rendered text has no `{` and no banned phrase.
- **Files:** `backend/app/models.py`, `backend/app/ids.py`, `backend/app/services/site_queries.py`, `backend/app/routers/site_signal.py`, `backend/tests/test_site_queries.py`, `backend/tests/test_roles.py`.
- **Depends on:** B17, D11.
- **Accept:** `cd backend && uv run pytest -q tests/test_site_queries.py tests/test_roles.py` passes.
- **Cut rule (05:25):** if Checkpoint B is behind, stop here; the query flow goes to `NOT_BUILT.md` and `/sites` ships read-only.

### B19 · Blind run endpoints (target 05:40, Checkpoint B)
Contract: `docs/03` §5.5; SAP §13.
- `SignalRun` table. `run_blind(seed_label)`: if the label matches a precomputed seed, serve that file (`source: "precomputed"`); otherwise run `MONITORING_CMD --seed-label <label> --json` as an argument list (no shell) with `BLIND_RUN_TIMEOUT_S`; on failure or timeout 503 `blind_run_unavailable` with `precomputed_seeds`. `BLIND_RUN_TIMEOUT_S=0` disables the subprocess. Never build a file path from user input.
- Store the answer key, planted count and confusion from the `blind.py` output; never serialize them before reveal. Reveal is idempotent and writes `signal.blind_run.revealed` once; create writes `signal.blind_run.created`.
- Routes `POST /api/site-signal/blind-run`, `GET .../blind-run/{run_id}`, `POST .../{run_id}/reveal`, `GET /api/site-signal/blind-run-seeds`: the `DEMO_MODE` check comes before the role check (404 `demo_disabled` otherwise).
- `backend/Dockerfile`: `uv sync --project monitoring --frozen` so the image can run the CLI.
- `backend/tests/test_blind_run.py` (REQ-029): subprocess mocked; one real smoke run marked `slow`; `DEMO_MODE=0` → 404; POST response has `planted_count: null`; GET before reveal hides the key; second reveal adds no audit row.
- **Files:** `backend/app/models.py`, `backend/app/services/site_signal.py`, `backend/app/routers/site_signal.py`, `backend/app/config.py`, `backend/Dockerfile`, `backend/tests/test_blind_run.py`.
- **Depends on:** S8, B17.
- **Accept:**
  ```bash
  make demo     # then:
  time curl -s -XPOST -H 'X-BV-Role: cra' -H 'Content-Type: application/json' -d '{"seed_label":"demo-42"}' localhost:8000/api/site-signal/blind-run | jq -e '.planted_count==null'
  ```
  `true` in under 10 s locally (`demo-42` is not a precomputed label, so this exercises the subprocess); reveal returns `answer_key` and per-indicator `confusion`; with `DEMO_MODE=0` the route returns 404; `uv run pytest -q tests/test_blind_run.py` passes.

### B20 · Types, contract conformance and REQ entries (target 06:00, Checkpoint B)
- `make types` regenerates `frontend/src/lib/api-types.ts` (never hand-edited).
- `backend/tests/test_contract_routes.py`: every route listed in `docs/03` §5.2 and §6 exists in `/openapi.json` with the documented method.
- REQ-021..030 are in `validation/requirements.yaml`, each added in the commit of its first passing test. Requirements whose only tests are in `monitoring/tests/` wait for WS4 D12.
- **Files:** `frontend/src/lib/api-types.ts`, `backend/tests/test_contract_routes.py`, `validation/requirements.yaml`.
- **Depends on:** B17, B18, B19.
- **Accept:**
  ```bash
  make types && git diff --stat frontend/src/lib/api-types.ts
  cd backend && uv run pytest -q tests/test_contract_routes.py
  cd .. && make validate ARGS=--check
  ```
  The diff shows the new schemas; the contract test passes; the traceability check exits 0.

### B21 · Days before next visit, MEASURED (target 06:50, Checkpoint C)
Contract: `docs/03` §5.8.
- `GET /api/checkins/{id}` adds `days_before_next_visit` and `site_aware_basis`: next dose date after the call minus the `DISPLAY_TZ` local date the site was made aware (first acknowledgment of an escalation on this check-in, else call end). Null when the call did not complete or no later dose date is known.
- `backend/tests/test_days_before_visit.py`.
- **Files:** `backend/app/serialize.py`, `backend/app/services/checkins.py`, `backend/app/schemas.py`, `backend/tests/test_days_before_visit.py`.
- **Depends on:** R3.
- **Accept:** `cd backend && uv run pytest -q tests/test_days_before_visit.py` passes: for Rosa's replay (dose dates from the seed) the value equals the hand-computed value in the test with `site_aware_basis: "page_ack"`; a call without acknowledgment uses `call_end`; an incomplete call gives null.
