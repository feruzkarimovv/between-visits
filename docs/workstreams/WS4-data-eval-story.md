# WS4 · Data, evaluation and story

Owner: teammate 4. Folders: `data/`, `eval/`, `validation/`, `README.md`, plus the deck and video.
Read first: `CLAUDE.md`, `docs/05-clinical-rules.md`, `docs/07-eval-and-validation.md`, `docs/08-demo-and-pitch.md`.

The clinical content and seed data are already written in `data/` (from the research done on Saturday afternoon). Your job: own their correctness, build the evaluation and validation tooling, and own the story (README, deck, video, Devpost).

## Kickoff prompt for Claude Code

> You are implementing workstream WS4 (data, evaluation, story) of Between Visits. Read CLAUDE.md, docs/05-clinical-rules.md, docs/07-eval-and-validation.md, docs/08-demo-and-pitch.md and docs/workstreams/WS4-data-eval-story.md. Start with task D1 (validate the data files), then D2 (evaluation harness). The harness must call the backend's real service functions in-process (backend/app/services/*), not reimplement them; if a function you need doesn't exist yet, write the harness against the interface described in docs/workstreams/WS2-backend.md and stub it until WS2 lands it. Use plan mode for each task. Commit each task as "WS4-Dn: <summary>". Only edit data/, eval/, validation/ and README.md.

## Tasks

### D0 · Local phone numbers (first 15 minutes)
- Create `data/patients.local.json` (gitignored) mapping patient IDs to teammates' verified phone numbers, and put the nurse and backup numbers in `.env`. Confirm every number is verified in Twilio.

### D1 · Validate the data files (target 6:00 PM)
- `data/validate_data.py` already exists and passes (cross-references between items, rules, red flags, scripts, tools, prompt and personas; licensed-content guards). Add it to `make test`, and extend it with Pydantic models for each file's shape. Run it after every content edit.
- Read every Spanish string out loud once. Fix anything awkward; keep "usted".
- **Accept:** script exits 0; add it to `make test`.

### D2 · Evaluation harness, text mode (target 3:30 AM, M3 gate)
- `eval/run_eval.py` per `docs/07-eval-and-validation.md` § Harness: in-process backend services on a temp DB; agent = Gemini with `agent/prompt.md` rendered exactly like a real call (same dynamic variables), tools declared as Gemini function declarations mirroring `agent/tools.json`; patient = Gemini persona; loop until `end_call` or 40 turns; post-call pipeline; scoring; `eval/results/latest.json` + `eval/results/transcripts/<id>.json`.
- `eval/score.py`: pure scoring functions with unit tests (expected vs actual escalation, AE terms, grades, CM, disclosure, approved wording similarity, pace checks).
- `eval/judge.py`: Gemini judge prompts for "no medical advice" and "read-back before recording" returning JSON `{"pass": bool, "evidence": "..."}`; temperature 0.
- Flags: `--personas P16,P04`, `--concurrency 2`, `--mode text|elevenlabs`, `--seed 7`.
- **Accept:** `make eval` completes all 20 personas and writes valid `latest.json`; the report card page renders it.

### D3 · Known misses and fixes (target 5:00 AM)
- Read every failing persona transcript. For each failure, decide: fix (tell WS1/WS2 what to change) or keep as an honest known miss with a planned fix in `latest.json`. Re-run after fixes. Keep at least one honest known miss if one exists; never hide failures.

### D4 · Validation pack (target 4:30 AM)
- `validation/requirements.yaml` (already written) and `validation/build_traceability.py` per `docs/07-eval-and-validation.md` § Validation pack. Coordinate with WS2 so every requirement has at least one tagged test.
- **Accept:** `make validate` writes `validation/traceability.md` and `validation/summary.json`; `--check` passes in CI.

### D5 · README (draft by 4:00 AM, final by 8:00 AM)
- Fill the skeleton in `README.md`: one-paragraph pitch, demo video link, screenshots/GIF, the problem with sources, how it works (diagram), safety design, evaluation results table (from `latest.json`), quickstart (demo mode in 3 commands, full mode with keys), configuration, data sources and licenses (CTCAE public domain, PRO-CTCAE terms, synthetic data statement), limitations, "not a medical device", team, MIT license.
- **Accept:** a teammate who hasn't seen the repo follows the README on a clean laptop and runs demo mode in under 10 minutes.

### D6 · Deck and video (deck draft 5:00 AM, video recorded by 8:30 AM)
- Deck: 11 slides per `docs/08-demo-and-pitch.md`, built from real screenshots and real numbers.
- Video: follow the script table exactly; record the hero call with WS1 at about 7:30 AM in a quiet room; add Spanish subtitles; export 1080p; upload unlisted to YouTube.
- **Accept:** video ≤ 3:15, deck ≤ 12 slides, both linked in the README.

### D7 · Devpost (submit by 9:30 AM)
- Text from the README; track Social Good; superlatives Regeneron and ElevenLabs; all four contributors; links to repo, video, deck. Screenshot the confirmation.
