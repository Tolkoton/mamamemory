#!/usr/bin/env python3
"""simplify_signals.py — the simplifier's deterministic signals. No model is involved.

    python3 .claude/hooks/simplify_signals.py --scope stop [--files F ...]    # the changed files, fast
    python3 .claude/hooks/simplify_signals.py --scope full [--paths P ...] [--record]

A signal is a measured fact with a file and a line, never a verdict: the simplifier agent
(.claude/agents/simplifier.md) receives the list as its input and has to cite a signal's id, or
say "judgement". gate.py calls `collect` from its own layers when COMPLEXITY_GATE is not off and
shows each signal as a `warn` finding — a signal never blocks.

    stop   the files the turn changed: a function that is new or got worse than at HEAD and is
           above the project's limit (complexity, nesting), a dependency the change adds, dead
           code in the changed modules
    full   the whole repository (pre_commit, ci, the nightly cleanup): every function above the
           limit, dead code, unused dependencies, duplication; with --record one line of totals
           is appended to .claude/state/simplifier/metrics.jsonl and compared with the median of
           the runs before it — growth past GROWTH is a `trend` signal, which calls the simplifier

Tools at the versions .claude/hooks/tool_versions.py pins (board 107) — the project's own copy in
its virtual environment if it has one, else one on PATH of exactly that version, else `uvx`:
vulture (dead code; the tests and scripts are read as users of a name and never reported
themselves), pylint's duplicate-code. Nothing is added to the project's dependencies; a tool that
cannot run — or only another version of it — is reported as `unavailable` with the reason, never
read as "clean". The result is also written to .claude/state/simplifier/signals-<scope>.json.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Any

import complexity_budget as budget
import tool_versions

Signal = dict[str, Any]
STATE_REL = Path(".claude/state/simplifier")
BUILTIN_LIMITS = {"max_cyclomatic_per_function": 10, "max_nesting_depth": 3}
KIND_OF = {"max_cyclomatic_per_function": "complexity", "max_nesting_depth": "nesting"}
TOOL_TIMEOUT_S = 120
DUPLICATE_LINES = 8
HISTORY = 5
GROWTH = 1.2
MIN_DELTA = {"lines": 200}
DEFAULT_MIN_DELTA = 3
VULTURE_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+): (?P<msg>.+ \(\d+% confidence\))$", re.MULTILINE)
SIMILAR_RE = re.compile(r"^==(?P<module>[\w.]+):\[(?P<start>\d+):(?P<end>\d+)\]$", re.MULTILINE)


def signal(tool: str, kind: str, file: str | None, line: int | None, message: str) -> Signal:
    ident = hashlib.sha1(f"{tool}|{kind}|{file}|{message}".encode()).hexdigest()[:8]
    return {"id": f"S-{ident}", "tool": tool, "kind": kind, "file": file, "line": line, "message": message}


def run_tool(root: Path, tool: str, *args: str) -> tuple[str | None, str]:
    """The tool's stdout and ""; None and why when it cannot run (tool_versions.py, board 107)."""
    own = tool_versions.project_tool(root, tool)
    prefix, why = ([own], "") if own else tool_versions.command(tool)
    if prefix is None:
        return None, why
    try:
        proc = subprocess.run([*prefix, *args], cwd=root, capture_output=True, text=True,
                              timeout=TOOL_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{tool} did not finish: {exc}"
    # Both tools exit non-zero when they FOUND something; only a run with no output at all and
    # an error text is a tool that did not run.
    if proc.returncode != 0 and not proc.stdout.strip() and proc.stderr.strip():
        return None, proc.stderr.strip().splitlines()[-1][:200]
    return proc.stdout, ""


def project_files(root: Path, env: dict[str, str]) -> list[str]:
    """Python the project wrote and git knows (tracked or untracked-not-ignored), anywhere in the
    repository, SIMPLIFY_EXCLUDE (fixtures, vendored code) excluded."""
    listed = budget.git(root, "ls-files", "-co", "--exclude-standard", "*.py").splitlines()
    excluded = [d for d in re.split(r"[\s,]+", env.get("SIMPLIFY_EXCLUDE", "")) if d]
    return sorted(p for p in listed if not (excluded and budget.in_source(p, excluded)) and (root / p).is_file())


def production_files(root: Path, env: dict[str, str], paths: list[str] | None) -> list[str]:
    """The project's files inside `paths` (else SOURCE_DIRS), tests excluded: what is measured."""
    scope = paths or budget.source_dirs_of(env)
    return [p for p in project_files(root, env) if budget.in_source(p, scope) and not budget.is_test(p)]


def limits_of(env: dict[str, str]) -> dict[str, int]:
    return BUILTIN_LIMITS | budget.default_limits(env)


def function_lines(tree: ast.AST) -> dict[str, int]:
    """Qualified function name -> its line, named the way complexity_budget.function_metrics names it."""
    found: dict[str, int] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[prefix + child.name] = child.lineno
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def complexity_signals(root: Path, env: dict[str, str], files: list[str], against_head: bool) -> list[Signal]:
    """Functions above the limit; with `against_head`, only those new or worse than at HEAD."""
    out: list[Signal] = []
    limits = limits_of(env)
    for rel in files:
        try:
            tree = budget.parse_py((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            tree = None
        if tree is None:
            continue
        before = budget.parse_py(budget.git(root, "show", f"HEAD:{rel}")) if against_head else None
        old = budget.function_metrics(before) if before else {}
        lines = function_lines(tree)
        for name, values in budget.function_metrics(tree).items():
            for index, key in enumerate(BUILTIN_LIMITS):
                was = old.get(name, (0, 0))[index] if against_head else 0
                if values[index] > limits[key] and values[index] > was:
                    grew = f", was {was} at HEAD" if was else ""
                    out.append(signal("ast", KIND_OF[key], rel, lines.get(name),
                                      f"{name}: {KIND_OF[key]} {values[index]}, the limit is {limits[key]}{grew}"))
    return out


def dependency_signals(root: Path, files: list[str]) -> list[Signal]:
    out: list[Signal] = []
    for rel in (f for f in files if PurePosixPath(f).name == "pyproject.toml"):
        try:
            now = budget.dependency_names((root / rel).read_text(encoding="utf-8"))
        except OSError:
            continue
        for name in sorted(now - budget.dependency_names(budget.git(root, "show", f"HEAD:{rel}"))):
            out.append(signal("pyproject", "new-dependency", rel, None, f"the change adds the dependency {name}"))
    return out


def dead_code_signals(root: Path, production: list[str], users: list[str], only: set[str] | None) -> list[Signal]:
    """vulture over the production code and its `users` — the tests and scripts, read only as
    callers: a name used in another file is not dead, a library's public function its tests call
    included. Reported for production files, those in `only` when given."""
    reported = set(production) if only is None else only & set(production)
    if not reported:
        return []
    out, why = run_tool(root, "vulture", "--min-confidence", "60", *sorted({*production, *users}))
    if out is None:
        return [signal("vulture", "unavailable", None, None, f"vulture could not run: dead code was not measured ({why})")]
    return [signal("vulture", "dead-code", m["file"], int(m["line"]), m["msg"])
            for m in VULTURE_RE.finditer(out) if m["file"] in reported]


# A distribution whose import name is not its own name: without the line, a package the code does
# import would be reported as unused (board 728). Keys are normalized names; a package absent here
# is looked for under its own name. Short on purpose — a signal is a lead, not a resolver.
IMPORT_NAMES = {
    "attrs": ("attr", "attrs"),
    "beautifulsoup4": ("bs4",),
    "dnspython": ("dns",),
    "msgpack-python": ("msgpack",),
    "opencv-contrib-python": ("cv2",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "pillow": ("PIL",),
    "protobuf": ("google",),
    "psycopg2-binary": ("psycopg2",),
    "pycryptodome": ("Crypto",),
    "pyjwt": ("jwt",),
    "pymupdf": ("fitz", "pymupdf"),
    "pyopenssl": ("OpenSSL",),
    "pyserial": ("serial",),
    "python-dateutil": ("dateutil",),
    "python-dotenv": ("dotenv",),
    "python-jose": ("jose",),
    "python-magic": ("magic",),
    "python-multipart": ("multipart", "python_multipart"),
    "pyyaml": ("yaml",),
    "pyzmq": ("zmq",),
    "scikit-image": ("skimage",),
    "scikit-learn": ("sklearn",),
    "setuptools": ("setuptools", "pkg_resources"),
}


def import_names(distribution: str) -> tuple[str, ...]:
    """The top-level modules a declared distribution is imported as."""
    normalized = re.sub(r"[-_.]+", "-", distribution).lower()
    return IMPORT_NAMES.get(normalized, (normalized.replace("-", "_"),))


def imported_modules(path: Path) -> set[str]:
    try:
        tree = budget.parse_py(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        tree = None
    modules: set[str] = set()
    for node in ast.walk(tree) if tree else ():
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return {module.split(".")[0].lower() for module in modules}


def importers(base: Path) -> dict[str, set[str]]:
    """Every top-level module imported by a Python file under `base` (lowercased) → the files, relative to `base`."""
    found: dict[str, set[str]] = {}
    for path in (p for p in base.rglob("*.py") if ".venv" not in p.parts):
        for module in imported_modules(path):
            found.setdefault(module, set()).add(path.relative_to(base).as_posix())
    return found


def unused_dependency_signals(root: Path) -> list[Signal]:
    """A runtime dependency of a pyproject.toml that no Python file beside or under it imports, or
    that only test files import — a candidate for the dev group, not for removal."""
    out: list[Signal] = []
    for rel in budget.git(root, "ls-files", "pyproject.toml", "*/pyproject.toml").splitlines():
        try:
            text = (root / rel).read_text(encoding="utf-8")
            declared = tomllib.loads(text).get("project", {}).get("dependencies", [])
        except (OSError, tomllib.TOMLDecodeError):
            continue
        base = PurePosixPath(rel).parent
        imported = importers(root / base)
        for spec in declared:
            name = re.split(r"[\s<>=!~;\[@(]", str(spec).strip(), maxsplit=1)[0]
            if not name:
                continue
            modules = import_names(name)
            users = sorted({f for module in modules for f in imported.get(module.lower(), ())})
            if not all(budget.is_test(f) for f in users):
                continue
            line = next((n for n, row in enumerate(text.splitlines(), 1) if name in row), None)
            message = (f"{name} is a runtime dependency imported only by tests: {', '.join((base / f).as_posix() for f in users)}"
                       if users else f"{name} is declared and no module named {' or '.join(modules)} is imported")
            out.append(signal("pyproject", "unused-dependency", rel, line, message))
    return out


def duplication_signals(root: Path, production: list[str]) -> list[Signal]:
    if len(production) < 2:
        return []
    out, why = run_tool(root, "pylint", "--disable=all", "--enable=duplicate-code",
                        f"--min-similarity-lines={DUPLICATE_LINES}", "-sn", *production)
    if out is None:
        return [signal("pylint", "unavailable", None, None, f"pylint could not run: duplication was not measured ({why})")]
    by_module = {PurePosixPath(p).stem: p for p in reversed(production)}
    found: list[Signal] = []
    for block in out.split("R0801: Similar lines in")[1:]:
        places = [(by_module.get(m["module"].split(".")[-1], m["module"]), int(m["start"]), int(m["end"]))
                  for m in SIMILAR_RE.finditer(block)]
        if len(places) >= 2:
            shown = " and ".join(f"{file}:{start}-{end}" for file, start, end in places)
            found.append(signal("pylint", "duplication", places[0][0], places[0][1],
                                f"{places[0][2] - places[0][1]} similar lines: {shown}"))
    return found


def totals(root: Path, production: list[str], signals: list[Signal]) -> dict[str, int]:
    lines = functions = 0
    for rel in production:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines += len(text.splitlines())
        tree = budget.parse_py(text)
        functions += len(budget.function_metrics(tree)) if tree else 0
    count = {kind: sum(s["kind"] == kind for s in signals) for kind in
             ("complexity", "nesting", "dead-code", "duplication", "unused-dependency")}
    return {"files": len(production), "lines": lines, "functions": functions, **count}


def trend_signals(root: Path, now: dict[str, int], record: bool) -> list[Signal]:
    """Compare the totals with the median of the last runs; `record` appends this run."""
    path = root / STATE_REL / "metrics.jsonl"
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        rows = []
    history = [row["totals"] for row in rows[-HISTORY:] if isinstance(row.get("totals"), dict)]
    out: list[Signal] = []
    for key, value in now.items():
        past = [int(h[key]) for h in history if key in h]
        if not past:
            continue
        usual = median(past)
        if value > usual * GROWTH and value - usual >= MIN_DELTA.get(key, DEFAULT_MIN_DELTA):
            out.append(signal("history", "trend", None, None,
                              f"{key} grew from {usual:g} (median of the last {len(past)} runs) to {value}"))
    if record:
        head = budget.git(root, "rev-parse", "--short", "HEAD").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"utc": utc_now(), "head": head, "totals": now}) + "\n")
    return out


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect(root: Path, env: dict[str, str], scope: str, files: list[str] | None = None,
            paths: list[str] | None = None, record: bool = False) -> list[Signal]:
    """The signals of one scope, also written to .claude/state/simplifier/signals-<scope>.json."""
    production = production_files(root, env, paths)
    users = project_files(root, env)
    if scope == "stop":
        changed = [f for f in files or [] if f in production]
        signals = (complexity_signals(root, env, changed, against_head=True)
                   + dependency_signals(root, files or [])
                   + dead_code_signals(root, production, users, set(changed)))
    else:
        signals = (complexity_signals(root, env, production, against_head=False)
                   + dead_code_signals(root, production, users, None)
                   + unused_dependency_signals(root)
                   + duplication_signals(root, production))
        signals += trend_signals(root, totals(root, production, signals), record)
    try:
        target = root / STATE_REL / f"signals-{scope}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"scope": scope, "utc": utc_now(), "signals": signals}, indent=2) + "\n",
                          encoding="utf-8")
    except OSError:
        pass
    return signals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--scope", choices=("stop", "full"), required=True)
    parser.add_argument("--files", nargs="*", default=None, help="stop: the changed files (default: the diff against HEAD)")
    parser.add_argument("--paths", nargs="*", default=None, help="directories or files to measure (default: SOURCE_DIRS)")
    parser.add_argument("--record", action="store_true", help="full: append the totals to the history")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = budget.project_root()
    files = args.files
    if args.scope == "stop" and files is None:
        files = sorted({*budget.git(root, "diff", "--name-only", "HEAD").splitlines(),
                        *budget.git(root, "ls-files", "--others", "--exclude-standard").splitlines()})
    signals = collect(root, budget.project_env(root), args.scope, files, args.paths, args.record)
    if args.json:
        print(json.dumps(signals, indent=2))
        return 0
    for s in signals:
        where = f"{s['file']}:{s['line']}" if s["line"] else (s["file"] or "-")
        print(f"{s['id']}  {s['kind']:18} {where}  {s['message']}")
    calls = [s["message"] for s in signals if s["kind"] == "trend"]
    print(f"\n{len(signals)} signal(s)" + ("; SIMPLIFIER CALL (sharp growth): " + "; ".join(calls) if calls else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
