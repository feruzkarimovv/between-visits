"""report.md and funnel.svg of the committed study, from its JSON outputs (docs/11-site-signal-sap.md §8.4, §12.7,
§15). SIMULATED.

Reads only the files ``run.py`` wrote into one output directory (``signal_run.json``, ``answer_key.json``,
``report_only.json`` and, when task S9 has landed, ``equity.json``), plus the display labels of
``data/signal_rules.json`` and the docs/11 §17 rows, and writes:

* ``report.md``: provenance; design and thresholds; the ranked sites with the three indicators on the identical
  study (capture discordance, the gsm-style rate KRI and simaerep classic (legacy)); the funnel image; the §8.3
  secondary calibrated p-values with Benjamini-Hochberg q-values; the §10.3 ablation; the §6.2 paged stratum and
  the §4.1 ungraded primary-term reports; the answer key and its confusion, labeled "illustration only"; equity
  when present; the docs/11 §17 rows that apply; and the §15 rule 8 next step (retrospective validation on
  trials with paired patient-reported and clinician-reported data);
* ``funnel.svg``: computed sites at (E, O/E) with the Look and Watch lower limits of ``signal_run.json``
  ``funnel``, not-computed sites as hollow grey points in a strip below the axis. Tiers use exact z*, never the
  drawn line.

Every number on both is badged SIMULATED (§15 rule 2) and rounded only for display (§15 rule 6: proportions 2
dp, MC SE and CI limits 3, z 2, O/E 2, E and V 1; probabilities and p-values 3). No wall-clock time, path or
random draw enters either file, so the same JSON gives byte-identical output. Wording follows §15 rule 4:
capture discordance, a reason to look, not a finding; ``none`` reads "No signal at this sample size"; no green.
No LLM anywhere on this path (CLAUDE.md rule 1).

Command line (re-render a development output directory; the committed report is written only by ``run.py``,
whose run is logged)::

    uv run --project monitoring python -m bvsignal.report --out "$TMPDIR/s6" [--report-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bvsignal import DATA_ORIGIN, REPO_ROOT
from bvsignal import seed as bvseed

REPORT_MD = "report.md"
FUNNEL_SVG = "funnel.svg"
OUTPUT_NAMES = (REPORT_MD, FUNNEL_SVG)
SIGNAL_RULES_FILE = REPO_ROOT / "data" / "signal_rules.json"
SAP_LINK = "../../docs/11-site-signal-sap.md"  # from validation/site_signal/report.md
SUMMARY_REL = "validation/site_signal/summary.json"
COMMITTED_DIRS = ("monitoring/out", "validation/site_signal")
BADGE = "`SIMULATED`"
DASH = "—"

INDICATOR_NAMES = {
    "discordance": "Capture discordance",
    "rate_kri": "gsm-style rate KRI",
    "simaerep_classic": "simaerep classic (legacy)",
    "ae_report_ratio": "AE-to-report ratio (ablation)",
}
TIERED = ("discordance", "rate_kri", "simaerep_classic")
NEXT_STEP = ("**Next step.** The only non-circular validation of Site Signal is retrospective analysis of trials "
             "with paired patient-reported and clinician-reported (CTCAE) adverse-event data and site IDs. Every "
             "number here comes from a simulation in which both streams and the answer key share one model family "
             "(docs/11 §16).")

# funnel.svg geometry and colours (no green anywhere: §15 rule 4)
W, H = 760, 548
LEFT, RIGHT, TOP, PLOT_BOTTOM = 72, 28, 78, 392
STRIP_Y = 484
COLOURS = {"watch": "#b91c1c", "look": "#d97706", "none": "#475569", "not_computed": "#9ca3af"}
LIMIT_STYLE = {"watch": ("#b91c1c", ""), "look": ("#d97706", "6 4")}


class ReportError(RuntimeError):
    """An input of the report is missing or malformed (message is user-facing)."""


# ---- inputs -----------------------------------------------------------------------------------------------------


def _load(path: Path) -> Any:
    if not path.is_file():
        raise ReportError(f"{path} does not exist; run `python -m bvsignal.run` first")
    return json.loads(path.read_text(encoding="utf-8"))


def load_outputs(out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    docs = {name: _load(out_dir / f"{name}.json") for name in ("signal_run", "answer_key", "report_only")}
    equity = out_dir / "equity.json"
    docs["equity"] = _load(equity) if equity.is_file() else None
    for name, doc in docs.items():
        if doc is not None and doc.get("data_origin") != DATA_ORIGIN:
            raise ReportError(f"{name}.json must carry data_origin {DATA_ORIGIN}")
    return docs


def labels(path: Path = SIGNAL_RULES_FILE) -> dict[str, Any]:
    """``signal_rules.json`` ``labels`` with the ``en`` strings flattened (as the API passes them, docs/03 §5.3)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))["labels"]

    def flat(v: Any) -> Any:
        if isinstance(v, dict) and set(v) == {"en"}:
            return v["en"]
        if isinstance(v, dict):
            return {k: flat(x) for k, x in v.items()}
        return v

    return flat(raw)


def deviation_rows(text: str | None = None) -> list[dict[str, str]]:
    """The rows of docs/11 §17: ID, date/time, commit, SAP section, type and whether eval outputs were seen."""
    text = bvseed.sap_deviations_text() if text is None else text
    rows = []
    for line in text.splitlines():
        if not re.match(r"^\|\s*[A-Z]+\d+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        rows.append({"id": cells[0], "when": cells[1], "section": cells[3], "type": cells[4], "seen": cells[-2]})
    return rows


# ---- formatting -----------------------------------------------------------------------------------------------


def fmt(x: Any, dp: int) -> str:
    """A display value rounded to ``dp`` places (§15 rule 6); a dash for null."""
    if x is None:
        return DASH
    v = float(x)
    if not math.isfinite(v):
        return DASH
    out = f"{v:.{dp}f}"
    return "0." + "0" * dp if dp and out == "-0." + "0" * dp else ("0" if out == "-0" else out)


def count(x: Any) -> str:
    return DASH if x is None else str(int(x))


def code(x: Any) -> str:
    return DASH if x is None else f"`{x}`"


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def tier_text(tier: str, reason: str | None, lab: Mapping[str, Any]) -> str:
    if tier == "not_computed":
        return f"{lab['not_computed']}: `{reason}`" if reason else str(lab["not_computed"])
    return str(lab.get(tier, tier))


# ---- report.md ----------------------------------------------------------------------------------------------------


def render_markdown(docs: Mapping[str, Any], lab: Mapping[str, Any], deviations: Sequence[Mapping[str, str]]
                    ) -> str:
    sr, ak, ro, eq = docs["signal_run"], docs["answer_key"], docs["report_only"], docs["equity"]
    run = sr["run"]
    dev = run.get("seed_label") == "dev"
    rows = sr["rows"]
    by_site = {r["site_id"]: r for r in rows}
    sites = {s["site_id"]: s for s in sr["sites"]}
    md: list[str] = []
    add = md.append

    add("# Site Signal: committed evaluation study")
    add("")
    add(f"{BADGE} · capture discordance is **a reason to look, not a finding**.")
    add("")
    if dev:
        add("> **DEVELOPMENT OUTPUT (dev seed), not a result.** Never committed or quoted.")
        add("")
    add("Every number on this page is SIMULATED: both streams of every site, the planted site behaviours and the "
        "answer key come from the simulation of the pre-registered analysis plan "
        f"[docs/11-site-signal-sap.md]({SAP_LINK}) (tag `sap-v1`, §11). It describes simulated sites only and says "
        "nothing about any real site. Numbers come from `monitoring/out/*.json` of the same run; they are rounded "
        "here for display only (§15 rule 6). Operating characteristics (false-flag rates, power, the failure case) "
        f"are in `{SUMMARY_REL}`, never on this page.")
    add("")

    # provenance
    add(f"## Provenance · {BADGE}")
    add("")
    md += table(["Field", "Value"], [
        ["Run", code(run["id"])],
        ["Seed", code(run.get("seed_label"))],
        ["sap_tag_commit", code(run.get("sap_tag_commit"))],
        ["eval_seed", code(run.get("eval_seed"))],
        ["beacon_round", code(run.get("beacon_round"))],
        ["code_commit", code(run.get("code_commit"))],
        ["generated_at (commit time of code_commit)", code(run.get("generated_at"))],
        ["numpy / scipy", f"{code(run.get('numpy_version'))} / {code(run.get('scipy_version'))}"],
        ["thresholds.json sha256", code(run.get("thresholds_sha256"))],
    ])
    add("")

    # design and thresholds
    d = run["design"]
    cal = ro.get("calibration", {})
    add(f"## Design and thresholds · {BADGE}")
    add("")
    md += table(["Quantity", "Value", "Data"], [
        ["Sites", count(d["n_sites"]), BADGE],
        ["Patients per site (design range)", f"{d['patients_per_site'][0]}–{d['patients_per_site'][1]}", BADGE],
        ["Data cut", f"{d['data_cut_date']} ({d['window_weeks']} weeks)", BADGE],
        ["Episode rate μ (grade ≥ 2 per patient window)", fmt(d.get("mu"), 2), BADGE],
        ["Gross planted capture loss f", fmt(d.get("gross_f"), 2), BADGE],
        ["Computed sites K (capture discordance)", count(run["n_computed_sites"]), BADGE],
        ["Study not computed", f"`{run['study_not_computed_reason']}`" if run["study_not_computed_reason"] else "no",
         BADGE],
        ["φ̂ (winsorized dispersion, §8.2)", fmt(run["phi"], 2), BADGE],
        ["τ̂² (additive between-site variance, §8.2)", fmt(run["tau2"], 3), BADGE],
        ["Expected false Look flags per study (calibration mean, §8.3)",
         fmt(run["expected_false_look_flags_per_study"], 2), BADGE],
        ["Null studies behind the thresholds (§9.2)", count(cal.get("r_null")), BADGE],
    ])
    add("")
    add("Thresholds are read from `thresholds.json` (calibrated once from the pre-registered null, §9), never "
        "computed by this run. Watch is nested in Look; a missing threshold is never assigned (§9.3).")
    add("")
    flag = {"discordance": "z* ≤ threshold", "rate_kri": "z* ≤ threshold", "simaerep_classic": "prob ≥ threshold"}
    dp = {"discordance": 2, "rate_kri": 2, "simaerep_classic": 3}
    md += table(["Indicator", "Look", "Watch", "Flagged when", "Data"], [
        [INDICATOR_NAMES[n], fmt(run["thresholds"][n]["look"], dp[n]), fmt(run["thresholds"][n]["watch"], dp[n]),
         flag[n], BADGE] for n in TIERED])
    add("")
    add(f"Tier labels: **{lab['watch']}**, **{lab['look']}**, **{lab['none']}** (neutral, never green) and "
        f"**{lab['not_computed']}** (grey, always with its reason). {lab['footer']}")
    add("")

    # ranked sites (primary)
    add(f"## Ranked sites: capture discordance · {BADGE}")
    add("")
    add("Primary indicator (§8): matched site AEs O against the leave-one-site-out expectation E for the site's "
        "evaluable, non-paged Diarrhea and Dyspnea grade 2 episodes, with the overdispersion-adjusted score z*. "
        "Computed sites by rank (z* ascending), then the sites that are not computed, by site.")
    add("")
    hdr = ["Rank", "Site", "Tier", "O", "E", "V", "O/E", "z", "z*", "Evaluable", "Pending", "Paged",
           "Call completion", "Data"]
    body = []
    for r in rows:
        body.append([count(r["rank"]), f"{r['site_id']} {sites[r['site_id']]['name']}",
                     tier_text(r["tier"], r["not_computed_reason"], lab), count(r["O"]), fmt(r["E"], 1),
                     fmt(r["V"], 1), fmt(r["oe_ratio"], 2), fmt(r["z_raw"], 2), fmt(r["z_adj"], 2),
                     count(r["n_episodes_evaluable"]), count(r["n_pending"]), count(r["n_paged"]),
                     fmt(r["call_completion"], 2), BADGE])
    md += table(hdr, body)
    add("")
    reasons_used = sorted({r["not_computed_reason"] for r in rows if r["not_computed_reason"]})
    if reasons_used:
        add("Not-computed reasons (§7):")
        add("")
        md += table(["Reason", "Meaning"], [[f"`{k}`", str(lab["reasons"][k])] for k in reasons_used])
        add("")

    # three indicators
    add(f"## Three indicators on the identical study · {BADGE}")
    add("")
    add("Both comparators use only the site AE log of the same simulated study (§10, REQ-028) and are calibrated "
        "on the same null studies. They have no coverage guard; they apply `min_patients`.")
    add("")
    body = []
    for r in rows:
        kri, se = r["comparators"]["rate_kri"], r["comparators"]["simaerep_classic"]
        body.append([r["site_id"], fmt(r["z_adj"], 2), tier_text(r["tier"], r["not_computed_reason"], lab),
                     fmt(kri["z_adj"], 2), tier_text(kri["tier"], None, lab), fmt(se["prob"], 3),
                     fmt(se["p_value"], 3), tier_text(se["tier"], None, lab), BADGE])
    md += table(["Site", "Discordance z*", "Tier", "Rate KRI z*", "Tier", "simaerep prob", "BH p-value", "Tier",
                 "Data"], body)
    add("")

    # funnel
    fn = sr["funnel"]
    add(f"## Funnel · {BADGE}")
    add("")
    add(f"![Capture discordance funnel plot, SIMULATED]({FUNNEL_SVG})")
    add("")
    add("Each computed site at (E, O/E); the Look and Watch lines are the §8.4 lower limits, which approximate V by "
        "E(1 − p̄) and are drawn for orientation only. Tiers always use each site's exact z*. Not-computed sites are "
        "the hollow grey points below the axis.")
    add("")
    md += table(["Quantity", "Value", "Data"], [["p̄ (pooled matched share of computed sites)", fmt(fn["p_bar"], 2),
                                                BADGE]])
    add("")

    # secondary p-values
    sec = ro["secondary"]
    add(f"## Secondary analysis: calibrated p-values with Benjamini-Hochberg q-values · {BADGE}")
    add("")
    add("Report only, never used for tiers (§8.3): p = (1 + #{null pooled z* ≤ z*}) / (1 + M) over the Look pool of "
        f"the calibration (M = {count(sec['M'])} SIMULATED null site values), with BH q-values across computed sites. "
        "Normal-approximation p-values are not used.")
    add("")
    md += table(["Site", "z*", "Calibrated p", "BH q", "Data"],
                [[s["site_id"], fmt(s["z_adj"], 2), fmt(s["p_empirical"], 3), fmt(s["q_bh"], 3), BADGE]
                 for s in _ranked(sec["sites"], by_site)])
    add("")

    # ablation
    abl = ro["ablation"]
    add(f"## Ablation: AE-to-report ratio · {BADGE}")
    add("")
    add("Validation and report only, never a UI column (§10.3): the site's AE rows that map to a primary term against "
        "its evaluable non-paged episodes, leave-one-site-out, with no episode-level matching. It separates the "
        "value of matching from the value of a patient-reported denominator.")
    add("")
    md += table(["Site", "U", "E^U", "z", "z*", "Tier", "Data"],
                [[s["site_id"], fmt(s["U"], 0), fmt(s["E_U"], 1), fmt(s["z_raw"], 2), fmt(s["z_adj"], 2),
                  tier_text(s["tier"], s["not_computed_reason"], lab), BADGE]
                 for s in _ranked(abl["sites"], by_site)])
    add("")
    md += table(["Quantity", "Value", "Data"], [["φ̂ of the ablation (multiplicative)", fmt(abl["phi"], 2), BADGE],
                                                ["Look threshold", fmt(abl["thresholds"]["look"], 2), BADGE],
                                                ["Watch threshold", fmt(abl["thresholds"]["watch"], 2), BADGE]])
    add("")

    # descriptive
    add(f"## Paged stratum and ungraded primary-term reports · {BADGE}")
    add("")
    add("Descriptive only. Paged episodes (an urgent or emergency page on a folded call, §6.2) are matched but never "
        "enter O, E or V: the site was told in real time. Ungraded primary-term reports are completed calls on which "
        "a primary term was reported without a gradable answer (§4.1); they open and close no episode.")
    add("")
    md += table(["Site", "Paged episodes", "Paged, matched", "Ungraded primary-term reports", "Data"],
                [[s["site_id"], count(s["paged_stratum"]["n"]), count(s["paged_stratum"]["matched"]),
                  count(s["ungraded_primary_term_reports"]["total"]), BADGE]
                 for s in ro["descriptive"]["sites"]])
    add("")

    # answer key and confusion
    add(f"## Answer key and confusion: illustration only · {BADGE}")
    add("")
    add("**Illustration only, never evidence of performance** (§12.7). With five planted positives these counts carry "
        f"little information; the evidence is the operating characteristics in `{SUMMARY_REL}` (§12.1–§12.6). "
        "Positives are the planted capture losses; a positive that is not computed counts as missed. The two "
        "must-be-grey sites are reported separately and are in no cell. A site at Watch also counts at Look. "
        "Honest sites with low capture are planted on purpose: low capture can come from honest practice.")
    add("")
    tiers = {n: {r["site_id"]: (r["tier"] if n == "discordance" else r["comparators"][n]["tier"]) for r in rows}
             for n in TIERED}
    md += table(["Site", "Answer key", "Planted f", "Discordance", "Rate KRI", "simaerep classic", "Data"],
                [[a["site_id"], str(lab["answer_key"].get(a["label"], a["label"])), fmt(a["f"], 2),
                  tier_text(tiers["discordance"][a["site_id"]], None, lab),
                  tier_text(tiers["rate_kri"][a["site_id"]], None, lab),
                  tier_text(tiers["simaerep_classic"][a["site_id"]], None, lab), BADGE] for a in ak["answer_key"]])
    add("")
    body = []
    for n in TIERED:
        for t in ("watch", "look"):
            c = ak["confusion"][n][t]
            body.append([INDICATOR_NAMES[n], str(lab[t]), count(c["tp"]), count(c["fp"]), count(c["fn"]),
                         count(c["tn"]), BADGE])
    md += table(["Indicator", "Tier", "TP", "FP", "FN", "TN", "Data"], body)
    add("")
    if ak.get("must_be_grey"):
        body = []
        for g in ak["must_be_grey"]:
            for n in TIERED:
                x = g["indicators"][n]
                exp = "—" if x["expected_reason"] is None else f"`{x['expected_reason']}`"
                ok = DASH if x["as_expected"] is None else ("yes" if x["as_expected"] else "**no**")
                body.append([g["site_id"], str(lab["answer_key"].get(g["label"], g["label"])), INDICATOR_NAMES[n],
                             tier_text(x["tier"], x["not_computed_reason"], lab), exp, ok, BADGE])
        md += table(["Site", "Answer key", "Indicator", "Tier", "Must be", "As expected", "Data"], body)
        add("")

    # equity
    if eq is not None:
        md += _equity_section(eq)

    # deviations
    add("## Deviations and clarifications (docs/11 §17)")
    add("")
    devs = [r["id"] for r in deviations if "deviation" in r["type"].lower()]
    add("Deviations from the pre-specified analysis that apply to this run: "
        + (", ".join(devs) if devs else "none") + f". Clarifications are listed for completeness; the full rows are in "
        f"[docs/11 §17]({SAP_LINK}#17-deviations).")
    add("")
    if deviations:
        md += table(["ID", "Type", "SAP section", "Date/time (ET)", "Eval outputs seen?"],
                    [[r["id"], r["type"], r["section"], r["when"], r["seen"]] for r in deviations])
        add("")

    add("## Next step")
    add("")
    add(NEXT_STEP)
    add("")
    add(f"{lab['footer']} {BADGE}")
    return "\n".join(md) + "\n"


def _ranked(entries: Sequence[Mapping[str, Any]], rows: Mapping[str, Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Per-site entries in the ranked-table order (computed by rank, then the rest by site id)."""
    order = {sid: k for k, sid in enumerate(rows)}
    return sorted(entries, key=lambda e: order.get(e["site_id"], len(order)))


def _equity_section(eq: Mapping[str, Any]) -> list[str]:
    md = [f"## Equity: capture by language and pace within sites · {BADGE}", ""]
    md.append("Mantel-Haenszel odds ratios within sites (§14); below 1 means that group's episodes were found in the "
              "site AE log less often. Power is low at these sample sizes; pace is a built-in negative control.")
    md.append("")
    body = []
    for block, name in (("language", "Spanish vs English"), ("pace", "Extra-time vs standard pace")):
        b = eq.get(block)
        if not isinstance(b, Mapping):
            continue
        ci = b.get("ci95") if isinstance(b.get("ci95"), Sequence) else None
        ci_text = f"{fmt(ci[0], 3)} to {fmt(ci[1], 3)}" if ci and len(ci) == 2 else DASH
        body.append([name, fmt(b.get("mh_or"), 2), ci_text, count(b.get("n_sites_used")), BADGE])
    if body:
        md += table(["Comparison", "MH odds ratio", "95% CI (patient bootstrap)", "Sites used", "Data"], body)
        md.append("")
    cf = eq.get("single_language_counterfactual")
    if isinstance(cf, Sequence) and cf:
        changed = [r for r in cf if isinstance(r, Mapping) and r.get("tier_now") != r.get("tier_if_english_only")]
        md += table(["Single-language counterfactual", "Value", "Data"],
                    [["Sites whose tier changes with English-only calls", count(len(changed)), BADGE]])
        md.append("")
    md.append("Full equity results: `monitoring/out/equity.json`.")
    md.append("")
    return md


# ---- funnel.svg -------------------------------------------------------------------------------------------------


def _nice_step(span: float, target: int) -> float:
    raw = span / max(1, target)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def render_funnel_svg(signal_run: Mapping[str, Any], lab: Mapping[str, Any]) -> str:
    fn = signal_run["funnel"]
    rows = signal_run["rows"]
    dev = signal_run["run"].get("seed_label") == "dev"
    points = [p for p in fn["points"] if p["E"] is not None and p["oe_ratio"] is not None]
    limits = fn["limits"]
    x_top = max([float(lim["E"]) for lim in limits] + [float(p["E"]) for p in points] + [10.0])
    y_top = max([1.5] + [float(p["oe_ratio"]) * 1.1 for p in points])
    y_step = _nice_step(y_top, 6)
    y_top = math.ceil(y_top / y_step) * y_step
    x_step = _nice_step(x_top, 8)
    x_top = math.ceil(x_top / x_step) * x_step
    pw, ph = W - LEFT - RIGHT, PLOT_BOTTOM - TOP

    def sx(e: float) -> float:
        return LEFT + pw * e / x_top

    def sy(v: float) -> float:
        return PLOT_BOTTOM - ph * min(v, y_top) / y_top

    def f2(v: float) -> str:
        return f"{v:.2f}"

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'font-family="Helvetica, Arial, sans-serif" font-size="12">',
           f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
    title = "Capture discordance funnel · SIMULATED"
    if dev:
        title = "DEVELOPMENT OUTPUT (dev seed), not a result · " + title
    out.append(f'<text x="{LEFT}" y="26" font-size="15" font-weight="bold" fill="#111827">{_esc(title)}</text>')
    out.append(f'<text x="{LEFT}" y="46" fill="#374151">{_esc(str(lab["footer"]))} Lines approximate; tiers use each '
               "site's exact z*.</text>")
    # axes and grid
    y = 0.0
    while y <= y_top + 1e-9:
        yy = f2(sy(y))
        out.append(f'<line x1="{LEFT}" y1="{yy}" x2="{W - RIGHT}" y2="{yy}" stroke="#e5e7eb" stroke-width="1"/>')
        out.append(f'<text x="{LEFT - 8}" y="{f2(sy(y) + 4)}" text-anchor="end" fill="#374151">{y:.2f}</text>')
        y += y_step
    x = 0.0
    while x <= x_top + 1e-9:
        xx = f2(sx(x))
        out.append(f'<line x1="{xx}" y1="{PLOT_BOTTOM}" x2="{xx}" y2="{PLOT_BOTTOM + 5}" stroke="#374151"/>')
        out.append(f'<text x="{xx}" y="{PLOT_BOTTOM + 19}" text-anchor="middle" fill="#374151">{x:g}</text>')
        x += x_step
    out.append(f'<line x1="{LEFT}" y1="{PLOT_BOTTOM}" x2="{W - RIGHT}" y2="{PLOT_BOTTOM}" stroke="#374151"/>')
    out.append(f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{PLOT_BOTTOM}" stroke="#374151"/>')
    out.append(f'<text x="{f2(LEFT + pw / 2)}" y="{PLOT_BOTTOM + 36}" text-anchor="middle" fill="#111827">'
               "E, expected matched episodes (SIMULATED)</text>")
    out.append(f'<text x="18" y="{f2(TOP + ph / 2)}" text-anchor="middle" fill="#111827" '
               f'transform="rotate(-90 18 {f2(TOP + ph / 2)})">O/E (SIMULATED)</text>')
    # reference line O/E = 1
    out.append(f'<line x1="{LEFT}" y1="{f2(sy(1.0))}" x2="{W - RIGHT}" y2="{f2(sy(1.0))}" stroke="#6b7280" '
               'stroke-dasharray="2 3"/>')
    # limits
    for tier in ("look", "watch"):
        colour, dash = LIMIT_STYLE[tier]
        pts = [(float(lim["E"]), lim[f"{tier}_lower"]) for lim in limits if lim[f"{tier}_lower"] is not None]
        pts = [(e, v) for e, v in pts if e <= x_top]
        if len(pts) > 1:
            path = " ".join(f"{f2(sx(e))},{f2(sy(float(v)))}" for e, v in pts)
            extra = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="1.5"{extra}/>')
    # computed sites
    for p in points:
        cx, cy = f2(sx(float(p["E"]))), f2(sy(float(p["oe_ratio"])))
        colour = COLOURS.get(p["tier"], COLOURS["none"])
        out.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{colour}" stroke="#ffffff" stroke-width="1"/>')
        out.append(f'<text x="{f2(sx(float(p["E"])) + 7)}" y="{f2(sy(float(p["oe_ratio"])) - 6)}" font-size="10" '
                   f'fill="#111827">{_esc(p["site_id"])}</text>')
    # not-computed strip
    grey = sorted((r for r in rows if r["tier"] == "not_computed"), key=lambda r: r["site_id"])
    out.append(f'<text x="{LEFT}" y="{STRIP_Y - 14}" fill="#6b7280">{_esc(str(lab["not_computed"]))} '
               "(no position: grey, with a reason)</text>")
    if grey:
        gap = min(48.0, pw / max(1, len(grey)))
        for k, r in enumerate(grey):
            cx = LEFT + 10 + gap * k
            out.append(f'<circle cx="{f2(cx)}" cy="{STRIP_Y}" r="5" fill="none" stroke="{COLOURS["not_computed"]}" '
                       'stroke-width="1.5"/>')
            out.append(f'<text x="{f2(cx)}" y="{STRIP_Y + 18}" text-anchor="middle" font-size="10" '
                       f'fill="#6b7280">{_esc(r["site_id"])}</text>')
    # legend
    lx, ly = W - RIGHT - 250, TOP + 4
    entries = [("watch", str(lab["watch"])), ("look", str(lab["look"])), ("none", str(lab["none"]))]
    out.append(f'<rect x="{lx - 8}" y="{ly - 14}" width="256" height="{18 * (len(entries) + 2) + 6}" fill="#ffffff" '
               'stroke="#e5e7eb"/>')
    for k, (tier, text) in enumerate(entries):
        yy = ly + 18 * k
        out.append(f'<circle cx="{lx}" cy="{yy - 4}" r="5" fill="{COLOURS[tier]}"/>')
        out.append(f'<text x="{lx + 12}" y="{yy}" fill="#111827">{_esc(text)}</text>')
    for k, tier in enumerate(("look", "watch")):
        yy = ly + 18 * (len(entries) + k)
        colour, dash = LIMIT_STYLE[tier]
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<line x1="{lx - 5}" y1="{yy - 4}" x2="{lx + 6}" y2="{yy - 4}" stroke="{colour}" '
                   f'stroke-width="1.5"{extra}/>')
        out.append(f'<text x="{lx + 12}" y="{yy}" fill="#111827">{_esc(str(lab[tier]))} lower limit</text>')
    out.append(f'<text x="{W - RIGHT}" y="{H - 10}" text-anchor="end" font-size="10" fill="#6b7280">SIMULATED · '
               "docs/11-site-signal-sap.md §8.4</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- writing ----------------------------------------------------------------------------------------------------


def write_report(out_dir: Path, report_dir: Path) -> list[Path]:
    """Render report.md and funnel.svg from the JSON outputs in ``out_dir`` into ``report_dir``."""
    docs = load_outputs(out_dir)
    lab = labels()
    md = render_markdown(docs, lab, deviation_rows())
    svg = render_funnel_svg(docs["signal_run"], lab)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path, svg_path = report_dir / REPORT_MD, report_dir / FUNNEL_SVG
    md_path.write_text(md, encoding="utf-8")
    svg_path.write_text(svg, encoding="utf-8")
    return [md_path, svg_path]


def _inside(path: Path, rel: str) -> bool:
    target = (REPO_ROOT / rel).resolve()
    p = Path(path).resolve()
    return p == target or target in p.parents


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bvsignal.report",
                                 description="Re-render report.md and funnel.svg from a development output directory "
                                             "(the committed report is written only by bvsignal.run). SIMULATED.")
    ap.add_argument("--out", type=Path, required=True, help="directory with the run's JSON outputs")
    ap.add_argument("--report-dir", type=Path, default=None, help="where to write (default: --out)")
    args = ap.parse_args(argv)
    report_dir = args.out if args.report_dir is None else args.report_dir
    try:
        for rel in COMMITTED_DIRS:
            if _inside(report_dir, rel):
                raise ReportError(f"only `python -m bvsignal.run` writes into {rel}/ (its run is logged, docs/11 §1.2)")
        paths = write_report(args.out, report_dir)
    except ReportError as e:
        print(f"bvsignal.report: {e}", file=sys.stderr)
        return 2
    for p in paths:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
