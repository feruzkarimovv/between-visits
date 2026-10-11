# 08 · Demo script, video and deck

Numbers in [brackets] are filled from real runs only: `eval/results/latest.json` (text-mode evaluation, with Clopper-Pearson intervals), `eval/results/voice_checks.json` (real calls, MEASURED) and `validation/site_signal/summary.json` (Site Signal, SIMULATED). Never script or round them by hand. Every chart or number on screen carries its SIMULATED or MEASURED label.

> **Decision (Sat Oct 10, ~8 PM):** LLMs moved from Gemini to Claude (Anthropic API credits): voice agent on Claude Sonnet 5.5 via ElevenLabs; post-call pipeline Haiku 5.5 / Opus 5.5; evaluation agent = same model as the voice agent. The model the deployed agent actually uses is recorded in `agent/deployed_snapshot.json` (V9).
>
> **Decision (Sat Oct 10, 6:30 PM):** no Twilio for the hackathon. Patient calls run in the browser (same ElevenLabs agent, same tools, same pipeline); the nurse page is ntfy and needs no Twilio. Phone calling stays in the code (`make sync-agent`, `ELEVENLABS_PHONE_NUMBER_ID`) for a real deployment.

## 30-second summary

"Patients in cancer trials who don't speak English, and patients who need more time, are the hardest to reach between visits. Between Visits is a voice agent that calls them in the days after a dose, in their language and at their pace. It asks plain-language symptom questions, fixed CTCAE rules grade the answers, and anything urgent pages the on-call nurse within seconds. The study team gets draft side-effect entries with the patient's own words as evidence, and serious events go to the sponsor with the 24-hour clock running. On the sponsor side, Site Signal compares each site's own AE log with what that site's patients told the agent and points a monitor at sites where the two disagree more than chance explains: a reason to look, not a finding. The AI listens, rules grade, humans decide."

## 3:00 video storyboard (D15)

Recorded on the production build (no dev badge), 1080p, dashboard at 125% zoom, Spanish audio subtitled. The call is the hero call (V12): a real browser call with a teammate playing the synthetic patient, labeled on screen "Real call; synthetic patient played by a teammate".

| Time | Screen | Voiceover / audio |
|---|---|---|
| 0:00–0:15 | Title card; Rosa's profile: 74, Spanish, extra time, day 3 after dose | "Rosa is 74, speaks Spanish, and lives an hour from her cancer center. She had her second dose two days ago. Her next visit is in three weeks." |
| 0:15–0:25 | `/plan`: approved check-in plan, EN and ES side by side, red flags | "The study team approves the plan: plain-language questions in English and Spanish, graded with NCI's CTCAE, red flags from the drug class's patient guide." |
| 0:25–1:05 | `/checkins/[id]` split screen, real call audio | Disclosure and offer of a human in Spanish → "¿Es buen momento?" → diarrhea question → "¿Cómo?" → slow repeat → "siete veces" → read-back → *Diarrhea · provisional grade 3* with the rule → the approved urgent line. Voiceover: "It discloses it is an AI, waits, repeats and reads back. A fixed rule, not the AI, sets the grade." |
| 1:05–1:20 | Nurse phone buzzes; one tap on Acknowledge; panel shows the acknowledgment time | "The on-call nurse is paged in seconds, told Rosa prefers Spanish, and acknowledges in [N] seconds. The agent gives no medical advice." |
| 1:20–1:40 | `/review` drafts with Spanish quotes and labeled AI translations → investigator marks serious → `/sae` 24-hour clock → `/sponsor` | "Every entry is a draft with the exact words and the second they were said. A serious event reaches the sponsor the same day, with the clock running." |
| 1:40–2:25 | Role switch to CRA → `/sites` (SIMULATED badge, funnel, Watch and Look) → open a flagged site → unmatched episodes with patients' words → approve a templated query → `/site-inbox` coded answer → blind run with a typed seed and reveal → "How well it works" | "On the sponsor side, Site Signal compares each site's AE log with what that site's own patients reported, in a simulated 20-site study. Thresholds were fixed before any result existed. A flag opens the patients' words; a monitor approves every query; legitimate clinical judgment is a normal answer. Anyone can type a seed and test it blind. It catches [gross-loss Watch power, from summary.json] of large capture gaps and misses most 25% and 50% gaps at the Watch tier, and we show that." |
| 2:25–2:45 | `/report-card`: intervals, equity table, known miss, real-call row | "On 20 simulated patients it paged [x of y] urgent cases ([CI]) in Spanish and in English. Here is one case it still gets wrong, and the planned fix." |
| 2:45–3:00 | Architecture strip, `make demo`, MIT | "Between Visits. Open source, runs from a clean clone, built on ElevenLabs and Claude. No symptom waits for the next visit, in any language, at any pace." |

If the 03:30 voice cut rule fired, the call beat uses the recorded replay and says so on screen.

## Live walkthrough (about 3 minutes)

Roles: **A** presents, **B** plays Rosa (headset on the dashboard laptop; the browser call runs where it's started), **C** drives the dashboard and holds the nurse phone, **D** switches to the CRA view and answers technical questions.

1. A (15 s): who is hardest to reach between visits, and Rosa in one sentence.
2. C clicks **Call in browser** on Rosa's row; B answers. Let the listener hear the disclosure, one patient-paced repeat and the red flag (about 60 s).
3. C shows the nurse push, taps Acknowledge, then the review queue and the sponsor clock (about 25 s).
4. D (about 50 s): CRA view, `/sites` funnel, one flagged site's quotes, approve a query, coordinator answers in the inbox. Offer a blind run with a seed the listener types.
5. A (15 s): "The AI listens, rules grade, humans decide", then the report card and the "How well it works" tab, including what it misses.
6. Offer the headset: "Ask it for medical advice."

Backup: if the call fails, say "Here is the recorded call" and run **Replay scenario** (a recorded scenario when V11 exported one, else `rosa_es_urgent`, which is labeled "Scripted"). Practice the switch in under 10 seconds.

## Deck (10 slides, D14)

1. Between Visits: tagline, team, one-line description
2. Who is hard to reach between visits: non-English speakers and patients who need more time
3. Rosa's three-week gap; clinician reports miss patient-reported symptoms (sources in `docs/10` §2, unverified figures marked)
4. Between Visits in one picture: plan → call → nurse → review → sponsor
5. Demo screenshots: call, nurse acknowledgment, drafts with evidence
6. Safety by design: discloses AI, approved words only, no advice, rules grade, a human decides; real calls MEASURED
7. Site Signal: patient-reported reference stream vs site AE log, funnel, drill-down to quotes, CRA-approved query (SIMULATED)
8. How well it works and what it gets wrong: report card with intervals; Site Signal power at both tiers including the 25% and 50% rows, null false-flag rate with MC SE, failure case (all from the source files)
9. Readiness: MIT, one command, demo mode, CI, requirement ↔ test traceability, pre-registered analysis plan, audit hash chain
10. Next steps: retrospective validation on trials with paired patient- and clinician-reported data, a pilot with one site, more languages, EDC/FHIR integration

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

- Links: GitHub repository (private; reviewer access arranged by the team lead), YouTube video (unlisted), deck PDF, public demo URL.
- "Built with": ElevenLabs, Claude (Anthropic API), FastAPI, Next.js, SQLite, TypeScript, Python, numpy, scipy.
- All four teammates added as contributors.
- Every number in the Devpost text matches its source file.
