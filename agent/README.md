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

## Agent sync

```bash
# from the repo root (same as `make sync-agent`)
uv run --project backend python agent/sync_agent.py                 # secret + 5 tools + 4 agents, writes agents.lock.json
uv run --project backend python agent/sync_agent.py --dry-run       # print every rendered config; no network, no API key
uv run --project backend python agent/sync_agent.py --only es-extra_time     # one agent (tools are always synced)
uv run --project backend python agent/sync_agent.py --setup-webhook          # + HMAC post-call webhook (prints the secret once)
uv run --project backend python agent/sync_agent.py --inbound es-extra_time  # + inbound-call fallback on that variant
python3 agent/test_sync_agent.py                                     # offline rendering checks
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
