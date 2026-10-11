# Privacy and security

Between Visits is a hackathon prototype. Every patient, call and event is **synthetic**, and it is not a medical device. This page says where data goes, which controls exist, what is missing, and which compliance and regulatory questions are still open. It is an engineering summary, not a legal or compliance assessment. How to report a problem and how secrets are handled: [`SECURITY.md`](../SECURITY.md).

**UNVERIFIED** marks a statement we have not checked against the vendor's documentation or the regulatory text.

## 1. Data the system holds

| Data | Where | Notes |
|---|---|---|
| Synthetic patients: name, age, sex, subject ID, language, pace, baseline, dose dates, phone number | `data/patients.json` (committed) → SQLite | Committed phone numbers are placeholders in the fictional 555 exchange. |
| Real phone numbers (teammates who play patients or the nurse) | `.env`, `data/patients.local.json` | Gitignored. `GET /api/patients/{id}` returns only `phone_on_file: true/false`, never the number. |
| Call transcripts, answers, findings, escalations, drafts, serious-event reports, audit events | SQLite file `backend/data/app.db` | Gitignored. `make seed` and `POST /api/demo/reset` delete and rebuild it. |
| Call audio (MP3 from the ElevenLabs `post_call_audio` webhook) | `scenarios/audio/` | Gitignored; never committed. Served on a public instance only with the speaker's written consent (`docs/03` §6.2). |
| Licensed official symptom items (optional, a registered study's own copy) | `data/local/` | Gitignored (CLAUDE.md rule 9). |
| Deployed agent IDs | `agent/agents.lock.json`, or `AGENTS_LOCK_JSON` on the host | Gitignored. |

## 2. Data flows

| Recipient | What it receives | When | What it never receives |
|---|---|---|---|
| **ElevenLabs** (voice agent) | Call audio in both directions and the live transcript. Per call: the patient's first name, caregiver name, study team name, check-in ID, language and pace instructions (dynamic variables), and the subject ID as `user_id`. Agent tool calls send answers and verbatim quotes back to our backend. After the call it posts the transcript and, optionally, the audio to our webhook. | Every live call (browser calls today). Not in `DEMO_MODE=1`. | Last name, phone number on browser calls, the API key (it stays on the backend; the browser gets a per-call conversation token). |
| **The agent's LLM provider, through ElevenLabs** | The conversation text, sent by ElevenLabs to the model pinned for the agent (`agent/variants.json`, V9). | Every live call. | Anything we do not send to ElevenLabs. Which sub-processors see the text under our ElevenLabs plan: UNVERIFIED. |
| **Anthropic** (post-call text) | Extraction and safety net: the numbered transcript, both speakers, so the agent's identity question carries the patient's first name. Translation: the patient quotes to translate. Narratives: the serious-event report JSON (subject ID, initials, age, sex, event, provisional grade, seriousness, relatedness, concomitant medications, the investigator's demo name) plus the evidence quotes. | After each live call, and when an investigator creates a serious-event report. Never in `DEMO_MODE=1` or tests (deterministic fake). | Audio, phone numbers, last names outside what was said in the call. |
| **Google Gemini** (alternative provider) | The same content as the Anthropic row. | Only when a Gemini key is set and either `LLM_PROVIDER=gemini`, or `LLM_PROVIDER=auto` with no Anthropic key. | Same as the Anthropic row. |
| **ntfy** (push to the nurse's phone, public `ntfy.sh` server by default) | Push title and text built from `data/scripts.json` `page_templates_en`: subject ID, level, the red-flag phrase with the values that triggered it (for example a temperature or stools over baseline), and the preferred language. The **Acknowledge** action carries the backend URL and that escalation's ack token. | Each urgent or emergency page and re-page. Console only in `DEMO_MODE=1`. | Names, phone numbers, transcripts. Topic names act as shared secrets: anyone who knows the topic can read the pages. |
| **Twilio** (optional) | Patient phone number and call audio for phone calls; the nurse's or backup investigator's number and the page text for a "press 1" page call. | Only when phone calling or `PAGER_CHANNEL=twilio_voice` is configured. Phone calling is not connected for the hackathon. | Anything on browser calls. |
| **Sponsor safety inbox** (mock, inside the app) | A CIOMS-style report: subject ID, initials, age, sex, country, event term, provisional grade, seriousness, relatedness, suspect product **by class only**, concomitant medications, narrative, reporter (the investigator's demo name), aware and due times. | When an investigator signs and sends. | Full names, phone numbers, transcripts. |
| **Sponsor Site Signal views, site queries, site inbox** (Checkpoint B) | Subject IDs, terms, episode dates, provisional grades and quotes, each labeled with its data origin (SIMULATED, MEASURED or MIXED). A CRA edit that contains any patient's first or last name is refused with 422 `contains_identifier`. | Sponsor and CRA screens; query flow between CRA and coordinator. | Names and phone numbers (`docs/10` §7.6). |
| **Hosting provider** (Render, planned in R6) | The containers, the SQLite file on the container disk, logs, and the live secrets as environment variables entered by a person. | While deployed. | The gitignored local files of §1, which `.dockerignore` keeps out of the images (R5). |
| **GitHub** | Source code, specs, synthetic seed data, eval transcripts of simulated patients. | Every push. | Secrets and real phone numbers (`make secret-scan`, R1). |

Application log lines carry IDs (check-in, escalation, conversation, subject) rather than names or phone numbers. Exception messages and stack traces are logged as they come and are not filtered.

## 3. Controls in place

"In place" means the control is in the code with a passing test. Rows marked **Checkpoint A** describe the contract in `docs/03` §6 for a task that lands at Checkpoint A; the row is in place once its requirement shows PASS in [`validation/traceability.md`](../validation/traceability.md), or, for a row without a requirement, once the task's acceptance check is recorded as passed in [`PROGRESS.md`](../PROGRESS.md).

| Control | What it does | Where | Proof | Status |
|---|---|---|---|---|
| Tool secret | Every `/agent/tools/*` call must carry `X-BV-Tool-Secret`, compared in constant time; otherwise 401. `inbound-init` checks the same secret and answers a bad one with the unknown-caller defaults. | `backend/app/routers/agent_tools.py`, `routers/webhooks.py` | `test_rosa_flow.py::test_missing_or_bad_secret_is_401` | In place |
| HMAC post-call webhook | `ElevenLabs-Signature` (`t=…,v0=…`) is an HMAC-SHA256 of `t.body` with `ELEVENLABS_WEBHOOK_SECRET`. A mismatch, a missing secret or a timestamp older than 30 minutes gets 401. | `backend/app/routers/webhooks.py` | `test_postcall.py::test_signature_verification`, `test_bad_signature_401` | In place |
| Ack tokens | Each escalation gets a random token (`secrets.token_urlsafe(24)`). The ntfy Acknowledge button must send it as a bearer token, compared in constant time; otherwise 401. | `routers/webhooks.py` (`/webhooks/ntfy/ack/{id}`) | `test_paging.py::test_ntfy_ack_requires_token` | In place |
| Twilio signatures | `X-Twilio-Signature` is validated on the page-ack and page-status callbacks (see the `APP_ENV=dev` gap in §4). | `routers/webhooks.py` | `test_paging.py::test_twilio_page_ack_requires_signature` (a valid signature is accepted; the rejection path has no test) | In place |
| CORS | Browsers may call the API only from `CORS_ORIGINS`; no credentials. CORS does not stop non-browser clients. | `backend/app/main.py` | Fresh-clone probe (`docs/workstreams/WS0-readiness.md`) | In place |
| Startup guard (R4) | With `DEMO_MODE=0` the backend exits non-zero when `TOOL_SHARED_SECRET` is empty, the `.env.example` placeholder or shorter than 24 characters, and warns when `NTFY_TOPIC` is shorter than 16 characters. | `backend/app/config.py` `assert_safe_startup()` | REQ-017, `test_security_guards.py` | In place |
| Demo-only routes (R4) | `/api/demo/*` (replay, reset) returns 404 `demo_disabled` unless `DEMO_MODE=1`; `APP_ENV=dev` no longer opens them. | `backend/app/routers/demo.py` | REQ-017, `test_security_guards.py` | In place |
| Pages carry subject IDs only | Page text comes only from approved templates and red-flag phrases, never from an LLM or a name field. | `backend/app/services/pager.py`, `data/scripts.json` | `test_paging.py::test_page_message_has_subject_id_only` | In place |
| No external calls in demo mode | `DEMO_MODE=1` uses the deterministic LLM fake and the console pager, and refuses to start calls. | `services/llm.py`, `config.py` (`effective_pager_channel`), `services/elevenlabs.py` | Fresh-clone demo run with empty keys (`docs/workstreams/WS0-readiness.md`) | In place |
| 403 for the wrong role (B12) | `require_role(*roles)` gates every role-restricted route; any other role gets 403 `wrong_role` (`docs/03` §6.1). | `backend/app/routers/api.py` | REQ-018, `test_roles.py` | Checkpoint A |
| Audit hash chain (B13) | Each `AuditEvent` stores `seq`, `prev_hash` and `hash = sha256(prev_hash + canonical JSON)`. `GET /api/audit/verify` walks the chain and reports the first event that no longer matches (`docs/03` §6.6). Rows are append-only today. | `backend/app/audit.py` | REQ-019, `test_audit_chain.py` | Checkpoint A |
| Optional dashboard token (R6) | When `BV_DASHBOARD_TOKEN` is set, every `/api/*` request except `GET /api/health` needs `X-BV-Token`, else 401 `invalid_token`. Set only on the private live instance (`docs/03` §6.8). | `backend/app/main.py` | `test_dashboard_token.py`; R6 acceptance on a local live-config container (`curl` returns 401, `docs/deploy.md` §8) | In place (the live instance is not deployed yet) |
| Secrets out of git and images (R1, R5) | Secrets live only in `.env` and host environment variables. `make secret-scan` runs gitleaks over the full history plus a phone-number scan; `.dockerignore` keeps `.env` and the gitignored local files out of images. | `.gitleaks.toml`, `validation/scan_numbers.py`, `.dockerignore` | `validation/secret-scan.md`, R5 acceptance | Checkpoint A |

## 4. Known gaps

| Gap | Effect | Mitigation today | Tracked |
|---|---|---|---|
| **No real authentication or RBAC.** `X-BV-User` and `X-BV-Role` are demo identity headers the client chooses. | Anyone who can reach `/api/*` can claim any role and read patient names, transcripts and reports, or start calls. `make tunnel` puts that backend on the public internet. | Public demo instance holds synthetic data only. The private live instance sets the dashboard token (R6), but a `NEXT_PUBLIC_` value ships in the browser bundle, so it keeps casual traffic out and is not authentication. | BL-18 |
| **No rate limiting** on `/agent/tools/*`, `/webhooks/*` or `/api/*`. | Brute-force attempts on the secrets are not slowed; call starts on an exposed live API can run up vendor usage. | Long random secrets and tokens. | BL-19 |
| **SQLite, single instance.** | No backups, no replication, no app-level encryption at rest. On the host the container disk is ephemeral: state resets on restart. | Synthetic data; reseeding is expected. | BL-19 |
| **Dev-only npm audit findings.** | `npm audit` in `frontend/` reports 5 high findings, all in the lint toolchain (`eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → `braces`). `npm audit --omit=dev` reports 0 (checked 2026-10-11). Python dependencies have not been audited. | Lint tools are not in the production image. | BL-19 |
| **Audit chain not anchored outside the database.** | Someone with write access who rewrites every row from the edited one onward is not detected. | `GET /api/audit/verify` catches a single edited row (B13). | BL-19 |
| **ntfy topics are shared secrets.** | Anyone who knows a topic reads its pages (subject ID and finding) and can press Acknowledge, because the action carries the ack token. Delivery on the public server is best effort. | Long random topic names; the startup warning; the dashboard acknowledgment and the re-page loop are the backstop. | BL-19 |
| **Twilio signatures are not enforced under `APP_ENV=dev`** (the `.env.example` default): an invalid signature is accepted with a warning log line. | A forged page-ack could acknowledge an escalation on a dev backend exposed through the tunnel. The route is active whatever `PAGER_CHANNEL` says, and escalation IDs are readable through `/api/*`. | The live instance runs `APP_ENV=prod` (R6). | BL-19 |
| **The public demo instance is open.** | Anyone can start replays and `POST /api/demo/reset`, which rebuilds the database. | Synthetic data only; a reset restores the seed. | Accepted for the demo |
| **No retention or deletion policy.** | Transcripts, audio and reports stay until the database is reseeded or the files are deleted by hand. | Synthetic data only. | BL-19 |

## 5. Compliance gap table

Nothing below has been assessed by a qualified reviewer. "Not assessed" means exactly that: no claim of compliance or non-compliance.

| Framework or item | What the prototype has | Status |
|---|---|---|
| HIPAA Privacy and Security Rules | Synthetic data only; no real patient data is handled. No access controls, audit of reads, encryption policy or breach process. | Not assessed |
| Processor agreements (BAAs or equivalent) with ElevenLabs, Anthropic, ntfy, Twilio and the hosting provider | None in place. | Not assessed; availability per vendor UNVERIFIED |
| ElevenLabs BAA availability | `docs/04-voice-agent.md` records a BAA as Enterprise-plan only; not confirmed with the vendor. | UNVERIFIED |
| ElevenLabs data-retention settings (transcripts, audio, zero-retention options) | `agent/sync_agent.py` sets no retention option, so the account default applies; that default is not checked. | UNVERIFIED |
| 21 CFR Part 11: electronic signatures | "Sign" on a serious-event report is a button gated by the demo role header; no unique credentials, no identity check at signing. | Not assessed |
| 21 CFR Part 11: audit trail | Append-only `AuditEvent` rows with before/after values, actor and role for every human action; hash chain and verify endpoint (B13). Actors are demo identities, not authenticated users. | Not assessed |
| 21 CFR Part 11: system validation | A mini validation pack (`validation/requirements.yaml` → tests → `validation/traceability.md`), CAPA log and the simulated-patient evaluation. This is not a computer system validation. | Not assessed |

## 6. Regulatory limits

- **Shadow mode only.** Between Visits produces drafts that the site confirms, edits or rejects; nothing is final without a human (CLAUDE.md rule 7). Site Signal compares a patient-reported reference stream with the site's own AE records on simulated multi-site data; a flag is a reason to look, not a finding, and a CRA approves every query (`docs/10` §7.1–§7.3).
- **Investigator control of ePRO source data** (EMA/INS/GCP/112288/2023, the EMA guideline on computerised systems and electronic data in clinical trials): how its expectations apply to a call-based patient stream, and to a sponsor-side copy of that stream, is an open question. UNVERIFIED.
- **Sponsor safety awareness from an unfiltered patient stream:** a sponsor that sees patient symptom reports before the site assesses them may become aware of possible serious or unexpected events, with possible IND safety-reporting implications (21 CFR 312.32). A real deployment needs a defined process. Open question, UNVERIFIED.
- **AI voice calls:** consent and calling rules for automated AI-voice calls (TCPA) need legal review before calling real people. UNVERIFIED (`docs/backlog.md`).
- **Not a medical device and not validated for clinical use.** The agent gives no medical advice (CLAUDE.md rule 3); provisional grades come from fixed CTCAE v5 rules and need clinician review. The study drug is referred to by class only (anti-PD-1).

## 7. Before any real patient data

All of these must be closed first (CLAUDE.md rule 8):

1. Real authentication, per-site scoping and roles from an identity provider (BL-18).
2. Production hardening: managed database with backups and retention, rate limits, external anchoring of the audit chain head, processor agreements, and a HIPAA and Part 11 gap assessment by a qualified reviewer (BL-19).
3. A regulatory memo on the sponsor-side patient stream (BL-20).
4. A fresh `make secret-scan` on the final history before any change to the repository's visibility.
