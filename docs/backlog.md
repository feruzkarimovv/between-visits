# Backlog · GitHub issues

The work considered for Between Visits and Site Signal that this submission does not build. This file is the source list for task R11 (WS0, Checkpoint C): each entry becomes one GitHub issue, and `NOT_BUILT.md` (task D13) links every item to its issue number. The README Roadmap links the issue list.

Written Sun Oct 11 (planning round). The repository is private; issues are created in it as is. Changing visibility is not part of this work.

## 1. Labels

Every issue carries `not-built`. R11's acceptance check counts that label (≥ 20 open issues, plus one per cut). Issues add one or more of the other labels.

| Label | Meaning | Suggested color |
|---|---|---|
| `not-built` | In scope of the idea, not built for this submission | `BFD4F2` |
| `known-miss` | A failure seen in our own evaluation | `F9D0C4` |
| `security` | Security, privacy or compliance gap | `D93F0B` |
| `pilot` | Needs real-world partners, data, legal or clinical review, or approvals; cannot be done with synthetic data alone | `C2E0C6` |
| `statistics` | Site Signal statistics and validation | `5319E7` |

```bash
gh label create not-built  --force --color BFD4F2 --description "In scope of the idea, not built for this submission"
gh label create known-miss --force --color F9D0C4 --description "A failure seen in our own evaluation"
gh label create security   --force --color D93F0B --description "Security, privacy or compliance gap"
gh label create pilot      --force --color C2E0C6 --description "Needs real-world partners, data, review or approvals"
gh label create statistics --force --color 5319E7 --description "Site Signal statistics and validation"
```

## 2. Issue body template

`.github/ISSUE_TEMPLATE/not-built.md` (R11) uses these sections. Each entry below gives the content for them.

```markdown
---
name: Not built
about: Work considered for Between Visits that the submission does not build
labels: not-built
---
**Summary** One or two sentences.
**Today** What exists now, with file paths.
**Proposal** What to build or decide.
**Done when** A checkable acceptance test.
**Constraints** Which CLAUDE.md rules apply and how they hold.
**References** Docs, tasks, sources.
```

Creating an issue: write the body to a temporary file outside the repo, then run `gh issue create --title "<title>" --label "<labels>" --body-file <file>`, then add the issue number next to the item in `NOT_BUILT.md`.

Wording rules for every issue body:
- Neutral voice.
- Drugs by class only (anti-PD-1, CD3 bispecific).
- Subject IDs only, no real phone numbers.
- No licensed text.
- "Capture discordance", never "under-reporting", "fraud" or "misconduct".
- Site Signal numbers only from `validation/site_signal/summary.json`.

## 3. Summary

| ID | Title | Labels | Area |
|---|---|---|---|
| BL-01 | Re-verify real voice calls on every agent change and measure speech error | `not-built` | Voice (WS1) |
| BL-02 | Outbound phone calls and warm transfer through Twilio | `not-built`, `pilot` | Voice (WS1, WS2) |
| BL-03 | A third language with professionally translated, approved wording | `not-built`, `pilot` | Voice, data (WS1, WS4) |
| BL-04 | P19: route unconfirmed safety-net red flags to a nurse callback | `known-miss`, `not-built` | Safety path (WS2, WS4) |
| BL-05 | Approved onset-date item for symptoms | `not-built` | Clinical content (WS4) |
| BL-06 | Grading rules for more symptom terms, with clinical review | `not-built` | Clinical content (WS4) |
| BL-07 | Design notes: spoken neuro-check after CD3 bispecific step-up dosing | `not-built`, `pilot` | New study pack |
| BL-08 | Design notes: long-term follow-up caller | `not-built`, `pilot` | New study pack |
| BL-09 | Chart-note stream as a second evidence source | `not-built` | Capture (WS2, WS4) |
| BL-10 | Protocol-to-plan: draft the check-in plan from a protocol, human-approved | `not-built` | Plan (WS2, WS3) |
| BL-11 | Retrospective validation of Site Signal on trials with paired patient- and clinician-reported data | `not-built`, `statistics`, `pilot` | Site Signal (WS5) |
| BL-12 | Port simaerep's inframe default (v1.0.0) as a comparator | `not-built`, `statistics` | Site Signal (WS5) |
| BL-13 | Data-fitted null model and misspecification diagnostics | `not-built`, `statistics` | Site Signal (WS5) |
| BL-14 | Indicator for integrated mode: draft rejection behavior | `not-built`, `statistics` | Site Signal (WS5) |
| BL-15 | Secondary Site Signal analyses: entry-lag KRI and a mixed model | `not-built`, `statistics` | Site Signal (WS5) |
| BL-16 | Synthea-derived cohort beyond the roster | `not-built`, `statistics` | Site Signal (WS5) |
| BL-17 | Sponsor-supplied MedDRA coding hook for matching | `not-built`, `pilot` | Site Signal (WS5, WS4) |
| BL-18 | Real authentication and role-based access control | `not-built`, `security` | Platform (WS0, WS2, WS3) |
| BL-19 | Production hardening and compliance assessment | `not-built`, `security` | Platform (WS0) |
| BL-20 | Regulatory review of the sponsor-side patient stream | `not-built`, `pilot` | Regulatory |

Conditional issues, created only if a cut rule fires, are in §5.

## 4. Issues

### Voice and reach

#### BL-01 · Re-verify real voice calls on every agent change and measure speech error

Labels: `not-built`

- **Summary.** Real calls work and are re-verified at submission time, but the safety evaluation is text-mode. Speech-recognition and accent error are unmeasured.
- **Today.**
  - A real ElevenLabs browser call works.
  - Task V10 logs three MEASURED calls against the deployed live backend in `eval/results/voice_checks.json`: en-standard grade 2 diarrhea, en-standard grade 3 red flag, es-extra_time.
  - Task V9 pins the agent LLM and snapshots the deployed configuration (`agent/deployed_snapshot.json`, with a CI hash check).
  - The 20-persona evaluation (`eval/results/latest.json`) is text-mode with simulated patients.
- **Proposal.**
  1. Re-run the three-call check automatically whenever the snapshot hashes change.
  2. Run all 20 personas by voice (teammates, or recorded synthetic audio), in both languages and both paces.
  3. Report AE capture, grade agreement and red-flag recall by language and pace, each with a Clopper-Pearson interval, as a separate MEASURED row that is never pooled with text mode.
  4. Log utterance-to-page and page-to-acknowledgment times.
- **Done when.**
  - `voice_checks.json` holds ≥ 20 voice-mode persona calls.
  - The report card shows the real-voice row with intervals.
  - Every speech-driven miss is listed under known misses.
- **Constraints.**
  - Rule 4 (disclosure and human offer) is checked on every call.
  - Synthetic personas only, with written consent for any recorded voice.
  - Audio is never committed.
- **References.** `docs/07`, `docs/04`, tasks V9–V11.
- **If the 03:30 hard box was missed.** Add to the body: "Not met at submission; demo calls are labeled recorded or scripted, and ElevenLabs claims are limited to `voice_checks.json`."

#### BL-02 · Outbound phone calls and warm transfer through Twilio

Labels: `not-built`, `pilot`

- **Summary.** Patients without a computer or smartphone need a plain phone call. Today the agent runs only in the browser.
- **Today.**
  - The outbound path exists in code: `backend/app/services/elevenlabs.py`, the ElevenLabs native Twilio outbound call, and `twilio_call_sid` on check-ins.
  - It is not connected: the Twilio account upgrade, phone number, compliance profile and number import into ElevenLabs are pending.
  - An inbound call-in exists only as a demo fallback.
  - A warm transfer of the patient straight to the nurse (`transfer_to_number`) was on the original stretch list.
- **Proposal.**
  - Connect outbound calling for the four agent variants.
  - Add a warm transfer to the on-call nurse.
  - Handle voicemail and no-answer with a retry schedule and calling-hours rules.
  - Show the call channel on the check-in page.
- **Done when.** Three phone calls to teammates' phones complete end to end (same checks as BL-01), and a transfer reaches the nurse phone with the subject ID only.
- **Constraints.**
  - Real numbers only in `.env` and `data/patients.local.json` (rule 8).
  - Call only consenting people. The kit notes that the FCC treats AI voices as "artificial" under the TCPA; legal review is UNVERIFIED.
  - The disclosure and the offer of a human come first.
- **References.** `docs/04`, `CLAUDE.md` § Status (human setup pending).

#### BL-03 · A third language with professionally translated, approved wording

Labels: `not-built`, `pilot`

- **Summary.** Between Visits speaks English and Spanish. Patients who are more comfortable in another language are not reached, and their symptoms are missing from the reference stream.
- **Today.** Four agent variants (EN/ES × standard/extra-time). All clinical wording comes from `data/scripts.json` and `data/symptom_items.json` per language (rule 2).
- **Proposal.**
  - Pick a language from site roster need.
  - Have the full item set, scripts and red-flag read-backs professionally translated and clinically reviewed.
  - Add the variants to `agent/variants.json`.
  - Extend the evaluation personas to the new language at both paces.
- **Done when.**
  - Data validation passes for the new language.
  - Persona results are reported per language with intervals.
  - The equity panel shows the new stratum.
- **Constraints.** Never machine-translate clinical questions at runtime (rule 2). No licensed item wording in git (rule 9).
- **References.** `docs/04`, `docs/05`, `docs/07`.

### Safety path and clinical content

#### BL-04 · P19: route unconfirmed safety-net red flags to a nurse callback

Labels: `known-miss`, `not-built`

- **Summary.** One false urgent page in the 20-persona evaluation, in the Spanish extra-time group.
- **Today.**
  - Persona P19: the live call was correct. Frequency was recorded as "often", count and blood as unknown, and there was no live page.
  - The post-call safety net, which is told to include a flag when unsure, raised `RF_DIARRHEA_SEVERE` from "muchas veces, no sé cuántas", although the count threshold was never stated (`eval/results/latest.json` `known_misses`).
  - This is conservative by design: under rule 5, misses are worse than false alarms.
- **Proposal.**
  - When a safety-net hit's stated threshold is not met in the transcript, route it to a nurse callback task instead of an urgent page.
  - Keep urgent paging for explicit mentions.
  - Ship only after clinical review signs off on the trade-off.
- **Done when.**
  - P19 yields a callback.
  - All 8 red-flag personas still page at the expected level.
  - Unit tests cover explicit and unconfirmed safety-net hits in both languages.
  - The change is recorded in `validation/capa.md`.
- **Constraints.**
  - Rule 1: rules decide, so the change lives in rules and data, not in an LLM prompt.
  - Rule 5: when in doubt, escalate. The callback is still a human action with a timer.
  - This changes escalation behavior, so it needs clinical sign-off.
- **References.** `docs/05`, `docs/07` §1, `eval/results/latest.json`.

#### BL-05 · Approved onset-date item for symptoms

Labels: `not-built`

- **Summary.** The interview never asks when a symptom started, so AE start dates and Site Signal episode dates are call dates.
- **Today.**
  - `postcall.py` sets `onset_date = None` on drafts.
  - The AESTDTC fallback is the local call date.
  - Site Signal's match window looks back to the subject's previous call that reported the symptom below the episode's grade, minus 2 days, and 7 days forward from the call date (`docs/11` §4.3, §5).
- **Proposal.**
  - Add a short onset item ("about how many days ago did this start?") in our own wording, EN/ES, both paces, owned by WS4 in `data/`.
  - Record it as a number of days.
  - Use it for AESTDTC and for episode dates.
  - Amend the SAP: a new tag if the estimand changes, otherwise a §17 entry.
- **Done when.**
  - Drafts carry an onset date with a verbatim quote.
  - Exports use it.
  - Episode dates use onset when present.
  - Replay fixtures are regenerated, and tests cover the "unknown" answer.
- **Constraints.** Rule 2: approved wording only, no runtime translation. Rule 6: evidence on the draft.
- **References.** `docs/05`, `docs/11` §4.3, `docs/research/site-signal-methods.md` §7.

#### BL-06 · Grading rules for more symptom terms, with clinical review

Labels: `not-built`

- **Summary.** Only Diarrhea, Fever and Dyspnea have grade 2 and 3 rules, so every other symptom is reported but ungraded and outside the Site Signal primary analysis.
- **Today.**
  - `data/ctcae_rules.json`: Diarrhea, Fever and Dyspnea at grades 1–3; Fatigue and Dizziness at grade 1 only.
  - Nausea, Vomiting, Rash and Confusion have items but no rules.
- **Proposal.**
  - For each term, decide with a clinician whether CTCAE v5 grade criteria can be reached from patient-reportable inputs. Many depend on clinical information, such as interventions or labs, that a call cannot collect.
  - Where they can, add rules with boundary tests and the mutation probe.
  - Where they cannot, keep the term "reported, ungraded" and say why.
  - Do not create a table that converts patient-reported answers into CTCAE grades.
- **Done when.**
  - Each term is either a reviewed rule with boundary tests or a documented "ungraded" decision.
  - `data/validate_data.py` checks contiguity.
  - The SAP is amended before any added term enters Site Signal.
- **Constraints.** Rules 1 and 2. Grades are always "provisional". No PRO-CTCAE wording in git (rule 9).
- **References.** `docs/05` §4, `docs/11` §4.1, task D9.

### New study packs (design notes)

#### BL-07 · Design notes: spoken neuro-check after CD3 bispecific step-up dosing

Labels: `not-built`, `pilot`

- **Summary.** Step-up dosing of CD3 bispecific antibodies comes with a monitoring window for cytokine release syndrome and neurologic toxicity. How much of that window falls at home varies by product label (UNVERIFIED in this round; class only). A short spoken check could reach patients who struggle with apps.
- **Concept.**
  - A study pack on the existing engine.
  - A clinic baseline taken in the same language, pace and channel.
  - Short home checks at patient-chosen times in a defined window after step-up doses: naming, counting backward, repeating a sentence.
  - Caregiver yes/no questions.
  - A temperature read-back through the existing `RF_FEVER` rule.
  - Fixed rules score the raw transcript against the patient's own baseline.
  - A confirmed drop pages the on-call nurse before the agent continues.
- **Open questions** (no build until answered):
  1. The items and scoring must be our own wording, with clinical and linguistic validation in both languages. No published instrument text goes in git. Established clinician grading frameworks exist (ASTCT consensus, Lee et al. 2019, UNVERIFIED in this round), but they are clinician tools, not patient self-checks.
  2. Speech-recognition error on number words and slow speech may dominate scores, and is expected to fall hardest on Spanish-speaking and extra-time patients. Measure it first (BL-01) and publish the false-page rate per 100 checks by language and pace with intervals.
  3. Who covers overnight hours, and how the product says so plainly.
  4. Dosing windows vary by product label; refer to the class only.
- **Done when.** A design note is reviewed by a clinician and a linguist, with an evaluation plan and paging-burden estimate. No code.
- **Constraints.** Rules 1–5. No medical advice; the agent never interprets results to the patient.
- **References.** `docs/decisions/ADR-001-site-signal.md` alternative E.

#### BL-08 · Design notes: long-term follow-up caller

Labels: `not-built`, `pilot`

- **Summary.** Survival follow-up can run for years by phone and is easy to lose to staff turnover. The same agent could make the protocol's follow-up calls and hand every sensitive call to a human.
- **Concept.**
  - Schedule from `data/` (for example every 12 weeks in years 1–2, then less often).
  - Approved questions only: new treatment, hospital stays, best number and time, contacts still right.
  - A contact ladder with patient first, then authorized alternates who are asked no health questions, then a human task.
  - "Lost to follow-up", "withdrawn" and "deceased" are set only by a coordinator with a source, and audited.
  - A follow-up completeness view by site and subgroup.
- **Open questions:**
  1. Consent and calling rules for AI-voice calls to alternate contacts. The kit notes the FCC treats AI voices as "artificial" under the TCPA. Legal review is UNVERIFIED.
  2. Difficult news must never be exchanged without a human taking over (kit sheet "The Long Game" §10). Any sign of death, grief, withdrawal or severe illness triggers an immediate warm handoff.
  3. Idioms can trip a rule-based detector (for example "se me murió el celular", "my phone died"). Measure false handoffs per 100 calls by language.
  4. Completeness statistics need real follow-up data to mean anything.
- **Done when.** A design note is reviewed by a coordinator and a clinician, with a legal question list. No code.
- **Constraints.** Rules 3, 4, 5 and 7. Subject IDs only in pages.
- **References.** ADR-001 alternative F.

#### BL-09 · Chart-note stream as a second evidence source

Labels: `not-built`

- **Summary.** Some AEs and medication changes appear only in clinic notes, triage notes or patient portal messages. A second source would catch them and corroborate call findings.
- **Today.** Chart-note scanning is a non-goal in `docs/00`. Synthea's generated notes are generic lists with no symptom narrative (`docs/research/synthea.md` §3).
- **Proposal.**
  1. Update `docs/00` scope first.
  2. Write synthetic notes from an answer key. Include indirect mentions, negations, resolved prior-cycle symptoms, caregiver messages in Spanish, and copied-forward lines.
  3. An LLM returns enums plus an exact quote. A deterministic check drops any finding whose quote is not verbatim in the note.
  4. A data file decides which statuses create drafts.
  5. Merge with call findings into one draft per event, keeping quotes from every source.
- **Done when.**
  - Precision and recall against the answer key are reported with intervals, by note type and language.
  - The quote-fidelity failure rate is reported.
  - Recurrence and copy-forward cases are listed as known misses.
- **Constraints.**
  - Rule 1: the LLM maps text to enums; rules decide.
  - Rule 6: verbatim evidence.
  - Rule 8: synthetic notes only.
- **References.** ADR-001 alternative B, kit sheet "How Are You Feeling?" (Better tier).

#### BL-10 · Protocol-to-plan: draft the check-in plan from a protocol, human-approved

Labels: `not-built`

- **Summary.** The check-in plan (items, red flags, schedule) is seeded by hand for one example study. Drafting it from a protocol would speed up setting up a new study.
- **Today.** Seeded plan in `data/`. This was a stretch goal in the original plan (`docs/00` scope item 1; `docs/09` history).
- **Proposal.**
  - An LLM proposes which existing approved items and red-flag rules apply, and the call schedule, citing protocol page numbers.
  - A human approves each line. Unapproved lines never reach the agent.
- **Done when.** A plan draft for the example study matches the seeded plan, or each difference is explained. Approval writes AuditEvents.
- **Constraints.**
  - Rule 2: the LLM selects from approved wording and never writes new clinical text.
  - Rule 7: human approval, audited.
- **References.** `docs/05`, `docs/03`.

### Site Signal statistics

#### BL-11 · Retrospective validation of Site Signal on trials with paired patient- and clinician-reported data

Labels: `not-built`, `statistics`, `pilot`

- **Summary.** Every Site Signal result in this repo uses a simulated study. The test that does not depend on our simulator is a completed trial that collected patient-reported symptoms and the clinician AE log for the same patients, with site IDs.
- **Today.** A pre-registered simulation (`docs/11`) and results in `validation/site_signal/summary.json`, all labeled SIMULATED. Whether suitable data are available to us is UNVERIFIED.
- **Proposal.**
  1. Pre-register a new SAP version and tag before data access. Define episodes on the instrument's own scale; never convert answers to CTCAE grades.
  2. Check the null in real data: the z\* distribution, φ̂, and the share of sites in each tier.
  3. Test association with quality evidence collected without the patient stream: monitoring and audit findings, source-data verification discrepancies, query rates.
  4. Check stability between early and late halves.
  5. Check whether discordance concentrates where clinical judgment legitimately differs.
  6. Compare rankings with a plain AE-rate KRI.
- **Done when.**
  - The protocol is written and tagged.
  - A data-access agreement is in place.
  - Results are reported in aggregate, including a null result.
- **Constraints.** No patient data in git. Licensed instruments and MedDRA stay with the data holder (rule 9). No LLM on this path.
- **References.** `docs/research/site-signal-methods.md` §8, `docs/10` §10.

#### BL-12 · Port simaerep's inframe default (v1.0.0) as a comparator

Labels: `not-built`, `statistics`

- **Summary.** The comparator is "simaerep classic (legacy)". Since v1.0.0, simaerep defaults to the inframe method.
- **Today.**
  - `monitoring/bvsignal/simaerep_classic.py` ports the `visit_med75` algorithm and is fixture-tested against the v1.0.0 regression data.
  - The v1.0.0 `NEWS.md` lists the new defaults: `inframe = TRUE, mult_corr = TRUE, visit_med75 = FALSE, under_only = FALSE`.
- **Proposal.**
  - Port the inframe method (table operations, fixed seeds) under the MIT license, with an R fixture test.
  - Add it as a fourth indicator, calibrated by the same null procedure, with a SAP amendment.
- **Done when.**
  - The fixture test matches R within the documented tolerance.
  - The power table shows the inframe row at both tiers.
- **Constraints.** MIT attribution in `monitoring/README.md`. Numbers only from `summary.json`.
- **References.** `docs/11` §10.2, `docs/research/site-signal-methods.md` §3.1.

#### BL-13 · Data-fitted null model and misspecification diagnostics

Labels: `not-built`, `statistics`

- **Summary.** Look and Watch thresholds come from a null pre-registered at assumed parameters. If real sites differ more than assumed, the false-flag rate is higher than stated.
- **Today.** A fixed parametric null calibrated once at the `sap-v1` design. A misspecification sensitivity analysis is reported (`docs/11` §9, §12.6).
- **Proposal.**
  - Estimate between-site and patient-level capture variation from the study itself, for example with a mixed model.
  - Recalibrate thresholds by parametric bootstrap from the fitted model.
  - Add diagnostics: observed vs null distribution of z\*, and φ̂ against its null distribution.
  - Pre-register the procedure as a new SAP version.
- **Done when.** Null false-flag rates of the fitted procedure are reported with Monte Carlo SE across the misspecification grid.
- **Constraints.** No LLM. The pre-registration order is kept.
- **References.** `docs/11` §9, §12.6.

#### BL-14 · Indicator for integrated mode: draft rejection behavior

Labels: `not-built`, `statistics`

- **Summary.** Site Signal assumes shadow mode: the site enters AEs from its own visits. Once Between Visits drafts reach sites, the AE log is no longer independent of the patient stream, and capture discordance stops being valid.
- **Today.** Only shadow mode is supported (`docs/10` §4.1). Rejecting a draft already requires a reason in the review workflow.
- **Proposal.** Design a per-site indicator from the review queue:
  - the rate at which rule-graded, quote-backed drafts are rejected;
  - the time to review;
  - the distribution of rejection reasons.

  It must not penalize legitimate rejections ("not an AE per investigator", "recorded as history").
- **Done when.** An SAP section and a simulation show its operating characteristics at both tiers.
- **Constraints.** Rules 1 and 7. Wording stays "a reason to look, not a finding".
- **References.** `docs/10` §4.1, `docs/11` §2.4.

#### BL-15 · Secondary Site Signal analyses: entry-lag KRI and a mixed model

Labels: `not-built`, `statistics`

- **Summary.** Two analyses were proposed and left out of the pre-registered plan to keep the scope small.
- **Proposal.**
  1. An entry-lag KRI: days from episode date to the site's `entered_on`, per site, calibrated like the other indicators.
  2. A logistic mixed model, capture ~ term × band + language + pace + (1 | site) + (1 | patient), reporting site random effects with intervals as a cross-check on the O/E ranking.
- **Done when.** Both are pre-registered in a SAP amendment and reported in `report.md` as secondary, not used for tiers.
- **Constraints.** Kept in `monitoring/`. No new heavy dependencies in the backend.
- **References.** `docs/11` §8, §16.

#### BL-16 · Synthea-derived cohort beyond the roster

Labels: `not-built`, `statistics`

- **Summary.** If used at all (task S10, optional), Synthea supplies only a language and age mix, for a labeled sensitivity analysis.
- **Today.** The committed study, calibration, validation and blind runs use the parametric roster frozen at `sap-v1`. An optional `monitoring/cohort/roster.json` with age and language only feeds `make site-signal ARGS="--roster synthea"` (`docs/research/synthea.md`).
- **Proposal.**
  - If S10 was dropped: build the roster as specified.
  - Otherwise: evaluate whether baseline comorbidity and medication context adds anything to the simulation, mapped to our own labels with no SNOMED codes.
- **Done when.** Either roster.json is committed with its manifest, the `report.md` "Roster source" sensitivity section and a §17 clarification in `docs/11` (the committed outputs unchanged), or a note explains why more Synthea content adds no statistical value.
- **Constraints.** Rule 9: no SNOMED, LOINC or RxNorm codes, raw output or jar in git. Rule 8: real organization names are never read.
- **References.** `docs/research/synthea.md`.

#### BL-17 · Sponsor-supplied MedDRA coding hook for matching

Labels: `not-built`, `pilot`

- **Summary.** Site Signal matches episodes to site AEs by CTCAE term plus our own synonym list. Real sites write verbatim terms that are coded later, and equivalent terms such as diarrhea and colitis can split.
- **Today.** Synonyms live in `data/signal_rules.json`. MedDRA is excluded by rule 9.
- **Proposal.**
  - Add an optional, gitignored local mapping file supplied by a licensed sponsor (pattern: `data/local/`). It maps verbatim site terms to coded terms.
  - The matcher uses it when present and falls back to the synonym list otherwise.
  - Report the match rate under both.
- **Done when.** Tests pass with a synthetic, non-MedDRA stand-in mapping, and the code path never reads a committed MedDRA file.
- **Constraints.** Rule 9: no MedDRA codes or hierarchy in git, ever.
- **References.** `docs/11` §5.

### Security, privacy and regulatory

#### BL-18 · Real authentication and role-based access control

Labels: `not-built`, `security`

- **Summary.** Roles are demo identity headers (`X-BV-User`, `X-BV-Role`). Anyone who can reach the API can claim any role.
- **Today.**
  - Header roles with 403 for the wrong role (task B12).
  - An optional shared dashboard token (`BV_DASHBOARD_TOKEN`) on the private live instance.
  - Demo routes only in `DEMO_MODE`.
- **Proposal.**
  - Single sign-on (OIDC).
  - Roles from the identity provider.
  - Per-site scoping, so a coordinator sees only their own site and its inbox.
  - Session audit, with audit events attributed to authenticated users.
- **Done when.** Every `/api/*` route requires an authenticated session, and the role-gating test table runs against real tokens.
- **Constraints.** Rule 7: every human action is still audited.
- **References.** `docs/privacy-security.md`, `SECURITY.md`.

#### BL-19 · Production hardening and compliance assessment

Labels: `not-built`, `security`

- **Summary.** The deployment is suitable for a demo with synthetic data, not for patient data.
- **Today.**
  - SQLite on a single instance.
  - No rate limiting on tool, webhook or acknowledgment endpoints.
  - The audit hash chain is tamper-evident only inside the database.
  - No HIPAA assessment and no 21 CFR Part 11 validation.
  - Agreements with processors (voice, LLM, push) are not in place, and their availability is UNVERIFIED.
- **Proposal.**
  - Managed Postgres with backups and a retention policy.
  - Rate limits.
  - External anchoring of the audit chain head, for example a periodic signed export.
  - A HIPAA and Part 11 gap assessment by a qualified reviewer.
  - Processor agreements, and data-flow review per vendor.
- **Done when.** Each item has an owner and a documented decision; the gap table in `docs/privacy-security.md` is updated.
- **Constraints.** No real patient data until this is closed (rule 8).
- **References.** `docs/privacy-security.md`, task R7.

#### BL-20 · Regulatory review of the sponsor-side patient stream

Labels: `not-built`, `pilot`

- **Summary.** Site Signal assumes the patient-reported stream reaches the sponsor separately from the site (shadow mode). Several questions need qualified review before any real use.
- **Open questions** (UNVERIFIED):
  1. Investigator control of eCOA/ePRO source data under EMA/INS/GCP/112288/2023.
  2. What sponsor awareness of unfiltered patient symptom reports means for IND safety reporting (21 CFR 312.32).
  3. Whether templated data-completeness queries prompted by patient reports can be seen as leading.
  4. How discordance findings may be used in monitoring without being treated as protocol deviations.
- **Done when.** A memo from a qualified regulatory reviewer exists, and the PRD's regulatory section (`docs/10` §7) is updated to match.
- **Constraints.** Until then: shadow mode only, the wording "a reason to look, not a finding", and CRA approval on every query.
- **References.** `docs/10` §7.7, `docs/research/site-signal-methods.md` §3.5.

## 5. Conditional issues (create only if a cut rule fires)

These follow the cut rules in `docs/09`. When one fires, add the item to `NOT_BUILT.md` and create the issue with the same template.

| Trigger (ET) | Title | Labels |
|---|---|---|
| 03:30, V10 not met | Fold into BL-01 (see its last line); no separate issue | — |
| 03:30, Render pair not up | Cloud deployment: public replay-only instance and private live instance ("verified locally only") | `not-built` |
| 05:00, simaerep classic not fixture-green | simaerep classic (legacy) comparator: finish the port and fixture test | `not-built`, `statistics` |
| 05:25, Checkpoint B behind | Site query flow and mock site inbox (CRA approval, coded responses, audit) | `not-built` |
| 05:25, Checkpoint B behind | Blind run with hidden planted count and audited reveal | `not-built`, `statistics` |
| Host slower than 10 s | Blind run on the host: subprocess path (only precomputed seeds shipped) | `not-built` |
| 05:50, S10 not done | Covered by BL-16 | — |
| 07:00, equity UI not done | Equity panel and single-language toggle in the UI (numbers already in `report.md`) | `not-built`, `statistics` |
| 07:30 freeze | Phone-width and 125% zoom polish on remaining pages | `not-built` |

## 6. Maintenance

- **Closing.** When an item is built later, close its issue with a link to the commit, and move the `NOT_BUILT.md` line to the change log.
- **New items.** New entries go here first (contracts-first spirit), then to GitHub.
- **Scope of issues.** Each issue describes this product only.
