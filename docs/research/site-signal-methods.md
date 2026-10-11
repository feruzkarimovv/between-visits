# Research · Site Signal methods and evidence

Background notes for Site Signal (`docs/10-site-signal.md`) and its statistical analysis plan (`docs/11-site-signal-sap.md`). They record what earlier work found, which methods we reuse, and where the evidence is thin.

**This page has no Site Signal results.** Every result comes from `validation/site_signal/summary.json`. Planning numbers live in `monitoring/planning/planning_grid.json`, labeled "planning only, not a result". Power figures from earlier planning drafts are withdrawn and should not be quoted.

Written Sun Oct 11 (planning round). Sources were reached through web search, cloned repositories and the HackRU Fall 2026 challenge kit. PubMed, PMC, medRxiv and the ICH site could not be opened from the planning environment, so some figures come from secondary summaries.

| Mark | Meaning |
|---|---|
| Checked | Read in the primary source (paper, guideline, repository file or kit document) during planning. The location is given. |
| UNVERIFIED (secondary) | Taken from an abstract, a news summary or a search snippet. Not checked against the full text. |
| UNVERIFIED | Not checkable at all, or our own inference. |

## 1. Summary

- **Clinicians record fewer symptoms than patients report, across the trials and sites studied** [1–7]. The gap is large and well documented. Two consequences:
  - The useful signal is how one site compares with the others, not the size of the raw gap.
  - The patient stream is a reference, not ground truth [3].
- **Open tools that industry has validated already look for sites with low AE reporting:** simaerep [9–11] and the gsm AE-rate KRI [12]. Both compare a site's AE log with other sites' AE logs, so a site whose patients are healthier and a site that records less produce the same pattern.
- **Regulators recognize centralized statistical monitoring** [19, 20]. The FDA SMART poster names under-reporting of AEs as an example of a site anomaly [17]. It also says the method works best with at least 10 sites and cannot detect a problem that every site shares.
- **Site Signal assembles standard parts:**
  - indirect standardization (O/E);
  - leave-one-site-out expected values;
  - the multiplicative overdispersion adjustment with winsorized z-scores [22, 23];
  - a funnel display.

  The one change is the denominator: each site's own patient-reported episodes, collected through a channel that site staff do not run.
- **Thresholds have to be calibrated by simulation.** Testing 20 sites at a nominal one-sided 5% gives about a 64% chance of at least one false flag per study, and normal-approximation p-values are optimistic when counts are overdispersed (§5).
- **Power for moderate capture gaps is limited at realistic site sizes.** This follows from the design and is stated up front. It is not something tuning can fix (§6).
- **The test that does not rely on our own simulation is retrospective validation** on trials that collected patient-reported and clinician-reported symptoms side by side, with site IDs (§8; `docs/backlog.md` BL-11).

## 2. Clinician vs patient reporting

| # | Study | Design | Finding | Status |
|---|---|---|---|---|
| 1 | Di Maio et al., *J Clin Oncol* 2015 | Pooled analysis of 3 randomized trials, about 1,090 patients, 6 symptoms | Physicians did not report 40.7–74.4% of the symptomatic toxicities patients reported at any severity (lowest share missed for nausea, highest for anorexia), and 13–50% at the highest severity (vomiting to anorexia) | UNVERIFIED (secondary) |
| 2 | Veitch et al., *J Natl Cancer Inst* 2021 | 243 phase I patients completed the PRO-CTCAE library | 19 symptomatic AEs recorded by clinicians in ≤ 1% of patients although ≥ 10% of patients reported them; 9 recorded at least 50 times less often; agreement (kappa) 0.00–0.59, worst for sexual health, bodily emissions and cognition | UNVERIFIED (secondary) |
| 3 | Basch et al., *J Natl Cancer Inst* 2009 | More than 160 patients with lung cancer, patient and clinician reports side by side | Patients reported symptoms earlier, more often and as more severe; clinician reports were more closely associated with unfavorable clinical outcomes | UNVERIFIED (secondary) |
| 4 | Fromme et al., *J Clin Oncol* 2004 | Phase II prostate cancer trial | Clinician reporting described as "neither sensitive nor specific" (via an NCI fact sheet); exact figures not seen | UNVERIFIED (secondary) |
| 5 | Atkinson et al., *Support Care Cancer* 2016 | Systematic review of clinician CTCAE vs patient-reported outcomes | Agreement "moderate at best" | UNVERIFIED (secondary) |
| 6 | *Int J Urol* 2017 (doi:10.1111/iju.13318) | Not confirmed | Clinicians missed diarrhea in 44%, appetite loss 39%, constipation 33%, nausea 22% of patient-reported cases | UNVERIFIED (secondary; authors not confirmed) |
| 7 | Basch, *N Engl J Med* 2010 | Perspective | Argues for patient self-report of symptoms in drug-safety reporting | UNVERIFIED (secondary) |
| 8 | NCI PRO-CTCAE program | Instrument development | Standard investigator reporting "underdetects symptomatic AEs", the stated reason for building PRO-CTCAE | Checked: kit sheet "How Are You Feeling?" §1, citing NCI [8] |

What this means for Site Signal:

1. **The gap is everywhere.** If 40–75% of patient-reported symptoms go unrecorded at a typical site, then a low capture rate on its own says nothing. The indicator compares each site with what the other sites capture for the same symptom mix (`docs/11` §8.1).
2. **The patient stream is a reference, not the truth.** Row 3 shows that clinician reports carry information that patient reports do not. Discordance therefore includes legitimate clinical judgment:
   - baseline symptoms recorded as medical history;
   - attribution to another cause;
   - grade 1 omissions the protocol allows.

   It is never called under-reporting or misconduct (`docs/10` §7.2).
3. **Symptom mix matters.** The miss rate varies several-fold by symptom (rows 1, 2, 6), so the expected count is built per term and grade band, not from one pooled rate.
4. **Severe events are missed less often** (row 1), and in this product every grade 3 episode also pages the nurse. Both push the analysis toward moderate (grade 2) episodes (`docs/10` §4.2).

## 3. Existing site-level methods

### 3.1 simaerep (openpharma; IMPALA consortium)

| Aspect | Detail | Status |
|---|---|---|
| Purpose | Detect sites that over- or under-report subject-level events (AEs, protocol deviations) | Checked: `DESCRIPTION` [11] |
| Input | One row per patient visit: study, site, patient, visit, cumulative event count. Days can replace visits. | Checked: `vignettes/intro.Rmd` [11] |
| Algorithm (classic) | Record the site's events-per-visit rate. Replace every patient with a random study patient who has at least as many visits. Repeat 1,000 times to get a site-specific distribution, place the observed rate in it, then apply Benjamini-Hochberg. The evaluation point is `visit_med75`: about 75% of the median last visit of the site's patients. | Checked: `intro.Rmd`, `classic.Rmd` [11] |
| Default since v1.0.0 | `inframe = TRUE, mult_corr = TRUE, visit_med75 = FALSE, under_only = FALSE`. The "inframe" method uses table operations only and fixed seeds. | Checked: `NEWS.md` v1.0.0 [11] |
| Classic vs inframe | The classic algorithm is faster, keeps a sampling pool of at least 20% of patients, and "all publications using {simaerep} employed the classic algorithm". It has "slightly lower statistical performance". | Checked: `classic.Rmd` [11] |
| Output | `prob` in [−1, 1] (negative = under-reporting) and expected minus reported events (`event_delta`) | From the planning research notes; field names not re-checked in code |
| Validation | Evaluated by three industry members for detecting AE under-reporting [9, 10]. | Evaluation claim checked in `README.md` |
| Stated limit on between-site differences | Planning notes say the authors state the method does not account for differences between sites. We could not find that sentence in the v1.0.0 repository text. | UNVERIFIED |
| Known artifact | Patients who leave early have fewer visits, so the resampling pool favors patients who stay ("survivor bias"); the documentation recommends planned visits for binary events. | Checked: `vignettes/discontinuity.Rmd` [11] |
| License, language | MIT (Roche and authors), R. No `simaerep` package on PyPI (checked during planning). | Checked |
| Version cloned | v1.0.0, commit `7956f45` (2026-09-28) | Checked |

Our comparator ports the **classic (legacy)** algorithm, because the published validations used it, and labels it "simaerep classic (legacy)" everywhere. The v1.0.0 inframe default is not ported (`docs/11` §10.2; `docs/backlog.md` BL-12). The port is fixture-tested against the regression data shipped in the v1.0.0 repository (`R/sysdata.rda`, which NEWS.md says is kept for regression testing against earlier simaerep versions). In planning, `scipy.stats.binomtest` reproduced the Poisson-test p-values of all 10 fixture sites to within floating-point error. The bootstrap probability can only match within Monte Carlo error.

### 3.2 gsm AE-rate KRI (`kri0001`)

| Aspect | Detail | Status |
|---|---|---|
| Definition | Numerator: adverse events. Denominator: days on study. Model: normal approximation. Score: adjusted z-score. | Checked: `inst/workflow/2_metrics/kri0001.yaml`, gsm v2.2.5 [12] |
| Thresholds | −2, −1, 2, 3 (asymmetric, stricter on the low side); `nMinDenominator: 30` days | Checked: same file |
| Overdispersion | φ = mean of squared unadjusted z-scores; adjusted z uses √(φ·μ/T) for rates. No winsorization in this implementation. | Checked: `R/Analyze_NormalApprox.R` [12] |
| Status | No longer maintained since March 2025; split into gsm.core, gsm.mapping, gsm.kri and gsm.reporting. v2.2.5 notes the move from `Gilead-BioStats/gsm` to `Gilead-Public/gsm`. | Checked: `NEWS.md` [12] |
| License | Apache-2.0 | Checked: `DESCRIPTION` |
| Related | `gsm.simaerep` (IMPALA, MIT) runs simaerep inside gsm workflows | Checked: README [13] |

Our gsm-style comparator follows `kri0001`: site-originated AEs per patient-day, Poisson normal approximation, minimum 30 days. Two differences:

- Its multiplicative φ̂ is winsorized at the 10th and 90th percentiles, as for the discordance indicator; gsm itself does not winsorize (`docs/11` §10.1).
- Its tiers come from the same null calibration rather than fixed ±2/±3 limits, so the two indicators are compared at the same false-flag rates.

### 3.3 Other approaches

- **Bayesian hierarchical modeling** of AE reporting rates for under-reporting detection: Barmaz and Ménard, *Drug Saf* 2021 [14]. UNVERIFIED (secondary). Not used here, to keep heavy dependencies out of the repo.
- **Machine learning to predict expected AE reporting** for clinical quality assurance: Ménard et al., *Drug Saf* 2019 [15]. Checked as a citation in Lamberti et al. 2025 [16]. That paper (kit reading) also cites the simaerep validation [9] as an example of transparent statistical models that help regulatory compliance.

### 3.4 FDA CDER SMART poster

"A Data Anomaly Detection Tool for Site Selection at FDA" (Wang, Schuette, Kam; CDER Office of Biostatistics) [17]. Checked against the poster text in the challenge kit.

- **Method.** A battery of statistical tests runs on every variable type: counts, missingness, means, variability, proportions, dates and more. This produces a matrix of site-versus-all-sites p-values. Sites are ranked by −log of an aggregated p-value. The work was done under a cooperative research agreement with a central statistical monitoring vendor.
- **Use.** "Only sites with highest ranks and larger sizes are recommended for inspections."
- **Causes it names:** errors, sloppiness ("under-reporting of AE"), tampering, and sites that are atypical of the underlying population.
- **Caveats:**
  - it works best with at least 10 sites;
  - if all the data are spurious, an anomaly will not be detected;
  - the clinical significance of an anomaly may not be obvious;
  - data preparation is easier with SDTM.

Site Signal adopts the first three caveats directly:

- the minimum of 10 computed sites (`data/signal_rules.json` `minimum_data.min_sites`);
- relative comparison only;
- "a reason to look, not a finding".

A follow-up analysis of sites flagged by central statistical monitoring exists (de Viron et al., *Ther Innov Regul Sci* 2024 [18]); its figures were not checked against the paper and are not quoted here.

### 3.5 Regulatory context

- **ICH E6(R3)** (Step 4, 6 Jan 2025 [19]). From search summaries: centralized monitoring is the review of accumulated data by qualified people, including biostatisticians. It can complement or reduce on-site monitoring, finds systemic or site-specific issues (for example protocol non-compliance or unreliable data), and helps choose sites for targeted visits. The section number (reported as 3.11.4.2) and the EU effective date (reported as 23 Jul 2025) are UNVERIFIED. This is our paraphrase, not checked against the guideline text.
- **FDA, A Risk-Based Approach to Monitoring of Clinical Investigations: Q&A** (2023) [20] encourages risk-based monitoring that uses centralized, data-driven review to decide where on-site effort goes (as summarized in the kit sheet "Check Engine Light" [29]).
- **Cost.** Site monitoring is 9–14% of clinical trial costs (Sertkaya et al. 2016 [21], cited in [29]).
- **ePRO source control.** EMA's guideline on computerised systems and electronic data in clinical trials [28] covers eCOA/ePRO. Whether a sponsor-side patient stream that bypasses the site meets its expectations on investigator control of source data is UNVERIFIED. Shadow mode only (`docs/10` §7.1, §7.7; `docs/backlog.md` BL-20).

### 3.6 The gap these methods leave

Every method above uses the site's own records, or comparisons between sites' records, as its only input. None uses an independent, patient-reported denominator. A single literature search during planning found no published site-level indicator anchored on a patient-reported stream. This novelty claim is UNVERIFIED. Even if the combination is new, its parts are not: patient-vs-clinician discordance has two decades of literature (§2), and the statistics are standard (§4).

## 4. What Site Signal reuses and what it changes

| Element | Source | In Site Signal | Where |
|---|---|---|---|
| Estimand framing | ICH E9(R1) estimand attributes [31] | Per-site, symptom-mix-standardized capture ratio among evaluable, non-paged, new or worsened rule-graded grade ≥ 2 episodes; one-sided (lower capture) | `docs/11` §3 |
| Indirect standardization (O/E) | Standard epidemiology; funnel plots for institutional comparison [22] | E = sum of other sites' capture rates for each episode's term × grade band | `docs/11` §8.1 |
| Leave-one-site-out expected values | Our choice: a site's own episodes never set its own expected rate | Applied to E | `docs/11` §8.1 |
| Overdispersion | Spiegelhalter 2005 [23] (additive random-effects adjustment); gsm uses the multiplicative φ [12] | φ̂ from z-scores winsorized at the 10th and 90th percentiles gives the additive between-site variance τ̂²; z* = (O − E)/√(V + τ̂²E²) with cluster-robust V. The multiplicative form is a sensitivity analysis. | `docs/11` §8.2 |
| Funnel display | Spiegelhalter 2005 [22] | O/E against E with Look and Watch lower limits drawn from the calibrated thresholds; tiers use exact z* | `docs/11` §8.4 |
| Threshold calibration | Simulation-based calibration; ADEMP structure for simulation studies [27] | Pre-registered parametric null with patient frailty, a patient-level capture effect, between-site capture variation and case mix; R = 2000 null studies | `docs/11` §9 |
| Minimum data | SMART caveat [17]; gsm `nMinDenominator` [12] | ≥ 10 computed sites; per site ≥ 10 patients, ≥ 15 evaluable episodes, ≥ 60% call completion; otherwise grey "not computed" | `docs/11` §7 |
| Multiplicity | Benjamini-Hochberg [24] | Secondary q-values only; tiers come from simulation | `docs/11` §8.3 |
| Comparators | gsm `kri0001` [12]; simaerep classic [9–11] | Computed on the identical simulated study, calibrated the same way | `docs/11` §10 |
| Uncertainty on reported rates | Monte Carlo SE; Clopper-Pearson [25] | Every simulated rate carries its MC SE; every eval proportion its exact interval | `docs/11` §12.8 |

What is new is the input, not the arithmetic. A statistician can recompute O, E, V, z, φ̂ and τ̂² by hand from `monitoring/out/*.json`. Task S4 tests a hand-computed 3-site example to 1e-9.

## 5. Multiplicity and threshold calibration

- **Per-site tests across many sites.** If 20 independent sites are each tested at one-sided 5%, P(at least one false flag) = 1 − 0.95²⁰ ≈ 0.64, and the expected number of false flags is 20 × 0.05 = 1.
  - Site Signal keeps this as the **Look** tier and says so on screen: "About 1 false Look flag is expected in a 20-site study with no problems."
- **Family-wise control.** The **Watch** tier uses the 10% quantile of the per-study minimum z* under the null, so P(at least one false Watch flag) ≤ 10%.
  - For orientation only: if the 20 z* values were independent standard normal, this would be a per-site level of about 1 − 0.9^(1/20) ≈ 0.0053 (z ≈ −2.56).
  - The calibrated threshold differs from this because φ̂ is estimated in every study, counts are discrete and small, and patients cluster within sites.
- **Normal-approximation p-values are optimistic under overdispersion.** In exploratory simulation before the SAP (not committed, not a result), Benjamini-Hochberg on normal-approximation p-values did not hold its nominal error rate. Tiers therefore come from simulating the full procedure, including φ̂ estimation (`docs/11` §8.3, §9). `validate.py` measures the achieved false-flag rates on fresh null seeds and reports each with its Monte Carlo SE.
- **Why the null includes a patient effect.** Several episodes from one patient are not independent. A null that treats episodes as independent understates the spread of z and gives too many false flags. The pre-registered null includes patient frailty on episode counts and a patient-level capture effect (`docs/11` §9.1).
- **What the null cannot do.** It is fixed at assumed parameters, not fitted to each study. If real sites differ more than assumed, the real false-flag rate is higher. The misspecification sensitivity analysis reports this (`docs/11` §12.6); a data-fitted null is `docs/backlog.md` BL-13.

## 6. Power considerations

### 6.1 What drives power

| Driver | Effect | Where set |
|---|---|---|
| Evaluable, non-paged episodes per site | Main driver. Equals patients × episode rate × window × call completion × the non-paged share × the evaluable share. | `params.yaml` design and episodes; `docs/11` §11 |
| Paged stratum | Every Fever episode and every grade 3 episode is on a paged call under the current red-flag rules, so the analysis rests mostly on Diarrhea and Dyspnea grade 2. This removes episodes on purpose. | `docs/10` §4.2; `docs/11` §4.4 |
| Size of the capture gap (*f*) | Larger gaps are easier to detect. The required number of episodes grows roughly with 1/*f*² (§6.2). | Planted truth, `docs/11` §11.4 |
| Honest variation between sites and patients | Widens the null and raises φ̂, so a fixed gap is harder to see | Null model, `docs/11` §9.1 |
| Tier | Watch is family-wise, so its threshold is more extreme than Look's and gets more extreme as sites are added | `docs/11` §8.3 |
| Abnormal sites in the same study | Raise φ̂. Winsorization limits this, and what remains makes the test more conservative. | `docs/11` §8.2 |
| Patient-stream error | Spurious episodes have no site match, so they lower O/E. Missed episodes shrink the denominator. Both blur the signal. | Mapping-error model and sensitivity, `docs/11` §11.2, §12.6 |
| Number of sites | More sites give more stable leave-one-site-out rates but a stricter family-wise threshold; below 10 sites nothing is computed | `data/signal_rules.json` |

### 6.2 A rough calculation, for intuition only

Take a site with *n* evaluable, non-paged episodes, other-site capture rates *p_j*, and a planted capture loss *f* (so the site enters an episode with probability (1 − *f*)·*p_j*). Ignore heterogeneity:

```math
\mathbb{E}[O_s - E_s] = -f\,E_s, \qquad
z_s \approx \frac{-f\,E_s}{\sqrt{V_s}}, \qquad
\text{and with all } p_j = p:\quad
z^*_s \approx -f\,\sqrt{n}\,\sqrt{\frac{p}{1-p}}\,\Big/\sqrt{\hat\phi}
```

Reaching a threshold *c* < 0 therefore needs about

```math
n \;\gtrsim\; \hat\phi\, c^2\, \frac{1-p}{f^2\, p}
```

evaluable episodes. Three readings follow:

- Halving the gap needs about four times the episodes.
- The requirement grows in proportion to φ̂.
- Terms that sites capture rarely (low *p*) carry less information per episode.

The sketch is written for a multiplicative adjustment. Under the additive adjustment the SAP uses (`docs/11` §8.2), the inflation factor is 1 + τ̂²E²/V, which grows with site size, so adding patients helps large sites less than the formula suggests. The sketch uses the expected value only. It ignores the variance of O under the alternative and every source of heterogeneity, so real power is lower. Real operating characteristics come only from `validate.py` (`docs/11` §12).

### 6.3 How the design responds

- **Two tiers instead of one operating point.** Look is sensitive; its expected number of false flags per study comes from calibration and is stated on screen. Watch is specific, family-wise ≤ 10%. Power is reported for both tiers, for all three indicators, across a grid of sites × patients per site × *f* × episode rate (`docs/11` §12.2).
- **Moderate gaps are reported, not hidden.** The 25% and 50% capture-loss rows stay in every power table and in the planted study, as honest "mostly missed" cases.
- **The size of the planted gross gap is fixed before any evaluation data exists.** It is the smallest *f* in {0.75, 0.80, 0.85, 0.90} with planning Watch power ≥ 0.80, chosen from `monitoring/planning/planning_grid.json` (dev seed, simplified model) and frozen by the `sap-v1` tag (`docs/11` §11.5).
- **Failure case.** When honest sites differ mainly in recording diligence rather than case mix, the patient-anchored indicator loses its edge over a plain rate KRI. That scenario is run and reported (`docs/11` §12.5).
- **The episode rate is an assumption.** It is set to represent a combination regimen, with a lower-rate row in the grid. At monotherapy-like rates power is lower.

### 6.4 Small-sample arithmetic used elsewhere in the docs

These are exact calculations, not results:

- **Clopper-Pearson** [25]. When all *n* cases succeed, the two-sided 95% interval is [0.025^(1/n), 1]. For 8 of 8 red-flag cases caught that is 63.1–100%, so the data are consistent with a miss rate up to about 37%. The one-sided 95% lower bound is 0.05^(1/8) ≈ 68.8%.
- **Zero-failure N** [26]. To show recall ≥ *p* with one-sided 95% confidence after a run with no misses, you need the smallest *n* with *p*ⁿ ≤ 0.05. That is 29 for 0.90, 59 for 0.95 and 299 for 0.99.

## 7. Threats to validity

| Threat | Why it matters | Response | Where |
|---|---|---|---|
| Circularity: we simulate both streams, plant gaps, then find them | Planted-site recall alone proves only that the code finds what the simulator planted | Design, thresholds, seeds and planted mix are frozen under `sap-v1` before any evaluation output. Comparators run on the same data. Power is shown at 25% and 50% and in the failure case. The claim is limited to "method and power". | `docs/11` §1.2; REQ-022 |
| Our own drafts enter the site AE log | The two streams stop being independent | Rows with `origin = between_visits` never match | `docs/11` §2.4; REQ-024 |
| The nurse page tells the site about the episode | The site's capture of paged episodes is caused by us | Paged episodes are a separate, descriptive stratum, outside O and E | `docs/11` §6.2; REQ-024 |
| Recent episodes look missed | Sites enter AEs after the visit (8 days visit-to-entry, Tufts CSDD) | An episode counts only after max(episode date + 14 days, next visit + 8 days); before that it is "pending" | `docs/11` §6.1 |
| Uneven patient-stream error by language or pace | Spurious episodes lower O/E at sites with many such patients | Mapping error is modeled and stress-tested symmetrically ×2 and ×4 per language; equity strata are shown. The text-mode eval (n = 20) found AE precision 0.833 in English and 1.0 in Spanish [30]. Persona P19 was an escalation false alarm from the post-call safety net, not an AE over-call. Speech-recognition error is unmeasured. | `docs/11` §11.2, §12.6, §14 |
| Legitimate clinical judgment | Baseline symptoms, attribution and grade 1 omissions are not errors | The wording is "capture discordance, a reason to look". Coded query responses include "recorded as medical history" and "not an AE per investigator". | `docs/10` §7.2–7.3 |
| No onset date | The interview has no onset item, so the episode date is the call date and live AESTDTC is the call date | Window from the subject's previous call that reported the symptom below the episode's grade (minus 2 days) to 7 days after the call; narrower and wider windows as sensitivity; an onset item is `docs/backlog.md` BL-05 | `docs/11` §4.3, §5 |
| Term matching without MedDRA | Real sites write verbatim terms that are coded later; for example, diarrhea vs colitis may split | Our own synonym list only, as a stated limit; a sponsor-supplied coding hook is `docs/backlog.md` BL-17 | `docs/11` §5 |
| Only three graded terms | Other symptoms are reported but cannot be banded without new clinical content | Primary set limited to Diarrhea, Fever and Dyspnea at grade 2–3; no conversion table from PRO answers to CTCAE grades | `docs/11` §4.1 |
| Assumed null parameters | If real heterogeneity is larger, false flags exceed the nominal rate | Misspecification sensitivity analysis; data-fitted null is `docs/backlog.md` BL-13 | `docs/11` §12.6 |
| Weak comparator | Beating a legacy algorithm overstates the gain | Labeled "simaerep classic (legacy)"; the inframe port is `docs/backlog.md` BL-12; the gsm-style KRI uses the same calibration | `docs/11` §10 |

## 8. The non-circular test: retrospective validation

Everything in the committed study is simulated. The test that does not depend on our simulator uses completed trials that collected, for the same patients:

- a patient-reported symptom instrument at scheduled times (for example PRO-CTCAE);
- the clinician AE log (SDTM AE with term, grade and start date);
- site IDs, dosing dates and visit dates.

Whether such data are available to us, and under what terms, is UNVERIFIED. Tracked as `docs/backlog.md` BL-11.

Sketch:

1. **Pre-register first** (a new SAP version and tag) before touching the data. Define episodes on the instrument's own scale, for example a pre-specified patient-reported severity level. Do not convert those answers into CTCAE grades. Licensed item wording and MedDRA coding stay with the data holder and never enter git.
2. **Check the null in real data.** Look at the distribution of z* across sites, the size of φ̂, and the share of sites in each tier.
3. **Check against independent evidence.** Do flagged sites coincide with quality findings made without the patient stream: monitoring visit findings, source-data verification discrepancies, audit or inspection findings, query rates?
4. **Check stability.** Are the same sites flagged in the first and second halves of enrollment?
5. **Check where discordance sits.** Is it concentrated in terms or grades where clinical judgment legitimately differs, such as fatigue at grade 1?
6. **Check against the rate KRI.** Does adjusting for case mix change the ranking of sites compared with a plain AE-rate KRI on the same trials?

A null result here, meaning no association with independent quality evidence, would be a reason to stop. It would not be a reason to tune.

## 9. Sources

1. Di Maio M, Gallo C, Leighl NB, et al. Symptomatic toxicities experienced during anticancer treatment: agreement between patient and physician reporting in three randomized trials. *J Clin Oncol* 2015;33(8):910–915. UNVERIFIED (secondary) for the figures quoted.
2. Veitch ZW, Shepshelovich D, Gallagher C, et al. Underreporting of symptomatic adverse events in phase I clinical trials. *J Natl Cancer Inst* 2021;113(8):980–988. https://academic.oup.com/jnci/article/113/8/980/6146406
3. Basch E, Jia X, Heller G, et al. Adverse symptom event reporting by patients vs clinicians: relationships with clinical outcomes. *J Natl Cancer Inst* 2009;101(23):1624–1632. https://pmc.ncbi.nlm.nih.gov/articles/PMC2786917
4. Fromme EK, et al. How accurate is clinician reporting of chemotherapy adverse effects? *J Clin Oncol* 2004;22(17):3485–3490. Characterization via an NCI PRO-CTCAE fact sheet; UNVERIFIED.
5. Atkinson TM, et al. The association between clinician-based common terminology criteria for adverse events (CTCAE) and patient-reported outcomes (PRO): a systematic review. *Support Care Cancer* 2016;24(8):3669–3676. UNVERIFIED (secondary).
6. *Int J Urol* 2017, doi:10.1111/iju.13318. https://onlinelibrary.wiley.com/doi/10.1111/iju.13318. UNVERIFIED (secondary).
7. Basch E. The missing voice of patients in drug-safety reporting. *N Engl J Med* 2010;362(10):865–869. UNVERIFIED (secondary).
8. NCI. PRO-CTCAE development and testing. https://healthcaredelivery.cancer.gov/pro-ctcae/testing.html, as cited in the kit sheet "How Are You Feeling?" §1.
9. Koneswarakantha B, Adyanthaya R, Emerson J, et al. An open-source R package for detection of adverse events under-reporting in clinical trials: implementation and validation by the IMPALA (Inter coMPany quALity Analytics) consortium. *Ther Innov Regul Sci* 2024;58:591–599. doi:10.1007/s43441-024-00631-8 (as listed in the simaerep v1.0.0 README and DESCRIPTION).
10. Koneswarakantha B, Barmaz Y, Ménard T, et al. Follow-up on the use of advanced analytics for clinical quality assurance: bootstrap resampling to enhance detection of adverse event under-reporting. *Drug Saf* 2020. doi:10.1007/s40264-020-01011-5
11. openpharma/simaerep v1.0.0 (MIT), commit `7956f45`: `DESCRIPTION`, `README.md`, `NEWS.md`, `vignettes/intro.Rmd`, `vignettes/classic.Rmd`, `vignettes/discontinuity.Rmd`, `R/sysdata.rda`. https://github.com/openpharma/simaerep · https://openpharma.github.io/simaerep/
12. Gilead gsm v2.2.5 (Apache-2.0): `inst/workflow/2_metrics/kri0001.yaml`, `R/Analyze_NormalApprox.R`, `NEWS.md`. https://github.com/Gilead-BioStats/gsm (moved to `Gilead-Public/gsm` per `NEWS.md`)
13. IMPALA-Consortium/gsm.simaerep (MIT). https://github.com/IMPALA-Consortium/gsm.simaerep
14. Barmaz Y, Ménard T. Bayesian modeling for the detection of adverse events underreporting in clinical trials. *Drug Saf* 2021;44:949. UNVERIFIED (secondary).
15. Ménard T, Barmaz Y, Koneswarakantha B, Bowling R, Popko L. Enabling data-driven clinical quality assurance: predicting adverse event reporting in clinical trials using machine learning. *Drug Saf* 2019;42(9):1045–1053. Checked as reference 17 of [16].
16. Lamberti MJ, et al. *Ther Innov Regul Sci* 2025;59:1074–1086 (challenge kit reading). References 17 and 39.
17. Wang X(T), Schuette P, Kam M. A Data Anomaly Detection Tool for Site Selection at FDA. FDA CDER, Office of Biostatistics, poster (challenge kit reading).
18. de Viron S, et al. *Ther Innov Regul Sci* 2024: analysis of sites flagged by central statistical monitoring. UNVERIFIED (secondary; title, authors and figures not confirmed).
19. ICH E6(R3) Guideline for Good Clinical Practice, Step 4, 6 Jan 2025. https://www.ich.org/page/efficacy-guidelines. Paraphrase UNVERIFIED.
20. FDA. A Risk-Based Approach to Monitoring of Clinical Investigations: Questions and Answers (2023). https://www.fda.gov/regulatory-information/search-fda-guidance-documents/risk-based-approach-monitoring-clinical-investigations-questions-and-answers
21. Sertkaya A, Wong HH, Jessup A, Beleche T. Key cost drivers of pharmaceutical clinical trials in the United States. *Clin Trials* 2016;13(2):117–126. https://journals.sagepub.com/doi/10.1177/1740774515625964
22. Spiegelhalter DJ. Funnel plots for comparing institutional performance. *Stat Med* 2005;24(8):1185–1202.
23. Spiegelhalter DJ. Handling over-dispersion of performance indicators. *Qual Saf Health Care* 2005;14(5):347–351.
24. Benjamini Y, Hochberg Y. Controlling the false discovery rate: a practical and powerful approach to multiple testing. *J R Stat Soc B* 1995;57(1):289–300.
25. Clopper CJ, Pearson ES. The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika* 1934;26(4):404–413.
26. Hanley JA, Lippman-Hand A. If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA* 1983;249(13):1743–1745.
27. Morris TP, White IR, Crowther MJ. Using simulation studies to evaluate statistical methods. *Stat Med* 2019;38(11):2074–2102.
28. EMA. Guideline on computerised systems and electronic data in clinical trials, EMA/INS/GCP/112288/2023. https://www.ema.europa.eu/en/documents/regulatory-procedural-guideline/guideline-computerised-systems-electronic-data-clinical-trials_en.pdf. Specific passages UNVERIFIED.
29. Starter sheet "Check Engine Light" (HackRU Fall 2026 challenge kit), §1, §7, §10.
30. `eval/results/latest.json` (text-mode evaluation, 20 simulated personas): `by_language.*.ae_precision`, `known_misses`.
31. ICH E9(R1) Addendum on estimands and sensitivity analysis in clinical trials, Step 4, 20 Nov 2019.
