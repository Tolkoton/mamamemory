#!/usr/bin/env python3
"""delete_guard.py — code no test ever touched is not deleted in silence (board 072).

    python3 .claude/hooks/delete_guard.py show                               # threshold, mode, confirmations
    python3 .claude/hooks/delete_guard.py confirm FINDINGS.json F-xxxxxxxx [--request FILE]   # the OWNER's

Called by gate.py on the `stop` and `pre_commit` layers; the procedure is in
.claude/references/gate.md ("The delete guard").

WHAT IS A DELETION. From the diff against the base (HEAD; the index at pre_commit): a function, a
class or a file of working code that is gone, or more than DELETE_GUARD_LINES lines (default 20)
removed inside one function. Working code is a file with a code extension (CODE_EXTENSIONS) that is
not a test. A move is not a deletion: a function or class whose name is defined anew elsewhere in
the same change, and a removed line that is added again anywhere in the same change, do not count.
For a language other than Python there are no names: the unit is the file, and what is counted is
its removed lines.

WAS THERE A TEST. Exactly, when the project set COVERAGE_CMD: the command runs in a checkout of the
code BEFORE the change — with the tests as they were and, when that is not enough, once more with
the test files of the change laid over it — and must leave `coverage.json` there (the format of
coverage.py's `coverage json`); a deletion passes when its lines were executed. Without COVERAGE_CMD, coarser: the module has its test file
(`test_<module>`, `<module>_test`, `<module>.test`, `<module>.spec`), or a test file mentions the
name. Test files are those of the base and of the change together.

THREE WAYS THROUGH. A test (above). A simplifier finding with tool evidence that the owner
confirmed: `confirm`, refused inside a Claude Code session, written to machine state. The owner's
grant in a sealed slice contract: `gate-allow: delete — <reason>` or `gate-allow: <path> — <reason>`.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_touch import (  # the shared answer to "does a test touch this code"
    COVERAGE_FILE,
    COVERAGE_KEY,
    TestIndex,
    coarse_reason,
    git,
    is_test_path,
    read_old,
    run_coverage,
)

DEFAULT_LINES = 20
KEY = "DELETE_GUARD_LINES"
CONFIRMED_REL = Path(".claude/state/delete-guard/confirmed.json")
# Used only when the project left CODE_EXTENSIONS empty ("everything is code" would guard prose).
CODE_EXTS = ("py", "sh", "js", "jsx", "ts", "tsx", "go", "rs", "java", "kt", "rb", "php", "c", "h", "cc", "cpp",
             "cs", "swift")
HUNK_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<n_old>\d+))? \+\d+(?:,(?P<n_new>\d+))? @@")
TARGET_RE = re.compile(r"^(?P<path>[^:]+?)(?::(?P<line>\d+)(?:-(?P<end>\d+))?)?(?:::(?P<symbol>[\w.]+))?$")
HINT = ("three ways through: (1) a test that pins what this code does today and passes on the code before the "
        "deletion (`python3 .claude/hooks/bugfix.py pins` shows that) — write it, then delete; (2) dead code needs no test: a simplifier finding with tool evidence that "
        "the owner confirmed (`python3 .claude/hooks/delete_guard.py confirm`, the owner's command); (3) the sealed "
        "slice contract carries `gate-allow: delete — <reason>` or `gate-allow: <path> — <reason>`. Moving the code "
        "within the same change is not a deletion")


@dataclass
class Definition:
    kind: str  # function | class
    name: str  # qualified: Class.method
    start: int
    end: int
    body: set[int]  # the lines a test would execute: function bodies, without the docstring


@dataclass
class Unit:
    """One thing the change deleted."""
    file: str
    kind: str  # function | class | file | lines
    name: str | None
    line: int | None
    lines: set[int] = field(default_factory=set)  # old line numbers a test should have executed
    count: int = 0  # for `lines`: how many were removed

    def shown(self) -> str:
        if self.kind == "lines":
            return f"{self.count} lines inside {self.name}()" if self.name else f"{self.count} lines"
        if self.kind == "file":
            return "the file"
        return f"{self.kind} {self.name}"


@dataclass
class FileChange:
    removed: dict[int, str] = field(default_factory=dict)  # old line number -> text
    added: list[str] = field(default_factory=list)
    deleted: bool = False
    created: bool = False


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def threshold(env: dict[str, str]) -> int:
    """DELETE_GUARD_LINES; unset, empty or not a whole number means the default."""
    raw = env.get(KEY, "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_LINES


def is_working_code(env: dict[str, str], rel: str) -> bool:
    exts = [t.lstrip(".").lower() for t in env.get("CODE_EXTENSIONS", "").replace(",", " ").split() if t.lstrip(".")]
    if rel.startswith("sketches/"):   # a sketch's quarantine (gate.py, board 099): its code is thrown away freely
        return False
    return Path(rel).suffix.lstrip(".").lower() in (exts or CODE_EXTS) and not is_test_path(rel)


# ------------------------------------------------------------------ the change


def base_args(layer: str, diff_ref: str | None) -> tuple[list[str], str]:
    """The diff arguments of a layer and the ref the code "before" is read from."""
    if layer == "pre_commit":
        return ["--cached"], "HEAD"
    return [diff_ref or "HEAD"], diff_ref or "HEAD"


def take_hunk_line(change: FileChange, left: list[int], line: str) -> bool:
    """One line of a hunk body into `change`; `left` is [old lines left, new lines left, old line number]."""
    if line.startswith("-") and left[0]:
        change.removed[left[2]] = line[1:]
        left[0], left[2] = left[0] - 1, left[2] + 1
        return True
    if line.startswith("+") and left[1]:
        change.added.append(line[1:])
        left[1] -= 1
        return True
    return line.startswith("\\")


def header_path(line: str) -> str:
    return "" if line[4:] == "/dev/null" else line[6:]


def parse_diff(text: str) -> dict[str, FileChange]:
    """`git diff -U0 --no-renames` as removed and added lines per file. Hunk sizes are counted, so a
    removed line that itself starts with `--` is not read as a header."""
    changes: dict[str, FileChange] = {}
    current: FileChange | None = None
    old_path = ""
    left = [0, 0, 0]
    for line in text.splitlines():
        if current is not None and (left[0] or left[1]) and take_hunk_line(current, left, line):
            continue
        left[0] = left[1] = 0
        hunk = HUNK_RE.match(line)
        if hunk and current is not None:
            left = [1 if hunk["n_old"] is None else int(hunk["n_old"]),
                    1 if hunk["n_new"] is None else int(hunk["n_new"]), int(hunk["old"])]
        if line.startswith("diff --git "):
            current, old_path = None, ""
        if line.startswith("--- "):
            old_path = header_path(line)
        if line.startswith("+++ "):
            current = changes.setdefault(old_path or header_path(line), FileChange())
            current.deleted, current.created = not header_path(line), not old_path
    return changes


def collect_change(root: Path, layer: str, diff_ref: str | None) -> dict[str, FileChange]:
    args, _ = base_args(layer, diff_ref)
    out = git(root, "diff", "-U0", "--no-color", "--no-renames", *args)
    changes = parse_diff(out.stdout) if out.returncode == 0 else {}
    if layer != "pre_commit":  # a function moved into a file git does not know yet is still a move
        for rel in git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines():
            try:
                text = (root / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            changes[rel] = FileChange(added=text.splitlines(), created=True)
    return changes


def read_new(root: Path, layer: str, rel: str) -> str | None:
    if layer == "pre_commit":
        out = git(root, "show", f":{rel}")
        return out.stdout if out.returncode == 0 else None
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ------------------------------------------------------------------ what a file defines


def docstring_lines(node: ast.AST) -> set[int]:
    body = getattr(node, "body", [])
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return set(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return set()


def definitions(text: str | None) -> dict[str, Definition] | None:
    """Functions, classes and methods of a Python source by qualified name; None when it does not
    parse. A function nested in a function is part of that function."""
    if text is None:
        return None
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    found: dict[str, Definition] = {}

    def visit(node: ast.AST, prefix: str) -> set[int]:
        executed: set[int] = set()
        for child in getattr(node, "body", []):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                first = child.body[0].lineno if child.body else child.lineno
                body = set(range(first, (child.end_lineno or first) + 1)) - docstring_lines(child)
                found[prefix + child.name] = Definition("function", prefix + child.name, child.lineno,
                                                        child.end_lineno or child.lineno, body)
                executed |= body
            elif isinstance(child, ast.ClassDef):
                inner = visit(child, f"{prefix}{child.name}.")
                end = child.end_lineno or child.lineno
                # A class with no method has nothing but its body for a test to execute.
                body = inner or set(range(child.lineno, end + 1)) - docstring_lines(child)
                found[prefix + child.name] = Definition("class", prefix + child.name, child.lineno, end, body)
                executed |= body
        return executed

    visit(tree, "")
    return found


def bare(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def code_line(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("#")


def lost_lines(change: FileChange, pool: Counter[str], skip: set[int]) -> list[int]:
    """Removed lines that the change adds nowhere again. `pool` is consumed: one added line answers
    for one removed line."""
    lost = []
    for number, text in sorted(change.removed.items()):
        if number in skip or not code_line(text):
            continue
        key = text.strip()
        if pool[key] > 0:
            pool[key] -= 1
        else:
            lost.append(number)
    return lost


def gone_units(rel: str, gone: dict[str, Definition], moved: set[str]) -> list[Unit]:
    """The definitions that left the file and were not defined anew elsewhere in the change."""
    units = []
    for item in gone.values():
        # A method of a class that is gone too is reported with the class, once.
        inside_gone = "." in item.name and item.name.rsplit(".", 1)[0] in gone
        if not inside_gone and bare(item.name) not in moved:
            units.append(Unit(rel, item.kind, item.name, item.start, set(item.body)))
    return units


def line_units(rel: str, lost: list[int], kept: list[Definition], limit: int) -> list[Unit]:
    """More than `limit` lines lost inside one function that stays."""
    per_def: dict[str, list[int]] = {}
    for number in lost:
        # The body leaves the docstring out: it is not behaviour.
        owner = next((d for d in kept if d.kind == "function" and number in d.body), None)
        if owner is not None:
            per_def.setdefault(owner.name, []).append(number)
    return [Unit(rel, "lines", name, numbers[0], set(numbers), len(numbers))
            for name, numbers in per_def.items() if len(numbers) > limit]


def units_of_python(rel: str, change: FileChange, old: dict[str, Definition], new: dict[str, Definition] | None,
                    moved: set[str], pool: Counter[str], limit: int) -> list[Unit]:
    if change.deleted and not old:
        return [Unit(rel, "file", None, None, set(change.removed))]
    gone = {name: d for name, d in old.items() if new is None or name not in new}
    skip = {n for d in gone.values() for n in range(d.start, d.end + 1)}
    kept = [d for d in old.values() if d.name not in gone]
    return gone_units(rel, gone, moved) + line_units(rel, lost_lines(change, pool, skip), kept, limit)


Parsed = dict[str, tuple[dict[str, Definition] | None, dict[str, Definition] | None]]


def python_view(root: Path, layer: str, ref: str, changes: dict[str, FileChange]) -> tuple[Parsed, set[str]]:
    """Every changed Python file's definitions before and after, and the names the change defines anew."""
    parsed: Parsed = {}
    moved: set[str] = set()
    for rel, change in changes.items():
        if not rel.endswith(".py") or not (change.removed or change.added):
            continue
        old = None if change.created else definitions(read_old(root, ref, rel))
        new = None if change.deleted else definitions(read_new(root, layer, rel))
        parsed[rel] = (old, new)
        moved.update(bare(name) for name in (new or {}) if name not in (old or {}))
    return parsed, moved


def find_units(root: Path, layer: str, diff_ref: str | None, env: dict[str, str],
               changes: dict[str, FileChange]) -> list[Unit]:
    limit = threshold(env)
    pool: Counter[str] = Counter(line.strip() for c in changes.values() for line in c.added if code_line(line))
    parsed, moved = python_view(root, layer, base_args(layer, diff_ref)[1], changes)
    units: list[Unit] = []
    for rel, change in sorted(changes.items()):
        if not change.removed or not is_working_code(env, rel):
            continue
        old, new = parsed.get(rel, (None, None))
        if old is not None and (new is not None or change.deleted):
            units.extend(units_of_python(rel, change, old, new, moved, pool, limit))
            continue
        lost = lost_lines(change, pool, set())  # no names to go by: the file and its removed lines
        if change.deleted and lost:
            units.append(Unit(rel, "file", None, None, set(lost)))
        elif len(lost) > limit:
            units.append(Unit(rel, "lines", None, lost[0], set(lost), len(lost)))
    return units


# ------------------------------------------------------------------ was there a test: coarse


def coarse_test(unit: Unit, tests: TestIndex) -> str:
    """Why the unit counts as tested without coverage, or ''."""
    return coarse_reason(tests, unit.file, bare(unit.name) if unit.name else None)


# ------------------------------------------------------------------ was there a test: coverage


def overlay(root: Path, layer: str, changes: dict[str, FileChange]) -> dict[str, str]:
    """The test files of the change as they are now: laid over the old code before coverage runs."""
    files = {}
    for rel, change in changes.items():
        if is_test_path(rel) and not change.deleted:
            text = read_new(root, layer, rel)
            if text is not None:
                files[rel] = text
    return files


Coverage = dict[str, dict[str, set[int]]]


def coverage_of(root: Path, ref: str, command: str, extra: dict[str, str], units: list[Unit], limit: int) -> Coverage | None:
    """What the tests executed on the code before the change: the tests as they were, and — only when
    those leave a deletion unanswered — once more with the test files of the change laid over them.
    Both count: a test edited or deleted together with its code still says the code was tested."""
    report = run_coverage(root, ref, command, {})
    if report is None or not extra or all(covered(unit, report, limit) for unit in units):
        return report
    for rel, entry in (run_coverage(root, ref, command, extra) or {}).items():
        mine = report.setdefault(rel, {"executed": set(), "missing": set()})
        mine["executed"] |= entry["executed"]
        mine["missing"] = (mine["missing"] | entry["missing"]) - mine["executed"]
    return report


def covered(unit: Unit, report: Coverage, limit: int) -> str:
    """Why the unit counts as tested by the coverage of the old code, or ''."""
    entry = report.get(unit.file)
    if entry is None:
        return ""
    executed = unit.lines & entry["executed"]
    if unit.kind == "lines":
        # The statements nobody executed are what would go unseen; the rest of the removed lines were run.
        unseen = unit.lines & entry["missing"] if entry["missing"] else unit.lines - entry["executed"]
        return "" if len(unseen) > limit or not executed else f"tests executed {len(executed)} of the removed lines"
    return f"tests executed {len(executed)} of its lines" if executed else ""


# ------------------------------------------------------------------ the owner's confirmation


def confirmations(root: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads((root / CONFIRMED_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("confirmed") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def confirmed(unit: Unit, rows: list[dict[str, Any]]) -> str:
    """The owner-confirmed finding that covers this deletion, or ''."""
    for row in rows:
        if row.get("path") != unit.file:
            continue
        names = row.get("names")
        if names is None or (unit.name and (unit.name in names or bare(unit.name) in names)):
            return str(row.get("finding"))
    return ""


def target_names(root: Path, target: str) -> tuple[str, list[str] | None]:
    """A finding's target as (path, names): the named symbol, else the definitions its lines fall in,
    else None — the whole file."""
    match = TARGET_RE.match(target.strip())
    if not match:
        return target, None
    if match["symbol"]:
        return match["path"], [match["symbol"]]
    if not match["line"]:
        return match["path"], None
    first, last = int(match["line"]), int(match["end"] or match["line"])
    try:
        found = definitions((root / match["path"]).read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError):
        found = {}
    names = [d.name for d in found.values() if d.start <= last and first <= d.end]
    return match["path"], names or None


def tool_finding(root: Path, findings: Path, ident: str, request: Path | None) -> tuple[dict[str, Any] | None, str]:
    """The valid finding `ident` of the file when it carries tool evidence, else (None, why not)."""
    import simplifier

    try:
        result = simplifier.validated_file(root, findings, request)
    except (OSError, ValueError) as exc:
        return None, f"{findings} is not a findings file: {exc}"
    finding = next((f for f in result["findings"] if f["id"] == ident), None)
    if finding is None:
        known = ", ".join(f["id"] for f in result["findings"]) or "none"
        return None, f"no valid finding {ident} in {findings} (valid: {known})"
    if not any(e.get("source") == "signal" for e in finding["evidence"]):
        return None, (f"{ident} has no evidence from a tool (a signal of simplify_signals.py); a judgement or a "
                      "reading alone does not make code dead")
    return finding, ""


def cmd_confirm(root: Path, findings: Path, ident: str, request: Path | None) -> int:
    """The owner's «так» on a simplifier finding, as far as this guard is concerned. Refused inside a
    Claude Code session: hooks do not see what a script runs, so the script carries the check."""
    if os.environ.get("CLAUDECODE"):
        print("delete_guard: confirm is the owner's command and is refused inside a Claude Code session "
              "(CLAUDECODE is set). Nothing was written. Run it in your own terminal.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import simplifier

    finding, problem = tool_finding(root, findings, ident, request)
    if finding is None:
        print(f"delete_guard: {problem}. Nothing was written.", file=sys.stderr)
        return 1
    path, names = target_names(root, finding["target"])
    rows = [r for r in confirmations(root) if r.get("finding") != ident]
    rows.append({"finding": ident, "path": path, "names": names, "target": finding["target"],
                 "evidence": [str(e.get("ref", "")) for e in finding["evidence"] if e.get("source") == "signal"],
                 "utc": utc_now()})
    target = root / CONFIRMED_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"confirmed": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    simplifier.decide(root, ident, "так")
    what = ", ".join(names) if names else "the whole file"
    print(f"confirmed {ident}: {path} ({what}) may be deleted without a test — {finding['category']}: {finding['claim']}")
    return 0


def cmd_show(root: Path, env: dict[str, str]) -> int:
    mode = f"exact, by {COVERAGE_KEY}: {env[COVERAGE_KEY]}" if env.get(COVERAGE_KEY) else \
        f"coarse (no {COVERAGE_KEY}): the module's test file, or the name in a test file"
    print(f"{KEY}: {threshold(env)} line(s) inside one function\nwas there a test: {mode}")
    rows = confirmations(root)
    print(f"confirmed by the owner: {len(rows)}")
    for row in rows:
        print(f"  {row.get('finding')} {row.get('path')} ({', '.join(row['names']) if row.get('names') else 'the whole file'})")
    return 0


# ------------------------------------------------------------------ the check gate.py calls


def finding(file: str | None, line: int | None, rule: str, severity: str, message: str, hint: str = "") -> dict[str, Any]:
    return {"file": file, "line": line, "rule": rule, "severity": severity, "message": message, "hint": hint}


def check(root: Path, layer: str, diff_ref: str | None, env: dict[str, str],
          grants: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    """The guard's findings as dicts with the fields of gate.Finding."""
    changes = collect_change(root, layer, diff_ref)
    units = find_units(root, layer, diff_ref, env, changes)
    if not units:
        return []
    ref = base_args(layer, diff_ref)[1]
    limit = threshold(env)
    findings: list[dict[str, Any]] = []
    report = None
    command = env.get(COVERAGE_KEY, "").strip()
    if command:
        report = coverage_of(root, ref, command, overlay(root, layer, changes), units, limit)
        if report is None:
            findings.append(finding(
                None, None, "delete/coverage-unavailable", "warn",
                f"{COVERAGE_KEY} left no readable {COVERAGE_FILE} on the code before the change; the coarser check is used",
                f"run it by hand in a clean checkout: {command}"))
    tests = TestIndex(root, ref, changes)
    rows = confirmations(root)

    def way_through(unit: Unit) -> str:
        grant = grants.get("delete") or grants.get(unit.file.lower())
        if grant:
            return f"allowed by the slice contract {grant[0]}"
        owner = confirmed(unit, rows)
        if owner:
            return f"the owner confirmed the simplifier's finding {owner}"
        return covered(unit, report, limit) if report is not None else coarse_test(unit, tests)

    untested: dict[str, list[Unit]] = {}
    for unit in units:
        why = way_through(unit)
        if why:
            findings.append(finding(unit.file, unit.line, "delete/passed", "log", f"{unit.shown()} deleted: {why}"))
        else:
            untested.setdefault(unit.file, []).append(unit)
    how = "no test executed it on the code before the change" if report is not None else \
        "the module has no test file and no test mentions it"
    for file, group in untested.items():
        shown = "; ".join(u.shown() for u in group[:8]) + (f"; and {len(group) - 8} more" if len(group) > 8 else "")
        findings.append(finding(
            file, group[0].line, "delete/untested", "block",
            f"the change deletes code no test touched ({shown}) — {how}, so nothing would notice lost behaviour", HINT))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    p = sub.add_parser("confirm")
    p.add_argument("findings", type=Path, help="the simplifier's findings file (its answer, or what `validate --out` wrote)")
    p.add_argument("finding", help="F-xxxxxxxx")
    p.add_argument("--request", type=Path, help="the request the simplifier was started with (its signals are the input)")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    root = gate.project_root()
    if args.command == "confirm":
        return cmd_confirm(root, args.findings, args.finding, args.request)
    return cmd_show(root, gate.load_env(root))


if __name__ == "__main__":
    sys.exit(main())
