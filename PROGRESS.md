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
| SAP | D11 signal rules and site query data files | done | 998ee3b | validate_data.py exit=0 (25 items, 13 red flags, 11 grading rules, 20 personas; site signal OK: 3 primary terms with G2+G3 rules, 10 synonyms, 6 not_computed reasons + 9 answer-key keys labelled, 1 query template, 5 response codes, 15 banned phrases); self-test 13/13 (temp copy with 'under-report' in SQ_UNMATCHED_EPISODES body exits 1); make test exit 0 (111 pytest, ruff, data + self-test, agent-sync, tsc+eslint) | |
| SAP | B16 shared episode builder | todo | | | |
| SAP | S1 monitoring project, params, planning grid, `sap-v1` tag | todo | | | |
| A | R1 full-history secret scan | done | cb6fff6 | make secret-scan exit=0 (gitleaks 8.30.1: 33 commits scanned, no leaks found; numbers: 0 hits, 12 fictional 555 ignored, 151 allowlisted); --self-test exit 0, PASS (scratch-clone scan exit=1, 4 hits shown as last 4 digits only); validation/secret-scan.md records tool, version, time, range, 0 findings; make test exit 0 (111 pytest, ruff, data, agent-sync, tsc+eslint) | |
| A | R2 toolchain pins and clean setup | todo | | | |
| A | R3 local dates | done | a0e57f2 | test_local_dates.py 7 passed; make validate --check exit 0, 16/16 REQs, REQ-016 PASS (7/7); make test exit 0 (93 pytest, ruff, data, agent-sync, tsc+eslint) | |
| A | R4 safe startup, demo-only routes | done (human step pending) | cb467ff | placeholder secret with DEMO_MODE=0: refusal line, exit=1; APP_ENV=dev DEMO_MODE=0 + generated secret: /api/demo/scenarios 404 demo_disabled; DEMO_MODE=1: 200; test_security_guards.py 17 passed; make validate --check 17/17 REQs, REQ-017 PASS (17/17); make test exit 0 (111 pytest, ruff, data, agent-sync, tsc+eslint) | Any machine running with DEMO_MODE=0 needs a TOOL_SHARED_SECRET of 24+ characters in .env (HUMAN_TODO 2); this checkout's .env already passes |
| A | R5 production Dockerfiles and compose | todo | | | |
| A | R6 Render blueprint and deploy doc | todo | | | |
| A | R7 SECURITY.md and privacy-security | done | 18dc7ac | grep -c UNVERIFIED docs/privacy-security.md = 8; README "Security and privacy" links SECURITY.md (l.132) and docs/privacy-security.md (l.133); validate_data exit 0 (self-test 13/13); make secret-scan exit=0 (40 commits, no leaks; numbers: 0 hits, 12 fictional 555 ignored, 151 allowlisted); make test exit 0 (179 pytest, ruff, data, agent-sync, tsc+eslint); diff has no keys, phone numbers or drug names | |
| A | R8 README pass 1 | todo | | | |
| A | R9 quickstart CI job | todo | | | |
| A | V9 pin the agent LLM | todo | | | |
| A | V11 export real calls as replay scenarios | todo | | | |
| A | B12 403 wrong_role and cra | done | 38e8eb0 | pytest tests/test_roles.py 36 passed (coordinator/sponsor/cra/unknown -> POST /api/drafts/{id}/investigator, PATCH /api/sae/{id}, POST /api/sae/{id}/sign 403 wrong_role; investigator -> 200; role checked before entity/body; 403 writes no audit; cra audited as cra); /openapi.json unchanged (no api-types drift); make validate --check 19/19 (REQ-018 PASS 36/36), 179/179 tests; make test exit 0 | |
| A | B13 audit hash chain | todo | | | |
| A | B14 export and narrative fixes | done | b4e7a34 | pytest tests/test_exports.py 32 passed; demo server :8090 Rosa replay, 3 drafts confirmed, Diarrhea serious -> SAE: ae.csv X-BV-Note "CTCAE v5.0; synthetic data; AEDECOD/AEBODSYS coded downstream by licensed sponsor; ORIGIN is a sponsor-defined column", DictReader fields STUDYID..ORIGIN, AEOUT NOT RECOVERED/NOT RESOLVED = SAE outcome not_recovered, narrative has no "..", ".;" or "(("; cm.csv X-BV-Note set; CORS exposes X-BV-Note, Content-Disposition; make validate --check 18/18 (REQ-020 PASS 32/32), 143/143 tests; make test exit 0; secret-scan no leaks, 0 numbers | |
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
