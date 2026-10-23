#!/usr/bin/env python3
"""mode.py — the one reader of a task's mode (board 097; the approved design is board 080).

    python3 .claude/hooks/mode.py show [--task FILE]      one line: the mode, the accompaniment,
                                                         «without supervision», the work type —
                                                         each with where it was read; writes nothing
    python3 .claude/hooks/mode.py raise <mode> --why "…"  the agent raises the mode of its task in doing/
    python3 .claude/hooks/mode.py unattended              `unattended env|mode-file` (exit 0) or `attended` (exit 1)
    python3 .claude/hooks/mode.py check-close <task>      the minimum of the mode of a task in done/ (board 098):
                                                         exit 0 it is there; 1 what is missing, a line each;
                                                         3 the check itself broke (never read as «missing»)

THREE MODES, a property of the TASK: ескіз (an answer to one question, code only in quarantine),
соло (one builder, the gates, the overseer), конвеєр (a feature architect, a sealed slice contract
on every slice). The owner writes the line `Режим: ескіз|соло|конвеєр` under the task's title; a
task without it is соло. A value that names no mode (or two such lines) is nobody's clear word:
the board does not take that task (board.py) and says why.

RAISING. The agent goes up by itself and never down: a lighter mode lifts checks, and nobody lifts
checks for themselves (the constitution, article 3). `raise` appends to the session's task in
doing/ the section `## Режим піднято`, one line per raise — when, from which mode to which, why.
The mode in force is the higher of the owner's line and the last raise. There is no state file:
the raise lives in the task file and moves to done/ with it, so the next task starts from its own
line or from соло. Only the owner undoes a raise, by deleting that section from the task file.

WHAT A MODE FORBIDS (`refusal`). A fix is never made in quarantine: /hotfix and /bugfix are
refused in ескіз. An urgent fix is small by definition: /hotfix is refused in конвеєр. hotfix.py
start and bugfix.py prove ask here.

«WITHOUT SUPERVISION» is a property of the SESSION: the runner's variable
CLAUDE_UNATTENDED_SESSION=1, or `.claude/state/overseer/mode` saying `unattended`. It was computed
in five places, each its own way (board.py, env-probe.sh, goals.py, hotfix.py, park-ask-gated.py);
they all ask `unattended` here.

THE ACCOMPANIMENT is a fact about the project: it has the snapshot `.engine/baseline.json` and the
profile `.engine/onboard/profile.md`. THE WORK TYPE belongs to the card: `type:` of the bug record
that `.engine/PROGRESS.md` marks IN PROGRESS.

THE MINIMUM AT CLOSING (`check-close`, board 098). When the agent has moved its task to done/, the
runner asks here, by files and never by words: in every mode, report.md in the task's folder;
соло — for every commit of the task that changed working code, a PASS of the overseer whose audit saw
exactly that code; конвеєр — the same, plus the feature artifact (.engine/architecture/feature/) and,
for every slice contract the task wrote (.engine/slices/), its seal (.claude/state/contracts/) that
still matches it; ескіз — the record .engine/sketches/<name>.md with a PASS of the reader on it as it
is (reader.py, board 099), and no change outside sketches/, .engine/ and tasks/. In соло and конвеєр a
task none of whose commits changed working code has no audit to show, so it shows a reading (board 100):
a PASS of the reader on its report.md as it is, read together with every document the task's commits
changed, each as it is now (`reader.py request <task> --report`).
Working code is what asks for an audit: a code path as the Stop hook reads it from .claude/project.env
(overseer_stop._is_code_path — under SOURCE_DIRS when set, else an extension of CODE_EXTENSIONS, else
every file), never under tasks/, .engine/ or sketches/ (the quarantine, board 099). The task's commits are those of EVERY stay of the task in
doing/ (a park and a restart do not drop the first stay's commits); the last stay runs on past the
move to done/ — the turn back — until another task enters doing/. A PASS sees a commit's code when,
for every working-code file the commit changed, the content the audit's request recorded (its tree
fingerprint: the file as it was uncommitted, else as at the request's HEAD) is the content of the
commit. A request whose HEAD already holds an earlier commit sees it too: a verdict speaks for every
file changed since the last accepted PASS (gate_allows.unit_files), not for the turn's edits alone.
A file of a commit that a later covered commit of the same task changed needs no PASS of its own (the
owner's answer, board 754): a fix with a PASS replaced the code a BLOCK was given on, and what is left
in the branch is audited. The commit that replaced it must itself be covered — else both are missing.

A mode says which roles run and how strictly; it never says who runs them, and nothing here
names one (tests/test_model_roles.py). Standard library only. Exit: 0 done; 1 attended
(`unattended` only) or a minimum missing (`check-close` only); 2 refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODES = ("ескіз", "соло", "конвеєр")  # in the order of their ceremony: a raise goes rightwards only
DEFAULT = "соло"
LINE = re.compile(r"^Режим:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
RAISED = "## Режим піднято"
RAISED_HEADING = re.compile(r"^##\s+Режим піднято\s*$", re.MULTILINE)
RAISE_LINE = re.compile(r"^- (\S+) — (\S+) → (\S+): (.+)$", re.MULTILINE)
QUESTIONS = re.compile(r"^##\s+Питання до власника\s*$", re.MULTILINE)
HEADING = re.compile(r"^##\s", re.MULTILINE)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ENV = "CLAUDE_UNATTENDED_SESSION"
MODE_FILE = ".claude/state/overseer/mode"
SOURCES = {"env": f"змінна runner-а {ENV}=1", "mode-file": f"файл {MODE_FILE}"}
BASELINE, PROFILE = ".engine/baseline.json", ".engine/onboard/profile.md"
TYPE_LINE = re.compile(r"^type:[ \t]*(\S+)", re.MULTILINE)
FORBIDDEN = {
    ("ескіз", "hotfix"): "a fix is never made in quarantine: /hotfix is refused in the mode «ескіз»",
    ("ескіз", "bugfix"): "a fix is never made in quarantine: /bugfix is refused in the mode «ескіз»",
    ("конвеєр", "hotfix"): "an urgent fix is small by definition: /hotfix is refused in the mode «конвеєр»",
}
EXIT_OK, EXIT_ATTENDED, EXIT_REFUSED = 0, 1, 2
EXIT_MISSING, EXIT_BROKEN = 1, 3
RECORDS = ("tasks/", ".engine/", "sketches/")   # the records and the sketches' quarantine: never working code
QUARANTINE = ("sketches/", ".engine/", "tasks/")   # all a task in ескіз may change (board 099)
SKETCH_RECORDS = ".engine/sketches/"
FEATURES, SLICES, SEALS = ".engine/architecture/feature/", ".engine/slices/", ".claude/state/contracts"


@dataclass(frozen=True)
class Raise:
    utc: str
    before: str
    after: str
    why: str


@dataclass(frozen=True)
class Mode:
    """What a task file says about its mode: the owner's line and the raises."""

    line: str | None  # the owner's value as written; None when the task has no `Режим:` line
    raises: tuple[Raise, ...] = ()
    error: str = ""  # why the line names no mode; "" when it does or is absent

    @property
    def owner(self) -> str:
        """The owner's mode: the line, else соло."""
        return _normal(self.line) if self.line is not None and not self.error else DEFAULT

    @property
    def current(self) -> str:
        """The mode in force: the higher of the owner's line and the last raise."""
        if self.error:
            return ""
        last = self.raises[-1].after if self.raises else self.owner
        return max(self.owner, last, key=MODES.index)

    def shown(self) -> str:
        """The mode with where it was read, for a person: `соло (рядка «Режим:» немає → соло)`."""
        if self.error:
            return f"невідомий ({self.error}; task board таку задачу не бере)"
        said = f"рядок «Режим: {self.line}»" if self.line is not None else f"рядка «Режим:» немає → {DEFAULT}"
        raised = "; ".join(f"піднято {r.utc} з {r.before} на {r.after} — {r.why}" for r in self.raises)
        return f"{self.current} ({said}" + (f"; {raised}" if raised else "") + ")"


def _normal(value: str) -> str:
    return value.strip().strip("*_.!").strip().lower()


def parse(text: str) -> Mode:
    """The mode of a task file. The line is read in the header only (above the first `## `)."""
    text = COMMENT.sub("", text)
    first = HEADING.search(text)
    lines = LINE.findall(text[: first.start()] if first else text)
    raises = tuple(Raise(*m.groups()) for m in RAISE_LINE.finditer(_raised_section(text))
                   if m.group(2) in MODES and m.group(3) in MODES)
    if not lines:
        return Mode(None, raises)
    if len(lines) > 1:
        return Mode(lines[0], raises, "рядків «Режим:» два або більше — незрозуміло, котрий чинний")
    if _normal(lines[0]) not in MODES:
        return Mode(lines[0], raises, f"«Режим: {lines[0]}» — такого режиму немає: {', '.join(MODES)}")
    return Mode(lines[0], raises)


def _raised_section(text: str) -> str:
    found = RAISED_HEADING.search(text)
    if not found:
        return ""
    rest = text[found.end():]
    following = HEADING.search(rest)
    return rest[: following.start()] if following else rest


# ------------------------------------------------------------------ the session


def unattended(root: Path) -> tuple[bool, str]:
    """(nobody is watching, where that was read: `env` or `mode-file`; "" when attended)."""
    if os.environ.get(ENV) == "1":
        return True, "env"
    try:
        said = (root / MODE_FILE).read_text(encoding="utf-8")
    except (OSError, ValueError):
        said = ""
    return (True, "mode-file") if _normal(said) == "unattended" else (False, "")


def _board() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unattended"))
    import board  # here, not at the top: board.py imports this module

    return board


def own_task(root: Path) -> list[Path]:
    """The session's tasks in doing/ (board.py `own`): one, or none when there is no board task."""
    tasks = root / "tasks"
    return list(_board().own(tasks)) if (tasks / "doing").is_dir() else []


def accompaniment(root: Path) -> tuple[bool, str]:
    missing = [p for p in (BASELINE, PROFILE) if not (root / p).is_file()]
    return (False, "немає " + " і ".join(missing)) if missing else (True, f"{BASELINE} і {PROFILE}")


def work_type(root: Path) -> tuple[str, str]:
    """(`type:` of the card IN PROGRESS, where it was read) — `—` when there is no such card."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import complexity_budget

        card = complexity_budget.active_contract(root)
    except (ImportError, OSError, ValueError):
        card = None
    if card is None:
        return "—", "у .engine/PROGRESS.md немає картки IN PROGRESS"
    found = TYPE_LINE.search(card.read_text(encoding="utf-8"))
    shown = card.relative_to(root).as_posix() if card.is_relative_to(root) else str(card)
    return (found.group(1), shown) if found else ("—", f"{shown} без рядка type:")


def show_line(root: Path, task: Path | None = None) -> str:
    """The one line `show` prints: the task given, else the session's task in doing/."""
    if task is None:
        mine = own_task(root)
        task = mine[0] if len(mine) == 1 else None
    if task is None:
        mode = "— (у tasks/doing/ немає задачі цієї сесії: без задачі task board режим задає команда власника)"
    else:
        name = task.parent.name if task.name == "task.md" else task.stem
        mode = f"{parse(task.read_text(encoding='utf-8')).shown()}, задача {name}"
    with_owner, said = accompaniment(root)
    alone, where = unattended(root)
    kind, card = work_type(root)
    return (f"режим: {mode} · супровід: {'так' if with_owner else 'ні'} ({said}) · "
            f"без нагляду: {'так (' + SOURCES[where] + ')' if alone else 'ні (ні змінної runner-а, ні файла режиму)'} · "
            f"тип роботи: {kind} ({card})")


def refusal(root: Path, command: str, task: Path | None = None) -> str | None:
    """Why `command` (hotfix, bugfix) may not run in the mode of `task` — the task file given, else
    the session's task in doing/. None when it may, or when there is no board task."""
    if task is None:
        mine = own_task(root)
        task = mine[0] if len(mine) == 1 else None
    try:
        text = task.read_text(encoding="utf-8") if task else ""
    except OSError:
        text = ""
    current = parse(text).current if text else ""
    reason = FORBIDDEN.get((current, command))
    return f"{reason} (task {task.name if task else '-'}, python3 .claude/hooks/mode.py show)" if reason else None


# ------------------------------------------------------------------ raise


def raise_mode(path: Path, target: str, why: str, now: str) -> str | None:
    """Append the raise to the task file; the reason it is refused, or None when it is written."""
    text = path.read_text(encoding="utf-8")
    mode = parse(text)
    why = " ".join(why.replace("<!--", "<! --").split())
    if mode.error:
        return f"the task's own line names no mode ({mode.error}); only the owner can say which one is meant"
    if target not in MODES:
        return f"«{target}» is no mode: {', '.join(MODES)}"
    if MODES.index(target) <= MODES.index(mode.current):
        return (f"the task is in «{mode.current}» already; a raise goes up only ({' → '.join(MODES)}) — "
                "a lighter mode is set by the owner alone, in the task's line")
    if not why:
        return "--why is empty: a raise says why"
    line = f"- {now} — {mode.current} → {target}: {why}"
    path.write_text(_with_line(text, line), encoding="utf-8")
    return None


def _with_line(text: str, line: str) -> str:
    """`text` with `line` at the end of the section `## Режим піднято`, made before the questions
    (or at the end) the first time."""
    text = text.rstrip("\n") + "\n"
    found = RAISED_HEADING.search(text)
    if found:
        rest = text[found.end():]
        following = HEADING.search(rest)
        cut = found.end() + (following.start() if following else len(rest))
        return text[:cut].rstrip("\n") + f"\n{line}\n" + ("\n" if following else "") + text[cut:]
    questions = QUESTIONS.search(text)
    if questions:
        head, tail = text[: questions.start()], text[questions.start():]
        return head.rstrip("\n") + f"\n\n{RAISED}\n{line}\n\n" + tail
    return text + f"\n{RAISED}\n{line}\n"


def cmd_raise(root: Path, target: str, why: str) -> int:
    mine = own_task(root)
    if len(mine) != 1:
        print(f"REFUSED: tasks/doing/ holds {len(mine)} tasks of this session, not one: a raise is written into the task in hand",
              file=sys.stderr)
        return EXIT_REFUSED
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    reason = raise_mode(mine[0], target, why, now)
    if reason:
        print(f"REFUSED: {reason}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"RAISED: {mine[0].relative_to(root).as_posix()} — {parse(mine[0].read_text(encoding='utf-8')).shown()}")
    return EXIT_OK


# ------------------------------------------------------------------ the minimum at closing (board 098)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def _lines(result: subprocess.CompletedProcess[bytes]) -> list[str]:
    return [line for line in result.stdout.decode("utf-8", "surrogateescape").splitlines() if line] if result.returncode == 0 else []


def _hooks() -> tuple[Any, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import overseer_stop
    import overseer_verdict

    return overseer_stop, overseer_verdict


def working_code(root: Path, env_text: str | None = None) -> Any:
    """The test «is this path working code?»: a code path as the Stop hook reads it (what asks for an
    audit — empty settings mean every file), never the board's or the engine's records. `env_text` is
    .claude/project.env as another commit has it (the review reads origin's), instead of the checkout's."""
    stop, _ = _hooks()
    if env_text is None:
        env = stop._load_project_env(root) if (root / ".claude" / "project.env").is_file() else {}
    else:
        import gate

        env = gate.parse_env_text(env_text)
    dirs, exts = stop._build_source_dirs(env), stop._build_code_extensions(env)

    def is_code(rel: str) -> bool:
        return not rel.startswith(RECORDS) and stop._is_code_path(rel, dirs, exts)

    return is_code


def _stays(root: Path, stem: str, head: str = "HEAD") -> list[tuple[str, str]]:
    """(the commit that brought tasks/doing/<stem>.md in, the one that took it out or ""), oldest first."""
    moves = _git(root, "log", "--reverse", "--no-renames", "-z", "--format=%x01%H", "--name-status", head, "--", f"tasks/doing/{stem}.md")
    stays: list[tuple[str, str]] = []
    for record in moves.stdout.decode("utf-8", "surrogateescape").split("\x01")[1:] if moves.returncode == 0 else []:
        fields = record.split("\0")   # «<sha>», «\n<status>», «<path>», …
        sha, status = fields[0].strip(), (fields[1].strip()[:1] if len(fields) > 1 else "")
        if status == "A":
            stays.append((sha, ""))
        elif status == "D" and stays and not stays[-1][1]:
            stays[-1] = (stays[-1][0], sha)
    return stays


def task_commits(root: Path, stem: str, head: str = "HEAD") -> list[str] | None:
    """The task's commits, oldest first: those of every stay of tasks/doing/<stem>.md; the last stay runs
    past the move to done/ (the turn back) until another task enters doing/. None when it never was there.
    `head` is the commit the history is read from (the review reads the work branch as origin has it)."""
    stays = _stays(root, stem, head)
    if not stays:
        return None
    commits: list[str] = []
    for number, (came, left) in enumerate(stays):
        end = left or head
        if number == len(stays) - 1:
            after = _lines(_git(root, "log", "--reverse", "--format=%H", "--diff-filter=A", "--no-renames", f"{left or came}..{head}",
                                "--", "tasks/doing/"))
            end = f"{after[0]}^" if after else head
        commits += [c for c in _lines(_git(root, "rev-list", "--reverse", "--no-merges", f"{came}..{end}")) if c not in commits]
    return commits


def _changed(root: Path, commit: str) -> list[str]:
    """The paths a commit changed, unquoted (-z): a name outside ASCII is not wrapped in quotes."""
    out = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", "-z", commit)
    return [rel for rel in out.stdout.decode("utf-8", "surrogateescape").split("\0") if rel] if out.returncode == 0 else []


def _digest(root: Path, commit: str, rel: str) -> str:
    """The content of a file at a commit as the request's tree fingerprint writes it: sha256[:16], or `absent`."""
    blob = _git(root, "cat-file", "blob", f"{commit}:{rel}")
    return hashlib.sha256(blob.stdout).hexdigest()[:16] if blob.returncode == 0 else "absent"


def passed_trees(root: Path, stem: str) -> list[dict[str, Any]]:
    """The tree fingerprints of the requests the overseer answered PASS for this task's units — or with no
    task in doing/ (`-`): the runner's turn back runs when the task is already in done/."""
    _, ov = _hooks()
    trees = []
    try:
        rows = [json.loads(line) for line in (root / ov.VERDICTS_REL).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        rows = []
    for row in rows:
        named = str(row.get("unit_key", "")).split("|")[1:2] if isinstance(row, dict) else []
        if not isinstance(row, dict) or row.get("verdict") != "PASS" or named not in ([stem], ["-"]):
            continue   # a PASS on another task's unit is not this one's; "-" is an audit with no task in doing/ (the turn back)
        try:
            request = json.loads((root / ov.REQUESTS_REL / str(row.get("request")) / "request.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tree = request.get("tree") if isinstance(request, dict) else None
        if isinstance(tree, dict) and isinstance(tree.get("files"), dict) and tree.get("head"):
            trees.append(tree)
    return trees


def _seen(root: Path, tree: dict[str, Any], rel: str) -> str:
    recorded = tree["files"].get(rel)
    return str(recorded).partition(":")[2] if recorded is not None else _digest(root, str(tree["head"]), rel)


def _left_by_others(root: Path, commit: str, rel: str, own: set[str]) -> list[tuple[str, str]]:
    """(another task's later commit in the file, the content it left), up to the task's own next commit in
    it: a PASS of the task whose request held such a commit saw this commit's change with theirs on top (board 1730)."""
    left: list[tuple[str, str]] = []
    for later in _lines(_git(root, "log", "--reverse", "--format=%H", "--no-renames", "--ancestry-path", f"{commit}..HEAD", "--", rel)):
        if later in own:
            break   # from here the task's own commit answers for the file (board 754)
        left.append((later, _digest(root, later, rel)))
    return left


def _saw(root: Path, tree: dict[str, Any], rel: str, commit: str, left: list[tuple[str, str]]) -> bool:
    """The PASS saw the file as the commit has it, or as another task's later commit left it — and that commit
    was in its request's history: the same content from before it is not the commit's code."""
    seen = _seen(root, tree, rel)
    return seen == _digest(root, commit, rel) or any(
        seen == digest and _git(root, "merge-base", "--is-ancestor", later, str(tree["head"])).returncode == 0 for later, digest in left)


def unaudited(root: Path, stem: str, commits: list[str]) -> list[str]:
    """Each commit of the task that changed working code no PASS of the overseer saw, as a line, oldest first.
    Read newest first: a file a later covered commit changed needs no PASS of its own (board 754); nor does a
    file a PASS of the task saw as another task's later commit left it (board 1730)."""
    is_code = working_code(root)
    trees = passed_trees(root, stem)
    missing: list[str] = []
    replaced: set[str] = set()   # the files a later covered commit of the task changed: what it left is what a PASS saw
    own = set(commits)
    for commit in reversed(commits):
        code = [rel for rel in _changed(root, commit) if is_code(rel)]
        if not code:
            continue
        left = {rel: _left_by_others(root, commit, rel, own) for rel in code if rel not in replaced}
        if any(all(rel in replaced or _saw(root, tree, rel, commit, left[rel]) for rel in code) for tree in trees):
            replaced.update(code)
            continue
        subject = _lines(_git(root, "log", "-1", "--format=%s", commit))
        missing.append(f"commit {commit[:10]} («{subject[0] if subject else '?'}») змінив робочий код ({', '.join(code[:5])}"
                       f"{', …' if len(code) > 5 else ''}), а PASS overseer-а, що бачив саме цей код, у журналі вердиктів немає")
    return missing[::-1]


def pipeline_missing(root: Path, commits: list[str]) -> list[str]:
    """конвеєр: the feature artifact and a matching seal on every slice contract the task wrote."""
    changed = sorted({rel for commit in commits for rel in _changed(root, commit)})
    features = [rel for rel in changed if rel.startswith(FEATURES) and rel.endswith(".md") and (root / rel).is_file()]
    # A contract is `.engine/slices/<slug>.md` itself: not the overrun records under overruns/, not <slug>.behaviors.md (board 201).
    slices = [rel for rel in changed if rel.startswith(SLICES) and "/" not in rel[len(SLICES):] and rel.endswith(".md")
              and not rel.endswith(".behaviors.md") and (root / rel).is_file()]
    missing = [] if features else [f"артефакту функції ({FEATURES}<назва>.md) серед змін задачі немає"]
    if not slices:
        missing.append(f"жодного slice contract-у ({SLICES}<slug>.md) серед змін задачі немає")
    for rel in slices:
        seal = root / SEALS / f"{Path(rel).stem}.sha256"
        if not seal.is_file():
            missing.append(f"slice contract {rel} не запечатано: немає {SEALS}/{seal.name}")
        elif seal.read_text(encoding="utf-8").split()[:1] != [hashlib.sha256((root / rel).read_bytes()).hexdigest()]:
            missing.append(f"slice contract {rel} змінено після печатки ({SEALS}/{seal.name})")
    return missing


def sketch_missing(root: Path, commits: list[str]) -> list[str]:
    """ескіз: nothing outside the quarantine, a record among the task's changes, a reader's PASS on each record as it is."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reader

    changed = sorted({rel for commit in commits for rel in _changed(root, commit)})
    missing = [f"задача-ескіз змінила файл поза карантином (sketches/, .engine/, tasks/): {rel}" for rel in changed if not rel.startswith(QUARANTINE)]
    records = [rel for rel in changed if rel.startswith(SKETCH_RECORDS) and rel.endswith(".md") and (root / rel).is_file()]
    if not records:
        missing.append(f"запису ескізу ({SKETCH_RECORDS}<назва>.md) серед змін задачі немає")
    missing += [f"на запис {rel} немає PASS агента-читача, що читав його таким, як він є (reader.py)" for rel in records if not reader.passed(root, rel)]
    return missing


def unread(root: Path, stem: str, commits: list[str]) -> list[str]:
    """A task none of whose commits changed working code: the reader's PASS on its report as it is, read
    with every document the commits changed. Nothing for a task with working code — the overseer judged it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reader

    is_code = working_code(root)
    changed = [rel for commit in commits for rel in _changed(root, commit)]
    report = f"tasks/done/{stem}/report.md"
    if any(is_code(rel) for rel in changed) or not (root / report).is_file() or reader.passed(root, report, reader.documents(changed, report)):
        return []
    return [(f"задача не змінила робочого коду, а PASS агента-читача на її звіт {report} — такий, як він є, разом з усіма документами, "
             f"які змінила задача, — у журналі читача немає (python3 .claude/hooks/reader.py request {stem} --report)")]


def check_close(root: Path, stem: str) -> tuple[str, list[str]]:
    """(the mode in force, what of its minimum is missing) for the task in tasks/done/<stem>/."""
    folder = root / "tasks" / "done" / stem
    mode = parse((folder / "task.md").read_text(encoding="utf-8")).current or DEFAULT
    missing = [] if (folder / "report.md").is_file() else [f"у tasks/done/{stem}/ немає report.md"]
    commits = task_commits(root, stem)
    if commits is None:
        return mode, [*missing, "задача ніколи не лежала в tasks/doing/ у git: невідомо, які commit-и її"]
    if mode == "ескіз":
        return mode, missing + sketch_missing(root, commits)
    missing += unaudited(root, stem, commits) + unread(root, stem, commits)
    if mode == "конвеєр":
        missing += pipeline_missing(root, commits)
    return mode, missing


def cmd_check_close(root: Path, given: str) -> int:
    stem = Path(given.rstrip("/")).name.removesuffix(".md")
    stem = Path(given.rstrip("/")).parent.name if stem == "task" else stem
    if not (root / "tasks" / "done" / stem / "task.md").is_file():
        print(f"REFUSED: tasks/done/{stem}/task.md is not there: check-close judges a task the agent has moved to done/", file=sys.stderr)
        return EXIT_REFUSED
    mode, missing = check_close(root, stem)
    if not missing:
        print(f"мінімум режиму «{mode}» є: {stem}")
        return EXIT_OK
    print(f"мінімуму режиму «{mode}» немає: {stem}")
    for line in missing:
        print(f"- {line}")
    return EXIT_MISSING


# ------------------------------------------------------------------ entry


def project_root() -> Path:
    given = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if given and Path(given).is_dir():
        return Path(given)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None, help="the project (default: CLAUDE_PROJECT_DIR, else the git repository here)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show").add_argument("--task", type=Path, default=None, help="a task file (default: the session's task in doing/)")
    raising = commands.add_parser("raise")
    raising.add_argument("mode", help=" | ".join(MODES))
    raising.add_argument("--why", required=True)
    commands.add_parser("unattended")
    commands.add_parser("check-close").add_argument("task", help="NNN-name, or its folder or task.md in tasks/done/")
    args = parser.parse_args(argv)
    root = (args.root or project_root()).resolve()
    if args.command == "check-close":
        try:
            return cmd_check_close(root, args.task)
        except Exception as exc:  # noqa: BLE001 — gate-allow: a check that breaks must say so with its own code, never pass for «missing»
            print(f"BROKEN: check-close could not judge {args.task}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_BROKEN
    if args.command == "raise":
        return cmd_raise(root, args.mode, args.why)
    if args.command == "unattended":
        alone, where = unattended(root)
        print(f"unattended {where}" if alone else "attended")
        return EXIT_OK if alone else EXIT_ATTENDED
    task = args.task if args.task is None or args.task.is_absolute() else root / args.task
    if task is not None and not task.is_file():
        print(f"REFUSED: {args.task} is not a file", file=sys.stderr)
        return EXIT_REFUSED
    print(show_line(root, task))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
