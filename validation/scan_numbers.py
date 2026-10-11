"""Full-history scan for real-looking US phone numbers (WS0 R1). Standard library only.

Reads `git log -p --all` and checks every added line, plus each commit message and each changed path, for
NANP-shaped numbers written with or without +1 and with spaces, dashes, dots or parentheses between the groups.
A match whose exchange (digits 4-6 of the 10-digit number) is 555 is ignored: that is the fictional range every
committed placeholder uses. Any other match prints the commit, the file and the last 4 digits only (never the
number), and the script exits 1. Known false positives (a digit run inside a hash, say) go in
validation/scan_numbers_allow.txt as the sha256 of the 10 matched digits, never the digits themselves.

Two kinds of added lines are not checked (validation/secret-scan.md, § Lines that are not checked):
- the digest lines of that allowlist (a hex digest has digit runs of its own); its comments are checked;
- every added line of a lockfile, chosen by path: a file named `uv.lock` or `package-lock.json`, or any `*.lock`.
  Package managers write these from registry metadata (names, versions, URLs, sha256/sha512 hashes). Their hash
  digit runs are number-shaped false positives that change with every re-lock. A lockfile's path is still checked,
  and gitleaks still scans its content.

gitleaks stays the primary check; `make secret-scan` runs gitleaks first, then this script.

    python3 validation/scan_numbers.py                  # scan this repository (all refs); exit 0 no hits, 1 hits, 2 error
    python3 validation/scan_numbers.py --self-test      # scratch clone under $TMPDIR with generated non-555 numbers
    python3 validation/scan_numbers.py --suggest-allow  # allowlist lines for the current hits, after reviewing each one
"""

from __future__ import annotations

import argparse
import hashlib
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW_REL = "validation/scan_numbers_allow.txt"
DEFAULT_ALLOW = ROOT / ALLOW_REL

# The pattern from docs/workstreams/WS0-readiness.md R1, unchanged.
NUMBER_RE = re.compile(r"(?<![0-9])(?:\+?1[ .-]?)?\(?[2-9][0-9]{2}\)?[ .-]?[2-9][0-9]{2}[ .-]?[0-9]{4}(?![0-9])")
FICTIONAL_EXCHANGE = "555"
# Lockfiles, matched on the file name in any directory (validation/secret-scan.md). `agents.lock.json` is not one.
LOCKFILE_NAMES = frozenset({"uv.lock", "package-lock.json"})
LOCKFILE_SUFFIX = ".lock"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUMMARY_RE = re.compile(r"^numbers: (\d+) hits? \(.*; (\d+) allowlisted\)$", re.M)  # parsed by the self-test

# Record markers for `git log --format`; a NUL byte never starts a line of patch text.
COMMIT_MARK = "\x00bv-commit "
MESSAGE_END = "\x00bv-message-end"
LOG_FORMAT = "--format=%x00bv-commit %H%n%B%n%x00bv-message-end"
MESSAGE = "(commit message)"


def national_digits(match: str) -> str:
    """Separators stripped; a leading country code 1 dropped, so the result is the 10-digit national number."""
    digits = re.sub(r"[^0-9]", "", match)
    return digits[1:] if len(digits) == 11 else digits


def is_lockfile(path: str) -> bool:
    """A package-manager lockfile, by file name: `uv.lock`, `package-lock.json` or any `*.lock`."""
    name = path.rsplit("/", 1)[-1]
    return name in LOCKFILE_NAMES or name.endswith(LOCKFILE_SUFFIX)


def digest(digits: str) -> str:
    return hashlib.sha256(digits.encode()).hexdigest()


def redact(text: str) -> str:
    """For printing a path or label: every number-shaped run becomes its last 4 digits."""
    return NUMBER_RE.sub(lambda m: f"[...{national_digits(m.group(0))[-4:]}]", text)


def load_allow(path: Path) -> set[str]:
    if not path.exists():
        return set()
    allowed: set[str] = set()
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if not SHA256_RE.match(line):
            raise ValueError(f"{path.name}:{n}: expected a 64-character sha256 hex digest")
        allowed.add(line)
    return allowed


def git_log_lines(repo: Path) -> Iterator[str]:
    cmd = [
        "git", "-c", "core.quotepath=off", "log", "-p", "--all", "--no-color", "--no-ext-diff", "--no-textconv",
        "--src-prefix=a/", "--dst-prefix=b/", LOG_FORMAT,
    ]
    proc = subprocess.Popen(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None and proc.stderr is not None
    for raw in proc.stdout:
        yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
    err = proc.stderr.read().decode("utf-8", errors="replace").strip()
    if proc.wait() != 0:
        raise RuntimeError(f"git log failed in {repo}: {err or 'no message'}")


class Scan:
    def __init__(self, allow: set[str]) -> None:
        self.allow = allow
        self.hits: dict[tuple[str, str, str], None] = {}  # (commit, file, digits), insertion-ordered
        self.commits = 0
        self.added_lines = 0
        self.lockfile_lines = 0  # added lines of lockfiles, not checked
        self.fictional = 0
        self.allowlisted = 0

    def check(self, text: str, commit: str, where: str) -> None:
        for m in NUMBER_RE.finditer(text):
            digits = national_digits(m.group(0))
            if digits[3:6] == FICTIONAL_EXCHANGE:
                self.fictional += 1
            elif digest(digits) in self.allow:
                self.allowlisted += 1
            else:
                self.hits.setdefault((commit, where, digits), None)

    def run(self, lines: Iterator[str]) -> None:
        commit, path, in_message, in_header = "", "", False, False
        for line in lines:
            if line.startswith(COMMIT_MARK):
                commit, path, in_message, in_header = line[len(COMMIT_MARK):].strip(), "", True, False
                self.commits += 1
            elif in_message:
                if line == MESSAGE_END:
                    in_message = False
                else:
                    self.check(line, commit, MESSAGE)
            elif line.startswith("diff --git "):
                in_header = True
                rest = line[len("diff --git "):]
                path = rest.rsplit(" b/", 1)[-1] if " b/" in rest else rest
                self.check(rest, commit, path)  # a number inside a file name is in git too
            elif in_header:
                if line.startswith("+++ b/"):
                    path = line[len("+++ b/"):]
                elif line.startswith("@@"):
                    in_header = False
            elif line.startswith("+"):
                if is_lockfile(path):
                    self.lockfile_lines += 1
                    continue
                self.added_lines += 1
                text = line[1:]
                if path == ALLOW_REL:
                    # The allowlist's own digests are hex, so they contain digit runs; only a line that is exactly one
                    # digest skips that digest, and any comment after it is still checked.
                    code, _, comment = text.partition("#")
                    if SHA256_RE.match(code.strip().lower()):
                        text = comment
                self.check(text, commit, path)

    def suggest_allow(self) -> int:
        """Allowlist lines for the current hits, one per distinct digit run, for review before they are appended."""
        first_file: dict[str, str] = {}
        for _, where, digits in self.hits:
            first_file.setdefault(digits, where)
        for digits, where in sorted(first_file.items(), key=lambda kv: (kv[1], digest(kv[0]))):
            print(f"{digest(digits)}  # {redact(where)}")
        return 0

    def report(self) -> int:
        for commit, where, digits in self.hits:
            print(f"hit: commit {commit[:12]}  file {redact(where)}  last4 {digits[-4:]}")
        n = len(self.hits)
        print(
            f"numbers: {n} hit{'' if n == 1 else 's'} ({self.commits} commits, {self.added_lines} added lines; "
            f"{self.lockfile_lines} lockfile lines not checked; "
            f"{self.fictional} fictional 555 matches ignored; {self.allowlisted} allowlisted)"
        )
        if n:
            print("Each hit shows the commit, the file and the last 4 digits only. A real number: stop, tell the "
                  "team lead, do not rewrite history alone. A false positive: add the sha256 of its 10 digits to "
                  "validation/scan_numbers_allow.txt.")
        return 1 if n else 0


def scan(repo: Path, allow_path: Path, suggest: bool = False) -> int:
    try:
        allow = load_allow(allow_path)
        s = Scan(allow)
        s.run(git_log_lines(repo))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"numbers: scan failed: {exc}", file=sys.stderr)
        return 2
    return s.suggest_allow() if suggest else s.report()


# --- self-test: proves the scan fails on a planted number and prints only its last 4 digits -----------------------


def _generated_number() -> str:
    """A random NANP-shaped 10-digit number with a non-555, non-N11 area code and exchange."""

    def group() -> str:
        while True:
            g = str(2 + secrets.randbelow(8)) + f"{secrets.randbelow(100):02d}"
            if g != FICTIONAL_EXCHANGE and g[1:] != "11":
                return g

    return group() + group() + f"{secrets.randbelow(10000):04d}"


def _forms(d: str) -> set[str]:
    """Every way the self-test could leak a planted number (or more than its last 4 digits)."""
    return {d, d[3:], d[:6], f"{d[:3]}-{d[3:6]}", f"{d[:3]}.{d[3:6]}", f"({d[:3]}) {d[3:6]}", f"{d[:3]} {d[3:6]}"}


def _summary(out: str) -> tuple[int, int] | None:
    m = SUMMARY_RE.search(out)
    return (int(m.group(1)), int(m.group(2))) if m else None


# Self-test files: two lockfiles (not checked) and a file whose name only contains "lock" (checked).
SELFTEST_LOCKFILES = ("selftest_deps/uv.lock", "selftest_deps/web/package-lock.json")
SELFTEST_NOT_LOCKFILE = "selftest_deps/agents.lock.json"


def self_test() -> int:
    numbers: list[str] = []
    while len(numbers) < 7:
        d = _generated_number()
        if all(d[-4:] != n[-4:] for n in numbers):
            numbers.append(d)
    a, b, c, e, h, f, g = numbers
    found, skipped = [a, b, c, e, h], [f, g]  # numbers the scan must report, numbers inside lockfiles
    fictional = _generated_number()[:3] + FICTIONAL_EXCHANGE + "0100"
    planted = (
        f"call +1 ({a[:3]}) {a[3:6]}-{a[6:]} after the visit\n"
        f"backup {b[:3]}.{b[3:6]}.{b[6:]}\n"
        f"pager 1-{c[:3]}-{c[3:6]}-{c[6:]}\n"
        f"placeholder +1{fictional} stays ignored\n"
    )
    # A digest line in the allowlist is skipped, but a number in its comment is still found.
    allow_line = f"{secrets.token_hex(32)}  # {e}\n"
    tmp = Path(tempfile.mkdtemp(prefix="bv-scan-selftest-")).resolve()
    if tmp == ROOT or ROOT in tmp.parents:
        print(f"self-test: FAIL: scratch directory {tmp} is inside the repository", file=sys.stderr)
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    clone = tmp / "clone"
    ok = False
    try:
        quiet = {"check": True, "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE}
        subprocess.run(["git", "clone", "-q", str(ROOT), str(clone)], **quiet)
        (clone / "selftest_contact.txt").write_text(planted)
        allow_in_clone = clone / ALLOW_REL
        allow_in_clone.parent.mkdir(parents=True, exist_ok=True)
        with allow_in_clone.open("a") as fh:
            fh.write(allow_line)
        planted_files = {SELFTEST_NOT_LOCKFILE: h, SELFTEST_LOCKFILES[0]: f, SELFTEST_LOCKFILES[1]: g}
        for rel, d in planted_files.items():
            (clone / rel).parent.mkdir(parents=True, exist_ok=True)
            (clone / rel).write_text(f'"contact": "{d[:3]}-{d[3:6]}-{d[6:]}"\n')
        subprocess.run(["git", "add", "selftest_contact.txt", ALLOW_REL, *planted_files], cwd=clone, **quiet)
        subprocess.run(
            ["git", "-c", "user.name=scan self-test", "-c", "user.email=selftest@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "self-test: planted numbers"],
            cwd=clone, **quiet,
        )
        print(f"self-test: scratch clone {clone} (outside the repository); 1 commit with 7 generated non-555 "
              f"numbers (3 formats in a file, 1 in an allowlist comment, 1 in {SELFTEST_NOT_LOCKFILE}, 1 in each "
              f"lockfile {' and '.join(SELFTEST_LOCKFILES)}) and 1 fictional 555 number")

        def run_scan(allow: Path) -> tuple[int, str]:
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--repo", str(clone), "--allow", str(allow)],
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        rc, out = run_scan(DEFAULT_ALLOW)
        allow_plus_one = tmp / "allow.txt"  # the repository allowlist plus the first planted number
        base = DEFAULT_ALLOW.read_text() if DEFAULT_ALLOW.exists() else ""
        allow_plus_one.write_text(f"{base.rstrip()}\n# self-test entry\n{digest(a)}\n")
        rc2, out2 = run_scan(allow_plus_one)

        if any(f in text for text in (out, out2) for n in numbers for f in _forms(n)):
            print("self-test: FAIL: the scan printed more than the last 4 digits of a planted number (output withheld)")
        else:
            for line in out.splitlines():
                print(f"  | {line}")
            print(f"self-test: scan exit={rc}")
            first, second = _summary(out), _summary(out2)
            last4_shown = all(f"last4 {n[-4:]}" in out for n in found)
            # the 555 placeholder, the digest line and the two lockfile lines are not hits
            exact_hits = first is not None and first[0] == len(found)
            lockfiles_skipped = not any(f"last4 {n[-4:]}" in text for text in (out, out2) for n in skipped)
            allow_works = (rc2 == 1 and first is not None and second is not None
                           and second == (first[0] - 1, first[1] + 1))
            ok = rc == 1 and last4_shown and exact_hits and lockfiles_skipped and allow_works
            print(f"self-test: exit 1 {'yes' if rc == 1 else 'NO'}; last 4 digits of each planted number outside "
                  f"lockfiles shown {'yes' if last4_shown else 'NO'}; full numbers absent from output yes; exactly "
                  f"{len(found)} hits (555 placeholder ignored, allowlist comment and {SELFTEST_NOT_LOCKFILE} "
                  f"checked) {'yes' if exact_hits else 'NO'}; lockfile numbers not reported "
                  f"{'yes' if lockfiles_skipped else 'NO'}; one allowlist sha256 suppresses one hit "
                  f"{'yes' if allow_works else 'NO'}")
    except (OSError, subprocess.CalledProcessError) as exc:
        err = getattr(exc, "stderr", None)
        detail = err.decode(errors="replace").strip() if isinstance(err, bytes) and err else exc
        print(f"self-test: FAIL: {detail}", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"self-test: {'PASS' if ok else 'FAIL'} (scratch clone removed)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, default=ROOT, help="repository to scan (default: this one)")
    ap.add_argument("--allow", type=Path, default=DEFAULT_ALLOW, help="allowlist of sha256 digests")
    ap.add_argument("--self-test", action="store_true", help="run the scratch-clone self-test instead of a scan")
    ap.add_argument("--suggest-allow", action="store_true",
                    help="print allowlist lines for the current hits (review every hit's context before appending)")
    args = ap.parse_args()
    return self_test() if args.self_test else scan(args.repo, args.allow, args.suggest_allow)


if __name__ == "__main__":
    sys.exit(main())
