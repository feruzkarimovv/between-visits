# What it gets wrong

This page lists the limits of Between Visits and of Site Signal, its sponsor-side layer, with the numbers that show them. It is the reader-facing version of `docs/10-site-signal.md` §10 and `docs/11-site-signal-sap.md` §16.

- **Site Signal numbers are SIMULATED.** Every one is read from `validation/site_signal/summary.json` (operating characteristics, `docs/11` §12) or `monitoring/out/*.json` (the committed evaluation study). None is typed by hand. They are rounded only for display (`docs/11` §15 rule 6): proportions to 2 decimals, Monte Carlo standard errors (MC SE) and interval limits to 3.
- **Evaluation numbers come from `eval/results/latest.json`.** That is the text-mode evaluation with 20 simulated patients. Each number names its key in that file.
- **No real voice-call (MEASURED) numbers yet.** `eval/results/voice_checks.json` holds only pending rows until the real calls are made (task V10, a human step), so this page quotes none.
- **How each number was checked** is at the end of this page.

Site Signal measures **capture discordance**. It compares the episodes a site's own patients reported on their between-visit calls with the site's AE log, relative to the other sites, and flags sites at two tiers. **Look** is a per-site 5% tier. **Watch** is a study-wide tier: at most a 10% chance of any false Watch flag per study under the pre-registered null. A flag is a reason to look, not a finding. A site with no flag reads "No signal at this sample size", never anything stronger.

## 1. Moderate capture gaps are mostly invisible at the Watch tier

The `sap-v1` design has {{ss:summary:design.n_sites:int}} sites, {{ss:summary:design.patients_per_site[0]:int}} to {{ss:summary:design.patients_per_site[1]:int}} patients per site, and an assumed {{ss:summary:design.mu:f1}} grade ≥ 2 episodes per patient. One planted site loses a share *f* of its episodes from the AE log. The table gives how often the discordance indicator flags it, with the thresholds frozen in `monitoring/out/thresholds.json`.

| Planted capture loss *f* (SIMULATED) | Flagged at Look or Watch | Flagged at Watch |
|---|---|---|
| 0.25 | {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.25].power // power[indicator=discordance,tier=look,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.25].mc_se // power[indicator=discordance,tier=look,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) | {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.25].power // power[indicator=discordance,tier=watch,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.25].mc_se // power[indicator=discordance,tier=watch,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) |
| 0.50 | {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.5].power // power[indicator=discordance,tier=look,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.5].mc_se // power[indicator=discordance,tier=look,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) | {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.5].power // power[indicator=discordance,tier=watch,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.5].mc_se // power[indicator=discordance,tier=watch,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) |
| {{ss:summary:design.gross_f:p2}} (gross loss) | {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.9].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=look,design_row=true,f=0.9].mc_se:f3}}) | {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.9].power:p2}} (MC SE {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.9].mc_se:f3}}) |

The pre-tag planning grid used a simplified model. Its value for the gross row at Watch was {{ss:summary:power[indicator=discordance,tier=watch,design_row=true,f=0.9].planning_power:p2}} (planning, simplified); the final value is the one in the table.

The Look tier catches more, at a price. Under the pre-registered null, a study with no problems is expected to show about {{ss:summary:null.look_per_study.rate:f2}} false Look flags (MC SE {{ss:summary:null.look_per_study.mc_se:f3}}). The calibration estimate of the same quantity, shown in the `/sites` footer, is {{ss:thresholds:expected_false_look_flags_per_study:f1}} (`thresholds.json`).

This heading was written before any result existed (`docs/10` §10.2). If the Watch column does not show most 25% and 50% gaps going unflagged, the heading is corrected, not the numbers.

The comparators flag the same planted site as follows (SIMULATED, same design and replicates):

| Indicator | *f* | Look or Watch | Watch |
|---|---|---|---|
| gsm-style AE-rate KRI | 0.25 | {{ss:summary:power[indicator=rate_kri,tier=look,design_row=true,f=0.25].power // power[indicator=rate_kri,tier=look,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=rate_kri,tier=look,design_row=true,f=0.25].mc_se // power[indicator=rate_kri,tier=look,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) | {{ss:summary:power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].power // power[indicator=rate_kri,tier=watch,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=rate_kri,tier=watch,design_row=true,f=0.25].mc_se // power[indicator=rate_kri,tier=watch,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) |
| gsm-style AE-rate KRI | 0.50 | {{ss:summary:power[indicator=rate_kri,tier=look,design_row=true,f=0.5].power // power[indicator=rate_kri,tier=look,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=rate_kri,tier=look,design_row=true,f=0.5].mc_se // power[indicator=rate_kri,tier=look,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) | {{ss:summary:power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].power // power[indicator=rate_kri,tier=watch,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=rate_kri,tier=watch,design_row=true,f=0.5].mc_se // power[indicator=rate_kri,tier=watch,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) |
| simaerep classic (legacy) | 0.25 | {{ss:summary:power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].power // power[indicator=simaerep_classic,tier=look,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=simaerep_classic,tier=look,design_row=true,f=0.25].mc_se // power[indicator=simaerep_classic,tier=look,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) | {{ss:summary:power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].power // power[indicator=simaerep_classic,tier=watch,n_sites=20,mu=1.5,f=0.25].power:p2}} (MC SE {{ss:summary:power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.25].mc_se // power[indicator=simaerep_classic,tier=watch,n_sites=20,mu=1.5,f=0.25].mc_se:f3}}) |
| simaerep classic (legacy) | 0.50 | {{ss:summary:power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].power // power[indicator=simaerep_classic,tier=look,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=simaerep_classic,tier=look,design_row=true,f=0.5].mc_se // power[indicator=simaerep_classic,tier=look,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) | {{ss:summary:power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].power // power[indicator=simaerep_classic,tier=watch,n_sites=20,mu=1.5,f=0.5].power:p2}} (MC SE {{ss:summary:power[indicator=simaerep_classic,tier=watch,design_row=true,f=0.5].mc_se // power[indicator=simaerep_classic,tier=watch,n_sites=20,mu=1.5,f=0.5].mc_se:f3}}) |

The power for a lower episode rate (*μ* = 0.5, closer to monotherapy) is in the `summary.json` `power[]` rows with `mu` 0.5 and on the **How well it works** tab. It is expected to be lower, because each site has fewer episodes (§6).

## 2. False flags under the null (REQ-023)

These come from {{ss:summary:null.r:int}} fresh null studies at the `sap-v1` design, with no planted site and the frozen thresholds (SIMULATED). REQ-023 passes when each rate is at most its nominal rate + 2·√(SE_cal² + SE_val²). SE_val is the MC SE below; SE_cal is the MC SE of the threshold's achieved in-sample rate in `thresholds.json`. Unrounded values are compared (`docs/11` §12.1).

| Rate (discordance) | Value | MC SE | Nominal | REQ-023 bound | Outcome |
|---|---|---|---|---|---|
| False Look per site | {{ss:summary:null.look_per_site.rate:p2}} | {{ss:summary:null.look_per_site.mc_se:f3}} | {{ss:derived:req023.look.nominal:p2}} | {{ss:derived:req023.look.bound:f3}} | {{ss:derived:req023.look.outcome:text}} |
| Any false Watch per study | {{ss:summary:null.watch_fwer.rate:p2}} (Clopper-Pearson 95% CI {{ss:summary:null.watch_fwer.ci95:ci3}}) | {{ss:summary:null.watch_fwer.mc_se:f3}} | {{ss:derived:req023.watch.nominal:p2}} | {{ss:derived:req023.watch.bound:f3}} | {{ss:derived:req023.watch.outcome:text}} |

A rate below nominal is conservative, not a failure. **Size calibration** checks the false Look rate by expected site size (tertiles of *E*). Each tertile must be within the nominal rate ± {{ss:derived:size.tolerance:p2}} (SIMULATED):

| Tertile 1 (smallest sites) | Tertile 2 | Tertile 3 (largest sites) | Check |
|---|---|---|---|
| {{ss:summary:null.look_per_site_by_e_tertile[tertile=1].rate:p2}} (MC SE {{ss:summary:null.look_per_site_by_e_tertile[tertile=1].mc_se:f3}}) | {{ss:summary:null.look_per_site_by_e_tertile[tertile=2].rate:p2}} (MC SE {{ss:summary:null.look_per_site_by_e_tertile[tertile=2].mc_se:f3}}) | {{ss:summary:null.look_per_site_by_e_tertile[tertile=3].rate:p2}} (MC SE {{ss:summary:null.look_per_site_by_e_tertile[tertile=3].mc_se:f3}}) | {{ss:derived:size.outcome:text}} |

A failed check is reported here and in `validation/site_signal/report.md`, never hidden.

## 3. The advantage over a plain AE-rate KRI depends on assumptions (the failure case)

Discordance beats a plain AE-rate KRI only if honest sites differ mostly in case mix (how sick their patients are) and not in how thoroughly they record AEs. The failure case reverses that assumption: between-site capture SD {{ss:summary:failure_case.between_site_sd_logit:f1}} (logit scale) and case-mix SD {{ss:summary:failure_case.casemix_sd_log:f1}} (SIMULATED).

**(a) Thresholds re-calibrated under the failure-case null.** Does the advantage disappear even with a correct null?

| Indicator | *f* | Look or Watch | Watch |
|---|---|---|---|
| Discordance | 0.50 | {{ss:summary:failure_case.a.power[indicator=discordance,tier=look,f=0.5].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=discordance,tier=look,f=0.5].mc_se:f3}}) | {{ss:summary:failure_case.a.power[indicator=discordance,tier=watch,f=0.5].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=discordance,tier=watch,f=0.5].mc_se:f3}}) |
| AE-rate KRI | 0.50 | {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=look,f=0.5].mc_se:f3}}) | {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=watch,f=0.5].mc_se:f3}}) |
| Discordance | {{ss:summary:design.gross_f:p2}} | {{ss:summary:failure_case.a.power[indicator=discordance,tier=look,f=0.9].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=discordance,tier=look,f=0.9].mc_se:f3}}) | {{ss:summary:failure_case.a.power[indicator=discordance,tier=watch,f=0.9].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=discordance,tier=watch,f=0.9].mc_se:f3}}) |
| AE-rate KRI | {{ss:summary:design.gross_f:p2}} | {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=look,f=0.9].mc_se:f3}}) | {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].power:p2}} (MC SE {{ss:summary:failure_case.a.power[indicator=rate_kri,tier=watch,f=0.9].mc_se:f3}}) |

**(b) The frozen `sap-v1` thresholds kept, null data from the failure case.** This shows the cost of a wrong null:

| Indicator | False Look per site | Any false Watch per study |
|---|---|---|
| Discordance | {{ss:summary:failure_case.b.null[indicator=discordance].look_per_site.rate:p2}} (MC SE {{ss:summary:failure_case.b.null[indicator=discordance].look_per_site.mc_se:f3}}) | {{ss:summary:failure_case.b.null[indicator=discordance].watch_fwer.rate:p2}} (MC SE {{ss:summary:failure_case.b.null[indicator=discordance].watch_fwer.mc_se:f3}}) |
| AE-rate KRI | {{ss:summary:failure_case.b.null[indicator=rate_kri].look_per_site.rate:p2}} (MC SE {{ss:summary:failure_case.b.null[indicator=rate_kri].look_per_site.mc_se:f3}}) | {{ss:summary:failure_case.b.null[indicator=rate_kri].watch_fwer.rate:p2}} (MC SE {{ss:summary:failure_case.b.null[indicator=rate_kri].watch_fwer.mc_se:f3}}) |

## 4. Both streams are simulated

The 20-site study, its patients, their calls, the patient-reported episodes and every site's AE log are generated by `monitoring/bvsignal/simulate.py`. Thresholds, power and the answer key all come from the same model family. The planted-site results show the method and its power under stated assumptions, not real-world validity. Calls at the demo site 101 (live or replayed) are labeled MEASURED and are never pooled with the simulated episodes.

## 5. The thresholds come from an assumed null

The Look and Watch thresholds were calibrated once, at the `sap-v1` design, from a parametric null with assumed design parameters (`monitoring/params.yaml`): patient frailty, a patient-level capture effect with SD 0.5, a between-site capture SD of 0.35 (logit scale) and a case-mix SD of 0.35. They are not fitted to each study. When real sites differ more than assumed, the false-flag rate is higher than stated. These misspecified-null rows keep the frozen thresholds and change the data (SIMULATED):

| Scenario | Data generated with | False Look per site | Any false Watch per study |
|---|---|---|---|
| SE9 | between-site capture SD 0.2 | {{ss:summary:sensitivity[id=SE9].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE9].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE9].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE9].null.watch_fwer.mc_se:f3}}) |
| SE10 | between-site capture SD 0.5 | {{ss:summary:sensitivity[id=SE10].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE10].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE10].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE10].null.watch_fwer.mc_se:f3}}) |
| SE11 | between-site capture SD 0.6 | {{ss:summary:sensitivity[id=SE11].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE11].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE11].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE11].null.watch_fwer.mc_se:f3}}) |
| SE12 | patient random-effect SD 0.0 | {{ss:summary:sensitivity[id=SE12].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE12].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE12].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE12].null.watch_fwer.mc_se:f3}}) |
| SE13 | patient random-effect SD 1.0 | {{ss:summary:sensitivity[id=SE13].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE13].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE13].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE13].null.watch_fwer.mc_se:f3}}) |

A data-fitted null is not built (`NOT_BUILT.md`, BL-13).

## 6. The episode rate is an assumption

The design assumes {{ss:summary:design.mu:f1}} grade ≥ 2 episodes per patient per 36-week window. That figure represents a combination regimen and is an ASSUMPTION; clinician-reported incidence with an anti-PD-1 antibody alone is lower (UNVERIFIED). At lower rates each site has fewer episodes, more sites fall below the minimum data, and power drops (`power[]` rows with `mu` 0.5).

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
| SE14: episode paged if any page for the subject falls within 7 days | {{ss:summary:sensitivity[id=SE14].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE14].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE14].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE14].null.watch_fwer.mc_se:f3}}) |
| SE15: higher capture near urgent calls at the 5 most-paged sites | {{ss:summary:sensitivity[id=SE15].null.look_per_site.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE15].null.look_per_site.mc_se:f3}}) | {{ss:summary:sensitivity[id=SE15].null.watch_fwer.rate:p2}} (MC SE {{ss:summary:sensitivity[id=SE15].null.watch_fwer.mc_se:f3}}) |

When Between Visits drafts reach a site's staff (integrated mode), the two streams are no longer independent. Such a site is "Not computed" with that reason; an indicator for integrated mode is not built (BL-14).

## 13. Discordance includes legitimate clinical judgment

An unmatched episode is not an error. The site may have recorded it as medical history, judged it not to be an AE, or graded it differently. The site query asks the site to review its source documents and either enter the event or say why no entry is needed. "Recorded as medical history" and "not an AE per investigator" are normal answers. Every simulated study plants an honest site with low recording diligence. In the full planted mix (SIMULATED), discordance flags it at Look in {{ss:summary:full_mix.false_flags[indicator=discordance,tier=look,label=honest_low_diligence].rate:p2}} of studies (MC SE {{ss:summary:full_mix.false_flags[indicator=discordance,tier=look,label=honest_low_diligence].mc_se:f3}}) and at Watch in {{ss:summary:full_mix.false_flags[indicator=discordance,tier=watch,label=honest_low_diligence].rate:p2}} (MC SE {{ss:summary:full_mix.false_flags[indicator=discordance,tier=watch,label=honest_low_diligence].mc_se:f3}}). A plain honest site is flagged at Look in {{ss:summary:full_mix.false_flags[indicator=discordance,tier=look,label=honest].rate:p2}} (MC SE {{ss:summary:full_mix.false_flags[indicator=discordance,tier=look,label=honest].mc_se:f3}}). A flag is a reason to look, not a finding about the site.

## 14. The committed study is an illustration, not evidence

The study on the `/sites` page is one draw (`monitoring/out/`, SIMULATED). Five planted sites, two must-be-grey sites and the rest honest. At Watch, discordance caught {{ss:answer_key:confusion.discordance.watch.tp:int}} planted sites, missed {{ss:answer_key:confusion.discordance.watch.fn:int}} and flagged {{ss:answer_key:confusion.discordance.watch.fp:int}} honest sites. At Look or Watch it caught {{ss:answer_key:confusion.discordance.look.tp:int}}, missed {{ss:answer_key:confusion.discordance.look.fn:int}} and flagged {{ss:answer_key:confusion.discordance.look.fp:int}} honest sites. With five positives these counts carry little information; sections 1 to 3 are the evidence.

## 15. Language gaps within a site: low power, no UI panel

Within sites, the Mantel-Haenszel odds ratio of capture for Spanish-speaking versus English-speaking patients in the committed study is {{ss:equity:language.mh_or:f2}} (patient-cluster bootstrap 95% CI {{ss:equity:language.ci95:ci3}}, {{ss:equity:language.n_sites_used:int}} sites with enough episodes in both groups; SIMULATED). Below 1 means lower capture for Spanish-speaking patients. Power is low, and a gap planted at one site is diluted in the pooled estimate. The Equity panel in the UI was cut this round (`NOT_BUILT.md`); the numbers are in `monitoring/out/equity.json` and `validation/site_signal/report.md`.

## 16. Other limits

- **simaerep classic is the legacy algorithm.** simaerep v1.0.0 defaults to its inframe method, which is not ported (BL-12).
- **Demo-grade security.** Roles are demo identity headers, with no real authentication (BL-18). It runs on SQLite, one instance. The audit hash chain is tamper-evident only inside the database (BL-19).
- **Regulatory questions are open (UNVERIFIED).** These include investigator control of patient-reported source data, and what sponsor awareness of an unfiltered patient stream means for safety reporting (BL-20). Site Signal runs in shadow mode only.
- **The blind run is not built.** No one can yet test the method on a study nobody prepared (`NOT_BUILT.md`).

## The next step, the one that is not circular

Every Site Signal result here comes from our own simulator. The test that does not depend on it is retrospective. It needs completed trials that collected patient-reported symptoms and the clinician AE log (CTCAE) for the same patients, with site IDs. The method would be pre-registered as a new SAP version before data access, and the results reported whatever they show (BL-11).

## How every number was checked

1. **No Site Signal number on this page, in the README, in the deck (`docs/pitch/deck.html`) or in the video storyboard (`docs/08-demo-and-pitch.md`) was typed.** Each was written as a token naming its source file, its JSON path and its display format. `validation/render_numbers.py` replaced each token with the value from `validation/site_signal/summary.json` or `monitoring/out/<file>.json`, rounded by `docs/11` §15 rule 6. It fails, writing nothing, when a path is missing or matches more than one row. The REQ-023 bounds and outcomes and the size check are computed by the same script from the unrounded values (`docs/11` §12.1).
2. **`python3 validation/render_numbers.py --check <rendered files>` passed.** It confirms that no token is left. It reads each value in the table below from its source path again and confirms that the document shows the same digits on the listed line.
3. **Evaluation numbers** (section 11) were copied from `eval/results/latest.json`, and the key is named next to each one.
4. **A second teammate ticks the table below against the source files** before the deck and the video use these numbers.

<!-- ss-provenance:start -->
The provenance table is generated here by `validation/render_numbers.py` when the numbers are filled. It lists every rendered number with the document, line, value, source file and JSON path.
<!-- ss-provenance:end -->
