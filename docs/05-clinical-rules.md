# 05 · Clinical content and rules

Everything clinical lives in `data/` as data, never in code. This doc explains what's there, where it came from, and the exact behavior the rules engine must implement. Not a medical device; every grade is provisional and every decision is a clinician's.

## 1. Licensing decisions (read before touching `data/`)

| Source | Status | What we do |
|---|---|---|
| **NCI PRO-CTCAE** item wording | NCI holds all rights; terms forbid modifying, translating or redistributing items without NCI's written consent, and it is not intended for diagnostic or therapeutic use on individual patients | **Not included.** Our questions in `data/symptom_items.json` are our own wording (MIT). A site that registered its study with NCI can load the official items locally into `data/local/symptom_items.local.json` (gitignored, same item codes); the backend uses that wording when present and the agent still says it verbatim. Never call our questions "PRO-CTCAE". |
| **NCI CTCAE v5.0** | U.S. government publication, reusable with credit | Grade text in `data/ctcae_rules.json` is verbatim from NCI's v5.0 workbook, credited. |
| **MedDRA** codes, hierarchy, SOC columns | Licensed; may not be redistributed or exposed to non-subscribers, including open-source repos | **Not included.** CTCAE term names are used as the AE term; SDTM `AEDECOD`/`AEBODSYS` are left empty with a note "coded downstream by licensed sponsor". |
| Medication Guides (Libtayo) | Manufacturer copyright | Red-flag symptoms are condensed in our own words, with the source named. |
| Example study NCT02760498 | Public registry and posted protocol | Registry facts and protocol page references only; all patients and events are synthetic. |

How to say it in the pitch: "standard symptom questions, graded with the National Cancer Institute's CTCAE, and ready to plug in NCI's official PRO-CTCAE items once a study registers." That is accurate.

CTCAE v6.0 was published July 2025; NCI's own CTEP studies and many ongoing trials still use v5.0. Rules are versioned data, so switching is a new rules file.

## 2. Example study

`data/study.json`: **NCT02760498**, Regeneron's open-label phase 2 study of an anti-PD-1 antibody in advanced cutaneous squamous cell carcinoma, the study behind the drug's first approval. Outpatient IV every 3 weeks; patients are home between doses. Useful protocol facts (posted protocol, Amendment 9):

- Doses on Day 1, 22±3 and 43±3 of each 9-week cycle (p.86–87).
- Diarrhea/colitis managed by **stools per day over baseline: <4, 4–6, ≥7**; Grade 2 hold and steroids, Grade 3 inpatient care (p.154–155). Our diarrhea rule uses exactly these thresholds.
- **SAEs and adverse events of special interest reported to the sponsor within 24 hours** (p.106–107). This is our 24-hour clock.
- For SAE purposes, hospitalization means admission or an ER stay over 24 hours (p.105).
- The protocol has no patient call-in instructions; our red flags paraphrase the public Medication Guide.

In the UI and pitch, describe the drug as "a PD-1 immunotherapy". Never present synthetic events as findings about the real drug or study.

## 3. Questions (`data/symptom_items.json`)

Plan items, in order (`data/plan.json`): `DIARRHEA_FREQ`, `NAUSEA_FREQ`, `VOMITING_FREQ`, `FEVER_CHILLS`, `SOB_SEV`, `DIZZINESS_SEV`, `FATIGUE_SEV`, `RASH_ANY`, `NEURO_CHANGE`; then `MEDS_NEW`, `CARE_VISIT`, `ANYTHING_ELSE`.

| Parent | Asked when | Follow-up | Why |
|---|---|---|---|
| `DIARRHEA_FREQ` | sometimes / often / almost_always | `DIARRHEA_STOOLS_PER_DAY` (worst day), `DIARRHEA_BASELINE` (only if no baseline on file), `STOOL_BLOOD` | count-based CTCAE grade; colitis red flag |
| `VOMITING_FREQ` | sometimes / often / almost_always | `FLUIDS_KEPT_DOWN` | dehydration red flag |
| `FEVER_CHILLS` | yes | `TEMP_HIGHEST` (number + unit, or `not_measured`) | CTCAE fever grade; fever red flag |
| `SOB_SEV` | mild or worse | `SOB_EXERTION` (`heavy_activity` / `light_activity` / `at_rest`) | CTCAE dyspnea grade; breathing red flag |
| `DIZZINESS_SEV` | mild or worse | `DIZZY_ON_STANDING` | dehydration red flag |
| `FATIGUE_SEV` | mild or worse | `FATIGUE_REST_HELPS` | CTCAE fatigue grade 1 |
| `RASH_ANY` | yes | `SKIN_BLISTER` | severe skin reaction red flag |
| `MEDS_NEW` | yes | `MEDS_DETAIL` (answered with `record_medication_change`) | CM drafts |
| `CARE_VISIT` | yes | `CARE_VISIT_DETAIL` | possible SAE (hospitalization) → callback |

Every scale also accepts `unknown`. The spoken `say` for a question is `text[lang]` + `options_say[lang]` when the item has one. Spanish option read-outs agree in gender with the item's noun, which is why they are stored per item.

## 4. Rules engine (`data/ctcae_rules.json`, `data/red_flags.json`)

**Condition DSL** (both files): a condition is either a leaf or a combinator.
- Leaf: `{"item": CODE, op: value}` or `{"derived": NAME, op: value}`, where `op` is `eq`, `in`, `gte`, `gt`, `lte`, `lt` (several ops in one leaf are ANDed, e.g. `gte` + `lte`).
- Combinators: `{"any": [cond, ...]}`, `{"all": [cond, ...]}`.
- An `item` leaf reads the answer's `option_code`, or its `numeric_value` for numeric scales (temperatures are normalized to °C, unrounded, before comparison).
- A leaf whose input is missing or `unknown` is **false**. (Missing data never grades and never clears a flag; red flags can still be reported by the agent and are caught by the safety net.)
- Derived input: `stools_over_baseline = DIARRHEA_STOOLS_PER_DAY − (DIARRHEA_BASELINE answer, else patient.baseline.stools_per_day)`.

**Grading:** for each term, the first matching rule gives `provisional_grade`, `rule_id`, `ctcae_text` and `basis`. No match → `grade_basis: "needs_clinician"` with the patient's answers shown.

| Term | Rule | Grade |
|---|---|---|
| Diarrhea | stools over baseline 1–3 / 4–6 / ≥7 | 1 / 2 / 3 |
| Fever | highest temp 38.0–39.0 °C / >39.0–40.0 / >40.0 | 1 / 2 / 3 (G4 needs duration; clinician) |
| Dyspnea | breathless with heavy activity / light activity / at rest | 1 / 2 / 3 |
| Fatigue | rest makes it better | 1 |
| Dizziness | rated mild | 1 |
| Everything else | none | needs clinician |

**Red flags** (`data/red_flags.json`), evaluated after every answer and on every `report_red_flag` call:

| ID | Level | Rule (structured) | Also by report |
|---|---|---|---|
| RF_FEVER | urgent | temp ≥ 38.0 °C (100.4 °F) | yes |
| RF_DIARRHEA_SEVERE | urgent | stools over baseline ≥ 7, or blood/mucus/black stool | yes (severe belly pain) |
| RF_DEHYDRATION | urgent | can't keep liquids down, or dizzy on standing + (stools over baseline ≥ 4 or vomiting sometimes+) | yes |
| RF_BREATHING | urgent | breathless at rest, or severe/very severe | yes (new cough with breathlessness) |
| RF_NEURO | urgent | new confusion / word-finding / sleepiness = yes | yes |
| RF_SKIN_SEVERE | urgent | blistering, peeling or painful mouth sores = yes | yes |
| RF_LIVER_KIDNEY | urgent | – | yellow skin/eyes, dark urine, much less urine |
| RF_HEART | urgent | – | new fast or irregular heartbeat |
| RF_BLEEDING | urgent | – | vomiting blood, bleeding that won't stop |
| RF_BREATHING_SEVERE | emergency | – | struggling to breathe right now |
| RF_CHEST_PAIN | emergency | – | chest pain, pressure, tightness |
| RF_SEIZURE_FAINT | emergency | – | seizure, fainting, can't be woken |
| RF_SELF_HARM | emergency (crisis line) | – | thoughts of self-harm or not wanting to live |

**Escalation ladder**

| Level | Agent says (from `data/scripts.json`) | Backend does | Call continues? |
|---|---|---|---|
| emergency | `emergency_line` (or `crisis_line` for RF_SELF_HARM) | page now | no: `action: "close"` |
| urgent | `urgent_line` + next question | page now; drop remaining symptom items | yes: medicines, care visits, anything else, then `closing_after_escalation` |
| callback | `deferral_medical`, `wants_person_close`, or `consent_later` | task for the coordinator, no page | depends on reason |

A second red flag at the same or lower level adds to the open escalation (`added_to_page`, no second page). A higher level re-pages at the new level.

## 5. Test vectors (WS2 must pass all of these)

| Inputs | Expected |
|---|---|
| baseline 1, worst day 4 | Diarrhea G1, no flag |
| baseline 1, worst day 5 | Diarrhea G2, no flag |
| baseline 1, worst day 7 | Diarrhea G2 (6 over), no flag |
| baseline 1, worst day 8 | Diarrhea G3, RF_DIARRHEA_SEVERE |
| baseline missing, `DIARRHEA_BASELINE` = 2, worst day 9 | Diarrhea G3, RF_DIARRHEA_SEVERE |
| baseline missing, no baseline answer, worst day 9 | needs clinician, no count flag |
| worst day `unknown` | needs clinician, no flag |
| `STOOL_BLOOD` = yes, count 2 over | Diarrhea G1, RF_DIARRHEA_SEVERE |
| 37.9 °C | no grade, no flag |
| 38.0 °C | Fever G1, RF_FEVER |
| 100.4 °F (38.0 °C) | Fever G1, RF_FEVER |
| 102.2 °F (39.0 °C) | Fever G1 |
| 102.3 °F (39.06 °C) | Fever G2 |
| 40.0 °C | Fever G2 |
| 40.1 °C | Fever G3 |
| `not_measured` | no grade, no flag |
| `SOB_EXERTION` = at_rest | Dyspnea G3, RF_BREATHING |
| `SOB_SEV` = severe, `SOB_EXERTION` = light_activity | Dyspnea G2, RF_BREATHING |
| `FLUIDS_KEPT_DOWN` = no | RF_DEHYDRATION |
| `DIZZY_ON_STANDING` = yes, stools 3 over, no vomiting | no flag |
| `DIZZY_ON_STANDING` = yes, stools 4 over | RF_DEHYDRATION |
| `DIZZY_ON_STANDING` = yes, `VOMITING_FREQ` = sometimes | RF_DEHYDRATION |
| `FATIGUE_REST_HELPS` = yes | Fatigue G1 |
| `NEURO_CHANGE` = yes | RF_NEURO |
| `report_red_flag(RF_CHEST_PAIN)` | emergency, `action: close` |
| urgent open + `report_red_flag(RF_HEART)` | added to the same escalation, no new page |
| urgent open + `report_red_flag(RF_CHEST_PAIN)` | escalation level raised to emergency, re-page |

## 6. Seriousness and reporting

- **Seriousness (ICH E2A):** results in death; life-threatening (at risk of death at the time); requires inpatient hospitalization or prolongs it; persistent or significant disability/incapacity; congenital anomaly/birth defect; important medical event. UI checkboxes map to `death`, `life_threatening`, `hospitalization`, `disability`, `congenital_anomaly`, `important_medical_event`.
- **Investigator → sponsor:** 21 CFR 312.64(b) requires reporting any SAE to the sponsor "immediately"; FDA's Dec 2025 investigator safety-reporting guidance expects initial reports generally within 1 calendar day, and the example protocol says 24 hours. Our clock: `due_at = aware_at + 24h`.
- **Sponsor → FDA (context for the pitch):** 15 calendar days for serious and unexpected suspected adverse reactions; 7 days if unexpected fatal or life-threatening (21 CFR 312.32(c)).
- **Valid case minimum** (ICH E2D(R1) / E2B(R3)): identifiable patient (subject ID + age or sex is enough), identifiable reporter, suspect product, adverse event. The sponsor inbox checks these four.

## 7. Sponsor notification payload (CIOMS I style, `SAEReport.payload`)

```json
{"report_type": "initial", "date_of_report": "2026-10-11",
 "study": {"nct_id": "NCT02760498", "site_id": "101", "sponsor_study_number": "R2810-ONC-1540"},
 "patient": {"subject_id": "101-007", "initials": "R.M.", "age": 74, "sex": "F", "country": "US"},
 "reaction": {"term": "Diarrhea", "onset_date": "2026-10-08", "provisional_ctcae_grade": 3, "ctcae_version": "5.0",
              "description": "...", "outcome": "not_recovered"},
 "seriousness": ["hospitalization"],
 "suspect_product": {"description": "Study drug (anti-PD-1 monoclonal antibody)", "route": "intravenous", "last_dose_date": "2026-10-07"},
 "concomitant": [{"medication": "loperamide (Imodium)", "start_date": "2026-10-09", "otc": true}],
 "causality": {"assessed_by": "Dr. Patel (investigator)", "result": "possibly_related"},
 "reporter": {"name": "Dr. Patel", "role": "investigator", "site": "Hillside Cancer Center (fictional)"},
 "aware_at": "2026-10-11T15:41:00Z", "due_at": "2026-10-12T15:41:00Z",
 "narrative": "<investigator-final narrative>", "narrative_ai_draft_used": true}
```

The narrative draft (Gemini) may use only facts present in the payload and evidence quotes; it is labeled "AI draft" until the investigator edits and signs it.

## 8. Exports (SDTM-style CSV, confirmed drafts only)

**AE:** `STUDYID, DOMAIN ("AE"), USUBJID, AESEQ, AESPID (check-in ID), AETERM (CTCAE term), AEDECOD (empty: coded downstream by licensed sponsor), AEBODSYS (empty), AETOXGR ("1"–"5", provisional or clinician-confirmed), AESER (Y/N), AESDTH, AESLIFE, AESHOSP, AESDISAB, AESCONG, AESMIE (Y/N), AEREL (NOT RELATED / UNLIKELY RELATED / POSSIBLY RELATED / PROBABLY RELATED / RELATED), AEOUT (RECOVERED/RESOLVED, RECOVERING/RESOLVING, NOT RECOVERED/NOT RESOLVED, RECOVERED/RESOLVED WITH SEQUELAE, FATAL, UNKNOWN), AESTDTC, AEENDTC` (ISO 8601). Add a header comment line with `# CTCAE v5.0; synthetic data`.

**CM:** `STUDYID, DOMAIN ("CM"), USUBJID, CMSEQ, CMTRT (as reported), CMDECOD (empty: WHODrug is licensed), CMINDC, CMDOSE, CMDOSU, CMDOSFRQ, CMROUTE (ORAL, INTRAVENOUS, ... UNKNOWN), CMSTDTC, CMENDTC`.

`USUBJID = STUDYID + "-" + subject_id`. These match SDTMIG v3.3 variable names and the CDISC controlled-terminology values listed above.
