# 06 · Frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query. API types are generated from the backend's OpenAPI (`make types` → `frontend/src/lib/api-types.ts`). All requests go through one `apiFetch()` helper that adds `X-BV-User` and `X-BV-Role` from the demo role switch.

## Design direction

Calm clinical tool, not a consumer app. White and light-gray surfaces, one accent color, dense but readable tables, large hit targets. Semantic colors are reserved for state:

| State | Color | Used for |
|---|---|---|
| Emergency | red | emergency escalations, red-flag chips |
| Urgent | amber | urgent escalations, provisional grade ≥ 3 |
| Callback / task | blue | nurse tasks, callbacks |
| Done / acknowledged | green | acknowledged, confirmed |
| AI-generated | violet outline + "AI draft" or "AI translation, verify" label | any LLM-produced text shown to staff |

Rules: every AI-produced string carries a visible label. Every draft shows its evidence quote. Original-language quotes are shown first, English translation second. Times show as relative ("21 s ago") with absolute time on hover. Provisional grades always say "provisional".

## Layout

Top bar: product name, study short title + NCT ID, **open escalations banner** (red/amber pill with count, links to `/escalations`, polls every 2 s), **Demo role switch** (Coordinator · Investigator · Sponsor) with a visible "demo, no authentication" note. Left nav: Today, Escalations, Review, Patients, Plan, Report card, Sponsor inbox, Audit.

## Pages

### `/` Today
- Table of check-ins due today: subject ID, name, day after dose, language chip (EN/ES), pace chip ("Extra time"), caregiver icon, status chip, actions **Call phone** and **Call in browser**.
- In demo mode the phone button is replaced by **Replay scenario** (dropdown of `/api/demo/scenarios`).
- Clicking a row or starting a call navigates to `/checkins/[id]`.

### `/checkins/[id]` Live check-in (the demo's main screen)
Polls `GET /api/checkins/{id}` every 1 s until `completed`, then every 5 s for 30 s (post-call pipeline results arrive).
- Header: patient name, subject ID, language, pace, speaker (patient or caregiver), call status with a running timer, channel.
- Left column, **Conversation**: during the call show the stream of recorded answers as chat-like cards (question label → patient's quote → recorded value). After the call, replace with the full transcript with timestamps; clicking a quote anywhere on the page scrolls here and highlights it.
- Right column, **Findings**: one card per term: term, the patient's answer (scale value), numeric input if any, **provisional grade** badge, the rule text that fired, red-flag chips.
- Top of right column, **Escalation panel** (only when one exists): level, reason, "Paged RN on call by push 0:21 ago", re-page count, **Acknowledged in N s** in green when done, language note ("Prefers Spanish: use interpreter line"), and a dashboard **Acknowledge** button as fallback.
- Bottom, **Drafts created** (after the call) with a link to the review queue filtered by this check-in.
- If `channel == "web"`: an embedded call widget (start/stop, mic level, connection status) using `@elevenlabs/react` (inside `<ConversationProvider>`), started with the `conversation_token` and `dynamic_variables` from `web_session`. After connecting, POST to `/api/checkins/{id}/web-started`.

### `/escalations`
Open first (sorted by level then age), then acknowledged and resolved. Each row: level chip, patient, red flags, summary sentence, paged time, ack time, ack method, actions Acknowledge / Resolve (with note).

### `/review` Review queue
- Filters: status (draft by default), kind (AE, CM, NURSE_TASK), patient.
- Each draft card: kind, term or medication, payload fields (editable inline in edit mode), provisional grade + rule, **evidence block** (original quote, translation with label, timestamp link to the check-in), source (live tool or post-call extraction, with a note "found after the call" for the latter).
- Actions: **Confirm**, **Edit** (then Save), **Reject** (requires reason). Toasts: "Draft confirmed", "Draft rejected".
- Investigator role on a confirmed AE: **Seriousness** checkboxes (six ICH E2A criteria), **Relatedness** select, **Sign**. If serious, a toast links to the new serious-event report.

### `/sae/[id]` Serious-event report
- Big **24-hour clock** (time remaining until `due_at`, turns amber under 6 h, red under 1 h).
- CIOMS-style form sections (patient, reaction, suspect product by class, seriousness, reporter) prefilled; narrative with "AI draft" label and an editable final version.
- Actions: Save, **Sign** (investigator), **Send to sponsor**. After sending: "Received by sponsor at 15:42, 22 h 58 m before deadline".

### `/sponsor` Sponsor safety inbox (mock)
Visually framed as a different organization's tool (different header color, "Sponsor view (mock)" label, no site-only data like phone numbers or names beyond subject ID). List of received reports with on-time badge and the four valid-case checks as green ticks. Clicking opens the report read-only.

### `/patients` and `/patients/[id]`
List with language, pace, caregiver, next due. Detail page: profile (language, pace, hearing, caregiver, baseline), dose timeline with check-in dots, a small multiple chart per symptom term showing provisional grade over time (sparkline style, dose dates as vertical markers), and past check-ins.

### `/plan`
Approved plan: version, approver, approval time, schedule (days after dose), item list with EN and ES wording side by side, red flags with levels. Stretch: **Propose from protocol PDF** → shows the Gemini proposal as a diff against the active plan with page citations → **Approve** creates the new version.

### `/report-card` Safety report card
Data from `GET /api/eval/latest` and `/api/validation/latest`.
- Header: run date, commit SHA, number of personas, mode ("text simulation" / "voice").
- Metric tiles: urgent and emergency cases paged (x/y), side effects captured (recall), grades matching the answer key, medical-advice requests refused, disclosure in first turn, interruptions per call (voice runs only).
- **Equity table**: the same metrics split by language (EN, ES) and pace (standard, extra time). Highlight any gap over 5 points.
- Persona table: persona, language, pace, expected vs actual escalation, pass/fail, link to transcript.
- **Known misses**: list from `latest.json` with the planned fix.
- Validation: requirement count, tests linked, pass rate, link to `validation/traceability.md` on GitHub.

### `/audit`
Append-only list: time, actor, role, action, entity, before/after diff on expand.

## Components to build once

`StatusChip`, `LevelChip`, `LanguageChip`, `PaceChip`, `GradeBadge` (always shows "provisional"), `EvidenceQuote` (quote + translation + timestamp + source), `AiLabel`, `CountdownClock`, `RelativeTime`, `RoleSwitch`, `EscalationBanner`, `WebCallWidget`, `Sparkline`. *Planned (Site Signal, below):* `TierBadge`, `DataOriginBadge`, `FunnelPlot`, `EpisodeTable`, `SiteQueryComposer`, `BlindRunDialog`, `PowerTable`, `EquityPanel`.

## States

Every list has a designed empty state ("No check-ins due today. Patients appear here 1, 3 and 7 days after a dose."). Every mutation shows a toast and disables its button while pending. Network errors show "Can't reach the backend. Check that `make dev` is running." with a retry.

## Accessibility

Keyboard reachable actions, visible focus, color never the only signal (chips have text), minimum 14 px text, 4.5:1 contrast.

## Site Signal pages (planned, Sun Oct 11)

What each page must show and who can act is in `docs/10-site-signal.md` §6; payloads are in `docs/03-api-contracts.md` §5; tasks are WS3 F10–F19. This section fixes layout, components and tokens.

**Tokens.** Site Signal tiers get their own neutral scale and never reuse state colors: no green or "success" token (no tier means "clean") and no escalation red or amber (a statistical tier is not a clinical escalation). Watch = strongest emphasis (dark slate fill, white text), Look = medium (slate outline), "No signal at this sample size" = neutral gray text, "Not computed: reason" = light gray with the reason. `DataOriginBadge`: SIMULATED (dashed outline), MEASURED (solid outline), MIXED (half dashed). AI-assisted translations, including those of synthetic quotes, keep the violet `AiLabel`.

**Nav.** `AppShell` adds **Sites** (`/sites`) and **Site inbox** (`/site-inbox`); `/sae` gets its own nav state. The role switch adds **CRA (sponsor)** (Sam Rivera). On phone width the bottom nav scrolls horizontally without page overflow.

### `/sites` Site Signal (cra, sponsor; other roles see a "Switch to CRA to view site rankings" notice)
- Header: `DataOriginBadge` SIMULATED, `sap-v1` short sha and date, "Thresholds fixed from the pre-registered null". Tabs: **Signal** · **How well it works** · **Equity**.
- **Signal:** `FunnelPlot` (hand-built SVG: x = E, y = O/E, Look and Watch lower-limit curves from `funnel.limits`, one dot per computed site, not-computed sites as hollow gray markers in a strip below the axis, accessible table fallback). Ranked table: site, patients, evaluable, pending, paged, coverage, O/E, `TierBadge`, rate-KRI tier, "simaerep classic (legacy)" tier, open queries. Tier legend with the number of computed sites. Footer from `labels.footer` and `labels.footer_expected_false_look` (number from the API). Buttons **Blind run** (`BlindRunDialog`, demo mode only) and **Reveal answer key** (display labels from `labels.answer_key` only).
- **How well it works** (any role): `PowerTable` with power at both tiers for every indicator, the 25% and 50% rows, null false-flag rates with MC SE, the failure case, sensitivity rows and the committed-study confusion labeled "illustration only"; link to `WHAT_IT_GETS_WRONG.md`. No number is typed in a component.
- **Equity** (Checkpoint C): `EquityPanel` with within-site odds ratios (Spanish vs English, extra time vs standard) and intervals, the "power is low" note, per-site rows, and the **Single-language app** toggle that grays out the sites in the counterfactual list.

### `/sites/[id]` Site drill-down (cra, sponsor; query actions cra only)
- Site card: fictional name, region, roster mix, call completion, `TierBadge` with reason.
- `EpisodeTable`: subject ID, term, `GradeBadge` ("provisional, rule-graded"), episode date, status chip (Unmatched, Matched, Pending grayed, "Paged: separate stratum", Not evaluated), `EvidenceQuote` (original language first, `AiLabel` translation), source chip (Live call / Replay / Synthetic), `DataOriginBadge`. Site 101 lists MEASURED episodes first. Strata mini-table (language, pace) and paged-stratum counts.
- `SiteQueryComposer` (cra): select `unmatched` rows → template preview → edit → **Approve and send**; 422 codes shown inline. Query list with status and links to the audit rows.

### `/site-inbox` Mock site inbox (coordinator responds; cra and sponsor read-only)
Banner "Mock site inbox (synthetic data)". Sent, answered and closed queries for every queried site (optional site filter): body, cited subject IDs and dates, status timeline, coded response plus note. Drafts never appear. Coordinators see no patient quotes.

### `/sae` Serious-event reports (any role)
Table: subject ID, event term, status, `aware_at`, `CountdownClock` to `due_at`, sent / on time. Rows open `/sae/[id]`; "Download CIOMS JSON" per row and on `/sae/[id]`.

### Changed pages
- `/` Today: replay speed 1x/2x/4x; "Call in browser" disabled with a reason in demo mode; replay controls only when `health.demo_mode` is true.
- `/checkins/[id]`: MEASURED badge "Site aware N days before next visit" (Checkpoint C); recorded-scenario label ("Recorded real call; synthetic patient played by a teammate" or "Scripted") and an audio player when `audio_url` is set.
- `/review` and `/sponsor`: "Download AE.csv" / "Download CM.csv"; "origin: between_visits" tag on confirmed AE rows; the sponsor page gets an `h1`.
- `/report-card`: Clopper-Pearson 95% interval on every proportion; the zero-failure note from `zero_failure_n`; a separate MEASURED "Real voice calls" row from `/api/eval/voice-checks`, never pooled with text mode; a line stating whether the evaluated and deployed agent models match.
