# Research · Synthea for the Site Signal roster

What Synthea can give Between Visits, what it cannot, how to run it reproducibly, and the parametric roster that is the default. Written Sun Oct 11 (planning round) from a test run of Synthea and a read of its source.

**Status: optional.**
- Task S10 (WS5, Checkpoint C), never on the critical path.
- Cut rule: if it is not done by 05:50 ET, the study uses the parametric roster only (`docs/09` § Cut rules).
- Whatever happens, Synthea supplies only the **language and age mix** of the simulated roster, for a labeled sensitivity analysis. It changes no other assumption, and the committed study stays parametric (`docs/11` §11.2 step 1).

## 1. Summary

| Question | Answer |
|---|---|
| What we take | Per synthetic patient: age and language, the latter from FHIR `Patient.communication`. Pace (standard or extra time) then follows our own documented rule. |
| What we do not take | Names, addresses, organizations, conditions, medications, encounters, notes, codes. None of these enter the repo. |
| Why so little | The Site Signal indicator uses only language and pace (equity strata, mapping-error sensitivity). Episodes, site capture, planted site behavior and AE logs are all modeled parametrically. Synthea has no immunotherapy and no treatment toxicities to offer (§3). |
| What it changes in results | Only the language and age mix of the 20-site roster. `report.md` says which roster was used. |
| Default without it | The parametric roster in `monitoring/params.yaml` (§8). All tests pass either way. |
| Never committed | The jar, raw output, SNOMED CT/LOINC/RxNorm codes, names, addresses, and Synthea's real organization and provider data (CLAUDE.md rules 8 and 9). |

## 2. What Synthea is

| Item | Detail | Status |
|---|---|---|
| Project | `synthetichealth/synthea`: a synthetic patient generator that simulates lifetimes through disease modules | Checked |
| License | Apache-2.0. Compatible with this MIT repo. We redistribute none of Synthea's code; `monitoring/cohort/NOTICE` credits it as the generator of the derived roster. | Checked |
| Source read | Commit `d9d07a6` (2026-08-18) | Checked |
| Binary used | Prebuilt `synthea-with-dependencies.jar` from the moving release tag `master-branch-latest` (197,025,542 bytes; sha256 `018ad7f04f7aacb995804d7d4781c76d5fc714f7f23257ba50daa9eefae224ac` when downloaded during planning). Whether that jar was built from `d9d07a6` was not confirmed. | Checked (hash); commit UNVERIFIED |
| Java | JDK 17 or later. Ran on OpenJDK 21.0.12. | Checked |
| Build from source | Failed in the planning environment: Gradle hit HTTP 429 (Too Many Requests) from Maven Central while downloading dependencies, twice. Use the prebuilt jar. | Checked |
| Outputs | FHIR R4 transaction bundles (US Core) by default. CSV with `--exporter.csv.export=true`. Free-text notes with `--exporter.clinical_note.export=true`. | Checked: `synthea.properties` |
| CLI | `-s seed`, `-cs clinicianSeed`, `-r referenceDate (yyyyMMdd)`, `-p population`, `-a minAge-maxAge`, `-g M\|F`, `-k keepModule.json`, `-c config`, `[state [city]]`, `--<any.property>=value` | Checked: `src/main/java/App.java` |
| Population | `-p` counts living patients. Deceased patients are generated and exported as well (a 200-patient run gave 257 records). | Checked (run) |

## 3. What it generates, checked during planning

**Oncology modules.** These were read directly from the module JSON files:

| Module | Therapies modeled |
|---|---|
| `lung_cancer` (NSCLC, SCLC, stages 1–4) | Cisplatin, paclitaxel, etoposide |
| `breast_cancer` plus 3 submodules | Anthracyclines, cyclophosphamide, 5-FU, carboplatin, hormonal and HER2-directed therapy |
| `colorectal_cancer` | Oxaliplatin, leucovorin |
| `acute_myeloid_leukemia` | Includes febrile neutropenia |
| `veteran_prostate_cancer` | Leuprolide, docetaxel |
| (none) | No myeloma module. Myeloma appears only as a reason inside `trigger_bone_marrow_transplant`. |

**Not present** (confirmed by searching the modules):

- No immune checkpoint inhibitors of any kind.
- No supportive-care drugs we would expect around chemotherapy. Loperamide, dexamethasone, filgrastim and prochlorperazine have no hits; ondansetron appears only in unrelated modules.
- No treatment side effects. The only symptom states are presenting symptoms, such as cough, lump and fatigue.

**Notes.** One FreeMarker template (`templates/notes/note.ftl`) writes a note per encounter, with chief complaint, HPI, social history, allergies, medications and plan. These are lists of conditions and medications with no symptom narrative. They are not useful as chart-scan input (`docs/backlog.md` BL-09).

**Language.**
- **Where it is stored.** FHIR `Patient.communication` holds one entry with a language code (`FhirR4.java`). There is no "preferred" flag and no interpreter-need or English-proficiency field. **The CSV `patients.csv` has no language column**, so the roster must be read from FHIR.
- **How it is assigned.** `Demographics.languageFromRaceAndEthnicity` (checked):
  - Hispanic patients speak Spanish with weight 51.15 and English with 48.85. Per the code comments, this is derived from ACS 2017 table B16006 by counting "only English" plus half of bilinguals as English.
  - Non-Hispanic patients get small race-specific shares of other languages.
- **What this means.** A site's Spanish share is driven by the Hispanic share of its city. The default geography (Massachusetts) gave 8 Spanish speakers among 253 patients (3%) in a planning run. One run with `Texas "El Paso"` gave 6 Spanish (`es`) and 6 English (`en-US`) among 12 living patients.

**Other output facts.**
- **Real places.** `organizations.csv` and `providers.csv` contain real facility names, addresses and phone numbers. We never read them.
- **Names.** Patient names come with numeric suffixes (for example "Jona712"). We never read them.
- **Codes.** Conditions use SNOMED CT, observations LOINC and medications RxNorm. US use of SNOMED CT falls under NLM licensing; whether its codes may be redistributed in a public repository is UNVERIFIED. We read none of them.
- **Clinical coherence.** Modules do not interact. In one planning run, a kept patient had a kidney transplant on tacrolimus and still received cisplatin.
- **Age.** Of 253 patients aged 50–85 with no module filter, 40 (16%) had a cancer diagnosis.

**Measured runtimes** (4 vCPU, planning environment):

| Run | Time | Output size |
|---|---|---|
| 5 patients, FHIR + CSV + notes | 20 s | small |
| 200 living (257 total), age 50–85, FHIR + CSV + notes | 75 s | 1.8 GB FHIR, 299 MB CSV |
| Cancer-only keep filter, `-p 60 -a 45-80`, CSV + notes, 3 years of history | 149 s | 58 living + 48 deceased, 193 MB CSV |

For the roster only, about 20 sites × 40 living patients, a run is estimated at a few minutes serially. That is an extrapolation and is UNVERIFIED. Full FHIR output is large, so it must be written outside the repo and deleted afterwards.

**Pre-generated sets.** `synthetichealth/synthea-sample-data` offers about 100-patient CSV and FHIR sets plus older larger sets. None are cancer-filtered or geography-controlled, so they are not useful for a per-site language mix. The PyPI package `pysynthea` downloads an unrelated OMOP database.

## 4. What we use

| Synthea field | Roster field (`monitoring/cohort/roster.json`) | Used for |
|---|---|---|
| `Patient.birthDate`, with `-r` fixed to the study start (2026-01-05; `docs/11` §11.2) | `age` (integer years at study start) | Pace: `extra_time` if age ≥ 75 (`params.yaml` `roster.extra_time.rule`) |
| `Patient.communication[0].language.coding[0].code` | `language`: `es` if the code starts with `es`, otherwise `en` | Call variant language, equity strata, language-specific mapping-error sensitivity |
| `Patient.deceasedDateTime` | (patient dropped) | Only living patients enter the pool |
| Everything else | (not read) | — |

`roster.json` holds one pool per site: `{"site_id": "1NN", "pool": [{"age": 71, "language": "es"}, ...]}`.

- `roster.py` samples each site's `n_patients` (from `params.yaml`, uniform over the range chosen by `docs/11` §11.5 rule P1) from that site's pool with the run's seed. Generate at least 2 × the upper bound of that range in living patients per site (160 if 40–80 is chosen) so every pool is large enough.
- If a pool is too small, the run fails loudly. It never silently falls back.
- No cancer keep filter is used. A keep module would have to list SNOMED CT codes, which rule 9 keeps out of git, and age and language do not depend on the cancer modules. Age is restricted with `-a 45-85`.

## 5. How to run (recipe for task S10)

**Prerequisites:** Java 17 or later on `PATH`; the `monitoring/` uv environment (`make setup`). The jar is never placed in the repo.

1. **Download and verify the jar** into a directory outside the repo:
   ```bash
   mkdir -p ~/.cache/bv-synthea && cd ~/.cache/bv-synthea
   curl -fsSLO https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
   sha256sum synthea-with-dependencies.jar
   ```
   The tag moves. Record the hash in `monitoring/cohort/manifest.json` the first time. After that, `build_roster.py` refuses to run if the hash differs (S10 acceptance). To adopt a newer jar, update the manifest deliberately in its own commit.

2. **Generate one pool per site.** `build_roster.py` runs the jar once per site with its working directory set to a fresh temporary directory outside the repo, so Synthea's `./output/` lands there. A typical call:
   ```bash
   java -jar "$SYNTHEA_JAR" -s <site_seed> -cs <site_seed> -r 20260105 -p 40 -a 45-85 \
     --exporter.fhir.export=true --exporter.csv.export=false \
     --exporter.clinical_note.export=false --exporter.years_of_history=1 \
     --exporter.fhir.included_resources=Patient \
     <State> "<City>"
   ```
   - `site_seed` = 20261000 + site number. It is fixed and recorded in the manifest. It is not the evaluation seed.
   - `--exporter.fhir.included_resources=Patient` was accepted in a planning run. Synthea always includes Patient and Encounter resources anyway (comment in `synthea.properties`). Whether this setting shrinks the output was not checked.
   - `-r` and `--exporter.years_of_history=1` are documented options that were not exercised in planning.

3. **Read and reduce.** For each site, read the Patient resources from the bundles, drop deceased patients, and keep `age` and `language` as in §4. Write `roster.json`, then delete the temporary directory.

4. **Write the manifest** (`monitoring/cohort/manifest.json`), recording:
   - jar URL and sha256, and Synthea commit (if known);
   - Java version and generation time (UTC);
   - per site: State, City, seed, `-p`, `-a` and the full argument list;
   - living and dropped-deceased counts;
   - the language rule, the age reference date and the extra-time rule.

5. **Commit only** `build_roster.py`, `manifest.json`, `roster.json` and `NOTICE`. `make cohort` runs steps 2–4.

**Choosing geography.** The goal is a realistic spread of Spanish-speaking share across sites, from a few percent to about 40–50%. Expected Spanish share ≈ 0.51 × the city's Hispanic share, plus a small non-Hispanic component. Suggested spread:

| Band | Example City/State inputs | Status |
|---|---|---|
| High | Texas "El Paso"; Florida "Miami"; California "Los Angeles"; Texas "San Antonio"; New Mexico "Albuquerque" | El Paso tested (6/12 `es`); others UNVERIFIED |
| Middle | New Jersey "Paterson"; Arizona "Phoenix"; Texas "Houston"; Illinois "Chicago"; New York "New York"; Colorado "Denver" | UNVERIFIED |
| Low | Massachusetts "Boston"; Ohio "Columbus"; Minnesota "Minneapolis"; Washington "Seattle"; Georgia "Atlanta"; Pennsylvania "Pittsburgh"; Tennessee "Nashville"; Oregon "Portland"; Michigan "Detroit" | UNVERIFIED |

- **Assignment.** Map cities to sites 101–120 in the manifest. City names are Synthea inputs only. Sites keep their fictional names and generic region labels (`docs/02`), and `roster.json` stores no place.
- **Bad city names.** If Synthea rejects a city name, `build_roster.py` stops with the Synthea error. It does not substitute a default.
- **Site 101.** Suggested: give Hillside Cancer Center (fictional) a high-share city, so the live demo site has Spanish speakers in its simulated roster too.

## 6. Reproducibility and the SAP

- **Commit the derived roster.** Synthea's output depends on jar version, configuration and seed, and whether it is identical across JDK versions and machines is UNVERIFIED. So `roster.json` is committed, and `make site-signal ARGS="--roster synthea"` reads the committed file. Regeneration is optional and is checked against the manifest hash.
- **Pre-registration.** `params.yaml` is frozen by `sap-v1` with `roster.source: parametric` and `synthea_optional: true`. S10 lands at Checkpoint C, after evaluation outputs exist, so the Synthea roster is a labeled sensitivity analysis only (WS5 S10, `docs/11` §11.2):
  1. `run.py` by default, `calibrate.py`, `validate.py` and blind runs keep the parametric roster; `monitoring/out/` and `summary.json` do not change (`git diff --exit-code monitoring/out` stays clean).
  2. `roster.json` is read only by `make site-signal ARGS="--roster synthea"`, which writes a "Roster source" section in `report.md`: "roster language and age mix from Synthea; everything else parametric". Look and Watch thresholds are not recalibrated.
  3. Adding it is logged as a `docs/11` §17 clarification, with the commit and "evaluation outputs seen: yes".

## 7. Rules

| Rule | How it holds |
|---|---|
| 1 (no LLM decisions) | No LLM touches the roster. Synthea is a deterministic simulator. |
| 8 (synthetic data only) | Synthea output is synthetic. Names, addresses, real organization and provider data, and phone numbers are never read. Sites stay fictional. |
| 9 (no licensed content) | No SNOMED CT, LOINC or RxNorm codes or descriptions in git. No keep module with codes. No raw output, no jar. |
| Subject IDs only | The roster has no identifiers at all. Subject IDs are assigned by `roster.py` (`docs/11` §11.2). |

## 8. Parametric roster (default)

Used by the committed study, calibration, validation and blind runs; the Synthea roster is used only by the `--roster synthea` sensitivity run. All values are in `monitoring/params.yaml`; each is tagged ASSUMPTION or cited there.

| Parameter | Value | Note |
|---|---|---|
| Sites | 20 (`101`–`120`); `101` is the live demo site | `design.site_ids` |
| Patients per site | Uniform integer over the range chosen by `docs/11` §11.5 rule P1 (15–30, 20–40, 30–60 or 40–80) | `design.patients_per_site`. A planted small site has 6. |
| Enrollment | Uniform over days 0–84 | `design.enrollment_spread_days` |
| Spanish-speaking share per site | Beta(1.2, 3.0), mean ≈ 0.29; each patient Spanish-speaking with the site's share | ASSUMPTION; gives a spread similar to the high, middle and low bands above |
| Age | Normal(66, 10) | ASSUMPTION |
| Pace | `extra_time` if age ≥ 75 | Same rule as with Synthea |

The parametric roster is fully deterministic from the seed, needs no Java, and runs in CI. The Synthea roster is a realism upgrade for one input, not a dependency.

## 9. Limits to state if Synthea is used

1. It contributes only the roster's language and age mix. Every statistical assumption, rate and planted behavior is ours (`docs/11` §11.3).
2. Its language rule is a national approximation applied city by city (ACS 2017, per the code comments). Real interpreter need and language preference at a cancer center are not modeled.
3. No immunotherapy, no toxicities and no symptom narrative. Synthea cannot validate anything about Site Signal.
4. Records can be clinically incoherent, because modules do not interact. We use no clinical fields, so this does not reach our data.
5. Geography other than El Paso was not tested in planning.
6. The kit sheet "Site Unseen" describes Synthea as "good for simulating, not for proving accuracy". That applies here: Synthea makes the roster look realistic; it proves nothing.

## 10. Other uses considered, not planned

- **Chart-note input** (suggested by the kit sheet "How Are You Feeling?"). Synthea's notes are generic, so useful notes would have to be written from an answer key instead (`docs/backlog.md` BL-09).
- **Baseline comorbidities and concomitant medications** as context for the simulated study. These would add SNOMED/RxNorm handling and no statistical value today (`docs/backlog.md` BL-16).
- **Cancer-filtered cohorts** with a keep module. This needs SNOMED codes in a committed file, so it is not planned.

## Sources

1. synthetichealth/synthea, commit `d9d07a6` (2026-08-18), Apache-2.0: `src/main/java/App.java` (CLI), `src/main/java/org/mitre/synthea/world/geography/Demographics.java` (`languageFromRaceAndEthnicity`), `src/main/java/org/mitre/synthea/export/FhirR4.java` (`Patient.communication`), `src/main/resources/synthea.properties`, `src/main/resources/templates/notes/note.ftl`, `src/main/resources/modules/`. https://github.com/synthetichealth/synthea
2. Synthea wiki, Keep Patients module (`-k`): regenerates rejected patients and gives up on a slot after 1,000 failed attempts. https://github.com/synthetichealth/synthea/wiki/Keep-Patients-Module
3. Synthea release `master-branch-latest`, `synthea-with-dependencies.jar`. https://github.com/synthetichealth/synthea/releases/tag/master-branch-latest
4. synthetichealth/synthea-sample-data. https://github.com/synthetichealth/synthea-sample-data
5. Kit sheet "Check Engine Light" §6 (Synthea for background patients); kit sheet "How Are You Feeling?" §6 (chart-scan input); kit sheet "Site Unseen" (Synthea "good for simulating, not for proving accuracy"). HackRU Fall 2026 challenge kit.
6. Planning runs (Sun Oct 11, 4 vCPU, OpenJDK 21.0.12): runtimes, language counts and the build failure quoted in §2–3. Logs were not committed.
