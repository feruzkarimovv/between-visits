"""Mutation probe for the grade-band boundary tests (WS4-D9). Run from the repository root:

    uv run --project backend python data/mutation_probe.py

Copies data/ to temp directories outside the repository and, one copy per mutant, shifts one numeric threshold
of the rules DSL by one unit, down or up. Thresholds are the gte/gt/lte/lt operands in data/ctcae_rules.json
(rules[].when) and data/red_flags.json (red_flags[].rule), the two files written in the condition DSL
(docs/05 §4); one unit is the precision the threshold is written with (7 -> 1, 39.0 -> 0.1). Each copy runs
backend/tests/test_rule_boundaries.py with BV_DATA_UNDER_TEST pointing the rules engine at it; a mutant is
killed when the boundary tests fail. The expected edges in those tests always come from the repository's data/,
so a kill means the tests pin that threshold to its committed value.

Prints one line per mutant and `killed N/N`. Exit 0 only when an unmodified copy passes the tests and every
mutant is killed. The repository's data/ is never written (checked before exit).
"""
import hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKEND = ROOT / "backend"
TESTS = "tests/test_rule_boundaries.py"
DSL_FILES = (("ctcae_rules.json", "rules", "when"), ("red_flags.json", "red_flags", "rule"))
CMP = ("gte", "gt", "lte", "lt")


def unit(t) -> Decimal:
    """One unit at the precision the threshold is written with: 7 -> 1, 39.0 -> 0.1."""
    return Decimal(1) if isinstance(t, int) else Decimal(1).scaleb(t.as_tuple().exponent)


def _walk(node, path):
    """(path, value) for every numeric gte/gt/lte/lt operand under a condition."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in CMP and isinstance(v, (int, Decimal)) and not isinstance(v, bool):
                yield (*path, k), v
            elif isinstance(v, (dict, list)):
                yield from _walk(v, (*path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, (*path, i))


def _label(path) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")


def mutants() -> list[dict]:
    """Two mutants (one unit down, one unit up) per numeric threshold, in file order."""
    out = []
    for name, list_key, cond_key in DSL_FILES:
        doc = json.loads((DATA / name).read_text(encoding="utf-8"), parse_float=Decimal)
        for i, entry in enumerate(doc[list_key]):
            for path, value in _walk(entry.get(cond_key), (list_key, i, cond_key)):
                for sign in (-1, 1):
                    new = value + sign * unit(value)
                    out.append({"file": name, "path": path, "old": value, "new": new,
                                "label": f"{name} {entry['id']} {_label(path[2:])} {value} -> {new}"})
    return out


def _set(doc, path, value) -> None:
    for p in path[:-1]:
        doc = doc[p]
    doc[path[-1]] = value


def make_copy(dest: pathlib.Path, mutant: dict | None) -> pathlib.Path:
    """A copy of data/ at dest/data with the mutant applied (unmodified when mutant is None)."""
    d = dest / "data"
    shutil.copytree(DATA, d, ignore=shutil.ignore_patterns("local", "*.local.json", "__pycache__", "*.py"))
    if mutant:
        p = d / mutant["file"]
        doc = json.loads(p.read_text(encoding="utf-8"))
        new = mutant["new"]
        _set(doc, mutant["path"], int(new) if isinstance(mutant["old"], int) else float(new))
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        check = json.loads(p.read_text(encoding="utf-8"), parse_float=Decimal)
        for k in mutant["path"]:
            check = check[k]
        if check != new:
            raise RuntimeError(f"mutant not applied: {mutant['label']} (copy holds {check})")
    return d


def run_tests(data_dir: pathlib.Path) -> tuple[str, str]:
    """Run the boundary tests with the rules engine on data_dir: passed, failed, or error (anything else)."""
    env = {**os.environ, "BV_DATA_UNDER_TEST": str(data_dir), "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", TESTS],
                       cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    if p.returncode == 0:
        return "passed", out
    if p.returncode == 1 and re.search(r"\b\d+ failed\b", out):
        return "failed", out
    return "error", out


def _digest() -> str:
    return hashlib.sha256(b"".join((DATA / name).read_bytes() for name, *_ in DSL_FILES)).hexdigest()


def main() -> int:
    before = _digest()
    ms = mutants()
    base = pathlib.Path(tempfile.mkdtemp(prefix="bv-mutation-probe-")).resolve()
    try:
        if base.is_relative_to(ROOT):
            print(f"mutation probe FAIL: temp dir {base} is inside the repository")
            return 1
        n_thresholds = len({(m["file"], m["path"]) for m in ms})
        print(f"mutation probe: {n_thresholds} numeric thresholds in {' and '.join(f for f, *_ in DSL_FILES)}, "
              f"each shifted one unit down and up = {len(ms)} mutants; temp copies of data/ under {base} "
              f"(outside the repository)")
        status, out = run_tests(make_copy(base / "baseline", None))
        if status != "passed":
            print("mutation probe FAIL: the boundary tests do not pass on an unmodified copy of data/")
            print("    " + "\n    ".join(out.strip().splitlines()[-15:]))
            return 1
        print("  baseline  unmodified copy: boundary tests pass")

        def run(i: int) -> tuple[str, str]:
            return run_tests(make_copy(base / f"m{i:02d}", ms[i]))

        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
            results = list(ex.map(run, range(len(ms))))
        killed = 0
        for m, (status, out) in zip(ms, results):
            verdict = {"failed": "killed", "passed": "SURVIVED"}.get(status, "ERROR")
            killed += verdict == "killed"
            print(f"  {verdict:<9} {m['label']}")
            if verdict != "killed":
                print("            " + "\n            ".join(out.strip().splitlines()[-8:]))
        print(f"killed {killed}/{len(ms)}")
        if _digest() != before:
            print("mutation probe FAIL: the repository's rule files changed during the run")
            return 1
        return 0 if killed == len(ms) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
