#!/usr/bin/env python3
"""gate.py — the one gate script. Four layers, one report, one place for the settings.

    python3 .claude/hooks/gate.py --layer post_write --files src/a.py
    python3 .claude/hooks/gate.py --layer stop                       # the files this turn changed
    python3 .claude/hooks/gate.py --layer pre_commit                 # the whole project, staged diff
    python3 .claude/hooks/gate.py --layer ci [--diff origin/main]    # the whole project
    ... --hook      speak Claude Code's hook protocol (stdin envelope, JSON on stdout)

Layers
    post_write  format one file, then a quick lint of it. NEVER blocks; what changed is shown to
                the model as additionalContext, and only when there is something to show.
    stop        quick, incremental: lint and types on the files the turn changed, tests that map
                to them. Reads `stop_hook_active` first. Counts consecutive blocks; on the Nth it
                lets the turn end and parks the item for a human (GATE_MAX_BLOCKS, default 3):
                in a project with a task board the question is a task in tasks/blocked/, and
                the owner's answer «так» there closes it; without a board, a parked.md entry.
                During a rebase or a merge no file is written to the board (board 065): the
                escalation goes to the anomaly journal, and its question is asked when that is
                over — by the next stop run or by `gate.py --ask-waiting` (the board runner).
                Also refuses to be passed by silencing: see "bypass guard".
    pre_commit  the full set on the staged change (what a git pre-commit hook runs).
    ci          the full set (what a pipeline runs). No workflow file ships; see
                .claude/references/gate.md.

Exit code: 0 = no `block` finding, 2 = at least one. With --hook a Stop block is instead the
JSON {"decision":"block","reason":...} on stdout with exit 0 (the protocol every baseline pins);
the report's `exit_code` is always the CLI value.

Report: .claude/state/gate/last-report.json — file, line, rule, severity (block|warn|log),
message, hint per finding, plus timings per step. post_write writes it only when it has
something to say, so a clean edit does not overwrite the verdict of the last real gate. A
concise list of the most important findings goes to stderr.

Settings stay in .claude/project.env: CODE_EXTENSIONS, PROJECT_MARKER, LINT_CMD, TYPECHECK_CMD,
TEST_CMD, FORMAT_CMD, and the optional keys TEST_CMD_FULL (pre_commit / ci only), GATE_MAX_BLOCKS,
DELETE_GUARD_LINES and COVERAGE_CMD.

AN INSTALL NOT YET COMMITTED (stop, pre_commit; board 786). `engine.py install` never commits, so
until the owner's first commit the engine's own files are untracked and would read as the turn's
work. A file that the base lacks AND that is byte for byte what .claude/engine-lock.json recorded
(an engine file, or a seeded one as it was seeded) is left out of everything below; one changed byte,
or a file the base already has, and it is judged like any other — a seeded file (project.env)
against the seed it started from, so only the keys really changed are named. See installed.py.

BYPASS GUARD (stop, pre_commit). A block when the turn's diff ADDS a `# type: ignore`, a `# noqa`,
a pytest skip / skipif / xfail, or CHANGES the linter's or the type checker's configuration
(the parsed [tool.ruff] / [tool.mypy] of pyproject.toml, ruff.toml, mypy.ini, and the gate's own
keys in project.env) — unless the justification stands next to it:
    # gate-allow: <reason>           same line, or the comment-only line directly above
(any added line of a config file) or the slice contract (.engine/slices/*.md) says
    gate-allow: <type-ignore|noqa|skip|xfail|config path> — <reason>
A change of PROJECT_MARKER, CODE_EXTENSIONS, DELETE_GUARD_LINES or PUSH_PROTECTED_BRANCHES in
project.env passes one way only: the sealed slice contract names the key (`gate-allow: PROJECT_MARKER — <reason>`); a reason in project.env itself or
a grant of the whole file is not enough.
A reason is at least 12 characters and two words. Syntax only: comments come from the tokenizer,
marks from the AST, configuration from the parsed tables — a string that merely mentions them
is not a finding. The guard calls no tool, so it runs whether or not PROJECT_MARKER exists; a
missing marker skips only lint, types and tests.

THE SKETCH'S QUARANTINE (stop, pre_commit, ci; board 099). Code under `sketches/` is a sketch's (the mode
ескіз): the gates do not check it — no lint, types, tests or guard; on the full layers the default ruff, mypy
and pytest, which go over `.`, are told to leave the root's sketches/ out (a project's own LINT_CMD,
TYPECHECK_CMD, TEST_CMD must do that itself: docs/engine-limits.md). Two blocks instead: a task in
ескіз (its mode as mode.py reads it) that changed a file outside sketches/, .engine/ and tasks/; and,
in any mode, working code that refers to a sketch — a Python import of `sketches`, a string holding a
path into a named sketch (`../../sketches/<name>`, `"$ROOT/sketches/<name>"`, `"bash sketches/<name>/run.sh"`), or such a
path on an added line of another language (a JavaScript import, a shell command).
The records under .engine/ and tasks/ are not working code, whatever CODE_EXTENSIONS says. Tests are not looked at (they hold sketch paths as data); a reference built at run time, or code
rewritten by hand from a sketch, is not seen (docs/engine-limits.md).

THE SNAPSHOT (stop, pre_commit, ci). With `.engine/baseline.json` (baseline.py) the question is
"no worse than it was", not "clean": a failing test blocks only when it is not on the snapshot's
list, a lint or type finding only when the count of its (file, rule) is above the recorded one.
A failure whose output names no test and no `file:line: message` blocks as before. Without the
file nothing changes. The bypass guard also watches the snapshot: a diff that adds a test to the
list or raises a count blocks unless the owner's `baseline.py record` approved exactly that text.

THE DELETE GUARD (stop, pre_commit). A block when the diff deletes a function, a class or a file
of working code, or more than DELETE_GUARD_LINES lines (default 20) inside one function, and no
test touched that code. A move within the same change is not a deletion. Through: a test; a
simplifier finding the owner confirmed; `gate-allow: delete — <reason>` in a sealed contract.
See delete_guard.py.

THE GUARDED FILES (stop; board 724). Before anything is skipped — a turn that changed no code, a
stop another hook forced — the constitution, the settings, `.engine/rules.md`, migrations and CI
workflows are compared with the snapshot taken when the turn began. A file that differs is put
back by the gate itself, the discarded change kept as a patch, the anomaly journal written, and
the turn blocked once so that the agent reads it. See protected_guard.py.

Standard library only; Python 3.11+. The linters are external commands.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tokenize
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LAYERS = ("post_write", "stop", "pre_commit", "ci")
SEVERITIES = ("block", "warn", "log")
SCHEMA = 1
DEFAULT_MAX_BLOCKS = 3
STEP_TIMEOUT_S = 900
REPORT_REL = Path(".claude/state/gate/last-report.json")
COUNT_REL = Path(".claude/state/gate/stop-count.json")
PARKED_REL = Path(".engine/overseer/parked.md")
NO_SLICE = "(none)"
ESCALATIONS_REL = Path(".claude/state/gate/escalations.json")
BASELINE_FILE = ".engine/baseline.json"
SNAPSHOT_PART = {"lint": "lint", "typecheck": "types", "tests": "tests"}
TAIL_LINES = {"lint": 30, "typecheck": 30, "tests": 40}
HEADINGS = {"lint": "LINT FAILED", "typecheck": "TYPECHECK FAILED", "tests": "TESTS FAILED"}
GATE_KEYS = ("LINT_CMD", "TYPECHECK_CMD", "TEST_CMD", "TEST_CMD_FULL", "FORMAT_CMD", "GATE_MAX_BLOCKS",
             "COMPLEXITY_MAX_CYCLOMATIC", "COMPLEXITY_MAX_NESTING", "COVERAGE_CMD")
# These decide WHETHER a check runs at all, so a reason written by the work being judged is not
# enough: only a sealed slice contract that names the key lets the change through.
SCOPE_KEYS = {
    "PROJECT_MARKER": "it decides whether lint, types and tests run at all",
    "CODE_EXTENSIONS": "it decides whether lint, types and tests run at all",
    "DELETE_GUARD_LINES": "it decides how much untested code may be deleted unseen",
    "PUSH_PROTECTED_BRANCHES": "it decides which branches block-dangerous.sh refuses a push into",
}
CONFIG_BASENAMES = ("ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini")
SKIP_NAMES = {
    "pytest.mark.skip": "skip",
    "pytest.mark.skipif": "skip",
    "pytest.skip": "skip",
    "mark.skip": "skip",
    "mark.skipif": "skip",
    "pytest.mark.xfail": "xfail",
    "pytest.xfail": "xfail",
    "mark.xfail": "xfail",
}
SUPPRESSIONS = (
    ("type-ignore", re.compile(r"#\s*type:\s*ignore", re.IGNORECASE)),
    ("noqa", re.compile(r"#\s*(?:\w+:\s*)?noqa", re.IGNORECASE)),
)
ALLOW_RE = re.compile(r"gate-allow:\s*(?P<reason>.*\S)", re.IGNORECASE)
CONTRACT_ALLOW_RE = re.compile(
    r"^\s*gate-allow:\s*(?P<what>[\w./-]+)\s+[—–-]+\s+(?P<reason>\S.*)$", re.IGNORECASE | re.MULTILINE
)
DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>[^\s:][^:\n]*\.py):(?P<line>\d+)(?::\d+)?:?\s+(?P<msg>.+)$", re.MULTILINE
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@", re.MULTILINE)


@dataclass
class Finding:
    file: str | None
    line: int | None
    rule: str
    severity: str
    message: str
    hint: str = ""


@dataclass
class Report:
    layer: str
    root: Path
    source: str = "gate"
    findings: list[Finding] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    steps_ms: dict[str, int] = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)
    started_utc: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def blocked(self) -> bool:
        return any(f.severity == "block" for f in self.findings)

    @property
    def exit_code(self) -> int:
        return 2 if self.blocked else 0

    def as_json(self, result: str) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "source": self.source,
            "layer": self.layer,
            "started_utc": self.started_utc,
            "finished_utc": utc_now(),
            "result": result,
            "exit_code": self.exit_code,
            "files": self.files,
            "findings": [asdict(f) for f in self.findings],
            "timings_ms": {
                "total": int((time.perf_counter() - self.started) * 1000),
                "steps": self.steps_ms,
            },
            **self.extra,
        }


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ project, settings, git


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else Path.cwd()


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[match.group(1)] = value
    return values


def load_env(root: Path) -> dict[str, str]:
    try:
        return parse_env_text((root / ".claude" / "project.env").read_text(encoding="utf-8"))
    except OSError:
        return {}


def code_extensions(env: dict[str, str]) -> list[str]:
    tokens = env.get("CODE_EXTENSIONS", "").replace(",", " ").split()
    return [t.lstrip(".").lower() for t in tokens if t.lstrip(".")]


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def has_head(root: Path) -> bool:
    return git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def lines_of(proc: subprocess.CompletedProcess[str]) -> list[str]:
    return [ln for ln in proc.stdout.splitlines() if ln.strip()] if proc.returncode == 0 else []


def changed_files(root: Path, layer: str, diff_ref: str | None) -> list[str]:
    """Files the turn changed: index and working tree against HEAD, plus untracked files."""
    names: set[str] = set()
    if layer == "pre_commit":
        names.update(lines_of(git(root, "diff", "--name-only", "--cached", "--diff-filter=ACMR")))
    elif diff_ref:
        names.update(lines_of(git(root, "diff", "--name-only", "--diff-filter=ACMR", diff_ref)))
    else:
        names.update(lines_of(git(root, "diff", "--name-only", "HEAD")))
        names.update(lines_of(git(root, "diff", "--name-only", "--cached")))
        names.update(lines_of(git(root, "ls-files", "--others", "--exclude-standard")))
    return sorted(n for n in names if (root / n).is_file())


def added_lines(root: Path, layer: str, rel: str, diff_ref: str | None) -> set[int] | None:
    """Line numbers this diff adds to `rel`; None means "every line" (a file with no base)."""
    if layer == "pre_commit":
        base = ["diff", "--cached", "-U0", "--no-color"]
    elif diff_ref:
        base = ["diff", diff_ref, "-U0", "--no-color"]
    elif has_head(root):
        base = ["diff", "HEAD", "-U0", "--no-color"]
    else:
        return None
    if layer != "pre_commit" and git(root, "ls-files", "--error-unmatch", "--", rel).returncode != 0:
        return None
    out = git(root, *base, "--", rel)
    if out.returncode != 0:
        return None
    new_in_head = layer != "pre_commit" and not diff_ref and has_head(root)
    if new_in_head and git(root, "cat-file", "-e", f"HEAD:{rel}").returncode != 0:
        return None
    added: set[int] = set()
    for hunk in HUNK_RE.finditer(out.stdout):
        start = int(hunk.group("start"))
        count = 1 if hunk.group("count") is None else int(hunk.group("count"))
        added.update(range(start, start + count))
    return added


def old_text(root: Path, layer: str, rel: str, diff_ref: str | None) -> str | None:
    ref = diff_ref or "HEAD"
    if layer == "pre_commit":
        ref = "HEAD"
    out = git(root, "show", f"{ref}:{rel}")
    return out.stdout if out.returncode == 0 else None


def new_text(root: Path, layer: str, rel: str) -> str | None:
    if layer == "pre_commit":
        out = git(root, "show", f":{rel}")
        return out.stdout if out.returncode == 0 else None
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ------------------------------------------------------------------ running commands


def run_shell(root: Path, command: str) -> tuple[int, str, int]:
    """Run `command` through bash with stderr merged into stdout (one stream, nothing clobbered)."""
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=STEP_TIMEOUT_S,
            check=False,
        )
        rc, out = proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        rc, out = 124, f"timed out after {STEP_TIMEOUT_S} s"
    return rc, out, int((time.perf_counter() - started) * 1000)


LOCK_RUNNERS = (("uv.lock", "uv", "uv run "), ("poetry.lock", "poetry", "poetry run "))
RUNNER_TIMEOUT_S = 60
WHICH = "import shutil, sys; print(shutil.which(sys.argv[1]) or '')"


def tool_prefix(root: Path, tool: str | None = None) -> str:
    """The lockfile runner of the project, or "". With `tool`: only when the runner really starts
    the project's own copy of it. A lockfile pins nothing for a tool it does not name, and naming
    is not enough either — for a tool locked in an extra or a group that is not installed,
    `uv run` starts whatever PATH holds (board 108, the overseers on board 107)."""
    for lock, runner, prefix in LOCK_RUNNERS:
        if (root / lock).is_file() and shutil.which(runner) and (
                tool is None or (lock_names(root / lock, tool) and runner_has(root, prefix, tool))):
            return prefix
    return ""


def lock_names(lock: Path, tool: str) -> bool:
    """The lockfile has a package of this name (uv.lock and poetry.lock both write `name = "<package>"`)."""
    try:
        text = lock.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return re.search(rf'^name\s*=\s*"{re.escape(tool)}"\s*$', text, re.MULTILINE | re.IGNORECASE) is not None


def runner_has(root: Path, prefix: str, tool: str) -> bool:
    """The runner finds the tool somewhere PATH alone does not: in the project's environment.
    The same file as on PATH (or none) means the runner would only pass the call through."""
    try:
        out = subprocess.run([*prefix.split(), "python", "-c", WHICH, tool], cwd=root, capture_output=True,
                             text=True, timeout=RUNNER_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    found = out.stdout.strip().splitlines()[-1].strip() if out.returncode == 0 and out.stdout.strip() else ""
    outside = shutil.which(tool)
    return bool(found) and (outside is None or os.path.realpath(found) != os.path.realpath(outside))


def tool_versions_module() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tool_versions

    return tool_versions


def check_tool(root: Path, tool: str) -> tuple[str | None, str]:
    """The shell text that starts a check tool of the default commands, and "" — or None and why.
    The project's own version when it pins one (a lockfile runner that really starts its own copy,
    its virtual environment), else the engine's (tool_versions.py, board 107): a tool on PATH of that version, else uvx."""
    prefix = tool_prefix(root, tool)
    if prefix:
        return f"{prefix}{tool}", ""
    versions = tool_versions_module()
    own = versions.project_tool(root, tool)
    if own:
        return shlex.quote(own), ""
    argv, why = versions.command(tool)
    if argv is None:
        return None, why
    return (tool if argv == [shutil.which(tool)] else " ".join(shlex.quote(a) for a in argv)), ""


def edit_ruff(root: Path) -> tuple[list[str] | None, str]:
    """ruff for the edit-time layer (the formatter, the quick lint), never fetched: the project's
    own, else one on PATH of the engine's version. None and "" when there is none at all; None and
    why when there is only another version — that one neither formats nor lints (board 107)."""
    prefix = tool_prefix(root, "ruff").split()
    if prefix:
        return prefix + ["ruff"], ""
    versions = tool_versions_module()
    own = versions.project_tool(root, "ruff")
    if own:
        return [own], ""
    on_path = shutil.which("ruff")
    if not on_path:
        return None, ""
    found = versions.installed_version(on_path)
    if found == versions.VERSIONS["ruff"]:
        return [on_path], ""
    return None, (f"ruff on PATH is {found or 'of a version it does not print'}, the engine's is "
                  f"{versions.VERSIONS['ruff']} (.claude/hooks/tool_versions.py): not formatted, not linted")


def pyproject_has(root: Path, table: str) -> bool:
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^\s*\[{re.escape(table)}[.\]]", text, re.MULTILINE) is not None


def quoted(files: list[str]) -> str:
    return " ".join(shlex.quote(f) for f in files)


def record_step(report: Report, kind: str, command: str, rc: int, out: str, ms: int) -> None:
    report.steps_ms[kind] = report.steps_ms.get(kind, 0) + ms
    if rc == 0:
        return
    tail = "\n".join(out.strip().splitlines()[-TAIL_LINES[kind]:])
    report.reasons.append(f"{HEADINGS[kind]} ({command}):\n{tail}")
    seen = 0
    for match in DIAGNOSTIC_RE.finditer(out):
        if seen >= 20:
            break
        seen += 1
        report.add(Finding(match["file"], int(match["line"]), kind, "block", match["msg"].strip(),
                           f"re-run: {command}"))
    if not seen:
        last = (out.strip().splitlines() or [f"exit {rc}"])[-1]
        report.add(Finding(None, None, kind, "block", f"{HEADINGS[kind]}: {last}",
                           f"re-run: {command}"))


# ------------------------------------------------------------------ bypass guard


def comment_map(text: str) -> dict[int, str] | None:
    comments: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    return comments


def dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def valid_reason(reason: str) -> bool:
    return len(reason) >= 12 and len(reason.split()) >= 2


def justified(line: int, comments: dict[int, str], source_lines: list[str]) -> bool:
    candidates = [comments.get(line)]
    if line >= 2 and source_lines[line - 2].lstrip().startswith("#"):
        candidates.append(comments.get(line - 1))
    for comment in candidates:
        match = ALLOW_RE.search(comment or "")
        if match and valid_reason(match["reason"].strip()):
            return True
    return False


def contract_grants(root: Path) -> dict[str, tuple[str, str]]:
    """What the SEALED slice contracts exempt: kind or path -> (contract file name, reason)."""
    grants: dict[str, tuple[str, str]] = {}
    for contract in sorted((root / ".engine" / "slices").glob("*.md")):
        # Only a SEALED contract speaks: the fingerprint written at approval must match, so the
        # party the guard judges cannot grant itself an exemption by editing a slice file.
        seal = root / ".claude" / "state" / "contracts" / f"{contract.stem}.sha256"
        try:
            text = contract.read_text(encoding="utf-8")
            recorded = seal.read_text(encoding="utf-8").split()[0]
        except (OSError, IndexError):
            continue
        if recorded != hashlib.sha256(text.encode("utf-8")).hexdigest():
            continue
        for match in CONTRACT_ALLOW_RE.finditer(text):
            if valid_reason(match["reason"].strip()):
                grants[match["what"].lower()] = (contract.name, match["reason"].strip())
    return grants


def guard_python(
    rel: str, text: str, added: set[int] | None, allowed: dict[str, tuple[str, str]], report: Report
) -> None:
    comments = comment_map(text)
    if comments is None:
        report.add(Finding(rel, None, "bypass/unparsed", "log",
                           "not tokenizable, bypass guard skipped for this file"))
        return
    source_lines = text.splitlines()
    hits: list[tuple[str, int]] = []
    for line, comment in comments.items():
        if added is not None and line not in added:
            continue
        for kind, pattern in SUPPRESSIONS:
            if pattern.search(comment):
                hits.append((kind, line))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and dotted(node) in SKIP_NAMES:
                line = node.lineno
                if added is None or line in added:
                    hits.append((SKIP_NAMES[dotted(node)], line))
    for kind, line in sorted(hits, key=lambda h: h[1]):
        if kind in allowed or justified(line, comments, source_lines):
            report.add(Finding(rel, line, f"bypass/{kind}", "log", f"new {kind}, justified"))
            continue
        report.add(Finding(
            rel, line, f"bypass/{kind}", "block",
            f"the diff adds a {kind} — the gate is passed by silencing it, not by fixing the code",
            "fix the cause; or put `# gate-allow: <why, two words at least>` on this line or the "
            "comment line above; or the slice contract may carry "
            f"`gate-allow: {kind} — <reason>`",
        ))


def toml_tools(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    tool = data.get("tool", {})
    return {k: tool[k] for k in ("ruff", "mypy") if k in tool}


def config_justified(text: str | None, added: set[int] | None) -> bool:
    if text is None:
        return False
    for number, line in enumerate(text.splitlines(), start=1):
        if added is not None and number not in added:
            continue
        match = ALLOW_RE.search(line)
        if match and valid_reason(match["reason"].strip()):
            return True
    return False


def changed_keys(old: str | None, new: str | None, keys: tuple[str, ...]) -> list[str]:
    # Unset and empty mean the same to every reader of these keys.
    before, after = parse_env_text(old or ""), parse_env_text(new or "")
    return [k for k in keys if before.get(k, "") != after.get(k, "")]


def scope_values(text: str | None) -> dict[str, str]:
    env = parse_env_text(text or "")
    values = {key: env.get(key, "") for key in SCOPE_KEYS}
    values["DELETE_GUARD_LINES"] = str(delete_guard_module().threshold(env))
    # The hook's own reading (block-dangerous.sh): spaces or commas, empty means main and stable.
    values["PUSH_PROTECTED_BRANCHES"] = " ".join(sorted(set(values["PUSH_PROTECTED_BRANCHES"].replace(",", " ").split()))) or "main stable"
    return values


def guard_scope_keys(rel: str, old: str | None, new: str | None, allowed: dict[str, tuple[str, str]], report: Report) -> None:
    # Unset and empty mean the same to every reader of these keys (for the delete guard's
    # threshold: the default), so dropping an empty line or writing the default is not a change.
    before, after = scope_values(old), scope_values(new)
    for key in (k for k in SCOPE_KEYS if before[k] != after[k]):
        if key.lower() in allowed:
            report.add(Finding(rel, None, "bypass/config", "log",
                               f"{key} changed, allowed by the slice contract {allowed[key.lower()][0]}"))
            continue
        report.add(Finding(
            rel, None, "bypass/config", "block",
            f"the diff changes {key} — {SCOPE_KEYS[key]}, and the work being judged may not decide that",
            f"restore {key}; the change passes only when the sealed slice contract carries "
            f"`gate-allow: {key} — <reason>` (a reason in {rel} itself, or a grant of the whole file, "
            "is not enough)",
        ))


def guard_config(
    root: Path, layer: str, rel: str, diff_ref: str | None, allowed: dict[str, tuple[str, str]],
    added: set[int] | None, report: Report,
) -> None:
    old, new = old_text(root, layer, rel, diff_ref), new_text(root, layer, rel)
    if old is None:
        # Seeded by an install nobody has committed yet: the base is the seed, not nothing (board 786).
        old = installed_module().seed_text(root, rel, None if layer == "pre_commit" else diff_ref)
    if rel == BASELINE_FILE:
        guard_baseline(root, rel, old, new, report)
        return
    base = Path(rel).name
    changed: str | None = None
    if base == "pyproject.toml":
        before, after = toml_tools(old), toml_tools(new)
        if before is not None and after is not None and before != after:
            changed = "the [tool.ruff] / [tool.mypy] settings"
    elif base in CONFIG_BASENAMES:
        if old != new:
            changed = "the linter / type-checker configuration"
    elif rel == ".claude/project.env":
        guard_scope_keys(rel, old, new, allowed, report)
        keys = changed_keys(old, new, GATE_KEYS)
        if keys:
            changed = f"the gate's own settings ({', '.join(keys)})"
    if changed is None:
        return
    if rel.lower() in allowed or base.lower() in allowed or config_justified(new, added):
        report.add(Finding(rel, None, "bypass/config", "log", f"{changed} changed, justified"))
        return
    report.add(Finding(
        rel, None, "bypass/config", "block",
        f"the diff changes {changed} — a gate that can be re-tuned by the work it judges proves nothing",
        "if the change is meant: add a line `gate-allow: <why, two words at least>` among the "
        f"added lines of {rel}, or put `gate-allow: {rel} — <reason>` in the slice contract",
    ))


def baseline_module() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import baseline

    return baseline


def delete_guard_module() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import delete_guard

    return delete_guard


def delete_guard(root: Path, layer: str, diff_ref: str | None, env: dict[str, str], report: Report) -> None:
    """Code no test touched is not deleted in silence (delete_guard.py): a function, a class, a file,
    or more than DELETE_GUARD_LINES lines inside one function."""
    for item in delete_guard_module().check(root, layer, diff_ref, env, contract_grants(root)):
        finding = Finding(**item)
        report.add(finding)
        if finding.severity == "block":
            where = f"{finding.file}:{finding.line}" if finding.line else str(finding.file)
            report.reasons.append(f"DELETE GUARD {where} [{finding.rule}] {finding.message}. {finding.hint}")


def protected_guard_module() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import protected_guard

    return protected_guard


def installed_module() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import installed

    return installed


def without_install(root: Path, layer: str, files: list[str], diff_ref: str | None, report: Report) -> list[str]:
    """`files` less the engine's own files of an install nobody has committed yet (installed.py,
    board 786): not in the base, byte for byte what engine-lock.json recorded — no turn's work."""
    if layer not in ("stop", "pre_commit"):
        return files
    if layer == "pre_commit":
        untouched = installed_module().as_installed(root, files, index=True)
    else:
        untouched = installed_module().as_installed(root, files, ref=diff_ref)
    if untouched:
        report.add(Finding(None, None, "installed", "log",
                           f"{len(untouched)} file(s) are the engine's install as engine-lock.json recorded it, "
                           "not yet committed — not judged"))
    return [f for f in files if f not in untouched]


def add_guarded(report: Report, found: list[dict[str, Any]]) -> None:
    """What protected_guard.py found (and already put back) goes into the report the turn is judged by."""
    for item in found:
        finding = Finding(**item)
        report.add(finding)
        report.reasons.append(f"GUARDED FILE {finding.file} [{finding.rule}] {finding.message}. {finding.hint}")


def deleted_code(root: Path, layer: str, diff_ref: str | None, env: dict[str, str]) -> list[str]:
    """Working-code files the change removed: `changed_files` lists only what still exists."""
    args = ["--cached"] if layer == "pre_commit" else [diff_ref or "HEAD"]
    gone = lines_of(git(root, "diff", "--name-only", "--diff-filter=D", *args))
    return [rel for rel in gone if delete_guard_module().is_working_code(env, rel)]


def guard_baseline(root: Path, rel: str, old: str | None, new: str | None, report: Report) -> None:
    """The snapshot only shrinks. A diff that adds a test to its list or raises a count loosens the
    gate; it passes one way only — the owner's `baseline.py record` approved exactly this text."""
    snapshot = baseline_module()
    looser = snapshot.loosened(old, new)
    if not looser:
        return
    if snapshot.sealed(root, new):
        report.add(Finding(rel, None, "bypass/baseline", "log",
                           f"the snapshot was loosened ({len(looser)} entr(ies)), approved by the owner's record"))
        return
    shown = "; ".join(looser[:5]) + (f"; and {len(looser) - 5} more" if len(looser) > 5 else "")
    report.add(Finding(
        rel, None, "bypass/baseline", "block",
        f"the diff loosens the snapshot ({shown}) — the gate is passed by calling the new failure old",
        f"restore {rel} (`git checkout HEAD -- {rel}`) and fix what got worse; only the owner loosens "
        "the snapshot, with `python3 .claude/hooks/baseline.py record` in their own terminal",
    ))


def bypass_guard(root: Path, layer: str, files: list[str], diff_ref: str | None, report: Report) -> None:
    allowed = contract_grants(root)
    for rel in files:
        if not (rel.endswith(".py") or is_config_file(rel)):
            continue
        added = added_lines(root, layer, rel, diff_ref)
        if rel.endswith(".py"):
            text = new_text(root, layer, rel)
            if text is not None:
                guard_python(rel, text, added, allowed, report)
        else:
            guard_config(root, layer, rel, diff_ref, allowed, added, report)
    blocks = [f for f in report.findings if f.rule.startswith("bypass/") and f.severity == "block"]
    for f in blocks:
        where = f"{f.file}:{f.line}" if f.line else str(f.file)
        report.reasons.append(f"BYPASS GUARD {where} [{f.rule}] {f.message}. {f.hint}")


# ------------------------------------------------------------------ checks


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    return rel.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def test_targets(root: Path, files: list[str]) -> list[str]:
    targets: list[str] = []
    for rel in files:
        if not rel.endswith(".py"):
            continue
        if is_test_file(rel):
            candidates = [rel]
        else:
            stem = Path(rel).stem
            candidates = [f"{d}/test_{stem}.py" for d in ("tests", "test")]
        targets.extend(c for c in candidates if (root / c).is_file() and c not in targets)
    return targets


def check_steps(root: Path, env: dict[str, str], files: list[str], full: bool, report: Report,
                snapshot: bool = False) -> list[tuple[str, str]]:
    """The (kind, command) steps of a layer. With a snapshot the default commands are the ones it
    can be read against: ruff one line per finding, pytest to the end instead of the first failure."""
    configured = {k: env.get(k, "") for k in ("LINT_CMD", "TYPECHECK_CMD", "TEST_CMD")}
    if full and env.get("TEST_CMD_FULL"):
        configured["TEST_CMD"] = env["TEST_CMD_FULL"]
    prefix = tool_prefix(root)
    py_files = [f for f in files if f.endswith(".py")]
    steps: list[tuple[str, str]] = []
    if any(configured.values()):
        steps = [(k, c) for k, c in (("lint", configured["LINT_CMD"]),
                                     ("typecheck", configured["TYPECHECK_CMD"]),
                                     ("tests", configured["TEST_CMD"])) if c]
    else:
        exts = code_extensions(env)
        if exts and "py" not in exts:
            report.add(Finding(None, None, "no-checks", "log",
                               f"CODE_EXTENSIONS='{' '.join(exts)}' but no check commands are set in "
                               ".claude/project.env (LINT_CMD / TYPECHECK_CMD / TEST_CMD)",
                               "set them to enable verification for this language"))
            return []
        if not py_files and not full:
            return []
        scope = "." if full else quoted(py_files)
        concise, pytest = ("--output-format concise ", "pytest") if snapshot else ("", "pytest -x")
        # The full layers go over `.`: a sketch's code (the quarantine, below) is left out by name — the
        # directory at the project's root only, and only where there is one.
        skip = full and (root / "sketches").is_dir()
        no_lint, no_types, no_tests = ((f"--extend-exclude {shlex.quote(str(root / 'sketches'))} ", "--exclude '^sketches/' ",
                                        " --ignore=sketches") if skip else ("", "", ""))
        for kind, tool, table, args in (("lint", "ruff", "tool.ruff", f" check --force-exclude {no_lint}{concise}{scope}"),
                                        ("typecheck", "mypy", "tool.mypy", f" {no_types}{scope}")):
            if not pyproject_has(root, table):
                continue
            start, why = check_tool(root, tool)
            if start:
                steps.append((kind, start + args))
            else:
                finding = Finding(None, None, "tools/version", "block", f"{tool} did not run: {why}",
                                  "a check with another release is not this check: give the machine uv "
                                  "or that version, or pin the tool in the project (a lockfile, its "
                                  "virtual environment, or LINT_CMD / TYPECHECK_CMD in .claude/project.env)")
                report.add(finding)
                report.reasons.append(f"TOOL VERSION [{finding.rule}] {finding.message}. {finding.hint}")
        if (root / "tests").is_dir() or (root / "test").is_dir():
            if full:
                steps.append(("tests", f"{prefix}{pytest} --no-header -q{no_tests}"))
            else:
                targets = test_targets(root, files)
                if targets:
                    steps.append(("tests", f"{prefix}{pytest} --no-header -q {quoted(targets)}"))
                else:
                    report.add(Finding(None, None, "tests/unmapped", "log",
                                       "no test file maps to the changed files; tests not run"))
    return steps


def load_snapshot(root: Path, report: Report) -> dict[str, Any] | None:
    """The snapshot "as it was", or None: no file, or one that cannot be read — then "clean" is asked."""
    if not (root / BASELINE_FILE).is_file():
        return None
    base: dict[str, Any] | None
    base, problem = baseline_module().load(root)
    if problem:
        report.add(Finding(BASELINE_FILE, None, "baseline/unreadable", "warn", f"{problem}; the gate asks for clean",
                           "restore the file from git, or the owner records it again (baseline.py record)"))
    return base


def judge_step(report: Report, base: dict[str, Any], kind: str, command: str, rc: int, out: str, ms: int,
               full: bool) -> bool:
    """A step against the snapshot; True when it got WORSE. A failure that names nothing readable is
    judged as without a snapshot."""
    snapshot = baseline_module()
    part = SNAPSHOT_PART[kind]
    was = base[part]
    if kind == "tests":
        now: Any = set() if rc == 0 else snapshot.failed_tests(out)
        worse = [(None, f"new failing test: {name}") for name in sorted(now - set(was))]
        fixed = len(set(was) - now)
        if was and snapshot.stops_at_first(command):
            report.add(Finding(None, None, "baseline/exitfirst", "warn",
                               f"the test command stops at the first failure ({command}): a new failure after an "
                               "old one is not seen", "drop that option from the test command"))
    else:
        now = {} if rc == 0 else snapshot.diagnostic_counts(out, report.root)
        worse = [(file, f"{rule}: {n} now, {old} in the snapshot") for file, rule, n, old in snapshot.worse_counts(now, was)]
        fixed = len(snapshot.fixed_counts(now, was))
    if rc != 0 and not now:
        record_step(report, kind, command, rc, out, ms)
        return True
    report.steps_ms[kind] = report.steps_ms.get(kind, 0) + ms
    if full and fixed:
        report.add(Finding(BASELINE_FILE, None, "baseline/stale", "warn",
                           f"{kind}: {fixed} entr(ies) of the snapshot are fixed and still listed",
                           "run `python3 .claude/hooks/baseline.py tighten` and commit the file"))
    if not worse:
        if rc != 0:
            report.add(Finding(None, None, f"baseline/{kind}", "log",
                               f"{kind}: only what the snapshot already lists, nothing new"))
        return False
    for file, message in worse[:20]:
        report.add(Finding(file, None, kind, "block", message,
                           f"worse than {BASELINE_FILE}; fix it (re-run: {command})"))
    listed = "\n".join(f"  {file + ': ' if file else ''}{message}" for file, message in worse[:20])
    tail = "\n".join(out.strip().splitlines()[-TAIL_LINES[kind]:])
    report.reasons.append(f"{HEADINGS[kind]} — worse than the snapshot {BASELINE_FILE} ({command}):\n{listed}\n{tail}")
    return True


def run_checks(root: Path, env: dict[str, str], files: list[str], full: bool, report: Report) -> None:
    """lint, then types, then tests only if those passed — as the Stop hook always did."""
    base = load_snapshot(root, report)
    failed = False
    for kind, command in check_steps(root, env, files, full, report, snapshot=base is not None):
        if kind == "tests" and failed:
            break
        rc, out, ms = run_shell(root, command)
        if base is None:
            record_step(report, kind, command, rc, out, ms)
            failed = failed or rc != 0
        else:
            failed = judge_step(report, base, kind, command, rc, out, ms, full) or failed


# ------------------------------------------------------------------ report, counter, escalation


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_report(report: Report, result: str, name: str | None = None) -> Path:
    path = report.root / (REPORT_REL if name is None else REPORT_REL.with_name(name))
    try:
        write_json(path, report.as_json(result))
    except OSError as exc:
        print(f"gate: cannot write {path}: {exc}", file=sys.stderr)
    return path


def record_findings(root: Path, source: str, layer: str, findings: list[Finding],
                    result: str | None = None) -> Path:
    """For a gate that stays a separate script (complexity_budget, contract_fingerprint): write its
    verdict in this schema to .claude/state/gate/<source>-report.json. Its own file, not
    last-report.json — two Stop hooks run side by side and must not race on one path."""
    report = Report(layer=layer, root=root, source=source, started_utc=utc_now(), findings=findings)
    return write_report(report, result or ("block" if report.blocked else "pass"), f"{source}-report.json")


def read_count(root: Path, session: str) -> int:
    """Consecutive blocks of THIS session; another session's count is not ours."""
    try:
        data = json.loads((root / COUNT_REL).read_text(encoding="utf-8"))
        return int(data.get("sessions", {}).get(session, 0))
    except (OSError, ValueError, AttributeError):
        return 0


def write_count(root: Path, session: str, count: int) -> None:
    try:
        data = json.loads((root / COUNT_REL).read_text(encoding="utf-8"))
        sessions = dict(data.get("sessions", {}))
    except (OSError, ValueError, AttributeError):
        sessions = {}
    if count:
        sessions[session] = count
    else:
        sessions.pop(session, None)
    try:
        write_json(root / COUNT_REL, {"sessions": sessions, "updated_utc": utc_now()})
    except OSError:
        pass


def active_slice(root: Path) -> str | None:
    """The slug of the slice .engine/PROGRESS.md marks IN PROGRESS (the convention overseer_stop.py
    and complexity_budget.py read): a `.engine/slices/<slug>.md` path in that block, else the slug
    of its `## Slice <slug>` heading. With no heading IN PROGRESS at all — in the pipeline nobody
    writes one (board 789) — the slice testing.py opened last under this session's board task.
    None when no slice is active."""
    try:
        text = (root / ".engine" / "PROGRESS.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    marked = False
    for block in re.split(r"(?=^## )", text, flags=re.MULTILINE):
        if "IN PROGRESS" not in block.upper():
            continue
        marked = marked or "IN PROGRESS" in block.split("\n", 1)[0].upper()
        named = re.search(r"\.engine/slices/([\w.-]+)\.md", block)
        heading = re.search(r"^##\s+Slice\s+([\w.-]+)", block, re.MULTILINE)
        found = named or heading
        if found:
            return found.group(1)
    if marked:   # a bug record or a hotfix card is the work in hand: no slice is (the words in an entry's body mark nothing)
        return None
    try:
        import testing

        return testing.opened_slice(root, work_in_hand(root))
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return None


def read_escalations(root: Path) -> dict[str, Any]:
    """The Stop gate's escalations: {"open": [...], "closed": [...], "refusals": [...]}."""
    try:
        data = json.loads((root / ESCALATIONS_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    for key in ("open", "closed", "refusals"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def work_in_hand(root: Path) -> str:
    """The board task of this session in tasks/doing/ (board.py in_hand); empty with none or no board."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        return str(board.in_hand(root / "tasks"))
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return ""


def open_escalation(root: Path, stamp: str, report: Report, task: str | None = None,
                    waiting: dict[str, Any] | None = None) -> None:
    """Machine state beside the parked entry: overseer_stop.py refuses an OVERSEER_PASS while an
    escalation of the work is open. In .claude/state/, which no agent tool may write — the park
    queue is the agent's own file and could not carry a lock on the agent. `work` is the board
    task whose turn the gate gave up on (board 301): its PASS is not accepted while the escalation
    is open, and the board does not start it."""
    data = read_escalations(root)
    # The files the gate blocked on; when a failure named none (a test run that just says
    # "failed"), every file the gate looked at. The lock is keyed on these, not on a slice name.
    files = sorted({f.file for f in report.findings if f.severity == "block" and f.file}) or sorted(report.files)
    head = git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()
    entry: dict[str, Any] = {"stamp": stamp, "slice": active_slice(root) or NO_SLICE, "files": files,
             "head": head, "reasons": [r.splitlines()[0][:200] for r in report.reasons[:5]]}
    if task:
        entry["task"] = task
    work = work_in_hand(root)
    if work:
        entry["work"] = work
    if waiting:
        entry["waiting"] = waiting
    data["open"].append(entry)
    try:
        write_json(root / ESCALATIONS_REL, data)
    except OSError as exc:
        print(f"gate: cannot record the escalation in {ESCALATIONS_REL}: {exc}", file=sys.stderr)


def close_escalation(root: Path, which: str) -> int:
    """`gate.py --close-escalation <stamp|all>` — a HUMAN's answer to a parked gate question:
    typed by the owner, or run by board-runner.sh on the owner's «так» under the question
    in tasks/blocked/ (board 005).

    Refuses inside a Claude Code session (CLAUDECODE is set in every shell the agent's tools
    start): hooks do not see a command a script runs, so this script carries the check itself.
    The party the gate judged does not get to close the gate's question."""
    if os.environ.get("CLAUDECODE"):
        print("gate: --close-escalation is the owner's command and is refused inside a Claude Code "
              "session (CLAUDECODE is set). Run it in your own terminal.", file=sys.stderr)
        return 2
    data = read_escalations(root)
    closing = [e for e in data["open"] if which == "all" or e.get("stamp") == which]
    if not closing:
        stamps = ", ".join(str(e.get("stamp")) for e in data["open"]) or "none"
        print(f"gate: no open escalation '{which}' (open: {stamps})", file=sys.stderr)
        return 1
    data["open"] = [e for e in data["open"] if e not in closing]
    data["closed"].extend(e | {"closed_utc": utc_now()} for e in closing)
    write_json(root / ESCALATIONS_REL, data)
    # Nothing is closed inside .engine/overseer/parked.md (board 037): the log is history, and
    # the open thing is the gate's question on the board, which the runner moves to done/.
    for entry in closing:
        print(f"gate: escalation {entry['stamp']} ({entry.get('slice')}) closed")
    return 0


def git_busy(root: Path) -> str | None:
    """`rebase` or `merge` while git is in the middle of one, else None. The working tree then is
    not the branch: files committed on it may be absent, so a number that looks free on the board
    may be taken (board 065) — nothing is written to the board until it is over."""
    for marker, word in (("rebase-merge", "rebase"), ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge")):
        found = git(root, "rev-parse", "--git-path", marker)
        if found.returncode == 0 and found.stdout.strip() and (root / found.stdout.strip()).exists():
            return word
    return None


def board_question(root: Path, stamp: str, report: Report, evidence: str, blocks: int, busy: str | None = None) -> str | None:
    """The escalation as a question on the task board (board.py, tasks/README.md): the path of the
    task written to tasks/blocked/, or None — no board in this project, it could not be written,
    or `busy` (a rebase or a merge is in progress: the journal entry only, `ask_waiting` asks
    later). Best effort: a problem here never changes what the gate decides."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        files = sorted({f.file for f in report.findings if f.severity == "block" and f.file}) or sorted(report.files)
        reasons = [r.splitlines()[0][:200] for r in report.reasons[:5]]
        task = None if busy else board.gate_question(board.Board(root / "tasks"), stamp, blocks, active_slice(root) or NO_SLICE, files[:20], reasons, evidence)
        asked = task.relative_to(root).as_posix() if task else None
        later = f"у репозиторії триває {busy}, тому питання власникові на task board поки не поставлено — його буде поставлено, щойно {busy} завершиться; " if busy else ""
        # Everything odd is in one journal (board 035); the board runner commits the entry.
        board.note(root, "gates (gate.py)", f"gates наприкінці ходу не пройшли {blocks} раз(и) поспіль і здалися (ескалація {stamp}): "
                   + (reasons[0] if reasons else "причину не записано"),
                   "хід дозволено закінчити; " + (f"власника спитано в `{asked}`; " if asked else later) + "поки ескалацію не закрито, overseer не приймає роботу з цими файлами")
        return asked
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"gate: the escalation was not put on the task board: {exc}", file=sys.stderr)
        return None


def ask_waiting(root: Path) -> int:
    """Put on the board the questions of the escalations that were opened during a rebase or a
    merge (board 065), once it is over. Called by every Stop gate run and by the board runner
    (`gate.py --ask-waiting`). Best effort, like `board_question`; returns how many were asked."""
    data = read_escalations(root)
    waiting = [e for e in data["open"] if isinstance(e, dict) and isinstance(e.get("waiting"), dict)]
    if not waiting or git_busy(root):
        return 0
    asked = 0
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        for entry in waiting:
            was = entry["waiting"]
            task = board.gate_question(board.Board(root / "tasks"), str(entry.get("stamp")), int(was.get("blocks") or 0), str(entry.get("slice") or NO_SLICE),
                                       [str(f) for f in entry.get("files") or []][:20], [str(r) for r in entry.get("reasons") or []], str(was.get("evidence") or ""))
            if task is None:
                continue
            entry["task"] = task.relative_to(root).as_posix()
            del entry["waiting"]
            asked += 1
            board.note(root, "gates (gate.py)", f"{was.get('for')} завершився: ескалація gates {entry.get('stamp')} чекала на це",
                       f"питання власникові поставлено в `{entry['task']}`")
        if asked:
            write_json(root / ESCALATIONS_REL, data)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"gate: the waiting escalations were not put on the task board: {exc}", file=sys.stderr)
    return asked


def park_escalation(root: Path, report: Report, report_path: Path, blocks: int) -> tuple[str | None, str | None]:
    """Park the item; returns the board task that asks the owner, when there is a board, and
    `rebase` or `merge` when the question waits for one to end (board 065: the journal entry
    only, no file on the board). With that task the item lives on the board and nowhere else
    (board 037); only a project without a board gets an entry in the log .engine/overseer/parked.md."""
    stamp = utc_now()
    evidence = str(report_path.relative_to(root) if report_path.is_relative_to(root) else report_path)
    busy = git_busy(root) if (root / "tasks").is_dir() else None
    task = board_question(root, stamp, report, evidence, blocks, busy)
    open_escalation(root, stamp, report, task, {"for": busy, "blocks": blocks, "evidence": evidence} if busy else None)
    if task or busy:
        return task, busy
    top = "\n".join(f"  - {r.splitlines()[0]}" for r in report.reasons[:5])
    entry = (
        f"## {stamp} — gate stop layer — PARKED\n"
        f"- Blocked on: the Stop gate blocked {blocks} turns in a row and was not satisfied\n"
        "- Class: human-input\n"
        # While the escalation is open (.claude/state/gate/escalations.json) overseer_stop.py does
        # not accept an OVERSEER_PASS for work that still holds the escalated files (package costs).
        f"- Slice: {active_slice(root) or NO_SLICE}\n"
        "- Reversibility: nothing was decided; the work is on disk and uncommitted\n"
        f"- Evidence: {evidence}\n"
        f"{top}\n"
        "- Unblocks when: a human reads the report, fixes or accepts the finding, and runs in their "
        f"own terminal `python3 .claude/hooks/gate.py --close-escalation {stamp}` (refused inside a "
        "Claude Code session; until then no OVERSEER_PASS is accepted for work that holds these files)\n"
        "- Continued with: the turn was allowed to end\n"
    )
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import journal

        journal.add(root, "parked", entry)   # this session's own file of the log (board 739)
    except (ImportError, OSError) as exc:
        print(f"gate: cannot park the escalation in {PARKED_REL}: {exc}", file=sys.stderr)
    return task, None


def lessons(root: Path, action: str, text: str = "") -> str:
    """Feed the lesson queue and the stuck counter (lesson_queue.py). Best effort: a problem here
    never changes what the gate decides. Returns the stuck protocol text when one is due."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lesson_queue

        if action == "collect":
            lesson_queue.collect(root)
        elif action == "failure":
            return lesson_queue.note_failure(root, text)
        elif action == "success":
            lesson_queue.note_success(root)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return ""


def simplify_signals(root: Path, env: dict[str, str], layer: str, files: list[str], report: Report) -> None:
    """The simplifier's deterministic signals (simplify_signals.py) as `warn` findings: the changed
    files at stop, the whole repository with its history at pre_commit and ci. Off with
    COMPLEXITY_GATE off. Best effort, and never a block: a signal is a fact, not a verdict."""
    if env.get("COMPLEXITY_GATE", "off").lower() in ("", "off"):
        return
    started = time.perf_counter()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import simplify_signals as signals

        scope = "stop" if layer == "stop" else "full"
        for s in signals.collect(root, env, scope, files, record=scope == "full"):
            report.add(Finding(s["file"], s["line"], f"simplify/{s['kind']}",
                               "log" if s["kind"] == "unavailable" else "warn", s["message"],
                               "a signal for the simplifier (.claude/references/simplifier.md), not a verdict"))
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        report.add(Finding(None, None, "simplify/unavailable", "log", f"the simplifier's signals did not run: {exc}"))
    report.steps_ms["simplify_signals"] = int((time.perf_counter() - started) * 1000)


def summarise(report: Report, limit: int = 8) -> str:
    order = {s: i for i, s in enumerate(SEVERITIES)}
    top = sorted(report.findings, key=lambda f: order[f.severity])[:limit]
    lines = [f"gate[{report.layer}] {len(report.findings)} finding(s), exit {report.exit_code}"]
    for f in top:
        where = f"{f.file}:{f.line}" if f.line else (f.file or "-")
        lines.append(f"  {f.severity:5} {where} [{f.rule}] {f.message.splitlines()[0]}")
    return "\n".join(lines)


# ------------------------------------------------------------------ layers


def layer_post_write(root: Path, env: dict[str, str], rel: str, report: Report) -> str | None:
    """Format one file, lint it quickly, never block. Returns the additionalContext text."""
    path = root / rel if not Path(rel).is_absolute() else Path(rel)
    if not path.is_file():
        return None
    shown_rel = os.path.relpath(path, root)
    report.files = [shown_rel]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    started = time.perf_counter()
    own_formatter = format_file(root, env, path)
    report.steps_ms["format"] = int((time.perf_counter() - started) * 1000)
    changed = hashlib.sha256(path.read_bytes()).hexdigest() != before
    notes: list[str] = []
    if changed:
        notes.append(f"{shown_rel} was rewritten by the formatter; re-read it before your next edit.")
        report.add(Finding(rel, None, "format", "log", "rewritten by the formatter"))
    # A project that names its own formatter owns its tooling: no ruff lint on top of it.
    ruff, why = edit_ruff(root) if path.suffix == ".py" and not own_formatter else (None, "")
    if why:
        report.add(Finding(rel, None, "tools/version", "log", why))
    if path.suffix == ".py" and not own_formatter and ruff:
        command = " ".join(shlex.quote(a) for a in ruff) + f" check --force-exclude --output-format concise {shlex.quote(str(path))}"
        rc, out, ms = run_shell(root, command)
        report.steps_ms["lint"] = ms
        if rc == 1:
            for match in DIAGNOSTIC_RE.finditer(out):
                shown = os.path.relpath(match["file"], root) if os.path.isabs(match["file"]) else match["file"]
                report.add(Finding(shown, int(match["line"]), "lint", "warn", match["msg"].strip(),
                                   "fix it in the next edit"))
                notes.append(f"lint {shown}:{match['line']} {match['msg'].strip()}")
    warns = [f for f in report.findings if f.severity == "warn"]
    if warns:
        stuck = lessons(root, "failure", " ; ".join(sorted(f"{w.rule} {w.file} {w.message}" for w in warns)))
        if stuck:
            notes.append(stuck)
    else:
        lessons(root, "success")
    if not notes:
        return None
    return "gate: " + "\n".join(notes[:10])


def format_file(root: Path, env: dict[str, str], path: Path) -> bool:
    """Format `path`; True when the project's own FORMAT_CMD handled it."""
    ext = path.suffix.lstrip(".").lower() if path.suffix else ""
    configured_exts = code_extensions(env)
    fmt = env.get("FORMAT_CMD", "")
    if fmt.strip() == "true":
        # The off switch project.env names: no file is formatted, the built-in handlers included — a ruff, black or
        # prettier that merely happens to be installed must not rewrite a whole file for a one-line edit (board 749).
        return True

    def quiet_run(cmd: list[str]) -> None:
        subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    if fmt and ext and ext in configured_exts:
        quiet_run(["bash", "-c", fmt.replace("{file}", shlex.quote(str(path)), 1)])
        return True
    target = str(path)
    if ext == "py":
        runner, why = edit_ruff(root)
        if runner is None:
            # Only when there is no ruff at all: a ruff of another version formats nothing either.
            if not why and shutil.which("black"):
                quiet_run(["black", "--quiet", target])
            return False
        quiet_run([*runner, "format", "--force-exclude", target])
        quiet_run([*runner, "check", "--force-exclude", "--fix", "--select", "I", target])
    elif ext == "json" and shutil.which("jq"):
        proc = subprocess.run(["jq", ".", target], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            path.write_text(proc.stdout, encoding="utf-8")
    elif ext in ("md", "yml", "yaml", "toml") and shutil.which("prettier"):
        quiet_run(["prettier", "--write", "--log-level", "silent", target])
    return False


def eligible(env: dict[str, str], files: list[str]) -> list[str]:
    exts = code_extensions(env)
    if not exts:
        return files
    return [f for f in files if Path(f).suffix.lstrip(".").lower() in exts]


def is_config_file(rel: str) -> bool:
    return Path(rel).name in ("pyproject.toml", *CONFIG_BASENAMES) or rel in (".claude/project.env", BASELINE_FILE)


SKETCHES = "sketches/"
QUARANTINE = ("sketches/", ".engine/", "tasks/")   # all a task in ескіз may change
# A path into a named sketch: `sketches/<name>`, after any number of `./` or `../`, standing alone or after a shell
# variable or substitution, quoted or not (`$ROOT/`, `"$ROOT"/`, `${ROOT:-.}/`, `$(dirname "$0")/`, a backtick
# command, the placeholder an f-string is read with); a directory that merely shares the name deeper in the tree
# (`src/sketches/a`) is not the quarantine, nor is an absolute path or an import alias (docs/engine-limits.md).
SHELL_VALUE = r"(?:\$\{[^}]*\}|\$\w+|\$\([^()]*\)|`[^`]*`)"
SKETCH_PATH_RE = re.compile(rf"(?:(?<![\w./-])|{SHELL_VALUE}[\"']?/)(?:\.{{1,2}}/)*sketches/[A-Za-z0-9_.-]+")


def sketch_mode(root: Path) -> bool:
    """The session's task in doing/ is in the mode ескіз, as its one reader says (mode.py)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import mode

        mine = mode.own_task(root)
        return len(mine) == 1 and mode.parse(mine[0].read_text(encoding="utf-8")).current == "ескіз"
    except (ImportError, OSError, ValueError, UnicodeDecodeError):
        return False


def sketch_references(root: Path, layer: str, rel: str, diff_ref: str | None) -> list[int]:
    """The added lines of a working-code file that refer to a sketch."""
    text = new_text(root, layer, rel)
    if text is None:
        return []
    added = added_lines(root, layer, rel, diff_ref)

    def counted(line: int, last: int | None = None) -> bool:
        """The node's lines (a string may span several) hold a line this diff adds."""
        return added is None or any(n in added for n in range(line, (last or line) + 1))

    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            hits = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    if any(n == "sketches" or n.startswith("sketches.") for n in names) and counted(node.lineno, node.end_lineno):
                        hits.add(node.lineno)
                elif (isinstance(node, ast.Constant) and isinstance(node.value, str) and SKETCH_PATH_RE.search(node.value)
                        and counted(node.lineno, node.end_lineno)):
                    hits.add(node.lineno)
                elif isinstance(node, ast.JoinedStr) and counted(node.lineno, node.end_lineno):
                    # an f-string is read with `$V` where each placeholder stands: f"{ROOT}/sketches/x" is "$V/sketches/x"
                    joined = "".join(part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "$V"
                                     for part in node.values)
                    if SKETCH_PATH_RE.search(joined):
                        hits.add(node.lineno)
            return sorted(hits)
    return [n for n, line in enumerate(text.splitlines(), 1)
            if counted(n) and not line.lstrip().startswith(("#", "//")) and SKETCH_PATH_RE.search(line)]


def quarantine(root: Path, env: dict[str, str], layer: str, files: list[str], diff_ref: str | None, report: Report) -> None:
    if sketch_mode(root):
        for rel in files:
            if not rel.startswith(QUARANTINE):
                report.add(Finding(rel, None, "sketch/outside", "block",
                                   "the task is a sketch (ескіз): it changes nothing outside sketches/, .engine/ and tasks/",
                                   "keep the work in sketches/<name>/ and the record in .engine/sketches/<name>.md; working "
                                   "code is written anew in a task in соло or конвеєр (mode.py raise соло, if it must be this one)"))
    # the records (.engine/, tasks/) hold a sketch's command by design and are never working code (mode.py RECORDS)
    for rel in eligible(env, [f for f in files if not f.startswith(QUARANTINE) and not is_test_file(f)]):
        for line in sketch_references(root, layer, rel, diff_ref):
            report.add(Finding(rel, line, "sketch/reference", "block",
                               "working code refers to a sketch: a sketch never becomes working code",
                               "write the code anew under this task's checks; never import, run or open sketches/<name>"))


def layer_checks(root: Path, env: dict[str, str], layer: str, files: list[str],
                 diff_ref: str | None, report: Report) -> None:
    full = layer in ("pre_commit", "ci")
    files = without_install(root, layer, files, diff_ref, report)   # before anything judges
    report.files = files
    started = time.perf_counter()
    quarantine(root, env, layer, files, diff_ref, report)   # before anything is skipped: a sketch's docs/ change is seen too
    report.steps_ms["quarantine"] = int((time.perf_counter() - started) * 1000)
    files = [f for f in files if not f.startswith(SKETCHES)]   # the gates do not check a sketch's code
    code = eligible(env, files)
    # A configuration file is not code, but changing the gate's own settings is exactly what
    # the guard exists to see; so a config-only turn still reaches the guard.
    # Nor is a file that is gone: a turn that only deletes code still reaches the delete guard.
    if (layer == "stop" and not code and not any(is_config_file(f) for f in files)
            and not deleted_code(root, layer, diff_ref, env)):
        return
    started = time.perf_counter()
    if layer in ("stop", "pre_commit"):
        bypass_guard(root, layer, files, diff_ref, report)
        report.steps_ms["bypass_guard"] = int((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        delete_guard(root, layer, diff_ref, env, report)
        report.steps_ms["delete_guard"] = int((time.perf_counter() - started) * 1000)
    if layer == "stop":
        # The marker stands for "the tooling is installed". The guard above needs no tooling, so
        # it has already run; only the checks that call a tool wait for the marker.
        marker = env.get("PROJECT_MARKER", "")
        if marker and not (root / marker).exists():
            report.add(Finding(None, None, "marker", "log",
                               f"{marker} not found — lint, types and tests skipped",
                               "add tooling, or clear PROJECT_MARKER in .claude/project.env"))
            return
    if layer != "stop" or code:
        run_checks(root, env, files, full, report)
        simplify_signals(root, env, layer, files, report)


def run_layer(layer: str, root: Path, files: list[str] | None, diff_ref: str | None) -> tuple[Report, str | None]:
    env = load_env(root)
    report = Report(layer=layer, root=root, started_utc=utc_now())
    if layer == "post_write":
        context = None
        for rel in files or []:
            context = layer_post_write(root, env, rel, report) or context
        return report, context
    selected = files if files else changed_files(root, layer, diff_ref)
    layer_checks(root, env, layer, selected, diff_ref, report)
    return report, None


def finish_stop(report: Report, root: Path, session: str) -> tuple[str, dict[str, Any]]:
    """Apply the counter: a block counts, a pass resets, the Nth block escalates."""
    limit = DEFAULT_MAX_BLOCKS
    raw = load_env(root).get("GATE_MAX_BLOCKS", "")
    if raw.isdigit() and int(raw) > 0:
        limit = int(raw)
    if not report.blocked:
        write_count(root, session, 0)
        report.extra["stop"] = {"consecutive_blocks": 0, "max": limit, "escalated": False}
        return "pass", {}
    count = read_count(root, session) + 1
    escalated = count >= limit
    report.extra["stop"] = {"consecutive_blocks": count, "max": limit, "escalated": escalated}
    if not escalated:
        write_count(root, session, count)
        return "block", {}
    write_count(root, session, 0)
    path = write_report(report, "escalated")
    task, busy = park_escalation(root, report, path, count)
    message = f"GATE ESCALATION: the Stop gate blocked {count} turns in a row. The turn may end; the item is "
    if busy:
        message += (f"in the anomaly journal only: a {busy} is in progress, and the question to the owner is put on the "
                    f"task board when it is over (by the next Stop gate run or the board runner). Report: {REPORT_REL}")
    elif task:
        message += (f"a question to the owner on the task board: {task} — leave its answer line empty; "
                    f"the board runner acts on the owner's answer. Report: {REPORT_REL}")
    else:
        message += f"parked in the parked log for a human (`python3 .claude/hooks/journal.py show parked`). Report: {REPORT_REL}"
    return "escalated", {"systemMessage": message}


def read_envelope() -> dict[str, Any]:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def emit_stop(report: Report, root: Path, hook: bool, session: str) -> int:
    result, extra = finish_stop(report, root, session)
    if result != "escalated":
        write_report(report, result)
    if report.blocked:
        stuck = lessons(root, "failure", " ; ".join(sorted(
            f"{f.rule} {f.file} {f.message}" for f in report.findings if f.severity == "block")))
        if stuck:
            report.reasons.append(stuck)
            if "systemMessage" in extra:
                extra["systemMessage"] += "\n" + stuck
    else:
        lessons(root, "success")
    lessons(root, "collect")
    if report.findings and any(f.severity != "log" for f in report.findings):
        print(summarise(report), file=sys.stderr)
    if result == "escalated":
        if hook:
            print(json.dumps(extra, ensure_ascii=False))
        else:
            print(extra["systemMessage"], file=sys.stderr)
        return 0
    if result == "block":
        reason = "\n\n".join(report.reasons) or "the gate blocked this turn"
        if hook:
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return 0
        print(reason, file=sys.stderr)
    return report.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--layer", choices=LAYERS)
    parser.add_argument("--close-escalation", metavar="STAMP|all", default=None,
                        help="the owner's command: close a parked Stop-gate escalation")
    parser.add_argument("--ask-waiting", action="store_true",
                        help="put on the task board the questions that waited for a rebase or a merge to end")
    parser.add_argument("--files", nargs="*", default=None, help="files to check (default: the diff)")
    parser.add_argument("--diff", dest="diff_ref", default=None, help="diff base (default: HEAD)")
    parser.add_argument("--hook", action="store_true", help="speak Claude Code's hook protocol")
    args = parser.parse_args(argv)
    root = project_root()
    if args.close_escalation:
        return close_escalation(root, args.close_escalation)
    if args.ask_waiting:
        ask_waiting(root)
        return 0
    if not args.layer:
        parser.error("--layer is required")
    files: list[str] | None = args.files
    session = "cli"
    guarded: list[dict[str, Any]] = []
    try:
        if args.layer == "stop":
            ask_waiting(root)
        if args.hook:
            envelope = read_envelope()
            session = str(envelope.get("session_id") or "cli")
            if args.layer == "stop":
                # Before every way out below (board 724): a turn that changed only the constitution
                # changed no code, and a few hashes cost nothing on a stop another hook forced.
                guarded = protected_guard_module().at_stop(root, session if session != "cli" else None)
            # Read first. Claude Code sets the flag on the stop that follows a block, so a gate
            # that always exits on it can never count to N. The flag therefore ends the gate's
            # work only when the gate has not itself blocked this session (counter 0): a stop
            # forced by someone else's hook is not verified again, a re-entry after OUR block is.
            if (args.layer == "stop" and envelope.get("stop_hook_active") is True
                    and read_count(root, session) == 0 and not guarded):
                return 0
            if args.layer == "post_write":
                tool_input = envelope.get("tool_input")
                tool_input = tool_input if isinstance(tool_input, dict) else {}
                target = tool_input.get("file_path") or tool_input.get("path")
                files = [target] if isinstance(target, str) and target else []
        if args.layer == "post_write":
            report, context = run_layer("post_write", root, files, args.diff_ref)
            if report.findings:
                write_report(report, "info")
            if context and args.hook:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PostToolUse", "additionalContext": context}}, ensure_ascii=False))
            elif context:
                print(context)
            return 0
        if args.layer == "stop" and not args.hook:
            guarded = protected_guard_module().at_stop(root, None)   # by hand: compared with HEAD, nothing put back
        report, _ = run_layer(args.layer, root, files, args.diff_ref)
        if args.layer == "stop":
            add_guarded(report, guarded)
            code = emit_stop(report, root, args.hook, session)
            if args.hook and session != "cli" and not report.blocked:
                protected_guard_module().take(root, session)   # the end of a turn that passed is the start of the next
            return code
        result = "block" if report.blocked else "pass"
        write_report(report, result)
        if any(f.severity != "log" for f in report.findings):
            print(summarise(report), file=sys.stderr)
        return report.exit_code
    except Exception as exc:  # noqa: BLE001  # gate-allow: a crashed gate must not read as a passed gate
        if args.layer == "post_write":
            print(f"gate: post_write failed, nothing reported: {exc}", file=sys.stderr)
            return 0
        reason = f"gate.py crashed: {type(exc).__name__}: {exc}"
        if args.hook and args.layer == "stop":
            print(json.dumps({"decision": "block", "reason": reason}))
            return 0
        print(reason, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
