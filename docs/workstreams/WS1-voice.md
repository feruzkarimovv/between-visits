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
