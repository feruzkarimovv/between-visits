// Display rounding of Site Signal numbers, the same rule as validation/render_numbers.py (which fills the numbers
// in WHAT_IT_GETS_WRONG.md, the README, the deck and docs/10): round half up (away from zero) on the shortest
// decimal string of the stored float, `Decimal(repr(x)).quantize(..., ROUND_HALF_UP)`, and print -0 as 0.
// Number.prototype.toFixed rounds the binary value instead, so a stored 0.745 (binary 0.74499999…) would show
// 0.74 here and 0.75 in the documents. No imports: src/lib/round.test.ts runs this file under `node --test`.

/** `v` rounded half up to `digits` decimals on its shortest decimal string, e.g. 0.745 -> "0.75", 0.0045 -> "0.005". */
export function roundHalfUp(v: number, digits: number): string {
  if (!Number.isFinite(v)) return String(v);
  const s = String(v);
  // Exponent form (|v| < 1e-6 or >= 1e21): far from any displayed tie at <= 3 decimals.
  if (/e/i.test(s)) return v.toFixed(digits);
  const negative = s.startsWith("-");
  const [intPart, fracPart = ""] = (negative ? s.slice(1) : s).split(".");
  let scaled = BigInt(intPart + fracPart.slice(0, digits).padEnd(digits, "0"));
  if (fracPart.length > digits && fracPart[digits] >= "5") scaled += BigInt(1);
  if (scaled === BigInt(0)) return (0).toFixed(digits);
  const t = scaled.toString().padStart(digits + 1, "0");
  const out = digits > 0 ? `${t.slice(0, t.length - digits)}.${t.slice(t.length - digits)}` : t;
  return negative ? `-${out}` : out;
}
