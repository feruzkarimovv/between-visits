// Unit test of the display rounding (run: `cd frontend && npm test`, Node's built-in test runner with type stripping).
// The expected strings are what validation/render_numbers.py prints for the same stored floats.
import assert from "node:assert/strict";
import { test } from "node:test";
import { roundHalfUp } from "./round.ts";

test("ties on the shortest decimal string round half up, as render_numbers.py does", () => {
  assert.equal(roundHalfUp(0.745, 2), "0.75"); // null.look_per_study.rate; toFixed gives 0.74
  assert.equal(roundHalfUp(0.155, 2), "0.16"); // failure_case.b.null[ae_report_ratio].watch_fwer.rate; toFixed gives 0.15
  assert.equal(roundHalfUp(0.0045, 3), "0.005"); // toFixed gives 0.004
  assert.equal(roundHalfUp(15.4445, 3), "15.445");
  assert.equal(roundHalfUp(0.772, 2), "0.77"); // thresholds expected_false_look_flags_per_study
});

test("ordinary values, carries, padding and signs", () => {
  assert.equal(roundHalfUp(0.04892996108949416, 2), "0.05");
  assert.equal(roundHalfUp(0.0020840476112319204, 3), "0.002");
  assert.equal(roundHalfUp(0.996, 2), "1.00");
  assert.equal(roundHalfUp(9.995, 2), "10.00");
  assert.equal(roundHalfUp(1, 2), "1.00");
  assert.equal(roundHalfUp(0.5, 0), "1");
  assert.equal(roundHalfUp(-0.745, 2), "-0.75"); // ROUND_HALF_UP is away from zero
  assert.equal(roundHalfUp(-2.2349, 2), "-2.23");
  assert.equal(roundHalfUp(-0.001, 2), "0.00"); // -0 prints as 0
  assert.equal(roundHalfUp(0, 3), "0.000");
  assert.equal(roundHalfUp(4.5e-7, 3), "0.000"); // exponent form falls back to toFixed
});
