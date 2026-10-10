"""Cross-checks every clinical/seed data file. Run: uv run python data/validate_data.py (exit 1 on failure).

Checks: plan items and red flags exist; every item has EN+ES text (or a script); follow-ups and rule
conditions reference real items and scale values; scripts exist in both languages with known
placeholders and dash-written emergency numbers; tool option enum == all scale options; the agent
prompt lists every option; personas reference real flags/terms; 2x2 persona grid; no licensed content
(PRO-CTCAE claims in item text, MedDRA-style codes). WS4 owns this file; extend it, don't weaken it.
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
J = lambda p: json.loads((ROOT / p).read_text(encoding="utf-8"))
errors: list[str] = []
fail = errors.append

items = J("data/symptom_items.json"); scripts = J("data/scripts.json"); rf = J("data/red_flags.json")
rules = J("data/ctcae_rules.json"); plan = J("data/plan.json"); pats = J("data/patients.json")
tools = J("agent/tools.json"); variants = J("agent/variants.json"); personas = J("eval/personas.json")
I, scales = items["items"], items["scales"]

for c in plan["items"]:
    if c not in I: fail(f"plan item {c} missing")
rf_ids = {r["id"] for r in rf["red_flags"]}
for r in plan["red_flag_ids"]:
    if r not in rf_ids: fail(f"plan red flag {r} missing")

all_opts = {"unknown"}
for code, it in I.items():
    sc = it["scale"]
    if sc not in scales: fail(f"{code}: unknown scale {sc}"); continue
    all_opts |= set(scales[sc].get("options", []))
    if "say_script" in it:
        if it["say_script"] not in scripts["lines"]: fail(f"{code}: say_script missing")
    else:
        for l in ("en", "es"):
            if not it.get("text", {}).get(l): fail(f"{code}: text.{l} missing")
    for l in ("en", "es"):
        if "options_say" in it and not it["options_say"].get(l): fail(f"{code}: options_say.{l} missing")
    for f in it.get("followups", []):
        if f["item"] not in I: fail(f"{code}: follow-up {f['item']} missing")
        for v in f["when"]["in"]:
            if v not in scales[sc].get("options", []): fail(f"{code}: follow-up value {v} not in scale {sc}")

KNOWN_PH = {"study_team_name", "patient_first_name", "caregiver_name", "options"}
for k, v in scripts["lines"].items():
    for l in ("en", "es"):
        if not v.get(l): fail(f"script {k}.{l} missing")
        for ph in re.findall(r"\{(\w+)\}", v.get(l, "")):
            if ph not in KNOWN_PH: fail(f"script {k}: unknown placeholder {{{ph}}}")
    if re.search(r"\b911\b|\b988\b", json.dumps(v)): fail(f"script {k}: write 9-1-1 / 9-8-8")

def walk(cond, where):
    if "any" in cond or "all" in cond:
        for c in cond.get("any", []) + cond.get("all", []): walk(c, where)
    elif "item" in cond:
        it = I.get(cond["item"])
        if not it: fail(f"{where}: item {cond['item']} missing"); return
        opts = scales[it["scale"]].get("options", [])
        for v in ([cond["eq"]] if "eq" in cond else []) + cond.get("in", []):
            if v not in opts: fail(f"{where}: {cond['item']} value {v} not in scale")
    elif "derived" in cond:
        if cond["derived"] not in rules["derived_inputs"]: fail(f"{where}: unknown derived {cond['derived']}")
    else:
        fail(f"{where}: bad condition {cond}")

for r in rf["red_flags"]:
    if r["level"] not in rf["levels"]: fail(f"{r['id']}: bad level")
    if r.get("rule"): walk(r["rule"], r["id"])
    if r.get("say_script") and r["say_script"] not in scripts["lines"]: fail(f"{r['id']}: say_script missing")
    if re.search(r"\{(first_name|name|last_name)\}", r["page_phrase_en"]): fail(f"{r['id']}: page phrase must not contain names")
for ru in rules["rules"]:
    walk(ru["when"], ru["id"])
    if ru["term"] not in rules["terms"]: fail(f"{ru['id']}: term missing from catalog")

props = tools["tools"][0]["api_schema"]["request_body_schema"]["properties"]
enum = set(props["option_code"]["enum"])
if enum != all_opts: fail(f"record_answer option enum mismatch: missing {all_opts - enum}, extra {enum - all_opts}")
prompt = (ROOT / "agent/prompt.md").read_text(encoding="utf-8")
for o in sorted(all_opts):
    if f"`{o}`" not in prompt: fail(f"agent/prompt.md does not list option `{o}`")
for ph in ("${RED_FLAG_LIST}", "{{pace_instructions}}", "{{language_name}}", "{{patient_first_name}}", "{{caregiver_name}}", "{{study_team_name}}"):
    if ph not in prompt: fail(f"agent/prompt.md missing {ph}")

terms = set(rules["terms"]) | {"Chest pain"}
grid: dict = {}
for p in personas["personas"]:
    grid[(p["language"], p["pace"])] = grid.get((p["language"], p["pace"]), 0) + 1
    for f in p["expected"]["red_flags"]:
        if f not in rf_ids: fail(f"{p['id']}: unknown red flag {f}")
    for a in p["expected"]["ae"]:
        if a["term"] not in terms: fail(f"{p['id']}: unknown term {a['term']}")
if sorted(grid.values()) != [5, 5, 5, 5]: fail(f"persona grid not 5x4: {grid}")

ids = [p["id"] for p in pats["patients"]]
if len(ids) != len(set(ids)): fail("duplicate patient ids")
for p in pats["patients"]:
    if p["language"] not in ("en", "es") or p["pace"] not in ("standard", "extra_time"): fail(f"{p['id']}: bad language/pace")
    if not str(p["phone_e164"]).startswith("+1555555"): fail(f"{p['id']}: real-looking phone number in committed seed")
if set(variants["variants"]) != {"en-standard", "en-extra_time", "es-standard", "es-extra_time"}: fail("agent variants incomplete")

if "PRO-CTCAE" in json.dumps(I): fail("item text mentions PRO-CTCAE (our wording is not PRO-CTCAE)")
if re.search(r"\b10\d{6}\b", json.dumps(rules)): fail("MedDRA-style code found in ctcae_rules.json")

if errors:
    print("\n".join("FAIL: " + e for e in errors)); sys.exit(1)
print(f"data OK: {len(I)} items, {len(rf_ids)} red flags, {len(rules['rules'])} grading rules, {len(personas['personas'])} personas")
