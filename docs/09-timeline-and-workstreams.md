# 09 · Timeline, workstreams and risks

All times Eastern. Devpost submission is due **Sun 10:00 AM** (aim 9:30). Hacking ends 11:30 AM. Judging from 12:30 PM.

## Workstreams

| WS | Owner | Folders | Task file |
|---|---|---|---|
| WS1 Voice | teammate 1 | `agent/`, `scenarios/` (recording) | `docs/workstreams/WS1-voice.md` |
| WS2 Backend | teammate 2 | `backend/`, `Makefile`, `docker-compose.yml`, `.env.example`, `.github/` | `docs/workstreams/WS2-backend.md` |
| WS3 Frontend | teammate 3 | `frontend/` | `docs/workstreams/WS3-frontend.md` |
| WS4 Data, eval, story | teammate 4 | `data/`, `eval/`, `validation/`, `README.md`, deck, video | `docs/workstreams/WS4-data-eval-story.md` |

## Milestones (gates)

| Milestone | Target | Gate (demo it to the team before moving on) |
|---|---|---|
| **M0 Skeleton** | Sat 6:30 PM | `make dev` runs backend + frontend; `make seed` loads data; Today page lists patients from the API; `make sync-agent` creates the 4 agent variants; a browser call talks to the agent; tunnel URL reaches `/api/health`. |
| **M1 First red flag** | Sat 10:00 PM | A real English phone call: the agent asks the diarrhea question, `record_answer` hits the backend, the rules produce grade 3 and an urgent escalation, the nurse's phone gets the urgent push, tapping Acknowledge turns the escalation green, and the live page shows all of it. |
| **M2 Rosa works** | Sun 1:30 AM | Spanish + extra-time call end to end with follow-ups and read-back; caregiver and request-human paths; post-call webhook → transcript, extraction, safety net, labeled translations → drafts; review queue confirm/edit/reject with audit. |
| **M3 Closed loop + proof** | Sun 4:30 AM | Investigator seriousness + SAE report + 24-hour clock + sponsor inbox; `make eval` runs all 20 personas and writes `latest.json`; report card page renders it with the equity split; validation pack + CI green; `rosa_es_urgent` replay scenario works in `DEMO_MODE=1`. |
| **M4 Freeze** | Sun 7:00 AM | No new features. Bug bash, clean-clone test on a second laptop, README complete, record the 6 voice spot checks and the hero call, screenshots. |
| **M5 Ship** | Sun 9:30 AM | Video uploaded, deck exported, Devpost submitted with track + 2 superlatives + all contributors. |

Sleep: WS1 and WS3 sleep 1:30–4:00 AM; WS2 and WS4 sleep 4:00–6:30 AM. Whoever is awake owns the open escalation of the build.

## Dependency order (what unblocks what)

1. **WS2 B1–B3** (models, seed, rules engine) unblock everything. Target 6:00 PM.
2. **WS2 B4** (tool endpoints + interview engine) unblocks WS1's first real conversation. Target 7:30 PM. Until then WS1 tests with the browser widget and a prompt-only flow.
3. **WS3** builds against fixture JSON copied from `docs/03-api-contracts.md` until the endpoints exist, then switches to the real API and runs `make types`.
4. **WS4** starts immediately: data files are already in `data/`; build the eval harness against WS2's service functions as they land; README and deck in parallel.

## Working with Claude Code

- Each teammate works in their **own clone** of the GitHub repo, with their own Claude Code session. Start by pasting the kickoff prompt from your workstream file.
- Use **plan mode** for any task touching more than two files. Read the plan, then let it implement.
- One task = one commit: `WS2-B3: rules engine + tests`. Pull and rebase before every push. Push small and often.
- Never let Claude change a contract silently. If an endpoint, schema or data file format must change: update `docs/03-api-contracts.md` (or the data schema) first, tell the team, then implement.
- Each task file lists an acceptance check. Run it and paste the output in the team chat at each milestone.
- Keep `CLAUDE.md` current when you add a command or a convention.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Twilio trial accounts don't work with ElevenLabs phone calls | Very high | **Upgrade Twilio in the first hour** (decide as a team now). |
| Outbound +1 calls blocked until Twilio's Primary Compliance Profile is approved (can take days) | High | Submit the profile in the first hour. Until cleared: browser calls for testing, and the inbound fallback (patient calls the study line) for the live demo. The nurse page uses ntfy push and never depends on Twilio. |
| Gemini free tier too small for the evaluation (reported ~20 requests/day on 3.8 Flash) | High | Link billing and prepay $5 (Tier 1) in the first hour. |
| Licensed content leaks into the public repo (PRO-CTCAE wording, MedDRA codes) | Medium | Our own question wording; local-only override folder; WS4's data validator fails on known licensed strings. |
| ElevenLabs credits run out | Medium | Claim the free Creator month now. Develop with short calls, run the eval in text mode, use replay for rehearsals. |
| Venue Wi-Fi or tunnel fails during judging | Medium | Phone hotspot; `DEMO_MODE` replay; practice the switch. |
| Gemini rate limits during eval | Medium | Concurrency 2, backoff, cache transcripts; run a 10-persona subset if needed; a paid key if available. |
| LLM paraphrases approved wording | Medium | Short `say` strings, explicit verbatim rule in the prompt, the approved-wording metric, and fix prompts until ≥ 95%. |
| Spanish speech recognition mishears numbers | Medium | Read-back confirmation before recording; numbers also stored with the verbatim quote. |
| Agent talks over slow speakers | Medium | Extra-time variant with slower voice and longer turn timeout; test with P06 and P16 by voice early (M2). |
| Scope creep | High | Cut list below; freeze at 7:00 AM. |
| Merge conflicts | Medium | Folder ownership; contracts first; small commits. |

## Cut list (cut from the top when a milestone slips)

1. Protocol-to-plan (already stretch)
2. Patient timeline sparklines
3. Re-page to backup contact (keep single re-page)
4. AI-drafted SAE narrative (use a template)
5. ElevenLabs simulate mode in the eval
6. Caregiver path (keep the persona, accept a known miss)

**Never cut:** disclosure line, approved wording, red-flag paging with acknowledgment, evidence on drafts, review confirm, the report card (even partial, with honest numbers), README, video.

## Stretch list (only between M3 and M4, only if ahead)

Protocol-to-plan with Gemini; warm transfer of the patient straight to the nurse (`transfer_to_number`); mid-call language switch; deployed demo URL in demo mode; Tiger Data and .tech domain extras (ask the MLH table first whether they count against the two-superlative limit).
