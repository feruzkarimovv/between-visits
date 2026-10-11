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
