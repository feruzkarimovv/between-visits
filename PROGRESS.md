# PROGRESS

Build of the Site Signal plan (`docs/KICKOFF.md`) on branch `site-signal-build`. One row per task: status, commit, acceptance output summary, blocker. Human steps are in `HUMAN_TODO.md`.

Status values: `todo`, `in progress`, `done`, `done (human step pending)`, `blocked (human)`.

## Decisions recorded by the implementing session

| Topic | Decision |
|---|---|
| Branch | `site-signal-build`, created from `main` at d29585e. The plan branch was brought in as one squash commit (d88dc99) so the history keeps a single author identity; its content is identical to the plan branch. |
| V9 LLM pin | Default from WS1 V9: the evaluated model `claude-sonnet-5-5`. |
| D8 product-name hash | Generic-name hash computed from the public registry entry of the example study without writing the name anywhere. |
| STUDYID | Default kept: the public registry ID of the example study. |
| SAP review | Separate reviewer agent with a statistician's lens; team lead review pending. |

## Tasks

| Step | Task | Status | Commit | Acceptance output | Blocker |
|---|---|---|---|---|---|
| SAP | D11 signal rules and site query data files | todo | | | |
| SAP | B16 shared episode builder | todo | | | |
| SAP | S1 monitoring project, params, planning grid, `sap-v1` tag | todo | | | |
| A | R1 full-history secret scan | todo | | | |
| A | R2 toolchain pins and clean setup | todo | | | |
| A | R3 local dates | done | a0e57f2 | test_local_dates.py 7 passed; make validate --check exit 0, 16/16 REQs, REQ-016 PASS (7/7); make test exit 0 (93 pytest, ruff, data, agent-sync, tsc+eslint) | |
| A | R4 safe startup, demo-only routes | todo | | | |
| A | R5 production Dockerfiles and compose | todo | | | |
| A | R6 Render blueprint and deploy doc | todo | | | |
| A | R7 SECURITY.md and privacy-security | todo | | | |
| A | R8 README pass 1 | todo | | | |
| A | R9 quickstart CI job | todo | | | |
| A | V9 pin the agent LLM | todo | | | |
| A | V11 export real calls as replay scenarios | todo | | | |
| A | B12 403 wrong_role and cra | todo | | | |
| A | B13 audit hash chain | todo | | | |
| A | B14 export and narrative fixes | todo | | | |
| A | B15 replay speed, provenance, health, voice checks | todo | | | |
| A | F10 demo UX, downloads, /sae list | todo | | | |
| A | D8 Spanish del fix, product-name guard | todo | | | |
| A | D9 boundary tests, mutation probe | todo | | | |
| A | D10 Clopper-Pearson intervals | todo | | | |
| B | S2 simulate and roster | todo | | | |
| B | S3 match | todo | | | |
| B | S4 calibrate and indicators | todo | | | |
| B | S5 simaerep classic port | todo | | | |
| B | S6 run and report | todo | | | |
| B | S7 validate | todo | | | |
| B | S8 blind run CLI | todo | | | |
| B | S9 equity | todo | | | |
| B | B16b Site Signal fixtures | todo | | | |
| B | B17 Site Signal read API | todo | | | |
| B | B18 site query flow | todo | | | |
| B | B19 blind run endpoints | todo | | | |
| B | B20 types, contract conformance | todo | | | |
| B | F11 CRA role and nav | todo | | | |
| B | F12 /sites overview | todo | | | |
| B | F13 /sites/[id] drill-down | todo | | | |
| B | F14 /site-inbox | todo | | | |
| B | F15 blind run dialog | todo | | | |
| B | F16 How well it works tab | todo | | | |
| B | R10 Playwright smoke | todo | | | |
| B | D12 traceability covers monitoring | todo | | | |
| C | B21 days before next visit | todo | | | |
| C | F17 equity panel | todo | | | |
| C | F18 check-in badge, recorded scenarios | todo | | | |
| C | F19 phone width, sidebar, screenshots | todo | | | |
| C | D13 WHAT_IT_GETS_WRONG and NOT_BUILT | todo | | | |
| C | R11 GitHub issues | todo | | | |
| C | S10 Synthea roster (optional) | todo | | | |
| P | D14 deck | todo | | | |
| P | D15 video storyboard | todo | | | |
| P | D16 README final | todo | | | |
| P | R12 final clean clone | todo | | | |
| P | V10 real calls against the live backend | todo | | | |
| P | V12 hero call | todo | | | |
