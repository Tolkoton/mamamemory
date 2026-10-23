#!/usr/bin/env python3
"""Complexity budget — the deterministic layer of the simplifier.

    python3 .claude/hooks/complexity_budget.py hook                 # Stop hook (stdin JSON)
    python3 .claude/hooks/complexity_budget.py check                # same measurement, as a report
    python3 .claude/hooks/complexity_budget.py validate <contract>  # at slice-contract approval
    python3 .claude/hooks/complexity_budget.py calibrate            # propose the default limits
    python3 .claude/hooks/complexity_budget.py set-defaults C N     # the OWNER's command: apply them

WHY THIS EXISTS. Code written by language models grows faster than the behaviour it adds,
and the growth ACCUMULATES across checkpoints: an instruction to "keep it simple" lowers the
starting point by about a third and leaves the slope untouched, and green tests do not see
structural decay at all (research part E2). So the limit is agreed BEFORE the code exists —
in the slice contract — and measured by something that cannot be talked round.

WHAT IT MEASURES: everything that changed since the slice began (`base_commit` in the
contract) up to the working tree, untracked files included. Cumulative per slice, not per
turn: ten small turns may not add up to what one turn would have been refused.

    max_new_files, max_net_new_lines   production code only; tests are counted and
                                       reported separately and never limited — a test
                                       adds lines and removes risk
    max_new_public_symbols             new top-level names without a leading underscore
    max_new_abstractions               new ABC / Protocol / abstract-method classes
    max_new_dependencies               new names in pyproject.toml, any group
    max_cyclomatic_per_function, max_nesting_depth
                                       only functions that are NEW or got WORSE than at
                                       base_commit: old complexity in a file you touch is
                                       not this slice's debt

Standard library only (ast, tomllib, git): the gate has to work in cloud sessions and on
a colleague's machine with no linter installed. Python 3.11+.

THE BUDGET IS AN EXPECTATION, NOT A CEILING (owner, board 010). Going over it does not forbid
the change; it calls the simplifier (.claude/agents/simplifier.md) with the figures. The
simplifier rules: justified — the reason is recorded next to the contract and in the ledger
(`simplifier.py accept`) and the turn ends; not justified — the builder makes the change smaller.

THE SWITCH is COMPLEXITY_GATE in .claude/project.env: off (default) | warn | call.
  warn   never holds the turn; writes .claude/state/overseer/complexity-report.md and says so
  call   holds the turn while an overrun has no recorded verdict of the simplifier
         (`block`, the value before board 010, means the same)
No active slice, or a contract without a budget section: nothing to enforce, silent.

DEFAULT LIMITS. Where the contract names no per-function limit, COMPLEXITY_MAX_CYCLOMATIC and
COMPLEXITY_MAX_NESTING of project.env apply. `calibrate` proposes them from the functions the
project already has; only the owner applies them (`set-defaults`, refused inside a session).

RAISING THE BUDGET is the owner's call. The limits seen FIRST for a slice are remembered
(.claude/state/overseer/.budget-<slug>.json); if the contract later shows higher numbers, the
original ones stay in force and the report says so. The owner re-baselines by deleting
that file — a visible act, not a quiet edit.

THE HARD MODE (board 075). A card of an urgent fix (`type: hotfix`, written by `hotfix.py start`
from .claude/templates/hotfix-record.md; `mode: hard` in its budget section) is the one budget
that IS a ceiling. Its limits cannot be set above HARD_LIMITS; it is measured whole — every
changed file but the tests and the engine's own records, added lines and not net ones — and code
may not be deleted outside the functions being fixed. Over it the turn is blocked whatever
COMPLEXITY_GATE says and on every stop, the simplifier is not called and its acceptance lifts
nothing. A card seen hard stays hard, whatever it is edited to say.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ENV_DEFAULTS = {
    "max_cyclomatic_per_function": "COMPLEXITY_MAX_CYCLOMATIC",
    "max_nesting_depth": "COMPLEXITY_MAX_NESTING",
}
CALIBRATION_FLOOR = {"max_cyclomatic_per_function": 5, "max_nesting_depth": 2}
ACCEPTED_DIR = Path(".claude/state/simplifier")
LIMIT_KEYS = (
    "max_new_files",
    "max_changed_files",
    "max_added_lines",
    "max_net_new_lines",
    "max_new_public_symbols",
    "max_new_abstractions",
    "max_new_dependencies",
    "max_cyclomatic_per_function",
    "max_nesting_depth",
)
KNOWN_KEYS = (*LIMIT_KEYS, "base_commit", "justification", "mode")
# An urgent fix (the approved design of board 070, section 4): the card may not set these higher.
HARD_LIMITS = {"max_new_files": 0, "max_changed_files": 2, "max_added_lines": 30,
               "max_new_public_symbols": 0, "max_new_dependencies": 0}
HARD_TYPE_RE = re.compile(r"^type:[ \t]*hotfix[ \t]*$", re.MULTILINE)
DELETED_OUTSIDE = "deleted_outside_fixed_functions"
# Not the fix: the engine's own records (the card, the debt, the board) and the machine state
# the hooks write — which a project need not have in its .gitignore.
RECORD_DIRS = (".engine/", "tasks/", ".claude/state/")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@", re.MULTILINE)
SECTION_RE = re.compile(r"^##\s+Complexity budget\s*$", re.IGNORECASE | re.MULTILINE)
ACTIVE_RE = re.compile(r"IN PROGRESS", re.IGNORECASE)
# A bug record (.engine/bugs/, written by /bugfix) carries its budget like a slice contract.
CONTRACT_PATH_RE = re.compile(r"\.engine/(?:slices|bugs)/[\w.-]+\.md")
SLUG_RE = re.compile(r"[Ss]lice\s+`?([\w.-]+)`?")
REPORT_FILE = Path(".claude/state/overseer/complexity-report.md")
NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())
ABSTRACT_BASES = {"ABC", "ABCMeta", "Protocol"}


class BudgetError(Exception):
    """The contract's budget section cannot be used as written."""


@dataclass
class Budget:
    slug: str
    base_commit: str
    limits: dict[str, int]
    justification: str = "none"
    hard: bool = False


@dataclass
class Usage:
    new_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    added_lines: int = 0
    net_new_lines: int = 0
    test_lines: int = 0
    new_public_symbols: list[str] = field(default_factory=list)
    new_abstractions: list[str] = field(default_factory=list)
    new_dependencies: list[str] = field(default_factory=list)
    worst_cyclomatic: list[tuple[int, str]] = field(default_factory=list)
    worst_nesting: list[tuple[int, str]] = field(default_factory=list)
    unparseable: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    """What the hook decides on. `over` is every exceeded limit with the value used; `open` the
    ones no recorded verdict of the simplifier covers."""

    text: str
    exceeded: bool
    slug: str = ""
    base_commit: str = ""
    over: dict[str, int] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    hard: bool = False
    changed_files: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ configuration


def project_env(root: Path) -> dict[str, str]:
    """KEY="value" lines of .claude/project.env; a missing file is an empty config. gate.py owns
    the reading, so the hooks cannot disagree about a value."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate as gate_module

    return gate_module.load_env(root)


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def active_contract(root: Path) -> Path | None:
    """The slice — or the bug record — .engine/PROGRESS.md marks IN PROGRESS: the engine's own convention.
    With no such card, the contract of the slice the session's board task has open."""
    try:
        text = (root / ".engine/PROGRESS.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    blocks = re.split(r"(?m)^(?=#{1,3} )", text)
    for block in blocks:
        if not ACTIVE_RE.search(block):
            continue
        named = CONTRACT_PATH_RE.search(block)
        slug = SLUG_RE.search(block)
        candidate = (
            Path(named.group(0))
            if named
            else (Path(".engine/slices") / f"{slug.group(1)}.md" if slug else None)
        )
        if candidate and (root / candidate).is_file():
            return root / candidate
    # No card names it: the slice the board task has open (gate.active_slice owns that reading, board 789).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate as gate_module

    opened = gate_module.active_slice(root)
    contract = root / ".engine/slices" / f"{opened}.md"
    return contract if opened and contract.is_file() else None


def parse_budget(contract: Path) -> Budget | None:
    """The `## Complexity budget` section as `key: value` lines. None = no such section."""
    text = contract.read_text(encoding="utf-8")
    start = SECTION_RE.search(text)
    if not start:
        return None
    rest = text[start.end() :]
    end = re.search(r"(?m)^## ", rest)
    limits: dict[str, int] = {}
    meta = {"base_commit": "", "justification": "none", "mode": "signal"}
    for raw in (rest[: end.start()] if end else rest).splitlines():
        line = raw.split("#", 1)[0].strip().lstrip("-* ").strip("`")
        if not line or ":" not in line or line.startswith("```"):
            continue
        key, value = (part.strip().strip("`") for part in line.split(":", 1))
        if key not in KNOWN_KEYS:
            # A typo must not silently switch a limit off.
            raise BudgetError(f"unknown budget field '{key}' (known: {', '.join(KNOWN_KEYS)})")
        if key in LIMIT_KEYS:
            if not re.fullmatch(r"\d+", value):
                raise BudgetError(f"{key} must be a whole number, got '{value}'")
            limits[key] = int(value)
        else:
            meta[key] = value
    if not meta["base_commit"]:
        raise BudgetError("base_commit is missing: the budget is measured from that commit")
    if meta["mode"] not in ("signal", "hard"):
        raise BudgetError(f"mode must be 'hard' or 'signal', got '{meta['mode']}'")
    hard = meta["mode"] == "hard" or bool(HARD_TYPE_RE.search(text))
    return Budget(contract.stem, meta["base_commit"], limits, meta["justification"] or "none", hard)


# ------------------------------------------------------------------ measurement


def is_test(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        "tests" in p.parts
        or "test" in p.parts
        or p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or p.name == "conftest.py"
    )


def in_source(path: str, source_dirs: list[str]) -> bool:
    if not source_dirs:
        return path.endswith(".py")
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in source_dirs)


def function_metrics(tree: ast.AST) -> dict[str, tuple[int, int]]:
    """qualified name -> (cyclomatic complexity, nesting depth) for every function.

    Cyclomatic: 1 + one per if / for / while / except / conditional expression /
    comprehension loop and its conditions / match case, plus one per extra operand of
    and/or. Nested functions are measured on their own, not added to their parent."""
    found: dict[str, tuple[int, int]] = {}

    def measure(func: ast.AST) -> tuple[int, int]:
        complexity, deepest = 1, 0

        def walk(node: ast.AST, depth: int) -> None:
            nonlocal complexity, deepest
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
                ):
                    continue
                if isinstance(
                    child,
                    (
                        ast.If,
                        ast.For,
                        ast.AsyncFor,
                        ast.While,
                        ast.ExceptHandler,
                        ast.IfExp,
                        ast.match_case,
                    ),
                ):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
                elif isinstance(child, ast.comprehension):
                    complexity += 1 + len(child.ifs)
                nested = depth + 1 if isinstance(child, NESTING_NODES) else depth
                deepest = max(deepest, nested)
                walk(child, nested)

        walk(func, 0)
        return complexity, deepest

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                found[name] = measure(child)
                visit(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def public_names(tree: ast.Module) -> set[str]:
    return {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not n.name.startswith("_")
    }


def abstractions(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {ast.unparse(b).split(".")[-1].split("[")[0] for b in node.bases}
        bases |= {
            ast.unparse(k.value).split(".")[-1] for k in node.keywords if k.arg == "metaclass"
        }
        abstract_method = any(
            "abstractmethod" in ast.unparse(d)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            for d in item.decorator_list
        )
        if bases & ABSTRACT_BASES or abstract_method:
            names.add(node.name)
    return names


def dependency_names(pyproject_text: str) -> set[str]:
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError:
        return set()
    project = data.get("project", {})
    specs: list[object] = list(project.get("dependencies", []))
    for group in (project.get("optional-dependencies", {}), data.get("dependency-groups", {})):
        for entries in group.values():
            specs.extend(entries)
    names = set()
    for spec in specs:
        if isinstance(spec, str):  # {include-group = "..."} tables add no package
            names.add(
                re.split(r"[\s<>=!~;\[@(]", spec.strip(), maxsplit=1)[0].lower().replace("_", "-")
            )
    return names - {""}


def parse_py(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def measure(root: Path, base: str, source_dirs: list[str], whole: bool = False) -> Usage:
    """`whole` (the hard mode): every changed file counts, not only those under SOURCE_DIRS —
    all but the tests and the engine's own records."""
    usage = Usage()
    status: dict[str, str] = {}
    for line in git(root, "diff", "--name-status", "--no-renames", base).splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            status[parts[1]] = parts[0]
    for path in git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        status.setdefault(path, "A")

    counted, plus = {}, {}
    for line in git(root, "diff", "--numstat", "--no-renames", base).splitlines():
        added, deleted, path = (line.split("\t") + ["", ""])[:3]
        if added.isdigit() and deleted.isdigit():
            counted[path] = int(added) - int(deleted)
            plus[path] = int(added)

    for path, state in sorted(status.items()):
        if whole and not is_test(path):
            if path.startswith(RECORD_DIRS):
                continue
        elif not (in_source(path, source_dirs) or is_test(path)):
            continue
        file = root / path
        net = counted.get(path)
        if not is_test(path):
            usage.changed_files.append(path)
        if state == "D":  # a deletion pays lines back
            if is_test(path):
                usage.test_lines += net or 0
            else:
                usage.net_new_lines += net or 0
            continue
        if net is None:  # untracked: every line is new
            try:
                net = len(file.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                net = 0
        if is_test(path):
            usage.test_lines += net
            continue
        usage.net_new_lines += net
        usage.added_lines += plus.get(path, net)
        if state == "A":
            usage.new_files.append(path)
        if not path.endswith(".py"):
            continue
        now = (
            parse_py(file.read_text(encoding="utf-8", errors="replace")) if file.is_file() else None
        )
        if now is None:
            usage.unparseable.append(path)
            continue
        before = parse_py(git(root, "show", f"{base}:{path}")) if state != "A" else None
        old_public = public_names(before) if before else set()
        old_abstract = abstractions(before) if before else set()
        old_metrics = function_metrics(before) if before else {}
        usage.new_public_symbols += [f"{path}:{n}" for n in sorted(public_names(now) - old_public)]
        usage.new_abstractions += [f"{path}:{n}" for n in sorted(abstractions(now) - old_abstract)]
        for name, (cyclomatic, nesting) in function_metrics(now).items():
            was_c, was_n = old_metrics.get(name, (0, 0))
            if cyclomatic > was_c:  # new, or worse than at base_commit
                usage.worst_cyclomatic.append((cyclomatic, f"{path}:{name}"))
            if nesting > was_n:
                usage.worst_nesting.append((nesting, f"{path}:{name}"))

    for path in (p for p in status if PurePosixPath(p).name == "pyproject.toml"):
        try:
            current = dependency_names((root / path).read_text(encoding="utf-8"))
        except OSError:
            continue
        usage.new_dependencies += sorted(
            current - dependency_names(git(root, "show", f"{base}:{path}"))
        )
    usage.worst_cyclomatic.sort(reverse=True)
    usage.worst_nesting.sort(reverse=True)
    return usage


def function_spans(tree: ast.AST) -> dict[str, tuple[int, int]]:
    """qualified name -> (first line, last line) of every function, decorators included."""
    found: dict[str, tuple[int, int]] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if not isinstance(child, ast.ClassDef):
                    first = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                    found[name] = (first, child.end_lineno or child.lineno)
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def deleted_outside(root: Path, base: str, paths: list[str]) -> list[str]:
    """Code an urgent fix deleted outside the functions it fixes: a deleted file, a function that
    is gone, and any place outside a surviving function where more lines went than came. A line
    replaced by another is an edit, not a deletion. Without a parse (another language) every
    place is "outside": there, a change may not remove more than it adds."""
    found = []
    for path in paths:
        if not (root / path).is_file():
            found.append(f"{path} (the file)")
            continue
        old_text = git(root, "show", f"{base}:{path}")
        if not old_text:
            continue  # a new file: max_new_files answers for it
        old = parse_py(old_text) if path.endswith(".py") else None
        now = parse_py((root / path).read_text(encoding="utf-8", errors="replace")) if old else None
        spans = function_spans(old) if old and now else {}
        kept = [span for name, span in spans.items() if name in function_spans(now)] if now else []
        for name, (first, last) in spans.items():
            if not any(a <= first and last <= b for a, b in kept):
                found.append(f"{path}:{first} (the function {name})")
        old_lines = old_text.splitlines()
        for hunk in HUNK_RE.finditer(git(root, "diff", "-U0", "--no-renames", base, "--", path)):
            start, gone, came = int(hunk.group(1)), int(hunk.group(2) or 1), int(hunk.group(3) or 1)
            outside = [n for n in range(start, start + gone)
                       if old_lines[n - 1 : n] and old_lines[n - 1].strip()
                       and not any(a <= n <= b for a, b in spans.values())]
            if len(outside) > came:
                found.append(f"{path}:{outside[0]}")
    return found


# ------------------------------------------------------------------ verdict


def first_seen_limits(root: Path, budget: Budget) -> tuple[dict[str, int], list[str]]:
    """Limits in force, plus a note for every limit the contract has raised since."""
    memo = root / ".claude" / "state" / "overseer" / f".budget-{budget.slug}.json"
    try:
        remembered = json.loads(memo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        remembered = None
    if not isinstance(remembered, dict) or remembered.get("base_commit") != budget.base_commit:
        try:
            memo.parent.mkdir(parents=True, exist_ok=True)
            memo.write_text(
                json.dumps({"base_commit": budget.base_commit, "limits": budget.limits,
                            "hard": budget.hard}, indent=2)
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return dict(budget.limits), []
    original = {k: int(v) for k, v in remembered.get("limits", {}).items() if k in LIMIT_KEYS}
    in_force, raised = dict(budget.limits), []
    if remembered.get("hard") and not budget.hard:
        budget.hard = True
        raised.append("the card began as an urgent fix (hard mode) and no longer says so — the hard limit stays in force")
    for key, first in original.items():
        if budget.limits.get(key, first) > first:
            in_force[key] = first
            raised.append(
                f"{key}: the contract now says {budget.limits[key]}, the slice began "
                f"with {first} — {first} stays in force"
            )
    return in_force, raised


def default_limits(env: dict[str, str]) -> dict[str, int]:
    """The project's own per-function limits (project.env), for a contract that names none."""
    return {key: int(env[name]) for key, name in ENV_DEFAULTS.items() if env.get(name, "").isdigit()}


def accepted_overruns(root: Path, slug: str, base_commit: str) -> list[tuple[dict[str, int], str]]:
    """Overruns the simplifier ruled justified (`simplifier.py accept` wrote them): per entry,
    the value accepted for each limit, and the reason."""
    try:
        data = json.loads((root / ACCEPTED_DIR / f"accepted-{slug}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or data.get("base_commit") != base_commit:
        return []
    return [
        ({k: int(v) for k, v in e["over"].items()}, str(e.get("reason", "")))
        for e in data.get("entries", [])
        if isinstance(e, dict) and isinstance(e.get("over"), dict)
    ]


def verdict(usage: Usage, limits: dict[str, int]) -> list[tuple[str, int, str]]:
    """Per exceeded limit: the field, the value used, and a line saying what counted."""

    def names(items: list[str]) -> str:
        return ", ".join(items[:6]) + (f" and {len(items) - 6} more" if len(items) > 6 else "")

    used: dict[str, tuple[int, str]] = {
        "max_new_files": (len(usage.new_files), names(usage.new_files)),
        "max_changed_files": (len(usage.changed_files), names(usage.changed_files)),
        "max_added_lines": (usage.added_lines, "lines added, tests not counted"),
        "max_net_new_lines": (usage.net_new_lines, "production code, net of deletions"),
        "max_new_public_symbols": (len(usage.new_public_symbols), names(usage.new_public_symbols)),
        "max_new_abstractions": (len(usage.new_abstractions), names(usage.new_abstractions)),
        "max_new_dependencies": (len(usage.new_dependencies), names(usage.new_dependencies)),
    }
    over = [
        (key, used[key][0], f"{key}: {used[key][0]} used, {limit} allowed ({used[key][1]})")
        for key, limit in limits.items()
        if key in used and used[key][0] > limit
    ]
    for key, worst in (
        ("max_cyclomatic_per_function", usage.worst_cyclomatic),
        ("max_nesting_depth", usage.worst_nesting),
    ):
        limit = limits.get(key)
        bad = [
            f"{where} = {value}" for value, where in worst if limit is not None and value > limit
        ]
        if bad:
            over.append((key, worst[0][0], f"{key}: {limit} allowed, exceeded by {names(bad)}"))
    return over


def report(
    budget: Budget, usage: Usage, over: list[str], raised: list[str],
    accepted: tuple[str, ...] = (),
) -> str:
    # The first line carries the verdict and the fields: it is what a log, a test and a
    # hurried reader see.
    fields = ", ".join(line.split(":", 1)[0] for line in over)
    head = "Complexity budget: exceeded, accepted by the simplifier" if accepted else "Complexity budget: within budget"
    lines = [f"COMPLEXITY BUDGET EXCEEDED: {fields}" if over else head]
    if budget.hard:
        lines = [f"HOTFIX LIMIT EXCEEDED: {fields}" if over else "Hotfix limit: within the limit"]
    lines += [
        f"{'hotfix' if budget.hard else 'slice'} {budget.slug}, measured from {budget.base_commit[:10]} to the working tree",
        (
            f"  production: {len(usage.new_files)} new files, "
            + (f"{len(usage.changed_files)} changed files, +{usage.added_lines} added lines, " if budget.hard else "")
            + f"{usage.net_new_lines:+d} lines, "
            f"{len(usage.new_public_symbols)} new public symbols, "
            f"{len(usage.new_abstractions)} new abstractions, "
            f"{len(usage.new_dependencies)} new dependencies"
        ),
        f"  tests: {usage.test_lines:+d} lines (reported, never limited)",
    ]
    lines += [f"  could not parse: {path}" for path in usage.unparseable]
    lines += [f"  - {line}" for line in over]
    lines += [f"  - accepted: {line}" for line in accepted]
    if raised:
        lines += ["BUDGET RAISED DURING THE SLICE:"] + [f"  - {line}" for line in raised]
    return "\n".join(lines)


CALL_ADVICE = (
    "\n\nThe budget is an expectation, not a ceiling: going over it calls the simplifier. Start "
    "the `simplifier` subagent (fresh context) with the request "
    "`python3 .claude/hooks/simplifier.py request --lens budget` prints, and save its JSON answer "
    "to a file. If it finds nothing to remove or confirm, record its verdict — "
    "`python3 .claude/hooks/simplifier.py accept --reason \"<why the excess is needed>\" "
    "--verdict <file>` — and the turn ends. Otherwise make the change smaller: delete what the "
    "slice contract does not require, inline an abstraction that has a single user, drop the new "
    "dependency, split the function only if that removes branches rather than hides them. "
    "Do not edit the budget: the limits the slice began with stay in force."
)


HARD_ADVICE = (
    "\n\nЦе не термінове виправлення — або зменш, або `/bugfix`.\n"
    "The limit of an urgent fix is hard: the simplifier is not called and no verdict lifts it. "
    "Make the fix smaller, or do the work as a full `/bugfix` (its own record; mark this card's "
    "block in .engine/PROGRESS.md as `became a bugfix`). Do not edit the card's numbers or its type: "
    "the limits it began with stay in force."
)


def evaluate(root: Path, contract: Path | None = None) -> Outcome | None:
    """The verdict for the active slice — or for the contract named; None when there is nothing to enforce."""
    contract = contract or active_contract(root)
    if contract is None:
        return None
    try:
        budget = parse_budget(contract)
    except BudgetError as exc:
        return Outcome(f"Complexity budget of {contract.name} cannot be read: {exc}", True)
    if budget is None:
        return None
    if not git(root, "rev-parse", "--verify", "--quiet", f"{budget.base_commit}^{{commit}}"):
        return Outcome(
            f"Complexity budget of {contract.name}: base_commit '{budget.base_commit}' is "
            "not a commit in this repository",
            True,
        )
    env = project_env(root)
    limits, raised = first_seen_limits(root, budget)
    usage = measure(root, budget.base_commit, source_dirs_of(env), whole=budget.hard)
    if budget.hard:
        limits |= {key: min(limits.get(key, top), top) for key, top in HARD_LIMITS.items()}
    over = verdict(usage, default_limits(env) | limits)
    gone = deleted_outside(root, budget.base_commit, usage.changed_files) if budget.hard else []
    if gone:
        shown = ", ".join(gone[:6]) + (f" and {len(gone) - 6} more" if len(gone) > 6 else "")
        over.append((DELETED_OUTSIDE, len(gone), f"{DELETED_OUTSIDE}: code deleted outside the functions being fixed — {shown}"))
    entries = [] if budget.hard else accepted_overruns(root, budget.slug, budget.base_commit)
    open_lines, accepted = [], []
    for key, used, line in over:
        reasons = [reason for values, reason in entries if values.get(key, -1) >= used]
        if reasons:
            accepted.append(f"{line} — {reasons[-1]}")
        else:
            open_lines.append(line)
    text = report(budget, usage, open_lines, raised, tuple(accepted))
    if budget.hard and open_lines:
        text += HARD_ADVICE
    return Outcome(text, bool(open_lines), budget.slug, budget.base_commit,
                   {key: used for key, used, _ in over}, [line for _, _, line in over],
                   budget.hard, usage.changed_files)


def hard_card(root: Path) -> bool:
    """Whether the active contract is an urgent fix's card — as it reads now, or as it was first seen."""
    contract = active_contract(root)
    if contract is None:
        return False
    try:
        if HARD_TYPE_RE.search(contract.read_text(encoding="utf-8")):
            return True
        budget = parse_budget(contract)
    except (OSError, BudgetError):
        return False
    if budget is None or budget.hard:
        return budget is not None
    memo = root / ".claude" / "state" / "overseer" / f".budget-{budget.slug}.json"
    try:
        return bool(json.loads(memo.read_text(encoding="utf-8")).get("hard"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def source_dirs_of(env: dict[str, str]) -> list[str]:
    return [d for d in re.split(r"[\s,]+", env.get("SOURCE_DIRS", "")) if d]


# ------------------------------------------------------------------ entry points


def project_root() -> Path:
    given = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if given and Path(given).is_dir():
        return Path(given)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def record_in_gate_format(root: Path, mode: str, text: str, exceeded: bool) -> None:
    """Also write the verdict in gate.py's report schema (.claude/state/gate/<source>-report.json).

    This script stays separate from gate.py — it reads the slice contract and its own state — but
    one format means one reader. Never lets a reporting problem change the verdict."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gate as gate_module

        severity = ("warn" if mode == "warn" else "block") if exceeded else "log"
        gate_module.record_findings(
            root, "complexity_budget", "stop",
            [gate_module.Finding(None, None, "complexity-budget", severity, text.splitlines()[0],
                                 f"see {REPORT_FILE}")],
        )
    except (ImportError, OSError):
        pass


def run_hook() -> int:
    raw = sys.stdin.read()
    root = project_root()
    hard = hard_card(root)  # an urgent fix: no switch turns its limit off, and no re-entry
    # Same loop guard as verify-on-stop.sh: a turn the hook itself started is not re-judged.
    if re.search(r'"stop_hook_active"\s*:\s*true', raw) and not hard:
        return 0
    gate = project_env(root).get("COMPLEXITY_GATE", "off").lower()
    if gate not in ("warn", "call", "block") and not hard:
        return 0
    outcome = evaluate(root)
    if outcome is None:
        return 0
    text, exceeded = outcome.text, outcome.exceeded
    try:
        (root / REPORT_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / REPORT_FILE).write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    record_in_gate_format(root, "call" if outcome.hard else gate, text, exceeded)
    if not exceeded:
        return 0
    if outcome.hard:
        print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
    elif gate != "warn":
        print(json.dumps({"decision": "block", "reason": text + CALL_ADVICE}))
    else:
        print(
            json.dumps(
                {
                    "systemMessage": "Complexity budget exceeded (warn mode, not blocking) "
                    f"— see {REPORT_FILE}"
                }
            )
        )
    return 0


def run_validate(contract: Path) -> int:
    try:
        budget = parse_budget(contract)
    except (OSError, BudgetError) as exc:
        print(f"INVALID: {exc}")
        return 1
    if budget is None:
        print("INVALID: the contract has no '## Complexity budget' section")
        return 1
    problems = []
    root = project_root()
    if not git(root, "rev-parse", "--verify", "--quiet", f"{budget.base_commit}^{{commit}}"):
        problems.append(f"base_commit '{budget.base_commit}' is not a commit in this repository")
    for key in ("max_new_files", "max_new_dependencies", "max_cyclomatic_per_function"):
        if key not in budget.limits:
            problems.append(f"{key} is missing — the three core limits are required")
    if budget.limits.get("max_new_dependencies", 0) > 0 and budget.justification.lower() in (
        "",
        "none",
    ):
        problems.append(
            "max_new_dependencies above 0 needs a justification (a goal id or a reason)"
        )
    if budget.limits.get("max_new_abstractions", 0) > 0 and budget.justification.lower() in (
        "",
        "none",
    ):
        problems.append(
            "max_new_abstractions above 0 needs a justification naming the two "
            "existing users of each abstraction"
        )
    for problem in problems:
        print(f"INVALID: {problem}")
    if not problems:
        print(f"OK: {len(budget.limits)} limits, measured from {budget.base_commit[:10]}")
    return 1 if problems else 0


def percentile(values: list[int], percent: int) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, (len(ordered) * percent) // 100)] if ordered else 0


def project_functions(root: Path) -> dict[str, tuple[int, int]]:
    """`path:function` -> (cyclomatic, nesting) for every production function git tracks."""
    env = project_env(root)
    source_dirs = source_dirs_of(env)
    excluded = [d for d in re.split(r"[\s,]+", env.get("SIMPLIFY_EXCLUDE", "")) if d]
    found: dict[str, tuple[int, int]] = {}
    for path in git(root, "ls-files", "*.py").splitlines():
        if is_test(path) or not in_source(path, source_dirs) or (excluded and in_source(path, excluded)):
            continue
        try:
            tree = parse_py((root / path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            tree = None
        for name, metrics in (function_metrics(tree) if tree else {}).items():
            found[f"{path}:{name}"] = metrics
    return found


def run_calibrate(root: Path) -> int:
    """Propose the default per-function limits from the functions the project already has: the
    90th percentile, never under the floor. A proposal — `set-defaults` applies it."""
    functions = project_functions(root)
    if not functions:
        print("no production functions found: nothing to calibrate on")
        return 1
    print(f"{len(functions)} functions measured (production code git tracks, tests excluded)\n")
    print("| metric | p50 | p75 | p90 | p95 | max | proposed | functions already above it |")
    print("|---|---|---|---|---|---|---|---|")
    proposed = []
    for index, key in enumerate(ENV_DEFAULTS):
        values = [metrics[index] for metrics in functions.values()]
        limit = max(percentile(values, 90), CALIBRATION_FLOOR[key])
        proposed.append(limit)
        cells = [percentile(values, p) for p in (50, 75, 90, 95)] + [max(values), limit, sum(v > limit for v in values)]
        print(f"| {ENV_DEFAULTS[key]} | " + " | ".join(str(c) for c in cells) + " |")
    print("\nOnly a function a change adds or makes worse is measured against the limit.")
    print(f"Apply (the owner, in their own terminal):\n\n    python3 .claude/hooks/complexity_budget.py set-defaults {proposed[0]} {proposed[1]}")
    return 0


def run_set_defaults(root: Path, values: list[str]) -> int:
    """The owner's command. Hooks do not see what a script runs, so the check is here."""
    if os.environ.get("CLAUDECODE"):
        print("complexity_budget: set-defaults is the owner's command and is refused inside a Claude "
              "Code session (CLAUDECODE is set). Run it in your own terminal.", file=sys.stderr)
        return 2
    if len(values) != 2 or not all(v.isdigit() and int(v) > 0 for v in values):
        print("usage: complexity_budget.py set-defaults <max cyclomatic> <max nesting>", file=sys.stderr)
        return 2
    path = root / ".claude" / "project.env"
    names = set(ENV_DEFAULTS.values())
    kept = [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.split("=", 1)[0].strip() not in names]
    kept += [f'{name}="{value}"' for name, value in zip(ENV_DEFAULTS.values(), values, strict=True)]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"written to {path.relative_to(root)}: " + ", ".join(kept[-2:]))
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "hook":
        return run_hook()
    if command == "check":
        outcome = evaluate(project_root())
        print(outcome.text if outcome else "no active slice with a complexity budget")
        return 1 if outcome and outcome.exceeded else 0
    if command == "calibrate":
        return run_calibrate(project_root())
    if command == "set-defaults":
        return run_set_defaults(project_root(), sys.argv[2:])
    if command == "validate" and len(sys.argv) == 3:
        return run_validate(Path(sys.argv[2]))
    print((__doc__ or "").split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
