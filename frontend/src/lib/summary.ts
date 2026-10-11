// Readers and display formatters for the Site Signal JSON outputs served verbatim by the API
// (`GET /api/site-signal/validation` = validation/site_signal/summary.json, `GET /api/site-signal/equity` =
// monitoring/out/equity.json). The route models type only the top-level keys and pass nested blocks through
// as dicts, so every nested read here is a runtime-checked accessor: a missing or malformed value renders "—",
// never a made-up number.
//
// Rounding is for display only (docs/11 §15 rule 6): proportions 2 decimals, MC SE and CI limits 3,
// z, O/E and odds ratios 2. The JSON keeps unrounded float64 values; nothing here feeds a calculation.

export type Rec = Record<string, unknown>;

export function asRec(v: unknown): Rec | null {
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Rec) : null;
}

export function asArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

export function asNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function asStr(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

/** Nested lookup: `pick(obj, "null", "watch_fwer", "rate")`. */
export function pick(v: unknown, ...path: string[]): unknown {
  let cur: unknown = v;
  for (const key of path) {
    const r = asRec(cur);
    if (!r) return undefined;
    cur = r[key];
  }
  return cur;
}

/** `{rate, mc_se, ci95?, n?}` block of summary.json (§12.8: every simulated rate carries its MC SE). */
export interface RateSe {
  rate: number | null;
  mcSe: number | null;
  ci: [number | null, number | null] | null;
  ciMethod: string | null;
  n: number | null;
}

export function readRateSe(v: unknown): RateSe | null {
  const r = asRec(v);
  if (!r) return null;
  const ci = Array.isArray(r.ci95) && r.ci95.length === 2 ? ([asNum(r.ci95[0]), asNum(r.ci95[1])] as [number | null, number | null]) : null;
  return {
    rate: asNum(r.rate ?? r.mean),
    mcSe: asNum(r.mc_se),
    ci,
    ciMethod: asStr(r.ci95_method),
    n: asNum(r.n ?? r.n_studies),
  };
}

const DASH = "—";

function fixed(v: number | null | undefined, digits: number): string {
  return v === null || v === undefined || !Number.isFinite(v) ? DASH : v.toFixed(digits);
}

/** Proportion or per-study mean, 2 decimals (§15 rule 6). */
export function fmtProp(v: number | null | undefined): string {
  return fixed(v, 2);
}

/** MC SE, CI limit or p-value, 3 decimals (§15 rule 6). */
export function fmtSe(v: number | null | undefined): string {
  return fixed(v, 3);
}

/** z, O/E or odds ratio, 2 decimals (§15 rule 6). */
export function fmtRatio(v: number | null | undefined): string {
  return fixed(v, 2);
}

/** CI limits to 3 decimals; a null bound is unbounded (docs/03 §5.3, equity). */
export function fmtCi(ci: [number | null, number | null] | null | undefined, unboundedText = "unbounded"): string {
  if (!ci) return DASH;
  const lo = ci[0] === null ? unboundedText : fmtSe(ci[0]);
  const hi = ci[1] === null ? unboundedText : fmtSe(ci[1]);
  return `[${lo}, ${hi}]`;
}

/** Integer count as is, "—" when missing. */
export function fmtCount(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? DASH : String(v);
}

/** A design parameter (patients per site range, mu, SD) exactly as stored, e.g. "40–80". */
export function fmtParam(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => fmtParam(x)).join("–");
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  if (typeof v === "string") return v;
  return DASH;
}
