# ADR-001 · Site Signal on top of Between Visits

| Field | Value |
|---|---|
| Status | Accepted |
| Date | Sat Oct 10, 2026, ~11:30 PM ET |
| Decided by | Team lead |
| Applies to | The Sun Oct 11 build: SAP tag 02:45, Checkpoint A 03:30, B 06:15, C 07:30 (code freeze) |
| Details | `docs/10-site-signal.md` (PRD), `docs/11-site-signal-sap.md` (SAP), `docs/09-timeline-and-workstreams.md` (tasks, cut rules), `docs/03-api-contracts.md` §5–6 (contracts) |
| Background | `docs/research/site-signal-methods.md`, `docs/research/synthea.md` |

## Context

**What exists** (`CLAUDE.md` § Status):

- A voice agent calls patients in English or Spanish, at standard or extra-time pace.
- Fixed CTCAE v5 rules grade the answers, red flags page the on-call nurse, and drafts carry verbatim evidence.
- Coordinator and investigator review, plus a serious-event handoff with a 24-hour clock.
- A 20-persona text-mode evaluation and a requirement-traceability pack.
- A real ElevenLabs browser call works; the team lead confirmed it.

**What is wrong today.** A clean-clone audit during planning found defects that matter whatever direction is chosen:

- dates are compared in UTC instead of local time, so the Today view and AE start dates are wrong in the evening;
- the default tool secret is accepted;
- demo routes are open whenever `APP_ENV=dev`;
- the exported CSV starts with a comment line, and the AE outcome disagrees with the serious-event narrative;
- the Spanish disclosure reads "de el" instead of "del";
- a drug product name and product code remain in `data/`, against rule 8;
- the documented agent LLM differs from the configured one;
- there is no production deploy path and no security document.

**Time and people.** About 7.5 hours to the code freeze. One implementing session runs parallel agents and starts from these docs alone. Human steps are listed in `docs/09` § Human actions.

**The sponsor-side problem.**
- Clinicians record fewer of the symptoms patients feel, across the trials and sites studied (`docs/research/site-signal-methods.md` §2; some figures are from secondary summaries and marked UNVERIFIED there).
- Current AE key risk indicators compare a site's AE log with other sites' AE logs. They cannot tell a site with healthier patients from a site that records less (same doc, §3).
- Between Visits already produces the missing input: a patient-reported symptom stream that is graded the same way at every site and collected through a channel site staff do not run.

**Constraints:**
- `CLAUDE.md` rules 1–9.
- The patient-facing safety path must not regress.
- Synthetic data only, and no licensed content.

## Decision drivers

1. **Protect the safety path.** Nothing new may touch grading, paging or the call itself.
2. **Fix correctness, security and packaging first.** Every direction depends on these fixes.
3. **Make a claim that can be checked and can fail,** with the method fixed before any evaluation data exist.
4. **Build on what only the voice product provides:** reach in two languages and at extra-time pace, and identical rule grading.
5. **Keep every checkpoint shippable,** with cut rules decided in advance.
6. **Add no new clinical content** that would need clinical or linguistic validation we cannot do this weekend.
7. **Show the limits in the product,** not only in documents.

## Decision

Build **Between Visits + Site Signal**, in this order.

1. **Readiness** (Checkpoint A, new workstream WS0 plus named fixes in WS1–WS4). Repair what is wrong today:
   - security and correctness: secret scan, local-date fix, default-secret refusal, demo routes only in `DEMO_MODE`, 403 for the wrong role, hash-chained audit log, CSV/AEOUT fix, Spanish "del" fix, rule-8 string removal;
   - deployment: production images, a public replay-only instance and a private live instance;
   - documentation: security and privacy docs, Clopper-Pearson intervals on the report card.

   Voice work is re-verification, not first contact:
   - three real calls against the deployed live backend, logged as MEASURED;
   - the agent LLM pinned and documented;
   - real calls exported as replay scenarios;
   - the hero call recorded on the production build.
2. **Pre-registration** (SAP gate, 02:45). These are committed and tagged `sap-v1` before any evaluation output exists:
   - `docs/11`, `monitoring/params.yaml`, `data/signal_rules.json`, `data/site_queries.json`;
   - the planning grid.

   The evaluation seed is derived from the tag's commit and a public randomness beacon published after the tag; every evaluation run is logged (`docs/11` §1.2–§1.3).
3. **Site Signal** (Checkpoint B, new workstream WS5):
   - a separate `monitoring/` uv project, a stdlib episode builder, the discordance indicator and two comparators;
   - a read API and a new CRA role;
   - a templated site query with CRA approval and a mock site inbox;
   - a demo-only blind run;
   - SIMULATED and MEASURED labels on every view.
4. **Polish** (Checkpoint C):
   - equity panel and the measured "site aware N days before next visit" badge;
   - `WHAT_IT_GETS_WRONG.md` and `NOT_BUILT.md`;
   - the GitHub issues in `docs/backlog.md`.

Key design choices:

| Choice | Why |
|---|---|
| **Analysis set.** New or worsened grade ≥ 2 episodes of Diarrhea, Fever and Dyspnea only. | These are the only terms with grade 2 and 3 rules. Grading any other term would be new clinical content (driver 6). |
| **Paged episodes form a separate stratum,** outside O/E. | The nurse page tells the site about the episode, so the site's capture of it is not independent. |
| **Confirmed Between Visits drafts** (`origin = between_visits`) never match, and a site where drafts reached site staff is not computed (`integrated_mode`). | The exclusion prevents self-matching; the guard keeps the comparison to shadow mode, where the streams are independent (`docs/11` §2.4). |
| **Two tiers.** Look: per-site 5%, with the expected false flags per study from calibration stated on screen. Watch: family-wise ≤ 10%. | One threshold cannot be both sensitive and specific at the site sizes considered (patients per site chosen by `docs/11` §11.5 rule P1). Both operating points are shown honestly. |
| **No green state.** Below minimum data, below 60% call completion, or on any error, a site shows grey "not computed". | Fail-safe (rule 5): the absence of a flag must never read as "clean". |
| **Comparators on identical data:** a gsm-style rate KRI and simaerep classic (legacy). | Shows what the patient stream adds and where it adds nothing (the failure case). |
| **Thresholds from a null model pre-registered under `sap-v1`;** a blind run replaces "plant and recompute". | The result cannot be tuned after the fact, and anyone can test it with a seed of their own. |
| **A CRA approves every site query.** Wording comes from `data/site_queries.json`, data-completeness only, subject IDs only. | Rules 2, 3 and 7. The statistics point; a human decides. |
| **No LLM anywhere on the statistics path.** numpy and scipy live only in `monitoring/`. | Rule 1. The backend stays light. |
| **Wording:** "capture discordance", "a reason to look, not a finding". | Discordance includes legitimate clinical judgment and is not evidence of misconduct. |

The repository stays private. Changing its visibility is a later human decision, made after a fresh secret scan.

## Alternatives considered

Each alternative was written up as a full option with a build plan and reviewed against the same drivers. The summaries below are in product terms.

### A. Polish only: readiness, no new scope

- **What it is.** Today's product, made correct, verified with real calls, deployed and documented.
- **What it would add.** The lowest-risk path to a working, verifiable product.
- **Why not on its own.**
  - The evidence base stays at 20 simulated text-mode personas.
  - The product's patient stream is used only on the site side.
  - It answers nothing for the sponsor about whether site AE data reflect what patients report.
- **What we keep.** All of it, as Checkpoint A, done first. It is also the fallback if Site Signal slips (`docs/09` § Cut rules).

### B. Chart-scan completion: two sources, one record

- **What it is.** A second evidence source alongside the call: synthetic clinic notes, triage notes, portal messages and medication lists.
  - An LLM extracts enums plus an exact quote.
  - A deterministic check confirms that the quote appears verbatim.
  - Call and chart findings merge into one draft per event, with the capture lag before the next visit.
- **What it would add.** A complete "check-in plus chart scan" capture desk, with more drafts per patient.
- **Why not now.**
  - Chart-note scanning is a listed non-goal in `docs/00`, so this would be a scope change.
  - It adds a second LLM extraction path over clinical text.
  - Precision and recall would be measured on notes we wrote ourselves from our own answer key.
  - Known hard cases need more evaluation than this weekend allows: a recurrence merged into one ongoing event, and copied-forward note lines read as current.
- **What we keep.** The measured days-before-next-visit metric (B21, F18). The chart-note stream is backlog BL-09.

### C. Pharmacovigilance day-zero intake

- **What it is.** The patient's words become an EDC AE row and a safety-case record shaped like E2B(R3).
  - It tracks the minimum-criteria "day zero" across case versions.
  - It looks up expectedness against a mock reference safety list and starts the expedited reporting clock.
  - It reconciles the EDC and safety databases continuously.
- **What it would add.** A deeper sponsor safety workflow downstream of the existing serious-event handoff.
- **Why not now.**
  - Expectedness and expedited-reporting decisions are regulatory judgments. A mock reference safety list risks implying determinations the product should not make.
  - Reconciliation needs MedDRA-level grouping of terms, which rule 9 keeps out of the repo. Equivalent terms such as diarrhea and colitis would show up as false mismatches.
  - The regulatory surface is large, and it overlaps the existing handoff.
- **What we keep.** The serious-event handoff, with the AE outcome made consistent with the narrative (B14). A sponsor-supplied coding hook is backlog BL-17.

### D. Detectability simulator: call-schedule planning

- **What it is.** A study-design tool: a seeded microsimulation of how many days earlier a severe side effect would be known under each between-visit call schedule, by language and pace.
- **What it would add.** A design-stage use of the voice product, with an equity view of reach.
- **Why not now.**
  - The results depend mainly on an assumed warning window (time from grade 2 to grade 3), and we found no published estimate for it.
  - Every number would be simulated, with no measured component.
  - Voice plays no part at runtime.
- **What we keep.**
  - The discipline of a pre-registered simulation and a planning grid (`docs/11` §11.5).
  - The single-language counterfactual in the equity panel.
  - The measured days-before-next-visit badge.

### E. Neuro-check after bispecific step-up dosing

- **What it is.** In the days after step-up doses of a CD3 bispecific, a short spoken check (naming, counting, repetition) scored by fixed rules against the patient's own baseline, paging the nurse on a drop.
- **What it would add.** The most voice-native use considered, aimed at a high-risk window and at patients who are hard to reach by app.
- **Why not now.**
  - It needs new patient-facing clinical items and scoring rules, which require clinical and linguistic validation (rules 2 and 3).
  - Speech-recognition error would dominate the scores. That error is unmeasured, and we expect it to fall hardest on Spanish-speaking and extra-time patients.
  - The false-page burden is unknown.
  - The delivery path is not built.
  - Overnight coverage would rest with caregivers.
- **What we keep.** Backlog BL-07 with design notes.

### F. Long-term follow-up caller

- **What it is.** After treatment ends, the same agent makes protocol follow-up calls for years.
  - A contact ladder includes authorized alternate contacts.
  - Rule-based detection hands death reports, withdrawal requests and very-ill calls to a human.
  - A view shows follow-up completeness by site and subgroup.
- **What it would add.** Support for a long, staff-intensive workflow that matters to survival endpoints.
- **Why not now.**
  - It is the largest build of the options.
  - Calls to alternate contacts raise consent and AI-voice calling questions. The challenge kit notes that the FCC treats AI voices as "artificial" under the TCPA; legal review is UNVERIFIED.
  - Difficult news must not be exchanged without a human taking over (kit sheet "The Long Game" §10), and idioms such as "se me murió el celular" can trip a rule-based detector.
  - Completeness statistics would rest on synthetic data alone.
- **What we keep.** Backlog BL-08 with design notes.

### G. Validation harness for clinical AI

- **What it is.** A multi-agent harness that drafts a GxP validation package for a repository (intended use, risk assessment, test protocols, test drafts).
  - A deterministic engine runs the tests and refuses anything unapproved or without evidence.
  - Humans sign.
- **What it would add.** Reusable validation tooling, with Between Visits as its first target.
- **Why not now.**
  - It moves the product's focus from patients and sites to tooling.
  - It cannot check whether approved wording is correct: our own Spanish "de el" disclosure passed every test and the evaluation, and only human review caught it.
  - It is a heavy build.
- **What we keep.**
  - Grade-boundary tests and the mutation probe (D9).
  - The corrective-action log `validation/capa.md`.
  - Clopper-Pearson intervals and the zero-failure N on the report card (D10).
  - Traceability that also covers the monitoring tests (D12).
  - The hash-chained audit log (B13).

### H. Site Signal without readiness first

- **What it is.** The same sponsor-side layer, built before the Checkpoint A fixes.
- **Why not.**
  - The known defects would stay in everything deployed and recorded.
  - Site Signal itself depends on correct local dates and exports (AESTDTC, the `ORIGIN` column).
- **What we do instead.** Readiness comes first. The SAP gate runs in parallel because it touches only docs, data files and the new `monitoring/` project.

## Consequences

**Positive**

- The voice stream gets a second, sponsor-side use without any change to the safety path.
- The claim can be checked and can fail:
  - pre-registered before the data;
  - reproducible from a seed;
  - O/E, z, φ̂ and τ̂² can be recomputed by hand;
  - comparators run on the same data;
  - the failure case is shown.
- The question of whose symptoms reach the safety record becomes measurable: capture by language and by pace within sites.
- The readiness fixes land first and benefit everything after them.

**Costs and risks**

- **A larger surface.**
  - Two new workstreams (WS0, WS5) and a new uv project.
  - A new role (`cra`) and two new tables (`SiteQuery`, `SignalRun`).
  - About 17 new endpoints and four new pages.
  - Longer CI runs.
- **Both streams in the 20-site study are simulated.** The results show method and power, not real-world validity (`docs/10` §10).
- **Power is limited.** At the `sap-v1` design (patients per site chosen by `docs/11` §11.5 rule P1), moderate capture gaps are mostly invisible at the Watch tier. The advantage over a plain rate KRI depends on assumed heterogeneity. Exact values come only from `validation/site_signal/summary.json`.
- **New regulatory questions,** marked UNVERIFIED: investigator control of ePRO source data, and what it means for the sponsor's safety awareness to see an unfiltered patient stream. Only shadow mode is supported (`docs/10` §7).
- **Two stories in one demo.** The patient call stays first, and the sponsor layer is shown as the use of that call's data.
- **Wording discipline everywhere.** "Capture discordance" and "a reason to look", never "under-reporting", "fraud" or "misconduct".

**Accepted constraints**

- No LLM on the statistics path. numpy and scipy only in `monitoring/`; the backend reads committed outputs and shells out only for the blind run.
- Thresholds come from a pre-registered null at assumed parameters. A data-fitted null is not built (backlog BL-13).
- The simaerep comparator is the legacy algorithm, labeled as such (backlog BL-12).
- Episode dates are call dates because no onset item exists (backlog BL-05).

**What does not change**

- `rules.py`, `interview.py`, `escalation.py`, `postcall.py` and `agent/*` are untouched.
- `sae.py` gets only the edits named in B14.
- Paging never waits on statistics, and the patient's call is unchanged.

## Revisit when

- **Retrospective validation fails.** If validation on trials with paired patient-reported and clinician-reported data (backlog BL-11) shows no association between discordance and independent quality evidence, retire or redesign the indicator.
- **Regulatory review rules out shadow mode.** If review (backlog BL-20) rules out a sponsor-side patient stream in shadow mode, stop.
- **Drafts reach sites.** In integrated mode the indicator is no longer valid; switch to a draft-rejection indicator (backlog BL-14).
- **Checkpoint B is cut at 05:25.** Site Signal ships read-only. This decision still stands, and `NOT_BUILT.md` lists what was dropped.

## Related

- `CLAUDE.md`: rules and status.
- `docs/00-overview.md`: scope and non-goals.
- `docs/10-site-signal.md`, `docs/11-site-signal-sap.md`.
- `docs/09-timeline-and-workstreams.md`, `docs/workstreams/WS0-readiness.md`, `docs/workstreams/WS5-site-signal.md`.
- `docs/research/site-signal-methods.md`, `docs/research/synthea.md`.
- `docs/backlog.md`: everything considered here and not built.
