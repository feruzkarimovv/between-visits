# 08 · Demo script, video and deck

Numbers come from real runs only:

- **Text-mode evaluation.** `eval/results/latest.json`, with Clopper-Pearson intervals, copied with the key named.
- **Real calls (MEASURED).** `eval/results/voice_checks.json`. None is quoted until it exists.
- **Site Signal (SIMULATED).** `validation/site_signal/summary.json` and `monitoring/out/*.json`. In this file, the README, `WHAT_IT_GETS_WRONG.md` and `docs/pitch/deck.html`, each Site Signal number is an `ss` token. `validation/render_numbers.py` fills the tokens from those files and rounds them by `docs/11` §15 rule 6. Never script, type or round one by hand.

Every chart or number on screen carries its SIMULATED or MEASURED label.

> **Decision (Sat Oct 10, ~8 PM):** LLMs moved from Gemini to Claude (Anthropic API credits): voice agent on Claude Sonnet 5.5 via ElevenLabs; post-call pipeline Haiku 5.5 / Opus 5.5; evaluation agent = same model as the voice agent. The model the deployed agent actually uses is recorded in `agent/deployed_snapshot.json` (V9).
>
> **Decision (Sat Oct 10, 6:30 PM):** no Twilio for the hackathon. Patient calls run in the browser (same ElevenLabs agent, same tools, same pipeline); the nurse page is ntfy and needs no Twilio. Phone calling stays in the code (`make sync-agent`, `ELEVENLABS_PHONE_NUMBER_ID`) for a real deployment.

## 30-second summary

"Patients in cancer trials who don't speak English, and patients who need more time, are the hardest to reach between visits. Between Visits is a voice agent that calls them in the days after a dose, in their language and at their pace. It asks plain-language symptom questions, fixed CTCAE rules grade the answers, and anything urgent pages the on-call nurse within seconds. The study team gets draft side-effect entries with the patient's own words as evidence, and serious events go to the sponsor with the 24-hour clock running. On the sponsor side, Site Signal compares each site's own AE log with what that site's patients told the agent and points a monitor at sites where the two disagree more than chance explains: a reason to look, not a finding. The AI listens, rules grade, humans decide."

## 3:00 video storyboard (D15, final)

**Format.** Recorded on the production build (`make demo DEMO_PROD=1`, no dev badge), 1080p, dashboard at 125% zoom, Spanish audio subtitled in English.

**The call.** The call is the hero call (V12): a real browser call with a teammate playing the synthetic patient, labeled on screen "Real call; synthetic patient played by a teammate". If the hero call is not available, shot 3 uses the scripted replay `rosa_es_urgent` at 1x, labeled on screen "Scripted replay", and the voiceover says "a scripted replay of the same call".

**Out of the video.** These were cut this round (`NOT_BUILT.md`), so the video does not show them: the blind run, the Equity tab, the "days before next visit" badge and a recorded-scenario label.

**Shot list.** Nine shots, 178 s in total, under the 180 s limit.

| # | Time | Length | Screen | Label on screen | Voiceover / audio |
|---|---|---|---|---|---|
| 1 | 0:00–0:12 | 12 s | Title card, then Rosa's profile: 74, Spanish, extra time, two days after her second dose | "Synthetic patient" | "Rosa is 74, speaks Spanish, and lives an hour from her cancer center. She had her second dose two days ago. Her next visit is in three weeks." |
| 2 | 0:12–0:22 | 10 s | `/plan`: the approved check-in plan, English and Spanish side by side, red flags | "Synthetic data" | "The study team approves the plan: plain-language questions in English and Spanish, graded with NCI's CTCAE, red flags from the drug class's patient guide." |
| 3 | 0:22–1:02 | 40 s | `/checkins/[id]` split screen with the call audio. Disclosure and offer of a human in Spanish, then "¿Es buen momento?", the diarrhea question, "¿Cómo?", a slow repeat, "siete veces", the read-back, *Diarrhea · provisional grade 3* with its rule, and the approved urgent line. | "Real call; synthetic patient played by a teammate" (or "Scripted replay"); English subtitles | "It discloses it is an AI, waits, repeats and reads back. A fixed rule, not the AI, sets the grade." |
| 4 | 1:02–1:15 | 13 s | The nurse phone buzzes; one tap on Acknowledge; the panel shows the acknowledgment time | Subject ID only on the push | "The on-call nurse is paged in seconds, told Rosa prefers Spanish, and acknowledges with one tap. The agent gives no medical advice." |
| 5 | 1:15–1:35 | 20 s | `/review` drafts with Spanish quotes and labeled AI translations, then the investigator marks serious, then the `/sae` 24-hour clock, then `/sponsor` | "AI translation, verify"; "AI draft" | "Every entry is a draft with the exact words and the second they were said. A serious event reaches the sponsor the same day, with the clock running." |
| 6 | 1:35–2:15 | 40 s | Role switch to CRA. `/sites` (SIMULATED badge, funnel, Look and Watch), then a flagged site with unmatched episodes and the patients' words, then the CRA approves a templated query, then the coordinator's coded answer in `/site-inbox` | SIMULATED on every view | "On the sponsor side, Site Signal compares each site's AE log with what that site's own patients reported, in a simulated 20-site study. The thresholds were fixed before any result existed. A flag opens the patients' words; a monitor approves every query; legitimate clinical judgment is a normal answer. A flag is a reason to look, not a finding." |
| 7 | 2:15–2:30 | 15 s | `/sites` tab **How well it works**: power at both tiers with MC SE, false-flag rates, the failure case | SIMULATED, with MC SE on screen | "In simulation, the Watch tier flags 70% of sites with a large capture gap, but 22% of 50% gaps and 3% of 25% gaps. Moderate gaps mostly go unflagged, and we show that." |
| 8 | 2:30–2:45 | 15 s | `/report-card`: intervals, the language and pace table, the known miss, the real-call row | "Text mode, 20 simulated patients"; MEASURED on the real-call row | "On 20 simulated patients it paged 8 of 8 urgent cases, an interval of 63 to 100 percent, in Spanish and in English. Here is one case it still gets wrong, and the planned fix." |
| 9 | 2:45–2:58 | 13 s | Architecture strip, `make demo`, MIT | none | "Between Visits. Open source, runs from a fresh clone, built on ElevenLabs and Claude. No symptom waits for the next visit, in any language, at any pace." |

**Where the spoken numbers come from.** Shot 7's percentages are `ss` tokens, filled by `validation/render_numbers.py` from `summary.json` (`power[]`, indicator `discordance`, tier `watch`). Shot 8's numbers are from `eval/results/latest.json`: `overall.red_flag_caught`, `overall.red_flag_cases` and `overall.red_flag_recall_ci95`, rounded to whole percent for speech. Shot 7's last sentence was written before any result existed. If the rendered numbers do not show most moderate gaps going unflagged at Watch, change the sentence, never the numbers (`docs/10` §10.2). The rendered numbers bear it out, so the sentence stands.

### Recording checklist

Before recording:

- [ ] **S7 is done**, and the Site Signal numbers are rendered in place: `python3 validation/render_numbers.py --in-place WHAT_IT_GETS_WRONG.md README.md docs/pitch/deck.html docs/08-demo-and-pitch.md`.
- [ ] **The check passes:** `python3 validation/render_numbers.py --check WHAT_IT_GETS_WRONG.md README.md docs/pitch/deck.html docs/08-demo-and-pitch.md` prints `check: OK`.
- [ ] **A second teammate ticks the provenance table** at the foot of `WHAT_IT_GETS_WRONG.md` against the source files.
- [ ] **The voiceover script uses the rendered shot 7 numbers** from this file, not numbers from memory.
- [ ] **Production build:** `make demo DEMO_PROD=1` (or the deployed public demo), no Next.js dev badge, browser zoom 125%, 1920×1080 capture.
- [ ] **Hero call (V12) consent:** the teammate playing Rosa agrees to the recording. No real name, phone number or other identifier is spoken.
- [ ] **Nurse phone:** subscribed to the ntfy topic, Do Not Disturb off for ntfy only, screen recording on. Never show the topic name, `.env`, a terminal with secrets, or an API key.
- [ ] **Screen hygiene:** desktop notifications off, unrelated tabs closed, and no drug product names anywhere on screen (class only, "anti-PD-1").
- [ ] **Screenshots for the deck,** taken from the same session into `docs/screenshots/`: `call.png`, `nurse-ack.png`, `review.png`, `sites-funnel.png`, `site-drilldown.png`, `site-inbox.png`, `how-well-it-works.png`, `report-card.png`.

While recording:

- [ ] **Labels are in frame:** every Site Signal view shows its SIMULATED badge, the call shows its label (real call or "Scripted replay"), and AI translations and AI drafts show their labels.
- [ ] **Grades read "provisional"** wherever they appear.
- [ ] **The voiceover keeps to the approved wording** in `docs/10` §6.1 (the "Say" column): "capture discordance" and "a reason to look, not a finding".

After recording:

- [ ] **Export:** 1080p, total length at most 3:00, English subtitles burned in for the Spanish audio.
- [ ] **Upload** to YouTube as unlisted, and check that the link plays in an incognito window.
- [ ] **README:** put the link on the "Demo video" line (`HUMAN_TODO.md`), and commit.

## Live walkthrough (about 3 minutes)

Roles: **A** presents, **B** plays Rosa (headset on the dashboard laptop; the browser call runs where it's started), **C** drives the dashboard and holds the nurse phone, **D** switches to the CRA view and answers technical questions.

1. A (15 s): who is hardest to reach between visits, and Rosa in one sentence.
2. C clicks **Call in browser** on Rosa's row; B answers. Let the listener hear the disclosure, one patient-paced repeat and the red flag (about 60 s).
3. C shows the nurse push, taps Acknowledge, then the review queue and the sponsor clock (about 25 s).
4. D (about 50 s): CRA view, `/sites` funnel, one flagged site's quotes, approve a query, coordinator answers in the inbox.
5. A (15 s): "The AI listens, rules grade, humans decide", then the report card and the "How well it works" tab, including what it misses.
6. Offer the headset: "Ask it for medical advice."

Backup: if the call fails, say "Here is a scripted replay of the same call" and run **Replay scenario** with `rosa_es_urgent` (labeled "Scripted"). Practice the switch in under 10 seconds.

## Deck (10 slides, D14, final)

The deck source is [`docs/pitch/deck.html`](pitch/deck.html). It is one self-contained HTML file with 16:9 slides and print CSS. Its Site Signal numbers are `ss` tokens. Render them, then print to `docs/pitch/deck.pdf` (13.333 × 7.5 in, no margins, background graphics on) with `uv run --no-project --with playwright==1.63.0 python docs/pitch/export_pdf.py`, which fails unless the PDF has one page per slide. The comment at the top of the file has the commands. Screenshots resolve to `docs/screenshots/<name>.png`; a missing one shows its path in a dashed frame.

| # | Slide | Numbers and labels | Screenshots |
|---|---|---|---|
| 1 | Between Visits: tagline, one-line description, "The AI listens, rules grade, humans decide", team | none | none |
| 2 | Who is hard to reach between visits: non-English speakers and patients who need more time | none | none |
| 3 | Rosa's three-week gap; clinician reports miss patient-reported symptoms | `docs/10` §2 sources, unverified figures marked UNVERIFIED | none |
| 4 | Between Visits in one picture: plan → call → nurse → review → sponsor, plus one line on Site Signal | none | none |
| 5 | Demo: the call, the nurse acknowledgment, drafts with evidence | call label (real call or "Scripted replay"), AI translation label | `call.png`, `nurse-ack.png`, `review.png` |
| 6 | Safety by design: each rule with its requirement ID; real calls MEASURED in their own row | MEASURED | none |
| 7 | Site Signal: funnel, drill-down to quotes, CRA-approved query | SIMULATED; computed sites (`signal_run.json`), expected false Look flags (`thresholds.json`) | `sites-funnel.png`, `site-drilldown.png`, `site-inbox.png` |
| 8 | How well it works and what it gets wrong | report card with Clopper-Pearson intervals (`latest.json`); Site Signal power at both tiers for the 25%, 50% and gross rows with MC SE, null false-flag rates with MC SE, the failure case (`summary.json`); all SIMULATED | none |
| 9 | Readiness: one command, MIT, CI, traceability, pre-registered plan, audit hash chain, honest limits | none | none |
| 10 | Next steps: retrospective validation on trials with paired patient- and clinician-reported data, a pilot with one site, more languages, EDC/FHIR integration | none | none |

## Common questions

- **Why voice, not an app?** Voice works on any phone, for older patients and people with low vision or literacy, in their language, and a conversation catches what forms miss ("I went to urgent care and got an antibiotic").
- **Isn't an AI calling sick patients risky?** It says only pre-approved words, says it's an AI, offers a human, never gives advice, and escalates by fixed rules. Each is a tested requirement.
- **What if it grades wrong?** Grades are provisional, come from CTCAE rules, and a clinician confirms every entry. The known miss and its fix are on the report card.
- **How is translation safe?** Every question is pre-written in both languages; the AI never translates clinical questions live. Studies registered with NCI can load the official PRO-CTCAE translations locally. Patient answers keep the original words; English translations are labeled as AI translations.
- **Why not NCI's PRO-CTCAE questions directly?** Their terms don't allow redistributing or modifying the items in an open-source repository, so we wrote our own and built a local plug-in for registered studies.
- **Does Site Signal accuse a site?** No. It measures capture discordance against other sites, says "a reason to look, not a finding", and the query asks the site to review its source documents and either enter the event or say why no entry is needed. "Recorded as medical history" and "not an AE per investigator" are normal answers.
- **Isn't the patient stream just as fallible?** It is a reference, not the truth: patients report earlier and more often, clinicians judge attribution. That is why the comparison is relative to other sites and why an honest low-diligence site is planted in the simulation.
- **How do we know the thresholds weren't tuned?** The analysis plan and parameters were tagged in git before any output existed, the evaluation seed includes a public beacon value published after the tag, and every evaluation run is logged (`docs/11` §1.2–§1.3).
- **Is any of the Site Signal data real?** No. Both streams in the 20-site study are simulated (SIMULATED); live and replayed calls at site 101 are MEASURED and never pooled with it. Real-world validation is the next step.
- **What did you build vs use?** Used ElevenLabs and Claude (Anthropic API). Built the interview engine, rules, escalation and paging, post-call pipeline, review and sponsor workflow, evaluation harness, validation pack and the Site Signal statistics.

## Submission checklist (D16, by 9:30 AM)

- Links: GitHub repository (private; reviewer access arranged by the team lead), YouTube video (unlisted), deck PDF (`docs/pitch/deck.pdf`), public demo URL (after the Render deploy).
- "Built with": ElevenLabs, Claude (Anthropic API), FastAPI, Next.js, SQLite, TypeScript, Python, numpy, scipy.
- All four teammates added as contributors.
- Every number in the Devpost text matches its source file.
