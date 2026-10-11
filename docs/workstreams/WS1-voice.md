# WS1 · Voice agent (ElevenLabs + Twilio)

Owner: teammate 1. Folders: `agent/`, `scenarios/` (recordings).
Read first: `CLAUDE.md`, `docs/04-voice-agent.md` (exact API fields), `docs/03-api-contracts.md` § Agent tool endpoints, `docs/05-clinical-rules.md` § Red flags, `agent/prompt.md`, `data/scripts.json`.

## Kickoff prompt for Claude Code

> You are implementing workstream WS1 (voice agent) of Between Visits. Read CLAUDE.md, docs/04-voice-agent.md, docs/03-api-contracts.md (agent tool endpoints), docs/05-clinical-rules.md (red flags), agent/prompt.md, agent/tools.json, data/scripts.json and docs/workstreams/WS1-voice.md. Implement task V1 (agent/sync_agent.py) first: it must create or update the four agent variants from the files in agent/ and data/, using the exact ElevenLabs API fields documented in docs/04-voice-agent.md, and write agent/agents.lock.json. Use plan mode. Never put clinical wording in Python; read it from data/. Commit each task as "WS1-Vn: <summary>". Only edit files in agent/ and scenarios/.

## Tasks

### V0 · Accounts and phone (first 45 minutes, do this before coding)
- ElevenLabs: claim the free Creator month (ElevenLabs Discord → coupon channel → Start Redemption). Create an API key with Agents permissions.
- Twilio: **upgrade the account** (trial accounts don't work with ElevenLabs), buy one US local number, and **submit the Primary Compliance Profile immediately** (outbound +1 calls fail with 21216/13225 until it's approved). Steps in `docs/04-voice-agent.md` § Twilio account setup.
- Nurse pager: the teammate playing the nurse installs the ntfy app, subscribes to `NTFY_TOPIC`, enables instant delivery and urgent notifications. Send a test push with curl.
- Import the Twilio number into ElevenLabs (native integration) and put its ID in `.env` as `ELEVENLABS_PHONE_NUMBER_ID`.
- Pick voices: one warm, clear English voice and one native Spanish voice that support the low-latency multilingual model; put their IDs in `.env`.
- Start the tunnel (`make tunnel`) and confirm `PUBLIC_BASE_URL/api/health` works from your phone's browser.
- **Accept:** a test call from the ElevenLabs dashboard to your verified phone works.

### V1 · Agent config as code (target 6:00 PM, M0 gate)
- `agent/sync_agent.py` (run via `make sync-agent`):
  - builds the system prompt from `agent/prompt.md`, replacing `${RED_FLAG_LIST}` from `data/red_flags.json` at sync time (one bullet per flag: `- RF_ID: agent_description_en (examples: ...)`); `{{pace_instructions}}`, `{{language_name}}` and the patient fields stay as ElevenLabs runtime dynamic variables.
  - upserts the five tools from `agent/tools.json` by name (`POST`/`PATCH /v1/convai/tools`), after replacing `${PUBLIC_BASE_URL}`, `${TOOL_SECRET_ID}` (create the workspace secret once via `POST /v1/convai/secrets`) and `"${RED_FLAG_IDS}"`.
  - fills `agent/agent.template.json` per variant from `agent/variants.json` and upserts each agent by name (send the full config on every update). Adds `skip_turn` for extra-time variants. Pins `tts.model_id`.
  - `--setup-webhook` flag: creates the HMAC workspace webhook, enables retries, attaches it for `transcript`, `call_initiation_failure` and `audio` events, and prints the secret for `.env`.
  - builds the first message from `data/scripts.json` → `first_message` (convert `{x}` to `{{x}}`) per language.
  - creates or updates **four variants**: `en-standard`, `en-extra_time`, `es-standard`, `es-extra_time` with the settings table in `docs/04-voice-agent.md` § Variants (language, voice, TTS speed, turn timeout, LLM, temperature 0).
  - registers the server tools from `agent/tools.json` with URLs under `PUBLIC_BASE_URL` and the `X-BV-Tool-Secret` header, plus the `end_call` system tool.
  - writes `agent/agents.lock.json`: `{"en-standard": "agent_...", ...}`. Idempotent: updates existing agents by name instead of creating duplicates.
- **Accept:** running it twice leaves exactly four agents; the dashboard shows the right prompt, first message, voice and tools on each.

### V2 · First conversation in the browser (target 7:30 PM)
- With WS2's tool endpoints up (B4), start a browser test conversation from the ElevenLabs dashboard (or WS3's widget) with dynamic variables for James (English, standard).
- Check: disclosure, identity, consent, questions arrive one by one via `record_answer`, `say` is spoken verbatim, `end_call` at the end. Read the backend log for every tool call.
- **Accept:** a complete English call with no paraphrased questions and correct tool calls.

### V3 · Phone call and first red flag (target 9:30 PM, M1 gate, with WS2)
- WS2's `POST /api/patients/pat_james/checkins {"channel":"phone"}` rings your phone with the right variant.
- Answer with severe diarrhea; confirm the urgent line plays and the nurse's phone gets the urgent push.
- Tune the prompt only through `agent/prompt.md`, then `make sync-agent`.
- **Accept:** the M1 gate in `docs/09-timeline-and-workstreams.md`.

### V4 · Spanish and extra time (target 12:30 AM)
- Run Rosa (`es-extra_time`) by voice end to end. Test: long pauses (5+ seconds) don't trigger interruptions, "¿Cómo?" gets a slow verbatim repeat, read-back happens before recording, numbers in Spanish ("siete u ocho") are recorded as 8.
- Run Walter (`en-extra_time`, hard of hearing) and a caregiver path (Mike answers).
- Adjust TTS speed and turn timeout per `docs/04-voice-agent.md` until it feels patient but not sluggish.
- **Accept:** a Spanish extra-time call with zero interruptions in a 3-minute call, and the read-back behavior on every answer.

### V5 · Post-call webhook (target 12:30 AM)
- Enable the post-call webhook (transcription; audio optional) pointing at `PUBLIC_BASE_URL/webhooks/elevenlabs/post-call`; give WS2 the HMAC secret for `.env`.
- Configure data-collection fields and evaluation criteria from `docs/04-voice-agent.md` § Analysis (these are extra signals; the backend's own pipeline remains the source of truth).
- Save one real webhook body as `scenarios/fixtures/post_call_rosa_real.json` (synthetic persona, safe to commit) next to the scripted `post_call_rosa.json`, and tell WS2 if any field differs from the scripted fixture.
- **Accept:** after a call, the check-in page shows the transcript and drafts.

### V6 · Replay scenario (target 3:30 AM)
- A scripted `scenarios/rosa_es_urgent.json` already exists (built from the approved scripts). From a real Rosa call, export the sequence of tool calls (with seconds from call start), the page acknowledgment time, and the post-call transcript into the same file (format in `docs/04-voice-agent.md` § Replay format). Optionally save the call audio as `scenarios/audio/rosa_es_urgent.mp3` (gitignored; keep a copy for the demo laptop).
- **Accept:** `make demo` + Replay plays the scenario in the dashboard identically to the live call.

### V7 · Voice spot checks and the hero call (6:30–8:00 AM)
- Record the 6 voice spot checks from `docs/07-eval-and-validation.md` and score them into `eval/results/voice_checks.json` with WS4.
- Record the hero Rosa call for the video in a quiet room (with WS4).

### V7b · Inbound fallback (only if outbound is still blocked at 2 AM)
- Add `--inbound <variant>` to `agent/sync_agent.py`: set the workspace `conversation_initiation_client_data_webhook` (URL + `X-BV-Tool-Secret` secret header), enable `enable_conversation_initiation_client_data_from_webhook` and first-message override permission on that variant's agent, and assign the imported number to it (exact calls in `docs/04-voice-agent.md` § Inbound fallback).
- Run `make sync-agent ARGS="--inbound es-extra_time"`, then call the study number from Rosa's verified phone with WS2's B5b endpoint up. Rehearse "Rosa calls the study line" as the live demo.
- Test one inbound call as soon as the number is imported (even before 2 AM): if inbound is also blocked, the browser call becomes the demo.

### V8 · Stretch
- Warm transfer of the patient to the nurse with `transfer_to_number` on emergencies.
- Mid-call language switch.

---

## Site Signal plan (Sat Oct 10, late)

Added in the planning round on Sat Oct 10, late. Tasks V0–V8 above are the original Saturday plan and stay as history; a real ElevenLabs browser call already works. This section continues the V series. Times are Sun Oct 11, ET. Checkpoints and cut rules: `docs/09-timeline-and-workstreams.md`. Human actions (keys, LLM decision, patient and nurse for the calls, consent): `docs/workstreams/WS0-readiness.md` § Human actions.

Site Signal adds no calls and changes nothing the agent says: `agent/prompt.md`, `agent/tools.json`, the template and the approved wording stay as they are. WS1's job in this plan is evidence: pin and document the model that actually runs, re-verify real calls against the deployed live backend, turn real calls into labeled replay scenarios, and record the hero call. All results here are **MEASURED** and are never pooled with the text-mode evaluation.

### Kickoff prompt for this section

> You are continuing workstream WS1 (voice) of Between Visits. Read CLAUDE.md, docs/04-voice-agent.md, docs/03-api-contracts.md §6.2 and §6.9–6.11, docs/workstreams/WS0-readiness.md (§ Human actions and task R6) and the section "Site Signal plan (Sat Oct 10, late)" at the end of docs/workstreams/WS1-voice.md. A real browser call already works: do not change the prompt, tools or approved wording. Implement V9 first (it needs the team lead's LLM decision), then V10 inside its 03:30 hard time box, then V11. Never commit a full agent ID, an API key, a webhook secret, call audio or a real phone number. Run each acceptance check exactly as written, show the output, and commit as "WS1-Vn: <summary>".

### V9 · Pin and document the agent LLM (target 02:30, Checkpoint A)
- **Human decision at 02:10** (open question). Default: pin the evaluated model `claude-sonnet-5-5` (`eval/results/latest.json` `model.agent`) if ElevenLabs accepts it for agents (UNVERIFIED until the sync succeeds), with `backup_llm_order_claude` as backups. Alternative: keep the model the working call uses, record `"llm_note": "differs from evaluated model: <why>"` in the snapshot, and start a background re-evaluation on that model (`make eval` with `ELEVENLABS_LLM` set to it; WS4 rescores with D10 when it finishes).
- Set the chosen model in `agent/variants.json` `llm`, the `elevenlabs_llm` default in `backend/app/config.py`, and `ELEVENLABS_LLM` in `.env.example`.
- `agent/sync_agent.py --snapshot`: read each deployed variant back from the API (no writes when used alone) and write `agent/deployed_snapshot.json`: `captured_at`; per variant `agent_id_suffix` (last 4 characters only), `llm`, `backup_llms`, `tts_model`, `prompt_sha256`, `tools_sha256`, `config_sha256` (sha256 over the keys the sync sends, read back, with IDs, URLs and secrets removed).
- `agent/check_config_hash.py` (offline, stdlib only): renders configs exactly like `--dry-run`, compares the hashes with the snapshot, and checks that the snapshot `llm` equals `latest.json` `model.agent` or that `llm_note` is present. Exit 0 or 1 with a readable diff. Run it in CI after the agent-sync offline tests.
- README model line (WS0 R8) and the model note in `docs/04` match the snapshot.
- **Files:** `agent/variants.json`, `backend/app/config.py`, `.env.example`, `agent/sync_agent.py`, `agent/deployed_snapshot.json`, `agent/check_config_hash.py`, `agent/test_sync_agent.py` (snapshot rendering, offline), `.github/workflows/ci.yml`, `README.md` (model line), `docs/04-voice-agent.md` (model note).
- **Depends on:** human LLM decision; ElevenLabs key in `.env`.
- **Accept:**
  ```bash
  make sync-agent ARGS=--snapshot
  jq -r '[.variants[].llm]|unique|.[]' agent/deployed_snapshot.json
  jq -r .llm agent/variants.json
  python3 agent/check_config_hash.py; echo "exit=$?"
  grep -n 'claude-sonnet-5-5\|gemini' README.md
  ```
  The snapshot lists one model for all 4 variants and it equals `variants.json` `llm`; `exit=0`; the model named in the README equals the snapshot.

### V10 · Re-verify real calls against the deployed live backend (03:00–03:30, hard time box, Checkpoint A)
- **Prerequisites:** `bv-live-api` is up (WS0 R6) with R3 and R4 deployed and `TOOL_SHARED_SECRET` equal to the local `.env` value (the ElevenLabs workspace secret `bv_tool_secret` holds that value). Nurse phone subscribed to the live instance's `NTFY_TOPIC`. If the live instance is not up, use the tunnel (`make tunnel`) as `PUBLIC_BASE_URL` and record `"backend": "tunnel"`.
- **Point the agents at the live backend:**
  ```bash
  PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
  ```
  If the script warns that the existing webhook points at an old tunnel URL, update the URL in the ElevenLabs dashboard (or delete the webhook and rerun to get a new secret). A human puts `ELEVENLABS_WEBHOOK_SECRET` and the contents of `agent/agents.lock.json` (as `AGENTS_LOCK_JSON`) into the `bv-live-api` environment and redeploys.
- **Dashboard for the calls:** run it locally against the live API (its CORS allows `http://localhost:3000`); the `X-BV-Token` header comes from WS0 R6, so F10 is not needed:
  ```bash
  cd frontend && NEXT_PUBLIC_API_BASE_URL=$LIVE_API NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<token> npm run dev
  ```
- **Three consecutive calls**, a teammate playing the synthetic persona, each started from Today → "Call in browser":

  | # | Variant | Patient | Answers given | Expected |
  |---|---|---|---|---|
  | 1 | `en-standard` | James (`pat_james`) | Diarrhea with a stool count in the `CTCAE5_DIARRHEA_G2` band (`docs/05` test vectors), no blood, no dizziness on standing | Provisional grade 2, `rule_id CTCAE5_DIARRHEA_G2`, no page |
  | 2 | `en-standard` | James, new check-in | Stool count in the `CTCAE5_DIARRHEA_G3` band | Grade 3, urgent page `RF_DIARRHEA_SEVERE`, nurse acknowledges on the phone |
  | 3 | `es-extra_time` | Rosa (`pat_rosa`) | "siete veces" plus Rosa's usual answers | Disclosure with "del equipo" in the first turn, grade 3, urgent page, acknowledged |

- **Record each call** with `agent/voice_check.py --conversation-id <conv_…> --checkin-id <ci_…> --scenario <name>` (new, small, stdlib + httpx): it reads the conversation from `GET /v1/convai/conversations/{id}` (turn times) and the check-in and escalations from `$LIVE_API`, then appends one row to `eval/results/voice_checks.json` (shape in `docs/03` §6.11): `disclosure_first_turn` (the first agent turn contains the approved disclosure line for the language), `red_flag_expected`, `paged`, `utterance_to_page_s` (from the start of the patient turn that triggered the page to `paged_at`), `page_to_ack_s`, `grade`, `rule_id`. The file header holds `run_at`, `backend` (`render-live` or `tunnel`) and `agent_llm` from `agent/deployed_snapshot.json`.
- `agent/README.md`: the procedure above. `docs/07`: the real-voice stratum is reported separately (MEASURED), never pooled with text mode.
- **Files:** `agent/voice_check.py`, `eval/results/voice_checks.json`, `agent/README.md`, `docs/07-eval-and-validation.md` (real-voice stratum, only if the procedure differs from what it says).
- **Depends on:** R6 (or the tunnel), V9, R3, R4, D8 ("del equipo" in the Spanish disclosure). **Human:** teammate as patient, nurse phone.
- **Accept:**
  ```bash
  jq '.calls|length' eval/results/voice_checks.json
  jq '[.calls[]|select(.red_flag_expected)|{paged, utterance_to_page_s, page_to_ack_s}]' eval/results/voice_checks.json
  jq '[.calls[]|.disclosure_first_turn]|all' eval/results/voice_checks.json
  curl -fsS -H "X-BV-Token: $BV_DASHBOARD_TOKEN" $LIVE_API/api/escalations | jq '[.[]|select(.status=="acknowledged" or .status=="resolved")]|length'
  ```
  `3`; both red-flag calls show `paged: true`, `utterance_to_page_s` ≤ 10 and a non-null `page_to_ack_s`; `true`; at least 2 acknowledged escalations on the live instance.
- **Cut rule (03:30):** if 3 logged calls do not exist by 03:30, stop voice work. Label every demo call "recorded" or "scripted", limit statements about live voice behavior to what `voice_checks.json` shows, and use the recorded replay in the video.

### V11 · Export real calls as replay scenarios (target 03:55; Checkpoint A item that moves to C if it slips)
- `agent/export_scenario.py --conversation-id <conv_…> --checkin-id <ci_…> --id <scenario_id> [--audio]`: reads the conversation (tool calls with seconds from call start, transcript) and the escalation acknowledgment time from the live backend, and writes `scenarios/<scenario_id>.json` in the existing replay format (`docs/04` § Replay format) with `recorded: true`, `recorded_at` (local date), `label: "Recorded real call; synthetic patient played by a teammate"` and a consent note in `_about`. `--audio` saves `scenarios/audio/<scenario_id>.mp3` (gitignored, never committed).
- **Field whitelist (rule 8).** The script writes only: transcript turns (`role`, `text`, seconds from call start), tool calls (name, arguments, seconds from call start), the acknowledgment time, and the provenance fields above. `agent_id` and `conversation_id` are truncated to their last 4 characters. All other conversation metadata (caller identifiers, dynamic variables, phone numbers, user IDs, analysis blocks) is dropped. A human reads each exported transcript before it is committed, to catch a real name spoken off-script.
- Export 2 new scenarios: call 1 (English, grade 2, no page) and call 2 or 3 (red flag).
- Backend: the audio route `GET /api/demo/scenarios/{scenario_id}/audio` (`docs/03` §6.2, demo only, 404 `audio_not_found` when the file is absent); WS2 B15 adds the provenance fields and the speed parameter. Coordinate with WS2 on `backend/app/routers/demo.py`.
- Serving recorded audio from the public demo requires the teammate's written consent; without it, recorded scenarios ship transcript-only.
- **Files:** `agent/export_scenario.py`, `agent/test_export_scenario.py` (offline fixture; asserts that no key outside the whitelist is written and that IDs are truncated), `scenarios/<2 new>.json`, `backend/app/services/replay.py`, `backend/app/routers/demo.py`.
- **Depends on:** V10, B15.
- **Accept:**
  ```bash
  python3 agent/test_export_scenario.py
  make demo     # then, in another terminal:
  curl -s localhost:8000/api/demo/scenarios | jq '[.[]|select(.recorded)]|length'
  ```
  The offline test passes; `2` (at least 1); replaying a recorded scenario through the real handlers gives the same `grade` and `rule_id` as the live call recorded in `voice_checks.json`.

### V12 · Record the hero call (07:40–08:00, Packaging)
- After the 07:30 freeze, on the production build: `bv-live-api` at the freeze commit (R3 deployed), dashboard served by `npm run build && npm run start` against it, quiet room.
- One `es-extra_time` call (Rosa): disclosure and the offer of a human in the first turn; "siete veces" → provisional grade 3 via `CTCAE5_DIARRHEA_G3`; the nurse phone buzzes; the Acknowledge time is visible on the check-in page.
- Label the clip "Real call; synthetic patient played by a teammate". Export it with `agent/export_scenario.py` as a recorded scenario (the video's fallback) and add its row to `voice_checks.json`.
- **Files:** `scenarios/<hero>.json`; the video source clip stays outside git.
- **Depends on:** Checkpoint C freeze, R3 on the deployed live build, F19. **Human:** teammate as Rosa (consent on file), nurse phone, recording.
- **Accept:** the clip shows every beat above; `scenarios/<hero>.json` replays in `make demo` with the same grade, rule ID and page; WS4 D15 has the clip by 08:05.
