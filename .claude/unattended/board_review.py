"""The owner's review of the task board: one markdown document, and nothing is changed (board 009).

    board.py review [--since <commit|date>] [--offline] [--remote origin] [--branch unattended/work]

The owner reviews when there is time for it, not when a task ends. So the review may run at any
moment, next to a runner in the middle of a task, and from any clone. Two things make that safe:

WHAT IT READS. The board as the work branch has it IN ORIGIN — never the checkout it is run
from, which on the runner's machine is half-way through something. `git ls-remote` names the
commit; when this clone lacks it, the commit is fetched as objects only (`--refmap=`,
`--no-write-fetch-head`): no ref, no index and no file of the working tree is written, so a
runner pulling at the same moment meets no lock of ours. With origin out of reach the last
state this clone knows (its remote-tracking ref) is shown, and the document says so.
The runner's own state — `.claude/state/board/` — is not in git; it is read when the review runs
on the runner's machine and replaced by what git shows when it does not.

WHAT IT SHOWS, in sections: the state now; what was done since `--since` (default: the
newest version tag), each finished task with the owner's parts of its report; the changed documents
and designs to look over (board 100; the approved design is board 080, §6) — every closed task none of
whose commits changed working code, with its title, the documents it changed and the verdict of the
fresh reader (.engine/reader/ledger.md), shown until its number stands in tasks/.reviewed as the
branch has it, whatever `--since` says; closing never waited for this, and a problem found is a new
task. The list begins where the reader first read a task's report in this project: a task closed
before that was never promised a reading, and one that never lay in doing/ (the runner closed the
owner's own answer) holds nothing an agent wrote; everything that
waits for the owner — every unfilled `Відповідь:` in blocked/ with the text above it, the
tasks that need the owner present (`Потрібна присутність власника: так`, board 016), the
settings proposals, the gate's open escalations, the rule proposals (board 037: what is open is read from the board
only — the logs .engine/overseer/escalations.md and parked.md are history and are not read here); the goals document (board 051: the decisions
that cite no line of it, the architects' requests to the analyst and which were closed by a quote, the amendments and what
they touched, the analyst's lessons — read by .claude/hooks/goals.py, figures to read and not targets); the new entries of the anomaly journal
tasks/ANOMALIES.md, after the overdue debts of urgent fixes (board 075; the open ones stand on a line of the state now) (board 021: what the runner — and since board 035 the gate, a hook or the agent — found odd and worked past); the plan; the
candidates for new tasks; the health — the last runs of the suites and of the golden set from the machine
records the tools leave in .claude/state/health/ (board 035), not from anybody's prose. `--since` narrows what was DONE (and the anomalies, the
candidates and the costs that come from it); what waits and what is planned is always shown whole. The last line is
the command for the next review.

Exit 0: the document is on stdout. Exit 2: no document — the branch is known neither to origin
nor to this clone, or `--since` is neither a commit nor a date.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import board
import board_state

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import goals  # the goals document's reader lives with the hooks
import hotfix  # and so does the reader of the urgent fixes' debts (.engine/debt.md, board 075)
import journal  # the journals every session adds to in its own file (board 739)
import mode as mode_reader  # and the one reader of a task's mode (board 097)
import reader as record_reader  # which of a task's changes are documents (board 100)
import testing  # and the reader of the testing ledger (.engine/testing/ledger.md, board 062)

CONTEXT_BUDGET = 200
MAX_HOPS = 4  # how deep Claude Code follows `@path` imports (tests/test_context_budget.py)
IMPORT_RE = re.compile(r"(?:(?<=\s)|^)@([^\s`]+)", re.MULTILINE)
FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
SPAN_RE = re.compile(r"`[^`\n]*`")
STATUS = re.compile(r"^state=(\S+) task=(\S+) since=(\S+)(?: reason=(.*))?$")
PROPOSAL = re.compile(r"^## (RP-\w+) — \S+ — PROPOSED[ \t]*$", re.MULTILINE)
GOLDEN = re.compile(r"^evals/baseline/[^/]+/results-[^/]+\.json$")
FINDING_MAX = 260
ATTEMPT = re.compile(r"^(\S+) attempt(-end)? (\S+) (\d+)(?: |$)")  # events.log: `<UTC> attempt <task> <n> …`, `… attempt-end <task> <n> …`
ANOMALY = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) — (.+)$")
# The runner's states (board-runner.sh), as the owner reads them.
STATES = {
    "running": "працює",
    "waiting-limit": "чекає, поки відновиться ліміт використання",
    "idle": "зупинився: у todo/ нічого немає",
    "waiting-owner": "зупинився: усе, що лишилося, чекає власника",
    "stopped": "зупинився після однієї задачі, як і просили",
    "error": "зупинився через помилку",
}
# The parts of a report the review quotes, by the start of the heading (reports word them freely).
OWNER_PARTS = (("що змінилось для власника",), ("демонстрація",), ("рішення, які я ухвалив сам",), ("витрати",), ("commit", "діапазон commit"))
CANDIDATE_PARTS = (("відкладене",), ("чого мені бракувало",))
READER_LEDGER = record_reader.LEDGER_REL.as_posix()
READING = re.compile(r"^## (\S+) — \S+ — READER_(PASS|BLOCK|INVALID)\n- Record: (tasks/done/[^/\n]+/report\.md)\n- Reason: (.*)$", re.MULTILINE)
DOCUMENTS_SHOWN = 12


class ReviewError(Exception):
    """No document can be made; the text is the reason."""


def git(root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Git that only reads, and never stops to ask for a password: a remote that wants one is out of reach."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    command = ["git", "-C", str(root), "-c", "core.quotepath=false", *args]
    try:
        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False, env=env,
                              stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "timed out")


class Source:
    """One commit of the work branch, read through git."""

    def __init__(self, root: Path, sha: str, name: str, note: str) -> None:
        self.root, self.sha, self.name, self.note = root, sha, name, note
        listed = git(root, "ls-tree", "-r", "-z", "--name-only", sha).stdout
        self.files = frozenset(p for p in listed.split("\0") if p)

    def show(self, path: str) -> str:
        return git(self.root, "show", f"{self.sha}:{path}").stdout if path in self.files else ""

    def column(self, name: str) -> list[str]:
        """The task files of todo/, doing/, blocked/ or proposed/, lowest number first — as board.Board.files."""
        prefix = f"tasks/{name}/"
        found = [p for p in self.files if p.startswith(prefix) and board.TASK_NAME.match(p[len(prefix):])]
        return sorted(found, key=lambda p: (board.number_of(posixpath.basename(p)) or 0, p))

    def done(self) -> list[str]:
        stems = {p.split("/")[2] for p in self.files if p.startswith("tasks/done/") and p.count("/") == 3 and p.endswith("/task.md")}
        return sorted((s for s in stems if board.DONE_NAME.match(s)), key=lambda s: (board.number_of(s) or 0, s))

    def log(self, *args: str) -> str:
        return git(self.root, "log", *args).stdout.strip()

    def whole(self, name: str) -> str:
        """One journal whole at this commit: the shared file and every session's file (board 739)."""
        return journal_at(self.files, self.show, name)


def whole(src: Any, name: str) -> str:
    """src.whole(name) for anything with `files` and `show` — a Source, or a suite's stand-in for one."""
    return journal_at(src.files, src.show, name)


def journal_at(files: frozenset[str] | set[str], show: Any, name: str) -> str:
    kind = journal.JOURNALS[name]
    prefix = f"{journal.PIECES_REL.as_posix()}/{name}/"
    return journal.assemble(kind, show(kind.shared), [show(p) for p in sorted(files) if p.startswith(prefix) and p.endswith(".md")])


def journal_at_commit(root: Path, commit: str, name: str) -> str:
    listed = git(root, "ls-tree", "-r", "-z", "--name-only", commit).stdout
    files = {p for p in listed.split("\0") if p}
    return journal_at(files, lambda path: git(root, "show", f"{commit}:{path}").stdout if path in files else "", name)


def has_commit(root: Path, sha: str) -> bool:
    return git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def source(root: Path, remote: str, branch: str, offline: bool) -> Source:
    name = f"{remote}/{branch}"
    note = "без звернення до origin (--offline): стан, який цей клон бачив востаннє"
    if not offline:
        asked = git(root, "ls-remote", remote, f"refs/heads/{branch}", timeout=30)
        sha = asked.stdout.split()[0] if asked.returncode == 0 and asked.stdout.split() else ""
        if sha and not has_commit(root, sha):
            # Objects only: no ref and no FETCH_HEAD, so nothing a runner's pull could trip over.
            git(root, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--refmap=", remote, f"refs/heads/{branch}", timeout=120)
        if sha and has_commit(root, sha):
            return Source(root, sha, name, "")
        if asked.returncode == 0 and not sha:
            raise ReviewError(f"{remote} has no branch {branch}: nothing to review (the work branch is named by --branch or BOARD_BRANCH)")
        note = f"{remote} недосяжний: показано стан, який цей клон бачив востаннє"
    known = git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/{name}^{{commit}}").stdout.strip()
    if not known:
        raise ReviewError(f"the branch {branch} of {remote} cannot be reached and this clone has never seen it: nothing to review")
    return Source(root, known, name, note)


@dataclass(frozen=True)
class Since:
    shown: str
    revisions: tuple[str, ...]  # what `git log` takes to list the period
    utc: datetime | None        # the same moment for the runner's records; None: from the start
    commit: str = ""            # the commit the period starts after, when it was named by one


def as_utc(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def since(src: Source, given: str | None) -> Since:
    label = given
    if given is None:
        label = git(src.root, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", src.sha).stdout.strip()
        if not label:
            return Since("від початку (міток версій у гілці немає)", (src.sha,), None)
    assert label is not None
    commit = git(src.root, "rev-parse", "--verify", "--quiet", f"{label}^{{commit}}").stdout.strip()
    if commit:
        moment = as_utc(git(src.root, "log", "-1", "--format=%cI", commit).stdout)
        what = f"мітки версії `{label}`" if given is None else f"commit-а `{label}`"
        return Since(f"від {what} ({commit[:7]}, {stamp(moment)})", (f"{commit}..{src.sha}",), moment, commit)
    moment = as_utc(label)
    if moment is None:
        raise ReviewError(f"--since {label}: neither a commit of this repository nor a date (2026-10-03 or 2026-10-03T14:00:00Z)")
    return Since(f"від {stamp(moment)}", (f"--since={moment.isoformat()}", src.sha), moment)


def mode_of(text: str) -> str:
    """The task's mode as the one reader shows it (.claude/hooks/mode.py, board 097)."""
    return mode_reader.parse(text).shown()


def stamp(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC") if moment else "час невідомий"


def elapsed(start: datetime, end: datetime) -> str:
    minutes = max(0, int((end - start).total_seconds()) // 60)
    days, hours, rest = minutes // 1440, minutes % 1440 // 60, minutes % 60
    parts = [f"{days} дн" if days else "", f"{hours} год" if days or hours else "", f"{rest} хв"]
    return " ".join(p for p in parts if p)


def title_of(text: str, fallback: str) -> str:
    first = next((line for line in text.splitlines() if line.startswith("# ")), "")
    return first[2:].strip() or fallback


# ------------------------------------------------------------------ reports


def sections(text: str) -> list[tuple[str, str]]:
    """The `## ` sections of a report: (heading, body). A `## ` line inside a code block is text."""
    found: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if heading is not None:
                found.append((heading, "\n".join(body).strip()))
            heading, body = line[3:].strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        found.append((heading, "\n".join(body).strip()))
    return found


def pick(found: list[tuple[str, str]], prefixes: tuple[str, ...]) -> tuple[str, str] | None:
    return next(((h, b) for h, b in found if b and h.lower().startswith(prefixes)), None)


def quoted(heading: str, body: str) -> list[str]:
    """A report's section inside the review: its heading in bold, its own headings pushed down."""
    lines = [f"**{heading}**", ""]
    fenced = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        lines.append("##" + line if not fenced and line.startswith("#") else line)
    return [*lines, ""]


# ------------------------------------------------------------------ the runner's state


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def task_costs(state: Path) -> dict[str, dict[str, Any]]:
    """costs.json's tasks; each that started extra sessions of Claude (board 078) carries them as
    `extra`: (how many, what they cost)."""
    tasks = load_json(state / "board/costs.json").get("tasks")
    costs = {str(k): v for k, v in tasks.items() if isinstance(v, dict)} if isinstance(tasks, dict) else {}
    for name, extra in board_state.extra_sessions(state / "board").items():
        if name:
            costs.setdefault(name, {})["extra"] = extra
    return costs


def extra_line(entry: dict[str, Any] | None) -> str:
    """The extra sessions of Claude a task started (evals, measurements), for the owner; empty with none."""
    extra = (entry or {}).get("extra")
    return f" Додаткових сесій Claude (evals, виміри): {extra[0]}, ${float(extra[1]):.2f}." if extra else ""


def runner_alive(state: Path) -> bool | None:
    """Whether the process named in the runner's lock exists. None: no lock to judge by."""
    try:
        pid = int((state / "board/lock").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def task_line(name: str, entry: dict[str, Any] | None, now: datetime) -> str:
    line = f"- Задача у runner-а: `{name}`"
    if entry:
        begun = as_utc(str(entry.get("started_utc", "")))
        line += f", триває {elapsed(begun, now)}" if begun and "outcome" not in entry else ""
        line += f"; витрачено ${float(entry.get('cost_usd', 0.0)):.2f} за {len(entry.get('attempts') or [])} завершених спроб"
        idle = int(entry.get("attempts_without_commit", 0) or 0)
        line += f", із них поспіль без commit-а: {idle}" if idle else ""
    return line + "." + extra_line(entry)


def attempt_line(state: Path, name: str, entry: dict[str, Any] | None, now: datetime) -> str | None:
    """The attempt in hand, as far as the state files show it: events.log has its start and no end
    yet. Its cost is in no file until it ends — the session reports one figure, at its end."""
    try:
        events = (state / "board/events.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    marks = [m for m in map(ATTEMPT.match, events) if m and m.group(3) == name]
    if not marks or marks[-1].group(2):
        return None
    begun = as_utc(marks[-1].group(1))
    spent = float((entry or {}).get("cost_usd", 0.0))
    return (f"- Спроба, що триває: №{marks[-1].group(4)}, від {stamp(begun)}" + (f" — {elapsed(begun, now)}" if begun else "")
            + ". Її вартості у файлах стану ще немає: сесія агента повідомляє суму один раз, наприкінці спроби; "
            + f"до цієї спроби на задачу записано ${spent:.2f}.")


def runner_lines(src: Source, state: Path, status: re.Match[str], now: datetime) -> list[str]:
    word, name, started, reason = status.group(1), status.group(2), as_utc(status.group(3)), status.group(4)
    working = word in ("running", "waiting-limit")
    lines = [f"За файлами стану runner-а (`{os.path.relpath(state / 'board', src.root)}/`, ця машина):",
             f"- Runner: **{STATES.get(word, word)}** (`{word}`), у цьому стані від {stamp(started)}"
             + (f" — {elapsed(started, now)}" if started else "") + (f"; причина: `{reason}`" if reason else "") + "."]
    if working and runner_alive(state) is False:
        lines.append("- Увага: процесу runner-а з файла `lock` на цій машині немає — запис стану міг застаріти.")
    if name != "-":
        entry = task_costs(state).get(name)
        lines.append(task_line(name, entry, now))
        running = attempt_line(state, name, entry, now) if working else None
        lines += [running] if running else []
    summary = state / "board/summary.md"
    if not working and summary.is_file():
        lines += [f"- Підсумок останнього запуску: {said[2:]}" for said in summary.read_text(encoding="utf-8").splitlines() if said.startswith("- Стан:")]
    return lines


def now_section(src: Source, state: Path, now: datetime) -> list[str]:
    try:
        status = STATUS.match((state / "board/status").read_text(encoding="utf-8").strip())
    except OSError:
        status = None
    if status:
        lines = runner_lines(src, state, status, now)
    else:
        lines = [("Файлів стану runner-а тут немає (вони лише на його машині), тож стан — із git; "
                  "витрат і того, чи runner зараз працює або чекає ліміту, з git не видно.")]
    doing = src.column("doing")
    for path in doing:
        moved = as_utc(src.log("-1", "--diff-filter=AR", "--format=%cI", src.sha, "--", path))
        text = src.show(path)
        with_owner = " (**у роботі з власником** — runner її не чіпає і бере наступні)" if board.parse(text).attended else ""
        lines.append(f"- У гілці в `doing/`: `{posixpath.basename(path)}` — {title_of(text, 'без назви')}{with_owner}; "
                     f"узято в роботу {stamp(moved)}" + (f", {elapsed(moved, now)} тому" if moved else "") + f"; режим: {mode_of(text)}.")
    if not doing:
        unpushed = status is not None and status.group(2) != "-"
        lines.append("- У гілці в `doing/` зараз порожньо" + (" (commit, яким задачу взято в роботу, ще не надіслано)." if unpushed else "."))
    counts = "   ".join(f"{c}: {len(src.done() if c == 'done' else src.column(c))}" for c in board.COLUMNS)
    lines.append(f"- Task board: {counts}")
    names = {c: src.done() if c == "done" else [posixpath.basename(p) for p in src.column(c)] for c in board.COLUMNS}
    lines += [f"- **{line}**" for line in board.duplicate_lines(names)]
    return lines + debt_line(src, now)


def debt_line(src: Source, now: datetime) -> list[str]:
    """The open debts of urgent fixes (/hotfix, board 075), on a line of their own; nothing in a
    project that never had one. The overdue ones are shown again among the anomalies."""
    if hotfix.DEBT_REL not in src.files:
        return []
    owed = [d for d in hotfix.debts(src.show(hotfix.DEBT_REL)) if d.open]
    if not owed:
        return [f"- Борги термінових виправлень (`{hotfix.DEBT_REL}`): відкритих немає."]
    late = sum(d.overdue(now.date()) for d in owed)
    return [f"- Борги термінових виправлень (`{hotfix.DEBT_REL}`): відкритих {len(owed)} із межі {hotfix.MAX_OPEN} — "
            + ", ".join(f"`{d.name}` (строк до {d.due})" for d in owed) + f"; прострочених: {late}."
            + (" Наступне термінове виправлення почнеться з питання до вас." if len(owed) >= hotfix.MAX_OPEN else "")]


def overdue_lines(src: Source, now: datetime) -> list[str]:
    late = [d for d in hotfix.debts(src.show(hotfix.DEBT_REL)) if d.overdue(now.date())]
    if not late:
        return []
    head = (f"Прострочені борги термінових виправлень: {len(late)}. Термінове виправлення відклало тест, запис причини й пошук таких самих "
            "місць на сім днів; повного виправлення (`/bugfix`) досі немає.")
    return [head, "", *(f"- **`{d.name}`** — строк минув {d.due} ({d.days_late(now.date())} дн тому), commit `{d.commit}`; "
                        f"продовження: `{d.followup}`" for d in late), ""]


# ------------------------------------------------------------------ done


def new_done(src: Source, period: Since) -> list[str]:
    """The stems under tasks/done/ that gained a file in the period — a task that was finished in it."""
    added = src.log("--format=", "--name-only", "--diff-filter=AR", *period.revisions, "--", "tasks/done")
    stems = {p.split("/")[2] for p in added.splitlines() if p.startswith("tasks/done/") and p.count("/") >= 3}
    return [s for s in src.done() if s in stems]


def done_section(src: Source, stems: list[str], costs: dict[str, dict[str, Any]]) -> list[str]:
    if not stems:
        return ["За цей період нових готових задач немає."]
    lines: list[str] = []
    for stem in stems:
        folder = f"tasks/done/{stem}"
        report = src.show(f"{folder}/report.md")
        task = src.show(f"{folder}/task.md")
        lines += [f"### {stem} — {title_of(task, stem)}", "", f"Режим: {mode_of(task)}."]
        closed = src.log("-1", "--diff-filter=AR", "--format=%h%x09%cI%x09%s", src.sha, "--", f"{folder}/report.md", f"{folder}/task.md").split("\t")
        if len(closed) == 3:
            lines.append(f"Закрито {stamp(as_utc(closed[1]))}, commit `{closed[0]}` — {closed[2]}")
        if stem in costs:
            spent = (f"За записами runner-а: ${float(costs[stem].get('cost_usd', 0.0)):.2f}, спроб: {len(costs[stem].get('attempts') or [])}."
                     if "cost_usd" in costs[stem] else "Runner цю задачу не вів.")
            lines.append(spent + extra_line(costs[stem]))
        lines.append("")
        found = sections(report)
        if not report:
            lines += ["Звіту `report.md` у теці немає.", ""]
        for prefixes in OWNER_PARTS:
            part = pick(found, prefixes)
            if part:
                lines += quoted(*part)
        lines += [f"Повний звіт: `{folder}/report.md`", ""]
    return lines


# ------------------------------------------------------------------ changed documents and designs (board 100)


def readings(src: Source) -> list[tuple[str, str, str, str]]:
    """The readers' verdicts on tasks' reports, oldest first: (utc, verdict, the report, the reason)."""
    return [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in READING.finditer(src.show(READER_LEDGER))]


def unreviewed(src: Source) -> list[tuple[str, list[str]]]:
    """(the task, the documents it changed) for every closed task without working code the owner has not
    looked over: closed since the reader first read a task's report here, once in doing/, no commit of it
    changed working code, its number not in tasks/.reviewed."""
    read = readings(src)
    if not read:
        return []
    closed = src.log("--format=", "--name-only", "--diff-filter=A", "--no-renames", f"--since={read[0][0]}", src.sha, "--", "tasks/done")
    stems = {p.split("/")[2] for p in closed.splitlines() if p.startswith("tasks/done/") and p.endswith("/task.md")}
    seen = set(board.reviewed_numbers(src.show(f"tasks/{board.REVIEWED}")))
    is_code = mode_reader.working_code(src.root, src.show(".claude/project.env"))
    found = []
    for stem in src.done():
        commits = mode_reader.task_commits(src.root, stem, src.sha) if stem in stems and board.number_of(stem) not in seen else None
        if commits is None:
            continue
        changed = [rel for commit in commits for rel in mode_reader._changed(src.root, commit)]
        if not any(is_code(rel) for rel in changed):
            report = f"tasks/done/{stem}/report.md"
            found.append((stem, [*([report] if report in src.files else []), *record_reader.documents(changed, report)]))
    return found


def verdict_line(read: list[tuple[str, str, str, str]], stem: str) -> str:
    mine = [row for row in read if row[2] == f"tasks/done/{stem}/report.md"]
    if not mine:
        return "Вердикт reader-а: немає — звіт цієї задачі reader не читав."
    utc, verdict, _, reason = mine[-1]
    return f"Вердикт reader-а: {verdict} ({stamp(as_utc(utc))}, читань: {len(mine)})" + (f" — {reason}" if verdict != "PASS" else ".")


def documents_section(src: Source) -> list[str]:
    waiting = unreviewed(src)
    how = (f"Запис висить, доки номера задачі немає у `tasks/{board.REVIEWED}` (номери, по одному в рядку): допишіть його в гілці або покладіть "
           f"файл `{board.REVIEWED}` в inbox — його готує `/owner-review`; агент цього файла не пише. Закриття задачі на вас не чекало. "
           "Знайшли проблему — це нова задача; стару ніхто не відкриває.")
    if not waiting:
        return ["Закритих задач без робочого коду, яких ви ще не переглянули, немає."]
    read = readings(src)
    lines = [f"Закритих задач без робочого коду, яких ви ще не переглянули: {len(waiting)}. {how}", ""]
    for stem, changed in waiting:
        shown = ", ".join(f"`{rel}`" for rel in changed[:DOCUMENTS_SHOWN]) + (f" і ще {len(changed) - DOCUMENTS_SHOWN}" if len(changed) > DOCUMENTS_SHOWN else "")
        lines += [f"### {stem} — {title_of(src.show(f'tasks/done/{stem}/task.md'), stem)}", "", verdict_line(read, stem),
                  f"Змінені документи: {shown or 'жодного'}.", ""]
    return lines[:-1]


# ------------------------------------------------------------------ what waits for the owner


def open_questions(questions: str) -> list[str]:
    """One block per `Відповідь:` line that is empty: everything written above it since the
    previous answer — the question, its context, the options, an offered action."""
    blocks: list[str] = []
    current: list[str] = []
    for line in questions.splitlines():
        answer = board.ANSWER.match(line)
        if answer is None:
            current.append(line)
            continue
        if not answer.group(1).strip():
            blocks.append(textwrap.dedent("\n".join(current)).strip() or "(питання без тексту)")
        current = []
    return blocks


Asked = tuple[str, str, board.Task]  # a blocked task: its path, its text, what board.py reads in it


def question_lines(src: Source, asked: list[Asked]) -> list[str]:
    lines: list[str] = []
    for path, text, task in asked:
        blocks = open_questions(task.questions)
        if not blocks:
            continue
        name = posixpath.basename(path)
        lines += [f"### {name} — {title_of(text, name)}", f"Режим: {mode_of(text)}."]
        draft = f"tasks/blocked/report-{name}"
        if draft in src.files:
            lines.append(f"Що зроблено і чому питання — у чернетці звіту `{draft}`.")
        if task.gate:
            lines.append(f"Це питання поставили gates (ескалація `{task.gate}`): відповідь `так` (рівно це слово) закриє її, інший текст — вказівка агентові.")
        if task.action:
            lines.append(f"Тут є дія runner-а `{task.action}`: відповідь `так` (рівно це слово) під тим питанням виконає її; інший текст — вказівка агентові.")
        for block in blocks:
            lines += ["", *(f"> {line}".rstrip() for line in block.splitlines()), "> **Відповідь:** _порожньо_"]
        lines.append("")
    return lines


def settings_lines(src: Source, asked: list[Asked]) -> list[str]:
    lines = [f"- `{posixpath.basename(path)}` чекає «так»: дію `{task.action}` виконає runner, не агент."
             for path, _, task in asked if task.action and not task.answered]
    proposal = src.show("docs/tasks/settings.json")
    if proposal and proposal != src.show(".claude/settings.json"):
        lines.append("- `docs/tasks/settings.json` відрізняється від живого `.claude/settings.json`: пропозицію не застосовано.")
    return lines or ["- Немає: жодна задача не чекає «так», пропозиція збігається з живим файлом або її немає."]


def escalation_lines(src: Source, state: Path, asked: list[Asked]) -> list[str]:
    lines = [f"- Gates, на task board: `{posixpath.basename(path)}` (ескалація `{task.gate}`)." for path, _, task in asked if task.gate]
    lines += [f"- Gates, на цій машині: `{entry.get('stamp')}` — slice {entry.get('slice') or 'не названо'}."
              for entry in load_json(state / "gate/escalations.json").get("open") or [] if isinstance(entry, dict)]
    return lines or ["- Немає."]


def rule_lines(src: Source, asked: list[Asked]) -> list[str]:
    proposals = src.show(".engine/rule-proposals.md")
    questions = {task.rule: path for path, _, task in asked if task.rule}
    lines = []
    for match in PROPOSAL.finditer(proposals):
        rule = re.search(r"^- Rule:[ \t]*(.*)$", proposals[match.end():].split("\n## ", 1)[0], re.MULTILINE)
        question = questions.get(match.group(1).removeprefix("RP-"))
        lines.append(f"- `{match.group(1)}`: {rule.group(1).strip() if rule else '(тексту правила немає)'} — "
                     + (f"питання: [`{question}`]({question}); відповідь `так` (рівно це слово) зробить урок правилом."
                        if question else "питання про неї в `tasks/blocked/` немає."))
    return lines or ["- Немає (`.engine/rule-proposals.md`)."]


def attended_lines(src: Source) -> list[str]:
    """The tasks no agent takes alone (board 016): `Потрібна присутність власника: так`, in todo/ or doing/."""
    lines = []
    for column in ("doing", "todo"):
        for path in src.column(column):
            text = src.show(path)
            if board.parse(text).attended:
                name = posixpath.basename(path)
                lines.append(f"- `{name}` — {title_of(text, name)}" + (" — зараз у роботі з власником (у `doing/`); runner-а вона не зупиняє" if column == "doing" else ""))
    if not lines:
        return ["- Немає."]
    return [("Runner їх не бере ніколи; кожна робиться в інтерактивній сесії Claude Code разом із вами (`tasks/README.md`, "
             "«Задачі з присутнім власником»)."), "", *lines]


def proposed_lines(src: Source) -> list[str]:
    """What agents, hooks and the overseer found and could do (board 111): the files of proposed/. Nothing
    takes a task from there; the owner puts one to work."""
    offered = src.column(board.PROPOSED)
    if not offered:
        return [f"- Немає (тека `tasks/{board.PROPOSED}/`)."]
    return [(f"Пропозицій: {len(offered)} (тека `tasks/{board.PROPOSED}/`). Це знахідки агентів, overseer-а й hook-ів; runner їх не бере. "
             "Щоб поставити пропозицію в роботу, покладіть в inbox файл із її номером (можна копію самої пропозиції, можна свій текст) — "
             "він ляже в `todo/`. Непотрібна пропозиція просто лежить далі й нічого не зупиняє."), "",
            *(f"- `{posixpath.basename(path)}` — {title_of(src.show(path), posixpath.basename(path))}" for path in offered)]


def waiting_section(src: Source, state: Path) -> list[str]:
    asked: list[Asked] = [(path, text, board.parse(text)) for path in src.column("blocked") for text in [src.show(path)]]
    total = sum(task.answers.count("") for _, _, task in asked)
    return [(f"Незаповнених відповідей: {total}, у задачах: {sum(1 for _, _, task in asked if '' in task.answers)} (тека `tasks/blocked/`). Відповідь пишеться в "
             "рядок «Відповідь:» файла задачі — у гілці або копією файла в inbox; задача повертається в роботу, коли заповнено всі."), "",
            *question_lines(src, asked),
            "### Задачі, що потребують вашої присутності", "", *attended_lines(src), "",
            "### Пропозиції налаштувань", "", *settings_lines(src, asked), "",
            "### Відкриті ескалації", "", *escalation_lines(src, state, asked), "",
            "### Пропозиції правил", "", *rule_lines(src, asked), "",
            "### Пропозиції нової роботи", "", *proposed_lines(src)]


# ------------------------------------------------------------------ the goals document (board 051)

REQUEST_ENDS = {"quote-valid": "закрито цитатою документа, вас не турбували", "quote-invalid": "цитата НЕ збігається з документом — запит іде до вас",
                "owner": "потрібне ваше рішення", "unanswered": "business analyst ще не відповів",
                "not-required": "документ цього не вимагає (NOT_REQUIRED) — не будується, вас не турбували"}


def goals_section(src: Source) -> list[str]:
    """What the owner sees of level 0: decisions that cite no line, the architects' requests to the
    analyst and how each ended, the amendments and what they touched, the analyst's lessons."""
    document = src.show(goals.GOALS_REL)
    try:
        numbered = goals.items(document)
    except ValueError as broken:
        return [f"- Документ цілей `{goals.GOALS_REL}` зіпсовано: {broken}."]
    asked = goals.requests(src.show, src.files)
    queue = journal.split(whole(src, "lessons"), journal.JOURNALS["lessons"])[1]
    lessons = [line for line in journal.open_candidates(queue) if re.match(r"^- \S+ \| analyst \|", line)]
    if not numbered:
        lines = [f"- Документа цілей (`{goals.GOALS_REL}`) ще немає: його складає `/business-analyst` разом із вами. Доки його немає, рішення архітекторів звіряти ні з чим."]
        if not asked and not lessons:
            return lines
    else:
        standing = sum(not item.struck for item in numbered.values())
        lines = [f"- Документ цілей: версія {goals.version(document)}, чинних рядків {standing}, закреслених {len(numbered) - standing}."]
    loose = goals.unreconciled(src.show, src.files)
    lines += ["", "### Не звірені рішення", "",
              *([f"- `{path}` — {why}" for path, why in loose] or ["- Немає."])]
    lines += ["", "### Запити до business analyst-а", "",
              *([f"- `{posixpath.basename(r.path)}` (привід {r.reason}): {REQUEST_ENDS[r.outcome]}" + (f" — {r.detail}" if r.detail else "") for r in asked] or ["- Немає."])]
    marked = goals.to_review(src.show)
    lines += ["", "### Поправки до документа", "",
              *([f"- {entry}" for entry in goals.changes(document)] or ["- Немає."]),
              *([f"- Чекає перегляду архітектором після поправки: {entry}" for entry in marked])]
    if src.show(goals.PROPOSED_REL):
        lines.append(f"- Запропонована поправка `{goals.PROPOSED_REL}` чекає вашого «так» (питання — в `tasks/blocked/`).")
    lines += ["", "### Уроки business analyst-а, що чекають розбору", "", *([f"- {line[2:]}" for line in lessons] or ["- Немає."])]
    return lines


# ------------------------------------------------------------------ testing

VERDICT_WORDS = {"test_right": "ПРАВИЙ ТЕСТ — знайдено справжню помилку в коді", "test_wrong": "тест був хибний, виправлено",
                 "contract_ambiguous": "slice contract двозначний — питання пішло planner-у"}
KIND_WORDS = {"catch_up": "наздогнати contract tests", "integration": "інтеграційні тести", "mutation": "mutation testing"}


def testing_section(src: Source, period: Since) -> list[str]:
    """What the owner reads of the testing manager and the tester (board 062): reading, not a gate.
    Open things — parked slices and debts — whatever the period; the rest for the period."""
    text = src.show(testing.LEDGER_REL.as_posix())
    every = testing.ledger_rows(text)
    if not every:
        return ["- Журналу тестування (`.engine/testing/ledger.md`) ще немає: жоден slice із запечатаним slice contract не проходив через test manager-а."]
    fresh = [r for r in every if period.utc is None or ((when := as_utc(str(r.get("utc", "")).replace("Z", "+00:00"))) is not None and when >= period.utc)]

    def of(kind: str, pool: list[dict[str, Any]] = fresh) -> list[dict[str, Any]]:
        return [r for r in pool if r.get("type") == kind]

    decisions = of("decision")
    lines = [(f"- Slice-ів із рішенням test manager-а за період: {len({r.get('slice') for r in decisions})}; питань до slice contract, знайдених до коду: "
              f"{sum(len(r.get('questions', [])) for r in of('handin') if r.get('accepted'))}. Це показники для читання, не цілі для агента.")]
    named = {str(r.get("slice")): r["invariants"] for r in decisions if r.get("point") == "a" and isinstance(r.get("invariants"), dict)}
    if named:
        none = sorted(slug for slug, n in named.items() if n.get("section") == "none")
        absent = sum(1 for n in named.values() if n.get("section") == "absent")
        lines.append(f"- Invariants у slice contracts за період: записано {sum(int(n.get('count') or 0) for n in named.values())} у "
                     f"{sum(1 for n in named.values() if n.get('section') == 'named')} slice-ах; «немає — причина» — {len(none)}"
                     + (" (" + "; ".join(f"`{slug}`: {testing.one_line(named[slug].get('none_reason'), 120)}" for slug in none) + ")" if none else "")
                     + (f"; slice contract без розділу (запечатаний раніше) — {absent}" if absent else "")
                     + ". Кожен invariant перевіряється прикладами: бібліотеки property-based testing немає.")
    lines += ["", "### Суперечки про тести", ""]
    rounds = of("round")
    for row in rounds:
        lines += [f"- `{row.get('slice')}`, коло {row.get('round')} із {testing.MAX_ROUNDS}: {item.get('test')} — "
                  f"{VERDICT_WORDS.get(str(item.get('verdict')), item.get('verdict'))} ({testing.one_line(item.get('reason'), 200)})" for item in row.get("items", [])]
    lines += [] if rounds else ["- Немає."]
    lines += ["", "### Відкладені slice-и", "",
              *([f"- `{r.get('slice')}` — третє коло суперечки не проводилось; обидва кола стоять у журналі тестування." for r in of("parked", every)] or ["- Немає."])]
    lines += ["", "### Рішення «не перемикатися»", "",
              *([f"- `{r.get('slice')}`: {testing.one_line(r.get('reason'), 200)} (малий: {testing.one_line(r.get('small'), 120)}; однорідний: {testing.one_line(r.get('uniform'), 120)})"
                 for r in decisions if r.get("decision") == "builder"] or ["- Немає."])]
    fired = [(r, case, why) for r in decisions for case, why in (r.get("mandatory") or {}).items()]
    lines += ["", "### Спрацювання обов'язкових випадків", "",
              *([f"- {case.partition(':')[0]} на `{r.get('slice')}`, точка ({r.get('point')}): {testing.one_line(why, 200)}"
                 + (" — TEST MANAGER САМ ДО ЦЬОГО НЕ ДІЙШОВ, рішення записав скрипт" if r.get("by_script") else "") for r, case, why in fired] or ["- Немає."])]
    debts = testing.debts_of(every)
    lines += ["", "### Борги тестування", "",
              *([f"- {KIND_WORDS.get(d['kind'], d['kind'])} slice-а `{d['slice']}` — відкладено до події `{d['until']}`: {testing.one_line(d.get('reason'), 200)}" for d in debts] or ["- Немає."])]
    results = {r.get("block"): r for r in of("mutation_result", every)}
    runs = [f"- блок `{r.get('block')}`: {r.get('seconds')} с, вихід {r.get('exit')}"
            + (f"; уціліло {results[r.get('block')].get('survived')}, розібрано {results[r.get('block')].get('handled')}" if r.get("block") in results else "; уцілілих ще не розібрано")
            for r in of("mutation")]
    runs += [f"- великий блок `{r.get('block')}` закрито БЕЗ mutation testing: команду `MUTATION_CMD` не задано" for r in decisions
             if r.get("block_large") and r.get("point") == "b" and (r.get("checks") or {}).get("mutation", {}).get("when") != "now"]
    lines += ["", "### Mutation testing", "", *(runs or ["- Немає."])]
    return lines


# ------------------------------------------------------------------ anomalies


def anomalies_section(src: Source, period: Since, now: datetime) -> list[str]:
    """The overdue debts of urgent fixes, whatever the period (board 075); then the entries of the journal."""
    return [*overdue_lines(src, now), *journal_lines(src, period)]


def journal_lines(src: Source, period: Since) -> list[str]:
    """The entries of tasks/ANOMALIES.md written in the period, oldest first. The journal only
    grows at its end, so after a commit the new entries are those past the ones it already had;
    after a date they are told by their own time."""
    entries = [(match, body) for heading, body in sections(whole(src, "anomalies")) if (match := ANOMALY.match(heading))]
    if not entries:
        return ["Журнал аномалій (`tasks/ANOMALIES.md`) порожній: runner не зустрів нічого дивного."]
    if period.commit:   # what the journal did not hold at that commit: every session's file counts (board 739)
        known = {(heading, body.strip()) for heading, body in sections(journal_at_commit(src.root, period.commit, "anomalies"))}
        fresh = [(match, body) for match, body in entries if (match.group(0), body.strip()) not in known]
    else:
        fresh = [(match, body) for match, body in entries
                 if period.utc is None or ((when := as_utc(match.group(1).replace("Z", "+00:00"))) is not None and when >= period.utc)]
    lines = [(f"Нових записів за період: {len(fresh)}; усього в журналі `tasks/ANOMALIES.md`: {len(entries)}. Це те, що runner, gates, hook чи агент вважали дивним, "
              "записали і пішли далі; задачі, які він сам переніс у `blocked/`, стоять також у «Чекає на власника»."), ""]
    for match, body in fresh:
        lines += [f"- **{stamp(as_utc(match.group(1).replace('Z', '+00:00')))} — `{match.group(2)}`**",
                  *(f"  {line}" for line in body.splitlines() if line.strip())]
    return lines


# ------------------------------------------------------------------ plan, candidates, health


def plan_section(src: Source) -> list[str]:
    first = src.show(f"tasks/{board.FIRST}").split()
    rank = board.first_rank(first)
    # The order the runner takes them in: a task with extra sessions after every ordinary one (board 110).
    todo = sorted(src.column("todo"), key=lambda p: (board.parse(src.show(p)).extra, rank(posixpath.basename(p))))
    if not todo:
        return ["У `todo/` порожньо."]
    place = {board.number_of(posixpath.basename(p)): c for c in ("todo", "doing", "blocked", board.PROPOSED) for p in src.column(c)}
    place.update({board.number_of(s): "done" for s in src.done()})
    lines = []
    first_free = not [p for p in src.column("doing") if not board.parse(src.show(p)).attended]   # the owner's session's task is not in the way
    for index, path in enumerate(todo, 1):
        text = src.show(path)
        task = board.parse(text)
        depends = task.depends
        unmet = [n for n in depends if place.get(n) != "done"]
        line = f"{index}. `{posixpath.basename(path)}` — {title_of(text, 'без назви')}"
        line += "; **першою — власник відповів**" if posixpath.basename(path) in first else ""
        line += f"; режим: {mode_of(text)}"
        line += "; **з додатковими сесіями** — після звичайних задач і в межах тижневої суми" if task.extra else ""
        if task.mode_error:
            line += "; **не береться** — рядок «Режим:» не називає режиму"
        elif task.attended:
            line += "; **лише з присутнім власником** — runner не бере"
            line += ("; чекає на: " + ", ".join(f"{n:03d} ({place.get(n) or 'такої задачі ніде немає'})" for n in unmet)) if unmet else ""
        elif unmet:
            line += "; **стоїть**, чекає на: " + ", ".join(f"{n:03d} ({place.get(n) or 'такої задачі ніде немає'})" for n in unmet)
        else:
            line += f"; залежності: {', '.join(f'{n:03d}' for n in depends) + ' — готові' if depends else 'немає'}"
            line += " — **наступна**" if first_free else ""
            first_free = False
        lines.append(line)
    return lines


def old_failures(src: Source) -> list[str]:
    """The snapshot "as it was" (.engine/baseline.json, board 071): every old test failure by name —
    a candidate for a task, whatever the period; the engine puts no task on the board itself."""
    try:
        data = json.loads(src.show(".engine/baseline.json") or "{}")
        tests = [str(name) for name in data.get("tests", [])]
        counts = [sum(n for rules in data.get(part, {}).values() for n in rules.values()) for part in ("lint", "types")]
    except (ValueError, AttributeError, TypeError):
        return ["### Старі падіння зі знімка «як було» (`.engine/baseline.json`)", "", "Знімок не читається: файл зіпсовано. Gates, поки так, вимагають чистоти.", ""]
    if not tests and not any(counts):
        return []
    lines = ["### Старі падіння зі знімка «як було» (`.engine/baseline.json`)", "",
             (f"Тестів, що падали ще на день знімка: {len(tests)}. Gates їх не блокують; кожен — кандидат у задачу, "
              "задачею стане, коли її поставите ви. Полагоджене зі знімка прибирає `baseline.py tighten`."), ""]
    lines += [f"- `{name}`" for name in tests]
    return [*lines, *([""] if tests else []), f"Старих зауважень лінтера у знімку: {counts[0]}; помилок типів: {counts[1]}.", ""]


def candidates_section(src: Source, stems: list[str], period: Since) -> list[str]:
    lines: list[str] = []
    for stem in stems:
        found = sections(src.show(f"tasks/done/{stem}/report.md"))
        parts = [part for prefixes in CANDIDATE_PARTS if (part := pick(found, prefixes))]
        if parts:
            lines += [f"### Зі звіту {stem}", ""]
            for part in parts:
                lines += quoted(*part)
    passes = []
    for heading, body in sections(src.show(".engine/simplifier/report.md")):
        moment = as_utc(heading.split(" ", 1)[0].replace("Z", "+00:00"))
        if period.utc and moment and moment < period.utc:
            continue
        findings = [line[2:] for line in body.splitlines() if line.startswith("- `F-")]
        passes += [f"**{heading}** — знахідок: {len(findings)}", ""]
        passes += [f"- {f if len(f) <= FINDING_MAX else f[:FINDING_MAX].rstrip() + '…'}" for f in findings] + [""]
    if passes:
        lines += ["### Знахідки simplifier-а для розбору (`.engine/simplifier/report.md`)", "", *passes]
    lines += old_failures(src)
    return lines or ["За цей період кандидатів немає: у нових звітах немає розділів «Відкладене» чи «Чого мені бракувало», знахідок simplifier-а немає."]


def context_lines(src: Source) -> tuple[int, int] | None:
    """Lines and files of the persistent context: CLAUDE.md and everything it imports."""
    if "CLAUDE.md" not in src.files:
        return None
    seen: dict[str, int] = {}

    def walk(path: str, hops: int) -> None:
        if path in seen or path not in src.files:
            return
        text = src.show(path)
        seen[path] = len(text.splitlines())
        if hops >= MAX_HOPS:
            return
        for token in IMPORT_RE.findall(SPAN_RE.sub("", FENCE_RE.sub("", text))):
            walk(posixpath.normpath(posixpath.join(posixpath.dirname(path), token.rstrip(".,;:)"))), hops + 1)

    walk("CLAUDE.md", 0)
    return sum(seen.values()), len(seen)


def period_costs(costs: dict[str, dict[str, Any]], period: Since) -> list[tuple[str, float]]:
    spent = []
    for name, entry in sorted(costs.items()):
        attempts = [a for a in entry.get("attempts") or [] if isinstance(a, dict)
                    and (period.utc is None or ((when := as_utc(str(a.get("utc", "")))) is not None and when >= period.utc))]
        if attempts:
            spent.append((name, board_state.cost_of(attempts)))
    return spent


def machine_record(state: Path, name: str) -> tuple[dict[str, Any], str]:
    """A record a tool left about its own run (board 035), and where it was run — the time, the
    commit and whether the tree was dirty — in words. The facts of «Здоров'я» come from these
    files, written by tests/run_all.sh and evals/run_hook_scenarios.py, not from anybody's prose."""
    record = load_json(state / "health" / name)
    if not record:
        return {}, ""
    when = as_utc(str(record.get("recorded_utc", "")).replace("Z", "+00:00"))
    commit = str(record.get("commit") or "")[:7]
    return record, (f"{stamp(when) if when else 'час не записано'}, commit `{commit or 'невідомий'}`"
                    + (" з незакоміченими змінами в робочому дереві" if record.get("dirty") else ""))


def test_run_lines(state: Path) -> list[str]:
    lines = []
    for name, title, command in (("tests-full.json", "Останній повний прогін тестів", "bash tests/run_all.sh"),
                                 ("tests-fast.json", "Останній швидкий прогін (набір gates)", "bash tests/run_all.sh --fast")):
        record, where = machine_record(state, name)
        if not record:
            if name == "tests-full.json":
                lines.append(f"- Повний прогін тестів: машинного запису (`.claude/state/health/{name}`) тут немає — його лишає "
                             f"`{command}` на машині, де його запущено.")
            continue
        red = [str(r) for r in record.get("red") or []]
        took = record.get("seconds")   # the run's own wall time (board 087); an older record has none
        lines.append(f"- {title}, за машинним записом ({where}): {record.get('green')} із {record.get('suites')} наборів зелені"
                     + (f"; тривав {int(took) // 60} хв {int(took) % 60} с" if isinstance(took, int | float) and not isinstance(took, bool) else "")
                     + (f"; червоні: {', '.join(f'`{r}`' for r in red[:10])}" if red else "") + ".")
    return lines


def golden_line(src: Source, state: Path) -> str:
    """The golden set: the runner's own record of its last whole run; where this machine has
    none, the newest results file in the repository, by the time written in the file itself."""
    record, where = machine_record(state, "golden.json")
    if record:
        compared = record.get("compare")
        differences = record.get("differences")
        return (f"- Golden set, за машинним записом ({where}): {record.get('green')} із {record.get('scenarios')} сценаріїв відповідають очікуванням"
                + (f"; порівняно з `{compared}` — відмінностей: {differences}" if compared and differences is not None else "") + ".")
    newest: tuple[str, str, list[Any]] | None = None
    for path in sorted(p for p in src.files if GOLDEN.match(p)):
        try:
            data = json.loads(src.show(path))
        except ValueError:
            continue
        results = data.get("results") if isinstance(data, dict) else None
        recorded = str(data.get("recorded_utc", "")) if isinstance(data, dict) else ""
        if isinstance(results, list) and (newest is None or recorded > newest[0]):
            newest = (recorded, path, results)
    if newest is None:
        return "- Golden set: ні машинного запису (`.claude/state/health/golden.json`), ні записаних результатів (`evals/baseline/*/results-*.json`) немає."
    met = sum(1 for r in newest[2] if isinstance(r, dict) and r.get("pass"))
    return (f"- Golden set: машинного запису прогону тут немає; найновіший файл результатів у репозиторії — `{newest[1]}` "
            f"({newest[0] or 'час не записано'}): {met} із {len(newest[2])} сценаріїв відповідають очікуванням.")


def health_section(src: Source, state: Path, costs: dict[str, dict[str, Any]], period: Since, now: datetime) -> list[str]:
    lines = [*test_run_lines(state), golden_line(src, state)]
    context = context_lines(src)
    if context:
        lines.append(f"- Постійний контекст (CLAUDE.md і все, що він імпортує): {context[0]} із {CONTEXT_BUDGET} рядків, файлів: {context[1]}.")
    if costs:
        spent = period_costs(costs, period)
        lines.append(f"- Витрати за період, за записами runner-а: ${sum(c for _, c in spent):.2f}"
                     + (" — " + ", ".join(f"{name} ${cost:.2f}" for name, cost in spent) if spent else "") + ".")
        lines.append("- Витрати за добу (UTC), за записами runner-а — темп; межі на добу немає:")   # board 106
        lines += [f"  - {line}" for line in board_state.daily(costs, now.astimezone(UTC).date())]
    else:
        lines.append("- Витрати за період: записів runner-а (`costs.json`) тут немає; суми по задачах — у розділах «Витрати» їхніх звітів.")
    return lines


# ------------------------------------------------------------------ the document


def review(root: Path, state: Path, remote: str, branch: str, given: str | None, offline: bool, now: datetime) -> str:
    src = source(root, remote, branch, offline)
    period = since(src, given)
    costs = task_costs(state)
    stems = new_done(src, period)
    head = src.log("-1", "--format=%cI%x09%s", src.sha).split("\t")
    lines = [f"# Огляд task board — {stamp(now)}", "",
             f"Джерело: гілка `{src.name}`, commit `{src.sha[:7]}`" + (f" від {stamp(as_utc(head[0]))} — {head[1]}" if len(head) == 2 else "") + ".",
             *([f"Увага: {src.note}."] if src.note else []),
             f"Період для «Зроблено», кандидатів і витрат: {period.shown}. Огляд нічого не змінює.", ""]
    for title, body in (("Стан зараз", now_section(src, state, now)),
                        ("Зроблено", done_section(src, stems, costs)),
                        ("Змінені документи й проєкти — переглянь", documents_section(src)),
                        ("Чекає на власника", waiting_section(src, state)),
                        ("Цілі та звірка з ними", goals_section(src)),
                        ("Тестування", testing_section(src, period)),
                        ("Аномалії", anomalies_section(src, period, now)),
                        ("План", plan_section(src)),
                        ("Кандидати в нові задачі", candidates_section(src, stems, period)),
                        ("Здоров'я", health_section(src, state, costs, period, now))):
        lines += [f"## {title}", "", *body, ""]
    lines += ["---", f"Наступний огляд — лише нове після цього: `python3 .claude/unattended/board.py review --since {src.sha[:12]}`"]
    return "\n".join(lines) + "\n"
