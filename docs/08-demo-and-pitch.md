# 08 · Demo, pitch and submission

Numbers in [brackets] must come from your real runs. Never script them.

> **Decision (Sat Oct 10, ~8 PM):** LLMs moved from Gemini to Claude (Anthropic API credits): voice agent on Claude Sonnet 5.5 via ElevenLabs; post-call pipeline Haiku 5.5 / Opus 5.5; evaluation agent = same model as the voice agent.
>
> **Decision (Sat Oct 10, 6:30 PM):** no Twilio for the hackathon. Patient calls run in the browser (same ElevenLabs agent, same tools, same pipeline); the nurse page is ntfy and needs no Twilio. Phone calling stays in the code (`make sync-agent`, `ELEVENLABS_PHONE_NUMBER_ID`) for a real deployment.

## 30-second pitch (mentors, hallway, Devpost tagline source)

"Regeneron's team told us the patients trials struggle with most are the ones who don't speak English and the ones who need more time. Between Visits is a voice agent that calls cancer-trial patients in the days after a dose, in their language and at their pace. It asks plain-language symptom questions, the National Cancer Institute's CTCAE rules grade the answers, and anything urgent pages the on-call nurse within seconds. The study team gets draft side-effect entries with the patient's own words as evidence, and serious events go to the sponsor with the 24-hour clock running. The AI listens, rules grade, humans decide."

## 3-minute video script

| Time | Screen | Voiceover / audio |
|---|---|---|
| 0:00–0:20 | Title card, then Rosa's profile: 74, Spanish, extra time, day 3 after dose | "We asked Regeneron what's broken in trials. They told us: patients who don't speak English, and patients who need more time. Rosa is 74, speaks Spanish, and lives an hour from her cancer center. She just had her second dose. Her next visit is in three weeks." |
| 0:20–0:35 | `/plan`: approved check-in plan, EN and ES wording side by side, red flags | "Between Visits runs on a check-in plan the study team approves: plain-language symptom questions written in English and Spanish, graded with the National Cancer Institute's CTCAE, and red flags taken from the drug's patient guide." |
| 0:35–1:25 | `/checkins/[id]` split screen, real call audio with subtitles | Real audio: disclosure in Spanish → "¿Es buen momento?" → diarrhea question → Rosa: "¿Cómo?" → agent repeats slowly → "Como siete u ocho veces al día... normalmente una" → read-back → dashboard shows *Diarrhea · provisional grade 3* with rule → "Y me mareé al levantarme" → agent says the approved urgent line. Voiceover (short, over the dashboard): "It waits, repeats, and reads back. A fixed CTCAE rule, not the AI, sets the grade." |
| 1:25–1:45 | Nurse's phone buzzes on camera with an urgent push; one tap on Acknowledge; panel turns green | "The on-call nurse is paged in seconds, told Rosa prefers Spanish, and acknowledges in [N] seconds. The agent never gives medical advice. Its job is to get the right human, fast." |
| 1:45–2:15 | `/review`: drafts with Spanish quotes + labeled English translation; confirm; investigator marks serious (hospitalized for IV fluids); `/sae` 24-hour clock; `/sponsor` inbox receives it | "Every entry is a draft with the exact words and second it came from. When the investigator marks it serious, the sponsor report is drafted and the 24-hour clock starts. What used to surface at the next visit reaches the sponsor the same day." |
| 2:15–2:45 | `/report-card`: metrics, equity table EN vs ES and standard vs extra time, known miss, validation badge | "We test it on 20 simulated patients on every change: chest pain, a caregiver answering, someone asking for medical advice. It catches [x of y] urgent cases in Spanish and in English. Here's one case we still get wrong, and our fix." |
| 2:45–3:00 | Architecture strip, GitHub, MIT, `make demo` | "Between Visits. Open source, runs from a clean clone, built on ElevenLabs and Claude. No symptom waits for the next visit, in any language, at any pace." |

Recording tips: record a real browser call (not dramatized), use a quiet room and a headset or good mic for Rosa's side, add subtitles for Spanish audio, keep the dashboard at 125% zoom, record screen at 1080p. Upload as unlisted YouTube.

## Live demo at the judging table (about 2 minutes)

Roles: **A** pitches, **B** plays Rosa (headset plugged into the dashboard laptop: the browser call runs where it's started), **C** drives the dashboard and holds the nurse phone, **D** answers technical questions.

1. A (15 s): the Regeneron feedback line + Rosa in one sentence. "Let's call her."
2. C clicks **Call in browser** on Rosa's row; B answers on the headset plugged into that laptop. (Phone calling is built but off: Twilio's outbound approval wouldn't clear before judging.) Run the call, answering quickly; let the judge hear the disclosure, one patient-paced repeat, and the red flag (≈ 60 s).
3. C holds up the nurse phone with the urgent push, taps Acknowledge, shows the green acknowledgment, then the review queue and sponsor clock (≈ 25 s).
4. A (15 s): "The AI listens, rules grade, humans decide. And we prove it" → report card equity table.
5. A: "Want to try to break it? Ask it for medical advice." Hand the judge the browser call (headset).

Backup: if the call fails, say "Here's the recorded call from this morning" and run **Replay scenario → rosa_es_urgent**. Practice switching in under 10 seconds.

## Deck (11 slides, ≤ 12)

1. Between Visits: tagline, team, track and prizes
2. What Regeneron told us: non-English speakers and patients who need more time
3. Rosa's three-week gap; NCI: clinician reports miss patient symptoms
4. Why sponsors feel it: late AE data, late serious-event reports, 7/15-day FDA clocks, 36 days to lock
5. Between Visits in one picture: plan → call → nurse → review → sponsor
6. Demo screenshots (call + dashboard)
7. Built for every patient: official translations, extra-time pace, caregivers, repeat-back
8. Safety by design: discloses AI, approved words only, no advice, 911/988 lines, rules not AI grade, human decides
9. Evidence: report card + equity split + known miss
10. Readiness: MIT, one command, demo mode, CI, requirement ↔ test traceability; architecture
11. What's next: EDC/FHIR integration, more languages, inbound line, a pilot with one site

## Judge Q&A cheat sheet

- **Why voice, not an app?** Apps work for people who use apps. Voice works on any phone, for older patients and people with low vision or literacy, in their language, and a conversation catches what forms miss ("I went to urgent care and got an antibiotic").
- **Isn't an AI calling sick patients risky?** It says only pre-approved words, says it's an AI, offers a human, never gives advice, and escalates by fixed rules. Each of those is a tested requirement.
- **What if it grades wrong?** Grades are provisional, come from CTCAE rules, and a clinician confirms every entry. Our known miss is [X]; fix is [Y].
- **How is translation safe?** Every question is pre-written in both languages and reviewed by a fluent speaker; the AI never translates clinical questions live. Studies registered with NCI can load the official PRO-CTCAE translations instead. Patient answers keep the original words as evidence; English translations are labeled for verification.
- **How is this different from symptom apps or the 2024 voice tracker?** Those log symptoms. We close the loop: standard questions, rule-based grading, nurse paged in seconds, trial-ready entries with evidence, and the sponsor report drafted on the clock.
- **Who uses it?** The site's study team. Sponsors could provide it to sites the way they provide patient apps today.
- **What was technically hard?** Live voice with mid-conversation tool calls, a backend-driven interview so the AI can't skip or invent questions, predictable escalation, and the simulated-patient evaluation.
- **Why not NCI's PRO-CTCAE questions directly?** NCI's terms don't allow redistributing or modifying them in an open-source repo, so we wrote our own and built a local plug-in for studies that register with NCI.
- **What did you build vs use?** Used ElevenLabs and Claude (Anthropic API). Built the interview engine, rules, escalation and paging, post-call pipeline, review and sponsor workflow, evaluation harness, validation pack.

## Devpost submission (by 9:30 AM)

- Track: **Social Good**. Superlatives: **Regeneron: Best Clinical Trial Solution** and **Use of ElevenLabs**.
- Links: GitHub repo (public, MIT), YouTube video, deck (PDF or Slides), optional live demo URL.
- "Built with": ElevenLabs, Claude (Anthropic API), FastAPI, Next.js, SQLite, TypeScript, Python.
- Add all four teammates as contributors.
- After awards (if placed): each member fills `regn.link/jedi` with the Devpost link.
