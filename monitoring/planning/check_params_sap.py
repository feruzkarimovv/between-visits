"""Check that monitoring/params.yaml agrees with the SAP tables (docs/11 §11.3, §11.4 and the §11.5 values).

docs/11 §11.3: "params.yaml must agree with this table at the tag; S1 includes that check." For every
table row this script extracts the numbers written in the SAP cell (section references, inline code
spans with letters and digits glued to words such as "G2" are ignored) and compares them, in order,
with the numbers params.yaml gives for the same key; text-only rows are checked for the key words.
The planted-truth rows (§11.4) are compared on count and mechanism numbers, and the §11.5 "Value
filled at tag time" table against params.yaml and planning_grid.json `.chosen`.

    uv run --project monitoring python monitoring/planning/check_params_sap.py   # prints the comparison, exit 1 on a mismatch
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SAP = "docs/11-site-signal-sap.md"
PARAMS = "monitoring/params.yaml"
GRID = "monitoring/planning/planning_grid.json"
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")


@dataclass
class Row:
    section: str
    key: str
    sap: str
    params: str
    ok: bool


def numbers(cell: str) -> list[float]:
    """Numbers written in a SAP table cell, ignoring §-references and code spans that contain letters."""
    s = cell.replace("−", "-")
    s = re.sub(r"`[^`]*[A-Za-z_][^`]*`", " ", s)
    s = re.sub(r"§\s?\d+(?:\.\d+)*", " ", s)
    return [float(x) for x in _NUM.findall(s)]


def section(text: str, heading: str) -> str:
    m = re.search(rf"^### {re.escape(heading)}.*?(?=^### |^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise SystemExit(f"{SAP}: section {heading} not found")
    return m.group(0)


def table_rows(sec: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in sec.splitlines():
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[cells[0]] = cells[1:]
    return rows


def _same(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(math.isclose(x, y, rel_tol=0, abs_tol=1e-9) for x, y in zip(a, b, strict=True))


def _fmt(xs: list[float] | str) -> str:
    if isinstance(xs, str):
        return xs
    return "[" + ", ".join(str(int(x)) if float(x).is_integer() else f"{x:g}" for x in xs) + "]"


def checks_11_3(p: dict[str, Any]) -> list[tuple[str, Callable[[], list[float]], Callable[[str], bool] | None]]:
    """(SAP key cell, params numbers in the order the SAP writes them, optional extra text check)."""
    d, r, ep, ag, sc, ps = p["design"], p["roster"], p["episodes"], p["answer_generation"], p["site_capture"], p["patient_stream"]
    sec = ag["secondary"]
    sev_order = ("mild", "moderate", "severe", "very_severe")
    sp = r["spanish_share_by_site"]
    return [
        ("`design.n_sites`", lambda: [d["n_sites"], d["site_ids"][0], d["site_ids"][-1], d["live_site"]],
         lambda _: len(d["site_ids"]) == d["n_sites"] and d["site_ids"] == list(range(d["site_ids"][0], d["site_ids"][0] + d["n_sites"]))),
        ("`design.patients_per_site`", lambda: [x for rng in p["planning"]["p1"]["ranges"] for x in rng],
         lambda _: list(d["patients_per_site"] or []) in [list(x) for x in p["planning"]["p1"]["ranges"]]),
        ("`design.window_weeks`, `data_cut_day`", lambda: [d["window_weeks"], d["data_cut_day"]],
         lambda _: d["data_cut_day"] == 7 * d["window_weeks"]),
        ("`design.study_start_date`", lambda: [int(x) for x in str(d["study_start_date"]).split("-")],
         lambda cell: str(d["study_start_date"]) in cell),
        ("`design.enrollment_spread_days`", lambda: [d["enrollment_spread_days"]], None),
        ("`design.cycle_days`", lambda: [d["cycle_days"]], None),
        ("`design.call_days_after_dose`", lambda: list(d["call_days_after_dose"]), None),
        ("`roster.spanish_share_by_site`", lambda: [sp["a"], sp["b"], round(sp["a"] / (sp["a"] + sp["b"]), 2)], None),
        ("`roster.extra_time`", lambda: [r["extra_time"]["min_age"], r["age"]["mean"], r["age"]["sd"]], None),
        ("`episodes.mu_g2plus_per_patient_window`", lambda: [ep["mu_g2plus_per_patient_window"], min(p["grid"]["mu"])], None),
        ("`episodes.term_mix`", lambda: [ep["term_mix"][t] for t in ("Diarrhea", "Fever", "Dyspnea")], None),
        ("`episodes.g3_share`", lambda: [ep["g3_share"]], None),
        ("`episodes.mean_duration_calls`", lambda: [ep["mean_duration_calls"]], lambda cell: ep["duration_dist"] in cell),
        ("`episodes.patient_frailty`", lambda: [ep["patient_frailty"]["shape"], ep["patient_frailty"]["scale"]], None),
        ("`episodes.casemix_sd_log`", lambda: [ep["casemix_sd_log"], p["failure_case"]["casemix_sd_log"]], None),
        ("`answer_generation.method`", lambda: [], lambda _: "enumerate" in ag["method"] and "rules_py" in ag["method"]),
        ("`answer_generation.numeric_domains`", lambda: [ag["numeric_domains"]["DIARRHEA_STOOLS_PER_DAY"]["min"],
                                                         ag["numeric_domains"]["DIARRHEA_STOOLS_PER_DAY"]["max"],
                                                         ag["numeric_domains"]["TEMP_HIGHEST"]["min"],
                                                         ag["numeric_domains"]["TEMP_HIGHEST"]["max"],
                                                         ag["numeric_domains"]["TEMP_HIGHEST"]["step"]],
         lambda _: ag["numeric_domains"]["DIARRHEA_STOOLS_PER_DAY"]["step"] == 1),
        ("`answer_generation.baseline_stools`", lambda: list(ag["baseline_stools"]["values"]),
         lambda _: len(set(ag["baseline_stools"]["p"])) == 1 and math.isclose(sum(ag["baseline_stools"]["p"]), 1.0)),
        ("`answer_generation.secondary`", lambda: [sec["diarrhea_episode"]["STOOL_BLOOD"]["yes"], sec["diarrhea_episode"]["dizzy_on_standing"],
                                                   *[sec["dyspnea_g2"]["SOB_SEV"][k] for k in sev_order],
                                                   *[sec["dyspnea_g3"]["SOB_SEV"][k] for k in sev_order[1:]]],
         lambda _: math.isclose(sum(sec["diarrhea_episode"]["STOOL_BLOOD"].values()), 1.0)
         and set(sec["diarrhea_episode"]["dizziness_sev_when_dizzy"]) == set(sev_order)
         and "mild" not in sec["dyspnea_g3"]["SOB_SEV"]),
        ("`site_capture.base_p`", lambda: [sc["base_p"][t][g] for t in ("Diarrhea", "Fever", "Dyspnea") for g in (2, 3)], None),
        ("`site_capture.between_site_sd_logit`", lambda: [sc["between_site_sd_logit"], p["failure_case"]["between_site_sd_logit"]], None),
        ("`site_capture.patient_re_sd_logit`", lambda: [sc["patient_re_sd_logit"]], None),
        ("`site_capture.aestdtc_noise_days_sd`", lambda: [sc["aestdtc_noise_days_sd"]], None),
        ("`site_capture.entry_lag_days`", lambda: [sc["entry_lag_days"]["mean"], sc["entry_lag_days"]["shape"]],
         lambda _: sc["entry_lag_days"]["dist"] == "gamma"),
        ("`site_capture.other_aes_per_patient_window`", lambda: [sc["other_aes_per_patient_window"]], None),
        ("`patient_stream.call_completion`", lambda: [ps["call_completion"]["mean"], ps["call_completion"]["kappa"]],
         lambda _: ps["call_completion"]["dist"] == "beta"),
        ("`patient_stream.mapping_error_per_answer`", lambda: [ps["mapping_error_per_answer"]["a"], ps["mapping_error_per_answer"]["b"]], None),
        ("`patient_stream.mapping_error_step`", lambda: [ps["mapping_error_step"]["ordinal_options"], ps["mapping_error_step"]["stools_per_day"],
                                                        ps["mapping_error_step"]["temperature_c"]],
         lambda _: ps["mapping_error_step"]["yes_no"] == "flip"),
        ("`calibration`", lambda: [p["calibration"]["r_null"], p["calibration"]["r_validation"], p["calibration"]["r_quick"]], None),
        ("`grid`", lambda: [*p["grid"]["n_sites"], *p["grid"]["patients_per_site"], *p["grid"]["f"], *p["grid"]["mu"],
                            p["grid"]["reps"], p["grid"]["reps_quick"]], None),
        ("`failure_case`", lambda: [p["failure_case"]["between_site_sd_logit"], p["failure_case"]["casemix_sd_log"]], None),
        ("`sensitivity`", lambda: [], lambda _: list(p["sensitivity"]["scenarios"]) == [f"SE{k}" for k in range(1, 22)]),
        ("`comparators`", lambda: [p["comparators"]["rate_kri"]["min_days"], p["comparators"]["simaerep_classic"]["r"]],
         lambda _: p["comparators"]["rate_kri"]["exposure"] == "patient_days" and p["comparators"]["simaerep_classic"]["visit_med75"] is True
         and p["comparators"]["simaerep_classic"]["bh"] is True and "ae_report_ratio" in p["comparators"]),
        ("`blind_run`", lambda: [p["blind_run"]["planted_count"]["min"], p["blind_run"]["planted_count"]["max"],
                                 len(p["blind_run"]["precomputed_labels"])],
         lambda _: p["blind_run"]["f_from"] == "planted.gross.f" and "demo-42" not in p["blind_run"]["precomputed_labels"]
         and len(set(p["blind_run"]["precomputed_labels"])) == len(p["blind_run"]["precomputed_labels"])),
        ("`signal_rules_sha256`", lambda: [], None),
        ("`frozen_inputs`", lambda: [], None),
        ("`seeds`", lambda: [p["seeds"]["dev"]], lambda _: p["seeds"]["eval"] == "derived_from_sap_v1_tag_and_beacon"
         and p["seeds"]["beacon"]["file"] == "monitoring/seed_beacon.json"),
        ("Provenance", lambda: [], lambda _: p["provenance"]["record_versions"] == ["numpy", "scipy"]),
    ]


def checks_11_4(p: dict[str, Any]) -> dict[str, tuple[str, list[float]]]:
    """SAP label cell -> (params planted key, mechanism numbers in SAP order)."""
    pl = p["planted"]
    return {
        "`gross_under`": ("gross", []),
        "`under_50` (**masked**)": ("under_50", [pl["under_50"]["f"], pl["under_50"]["casemix"]]),
        "`under_25`": ("under_25", [pl["under_25"]["f"]]),
        "`language_gap`": ("language_gap", [pl["language_gap"]["spanish_share"], pl["language_gap"]["spanish_capture_odds_ratio"],
                                            pl["language_gap"]["spanish_capture_odds_ratio"]]),
        "`decoy_healthy_casemix`": ("decoy_healthy_casemix", [pl["decoy_healthy_casemix"]["casemix"]]),
        "`honest_low_diligence`": ("honest_low_diligence", [pl["honest_low_diligence"]["u_s_between_site_sds"],
                                                            p["site_capture"]["between_site_sd_logit"]]),
        "`low_coverage`": ("low_coverage", [pl["low_coverage"]["call_completion_mean"]]),
        "`small_site`": ("small_site", [pl["small_site"]["patients"]]),
        "`honest`": ("honest", []),
    }


def compare(root: Path = ROOT) -> list[Row]:
    text = (root / SAP).read_text(encoding="utf-8")
    p = yaml.safe_load((root / PARAMS).read_text(encoding="utf-8"))
    out: list[Row] = []
    t113 = table_rows(section(text, "11.3"))
    seen = set()
    for key, expect, extra in checks_11_3(p):
        if key not in t113:
            out.append(Row("11.3", key, "(row missing in SAP)", "", False))
            continue
        seen.add(key)
        cell = t113[key][0]
        sap_nums, par_nums = numbers(cell), [float(x) for x in expect()]
        ok = _same(sap_nums, par_nums) and (extra is None or bool(extra(cell)))
        out.append(Row("11.3", key, _fmt(sap_nums) if sap_nums else cell[:60], _fmt(par_nums) if par_nums else "(text check)", ok))
    for key in t113:
        if key not in seen and key != "`params.yaml` key":
            out.append(Row("11.3", key, "(SAP row without a check)", "", False))
    # signal_rules_sha256 and frozen_inputs: values must match the files (bvsignal.seed is the one implementation)
    sys.path.insert(0, str(root / "monitoring"))
    from bvsignal import seed as bvseed

    sig_ok = str(p["signal_rules_sha256"]) == bvseed.signal_rules_sha256(root)
    out.append(Row("11.3", "signal_rules_sha256 value", "sha256(data/signal_rules.json)", str(p["signal_rules_sha256"])[:16] + "...", sig_ok))
    fz_ok, report = bvseed.check_frozen(root)
    out.append(Row("11.3", "frozen_inputs values", "recomputed", "; ".join(r.split()[1] for r in report if r.split()[1] in bvseed.FROZEN_KEYS), fz_ok))
    # §11.4 planted truth
    t114 = table_rows(section(text, "11.4"))
    for label, (pkey, nums) in checks_11_4(p).items():
        if label not in t114:
            out.append(Row("11.4", label, "(row missing in SAP)", "", False))
            continue
        count_cell, mech = t114[label][0], t114[label][1]
        spec = p["planted"][pkey]
        sap_count = count_cell.lower()
        par_count = str(spec["count"]).lower()
        sap_nums = numbers(mech)
        ok = sap_count == par_count and _same(sap_nums, [float(x) for x in nums]) and spec["label"] == label.split("`")[1]
        out.append(Row("11.4", label.split("`")[1], f"count {count_cell}; {_fmt(sap_nums)}", f"count {spec['count']}; {_fmt([float(x) for x in nums])}", ok))
    n_planted = sum(int(s["count"]) for s in p["planted"].values() if s["count"] != "rest")
    out.append(Row("11.4", "planted sites fit", f"<= {p['design']['n_sites'] - 1} non-live sites", str(n_planted), n_planted <= p["design"]["n_sites"] - 1))
    # §11.5 values filled at tag time
    t115 = table_rows(section(text, "11.5"))
    grid = json.loads((root / GRID).read_text(encoding="utf-8")) if (root / GRID).exists() else None
    chosen = (grid or {}).get("chosen", {})
    pps = t115.get("`design.patients_per_site`", ["", ""])
    m = re.search(r"(\d+)\s*[–-]\s*(\d+)", pps[0])
    sap_pps = [int(m.group(1)), int(m.group(2))] if m else None
    out.append(Row("11.5", "design.patients_per_site", f"{sap_pps} ({pps[1].split()[0] if pps[1] else '?'})",
                   f"{p['design']['patients_per_site']} (grid {chosen.get('patients_per_site')}, {chosen.get('p1')})",
                   sap_pps is not None and sap_pps == list(p["design"]["patients_per_site"] or []) == chosen.get("patients_per_site")
                   and pps[1].split()[0].strip("*_:;,.") == chosen.get("p1")))
    gf = t115.get("`planted.gross.f`", ["", ""])
    sap_f = numbers(gf[0])
    out.append(Row("11.5", "planted.gross.f", f"{_fmt(sap_f)} ({gf[1].split()[0] if gf[1] else '?'})",
                   f"{p['planted']['gross']['f']} (grid {chosen.get('gross_f')}, {chosen.get('p2')})",
                   len(sap_f) == 1 and p["planted"]["gross"]["f"] is not None and math.isclose(sap_f[0], p["planted"]["gross"]["f"])
                   and chosen.get("gross_f") is not None and math.isclose(sap_f[0], chosen["gross_f"])
                   and gf[1].split()[0].strip("*_:;,.") == chosen.get("p2")))
    return out


def main() -> int:
    rows = compare(ROOT)
    w = max(len(r.key) for r in rows)
    print(f"params.yaml vs {SAP} (§11.3 parameter table, §11.4 planted truth, §11.5 tag-time values)")
    for r in rows:
        print(f"{'ok ' if r.ok else 'BAD'}  §{r.section:<4} {r.key:<{w}}  SAP {r.sap}  |  params {r.params}")
    bad = [r for r in rows if not r.ok]
    print(f"{len(rows) - len(bad)}/{len(rows)} rows agree" + ("" if not bad else f"; {len(bad)} disagree"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
