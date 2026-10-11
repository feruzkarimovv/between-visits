# Not built

This page lists what Between Visits and Site Signal do not do in this submission. It has one line per item. The full write-up of each item (what exists today, the proposal, the acceptance test, the constraints) is in [`docs/backlog.md`](docs/backlog.md). Each line ends with its GitHub issue number (label `not-built`): `#N` is `https://github.com/feruzkarimovv/between-visits/issues/N`, and the [open `not-built` issues](https://github.com/feruzkarimovv/between-visits/issues?q=is%3Aissue+is%3Aopen+label%3Anot-built) are the full list. The limits with numbers are in [`WHAT_IT_GETS_WRONG.md`](WHAT_IT_GETS_WRONG.md).

## Backlog (docs/backlog.md §3)

| ID | Not built | Labels | Issue
|---|---|---|---
| BL-01 | Re-verify real voice calls on every agent change and measure speech error | `not-built` | #1
| BL-02 | Outbound phone calls and warm transfer through Twilio | `not-built`, `pilot` | #2
| BL-03 | A third language with professionally translated, approved wording | `not-built`, `pilot` | #3
| BL-04 | P19: route unconfirmed safety-net red flags to a nurse callback | `known-miss`, `not-built` | #4
| BL-05 | Approved onset-date item for symptoms | `not-built` | #5
| BL-06 | Grading rules for more symptom terms, with clinical review | `not-built` | #6
| BL-07 | Design notes: spoken neuro-check after CD3 bispecific step-up dosing | `not-built`, `pilot` | #7
| BL-08 | Design notes: long-term follow-up caller | `not-built`, `pilot` | #8
| BL-09 | Chart-note stream as a second evidence source | `not-built` | #9
| BL-10 | Protocol-to-plan: draft the check-in plan from a protocol, human-approved | `not-built` | #10
| BL-11 | Retrospective validation of Site Signal on trials with paired patient- and clinician-reported data | `not-built`, `statistics`, `pilot` | #11
| BL-12 | Port simaerep's inframe default (v1.0.0) as a comparator | `not-built`, `statistics` | #12
| BL-13 | Data-fitted null model and misspecification diagnostics | `not-built`, `statistics` | #13
| BL-14 | Indicator for integrated mode: draft rejection behavior | `not-built`, `statistics` | #14
| BL-15 | Secondary Site Signal analyses: entry-lag KRI and a mixed model | `not-built`, `statistics` | #15
| BL-16 | Synthea-derived cohort beyond the roster | `not-built`, `statistics` | #16
| BL-17 | Sponsor-supplied MedDRA coding hook for matching | `not-built`, `pilot` | #17
| BL-18 | Real authentication and role-based access control | `not-built`, `security` | #18
| BL-19 | Production hardening and compliance assessment | `not-built`, `security` | #19
| BL-20 | Regulatory review of the sponsor-side patient stream | `not-built`, `pilot` | #20

## Cut for time this round

These were planned for this submission and were cut. None of them is built, and nothing else in the repository describes them as built.

| Cut | Not built | Labels | Issue
|---|---|---|---
| S8, B19, F15 | Blind run with hidden planted count and audited reveal: the command-line run, the demo-only endpoints and the dialog. The `/sites` page has no **Blind run** button. | `not-built`, `statistics` | #21
| S10 | Synthea roster (language and age mix only, for a labeled sensitivity analysis). The committed study uses the parametric roster frozen at `sap-v1`. | `not-built`, `statistics` | same issue as BL-16 (`docs/backlog.md` §5): #16
| F17 | Equity panel and single-language toggle in the UI. The equity numbers exist in `monitoring/out/equity.json` and `validation/site_signal/report.md`. | `not-built`, `statistics` | #22
| B21, F18 | "Site aware N days before next visit" badge on the check-in page, and the recorded-scenario label in the replay picker | `not-built` | #23

## Human steps the build did not do

These need a person (accounts, phones, a camera, a submission form). `HUMAN_TODO.md` has the exact steps. Each line is updated when the step is done.

| Step | Not done by the build | Labels | Issue
|---|---|---|---
| R6 | Render deploy: the public replay-only demo and the private live instance (verified locally only so far) | `not-built` | #24
| V10 | Three real browser calls against the deployed live backend, logged in `eval/results/voice_checks.json` | `not-built` | folded into BL-01 (`docs/backlog.md` §5): #1
| V12 | Hero call: a real browser call with a teammate playing the synthetic patient, for the video | `not-built` | #25
| D15 | Recording, editing and upload of the 3:00 video (storyboard in `docs/08-demo-and-pitch.md`) | `not-built` | #26
| D16 | Devpost submission (text from the README, links, contributors, confirmation screenshot) | `not-built` | #27
