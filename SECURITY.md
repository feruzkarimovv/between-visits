# Security policy

Between Visits is a hackathon prototype (HackRU Fall 2026). It runs on **synthetic data only** and is not a medical device. Data flows, controls in place, known gaps and the compliance gap table are in [`docs/privacy-security.md`](docs/privacy-security.md).

## Supported scope

| In scope | Out of scope |
|---|---|
| The code on the default branch: `backend/`, `frontend/`, `agent/`, `eval/`, `validation/`, the Makefile, Dockerfiles and CI | Third-party services we call (ElevenLabs, Anthropic, ntfy.sh, Twilio, the hosting provider): report those to the vendor |
| The public demo instance (`DEMO_MODE=1`, replay only, synthetic data) and the private live instance | Denial of service and load testing against either instance |
| Secrets, real phone numbers or real personal data found anywhere in the repository or its history | Findings that need real patient data: there is none, by design (CLAUDE.md rule 8) |

There are no releases and no backports. Fixes go to the default branch.

## Reporting a problem

- **Do not post secret values, phone numbers or exploit details in a public place.** Describe where the problem is (file, commit, endpoint) and what it allows.
- While the repository is private, contact the repository owner directly on GitHub, or open an issue with the `security` label (`docs/backlog.md` §1) that names the file or endpoint without the sensitive value.
- If the repository is made public later, the owner turns on GitHub private vulnerability reporting first, and reports go through the repository's **Security** tab.
- This is a volunteer hackathon team: there is no bug bounty and no response-time commitment.

## How secrets are handled

- **Where secrets live.** Only in `.env` on a developer machine (gitignored; copy `.env.example`, which holds placeholders only) and in the hosting provider's environment settings, entered by a person (`sync: false` variables on the live instance). Never in git, images, logs, issues or chat.
- **Which values are secret.** `TOOL_SHARED_SECRET`, `ELEVENLABS_API_KEY`, `ELEVENLABS_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TWILIO_AUTH_TOKEN`, `BV_DASHBOARD_TOKEN`, and the ntfy topic names `NTFY_TOPIC` and `NTFY_BACKUP_TOPIC` (anyone who knows a topic can read its pages). Real phone numbers are treated the same way: they live only in `.env` and `data/patients.local.json`.
- **Gitignored local files that must never be committed or copied into an image:** `.env`, `data/patients.local.json` (real phone numbers), `data/local/` (a study's licensed item wording), `agent/agents.lock.json` (deployed agent IDs), `scenarios/audio/*.mp3` (call recordings), `backend/data/*.db` (the database).
- **Placeholders.** Committed examples use `+1XXXXXXXXXX`, numbers in the fictional 555 exchange, `change-me…` strings and `bv-change-me…` topics.
- **Startup guard.** Outside demo mode the backend refuses to start when `TOOL_SHARED_SECRET` is empty, still the `.env.example` placeholder, or shorter than 24 characters, and it warns when `NTFY_TOPIC` is shorter than 16 characters. Generate a secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
- **Scanning.** `make secret-scan` runs gitleaks over the full git history (`--log-opts="--all"`, redacted output) and `validation/scan_numbers.py`, which flags any NANP-shaped phone number outside the 555 exchange and prints only its last 4 digits. The CI `gitleaks` job runs the same target. The latest result is recorded in `validation/secret-scan.md`.

## If a secret or real number reaches git

1. Rotate or revoke the credential at the provider first. Treat it as exposed even if the commit was never pushed.
2. Tell the team lead.
3. Decide together whether to rewrite history. Nobody rewrites shared history alone.
4. Re-run `make secret-scan` and record the result in `validation/secret-scan.md`.

Changing the repository's visibility is a separate human decision. Run `make secret-scan` on the final history before that decision.
