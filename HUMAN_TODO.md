# HUMAN_TODO

Steps that need a person. Everything around them is done; each item says exactly what to run or click. Ordered by priority as of Sun Oct 11, end of the build (most urgent first).

1. **Submit Devpost and record the video (by 11:30 ET today).** Submit first, polish after (edits stay open until 11:30). Text: the README sections (What it does, Results, What it gets wrong) or the draft the build session gave you; gallery: `docs/screenshots/*.png` (1280x800; crop to 1200x800 for 3:2); deck: `docs/pitch/deck.pdf`; storyboard and recording checklist: `docs/08-demo-and-pitch.md`. Record on the production build (`make demo DEMO_PROD=1`), label any replay "Scripted", upload to YouTube unlisted, paste the link. Track: one track only (Social Good); prizes: at most two superlatives (Regeneron: Improve Clinical Trials, Use of ElevenLabs). Public demo link: https://bv-demo-web.onrender.com (Render, Free instances; the first load after about 15 idle minutes takes up to a minute, so open it shortly before judges look). The temporary laptop tunnel used earlier is shut down.

2. **Give judges access without making the repository public.** Invite them as collaborators (GitHub > Settings > Collaborators). Do not change visibility yet: the first commit on `main` (07f2773) still contains the study drug's brand name and product code in `data/` (removed on this branch in 6da3b18, but history keeps it). See the history item below before any visibility change.

3. **Before any change of repository visibility (for example a public repository link in item 1's Devpost entry): remove the product name from git history (CLAUDE.md rule 8).** Git history before 6da3b18 (commit 07f2773, the build kit, the root commit) still holds the product brand name and product code: `python3 data/validate_data.py --guard-file` over `git log -p --all` reports 23 denylisted-token lines, added in 07f2773 (`data/red_flags.json` 9, `data/study.json` 1, `docs/05-clinical-rules.md` 1) and removed in 6da3b18 (`data/`) and in d88dc99 and edc3991 (`docs/05`). `origin/main` still holds them at its tip (d29585e) until item 5's merge, and `origin/claude/vibrant-fermi-6vwzie` holds the history too. The product-name guard that `make test` runs covers the working tree only, and `make secret-scan` does not look for product names, so both pass. The build session may not force-push (`docs/KICKOFF.md`), so this needs a person. Choose one:
   - **Publish a fresh repository from a squashed snapshot** (keeps this private repository, its `sap-v1` tag and GitHub Release unchanged as the pre-registration record):
     ```bash
     git fetch origin && mkdir "$TMPDIR/bv-public"
     git archive origin/main | tar -x -C "$TMPDIR/bv-public"      # after item 5's merge
     cd "$TMPDIR/bv-public" && git init -b main && git add -A && git commit -m "Between Visits: snapshot of between-visits main"
     ```
   - **Or rewrite history** with `git filter-repo` and force-push every branch and tag. This changes every commit sha, including the `sap-v1` tag commit 68838978… from which the evaluation seed is derived (`docs/11` §1.3), so `sap_tag_commit` and `eval_seed` in every committed Site Signal output, the REQ-022 test and the GitHub Release (`docs/11` §17 C1) would no longer match. Decide it with the team (`SECURITY.md`).

   Then, in the repository that is to be made visible, re-run the product-name guard over its whole history and the secret scan, and record both in `validation/secret-scan.md`:
   ```bash
   git log -p --all > "$TMPDIR/history.patch"
   python3 data/validate_data.py --guard-file "$TMPDIR/history.patch"   # expect "product names: 0 hits in 1 files"; today: 23 FAIL lines
   rm "$TMPDIR/history.patch"
   make secret-scan                                                      # expect "no leaks found" and "numbers: 0 hits"
   ```
   The guard prints only the patch line number of a hit, never the matched text.

4. **Post the `sap-v1` tag sha in the Devpost draft or the organizer channel, and log the link in docs/11 §17 (S1; docs/11 §1.2 step 6).** The tag, the GitHub Release (the external timestamp) and the beacon are done (docs/11 §17 rows C1, C2); only this post is left. Never edit the docs/11 §1.5 `sap-v1` row or `monitoring/seed_beacon.json`.
   1. Post this text in the Devpost draft (project description or an update) or in the event's organizer channel, then copy the post's link and note the post time in UTC:
      ```
      Between Visits Site Signal SAP v1 is frozen: sap-v1 = 68838978bb305e0f730d30e5cbf3c00bceca5a25
      https://github.com/feruzkarimovv/between-visits/releases/tag/sap-v1
      ```
   2. Update the branch first (`cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only`). In `docs/11-site-signal-sap.md` §17, add a row with the next free C number (C5 unless more rows have landed) directly above the empty placeholder row `| | | | | | | | | |`, which stays last. Fill in `<n>`, `<HH:MM>`, `<post link>` and `<UTC time>`:
      ```
      | C<n> | 2026-10-11 <HH:MM> ET | Commit `SAP v1: organizer timestamp link (docs/11 §17)` | §1.2 step 6 | clarification | Tag sha `68838978bb305e0f730d30e5cbf3c00bceca5a25` and the Release link posted at <post link> at <UTC time>. This post is later than the 10-minute window after the tag push and later than the beacon round time 2026-10-11T08:48:00Z (row C2); the GitHub Release in row C1 (`publishedAt` 08:38:10Z) is the external timestamp that is earlier than the round. | §1.2 step 6 puts both external-timestamp links in a §17 clarification and requires §17 to say when one is not earlier than the beacon round. | No | None on any result. |
      ```
   3. Check, commit and push the branch:
      ```bash
      uv run --project monitoring python -m bvsignal.seed --check-frozen     # expect: frozen inputs: OK
      make test
      git add docs/11-site-signal-sap.md && git commit -m "SAP v1: organizer timestamp link (docs/11 §17)" && git push origin site-signal-build
      ```
   If the team lead reviews the SAP later, the sign-off and any findings go in their own §17 rows the same way (docs/11 §1.2 step 4).

5. **Merge `site-signal-build` into `main` with a merge commit (not squash or rebase).** The `sap-v1` tag must stay an ancestor of the evaluation outputs (REQ-022), so the branch history must be kept as is:
   ```bash
   git fetch origin
   git checkout main && git pull --ff-only
   git merge --no-ff origin/site-signal-build -m "Merge site-signal-build: Site Signal + readiness"
   make test && git push origin main
   ```
   Or on GitHub: open a pull request from `site-signal-build` to `main` and use **Create a merge commit** (not "Squash and merge", not "Rebase and merge").

6. **Record the V12 hero call (V12; after the freeze and item 10).** Full procedure: `agent/README.md` § "Hero call (V12)".
   1. With `bv-live-api` at the freeze commit, in a quiet room with a screen recording running:
      ```bash
      cd frontend && export NEXT_PUBLIC_API_BASE_URL=$LIVE_API NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<token> && npm run build && npm run start
      ```
   2. Make one `es-extra_time` call as Rosa (written consent on file) showing: the disclosure plus the offer of a human, "¿Cómo?" and the slow repeat, "como siete u ocho veces" and the read-back, *Diarrhea · provisional grade 3* with `CTCAE5_DIARRHEA_G3`, the nurse phone buzzing, and the Acknowledge time on the check-in page.
   3. Log it as an extra real call:
      ```bash
      uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario rosa_hero_call --red-flag-expected yes
      ```
   4. Export it with `agent/export_scenario.py --id rec_es_hero` as in item 11 (`--audio` only with written consent), and label the clip "Real call; synthetic patient played by a teammate". The video source clip stays outside git.

7. **Done for the public demo pair (Sun Oct 11, 11:42 ET): `bv-demo-api` https://bv-demo-api.onrender.com and `bv-demo-web` https://bv-demo-web.onrender.com, Free instances, branch `site-signal-build`, created in the Render dashboard; README updated. Still open: the private live API (`bv-live-api`) and, optionally, paid always-on instances.** Deploy to Render: public demo pair and private live API (R6; `render.yaml`, full guide in `docs/deploy.md`).** R6 is integrated on `site-signal-build` and verified locally only (token tests, a live-config container returning 401 without `X-BV-Token`, `render.yaml` parses to the three services). Dashboard labels are as of Oct 2026 and may have moved (UNVERIFIED). Never type a secret into a file in the repository.
   1. **`render.yaml` must be on `main`**: the Blueprint and every auto-deploy read `main`. Do item 5 (merge `site-signal-build` into `main`) first.
   2. **Billing.** Sign in at https://dashboard.render.com with GitHub → **Workspace Settings → Billing** → add a payment method, and approve three always-on `starter` instances (`bv-demo-api`, `bv-demo-web`, `bv-live-api`; pricing UNVERIFIED).
   3. **GitHub app access.** Render dashboard → **New → Blueprint → Connect a repository** → on GitHub's Render app page choose the account that owns `feruzkarimovv/between-visits` → **Only select repositories** → add `between-visits` → **Install** (or **Save**). Do not change the repository's visibility.
   4. **Create the Blueprint.** Select `between-visits`; Blueprint name `between-visits`, branch `main`, Blueprint path `render.yaml`. When Render asks for the `sync: false` values of `bv-live-api`, paste:
      - `TOOL_SHARED_SECRET` = the exact value in the local `.env` (it must equal the ElevenLabs workspace secret `bv_tool_secret`);
      - `BV_DASHBOARD_TOKEN` = a new value; keep a copy for sub-step 8:
        ```bash
        python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | pbcopy
        ```
      - `ELEVENLABS_API_KEY`, `ELEVENLABS_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, `NTFY_TOPIC`, `NTFY_BACKUP_TOPIC` = the local `.env` values;
      - `AGENTS_LOCK_JSON` = the lock file on one line, copied without printing it (run in the repo root):
        ```bash
        python3 -c 'import json; print(json.dumps(json.load(open("agent/agents.lock.json")), separators=(",", ":")))' | pbcopy
        ```
      Then click **Deploy Blueprint** (or **Apply**).
   5. **After three green deploys, check the cross-service URLs** on each service's **Environment** tab: `bv-demo-api` `CORS_ORIGINS` = the `bv-demo-web` URL; `bv-demo-web` `NEXT_PUBLIC_API_BASE_URL` = the `bv-demo-api` URL; `bv-live-api` `PUBLIC_BASE_URL` = its own URL. If any is empty or wrong, set the `https://….onrender.com` URL by hand. For `bv-demo-web`, then use **Manual Deploy → Clear build cache & deploy** (the URL is inlined at build time).
   6. **Point the agents at the live API**, from a laptop with the full `.env`:
      ```bash
      LIVE_API=https://bv-live-api.onrender.com     # the real URL from sub-step 5
      PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
      ```
      If it warns that the webhook points at an old tunnel, edit the webhook URL in ElevenLabs (workspace **Settings → Webhooks**) to `$LIVE_API/webhooks/elevenlabs/post-call`. If a new `ELEVENLABS_WEBHOOK_SECRET` is printed or `agent/agents.lock.json` changed, update those two values in **`bv-live-api` → Environment → Save**, then rebuild and deploy.
   7. **Acceptance**, with `main` checked out at the deployed commit:
      ```bash
      DEMO_API=https://bv-demo-api.onrender.com   # the real URLs from sub-step 5
      DEMO_WEB=https://bv-demo-web.onrender.com
      LIVE_API=https://bv-live-api.onrender.com
      curl -fsS $DEMO_API/api/health | jq -e '.demo_mode==true and .commit=="'$(git rev-parse --short HEAD)'"'   # true
      curl -fsS $LIVE_API/api/health | jq -e '.demo_mode==false and .browser_calls_enabled'                       # true
      curl -s -o /dev/null -w '%{http_code}\n' $LIVE_API/api/patients                                               # 401
      ```
      Then, in an incognito window on `$DEMO_WEB`: **Replay** a scenario → confirm the drafts → switch to Investigator → assessment → SAE sign → send → the report appears in the sponsor inbox.
   8. **Live calls** run from a local dashboard against `bv-live-api`. Put these in `frontend/.env.local` (gitignored), then start it:
      ```bash
      # frontend/.env.local
      NEXT_PUBLIC_API_BASE_URL=https://bv-live-api.onrender.com
      NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<the BV_DASHBOARD_TOKEN from sub-step 4>
      ```
      ```bash
      cd frontend && npm run dev      # http://localhost:3000
      ```
      Do not merge to `main` during the calls: each deploy resets the live SQLite state. You can also turn off **`bv-live-api` → Settings → Build & Deploy → Auto-Deploy** for the session. Known gap (F10): the SAE JSON export link is a plain link and cannot send `X-BV-Token`, so it returns 401 on the live instance (`docs/deploy.md` §5).
   9. **Once it works:** put the `bv-demo-web` URL into the README (R8 replaced the old "**Live demo:** not deployed yet" line; the exact edits are item 8 below), and remove "verified locally only" from `docs/deploy.md`; commit and push.

8. **Done (README points at https://bv-demo-web.onrender.com).** Put the public demo URL into the README after the Render deploy (R8; after item 7).** The README says "the public demo URL (pending deploy, …)" in two places. With the real `bv-demo-web` URL (from item 7, sub-step 5):
   - README line 13 (starts with "**Public demo:**"): replace the words from "the public demo URL (pending deploy" through the closing parenthesis after the `docs/deploy.md` link with the `bv-demo-web` URL, and change "Until it is live, run" to "To run"; keep the `make demo` and Quickstart link.
   - README line 17 (first line under "Reviewer path (3 minutes)"): replace the same words, "the public demo URL (pending deploy" through the closing parenthesis after the `docs/deploy.md` link, with the `bv-demo-web` URL.
   - README "Deploy" section: remove the sentence "So far it is verified locally only." (and the same words at the top of `docs/deploy.md`, as in item 7 sub-step 9; `docs/deploy.md` §4 step 8 still names the old "**Live demo:** not deployed yet" line, update it to say README lines 13 and 17).
   - Check, then commit and push:
     ```bash
     grep -n 'pending deploy' README.md    # prints nothing
     git add README.md docs/deploy.md && git commit -m "README: public demo URL" && git push origin site-signal-build
     ```
   - The demo video line (README line 9) is filled at submission (item 1), not here.

9. **Second R10 acceptance run against the public demo (R10; after item 7).** The suite drives only the dashboard, so it runs unchanged against the deployed `bv-demo-web` (which calls `bv-demo-api`). Each run adds a check-in, a serious-event report and a closed site query to the demo instance (they disappear on the next deploy); do not run it against the live instance. From the main checkout root, with the real URL from item 7, sub-step 5:
   ```bash
   git checkout site-signal-build && git pull --ff-only
   DEMO_WEB=https://bv-demo-web.onrender.com   # the real bv-demo-web URL
   cd e2e && npm ci && npx playwright install chromium && BASE_URL=$DEMO_WEB npx playwright test
   # expected: "2 passed" (serious event: replay ... sponsor inbox; site signal: ... five audit rows)
   ```
   A free Render instance can take a minute to wake up; if the first test times out on "the Replay control shows only when /api/health says demo_mode", open `$DEMO_WEB` in a browser once and run the command again. Then record the result on the R10 row of `PROGRESS.md` (Status `done`, empty Blocker once item 12 is green too).

10. **Make and log the three real V10 calls against the live backend (V10; after item 7).** V10CODE is integrated on `site-signal-build`: `agent/voice_check.py`, its offline test, and `eval/results/voice_checks.json` with 3 `"status": "pending"` rows (the report card's "Real voice calls" row says "pending: no real calls logged yet"). Full procedure: `agent/README.md` § "Real calls against the live backend (V10)". Work from the main checkout root (`cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only`).
   1. **Checklist first.**
      - Each teammate who plays a patient agrees, before the call, to recording by ElevenLabs, logging here and a later transcript export (V11).
      - `bv-live-api` is up with R3 and R4 deployed, `DEMO_MODE=0`, and `TOOL_SHARED_SECRET` equal to the local `.env` value. `curl -fsS $LIVE_API/api/health | jq '{ok, demo_mode, commit}'` shows `"demo_mode": false`. If the live instance is not up: `make tunnel` and use the tunnel URL as `LIVE_API`.
      - The nurse phone's ntfy app is subscribed to the live `NTFY_TOPIC` and `NTFY_BACKUP_TOPIC`.
      - Local `.env` has `ELEVENLABS_API_KEY`, plus `BV_DASHBOARD_TOKEN` if the live instance uses one.
   2. **Point the agents at the live backend:**
      ```bash
      export LIVE_API=https://<bv-live-api host>     # or the tunnel URL
      PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
      ```
      If it warns about an old tunnel URL, fix the webhook URL in the ElevenLabs dashboard. Put `ELEVENLABS_WEBHOOK_SECRET` (only if a new one was printed) and the contents of `agent/agents.lock.json` (as `AGENTS_LOCK_JSON`) into the `bv-live-api` environment, then redeploy.
   3. **Deployed config equals git:** `make sync-agent ARGS=--snapshot && python3 agent/check_config_hash.py` must print OK (`voice_check.py` copies `agent_llm` from `agent/deployed_snapshot.json`).
   4. **Dashboard against the live API:** `cd frontend && NEXT_PUBLIC_API_BASE_URL=$LIVE_API NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<token> npm run dev`, then open http://localhost:3000.
   5. **Three calls in a row**, each from **Today** → patient row → **Call in browser**. Note each `ci_...` ID from the check-in page URL, and keep the full IDs outside git (the file stores only the last 4 characters; item 11 needs the full IDs).
      - Call 1 `james_g2_diarrhea` (en-standard, `pat_james`): worst day "five times", no blood, **not** dizzy on standing → expected grade 2, `CTCAE5_DIARRHEA_G2`, no page.
      - Call 2 `james_g3_diarrhea` (en-standard, `pat_james`, new check-in): worst day "eight times" → expected grade 3, urgent `RF_DIARRHEA_SEVERE`; the nurse taps **Acknowledge** on the phone.
      - Call 3 `rosa_g3_diarrhea` (es-extra_time, `pat_rosa`): persona P16 answers, including "como siete u ocho veces" (the agent records 8) → expected "del equipo" disclosure, grade 3, urgent page, acknowledged. ("siete veces" alone is 6 over her baseline of 1: grade 2, no page.)
   6. **Log each call** after it has ended and its page is acknowledged (rerun after a late acknowledgment; the row is updated in place):
      ```bash
      uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario james_g2_diarrhea
      uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario james_g3_diarrhea
      uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario rosa_g3_diarrhea
      ```
      Add `--conversation-id conv_...` if the check-in has no `el_conversation_id`. Add `--backend render-live` or `--backend tunnel` if the host is neither `*.onrender.com` nor ngrok. Never type a measurement into the file by hand, and never rerun a call to replace a bad result.
   7. **Check, commit and push:**
      ```bash
      jq '.calls|length' eval/results/voice_checks.json                                   # 3
      jq '[.calls[]|select(.red_flag_expected)|{paged, utterance_to_page_s, page_to_ack_s}]' eval/results/voice_checks.json
      jq '[.calls[]|.disclosure_first_turn]|all' eval/results/voice_checks.json            # true
      curl -fsS -H "X-BV-Token: $BV_DASHBOARD_TOKEN" $LIVE_API/api/escalations | jq '[.[]|select(.status=="acknowledged" or .status=="resolved")]|length'   # >= 2
      python3 agent/test_voice_check.py
      git add eval/results/voice_checks.json agent/deployed_snapshot.json
      git commit -m "WS1-V10: three real calls against the live backend" && git push origin site-signal-build
      ```
      V10 passes when both red-flag calls show `paged: true`, `utterance_to_page_s` <= 10 and a non-null `page_to_ack_s`, and every first turn disclosed. Then do item 11 (V11 export).

11. **Export the real V10 calls as recorded replay scenarios (V11; after V10).** V11 is integrated on `site-signal-build`: `agent/export_scenario.py` and the demo-only route `GET /api/demo/scenarios/{id}/audio`. No recorded scenario exists yet (the demo lists 0 recorded scenarios until this item is done).
   1. **Consent first.** Confirm that the teammate who played each synthetic patient agrees to the call being recorded and exported as a transcript. Use `--audio` only with that consent. Serving the audio from the public demo also needs their written consent; without it, ship transcript-only (leave out `--audio`, or keep the mp3 off the public instance).
   2. **Setup.** After the V10 calls are logged in `eval/results/voice_checks.json`, work from the main checkout root and take each call's full `conversation_id` and `checkin_id` from where you kept them outside git (item 10 step 5; that file stores only the last 4 characters, which identify the call but cannot be passed to the script). `ELEVENLABS_API_KEY` must be in `.env`. If the live instance uses a dashboard token, `BV_DASHBOARD_TOKEN` must be set in `.env` or the shell.
      ```bash
      export LIVE_API=<live API base URL the calls ran against>   # falls back to PUBLIC_BASE_URL
      ```
   3. **Call 1** (en-standard, James, grade 2, no page):
      ```bash
      uv run --project backend python agent/export_scenario.py --conversation-id <conv_ of call 1> --checkin-id <ci_ of call 1> --id rec_en_g2 --title "James, English, standard, grade 2 diarrhea (recorded)"
      ```
   4. **Call 3** (es-extra_time, Rosa, red flag). Leave out `--audio` if there is no consent:
      ```bash
      uv run --project backend python agent/export_scenario.py --conversation-id <conv_ of call 3> --checkin-id <ci_ of call 3> --id rec_es_g3_flag --title "Rosa, Spanish, extra time, urgent diarrhea (recorded)" --audio
      ```
      If call 3 failed, export call 2 instead with `--id rec_en_g3_flag --title "James, English, standard, urgent diarrhea (recorded)"`.
   5. **Read every warning the script prints.** "link check" or "no whitelisted argument left" means stop and investigate. Do not pass `--skip-link-check` unless you are sure the conversation and the check-in are the same call.
   6. **RULE: a person reviews before `git add`.** Read the whole transcript (`events[-1].transcript`) and every tool argument (`events[].body`) in each `scenarios/<id>.json`, looking for a real name, phone number or other identifier spoken off-script. If one appears, do not commit the file as is: re-record the call, or replace the words with `[redacted]` and say so in the commit message. Do not edit the file in any other way.
   7. **Verify.**
      ```bash
      python3 agent/test_export_scenario.py      # also checks every committed recorded scenario against the whitelist
      make demo                                  # then, in another terminal:
      curl -s localhost:8000/api/demo/scenarios | jq '[.[]|select(.recorded)]|length'   # expect 2
      ```
   8. **Fidelity check** for each exported scenario (example for `rec_es_g3_flag`; repeat with `rec_en_g2`):
      ```bash
      cid=$(curl -s -X POST 'localhost:8000/api/demo/replay/rec_es_g3_flag?speed=4' | jq -r .checkin_id)
      # wait for the replay to finish, then:
      curl -s localhost:8000/api/checkins/$cid | jq '[.findings[]|{term,provisional_grade,rule_id}]'
      ```
      The result must equal the grade and `rule_id` of that call in `eval/results/voice_checks.json`.
   9. **Commit** only `scenarios/rec_*.json`, then push. Never commit `scenarios/audio/*.mp3` (gitignored); copy the mp3 to the demo machine's `scenarios/audio/` by hand.
      ```bash
      git add scenarios/rec_*.json && git commit -m "WS1-V11: recorded scenarios rec_en_g2 rec_es_g3_flag" && git push origin site-signal-build
      ```

12. **Check that the new CI job `e2e` is green on GitHub (R10; first run on GitHub runners).** R10 is integrated on `site-signal-build` and passed locally (2 passed, dev and production frontend builds). The `e2e` job in `.github/workflows/ci.yml` installs Chromium with `npx playwright install --with-deps chromium`, starts `make demo DEMO_PROD=1` in the background, waits up to 300 s for `/api/health` (`demo_mode: true`) and the dashboard, then runs both journeys; it has never run on a GitHub runner. From the main checkout root:
   ```bash
   gh run list --repo feruzkarimovv/between-visits --workflow CI --branch site-signal-build --limit 3
   gh run watch <run id from the first row> --repo feruzkarimovv/between-visits
   gh run view <run id> --repo feruzkarimovv/between-visits --json jobs --jq '.jobs[] | select(.name=="e2e") | .conclusion'   # "success"
   ```
   Or on GitHub: **Actions → CI →** the newest run on `site-signal-build` **→ e2e**; the step "Playwright smoke (both journeys)" ends with `2 passed`. If it is red, download the traces and the demo log, and open the report locally:
   ```bash
   gh run view <run id> --repo feruzkarimovv/between-visits --log-failed | tail -n 80   # includes "make demo log (on failure)"
   gh run download <run id> --repo feruzkarimovv/between-visits --name e2e-playwright --dir /tmp/e2e-playwright
   cd e2e && npm ci && npx playwright show-report /tmp/e2e-playwright/playwright-report
   ```
   CI retries a failed test once (`retries: 1` in `e2e/playwright.config.ts`), so a red job is a real failure, not a single flaky step.

13. **Check that the CI jobs `gitleaks` and `frontend` are green on GitHub after the FINALFIX push (final review fixes; first run on GitHub runners).** FINALFIX is integrated on `site-signal-build` and passed locally (`make secret-scan` exit 0: 189 commits scanned, no leaks found, numbers 0 hits; `make test` exit 0, including the new `npm test` display-rounding unit test). The `gitleaks` job now uses the two new allowlists in `.gitleaks.toml` (run-log sha256 digests, app record IDs), and the `frontend` job gained the step `cd frontend && npm test`; neither has run on a GitHub runner yet.
   ```bash
   gh run list --repo feruzkarimovv/between-visits --workflow CI --branch site-signal-build --limit 1
   gh run watch <run id from that row> --repo feruzkarimovv/between-visits
   gh run view <run id> --repo feruzkarimovv/between-visits --json jobs --jq '.jobs[] | select(.name=="gitleaks") | .conclusion'   # "success"
   gh run view <run id> --repo feruzkarimovv/between-visits --json jobs --jq '.jobs[] | select(.name=="frontend") | .conclusion'   # "success"
   ```
   Or on GitHub: **Actions → CI →** the newest run on `site-signal-build` **→ gitleaks** (ends with `no leaks found`) and **→ frontend** (the `npm test` step prints `pass 2`, `fail 0`). If a newer push cancelled that run, check the newest uncancelled one. If `gitleaks` is red, run `make secret-scan` locally on the same commit and record the finding in `validation/secret-scan.md`; never allowlist a real key (rotate it first).

14. **Record the first uncancelled run of the `Site Signal quick check` workflow (S7 final review fix; after the push that brings `.github/workflows/site-signal-quick-check.yml`).** The quick check of the committed validation now runs on `macos-latest` (arm64), the platform of the committed evaluation runs, in its own workflow with `cancel-in-progress: false`, so a later push queues behind it instead of cancelling it (`docs/11` §17 C8). It runs on pushes that touch `monitoring/`, `validation/site_signal/`, `data/`, `backend/app/`, the `Makefile`, `.python-version` or the workflow itself, and on demand (`workflow_dispatch`, available once the file is on `main`). macOS minutes count 10x against a private repository's Actions quota.
   ```bash
   gh run list --repo feruzkarimovv/between-visits --workflow "Site Signal quick check" --branch site-signal-build --limit 3
   gh run watch <run id> --repo feruzkarimovv/between-visits
   gh run view <run id> --repo feruzkarimovv/between-visits --log | grep -E "MATCH|MISMATCH|quick check"   # expect "quick check passed: every quick_hashes entry equals summary.json"
   ```
   Then put the run ID and the result line in the WS5-S7 row of `PROGRESS.md` § Final review fixes (the quick-check row). If the macOS runner also prints `MISMATCH power_grid` (a different macOS or Accelerate build than the build machine's), do not change `summary.json` or `validate.py`: add the run ID and the platform (`sw_vers`, printed by the job) to `WHAT_IT_GETS_WRONG.md` §16 and a `docs/11` §17 row, and tell the team lead.

15. **R12 clean clone on a second laptop by someone who did not build the product (R12 acceptance; the secret-scan fix is done).** The R12 run was done on the build machine with warm uv and npm caches, so it does not count for this part. On a second laptop with uv, Node 22, make, gh (signed in; the repo is private) and gitleaks 8.30.1:
   ```bash
   gh repo clone feruzkarimovv/between-visits && cd between-visits
   git checkout site-signal-build
   cp .env.example .env            # leave every key empty
   make setup && make seed && make test   # make test: exit 0
   make demo                       # backend :8000 + dashboard :3000, DEMO_MODE=1; leave it running
   ```
   In a second terminal, from the same folder:
   ```bash
   cd e2e && npm ci && npx playwright install chromium && BASE_URL=http://localhost:3000 npx playwright test   # "2 passed"
   cd .. && make secret-scan; echo exit=$?   # exit=0 once item 17 is pushed
   ```
   Stop `make demo` with Ctrl-C. Record who ran it, the date, the machine and each step's result (or the exact failing line) in a new short section at the end of `validation/secret-scan.md`, and on the R12 row of `PROGRESS.md` (Status `done`, empty Blocker), then:
   ```bash
   git add validation/secret-scan.md PROGRESS.md && git commit -m "R12: second-laptop clean clone" && git push origin site-signal-build
   ```

16. **Timed README walkthrough (R8 acceptance).** A teammate who did not build the product follows only the README section "Reviewer path (3 minutes)" and must reach the Sponsor inbox in under 3 minutes. Do not help them; start a stopwatch when they open the dashboard.
   - Once `bv-demo-web` is deployed (item 7): open the `bv-demo-web` URL in an incognito window.
   - Until then, on a laptop with uv, Node 22 and make, from the repo root:
     ```bash
     cp .env.example .env                  # leave every key empty
     make setup && make seed && make demo  # backend :8000 + dashboard :3000, DEMO_MODE=1
     ```
     then open http://localhost:3000.
   - They follow the table: **Today** → Speed **4x** → **Replay scenario** → Check-in (Urgent panel, "Acknowledged in N s") → **Review 3 drafts** → **Confirm** Diarrhea → role **Investigator · Dr. Patel** → tick **Requires or prolongs hospitalization**, pick a relatedness, **Sign as Dr. Patel** → **Open report** → **Sign as Dr. Patel** → **Send to sponsor** → **Sponsor inbox** shows 101-007 *On time*. Stop the clock there.
   - Record the time and where they got stuck (if anywhere) in the R8 row of `PROGRESS.md` (Acceptance output), then commit and push:
     ```bash
     git add PROGRESS.md && git commit -m "R8: timed README walkthrough" && git push origin site-signal-build
     ```
   - If it took 3 minutes or more, note the step that cost the time; the README path gets fixed before submission (D16).

17. **A second teammate ticks the provenance table at the foot of `WHAT_IT_GETS_WRONG.md` (FILL; D13/D14 acceptance; footer item 20 of that page).** FILL rendered every Site Signal number in `WHAT_IT_GETS_WRONG.md`, `README.md`, `docs/pitch/deck.html`, `docs/08-demo-and-pitch.md` and `docs/10-site-signal.md` §10.1 (447 values: 400 at FILL, 47 more from the final review fixes; item 1 steps 1 and 3 are done apart from this tick and item 14). Someone who did not write the story files does this, from the main checkout root:
   ```bash
   git checkout site-signal-build && git pull --ff-only
   python3 validation/render_numbers.py --check WHAT_IT_GETS_WRONG.md README.md docs/pitch/deck.html docs/08-demo-and-pitch.md docs/10-site-signal.md   # last line: check: OK, 0 tokens left in 5 files; 447 rendered values ...
   ```
   Then open `WHAT_IT_GETS_WRONG.md` § "How every number was checked" and, row by row (at least every row on deck slides and in the README, and a sample of the rest), look the JSON path up in the source file and confirm the value and that the sentence on the listed line says what the number says. Selector paths become a jq `select`, for example row 5:
   ```bash
   jq '.power[] | select(.indicator=="discordance" and .tier=="look" and .design_row==true and .f==0.25) | .power' validation/site_signal/summary.json   # 0.15
   jq '.design.n_sites' validation/site_signal/summary.json   # 20
   ```
   Pay attention to the claims FILL reworded because the numbers contradict the drafts: discordance is ahead of the plain AE-rate KRI only for a 50% gap at Watch and behind it for a gross loss; at mu = 0.5 discordance never computes the planted site (power 0.00); in the committed study discordance caught 0 of 5 planted sites at Watch and the KRI caught the two gross-loss sites. If a value is wrong, do not type a new one: restore the tokenised source (`git show 93d9333:<file>`), fix the path inside the token and re-render with `python3 validation/render_numbers.py --in-place <files>`. When every row is ticked, change footer item 20 of `WHAT_IT_GETS_WRONG.md` to say who checked it and when, then:
   ```bash
   git add WHAT_IT_GETS_WRONG.md && git commit -m "WS4-D13: provenance table checked by a second teammate" && git push origin site-signal-build
   ```

18. **Set a real `TOOL_SHARED_SECRET` on every machine or deploy that runs with `DEMO_MODE=0` (R4).** Outside demo mode the backend now refuses to start (exit 1, one-line message) when `TOOL_SHARED_SECRET` is empty, still `change-me-long-random-string`, or shorter than 24 characters. The main checkout's `.env` already passes. On any other machine (or a fresh `cp .env.example .env`):
   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
   # paste the output into .env as TOOL_SHARED_SECRET=<value>, then:
   make dev
   ```
   If the value changes, push it to the ElevenLabs workspace secret too, so the agent's tools keep authenticating:
   ```bash
   make sync-agent
   ```
   `make demo` (`DEMO_MODE=1`) starts with any secret and needs none of this.

19. **Reseed every SQLite database built before B13 (audit hash chain).** `AuditEvent` gained `seq`, `prev_hash` and `hash` columns and there is no migration (docs/02). Until an old database is reseeded, each audit row is dropped (the hook logs `audit_chain_failed`; the caller's own write still commits) and `GET /api/audit` returns 500. Reseeding deletes the local demo data in that database. In each checkout or deploy that has a database:
   ```bash
   git checkout site-signal-build && git pull --ff-only
   make seed                                  # or: make demo (reseeds with DEMO_MODE=1, then starts backend + frontend)
   # with the backend running on :8000:
   curl -s localhost:8000/api/audit/verify    # expect {"ok":true,...}
   ```
   For a deployed instance, run the same seed command in its shell (`cd backend && uv run python -m app.seed`, with `DEMO_MODE=1` for a demo deploy) and restart the service.

20. **Optional: make `make up` (R5 production images) run from this laptop's docker CLI.** The host `docker` has no working `compose` or `buildx` plugin: `~/.docker/cli-plugins/docker-compose` and `docker-buildx` are symlinks into `/Applications/Docker.app`, which is not installed (colima is the engine). Install Compose and point both symlinks at the Homebrew binaries (`docker-buildx` is already installed by Homebrew):
   ```bash
   brew install docker-compose
   ln -sfn /opt/homebrew/opt/docker-compose/bin/docker-compose ~/.docker/cli-plugins/docker-compose
   ln -sfn /opt/homebrew/opt/docker-buildx/bin/docker-buildx ~/.docker/cli-plugins/docker-buildx
   docker compose version && docker buildx version     # both print a version
   cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
   make up                                             # foreground; API :8000, dashboard :3000 (API_PORT/WEB_PORT to change)
   # in another terminal:
   curl -fsS localhost:8000/api/health | jq -e '.ok and .demo_mode'   # expect: true
   curl -fsS localhost:3000 | grep -q 'Between Visits' && echo web-ok  # expect: web-ok
   # Ctrl-C, then:
   docker compose -f docker-compose.prod.yml down
   ```
   Without this, the same stack runs through the compose inside the colima VM: `colima ssh -- env GIT_COMMIT=$(git rev-parse --short HEAD) docker compose --project-directory "$PWD" -f "$PWD/docker-compose.prod.yml" up --build -d` (stop with the same command and `down`).
