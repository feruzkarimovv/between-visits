#!/usr/bin/env python3
"""Fill the Site Signal number tokens in the story documents (WS4 D13-D16). Standard library only.

No Site Signal number is ever typed into WHAT_IT_GETS_WRONG.md, README.md, docs/pitch/deck.html or the
docs/08 storyboard. Each one is written as a token, double curly braces around

    ss:<file>:<json path>:<format>

and this script replaces every token with the value read from the source file, rounded for display by
docs/11 §15 rule 6. Values are stored unrounded in the JSON files; rounding happens only here.

<file>       summary      validation/site_signal/summary.json   (S7, docs/11 §12.9)
             signal_run   monitoring/out/signal_run.json        (S6, committed evaluation study)
             answer_key   monitoring/out/answer_key.json        (S6)
             equity       monitoring/out/equity.json            (S9)
             thresholds   monitoring/out/thresholds.json        (S4/S6)
             derived      computed here from summary + thresholds + data/signal_rules.json, docs/11 §12.1:
                          req023.{look,watch}.{rate,se_val,se_cal,nominal,bound,outcome}, size.{outcome,tolerance}
             With --source DIR every file is read from DIR/<file>.json instead (e.g. the B16b fixtures).

<json path>  jq-like: `.a.b[0].c`; a list element selected by its fields: `power[indicator=discordance,tier=watch,
             f=0.25]` (the filter must match exactly one element; true/false/null and numbers are typed, anything
             else is a string). `A // B` is jq's alternative operator: B is tried only when A does not exist
             (an ambiguous A is an error, never a fall-through), and the provenance table names the path used.

<format>     p2    proportion, 2 decimals            0.23    (must lie in [0, 1])
             pct2  proportion, 2 decimals, as %      23%     (must lie in [0, 1])
             f1    1 decimal (E, V, expected counts) 1.4
             f2    2 decimals (z, O/E, odds ratios)  0.81
             f3    3 decimals (MC SE, CI limits)     0.011
             ci3   [lo, hi] pair, 3 decimals         [0.012, 0.034]
             int   integer (counts, seeds)           14
             text  a string value verbatim           met
             Rounding is half-up on the shortest decimal repr of the stored float; -0 prints as 0.

Usage:
    python3 validation/render_numbers.py --in-place WHAT_IT_GETS_WRONG.md README.md docs/pitch/deck.html \
        docs/08-demo-and-pitch.md                                   # after S7: real sources, files rewritten
    python3 validation/render_numbers.py --source backend/tests/fixtures/site_signal --out "$TMPDIR/rendered" \
        WHAT_IT_GETS_WRONG.md README.md docs/pitch/deck.html docs/08-demo-and-pitch.md   # dry run, copies only
    python3 validation/render_numbers.py --check "$TMPDIR/rendered"/*     # no token left; provenance re-read
    python3 validation/render_numbers.py --list FILES...                  # print the tokens, resolve nothing

Rendering fails loudly (exit 1, nothing written) on a missing file, a missing or ambiguous path, a value of the
wrong type for its format, or a malformed token, and lists every failure. A rendered run writes a provenance
table (document, line, value, source file, JSON path, format) between the `ss-provenance` markers at the foot of
WHAT_IT_GETS_WRONG.md (printed to stdout when no given file has the markers). `--check` fails on any token left,
re-reads every provenance row from the file and path it names, and fails when the digits differ or are not on the
listed line. Never commit numbers rendered from the fixtures: render them into a scratch directory only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SIGNAL_RULES = ROOT / "data" / "signal_rules.json"
DEFAULT_PATHS = {
    "summary": ROOT / "validation" / "site_signal" / "summary.json",
    "signal_run": ROOT / "monitoring" / "out" / "signal_run.json",
    "answer_key": ROOT / "monitoring" / "out" / "answer_key.json",
    "equity": ROOT / "monitoring" / "out" / "equity.json",
    "thresholds": ROOT / "monitoring" / "out" / "thresholds.json",
}
FILES = (*DEFAULT_PATHS, "derived")
# docs/11 §12.1 size calibration: every E_s tertile's unrounded Look rate within the nominal rate ± this tolerance.
SIZE_TOLERANCE = 0.02

TOKEN_RE = re.compile(r"\{\{ss:([^{}]*)\}\}")
LEFTOVER_RE = re.compile(r"\{\{\s*ss:")
PROV_START = "<!-- ss-provenance:start -->"
PROV_END = "<!-- ss-provenance:end -->"
PROV_ROW_RE = re.compile(
    r"^\| (\d+) \| `([^`]+)`:(\d+) \| `([^`]*)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \|$"
)
SEGMENT_RE = re.compile(r"\.?([A-Za-z_][A-Za-z0-9_]*)|\[(-?\d+)\]|\[([^\[\]]+)\]")


class RenderError(Exception):
    """Fatal for the token: reported, and nothing is written."""


class Missing(RenderError):
    """The path does not exist in the source; the next `//` alternative is tried."""


# ---------------------------------------------------------------------------------------------------- paths


def parse_path(path: str) -> list[tuple[str, Any]]:
    """`a.b[0][k=v,k2=v2]` -> [("key","a"), ("key","b"), ("index",0), ("filter",[("k","v"),...])]."""
    path = path.strip()
    if not path or path == ".":
        raise RenderError("empty path")
    out: list[tuple[str, Any]] = []
    pos = 0
    while pos < len(path):
        m = SEGMENT_RE.match(path, pos)
        if not m or m.end() == pos:
            raise RenderError(f"cannot parse path at {path[pos:]!r}")
        if m.group(1) is not None:
            if out and path[pos] != ".":
                raise RenderError(f"missing '.' before {m.group(1)!r}")
            out.append(("key", m.group(1)))
        elif m.group(2) is not None:
            out.append(("index", int(m.group(2))))
        else:
            conds = []
            for part in m.group(3).split(","):
                if "=" not in part:
                    raise RenderError(f"filter term {part!r} is not key=value")
                k, v = part.split("=", 1)
                conds.append((k.strip(), typed(v.strip())))
            out.append(("filter", conds))
        pos = m.end()
    return out


def typed(raw: str) -> Any:
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "null":
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def same(actual: Any, wanted: Any) -> bool:
    if isinstance(wanted, bool) or wanted is None:
        return actual is wanted
    if isinstance(wanted, (int, float)):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and float(actual) == float(wanted)
    return isinstance(actual, str) and actual == wanted


def walk(doc: Any, path: str) -> Any:
    cur = doc
    for kind, arg in parse_path(path):
        if kind == "key":
            if not isinstance(cur, dict) or arg not in cur:
                raise Missing(f"no key {arg!r}")
            cur = cur[arg]
        elif kind == "index":
            if not isinstance(cur, list) or not -len(cur) <= arg < len(cur):
                raise Missing(f"no index [{arg}]")
            cur = cur[arg]
        else:
            if not isinstance(cur, list):
                raise Missing("filter applied to a non-list")
            hits = [el for el in cur if isinstance(el, dict) and all(k in el and same(el[k], v) for k, v in arg)]
            label = ",".join(f"{k}={v}" for k, v in arg)
            if not hits:
                raise Missing(f"no element matches [{label}]")
            if len(hits) > 1:
                raise RenderError(f"{len(hits)} elements match [{label}] (must be exactly 1)")
            cur = hits[0]
    return cur


def resolve(doc: Any, path: str) -> tuple[Any, str, bool]:
    """Value, the alternative actually used, and whether it was a fallback (not the first alternative)."""
    alternatives = [a.strip() for a in path.split("//")]
    misses = []
    for i, alt in enumerate(alternatives):
        try:
            return walk(doc, alt), alt, i > 0
        except Missing as exc:
            misses.append(f"{alt}: {exc}")
    raise RenderError("missing path; " + "; ".join(misses))


# ---------------------------------------------------------------------------------------------------- formats


def _dec(x: Any, what: str) -> Decimal:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise RenderError(f"{what} needs a number, got {type(x).__name__} {x!r}")
    if isinstance(x, float) and not math.isfinite(x):
        raise RenderError(f"{what} needs a finite number, got {x!r}")
    return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


def _round(x: Any, places: int, what: str) -> Decimal:
    d = _dec(x, what).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return abs(d) if d == 0 else d


def _proportion(x: Any, what: str) -> Any:
    if not 0 <= _dec(x, what) <= 1:
        raise RenderError(f"{what} needs a proportion in [0, 1], got {x!r}")
    return x


def _int(x: Any) -> str:
    d = _dec(x, "int")
    if d != d.to_integral_value():
        raise RenderError(f"int needs an integral value, got {x!r}")
    return str(int(d))


def _ci3(x: Any) -> str:
    if not isinstance(x, list) or len(x) != 2:
        raise RenderError(f"ci3 needs a [lo, hi] pair, got {x!r}")
    return f"[{_round(x[0], 3, 'ci3')}, {_round(x[1], 3, 'ci3')}]"


def _text(x: Any) -> str:
    if not isinstance(x, str):
        raise RenderError(f"text needs a string, got {type(x).__name__} {x!r}")
    return x


FORMATS: dict[str, Callable[[Any], str]] = {
    "p2": lambda x: str(_round(_proportion(x, "p2"), 2, "p2")),
    "pct2": lambda x: f"{(_round(_proportion(x, 'pct2'), 2, 'pct2') * 100).quantize(Decimal(1))}%",
    "f1": lambda x: str(_round(x, 1, "f1")),
    "f2": lambda x: str(_round(x, 2, "f2")),
    "f3": lambda x: str(_round(x, 3, "f3")),
    "ci3": _ci3,
    "int": _int,
    "text": _text,
}


# ---------------------------------------------------------------------------------------------------- sources


class Sources:
    def __init__(self, source_dir: Path | None) -> None:
        self.source_dir = source_dir
        self._cache: dict[str, Any] = {}

    def path_of(self, name: str) -> Path:
        if self.source_dir is not None:
            return self.source_dir / f"{name}.json"
        return DEFAULT_PATHS[name]

    def label(self, name: str) -> str:
        if name == "derived":
            return "derived (docs/11 §12.1)"
        return rel(self.path_of(name))

    def get(self, name: str) -> Any:
        if name not in self._cache:
            if name == "derived":
                self._cache[name] = self._derive()
            else:
                p = self.path_of(name)
                if not p.is_file():
                    raise RenderError(f"source file {rel(p)} does not exist")
                try:
                    self._cache[name] = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise RenderError(f"source file {rel(p)} is not valid JSON: {exc}") from exc
        return self._cache[name]

    def _derive(self) -> dict[str, Any]:
        """docs/11 §12.1: REQ-023 bounds and outcomes, and the size-calibration check, on unrounded values."""
        summary, thresholds = self.get("summary"), self.get("thresholds")
        tiers = json.loads(SIGNAL_RULES.read_text(encoding="utf-8"))["tiers"]
        req: dict[str, Any] = {}
        for tier, null_key, nominal in (
            ("look", "null.look_per_site", tiers["look"]["per_site_alpha"]),
            ("watch", "null.watch_fwer", tiers["watch"]["family_wise_alpha"]),
        ):
            rate = float(_dec(walk(summary, f"{null_key}.rate"), "rate"))
            se_val = float(_dec(walk(summary, f"{null_key}.mc_se"), "mc_se"))
            se_cal = float(_dec(walk(thresholds, f"achieved.discordance.{tier}.mc_se"), "mc_se"))
            bound = nominal + 2 * math.sqrt(se_cal**2 + se_val**2)
            if rate > bound:
                outcome = "not met"
            elif rate < nominal:
                outcome = "met (conservative: below the nominal rate)"
            else:
                outcome = "met"
            req[tier] = {"rate": rate, "se_val": se_val, "se_cal": se_cal, "nominal": nominal, "bound": bound,
                         "outcome": outcome}
        nominal = tiers["look"]["per_site_alpha"]
        off = [row for row in walk(summary, "null.look_per_site_by_e_tertile")
               if abs(float(_dec(row["rate"], "rate")) - nominal) > SIZE_TOLERANCE]
        size = "met" if not off else "not met (E tertile " + ", ".join(
            f"{row['tertile']}: {_round(row['rate'], 2, 'p2')}" for row in off) + ")"
        return {"req023": req, "size": {"outcome": size, "tolerance": SIZE_TOLERANCE}}


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------------------------------- render


@dataclass
class Rendered:
    doc: str
    line: int
    value: str
    source: str
    path: str
    fmt: str
    fallback: bool


def split_token(inner: str) -> tuple[str, str, str]:
    if ":" not in inner:
        raise RenderError("token is not ss:<file>:<path>:<format>")
    name, rest = inner.split(":", 1)
    if ":" not in rest:
        raise RenderError("token is not ss:<file>:<path>:<format>")
    path, fmt = rest.rsplit(":", 1)
    name, path, fmt = name.strip(), path.strip(), fmt.strip()
    if name not in FILES:
        raise RenderError(f"unknown file {name!r} (one of {', '.join(FILES)})")
    if fmt not in FORMATS:
        raise RenderError(f"unknown format {fmt!r} (one of {', '.join(FORMATS)})")
    return name, path, fmt


def tokens_in(text: str) -> list[tuple[int, re.Match[str]]]:
    return [(text.count("\n", 0, m.start()) + 1, m) for m in TOKEN_RE.finditer(text)]


def render_text(doc: str, text: str, sources: Sources, rows: list[Rendered], errors: list[str]) -> str:
    def repl(m: re.Match[str]) -> str:
        line = text.count("\n", 0, m.start()) + 1
        try:
            name, path, fmt = split_token(m.group(1))
            value, used, fallback = resolve(sources.get(name), path)
            shown = FORMATS[fmt](value)
        except RenderError as exc:
            errors.append(f"{doc}:{line}: {m.group(0)}: {exc}")
            return m.group(0)
        rows.append(Rendered(doc, line, shown, sources.label(name), used, fmt, fallback))
        return shown

    return TOKEN_RE.sub(repl, text)


def provenance_block(rows: list[Rendered], sources: Sources) -> str:
    about = ""
    try:
        summary = sources.get("summary")
        meta = {k: summary.get(k) for k in ("sap_tag_commit", "eval_seed", "code_commit", "generated_at")}
        about = ", ".join(f"`{k}` {v}" for k, v in meta.items())
        if summary.get("_about"):
            about += f"; `_about`: {summary['_about']}"
    except RenderError:
        about = "summary.json not read"
    where = rel(sources.source_dir) if sources.source_dir else "validation/site_signal/ and monitoring/out/"
    lines = [
        PROV_START,
        (f"Rendered by `validation/render_numbers.py` from `{where}` ({about}). {len(rows)} values, every one "
         "SIMULATED. The path column is the path actually read; a path after `//` in the token was a fallback."),
        "",
        "| # | Where | Value | Source file | JSON path | Format | Used |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | `{r.doc}`:{r.line} | `{r.value}` | `{r.source}` | `{r.path.replace('|', '/')}` "
                     f"| `{r.fmt}` | `{'fallback' if r.fallback else 'first'}` |")
    lines.append(PROV_END)
    return "\n".join(lines)


def insert_provenance(text: str, block: str) -> str | None:
    start, end = text.find(PROV_START), text.find(PROV_END)
    if start < 0 or end < start:
        return None
    return text[:start] + block + text[end + len(PROV_END):]


def cmd_render(files: list[Path], sources: Sources, out_dir: Path | None, in_place: bool) -> int:
    texts = {f: f.read_text(encoding="utf-8") for f in files}
    names = [f.name for f in files]
    if out_dir is not None and len(set(names)) != len(names):
        print("render: two input files share a name; --out writes them flat", file=sys.stderr)
        return 2
    rows: list[Rendered] = []
    errors: list[str] = []
    rendered = {f: render_text(f.name, t, sources, rows, errors) for f, t in texts.items()}
    if errors:
        print(f"render: {len(errors)} token(s) failed, nothing written:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    block = provenance_block(rows, sources)
    placed = False
    for f in files:
        with_prov = insert_provenance(rendered[f], block) if rows else None  # no token: keep the existing table
        if with_prov is not None:
            rendered[f], placed = with_prov, True
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        target = f if in_place else out_dir / f.name  # type: ignore[operator]
        target.write_text(rendered[f], encoding="utf-8")
    per_doc: dict[str, int] = {}
    for r in rows:
        per_doc[r.doc] = per_doc.get(r.doc, 0) + 1
    print(f"render: {len(rows)} tokens in {len(files)} files ("
          + ", ".join(f"{d} {n}" for d, n in per_doc.items()) + ")"
          + f" -> {'in place' if in_place else out_dir}")
    fallbacks = [r for r in rows if r.fallback]
    if fallbacks:
        where = sorted({f"{r.doc}:{r.line}" for r in fallbacks}, key=lambda w: (w.split(":")[0], int(w.split(":")[1])))
        print(f"render: {len(fallbacks)} tokens read their `//` fallback path (the first path is missing in this "
              f"source; Used column = fallback) at {', '.join(where)}")
    if not rows:
        print("render: no token found; files copied unchanged, provenance table left as it was")
    elif not placed:
        print("render: no file has the ss-provenance markers; provenance table follows")
        print(block)
    return 0


# ---------------------------------------------------------------------------------------------------- check


def _abs(source: str) -> Path:
    p = Path(source)
    return p if p.is_absolute() else ROOT / p


def cmd_check(files: list[Path]) -> int:
    """No token left; every provenance row is re-read from the file it names and must give the same digits."""
    problems: list[str] = []
    texts = {f.name: f.read_text(encoding="utf-8") for f in files}
    for name, text in texts.items():
        for i, line in enumerate(text.splitlines(), 1):
            if LEFTOVER_RE.search(line):
                problems.append(f"{name}:{i}: token left: {line.strip()[:120]}")
    prov: list[tuple[str, int, str, str, str, str, str]] = []
    for text in texts.values():
        start, end = text.find(PROV_START), text.find(PROV_END)
        if start >= 0 and end > start:
            for line in text[start:end].splitlines():
                m = PROV_ROW_RE.match(line.strip())
                if m:
                    prov.append((m.group(2), int(m.group(3)), m.group(4), m.group(5), m.group(6), m.group(7),
                                 m.group(8)))
    if not prov:
        problems.append("no provenance rows found (include the rendered WHAT_IT_GETS_WRONG.md)")
    summary_dir = next((_abs(r[3]).parent for r in prov if r[3].endswith("summary.json")), None)
    derived_sources = Sources(None if summary_dir in (None, DEFAULT_PATHS["summary"].parent) else summary_dir)
    loaded: dict[str, Any] = {}
    for doc, line, value, source, path, fmt, used in prov:
        print(f"{value:>12}  {doc}:{line}  <- {source} {path} ({fmt}{', fallback' if used == 'fallback' else ''})")
        if doc in texts:
            lines = texts[doc].splitlines()
            if not (0 < line <= len(lines) and value in lines[line - 1]):
                problems.append(f"{doc}:{line}: rendered value {value!r} not found on that line")
        try:
            if source.startswith("derived"):
                doc_json = derived_sources.get("derived")
            else:
                if source not in loaded:
                    src = _abs(source)
                    if not src.is_file():
                        raise RenderError(f"source file {source} does not exist")
                    loaded[source] = json.loads(src.read_text(encoding="utf-8"))
                doc_json = loaded[source]
            again = FORMATS[fmt](walk(doc_json, path))
            if again != value:
                problems.append(f"{doc}:{line}: {path} reads {again!r} now, the document says {value!r}")
        except RenderError as exc:
            problems.append(f"{doc}:{line}: {path}: {exc}")
    if problems:
        print(f"check: FAIL ({len(problems)} problem(s))", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"check: OK, 0 tokens left in {len(files)} files; {len(prov)} rendered values listed with their source path "
          "and re-read from it")
    return 0


def cmd_list(files: list[Path]) -> int:
    bad = 0
    for f in files:
        for line, m in tokens_in(f.read_text(encoding="utf-8")):
            try:
                name, path, fmt = split_token(m.group(1))
                for alt in path.split("//"):
                    parse_path(alt)
                print(f"{f.name}:{line}  {name}  {path}  {fmt}")
            except RenderError as exc:
                bad += 1
                print(f"{f.name}:{line}  MALFORMED {m.group(0)}: {exc}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--source", type=Path, help="read every source file from DIR/<file>.json (e.g. the fixtures)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--out", type=Path, help="write rendered copies into this directory (flat, by file name)")
    mode.add_argument("--in-place", action="store_true", help="overwrite the given files")
    mode.add_argument("--check", action="store_true", help="no token left; list the provenance rows")
    mode.add_argument("--list", action="store_true", help="print every token; resolve nothing")
    args = ap.parse_args(argv)
    missing = [str(f) for f in args.files if not f.is_file()]
    if missing:
        print(f"render: no such file: {', '.join(missing)}", file=sys.stderr)
        return 2
    sources = Sources(args.source.resolve() if args.source else None)
    if args.list:
        return cmd_list(args.files)
    if args.check:
        return cmd_check(args.files)
    if args.out is None and not args.in_place:
        ap.error("give --out DIR, --in-place, --check or --list")
    return cmd_render(args.files, sources, args.out, args.in_place)


if __name__ == "__main__":
    sys.exit(main())
