# What it gets wrong

This page lists the limits of Between Visits and of Site Signal, its sponsor-side layer, with the numbers that show them. It is the reader-facing version of `docs/10-site-signal.md` §10 and `docs/11-site-signal-sap.md` §16.

- **Site Signal numbers are SIMULATED.** Every one is read from `validation/site_signal/summary.json` (operating characteristics, `docs/11` §12) or `monitoring/out/*.json` (the committed evaluation study). None is typed by hand. They are rounded only for display (`docs/11` §15 rule 6): proportions to 2 decimals, Monte Carlo standard errors (MC SE) and interval limits to 3.
- **Evaluation numbers come from `eval/results/latest.json`.** That is the text-mode evaluation with 20 simulated patients. Each number names its key in that file.
- **No real voice-call (MEASURED) numbers yet.** `eval/results/voice_checks.json` holds only pending rows until the real calls are made (task V10, a human step), so this page quotes none.
- **How each number was checked** is at the end of this page.

Site Signal measures **capture discordance**. It compares the episodes a site's own patients reported on their between-visit calls with the site's AE log, relative to the other sites, and flags sites at two tiers. **Look** is a per-site 5% tier. **Watch** is a study-wide tier: at most a 10% chance of any false Watch flag per study under the pre-registered null. A flag is a reason to look, not a finding. A site with no flag reads "No signal at this sample size", never anything stronger.

## 1. Moderate capture gaps are mostly invisible at the Watch tier

The `sap-v1` design has 20 sites, 40 to 80 patients per site, and an assumed 1.5 grade ≥ 2 episodes per patient. One planted site loses a share *f* of its episodes from the AE log. The table gives how often the discordance indicator flags it, with the thresholds frozen in `monitoring/out/thresholds.json`.

| Planted capture loss *f* (SIMULATED) | Flagged at Look or Watch | Flagged at Watch |
|---|---|---|
| 0.25 | 0.15 (MC SE 0.021) | 0.03 (MC SE 0.009) |
| 0.50 | 0.51 (MC SE 0.029) | 0.22 (MC SE 0.024) |
| 0.90 (gross loss) | 0.77 (MC SE 0.024) | 0.70 (MC SE 0.026) |

The pre-tag planning grid used a simplified model. Its value for the gross row at Watch was 0.72 (planning, simplified); the final value is the one in the table.

The Look tier catches more, at a price. Under the pre-registered null, a study with no problems is expected to show about 0.75 false Look flags (MC SE 0.015). The calibration estimate of the same quantity, shown in the `/sites` footer, is 0.8 (`thresholds.json`).

This heading was written before any result existed (`docs/10` §10.2), with the rule that the heading is corrected, not the numbers, if they disagree. The Watch column bears it out: most 25% and 50% gaps go unflagged at Watch.

The comparators flag the same planted site as follows (SIMULATED, same design and replicates):

| Indicator | *f* | Look or Watch | Watch |
|---|---|---|---|
| gsm-style AE-rate KRI | 0.25 | 0.19 (MC SE 0.023) | 0.02 (MC SE 0.007) |
| gsm-style AE-rate KRI | 0.50 | 0.50 (MC SE 0.029) | 0.13 (MC SE 0.019) |
| gsm-style AE-rate KRI | 0.90 | 0.99 (MC SE 0.005) | 0.78 (MC SE 0.024) |
| simaerep classic (legacy) | 0.25 | 0.07 (MC SE 0.014) | 0.02 (MC SE 0.008) |
| simaerep classic (legacy) | 0.50 | 0.14 (MC SE 0.020) | 0.04 (MC SE 0.012) |
| simaerep classic (legacy) | 0.90 | 0.12 (MC SE 0.019) | 0.03 (MC SE 0.010) |

Discordance is not ahead of the plain AE-rate KRI everywhere, even at the design and without the failure case of §3. The paired differences (discordance minus KRI, same replicates, `head_to_head.grid`) are:

- **50% gap, Watch:** 0.09 (paired MC SE 0.029). Discordance is ahead.
- **25% gap, Look or Watch:** -0.04 (paired MC SE 0.031). No clear difference.
- **Gross loss, Look or Watch:** -0.22 (paired MC SE 0.025). **Gross loss, Watch:** -0.08 (paired MC SE 0.033). The KRI is ahead.

One reason is the minimum-data rule. Discordance needs a minimum number of evaluable non-paged episodes per site (`data/signal_rules.json` `minimum_data`), and a planted site that is not computed counts as a miss. At the design the planted site was computed in 0.77 of studies, against 1.00 for the KRI, so the discordance power above can never exceed 0.77.

**At a lower episode rate, discordance is not computed at all.** With *μ* = 0.5 (closer to monotherapy, §6), the planted site never reached the minimum data in any cell of the power grid. For example, at 20 sites with 60 patients each and a 50% gap, it was computed in 0.00 of studies, so discordance flagged it in 0.00 at Look or Watch. The AE-rate KRI, which has no episode minimum, flagged it in 0.46 (MC SE 0.029). The rows are the `summary.json` `power[]` rows with `mu` 0.5 (SIMULATED).

## 2. False flags under the null (REQ-023)

These come from 2000 fresh null studies at the `sap-v1` design, with no planted site and the frozen thresholds (SIMULATED). REQ-023 passes when each rate is at most its nominal rate + 2·√(SE_cal² + SE_val²). SE_val is the MC SE below; SE_cal is the MC SE of the threshold's achieved in-sample rate in `thresholds.json`. Unrounded values are compared (`docs/11` §12.1).

| Rate (discordance) | Value | MC SE | Nominal | REQ-023 bound | Outcome |
|---|---|---|---|---|---|
| False Look per site | 0.05 | 0.001 | 0.05 | 0.053 | met (conservative: below the nominal rate) |
| Any false Watch per study | 0.11 (Clopper-Pearson 95% CI [0.095, 0.122]) | 0.007 | 0.10 | 0.119 | met |

A rate below nominal is conservative, not a failure. **Size calibration** checks the false Look rate by expected site size (tertiles of *E*). Each tertile must be within the nominal rate ± 0.02 (SIMULATED):

| Tertile 1 (smallest sites) | Tertile 2 | Tertile 3 (largest sites) | Check |
|---|---|---|---|
| 0.03 (MC SE 0.002) | 0.05 (MC SE 0.002) | 0.06 (MC SE 0.002) | met |

A failed check is reported here and in `validation/site_signal/report.md`, never hidden.

## 3. In the failure case a plain AE-rate KRI does much better

Discordance can beat a plain AE-rate KRI only if honest sites differ mostly in case mix (how sick their patients are) and not in how thoroughly they record AEs. The failure case reverses that assumption: between-site capture SD 0.6 (logit scale) and case-mix SD 0.2 (SIMULATED).

**(a) Thresholds re-calibrated under the failure-case null.** With a correct null, does discordance keep any advantage? No. The plain AE-rate KRI flags the planted site far more often than discordance, at both tiers:

| Indicator | *f* | Look or Watch | Watch |
|---|---|---|---|
| Discordance | 0.50 | 0.30 (MC SE 0.026) | 0.04 (MC SE 0.011) |
| AE-rate KRI | 0.50 | 0.82 (MC SE 0.022) | 0.36 (MC SE 0.028) |
| Discordance | 0.90 | 0.82 (MC SE 0.022) | 0.48 (MC SE 0.029) |
| AE-rate KRI | 0.90 | 1.00 (MC SE 0.000) | 0.99 (MC SE 0.005) |

**(b) The frozen `sap-v1` thresholds kept, null data from the failure case.** This shows the cost of a wrong null. Every rate below is above its nominal rate (0.05 per site at Look, 0.10 per study at Watch):

| Indicator | False Look per site | Any false Watch per study |
|---|---|---|
| Discordance | 0.06 (MC SE 0.001) | 0.15 (MC SE 0.011) |
| AE-rate KRI | 0.06 (MC SE 0.001) | 0.21 (MC SE 0.013) |

## 4. Both streams are simulated

The 20-site study, its patients, their calls, the patient-reported episodes and every site's AE log are generated by `monitoring/bvsignal/simulate.py`. Thresholds, power and the answer key all come from the same model family. The planted-site results show the method and its power under stated assumptions, not real-world validity. Calls at the demo site 101 (live or replayed) are labeled MEASURED and are never pooled with the simulated episodes.

## 5. The thresholds come from an assumed null

The Look and Watch thresholds were calibrated once, at the `sap-v1` design, from a parametric null with assumed design parameters (`monitoring/params.yaml`): patient frailty, a patient-level capture effect with SD 0.5, a between-site capture SD of 0.35 (logit scale) and a case-mix SD of 0.35. They are not fitted to each study. When real sites differ more than assumed, the false-flag rate is higher than stated. These misspecified-null rows keep the frozen thresholds and change the data (SIMULATED):

| Scenario | Data generated with | False Look per site | Any false Watch per study |
|---|---|---|---|
| SE9 | between-site capture SD 0.2 | 0.04 (MC SE 0.003) | 0.05 (MC SE 0.013) |
| SE10 | between-site capture SD 0.5 | 0.05 (MC SE 0.002) | 0.14 (MC SE 0.020) |
| SE11 | between-site capture SD 0.6 | 0.06 (MC SE 0.003) | 0.15 (MC SE 0.021) |
| SE12 | patient random-effect SD 0.0 | 0.05 (MC SE 0.003) | 0.11 (MC SE 0.018) |
| SE13 | patient random-effect SD 1.0 | 0.04 (MC SE 0.003) | 0.09 (MC SE 0.017) |

A data-fitted null is not built (`NOT_BUILT.md`, BL-13).

## 6. The episode rate is an assumption

The design assumes 1.5 grade ≥ 2 episodes per patient per 36-week window. That figure represents a combination regimen and is an ASSUMPTION; clinician-reported incidence with an anti-PD-1 antibody alone is lower (UNVERIFIED). At lower rates each site has fewer episodes and more sites fall below the minimum data. At *μ* = 0.5 the planted site never reached the minimum data in the power grid, so discordance never flagged it there, while the AE-rate KRI still did (§1; `power[]` rows with `mu` 0.5).

## 7. Three terms only, and mostly grade 2

Only Diarrhea, Fever and Dyspnea have grade 2 and grade 3 rules (`data/ctcae_rules.json`). Every other symptom is "reported, ungraded" and outside the analysis. Red flags page for every Fever episode and every grade 3 episode, and paged episodes are a separate stratum (§12). So O/E rests mostly on non-paged grade 2 Diarrhea and Dyspnea episodes. Grading more terms needs clinical review (BL-06).

## 8. Episode date = call date

The interview has no onset item, so an episode's date is the date of the call that captured it, and the live AE start date is the call date too. The match window looks back to the subject's previous call that reported the symptom below the episode's grade, with 2 days of tolerance, and 7 days forward. A site AE dated earlier than that cannot match. Window sensitivity is in `summary.json` (`sensitivity` SE1, SE2). An onset item is BL-05.

## 9. No MedDRA

Matching uses CTCAE terms and our own synonym list in `data/signal_rules.json`. Real sites record verbatim terms that are coded later, and equivalent terms (for example diarrhea and colitis) can split. Real matching needs licensed coding by the sponsor (BL-17). No MedDRA content is in this repository.

## 10. Patient-stream error is assumed, not measured

The simulation assumes a per-answer mapping error with mean 0.05, the same in both languages. The text-mode evaluation (20 simulated patients) is too small to estimate error by language or pace. Speech-recognition and accent error are **unmeasured**: the safety evaluation is text mode, and real-call checks are pending (BL-01). Sensitivity rows SE3–SE6 in `summary.json` double and quadruple the error for one language at a time.

## 11. The known miss in our own evaluation (P19)

Text-mode evaluation, `eval/results/latest.json`: 19 of 20 personas passed (`overall.passed`, 95% CI [0.751, 0.999]). Urgent and emergency cases paged: 8 of 8 (`overall.red_flag_recall`, 95% CI [0.631, 1]). A run this small cannot rule out missing more than a third of red flags. Showing recall of at least 0.95 with one-sided 95% confidence needs 59 consecutive catches without a miss (`zero_failure_n`).

The one failure is P19 (Spanish, extra time), a false urgent page (`known_misses`). The live call was correct. The post-call safety net, which is told to include a flag when unsure, raised the severe-diarrhea red flag from "muchas veces, no sé cuántas" although the count threshold was never stated. This is conservative by design: false alarms are acceptable, misses are not. The planned fix routes such unconfirmed safety-net hits to a nurse callback instead of an urgent page, after clinical review (BL-04).

P19 was an escalation false alarm, not an AE-term error: AE precision is 1.0 in Spanish and 0.833 in English (`by_language.*.ae_precision`).

## 12. Paged episodes are a separate stratum

Red-flag pages reach the site, so an episode on a paged call is excluded from O/E and reported separately. A page may also raise the site's capture of the same subject's other episodes nearby. Two sensitivity rows bound this with the frozen thresholds (SIMULATED):

| Scenario | False Look per site | Any false Watch per study |
|---|---|---|
| SE14: episode paged if any page for the subject falls within 7 days | 0.05 (MC SE 0.003) | 0.10 (MC SE 0.017) |
| SE15: higher capture near urgent calls at the 5 most-paged sites | 0.05 (MC SE 0.002) | 0.09 (MC SE 0.016) |

When Between Visits drafts reach a site's staff (integrated mode), the two streams are no longer independent. Such a site is "Not computed" with that reason; an indicator for integrated mode is not built (BL-14).

## 13. Discordance includes legitimate clinical judgment

An unmatched episode is not an error. The site may have recorded it as medical history, judged it not to be an AE, or graded it differently. The site query asks the site to review its source documents and either enter the event or say why no entry is needed. "Recorded as medical history" and "not an AE per investigator" are normal answers. Every simulated study plants an honest site with low recording diligence. In the full planted mix (SIMULATED), discordance flags it at Look in 0.00 of studies (MC SE 0.001) and at Watch in 0.00 (MC SE 0.000). A plain honest site is flagged at Look in 0.00 (MC SE 0.000). Both are below the null rate of §2 because each site is compared with the other sites of its study, and in the full mix the planted sites lower that reference. A flag is a reason to look, not a finding about the site.

## 14. The committed study is an illustration, not evidence

The study on the `/sites` page is one draw (`monitoring/out/`, SIMULATED). Five planted sites, two must-be-grey sites and the rest honest. At Watch, discordance caught 0 planted sites, missed 5 and flagged 0 honest sites. At Look or Watch it caught 2, missed 3 and flagged 0 honest sites. In this draw the plain AE-rate KRI did better at Watch: it caught 2 planted sites (the two gross-loss sites, which discordance placed at Look only), missed 3 and flagged 0 honest sites. Discordance did not compute the language-gap site (too few evaluable episodes), which counts as a miss. simaerep classic caught 0 at Look or Watch. With five positives these counts carry little information; sections 1 to 3 are the evidence.

## 15. Language gaps within a site: low power

Within sites, the Mantel-Haenszel odds ratio of capture for Spanish-speaking versus English-speaking patients in the committed study is 1.00 (patient-cluster bootstrap 95% CI [0.580, 1.846], 11 sites with enough episodes in both groups; SIMULATED). Below 1 means lower capture for Spanish-speaking patients. Power is low, and a gap planted at one site is diluted in the pooled estimate. The separate Equity tab, the per-site odds ratios and the single-language toggle were cut this round (`NOT_BUILT.md`, #22). The pooled odds ratios above are shown to the CRA and sponsor in the Equity block of the How well it works tab; per-site values are in `monitoring/out/equity.json` and `validation/site_signal/report.md`.

## 16. Other limits

- **simaerep classic is the legacy algorithm.** simaerep v1.0.0 defaults to its inframe method, which is not ported (BL-12).
- **Demo-grade security.** Roles are demo identity headers, with no real authentication (BL-18). It runs on SQLite, one instance. The audit hash chain is tamper-evident only inside the database (BL-19).
- **Regulatory questions are open (UNVERIFIED).** These include investigator control of patient-reported source data, and what sponsor awareness of an unfiltered patient stream means for safety reporting (BL-20). Site Signal runs in shadow mode only.
- **The blind run is not built.** No one can yet test the method on a study nobody prepared (`NOT_BUILT.md`).
- **The power grid is bit-reproducible only on the platform of the committed run.** The CI quick check re-runs the first replicates of every validation stream and compares a hash of the per-replicate results with `summary.json` (`docs/11` §12). On Linux (ubuntu-latest, x86_64) it reproduces the committed study, the null validation and the failure-case and sensitivity streams bit for bit, but not the power grid that the power numbers of section 1 come from (CI run 38141286952). On macOS arm64, where the committed runs were made, all four match, and CI now runs the check there (`docs/11` §17 C8). How far the Linux power-grid results differ, and whether any displayed power value would change, was not measured.

## The next step, the one that is not circular

Every Site Signal result here comes from our own simulator. The test that does not depend on it is retrospective. It needs completed trials that collected patient-reported symptoms and the clinician AE log (CTCAE) for the same patients, with site IDs. The method would be pre-registered as a new SAP version before data access, and the results reported whatever they show (BL-11).

## How every number was checked

1. **No Site Signal number on this page, in the README, in the deck (`docs/pitch/deck.html`), in the video storyboard (`docs/08-demo-and-pitch.md`) or in the results table of `docs/10-site-signal.md` §10.1 was typed.** Each was written as a token naming its source file, its JSON path and its display format. `validation/render_numbers.py` replaced each token with the value from `validation/site_signal/summary.json` or `monitoring/out/<file>.json`, rounded by `docs/11` §15 rule 6. It fails, writing nothing, when a path is missing or matches more than one row. The REQ-023 bounds and outcomes and the size check are computed by the same script from the unrounded values (`docs/11` §12.1).
2. **`python3 validation/render_numbers.py --check <rendered files>` passed.** It confirms that no token is left. It reads each value in the table below from its source path again and confirms that the document shows the same digits on the listed line.
3. **Evaluation numbers** (section 11) were copied from `eval/results/latest.json`, and the key is named next to each one.
4. **A second teammate ticks the table below against the source files** before the deck and the video use these numbers.

<!-- ss-provenance:start -->
Rendered by `validation/render_numbers.py` from `validation/site_signal/ and monitoring/out/` (`sap_tag_commit` 68838978bb305e0f730d30e5cbf3c00bceca5a25, `eval_seed` 92794863, `code_commit` 9204a1e025443d19150cc4bb7c41c02d485fb620, `generated_at` 2026-10-11T08:18:52-04:00; `_about`: Site Signal operating characteristics (docs/11-site-signal-sap.md §12). Every number is SIMULATED; capture discordance is a reason to look, not a finding. Values are unrounded; round only for display.). 400 values, every one SIMULATED. The path column is the path actually read; a path after `//` in the token was a fallback.

| # | Where | Value | Source file | JSON path | Format | Used |
|---|---|---|---|---|---|---|
| 1 | `WHAT_IT_GETS_WRONG.md`:14 | `20` | `validation/site_signal/summary.json` | `design.n_sites` | `int` | `first` |
| 2 | `WHAT_IT_GETS_WRONG.md`:14 | `40` | `validation/site_signal/summary.json` | `design.patients_per_site[0]` | `int` | `first` |
| 3 | `WHAT_IT_GETS_WRONG.md`:14 | `80` | `validation/site_signal/summary.json` | `design.patients_per_site[1]` | `int` | `first` |
| 4 | `WHAT_IT_GETS_WRONG.md`:14 | `1.5` | `validation/site_signal/summary.json` | `design.mu` | `f1` | `first` |
| 5 | `WHAT_IT_GETS_WRONG.md`:18 | `0.15` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 6 | `WHAT_IT_GETS_WRONG.md`:18 | `0.021` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 7 | `WHAT_IT_GETS_WRONG.md`:18 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 8 | `WHAT_IT_GETS_WRONG.md`:18 | `0.009` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 9 | `WHAT_IT_GETS_WRONG.md`:19 | `0.51` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 10 | `WHAT_IT_GETS_WRONG.md`:19 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 11 | `WHAT_IT_GETS_WRONG.md`:19 | `0.22` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 12 | `WHAT_IT_GETS_WRONG.md`:19 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 13 | `WHAT_IT_GETS_WRONG.md`:20 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 14 | `WHAT_IT_GETS_WRONG.md`:20 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 15 | `WHAT_IT_GETS_WRONG.md`:20 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 16 | `WHAT_IT_GETS_WRONG.md`:20 | `0.70` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 17 | `WHAT_IT_GETS_WRONG.md`:20 | `0.026` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 18 | `WHAT_IT_GETS_WRONG.md`:22 | `0.72` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].planning_power` | `p2` | `first` |
| 19 | `WHAT_IT_GETS_WRONG.md`:24 | `0.75` | `validation/site_signal/summary.json` | `null.look_per_study.rate` | `f2` | `first` |
| 20 | `WHAT_IT_GETS_WRONG.md`:24 | `0.015` | `validation/site_signal/summary.json` | `null.look_per_study.mc_se` | `f3` | `first` |
| 21 | `WHAT_IT_GETS_WRONG.md`:24 | `0.8` | `monitoring/out/thresholds.json` | `expected_false_look_flags_per_study` | `f1` | `first` |
| 22 | `WHAT_IT_GETS_WRONG.md`:32 | `0.19` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 23 | `WHAT_IT_GETS_WRONG.md`:32 | `0.023` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 24 | `WHAT_IT_GETS_WRONG.md`:32 | `0.02` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 25 | `WHAT_IT_GETS_WRONG.md`:32 | `0.007` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 26 | `WHAT_IT_GETS_WRONG.md`:33 | `0.50` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 27 | `WHAT_IT_GETS_WRONG.md`:33 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 28 | `WHAT_IT_GETS_WRONG.md`:33 | `0.13` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 29 | `WHAT_IT_GETS_WRONG.md`:33 | `0.019` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 30 | `WHAT_IT_GETS_WRONG.md`:34 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 31 | `WHAT_IT_GETS_WRONG.md`:34 | `0.99` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 32 | `WHAT_IT_GETS_WRONG.md`:34 | `0.005` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 33 | `WHAT_IT_GETS_WRONG.md`:34 | `0.78` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 34 | `WHAT_IT_GETS_WRONG.md`:34 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 35 | `WHAT_IT_GETS_WRONG.md`:35 | `0.07` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 36 | `WHAT_IT_GETS_WRONG.md`:35 | `0.014` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 37 | `WHAT_IT_GETS_WRONG.md`:35 | `0.02` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 38 | `WHAT_IT_GETS_WRONG.md`:35 | `0.008` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 39 | `WHAT_IT_GETS_WRONG.md`:36 | `0.14` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 40 | `WHAT_IT_GETS_WRONG.md`:36 | `0.020` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 41 | `WHAT_IT_GETS_WRONG.md`:36 | `0.04` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 42 | `WHAT_IT_GETS_WRONG.md`:36 | `0.012` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 43 | `WHAT_IT_GETS_WRONG.md`:37 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 44 | `WHAT_IT_GETS_WRONG.md`:37 | `0.12` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 45 | `WHAT_IT_GETS_WRONG.md`:37 | `0.019` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 46 | `WHAT_IT_GETS_WRONG.md`:37 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 47 | `WHAT_IT_GETS_WRONG.md`:37 | `0.010` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 48 | `WHAT_IT_GETS_WRONG.md`:41 | `0.09` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].power_diff` | `f2` | `first` |
| 49 | `WHAT_IT_GETS_WRONG.md`:41 | `0.029` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].paired_mc_se` | `f3` | `first` |
| 50 | `WHAT_IT_GETS_WRONG.md`:42 | `-0.04` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.25].power_diff` | `f2` | `first` |
| 51 | `WHAT_IT_GETS_WRONG.md`:42 | `0.031` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.25].paired_mc_se` | `f3` | `first` |
| 52 | `WHAT_IT_GETS_WRONG.md`:43 | `-0.22` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.9].power_diff` | `f2` | `first` |
| 53 | `WHAT_IT_GETS_WRONG.md`:43 | `0.025` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.9].paired_mc_se` | `f3` | `first` |
| 54 | `WHAT_IT_GETS_WRONG.md`:43 | `-0.08` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.9].power_diff` | `f2` | `first` |
| 55 | `WHAT_IT_GETS_WRONG.md`:43 | `0.033` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.9].paired_mc_se` | `f3` | `first` |
| 56 | `WHAT_IT_GETS_WRONG.md`:45 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 57 | `WHAT_IT_GETS_WRONG.md`:45 | `1.00` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 58 | `WHAT_IT_GETS_WRONG.md`:45 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 59 | `WHAT_IT_GETS_WRONG.md`:47 | `20` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].n_sites` | `int` | `first` |
| 60 | `WHAT_IT_GETS_WRONG.md`:47 | `60` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].patients_per_site` | `int` | `first` |
| 61 | `WHAT_IT_GETS_WRONG.md`:47 | `0.00` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].p_computed` | `p2` | `first` |
| 62 | `WHAT_IT_GETS_WRONG.md`:47 | `0.00` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].power` | `p2` | `first` |
| 63 | `WHAT_IT_GETS_WRONG.md`:47 | `0.46` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].power` | `p2` | `first` |
| 64 | `WHAT_IT_GETS_WRONG.md`:47 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].mc_se` | `f3` | `first` |
| 65 | `WHAT_IT_GETS_WRONG.md`:51 | `2000` | `validation/site_signal/summary.json` | `null.r` | `int` | `first` |
| 66 | `WHAT_IT_GETS_WRONG.md`:55 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site.rate` | `p2` | `first` |
| 67 | `WHAT_IT_GETS_WRONG.md`:55 | `0.001` | `validation/site_signal/summary.json` | `null.look_per_site.mc_se` | `f3` | `first` |
| 68 | `WHAT_IT_GETS_WRONG.md`:55 | `0.05` | `derived (docs/11 §12.1)` | `req023.look.nominal` | `p2` | `first` |
| 69 | `WHAT_IT_GETS_WRONG.md`:55 | `0.053` | `derived (docs/11 §12.1)` | `req023.look.bound` | `f3` | `first` |
| 70 | `WHAT_IT_GETS_WRONG.md`:55 | `met (conservative: below the nominal rate)` | `derived (docs/11 §12.1)` | `req023.look.outcome` | `text` | `first` |
| 71 | `WHAT_IT_GETS_WRONG.md`:56 | `0.11` | `validation/site_signal/summary.json` | `null.watch_fwer.rate` | `p2` | `first` |
| 72 | `WHAT_IT_GETS_WRONG.md`:56 | `[0.095, 0.122]` | `validation/site_signal/summary.json` | `null.watch_fwer.ci95` | `ci3` | `first` |
| 73 | `WHAT_IT_GETS_WRONG.md`:56 | `0.007` | `validation/site_signal/summary.json` | `null.watch_fwer.mc_se` | `f3` | `first` |
| 74 | `WHAT_IT_GETS_WRONG.md`:56 | `0.10` | `derived (docs/11 §12.1)` | `req023.watch.nominal` | `p2` | `first` |
| 75 | `WHAT_IT_GETS_WRONG.md`:56 | `0.119` | `derived (docs/11 §12.1)` | `req023.watch.bound` | `f3` | `first` |
| 76 | `WHAT_IT_GETS_WRONG.md`:56 | `met` | `derived (docs/11 §12.1)` | `req023.watch.outcome` | `text` | `first` |
| 77 | `WHAT_IT_GETS_WRONG.md`:58 | `0.02` | `derived (docs/11 §12.1)` | `size.tolerance` | `p2` | `first` |
| 78 | `WHAT_IT_GETS_WRONG.md`:62 | `0.03` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=1].rate` | `p2` | `first` |
| 79 | `WHAT_IT_GETS_WRONG.md`:62 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=1].mc_se` | `f3` | `first` |
| 80 | `WHAT_IT_GETS_WRONG.md`:62 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=2].rate` | `p2` | `first` |
| 81 | `WHAT_IT_GETS_WRONG.md`:62 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=2].mc_se` | `f3` | `first` |
| 82 | `WHAT_IT_GETS_WRONG.md`:62 | `0.06` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=3].rate` | `p2` | `first` |
| 83 | `WHAT_IT_GETS_WRONG.md`:62 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=3].mc_se` | `f3` | `first` |
| 84 | `WHAT_IT_GETS_WRONG.md`:62 | `met` | `derived (docs/11 §12.1)` | `size.outcome` | `text` | `first` |
| 85 | `WHAT_IT_GETS_WRONG.md`:68 | `0.6` | `validation/site_signal/summary.json` | `failure_case.between_site_sd_logit` | `f1` | `first` |
| 86 | `WHAT_IT_GETS_WRONG.md`:68 | `0.2` | `validation/site_signal/summary.json` | `failure_case.casemix_sd_log` | `f1` | `first` |
| 87 | `WHAT_IT_GETS_WRONG.md`:74 | `0.30` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].power` | `p2` | `first` |
| 88 | `WHAT_IT_GETS_WRONG.md`:74 | `0.026` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 89 | `WHAT_IT_GETS_WRONG.md`:74 | `0.04` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.5].power` | `p2` | `first` |
| 90 | `WHAT_IT_GETS_WRONG.md`:74 | `0.011` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 91 | `WHAT_IT_GETS_WRONG.md`:75 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].power` | `p2` | `first` |
| 92 | `WHAT_IT_GETS_WRONG.md`:75 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 93 | `WHAT_IT_GETS_WRONG.md`:75 | `0.36` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].power` | `p2` | `first` |
| 94 | `WHAT_IT_GETS_WRONG.md`:75 | `0.028` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 95 | `WHAT_IT_GETS_WRONG.md`:76 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 96 | `WHAT_IT_GETS_WRONG.md`:76 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.9].power` | `p2` | `first` |
| 97 | `WHAT_IT_GETS_WRONG.md`:76 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 98 | `WHAT_IT_GETS_WRONG.md`:76 | `0.48` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.9].power` | `p2` | `first` |
| 99 | `WHAT_IT_GETS_WRONG.md`:76 | `0.029` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 100 | `WHAT_IT_GETS_WRONG.md`:77 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 101 | `WHAT_IT_GETS_WRONG.md`:77 | `1.00` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].power` | `p2` | `first` |
| 102 | `WHAT_IT_GETS_WRONG.md`:77 | `0.000` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 103 | `WHAT_IT_GETS_WRONG.md`:77 | `0.99` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].power` | `p2` | `first` |
| 104 | `WHAT_IT_GETS_WRONG.md`:77 | `0.005` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 105 | `WHAT_IT_GETS_WRONG.md`:79 | `0.05` | `derived (docs/11 §12.1)` | `req023.look.nominal` | `p2` | `first` |
| 106 | `WHAT_IT_GETS_WRONG.md`:79 | `0.10` | `derived (docs/11 §12.1)` | `req023.watch.nominal` | `p2` | `first` |
| 107 | `WHAT_IT_GETS_WRONG.md`:83 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.rate` | `p2` | `first` |
| 108 | `WHAT_IT_GETS_WRONG.md`:83 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.mc_se` | `f3` | `first` |
| 109 | `WHAT_IT_GETS_WRONG.md`:83 | `0.15` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.rate` | `p2` | `first` |
| 110 | `WHAT_IT_GETS_WRONG.md`:83 | `0.011` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.mc_se` | `f3` | `first` |
| 111 | `WHAT_IT_GETS_WRONG.md`:84 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].look_per_site.rate` | `p2` | `first` |
| 112 | `WHAT_IT_GETS_WRONG.md`:84 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].look_per_site.mc_se` | `f3` | `first` |
| 113 | `WHAT_IT_GETS_WRONG.md`:84 | `0.21` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].watch_fwer.rate` | `p2` | `first` |
| 114 | `WHAT_IT_GETS_WRONG.md`:84 | `0.013` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].watch_fwer.mc_se` | `f3` | `first` |
| 115 | `WHAT_IT_GETS_WRONG.md`:96 | `0.04` | `validation/site_signal/summary.json` | `sensitivity[id=SE9].null.look_per_site.rate` | `p2` | `first` |
| 116 | `WHAT_IT_GETS_WRONG.md`:96 | `0.003` | `validation/site_signal/summary.json` | `sensitivity[id=SE9].null.look_per_site.mc_se` | `f3` | `first` |
| 117 | `WHAT_IT_GETS_WRONG.md`:96 | `0.05` | `validation/site_signal/summary.json` | `sensitivity[id=SE9].null.watch_fwer.rate` | `p2` | `first` |
| 118 | `WHAT_IT_GETS_WRONG.md`:96 | `0.013` | `validation/site_signal/summary.json` | `sensitivity[id=SE9].null.watch_fwer.mc_se` | `f3` | `first` |
| 119 | `WHAT_IT_GETS_WRONG.md`:97 | `0.05` | `validation/site_signal/summary.json` | `sensitivity[id=SE10].null.look_per_site.rate` | `p2` | `first` |
| 120 | `WHAT_IT_GETS_WRONG.md`:97 | `0.002` | `validation/site_signal/summary.json` | `sensitivity[id=SE10].null.look_per_site.mc_se` | `f3` | `first` |
| 121 | `WHAT_IT_GETS_WRONG.md`:97 | `0.14` | `validation/site_signal/summary.json` | `sensitivity[id=SE10].null.watch_fwer.rate` | `p2` | `first` |
| 122 | `WHAT_IT_GETS_WRONG.md`:97 | `0.020` | `validation/site_signal/summary.json` | `sensitivity[id=SE10].null.watch_fwer.mc_se` | `f3` | `first` |
| 123 | `WHAT_IT_GETS_WRONG.md`:98 | `0.06` | `validation/site_signal/summary.json` | `sensitivity[id=SE11].null.look_per_site.rate` | `p2` | `first` |
| 124 | `WHAT_IT_GETS_WRONG.md`:98 | `0.003` | `validation/site_signal/summary.json` | `sensitivity[id=SE11].null.look_per_site.mc_se` | `f3` | `first` |
| 125 | `WHAT_IT_GETS_WRONG.md`:98 | `0.15` | `validation/site_signal/summary.json` | `sensitivity[id=SE11].null.watch_fwer.rate` | `p2` | `first` |
| 126 | `WHAT_IT_GETS_WRONG.md`:98 | `0.021` | `validation/site_signal/summary.json` | `sensitivity[id=SE11].null.watch_fwer.mc_se` | `f3` | `first` |
| 127 | `WHAT_IT_GETS_WRONG.md`:99 | `0.05` | `validation/site_signal/summary.json` | `sensitivity[id=SE12].null.look_per_site.rate` | `p2` | `first` |
| 128 | `WHAT_IT_GETS_WRONG.md`:99 | `0.003` | `validation/site_signal/summary.json` | `sensitivity[id=SE12].null.look_per_site.mc_se` | `f3` | `first` |
| 129 | `WHAT_IT_GETS_WRONG.md`:99 | `0.11` | `validation/site_signal/summary.json` | `sensitivity[id=SE12].null.watch_fwer.rate` | `p2` | `first` |
| 130 | `WHAT_IT_GETS_WRONG.md`:99 | `0.018` | `validation/site_signal/summary.json` | `sensitivity[id=SE12].null.watch_fwer.mc_se` | `f3` | `first` |
| 131 | `WHAT_IT_GETS_WRONG.md`:100 | `0.04` | `validation/site_signal/summary.json` | `sensitivity[id=SE13].null.look_per_site.rate` | `p2` | `first` |
| 132 | `WHAT_IT_GETS_WRONG.md`:100 | `0.003` | `validation/site_signal/summary.json` | `sensitivity[id=SE13].null.look_per_site.mc_se` | `f3` | `first` |
| 133 | `WHAT_IT_GETS_WRONG.md`:100 | `0.09` | `validation/site_signal/summary.json` | `sensitivity[id=SE13].null.watch_fwer.rate` | `p2` | `first` |
| 134 | `WHAT_IT_GETS_WRONG.md`:100 | `0.017` | `validation/site_signal/summary.json` | `sensitivity[id=SE13].null.watch_fwer.mc_se` | `f3` | `first` |
| 135 | `WHAT_IT_GETS_WRONG.md`:106 | `1.5` | `validation/site_signal/summary.json` | `design.mu` | `f1` | `first` |
| 136 | `WHAT_IT_GETS_WRONG.md`:138 | `0.05` | `validation/site_signal/summary.json` | `sensitivity[id=SE14].null.look_per_site.rate` | `p2` | `first` |
| 137 | `WHAT_IT_GETS_WRONG.md`:138 | `0.003` | `validation/site_signal/summary.json` | `sensitivity[id=SE14].null.look_per_site.mc_se` | `f3` | `first` |
| 138 | `WHAT_IT_GETS_WRONG.md`:138 | `0.10` | `validation/site_signal/summary.json` | `sensitivity[id=SE14].null.watch_fwer.rate` | `p2` | `first` |
| 139 | `WHAT_IT_GETS_WRONG.md`:138 | `0.017` | `validation/site_signal/summary.json` | `sensitivity[id=SE14].null.watch_fwer.mc_se` | `f3` | `first` |
| 140 | `WHAT_IT_GETS_WRONG.md`:139 | `0.05` | `validation/site_signal/summary.json` | `sensitivity[id=SE15].null.look_per_site.rate` | `p2` | `first` |
| 141 | `WHAT_IT_GETS_WRONG.md`:139 | `0.002` | `validation/site_signal/summary.json` | `sensitivity[id=SE15].null.look_per_site.mc_se` | `f3` | `first` |
| 142 | `WHAT_IT_GETS_WRONG.md`:139 | `0.09` | `validation/site_signal/summary.json` | `sensitivity[id=SE15].null.watch_fwer.rate` | `p2` | `first` |
| 143 | `WHAT_IT_GETS_WRONG.md`:139 | `0.016` | `validation/site_signal/summary.json` | `sensitivity[id=SE15].null.watch_fwer.mc_se` | `f3` | `first` |
| 144 | `WHAT_IT_GETS_WRONG.md`:145 | `0.00` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=look,label=honest_low_diligence].rate` | `p2` | `first` |
| 145 | `WHAT_IT_GETS_WRONG.md`:145 | `0.001` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=look,label=honest_low_diligence].mc_se` | `f3` | `first` |
| 146 | `WHAT_IT_GETS_WRONG.md`:145 | `0.00` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=watch,label=honest_low_diligence].rate` | `p2` | `first` |
| 147 | `WHAT_IT_GETS_WRONG.md`:145 | `0.000` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=watch,label=honest_low_diligence].mc_se` | `f3` | `first` |
| 148 | `WHAT_IT_GETS_WRONG.md`:145 | `0.00` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=look,label=honest].rate` | `p2` | `first` |
| 149 | `WHAT_IT_GETS_WRONG.md`:145 | `0.000` | `validation/site_signal/summary.json` | `full_mix.false_flags[indicator=discordance,tier=look,label=honest].mc_se` | `f3` | `first` |
| 150 | `WHAT_IT_GETS_WRONG.md`:149 | `0` | `monitoring/out/answer_key.json` | `confusion.discordance.watch.tp` | `int` | `first` |
| 151 | `WHAT_IT_GETS_WRONG.md`:149 | `5` | `monitoring/out/answer_key.json` | `confusion.discordance.watch.fn` | `int` | `first` |
| 152 | `WHAT_IT_GETS_WRONG.md`:149 | `0` | `monitoring/out/answer_key.json` | `confusion.discordance.watch.fp` | `int` | `first` |
| 153 | `WHAT_IT_GETS_WRONG.md`:149 | `2` | `monitoring/out/answer_key.json` | `confusion.discordance.look.tp` | `int` | `first` |
| 154 | `WHAT_IT_GETS_WRONG.md`:149 | `3` | `monitoring/out/answer_key.json` | `confusion.discordance.look.fn` | `int` | `first` |
| 155 | `WHAT_IT_GETS_WRONG.md`:149 | `0` | `monitoring/out/answer_key.json` | `confusion.discordance.look.fp` | `int` | `first` |
| 156 | `WHAT_IT_GETS_WRONG.md`:149 | `2` | `monitoring/out/answer_key.json` | `confusion.rate_kri.watch.tp` | `int` | `first` |
| 157 | `WHAT_IT_GETS_WRONG.md`:149 | `3` | `monitoring/out/answer_key.json` | `confusion.rate_kri.watch.fn` | `int` | `first` |
| 158 | `WHAT_IT_GETS_WRONG.md`:149 | `0` | `monitoring/out/answer_key.json` | `confusion.rate_kri.watch.fp` | `int` | `first` |
| 159 | `WHAT_IT_GETS_WRONG.md`:149 | `0` | `monitoring/out/answer_key.json` | `confusion.simaerep_classic.look.tp` | `int` | `first` |
| 160 | `WHAT_IT_GETS_WRONG.md`:153 | `1.00` | `monitoring/out/equity.json` | `language.mh_or` | `f2` | `first` |
| 161 | `WHAT_IT_GETS_WRONG.md`:153 | `[0.580, 1.846]` | `monitoring/out/equity.json` | `language.ci95` | `ci3` | `first` |
| 162 | `WHAT_IT_GETS_WRONG.md`:153 | `11` | `monitoring/out/equity.json` | `language.n_sites_used` | `int` | `first` |
| 163 | `README.md`:75 | `92794863` | `validation/site_signal/summary.json` | `eval_seed` | `int` | `first` |
| 164 | `README.md`:75 | `68838978bb305e0f730d30e5cbf3c00bceca5a25` | `validation/site_signal/summary.json` | `sap_tag_commit` | `text` | `first` |
| 165 | `README.md`:148 | `0.15` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 166 | `README.md`:148 | `0.021` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 167 | `README.md`:148 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 168 | `README.md`:148 | `0.009` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 169 | `README.md`:149 | `0.51` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 170 | `README.md`:149 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 171 | `README.md`:149 | `0.22` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 172 | `README.md`:149 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 173 | `README.md`:150 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 174 | `README.md`:150 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 175 | `README.md`:150 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 176 | `README.md`:150 | `0.70` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 177 | `README.md`:150 | `0.026` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 178 | `README.md`:154 | `0.09` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].power_diff` | `f2` | `first` |
| 179 | `README.md`:154 | `0.029` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].paired_mc_se` | `f3` | `first` |
| 180 | `README.md`:154 | `0.99` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 181 | `README.md`:154 | `0.005` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 182 | `README.md`:154 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 183 | `README.md`:156 | `2000` | `validation/site_signal/summary.json` | `null.r` | `int` | `first` |
| 184 | `README.md`:158 | `0.05` | `derived (docs/11 §12.1)` | `req023.look.nominal` | `p2` | `first` |
| 185 | `README.md`:158 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site.rate` | `p2` | `first` |
| 186 | `README.md`:158 | `0.001` | `validation/site_signal/summary.json` | `null.look_per_site.mc_se` | `f3` | `first` |
| 187 | `README.md`:158 | `met (conservative: below the nominal rate)` | `derived (docs/11 §12.1)` | `req023.look.outcome` | `text` | `first` |
| 188 | `README.md`:159 | `0.10` | `derived (docs/11 §12.1)` | `req023.watch.nominal` | `p2` | `first` |
| 189 | `README.md`:159 | `0.11` | `validation/site_signal/summary.json` | `null.watch_fwer.rate` | `p2` | `first` |
| 190 | `README.md`:159 | `[0.095, 0.122]` | `validation/site_signal/summary.json` | `null.watch_fwer.ci95` | `ci3` | `first` |
| 191 | `README.md`:159 | `0.007` | `validation/site_signal/summary.json` | `null.watch_fwer.mc_se` | `f3` | `first` |
| 192 | `README.md`:159 | `met` | `derived (docs/11 §12.1)` | `req023.watch.outcome` | `text` | `first` |
| 193 | `README.md`:163 | `0.30` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].power` | `p2` | `first` |
| 194 | `README.md`:163 | `0.026` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 195 | `README.md`:163 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].power` | `p2` | `first` |
| 196 | `README.md`:163 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 197 | `README.md`:164 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.rate` | `p2` | `first` |
| 198 | `README.md`:164 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.mc_se` | `f3` | `first` |
| 199 | `README.md`:164 | `0.15` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.rate` | `p2` | `first` |
| 200 | `README.md`:164 | `0.011` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.mc_se` | `f3` | `first` |
| 201 | `deck.html`:261 | `14` | `monitoring/out/signal_run.json` | `run.n_computed_sites` | `int` | `first` |
| 202 | `deck.html`:261 | `0.8` | `monitoring/out/thresholds.json` | `expected_false_look_flags_per_study` | `f1` | `first` |
| 203 | `deck.html`:298 | `0.15` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 204 | `deck.html`:298 | `0.021` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 205 | `deck.html`:298 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 206 | `deck.html`:298 | `0.009` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 207 | `deck.html`:299 | `0.51` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 208 | `deck.html`:299 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 209 | `deck.html`:299 | `0.22` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 210 | `deck.html`:299 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 211 | `deck.html`:300 | `90%` | `validation/site_signal/summary.json` | `design.gross_f` | `pct2` | `first` |
| 212 | `deck.html`:300 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 213 | `deck.html`:300 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 214 | `deck.html`:300 | `0.70` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 215 | `deck.html`:300 | `0.026` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 216 | `deck.html`:301 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site.rate` | `p2` | `first` |
| 217 | `deck.html`:301 | `0.001` | `validation/site_signal/summary.json` | `null.look_per_site.mc_se` | `f3` | `first` |
| 218 | `deck.html`:301 | `0.05` | `derived (docs/11 §12.1)` | `req023.look.nominal` | `p2` | `first` |
| 219 | `deck.html`:302 | `0.11` | `validation/site_signal/summary.json` | `null.watch_fwer.rate` | `p2` | `first` |
| 220 | `deck.html`:302 | `0.007` | `validation/site_signal/summary.json` | `null.watch_fwer.mc_se` | `f3` | `first` |
| 221 | `deck.html`:302 | `0.10` | `derived (docs/11 §12.1)` | `req023.watch.nominal` | `p2` | `first` |
| 222 | `deck.html`:305 | `0.99` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 223 | `deck.html`:305 | `0.005` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 224 | `deck.html`:305 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 225 | `deck.html`:305 | `0.30` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].power` | `p2` | `first` |
| 226 | `deck.html`:305 | `0.026` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 227 | `deck.html`:305 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].power` | `p2` | `first` |
| 228 | `deck.html`:305 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 229 | `08-demo-and-pitch.md`:37 | `70%` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].power` | `pct2` | `first` |
| 230 | `08-demo-and-pitch.md`:37 | `22%` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].power` | `pct2` | `first` |
| 231 | `08-demo-and-pitch.md`:37 | `3%` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].power` | `pct2` | `first` |
| 232 | `10-site-signal.md`:306 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site.rate` | `p2` | `first` |
| 233 | `10-site-signal.md`:306 | `0.001` | `validation/site_signal/summary.json` | `null.look_per_site.mc_se` | `f3` | `first` |
| 234 | `10-site-signal.md`:306 | `0.053` | `derived (docs/11 §12.1)` | `req023.look.bound` | `f3` | `first` |
| 235 | `10-site-signal.md`:306 | `met (conservative: below the nominal rate)` | `derived (docs/11 §12.1)` | `req023.look.outcome` | `text` | `first` |
| 236 | `10-site-signal.md`:306 | `0.03` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=1].rate` | `p2` | `first` |
| 237 | `10-site-signal.md`:306 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=1].mc_se` | `f3` | `first` |
| 238 | `10-site-signal.md`:306 | `0.05` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=2].rate` | `p2` | `first` |
| 239 | `10-site-signal.md`:306 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=2].mc_se` | `f3` | `first` |
| 240 | `10-site-signal.md`:306 | `0.06` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=3].rate` | `p2` | `first` |
| 241 | `10-site-signal.md`:306 | `0.002` | `validation/site_signal/summary.json` | `null.look_per_site_by_e_tertile[tertile=3].mc_se` | `f3` | `first` |
| 242 | `10-site-signal.md`:306 | `met` | `derived (docs/11 §12.1)` | `size.outcome` | `text` | `first` |
| 243 | `10-site-signal.md`:307 | `0.11` | `validation/site_signal/summary.json` | `null.watch_fwer.rate` | `p2` | `first` |
| 244 | `10-site-signal.md`:307 | `0.007` | `validation/site_signal/summary.json` | `null.watch_fwer.mc_se` | `f3` | `first` |
| 245 | `10-site-signal.md`:307 | `[0.095, 0.122]` | `validation/site_signal/summary.json` | `null.watch_fwer.ci95` | `ci3` | `first` |
| 246 | `10-site-signal.md`:307 | `0.119` | `derived (docs/11 §12.1)` | `req023.watch.bound` | `f3` | `first` |
| 247 | `10-site-signal.md`:307 | `met` | `derived (docs/11 §12.1)` | `req023.watch.outcome` | `text` | `first` |
| 248 | `10-site-signal.md`:308 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 249 | `10-site-signal.md`:308 | `0.70` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 250 | `10-site-signal.md`:308 | `0.026` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 251 | `10-site-signal.md`:308 | `0.22` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 252 | `10-site-signal.md`:308 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 253 | `10-site-signal.md`:308 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 254 | `10-site-signal.md`:308 | `0.009` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 255 | `10-site-signal.md`:309 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 256 | `10-site-signal.md`:309 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 257 | `10-site-signal.md`:309 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 258 | `10-site-signal.md`:309 | `0.51` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 259 | `10-site-signal.md`:309 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 260 | `10-site-signal.md`:309 | `0.15` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 261 | `10-site-signal.md`:309 | `0.021` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 262 | `10-site-signal.md`:309 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,design_row=true,f=0.9].p_computed` | `p2` | `first` |
| 263 | `10-site-signal.md`:310 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 264 | `10-site-signal.md`:310 | `0.99` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 265 | `10-site-signal.md`:310 | `0.005` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 266 | `10-site-signal.md`:310 | `0.50` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 267 | `10-site-signal.md`:310 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 268 | `10-site-signal.md`:310 | `0.19` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 269 | `10-site-signal.md`:310 | `0.023` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 270 | `10-site-signal.md`:310 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 271 | `10-site-signal.md`:310 | `0.78` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 272 | `10-site-signal.md`:310 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 273 | `10-site-signal.md`:310 | `0.13` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 274 | `10-site-signal.md`:310 | `0.019` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 275 | `10-site-signal.md`:310 | `0.02` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 276 | `10-site-signal.md`:310 | `0.007` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 277 | `10-site-signal.md`:311 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 278 | `10-site-signal.md`:311 | `-0.22` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.9].power_diff` | `f2` | `first` |
| 279 | `10-site-signal.md`:311 | `0.025` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.9].paired_mc_se` | `f3` | `first` |
| 280 | `10-site-signal.md`:311 | `0.01` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.5].power_diff` | `f2` | `first` |
| 281 | `10-site-signal.md`:311 | `0.043` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.5].paired_mc_se` | `f3` | `first` |
| 282 | `10-site-signal.md`:311 | `-0.04` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.25].power_diff` | `f2` | `first` |
| 283 | `10-site-signal.md`:311 | `0.031` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=look,design_row=true,f=0.25].paired_mc_se` | `f3` | `first` |
| 284 | `10-site-signal.md`:311 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 285 | `10-site-signal.md`:311 | `-0.08` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.9].power_diff` | `f2` | `first` |
| 286 | `10-site-signal.md`:311 | `0.033` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.9].paired_mc_se` | `f3` | `first` |
| 287 | `10-site-signal.md`:311 | `0.09` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].power_diff` | `f2` | `first` |
| 288 | `10-site-signal.md`:311 | `0.029` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.5].paired_mc_se` | `f3` | `first` |
| 289 | `10-site-signal.md`:311 | `0.01` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.25].power_diff` | `f2` | `first` |
| 290 | `10-site-signal.md`:311 | `0.012` | `validation/site_signal/summary.json` | `head_to_head.grid[comparator=rate_kri,tier=watch,design_row=true,f=0.25].paired_mc_se` | `f3` | `first` |
| 291 | `10-site-signal.md`:312 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 292 | `10-site-signal.md`:312 | `0.12` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 293 | `10-site-signal.md`:312 | `0.019` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 294 | `10-site-signal.md`:312 | `0.14` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 295 | `10-site-signal.md`:312 | `0.020` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 296 | `10-site-signal.md`:312 | `0.07` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 297 | `10-site-signal.md`:312 | `0.014` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 298 | `10-site-signal.md`:312 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 299 | `10-site-signal.md`:312 | `0.03` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 300 | `10-site-signal.md`:312 | `0.010` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 301 | `10-site-signal.md`:312 | `0.04` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 302 | `10-site-signal.md`:312 | `0.012` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 303 | `10-site-signal.md`:312 | `0.02` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 304 | `10-site-signal.md`:312 | `0.008` | `validation/site_signal/summary.json` | `power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 305 | `10-site-signal.md`:313 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 306 | `10-site-signal.md`:313 | `0.77` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.9].power` | `p2` | `first` |
| 307 | `10-site-signal.md`:313 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 308 | `10-site-signal.md`:313 | `0.53` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.5].power` | `p2` | `first` |
| 309 | `10-site-signal.md`:313 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 310 | `10-site-signal.md`:313 | `0.17` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.25].power` | `p2` | `first` |
| 311 | `10-site-signal.md`:313 | `0.022` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=look,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 312 | `10-site-signal.md`:313 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 313 | `10-site-signal.md`:313 | `0.69` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.9].power` | `p2` | `first` |
| 314 | `10-site-signal.md`:313 | `0.027` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.9].mc_se` | `f3` | `first` |
| 315 | `10-site-signal.md`:313 | `0.21` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.5].power` | `p2` | `first` |
| 316 | `10-site-signal.md`:313 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.5].mc_se` | `f3` | `first` |
| 317 | `10-site-signal.md`:313 | `0.02` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.25].power` | `p2` | `first` |
| 318 | `10-site-signal.md`:313 | `0.009` | `validation/site_signal/summary.json` | `power[indicator=ae_report_ratio,tier=watch,design_row=true,f=0.25].mc_se` | `f3` | `first` |
| 319 | `10-site-signal.md`:314 | `20` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].n_sites` | `int` | `first` |
| 320 | `10-site-signal.md`:314 | `60` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].patients_per_site` | `int` | `first` |
| 321 | `10-site-signal.md`:314 | `0.00` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].p_computed` | `p2` | `first` |
| 322 | `10-site-signal.md`:314 | `0.00` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].power` | `p2` | `first` |
| 323 | `10-site-signal.md`:314 | `0.000` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].mc_se` | `f3` | `first` |
| 324 | `10-site-signal.md`:314 | `0.46` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].power` | `p2` | `first` |
| 325 | `10-site-signal.md`:314 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=look,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].mc_se` | `f3` | `first` |
| 326 | `10-site-signal.md`:314 | `0.13` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].power` | `p2` | `first` |
| 327 | `10-site-signal.md`:314 | `0.019` | `validation/site_signal/summary.json` | `power[indicator=rate_kri,tier=watch,n_sites=20,patients_per_site=60,mu=0.5,f=0.5].mc_se` | `f3` | `first` |
| 328 | `10-site-signal.md`:314 | `0.55` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=1.5,f=0.5].power` | `p2` | `first` |
| 329 | `10-site-signal.md`:314 | `0.029` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=look,n_sites=20,patients_per_site=60,mu=1.5,f=0.5].mc_se` | `f3` | `first` |
| 330 | `10-site-signal.md`:314 | `0.23` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,n_sites=20,patients_per_site=60,mu=1.5,f=0.5].power` | `p2` | `first` |
| 331 | `10-site-signal.md`:314 | `0.024` | `validation/site_signal/summary.json` | `power[indicator=discordance,tier=watch,n_sites=20,patients_per_site=60,mu=1.5,f=0.5].mc_se` | `f3` | `first` |
| 332 | `10-site-signal.md`:315 | `0.30` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].power` | `p2` | `first` |
| 333 | `10-site-signal.md`:315 | `0.026` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 334 | `10-site-signal.md`:315 | `0.04` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.5].power` | `p2` | `first` |
| 335 | `10-site-signal.md`:315 | `0.011` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 336 | `10-site-signal.md`:315 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].power` | `p2` | `first` |
| 337 | `10-site-signal.md`:315 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 338 | `10-site-signal.md`:315 | `0.36` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].power` | `p2` | `first` |
| 339 | `10-site-signal.md`:315 | `0.028` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 340 | `10-site-signal.md`:315 | `0.81` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=look,f=0.5].power` | `p2` | `first` |
| 341 | `10-site-signal.md`:315 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 342 | `10-site-signal.md`:315 | `0.02` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=watch,f=0.5].power` | `p2` | `first` |
| 343 | `10-site-signal.md`:315 | `0.008` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 344 | `10-site-signal.md`:315 | `0.38` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=look,f=0.5].power` | `p2` | `first` |
| 345 | `10-site-signal.md`:315 | `0.028` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=look,f=0.5].mc_se` | `f3` | `first` |
| 346 | `10-site-signal.md`:315 | `0.06` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=watch,f=0.5].power` | `p2` | `first` |
| 347 | `10-site-signal.md`:315 | `0.014` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=watch,f=0.5].mc_se` | `f3` | `first` |
| 348 | `10-site-signal.md`:315 | `0.90` | `validation/site_signal/summary.json` | `design.gross_f` | `p2` | `first` |
| 349 | `10-site-signal.md`:315 | `0.82` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.9].power` | `p2` | `first` |
| 350 | `10-site-signal.md`:315 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 351 | `10-site-signal.md`:315 | `0.48` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.9].power` | `p2` | `first` |
| 352 | `10-site-signal.md`:315 | `0.029` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=discordance,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 353 | `10-site-signal.md`:315 | `1.00` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].power` | `p2` | `first` |
| 354 | `10-site-signal.md`:315 | `0.000` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 355 | `10-site-signal.md`:315 | `0.99` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].power` | `p2` | `first` |
| 356 | `10-site-signal.md`:315 | `0.005` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 357 | `10-site-signal.md`:315 | `1.00` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=look,f=0.9].power` | `p2` | `first` |
| 358 | `10-site-signal.md`:315 | `0.000` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 359 | `10-site-signal.md`:315 | `0.03` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=watch,f=0.9].power` | `p2` | `first` |
| 360 | `10-site-signal.md`:315 | `0.010` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=simaerep_classic,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 361 | `10-site-signal.md`:315 | `0.81` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=look,f=0.9].power` | `p2` | `first` |
| 362 | `10-site-signal.md`:315 | `0.022` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=look,f=0.9].mc_se` | `f3` | `first` |
| 363 | `10-site-signal.md`:315 | `0.55` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=watch,f=0.9].power` | `p2` | `first` |
| 364 | `10-site-signal.md`:315 | `0.029` | `validation/site_signal/summary.json` | `failure_case.a.power[indicator=ae_report_ratio,tier=watch,f=0.9].mc_se` | `f3` | `first` |
| 365 | `10-site-signal.md`:315 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.rate` | `p2` | `first` |
| 366 | `10-site-signal.md`:315 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].look_per_site.mc_se` | `f3` | `first` |
| 367 | `10-site-signal.md`:315 | `0.15` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.rate` | `p2` | `first` |
| 368 | `10-site-signal.md`:315 | `0.011` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=discordance].watch_fwer.mc_se` | `f3` | `first` |
| 369 | `10-site-signal.md`:315 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].look_per_site.rate` | `p2` | `first` |
| 370 | `10-site-signal.md`:315 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].look_per_site.mc_se` | `f3` | `first` |
| 371 | `10-site-signal.md`:315 | `0.21` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].watch_fwer.rate` | `p2` | `first` |
| 372 | `10-site-signal.md`:315 | `0.013` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=rate_kri].watch_fwer.mc_se` | `f3` | `first` |
| 373 | `10-site-signal.md`:315 | `0.00` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=simaerep_classic].look_per_site.rate` | `p2` | `first` |
| 374 | `10-site-signal.md`:315 | `0.000` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=simaerep_classic].look_per_site.mc_se` | `f3` | `first` |
| 375 | `10-site-signal.md`:315 | `0.00` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=simaerep_classic].watch_fwer.rate` | `p2` | `first` |
| 376 | `10-site-signal.md`:315 | `0.000` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=simaerep_classic].watch_fwer.mc_se` | `f3` | `first` |
| 377 | `10-site-signal.md`:315 | `0.06` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=ae_report_ratio].look_per_site.rate` | `p2` | `first` |
| 378 | `10-site-signal.md`:315 | `0.001` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=ae_report_ratio].look_per_site.mc_se` | `f3` | `first` |
| 379 | `10-site-signal.md`:315 | `0.16` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=ae_report_ratio].watch_fwer.rate` | `p2` | `first` |
| 380 | `10-site-signal.md`:315 | `0.011` | `validation/site_signal/summary.json` | `failure_case.b.null[indicator=ae_report_ratio].watch_fwer.mc_se` | `f3` | `first` |
| 381 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.watch.tp` | `int` | `first` |
| 382 | `10-site-signal.md`:316 | `5` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.watch.fn` | `int` | `first` |
| 383 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.watch.fp` | `int` | `first` |
| 384 | `10-site-signal.md`:316 | `2` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.look.tp` | `int` | `first` |
| 385 | `10-site-signal.md`:316 | `3` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.look.fn` | `int` | `first` |
| 386 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.discordance.look.fp` | `int` | `first` |
| 387 | `10-site-signal.md`:316 | `2` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.watch.tp` | `int` | `first` |
| 388 | `10-site-signal.md`:316 | `3` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.watch.fn` | `int` | `first` |
| 389 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.watch.fp` | `int` | `first` |
| 390 | `10-site-signal.md`:316 | `2` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.look.tp` | `int` | `first` |
| 391 | `10-site-signal.md`:316 | `3` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.look.fn` | `int` | `first` |
| 392 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.rate_kri.look.fp` | `int` | `first` |
| 393 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.watch.tp` | `int` | `first` |
| 394 | `10-site-signal.md`:316 | `5` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.watch.fn` | `int` | `first` |
| 395 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.watch.fp` | `int` | `first` |
| 396 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.look.tp` | `int` | `first` |
| 397 | `10-site-signal.md`:316 | `5` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.look.fn` | `int` | `first` |
| 398 | `10-site-signal.md`:316 | `0` | `validation/site_signal/summary.json` | `eval_study.confusion.simaerep_classic.look.fp` | `int` | `first` |
| 399 | `10-site-signal.md`:317 | `0.000` | `validation/site_signal/summary.json` | `simaerep_fixture.max_rel_diff` | `f3` | `first` |
| 400 | `10-site-signal.md`:317 | `10` | `validation/site_signal/summary.json` | `simaerep_fixture.rows` | `int` | `first` |
<!-- ss-provenance:end -->
