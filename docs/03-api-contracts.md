# 03 · API contracts

Single source of truth for every HTTP interface. The backend implements these with Pydantic models in `backend/app/schemas.py`; the frontend generates TypeScript types from `GET /openapi.json` with `make types`. JSON is snake_case. Errors use `{"error": {"code": "string", "message": "string"}}` with a matching HTTP status.

Headers sent by the dashboard on every request: `X-BV-User`, `X-BV-Role` (demo identity, see `02-data-model.md`).

---

## 1. Dashboard API (`/api`)

### Health and reference data

`GET /api/health` → `{"ok": true, "demo_mode": false, "version": "0.1.0", "commit": "abc1234"}`

`GET /api/study`
```json
{"id":"std_demo01","nct_id":"NCT02760498","title_short":"Open-label PD-1 immunotherapy study in advanced skin cancer (example)","drug_class":"anti-PD-1 monoclonal antibody (immunotherapy)","masking":"open_label","site_id":"101","site_name":"Hillside Cancer Center (fictional)","active_plan_id":"plan_v1"}
```

`GET /api/plan/active`
```json
{"id":"plan_v1","version":1,"status":"approved","approved_by":"Jess Kim","approved_at":"2026-10-10T20:00:00Z",
 "schedule_days_after_dose":[1,3,7],
 "items":[{"item_code":"DIARRHEA_FREQ","term":"Diarrhea","attribute":"frequency","text":{"en":"...","es":"..."},"source":"study_team"}],
 "red_flags":[{"id":"RF_DIARRHEA_SEVERE","level":"urgent","label_en":"7 or more stools a day over baseline, or blood in stool"}],
 "source":"seed","source_citations":[]}
```

Stretch: `POST /api/plan/propose` (multipart `file`=protocol PDF) → a `draft` plan with `source_citations`; `POST /api/plan/{plan_id}/approve` → approved plan, previous plan becomes `superseded`. Proposed items must be codes that exist in `data/symptom_items.json` and red flags must exist in `data/red_flags.json`; anything else is rejected (Gemini output is constrained with enums).

### Patients and check-ins

`GET /api/patients` → list of
```json
{"id":"pat_rosa","subject_id":"101-007","first_name":"Rosa","last_name":"Méndez","age":74,"language":"es","pace":"extra_time","hearing":"typical","caregiver_name":"Lucía","caregiver_relation":"daughter","next_due":{"day_after_dose":3,"date":"2026-10-11"},"last_checkin_status":"completed","open_escalations":0}
```

`GET /api/patients/{patient_id}` → patient + `checkins` (newest first) + `timeline` (per term, one point per check-in: `{"term":"Diarrhea","points":[{"checkin_id":"...","date":"...","provisional_grade":3,"answer":"almost_always"}]}`) + `dose_dates`.

`GET /api/checkins?date=2026-10-11` → check-ins scheduled or run that day, plus patients due that day without a check-in yet (`"status":"due"`).

`POST /api/patients/{patient_id}/checkins`
```json
// request
{"channel":"phone","day_after_dose":3}
// response 201 (phone)
{"checkin":{"id":"ci_8KD2...","status":"dialing","channel":"phone","language":"es","pace":"extra_time","agent_variant":"es-extra_time"}}
// response 201 (web): the browser starts the session itself
{"checkin":{"id":"ci_...","status":"dialing","channel":"web"},
 "web_session":{"agent_id":"agent_...","conversation_token":"<from GET /v1/convai/conversation/token>","conversation_id":"conv_...","dynamic_variables":{"checkin_id":"ci_...","patient_first_name":"Rosa","study_team_name":"...","language_name":"Spanish","pace_instructions":"...","caregiver_name":"Lucía"}}}
```
Errors: 409 `checkin_in_progress` if the patient already has a live check-in; 503 `telephony_unavailable` in demo mode for `phone`.

`POST /api/checkins/{checkin_id}/web-started` `{"conversation_id":"conv_..."}` → `{"ok":true}` (confirms the browser session started; the token endpoint already returned the conversation ID, so this mainly flips status to `in_progress`).

`POST /api/checkins/{checkin_id}/cancel` → check-in with `status:"cancelled"`.

`GET /api/checkins/{checkin_id}` (polled every 1 s while live)
```json
{"checkin":{"id":"ci_...","status":"in_progress","language":"es","pace":"extra_time","speaker":"patient","started_at":"...","interview_state":{"current":"DIZZY_ON_STANDING","asked":["CALL_CONSENT","DIARRHEA_FREQ","DIARRHEA_STOOLS_PER_DAY"],"escalated":true}},
 "patient":{"id":"pat_rosa","subject_id":"101-007","first_name":"Rosa","language":"es","pace":"extra_time","caregiver_name":"Lucía"},
 "answers":[{"id":"ans_...","item_code":"DIARRHEA_STOOLS_PER_DAY","numeric_value":8,"unit":"per_day","verbatim_quote":"Como siete u ocho veces al día","quote_lang":"es","reporter":"patient","source":"live_tool","created_at":"..."}],
 "findings":[{"term":"Diarrhea","provisional_grade":3,"grade_basis":"rule","rule_id":"CTCAE5_DIARRHEA_G3","rule_text":"...","inputs":{"stools_over_baseline":7},"red_flag_ids":["RF_DIARRHEA_SEVERE"],"escalation_level":"urgent"}],
 "escalations":[{"id":"esc_...","level":"urgent","status":"open","paged_at":"...","seconds_open":21,"page_target_name":"RN on call","repage_count":0}],
 "drafts":[],
 "transcript":[]}
```

### Escalations

`GET /api/escalations?status=open` → list (each includes `patient` summary and `seconds_open`).
`POST /api/escalations/{id}/ack` `{}` → escalation with `status:"acknowledged"`, `ack_method:"dashboard"`, `acknowledged_by` from `X-BV-User`.
`POST /api/escalations/{id}/resolve` `{"note":"Nurse spoke with patient, sent to ED for IV fluids"}` → `status:"resolved"`.

### Drafts (review queue)

`GET /api/drafts?status=draft&kind=AE` → list of DraftEntry (see `02-data-model.md`) with `patient` summary.

`PATCH /api/drafts/{id}` `{"payload":{"provisional_grade":2,"onset_date":"2026-10-07"},"note":"Patient corrected count on nurse call"}` → updated draft (still `draft`). Audit `draft.edited` with before/after.

`POST /api/drafts/{id}/confirm` `{"note":null}` → `status:"confirmed"`. Audit `draft.confirmed`.

`POST /api/drafts/{id}/reject` `{"reason":"Duplicate of earlier report"}` → `status:"rejected"`.

`POST /api/drafts/{id}/investigator` (role must be `investigator`; draft must be a confirmed AE)
```json
{"is_serious":true,"seriousness_criteria":["hospitalization"],"relatedness":"possibly_related","sign":true}
```
→ `{"draft":{...},"sae_report":{"id":"sae_...","status":"draft","aware_at":"...","due_at":"..."}}` (`sae_report` only when serious). Allowed `seriousness_criteria`: `death`, `life_threatening`, `hospitalization`, `disability`, `congenital_anomaly`, `important_medical_event`. Allowed `relatedness`: `not_related`, `unlikely_related`, `possibly_related`, `probably_related`, `related`.

### Serious-event reports and mock sponsor

`GET /api/sae` · `GET /api/sae/{id}` → SAEReport with `seconds_until_due`.
`PATCH /api/sae/{id}` `{"narrative_final":"...","payload":{...}}` (investigator).
`POST /api/sae/{id}/sign` (investigator) → `status:"signed"`.
`POST /api/sae/{id}/send` → `status:"sent"`, sets `sent_at` and `sponsor_received_at` (same instant, mock).
`GET /api/sponsor/inbox`
```json
[{"sae_id":"sae_...","received_at":"...","due_at":"...","on_time":true,"study":"NCT02760498","site":"101","subject_id":"101-007",
  "event_term":"Diarrhea","seriousness_criteria":["hospitalization"],"provisional_grade":3,"relatedness":"possibly_related",
  "valid_case_checks":{"identifiable_patient":true,"identifiable_reporter":true,"suspect_product":true,"adverse_event":true},
  "narrative":"..."}]
```

### Exports, audit, evaluation, validation

`GET /api/export/ae.csv` and `/api/export/cm.csv` → confirmed drafts only, SDTM-style columns (see `docs/05-clinical-rules.md`).
`GET /api/export/sae/{id}.json` → CIOMS-style JSON.
`GET /api/audit?entity_id=ci_...&limit=200` → newest first.
`GET /api/eval/latest` → contents of `eval/results/latest.json` (404 `no_eval_run` if missing).
`GET /api/validation/latest` → contents of `validation/summary.json`.

### Demo controls (enabled when `DEMO_MODE=1` or `APP_ENV=dev`)

`GET /api/demo/scenarios` → `[{"id":"rosa_es_urgent","title":"Rosa, Spanish, extra time, urgent diarrhea","duration_s":140}]`
`POST /api/demo/replay/{scenario_id}` → `{"checkin_id":"ci_..."}`; the replay runs in the background through the same service functions.
`POST /api/demo/reset` → reseeds the database.

---

## 2. Agent tool endpoints (`/agent/tools`)

Called by the ElevenLabs agent as server tools. Every request must carry `X-BV-Tool-Secret`. `checkin_id` is injected from the conversation's dynamic variables (exact mechanism in `docs/04-voice-agent.md`); the LLM never has to remember it.

All tools return HTTP 200 with this envelope, even on validation errors:

```json
{"ok": true,
 "next": {"action": "ask", "item_code": "DIARRHEA_STOOLS_PER_DAY", "say": "<approved text in the call's language>"},
 "escalated": false}
```

- `next.action`: `ask` (say `say` verbatim, then listen) or `close` (say `say` verbatim, then call `end_call`).
- `say` is always approved text assembled by the backend from `data/scripts.json` and `data/symptom_items.json` (or the local official-item override). The agent may put one short neutral acknowledgment before it ("Thank you" / "Gracias"), nothing else.
- On a bad option code: `{"ok": false, "error": "invalid_option", "next": {"action":"ask","item_code":"<same>","say":"<approved re-ask listing the options>"}}`.
- On an internal error: `{"ok": false, "error": "internal", "next": {"action":"ask" or "close","say":"<approved fallback line>"}}` and the backend escalates to `callback` so a human follows up.

### The interview engine

The backend owns the question order. At check-in creation it builds `interview_state.queue`:

1. `IDENTITY` (the agent's first message, from `data/scripts.json` `first_message`, discloses the AI and asks "May I speak with {first name}?"; nothing about the study or health is said before identity is confirmed)
2. `CALL_CONSENT` (`say` = `consent_question`, or `caregiver_allowed` after `set_speaker`)
3. the plan's `items` in order (the first one is prefixed with `intro_questions`)
4. `MEDS_NEW` (+ `MEDS_DETAIL` if yes), `CARE_VISIT` (+ `CARE_VISIT_DETAIL` if yes), `ANYTHING_ELSE`
5. closing line (`closing`, or `closing_after_escalation` if an urgent escalation happened)

`IDENTITY` = `no` (wrong person) → `say` = `wrong_person_close`, `action:"close"`, no health information recorded.

Follow-up items are inserted right after their parent when the parent's answer triggers them (rules in `data/symptom_items.json` → `followups`). Rules engine runs after every answer:

- **urgent** red flag → page now, set `escalated=true`, drop remaining symptom items and their follow-ups, keep the flow items (`MEDS_NEW`, `CARE_VISIT`, `ANYTHING_ELSE`); `say` = urgent line + next question.
- **emergency** red flag → page now, `say` = emergency line + closing line, `action:"close"`.
- `CALL_CONSENT` = `no` or `later` → create a `callback` escalation, `say` = `consent_later`, `action:"close"`.
- A red flag reported while an escalation at the same or higher level is already open is added to that escalation (no second page) and `say` = `added_to_page` + the current question.
- `MEDS_DETAIL` is answered with `record_medication_change`; `CARE_VISIT` = `yes` creates a `callback` escalation and a `NURSE_TASK`; a non-empty `ANYTHING_ELSE` creates a `NURSE_TASK`.

Every tool body also carries `conversation_id` (injected from `system__conversation_id`). Exact ElevenLabs tool definitions: `agent/tools.json`.

### `POST /agent/tools/record_answer`
```json
{"checkin_id":"ci_...","conversation_id":"conv_...","item_code":"DIARRHEA_STOOLS_PER_DAY","option_code":null,"numeric_value":8,"unit":"per_day",
 "verbatim_quote":"Como siete u ocho veces al día"}
```
- `item_code` is optional; when missing, the answer applies to `interview_state.current`.
- `item_code` must equal `interview_state.current` or any already-asked item (corrections allowed). Otherwise `error:"unexpected_item"` and `say` re-asks the current question.
- `option_code` must be one of the item's options, or `unknown` (patient doesn't know or declines).
- For ranges ("seven or eight") the agent sends the higher number and keeps the exact words in `verbatim_quote`.
- Temperature answers: `numeric_value` plus `unit` `"celsius"` or `"fahrenheit"`; the backend converts to °C. Temperature not taken: `option_code:"not_measured"`.

### `POST /agent/tools/report_red_flag`
Use any time the person mentions something on the red-flag list, even outside a question.
```json
{"checkin_id":"ci_...","red_flag_id":"RF_CHEST_PAIN","verbatim_quote":"me duele el pecho","language":"es"}
```
`red_flag_id` is an enum of the study's active red flags. The backend never second-guesses a report: it escalates at the flag's level (false alarms are acceptable; misses are not) and returns the urgent or emergency `say`.

### `POST /agent/tools/record_medication_change`
```json
{"checkin_id":"ci_...","description":"Imodium from the pharmacy, started yesterday","verbatim_quote":"Tomé Imodium de la farmacia ayer","language":"es"}
```
Creates or appends a CM draft. Returns `next` (usually the following queue item).

### `POST /agent/tools/request_human`
```json
{"checkin_id":"ci_...","reason":"medical_question","verbatim_quote":"¿Debo tomar más Imodium?","language":"es"}
```
`reason`: `wants_person` \| `medical_question` \| `distress` \| `other`. Creates a `callback` escalation and a `NURSE_TASK` draft. `say` is the approved deferral line ("That's a question for your nurse. I'll pass it on and they'll call you.") followed by the current question again, unless the person asked to stop, in which case `action:"close"`.

### `POST /agent/tools/set_speaker`
```json
{"checkin_id":"ci_...","speaker":"caregiver","relation":"daughter"}
```
If the patient's `caregiver_may_answer` is true: continue, and later answers are stored with `reporter:"caregiver"`. If false: `say` = approved "I can only complete this check-in with {name}..." line and `action:"close"` with a `callback` escalation.

---

## 3. Webhooks (`/webhooks`)

### `POST /webhooks/elevenlabs/post-call`
ElevenLabs `post_call_transcription`, `call_initiation_failure` (set the check-in to `no_answer` or `failed`) and optionally `post_call_audio` (save the MP3 for replay) events. Payload shapes in `docs/04-voice-agent.md`. Verify the HMAC header with `ELEVENLABS_WEBHOOK_SECRET` (algorithm in `docs/04-voice-agent.md`); reject with 401 on mismatch. Return 200 within 1 s and run the post-call pipeline in a background task. Idempotent by `conversation_id`. Find the check-in by `conversation_id`, falling back to the `checkin_id` dynamic variable in the payload.

### `POST /webhooks/elevenlabs/inbound-init` (inbound fallback)
Called by ElevenLabs before the agent answers an inbound call. Header `X-BV-Tool-Secret` must match; `called_number` must equal `TWILIO_FROM_NUMBER`. Body: `{"caller_id","called_number","agent_id","call_sid","conversation_id"}`. Match `caller_id` to a patient's `phone_e164`; create a check-in (`channel:"phone_inbound"`, `status:"in_progress"`, `el_conversation_id` from the body); return `{"type":"conversation_initiation_client_data","dynamic_variables":{...},"conversation_config_override":{"agent":{"first_message":"..."}},"user_id":"<subject_id>"}`. **Always 200**, even on a bad secret or unknown caller (then return the unknown-caller defaults and log a warning). Must respond in under 1 s. Full shapes in `docs/04-voice-agent.md` § Inbound fallback.

### `POST /webhooks/ntfy/ack/{escalation_id}` (default pager)
Called by the **Acknowledge** button on the nurse's ntfy push notification, with header `Authorization: Bearer <escalation.ack_token>`. Valid token → acknowledge (`ack_method:"push_button"`, `acknowledged_by` = `ONCALL_NURSE_NAME`) → `{"ok":true}`; already acknowledged → `{"ok":true}` (idempotent); bad token → 401.

### `POST /webhooks/twilio/page-ack?escalation_id=esc_...` (optional pager)
Twilio `<Gather>` action (form-encoded: `Digits`, `CallSid`, ...). If `Digits == "1"`: acknowledge (`ack_method:"phone_keypress"`) and respond with TwiML `<Response><Say>Acknowledged. Thank you.</Say></Response>`. Otherwise re-prompt once. Validate `X-Twilio-Signature` against `PUBLIC_BASE_URL` + path + query.

### `POST /webhooks/twilio/page-status?escalation_id=esc_...` (optional)
Twilio status callback. Logs `no-answer` / `busy` / `failed`; the re-page loop handles retries.

---

## 4. Additions made during implementation (Sat Oct 10, evening)

Backward-compatible additions; `GET /openapi.json` is the exact schema (`make types`).

- `GET /api/health` also returns `app_env` and `pager_channel` (`console` when `DEMO_MODE=1` or no `NTFY_TOPIC`).
- `GET /api/checkins/{id}` also returns `current_question` (the approved text currently being asked, or null) and `checkin.postcall_status` (`processing` | `done` | `failed`).
- Escalations also return `red_flag_labels`, `seconds_to_ack` (paged → acknowledged), `backup_paged_at` and a `patient` summary. `Escalation.reason` can also be `care_visit` (patient reported an ER / urgent care / other doctor visit; callback level). `GET /api/escalations` accepts `checkin_id` and a comma-separated `status`.
- Drafts also return `sae_report_id` and a `patient` summary. `GET /api/drafts` also filters by `checkin_id`; `status` and `kind` accept comma-separated values. NURSE_TASK categories: `medical_question`, `wants_person`, `distress`, `other`, `care_visit`, `anything_else`. CM payloads may carry `as_reported_en` (the agent's description) when post-call extraction normalized `medication_name`.
- `GET /api/checkins` items: `{"id": "ci_..." | null, "status", "channel", "day_after_dose", "started_at", "patient": PatientSummary, "open_escalations"}`.
- `GET /api/patients/{id}` also returns `phone_on_file` (true when a real number came from `data/patients.local.json`), `baseline` and `notes`; never the phone number itself.
- Sponsor inbox items also return `seconds_before_deadline` and the full `report` payload.
- `POST /api/sae/{id}/send` requires a signed report (409 `not_signed`). Editing a signed report returns it to `draft` (re-sign needed).
- `GET /api/demo/scenarios` items also return `patient_id`. Replay timing scales with env `REPLAY_SPEED` (default 1.0). Scenario files may carry `translations_en` (scripted quote → English) used only by the fake translator in demo mode, and `summary_en`.
- `POST /agent/tools/*` unknown or `"unknown"` `checkin_id`: `{"ok": false, "error": "unknown_checkin", "next": {"action": "close", "say": <wrong_person_close>}}`. Internal errors close with `fallback_error` and escalate (urgent + page for `report_red_flag` and symptom answers, callback otherwise).
