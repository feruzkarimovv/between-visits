# 00 · Product overview

**Between Visits** is a voice agent that phones cancer-trial patients between clinic visits, asks validated symptom questions in the patient's language and at the patient's pace, pages a human nurse within seconds when something is urgent, and hands the study team draft adverse-event (AE) and medication entries with the patient's own words as evidence. When the investigator marks an event serious, it drafts the sponsor notification and starts the 24-hour clock.

Tagline: **No symptom waits for the next visit, in any language, at any pace.**

## The problem

- Trial patients see their study team every few weeks. Side effects start in between. Today they surface at the next visit, from memory. NCI found that clinician-reported AEs under-detect the symptoms patients actually feel, which is why it built PRO-CTCAE.
- Urgent symptoms mentioned casually (or not at all) are not escalated. In PD-1 immunotherapy trials, diarrhea can be the first sign of immune-related colitis, which the example study's protocol treats as urgent at 7 or more stools a day above baseline.
- **Regeneron's own feedback (Sat Oct 10, mentor conversation):** patients who don't speak English and patients who move slowly are the hardest to reach and keep. Most tools (English-only staff, apps, fast voice bots) fail exactly these people.
- Late or wrong AE data creates queries, late serious-event reports, and slower database lock (Tufts CSDD: 8 days visit-to-entry, 36 days last-visit-to-lock). Sponsors must report serious unexpected suspected reactions to FDA within 15 days (7 if fatal or life-threatening).
- **On the sponsor side**, clinicians record fewer of the symptoms patients feel, across the trials and sites studied (across three randomized trials, physicians did not report 40.7–74.4% of patient-reported symptomatic toxicities; Di Maio, *J Clin Oncol* 2015;33:910; secondary summary, UNVERIFIED), and site monitoring is 9–14% of trial cost (Sertkaya, *Clin Trials* 2016;13:117; secondary summary, UNVERIFIED). Today's AE key risk indicators compare one site's AE log with other sites' AE logs, so they cannot tell a site with healthier patients from a site that misses AEs. Sources and verification status: `docs/10-site-signal.md` §2.

## Users

| Role | What they do in Between Visits |
|---|---|
| Patient (synthetic persona, played by a teammate) | Receives the check-in call. Speaks English or Spanish. May need extra time. May have a caregiver answer. |
| Research coordinator | Starts or schedules check-ins, watches live calls, reviews and confirms draft entries. Main dashboard user. Answers site queries in the mock site inbox, which stands in for the coordinator of whichever site was queried (Site Signal, planned). |
| On-call nurse | Gets paged for urgent findings, acknowledges, calls the patient back (human-to-human, outside our system). |
| Principal investigator | Marks seriousness and relatedness, signs the serious-event report. |
| Sponsor safety team (mock) | Receives the serious-event notification in a mock "sponsor safety inbox". Represents Regeneron's side. Can view Site Signal and run blind runs; cannot draft or send site queries (planned). |
| CRA / central monitor (sponsor side, mock; new role `cra`, planned) | Reviews the Site Signal ranking and funnel, opens a site to read its patients' own words, drafts and approves templated data-completeness queries to the site, and closes them once the site answers. The only role that drafts, edits, approves or closes a site query. Demo identity: Sam Rivera, "CRA (sponsor)". |

## What we build (scope)

1. **Approved check-in plan** for an example open-label oncology study (NCT02760498, a PD-1 immunotherapy study with a public protocol): which symptoms to ask, red-flag rules, call schedule (days 1, 3 and 7 after each dose). Seeded; stretch: generated from a protocol PDF by Gemini and approved by a human.
2. **Outbound check-in call** (phone via Twilio, or in-browser) by an ElevenLabs agent running on Claude (Gemini was the original plan; switchable with `ELEVENLABS_LLM`). Discloses it is an AI, offers a human, asks plain-language symptom questions (our own wording, structured like NCI's PRO-CTCAE; official items can be plugged in by registered studies) using only approved wording in English or Spanish, adapts to "extra time" pace, supports caregivers. The model the deployed agent actually uses is pinned and recorded in `agent/deployed_snapshot.json` (planned, task V9).
3. **Deterministic rules engine**: answers are recorded as enums and numbers; fixed CTCAE v5 rules produce *provisional* grades; a fixed red-flag table decides escalation level.
4. **Escalation**: urgent or emergency findings page the on-call nurse immediately (push notification with an Acknowledge button; a Twilio "press 1" call is optional), with an acknowledgment timer and re-page.
5. **Post-call pipeline**: transcript stored with timestamps; Claude extracts any missed symptoms and new medications with evidence spans; a safety-net scan catches red flags the live call missed; non-English quotes get a labeled AI translation.
6. **Review workflow**: coordinator confirms, edits or rejects each draft; investigator sets seriousness and relatedness; everything is audited.
7. **Sponsor handoff**: serious events produce a draft notification (minimum valid-case fields + narrative), a 24-hour clock from site awareness, investigator signature, and delivery to a mock sponsor safety inbox.
8. **Safety report card**: an evaluation harness runs 20 simulated patients (English/Spanish × standard/extra-time) and reports escalation recall, AE capture, grade agreement, advice refusals, disclosure, and pace metrics, broken down by language and pace, with known misses.
9. **Readiness kit**: MIT license, one-command local run, demo mode that works without API keys, CI, and a mini validation pack (requirement ↔ test ↔ result). Planned for Checkpoint A (`docs/09`): full-history secret scan, pinned toolchain, production Docker images, a public replay-only demo instance plus a private live instance, `SECURITY.md` and `docs/privacy-security.md`, a hash-chained audit log, and Clopper-Pearson 95% intervals on every report-card proportion.
10. **Site Signal (sponsor side, planned Sun Oct 11; `docs/10-site-signal.md`, SAP in `docs/11-site-signal-sap.md`).** For each site, compares the site's own AE log with what that site's patients reported to the voice agent, adjusted for the mix of moderate (grade 2) diarrhea and breathlessness episodes. Output is *capture discordance*: a reason to look, not a finding.
    - Unit: new or worsened rule-graded grade ≥ 2 episodes of Diarrhea, Fever and Dyspnea (the only terms with grade 2 and 3 rules), matched to site-originated AEs by CTCAE term, with a window that looks back to the patient's previous call (patients report after onset) and 7 days forward. Episodes on a call that paged the nurse form a separate stratum; episodes still inside the site's entry window are "pending", never "missed".
    - Statistic: leave-one-site-out observed/expected with an overdispersion-adjusted funnel. Two tiers, **Watch** and **Look**, with thresholds from a null model pre-registered under the git tag `sap-v1` before any evaluation output exists. Sites with too little data or low call completion show grey "Not computed"; no tier is green.
    - Comparators on the identical data: a gsm-style AE-rate indicator and simaerep classic (legacy).
    - Every flag drills down to the patients' verbatim words. A CRA approves every templated, data-completeness-only site query; the coordinator answers in a mock site inbox; every step is audited.
    - Also: a demo-only blind run (any typed seed, hidden planted count, audited reveal), an equity panel (capture by language and pace within sites), and a "what it gets wrong" page with numbers only from `validation/site_signal/summary.json`.
    - Data: a simulated 20-site study (badged SIMULATED) plus live or replayed calls at site 101 (badged MEASURED). No LLM anywhere on this path.

## Non-goals (say "no" fast)

Diagnosis, treatment or medication advice, causality assessment by AI, real patient data, real EDC/EHR integration, MedDRA coding, blinded studies, consent, clinic scheduling, wearables, camera vitals, pill-bottle photos, chart-note scanning. (Inbound calls exist only as a demo fallback.)

For Site Signal specifically:

- **No misconduct determination.** Capture discordance is not evidence of fraud, misconduct or a protocol deviation; it includes legitimate clinical judgment (baseline symptoms recorded as history, attribution, grade 1 omissions). The product never calls it under-reporting.
- **No automated site action.** Nothing reaches a site unless a CRA approves a templated query, and the site inbox is a mock. No site score is shared with sites; no EDC, CTMS or e-mail integration.
- **No real-world validity claim.** Both streams in the 20-site study are simulated; the planted-site results show method and power. The non-circular test, retrospective validation on trials with paired patient-reported and clinician-reported data, is a next step, not part of this build.
- **No LLM in the statistics**, no new grading of terms without a CTCAE rule, and shadow mode only (the site enters AEs from its own visits; drafts are reviewed sponsor-side during the analysis period; a site where drafts reach site staff is shown "Not computed").

Anything cut under the rules in `docs/09-timeline-and-workstreams.md` is listed in `NOT_BUILT.md`.

## Non-negotiable product rules

These are also in `CLAUDE.md`. Every pull request is checked against them.

1. **The LLM listens, rules grade, humans decide.** No grade, red-flag decision or escalation level is produced by an LLM at runtime. The LLM maps speech to enums and numbers; deterministic backend code decides. Statistical site flags (Site Signal) come only from pre-specified code driven by `data/signal_rules.json` and the `sap-v1` parameters; a human decides whether to act.
2. **Approved words only.** Clinical content the agent says (questions, response options, escalation lines, deferrals) comes verbatim from `data/scripts.json` and `data/symptom_items.json` in the patient's language. Never machine-translated on the fly.
3. **No medical advice, ever.** Medical questions get the approved deferral line and become a task for the nurse.
4. **Disclose and offer a human.** The first sentence of every call says it is an automated AI assistant and that the patient can ask for a person at any time.
5. **Emergencies:** the standard line "If this is an emergency, hang up and call 911" plus an immediate page.
6. **Evidence on everything.** Every draft entry links to a verbatim quote (original language), its timestamp in the call, and its source (live tool call or post-call extraction).
7. **Nothing is final without a human**, and every human action writes an audit event.
8. **Synthetic data only.** Only call teammates' phones that consented. Refer to the study drug by class, never as a named product.
9. **No licensed content in git:** no PRO-CTCAE item text, no MedDRA codes or hierarchy, no WHODrug. See `docs/05-clinical-rules.md` § Licensing.
10. **Equity is measured.** Every safety metric is reported separately for English vs Spanish and standard vs extra-time pace.

## Demo in one paragraph

A protocol-derived check-in plan is shown as approved. The coordinator starts Rosa's day-3 check-in (Spanish, extra time). The call runs in the browser (phone calling is built but not connected for the hackathon); the agent discloses it is an AI, asks if now is a good time, asks the diarrhea question, waits patiently, repeats when asked, reads back "seven times a day, usually once". The dashboard shows *Diarrhea · provisional grade 3* with the rule that fired. Rosa adds that she got dizzy standing up: red flag, the agent says the approved urgent line, the nurse's phone buzzes with an urgent push and one tap acknowledges it, the dashboard shows "acknowledged in N seconds, Spanish speaker, use interpreter line". After the call, the review queue shows drafts with Rosa's Spanish quotes and labeled English translations. The investigator marks the AE serious (hospitalized for IV fluids); the 24-hour clock starts; the signed notification lands in the mock sponsor inbox. The report card closes the site-side part: 20 simulated patients, metrics split by language and pace, one known miss.

**Sponsor side (Site Signal, planned; storyboard in `docs/08-demo-and-pitch.md`).** The view switches to the CRA: a simulated 20-site study (badged SIMULATED) on a funnel plot, ranked by capture discordance, next to the AE-rate indicator and simaerep classic (legacy). Opening a flagged site shows its unmatched episodes with the patients' words in English or Spanish; Rosa's episode at site 101 appears as MEASURED, in the separate paged stratum because her call paged the nurse. The CRA approves a templated query, the coordinator answers it in the mock site inbox, and the audit log shows each step. A blind run on a typed seed, the answer-key reveal and the "How well it works" tab show what the indicator catches and what it misses.

## Hackathon submission

- Built for HackRU Fall 2026 (Social Good track: language access and older patients in cancer trials).
- Deliverables: MIT-licensed GitHub repo, ~3 minute demo video, 10-slide deck (`docs/08-demo-and-pitch.md`), clear README.
- The repository is private for now. How reviewers get access is decided by the team at submission; any change of visibility is a human decision made after a fresh secret scan (`docs/09-timeline-and-workstreams.md`).
