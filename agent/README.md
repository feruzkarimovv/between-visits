# agent/

ElevenLabs agent config as code (WS1). Exact API fields: `docs/04-voice-agent.md`.

| File | What |
|---|---|
| `prompt.md` | System prompt. `${RED_FLAG_LIST}` is filled at sync time from `data/red_flags.json`; `{{...}}` are ElevenLabs runtime variables |
| `tools.json` | The five webhook tools (`/agent/tools/*`, contracts in `docs/03-api-contracts.md` § 2) |
| `agent.template.json` | Shared agent config with `${...}` placeholders |
| `variants.json` | `en-standard`, `en-extra_time`, `es-standard`, `es-extra_time` (language, voice, pace settings) |
| `sync_agent.py` | Renders all of the above and upserts it in ElevenLabs |
| `agents.lock.json` | Written by the sync: `{"en-standard": "agent_...", ...}` (gitignored; the backend reads it) |
| `deployed_snapshot.json` | Written by `--snapshot` (committed): what each deployed variant runs, as model names and config hashes; agent IDs cut to the last 4 characters (`docs/02`) |
| `check_config_hash.py` | Offline CI check: the hashes of the config in git equal the snapshot, and the deployed LLM is the evaluated one |
| `voice_check.py` | Logs one real call against the live backend as a row of `eval/results/voice_checks.json` (V10): disclosure, page and acknowledgment times, grade; fills the planned call's pending row; IDs cut to the last 4 characters |
| `export_scenario.py` | Turns a real call into a recorded replay scenario `scenarios/<id>.json` (V11): whitelisted fields only, IDs cut to the last 4 characters; `--audio` saves the gitignored mp3 |

## Agent sync

```bash
# from the repo root (same as `make sync-agent`)
uv run --project backend python agent/sync_agent.py                 # secret + 5 tools + 4 agents, writes agents.lock.json
uv run --project backend python agent/sync_agent.py --dry-run       # print every rendered config; no network, no API key
uv run --project backend python agent/sync_agent.py --only es-extra_time     # one agent (tools are always synced)
uv run --project backend python agent/sync_agent.py --setup-webhook          # + HMAC post-call webhook (prints the secret once)
uv run --project backend python agent/sync_agent.py --inbound es-extra_time  # + inbound-call fallback on that variant
uv run --project backend python agent/sync_agent.py --snapshot      # read-only: writes deployed_snapshot.json
python3 agent/test_sync_agent.py                                     # offline rendering + snapshot checks
python3 agent/check_config_hash.py                                   # offline: deployed snapshot == git (CI)
```

Needs in `.env`: `ELEVENLABS_API_KEY`, `PUBLIC_BASE_URL` (https tunnel URL), `TOOL_SHARED_SECRET`, `ELEVENLABS_VOICE_ID_EN`, `ELEVENLABS_VOICE_ID_ES`; `ELEVENLABS_PHONE_NUMBER_ID` for `--inbound`. Optional: `ELEVENLABS_LLM`, `ELEVENLABS_TTS_MODEL_EN` / `ELEVENLABS_TTS_MODEL_ES` (defaults per language in `variants.json`). `--dry-run` uses placeholders for anything missing.

What a sync does:

1. Finds or creates the workspace secret `bv_tool_secret` (value `TOOL_SHARED_SECRET`) that tools send as `X-BV-Tool-Secret`.
2. Upserts the five tools by name, with URLs under `PUBLIC_BASE_URL` and the `red_flag_id` enum from `data/plan.json`.
3. Upserts `between-visits-<variant>` agents by name, sending the full config every time (first message and voicemail from `data/scripts.json`, `skip_turn` on extra-time variants, `tts.model_id` pinned).
4. Writes `agent/agents.lock.json`.

It is idempotent: running it twice leaves one secret, five tools and four agents. **Re-run it whenever `PUBLIC_BASE_URL` changes** (new tunnel URL) or after editing `prompt.md`, `tools.json`, the template, `variants.json` or the scripts/red flags in `data/`.

`--setup-webhook`: creates the `between-visits` workspace webhook (`{PUBLIC_BASE_URL}/webhooks/elevenlabs/post-call`, HMAC), turns on retries, and attaches it for `transcript`, `call_initiation_failure` and `audio`. Copy the printed secret into `.env` as `ELEVENLABS_WEBHOOK_SECRET`. ElevenLabs shows the secret only at creation; if the webhook already exists it is reused and no secret is printed.

`--inbound <variant>`: points the workspace inbound-init webhook at `{PUBLIC_BASE_URL}/webhooks/elevenlabs/inbound-init`, lets that variant take its variables and first message from the webhook, and assigns `ELEVENLABS_PHONE_NUMBER_ID` to it. Later plain syncs keep the inbound settings on whichever variant has them. Test with a real call; dashboard Preview doesn't call the inbound webhook.

## Deployed snapshot and the CI hash check (V9)

The agent LLM is pinned to the evaluated model: `variants.json` `llm` = `eval/results/latest.json` `model.agent` = `claude-sonnet-5-5`, with Claude backups from `backup_llm_order_claude`. After every sync, record what is deployed and commit it:

```bash
make sync-agent                     # push the config in git
make sync-agent ARGS=--snapshot     # read it back (GET only) -> agent/deployed_snapshot.json
python3 agent/check_config_hash.py  # must print OK and exit 0; then commit agent/deployed_snapshot.json
```

`--snapshot` reads each variant by the IDs in `agents.lock.json` (or `AGENTS_LOCK_JSON`) together with its tools. It keeps only the keys the sync sends, removes IDs, tool URLs, secret references and the `--inbound` wiring (`platform_settings.overrides`), turns integral floats back into ints (the API reads `0` back as `0.0`), and hashes canonical JSON. `check_config_hash.py` renders the same config offline exactly like `--dry-run` (without `.env` and ignoring the `ELEVENLABS_LLM` / `ELEVENLABS_TTS_MODEL_*` overrides, as in CI). It exits 1 with the differing hashes and values, or with "no deployed snapshot yet" when the file is missing. It also fails when the deployed LLM is not the evaluated model, unless the snapshot was taken with `--llm-note 'differs from evaluated model: <why>'`.

## Real calls against the live backend (V10)

Three consecutive browser calls, each with a teammate playing a synthetic patient, check the real voice path end to end against the deployed live backend: disclosure in the first turn, grading by the fixed rules, the nurse's page and its acknowledgment. Each call is logged with `agent/voice_check.py` as one row of `eval/results/voice_checks.json`. `GET /api/eval/voice-checks` serves that file labeled `MEASURED`, and the report card shows it as its own "Real voice calls" row, never pooled with the text-mode evaluation.

Until a call is logged, its row in the file is a placeholder: `"status": "pending"`, every measurement `null`, and `expected` holding the plan. The report card counts no pending row; while all three are pending it says "pending: no real calls logged yet". Nothing in the file is a result until `voice_check.py` writes it from a real call. Never type a measurement into the file by hand.

### Checklist (before the first call)

- [ ] **Consent.** Each teammate who plays a patient agrees, before the call, that the call is recorded by ElevenLabs, logged here and later exported as a transcript (V11). Serving the audio from the public demo needs their written consent.
- [ ] **Live backend.** `bv-live-api` is up (WS0 R6) with R3 and R4 deployed, `DEMO_MODE=0`, and `TOOL_SHARED_SECRET` equal to the local `.env` value (the ElevenLabs workspace secret `bv_tool_secret` holds that value). `curl -fsS $LIVE_API/api/health | jq '{ok, demo_mode, commit}'` shows `"demo_mode": false`. If the live instance is not up, run `make tunnel` and use the tunnel URL as `LIVE_API`; the calls are then logged with `--backend tunnel`.
- [ ] **Nurse phone.** The ntfy app is subscribed to the live instance's `NTFY_TOPIC` (and `NTFY_BACKUP_TOPIC`), with instant delivery and urgent notifications on.
- [ ] **Local `.env`.** `ELEVENLABS_API_KEY` is set. `BV_DASHBOARD_TOKEN` is set when the live instance has a dashboard token.
- [ ] **Agents point at the live backend** (step 1 below), and the live instance has `ELEVENLABS_WEBHOOK_SECRET` and `AGENTS_LOCK_JSON` and was redeployed.
- [ ] **Deployed config still equals git.** `make sync-agent ARGS=--snapshot && python3 agent/check_config_hash.py` prints OK. `voice_check.py` copies `agent_llm` from that snapshot.
- [ ] A quiet room, a headset for the "patient", and microphone permission in the browser.

### Procedure

1. **Point the agents at the live backend** (from the repo root):
   ```bash
   export LIVE_API=https://<bv-live-api host>     # or the tunnel URL
   PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
   ```
   If the script warns that the existing webhook points at an old tunnel URL, update the URL in the ElevenLabs dashboard (or delete the webhook and rerun to get a new secret). Put `ELEVENLABS_WEBHOOK_SECRET` (only if a new one was printed) and the contents of `agent/agents.lock.json` (as `AGENTS_LOCK_JSON`) into the `bv-live-api` environment, and redeploy.
2. **Run the dashboard locally against the live API.** Its CORS allows `http://localhost:3000`:
   ```bash
   cd frontend && NEXT_PUBLIC_API_BASE_URL=$LIVE_API NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<token> npm run dev
   ```
   Open http://localhost:3000.
3. **Make the three calls**, one after another. Start each one from Today → the patient's row → **Call in browser**. Each call creates a new check-in, and the dashboard opens its page; the check-in ID is the `ci_...` at the end of that URL. Note each call's `ci_...` ID outside git.

   | # | `--scenario` | Variant | Patient | What the patient says | Expected (the row's `expected`) |
   |---|---|---|---|---|---|
   | 1 | `james_g2_diarrhea` | `en-standard` | James (`pat_james`) | Confirms identity and consent. Diarrhea "often"; worst day "five times" (his usual is 1, so 4 over); no blood; no to every other symptom (in particular **not** dizzy on standing, which with 4 over would page `RF_DEHYDRATION`); no new medicines, no care visits, nothing else. | Provisional Diarrhea grade 2, `CTCAE5_DIARRHEA_G2`, no page |
   | 2 | `james_g3_diarrhea` | `en-standard` | James, new check-in | The same, but worst day "eight times" (7 over). | Grade 3, `CTCAE5_DIARRHEA_G3`, urgent page `RF_DIARRHEA_SEVERE`; the nurse taps Acknowledge on the phone |
   | 3 | `rosa_g3_diarrhea` | `es-extra_time` | Rosa (`pat_rosa`) | Her usual answers (persona P16): asks "¿Cómo?" once, "como siete u ocho veces" on the worst day (the agent reads it back and records the higher number, 8: 7 over her usual 1), dizzy on standing, an anti-diarrheal from the pharmacy yesterday. | First turn discloses with "del equipo"; grade 3, `CTCAE5_DIARRHEA_G3`, urgent page `RF_DIARRHEA_SEVERE` (dizziness adds `RF_DEHYDRATION` to the same page), acknowledged |

   A worst day of seven alone ("siete veces") is 6 over a usual of 1: grade 2 and no page (`docs/05` test vectors). Grade 3 needs at least 8 for Rosa or James.
4. **Log each call** after it ends and after the nurse has acknowledged the page (run it again after a late acknowledgment; the row is updated in place):
   ```bash
   uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario james_g2_diarrhea
   uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario james_g3_diarrhea
   uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario rosa_g3_diarrhea
   ```
   The conversation ID comes from the check-in (`el_conversation_id`); pass `--conversation-id conv_...` if the check-in has none. `--backend` is taken from the URL (`*.onrender.com` = `render-live`, ngrok = `tunnel`); otherwise pass `--backend render-live` or `--backend tunnel`. `--dry-run` prints the row without writing it. The script prints the measurements, the plan, and whether they match ("measured as planned" or "DIFFERS from the plan"); a difference is logged as measured.
5. **Check and commit:**
   ```bash
   jq '.calls|length' eval/results/voice_checks.json                       # 3
   jq '[.calls[]|select(.red_flag_expected)|{paged, utterance_to_page_s, page_to_ack_s}]' eval/results/voice_checks.json
   jq '[.calls[]|.disclosure_first_turn]|all' eval/results/voice_checks.json   # true
   curl -fsS -H "X-BV-Token: $BV_DASHBOARD_TOKEN" $LIVE_API/api/escalations | jq '[.[]|select(.status=="acknowledged" or .status=="resolved")]|length'
   python3 agent/test_voice_check.py
   git add eval/results/voice_checks.json agent/deployed_snapshot.json
   git commit -m "WS1-V10: three real calls against the live backend"
   ```
   V10 passes when both red-flag calls show `paged: true`, `utterance_to_page_s` ≤ 10 and a non-null `page_to_ack_s`, every first turn disclosed, and the live instance has at least 2 acknowledged escalations.

**Rules.**
- A call that goes wrong is logged as it happened. Never rerun a call to replace a bad result, and never delete a logged row. A repeat call for a scenario that is already logged is added as an extra row with `--append`. A call logged against the wrong check-in (an operator mistake, not a result) is the only row to correct by hand, and the commit message says so.
- The file keeps conversation and check-in IDs cut to their last 4 characters (`conv_...9s0t`). Keep the full IDs outside git for the V11 export.
- Never commit audio, keys, tokens or real phone numbers.

**What the script measures** (definitions in `docs/03-api-contracts.md` §6.11). It reads the conversation from ElevenLabs (`GET /v1/convai/conversations/{id}`) and the check-in from the live backend (`GET /api/checkins/{id}`). It checks that they are the same call (the same link check as V11; `--skip-link-check` overrides it) and that the check-in matches the planned variant and patient of the scenario.
- `disclosure_first_turn`: the first agent turn contains the approved first message for the call's language (`data/scripts.json`).
- `paged`: an urgent or emergency escalation was paged.
- `utterance_to_page_s`: from the start of the patient turn that triggered the page (the turn before the first tool call whose result says `escalated: true`; after a read-back, the patient's confirmation) to `paged_at`.
- `page_to_ack_s`: from `paged_at` to `acknowledged_at`.
- `grade`, `rule_id`: from the backend's finding for the planned term.

The script decides nothing itself: grades, rule IDs and pages come from the backend's fixed rules. It warns when the call's agent is not the one recorded in `agent/deployed_snapshot.json`.

### Hero call (V12)

After the freeze, on the production build:
1. `bv-live-api` runs at the freeze commit (R3 deployed). Serve the production dashboard build against it (`NEXT_PUBLIC_*` values are fixed at build time, so export them before the build), in a quiet room, with a screen recording:
   ```bash
   cd frontend && export NEXT_PUBLIC_API_BASE_URL=$LIVE_API NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<token> && npm run build && npm run start
   ```
2. Make one `es-extra_time` call with Rosa: the disclosure and the offer of a human in the first turn, "¿Cómo?" and the slow repeat, "como siete u ocho veces" and the read-back, *Diarrhea · provisional grade 3* with `CTCAE5_DIARRHEA_G3`, the nurse's phone buzzing, and the Acknowledge time on the check-in page.
3. Log it as an extra real call:
   ```bash
   uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario rosa_hero_call --red-flag-expected yes
   ```
4. Export it as a recorded scenario (next section) with `--id rec_es_hero` (`--audio` only with written consent), and label the clip "Real call; synthetic patient played by a teammate". The video source clip stays outside git.

## Export a real call as a replay scenario (V11)

After a logged real call (V10), from the repo root:

```bash
export LIVE_API=https://<live api host>   # the backend the call ran against (default: PUBLIC_BASE_URL)
# BV_DASHBOARD_TOKEN (from .env or the shell) is sent as X-BV-Token when the live instance has one
uv run --project backend python agent/export_scenario.py --conversation-id conv_... --checkin-id ci_... \
  --id rec_en_g2 --title "James, English, standard, grade 2 diarrhea (recorded)"
uv run --project backend python agent/export_scenario.py --conversation-id conv_... --checkin-id ci_... \
  --id rec_es_g3_flag --title "Rosa, Spanish, extra time, urgent diarrhea (recorded)" [--audio]
python3 agent/test_export_scenario.py   # offline: whitelist and ID checks, also over every committed recorded scenario
```

It reads the conversation from ElevenLabs (`GET /v1/convai/conversations/{id}`: transcript and tool calls with seconds from call start) and the check-in from the backend (`GET /api/checkins/{id}`: patient, day after dose, acknowledgment time), checks that they belong to the same call (`el_conversation_id` or the `checkin_id` dynamic variable; `--skip-link-check` overrides), and writes the replay format of `docs/04-voice-agent.md` with `recorded: true`, `recorded_at` (local date in `DISPLAY_TZ`), the label "Recorded real call; synthetic patient played by a teammate" and a consent note in `_about`. It never overwrites a scenario without `--force`. Offline re-export: `--conversation-file <saved conversation or post-call body> --checkin-file <saved check-in JSON>`.

**Field whitelist (CLAUDE.md rule 8).** Kept: transcript turns (`role`, `text`, `t_s`); tool calls (name, the arguments declared in `tools.json` except `checkin_id` and `conversation_id`, seconds from call start); the first urgent or emergency acknowledgment as `page_ack` (always `by: "RN on call"`, never the person's name); `call_ended` (`termination_reason` only when the agent called `end_call`) and `post_call` at the call duration; provenance (`id`, `title`, `patient_id`, `day_after_dose`, `recorded`, `recorded_at`, `label`, `_about`, `audio`, `agent_id_suffix`, `conversation_id_suffix`, the last 4 characters only). Dropped: everything else (caller identifiers, dynamic variables, phone numbers, user IDs, analysis blocks, tool results, LLM metadata, other system tools). The script checks the finished document against the whitelist before writing it, and warns (by turn number, never quoting it) about any long number in the text.

**Before committing a scenario, a human reads its whole transcript and every tool argument** to catch a real name, number or other identifier spoken off-script. If one appears, do not commit the file as is: re-record the call, or replace the words with `[redacted]` and say so in the commit message. Do not otherwise edit a recorded scenario; it must replay the way the call happened.

**Audio.** `--audio` saves `scenarios/audio/<id>.mp3` (`GET /v1/convai/conversations/{id}/audio`). The file is gitignored and never committed (the script refuses a path git would track); copy it to the demo machine by hand. With `make demo`, `GET /api/demo/scenarios/{id}/audio` serves it and the scenario list shows its `audio_url`. Serving a recorded call's audio from the public demo needs the written consent of the teammate who played the patient; without it, recorded scenarios ship transcript-only.
