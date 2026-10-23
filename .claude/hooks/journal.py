#!/usr/bin/env python3
"""The journals every session only adds to, one file per session (board 739).

    python3 .claude/hooks/journal.py show <ledger|parked|anomalies|lessons>
    python3 .claude/hooks/journal.py add <ledger|parked|anomalies> < entry.md   # an agent's own entry
    python3 .claude/hooks/journal.py fold
    python3 .claude/hooks/journal.py contradictions

WHY. Four journals grow by entries: the overseer's ledger, the log of parked units, the task board's
anomaly journal and the lesson queue. When two sessions on two branches each added an entry to the same
file, merging the branches conflicted — and git's `merge=union` is no way out: it merges by lines, keeps a
line two entries share only once, so an entry silently loses its lines, and it gives back a lesson
candidate another branch had triaged (the probe of board 739). So a session never writes the shared file.
It adds its entries to a file of its own, `.engine/journal/<journal>/<session>.md`, which no other
session touches, and branches merge without a conflict.

READING. Every reader takes a journal whole: the shared file (the history before board 739 and what is
folded since) and every session's file, merged by the time each entry carries — `text()` gives it in the
shared file's own form, newest first for the ledger, oldest first for the others. An entry present twice
(folded already and still in its session's file) counts once. Without a session file the shared file is
returned exactly as it is.

FOLDING (`fold`). After branches are merged, the entries of every session's file are written into the
shared file, by time and without loss; a session file whose newest entry is older than KEEP_DAYS is then
removed — its session is long over and no branch will add to it again. No reader needs the fold: it makes
one file for a person to read. Run it where branches meet, not on two branches at once — the shared file
is the one thing a fold changes, and two folds are two edits of it.

THE LESSON QUEUE is a state, not only a log: a candidate leaves it when triaged. A session never removes
the candidate's line; it adds `- <date> | resolved:<where> | <note> #<id>` to its own file, and the queue
is the candidates without a resolution. A resolution line is never folded away, so a candidate line
still in an older session's file stays triaged. When two sessions triaged one candidate differently
(memory in one, discard in the other) the script does not choose: `contradictions()` names it, an agent
decides (lesson_queue.py puts it on the board), and the decision is one more line,
`resolved:settled-<where>`.

THE SESSION. CLAUDE_CODE_SESSION_ID (or CLAUDE_SESSION_ID) where Claude Code sets it; elsewhere — a
script the runner starts outside any session — one id per working tree, kept in
.claude/state/journal/session-id, behind the UTC date: a new file every day.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path


@dataclass(frozen=True)
class Journal:
    name: str
    shared: str              # the shared file, relative to the project root
    newest_first: bool
    lines: bool = False      # one line per entry (the lesson queue), else `## <UTC time> — …` blocks
    head: str = ""           # the shared file's heading when a fold has to create it
    placeholder: str = ""    # what a heading says while there is no entry; gone once there is one


JOURNALS = {j.name: j for j in (
    Journal("ledger", ".engine/overseer/ledger.md", True, head="# Overseer ledger — append-only\n\n---\n", placeholder="(no entries yet)"),
    Journal("parked", ".engine/overseer/parked.md", False, head="# Parked items\n"),
    Journal("anomalies", "tasks/ANOMALIES.md", False, head=(
        "# Журнал аномалій task board\n\nУсе дивне, що сталося під час роботи runner-а: воно записується сюди, а не зупиняє task board. "
        "Пишуть runner, gates, hook-и й агент — у кожному записі сказано, хто; найновіший запис унизу. "
        "Огляд (`board.py review`) показує нові записи окремим розділом. Кожна сесія пише у свій файл "
        "`.engine/journal/anomalies/<сесія>.md`; увесь журнал — `python3 .claude/hooks/journal.py show anomalies`.\n")),
    Journal("lessons", ".engine/lesson-queue.md", False, lines=True, head=(
        "# Lesson queue\n\n"
        "One line per candidate: `- <date UTC> | <source> | <slice> | <essence> #<id>`. Filled by hooks "
        "(gate, overseer, parked, escalation) and by the agent. Triaged with "
        "`python3 .claude/hooks/lesson_queue.py resolve <id> --to memory|rule|engine|discard`, which adds "
        "`- <date> | resolved:<where> | <note> #<id>`. Each session writes its own file, "
        "`.engine/journal/lessons/<session>.md`; `journal.py show lessons` reads the queue whole. Never loaded "
        "into the persistent context.\n\n")),
)}
PIECES_REL = Path(".engine/journal")
SESSION_REL = Path(".claude/state/journal/session-id")
KEEP_DAYS = 7
ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", re.MULTILINE)
LINE_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \| ")
RESOLVED_RE = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) \| resolved:(?P<to>[\w-]+) \| (?P<note>.*) #(?P<id>[0-9a-f]{8})$")
CANDIDATE_RE = re.compile(r"^- \d{4}-\d{2}-\d{2} \| \w+ \| .* #(?P<id>[0-9a-f]{8})$")
SETTLED = "settled-"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def session_id(root: Path) -> str:
    """This session's name for its own files."""
    given = os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or ""
    given = re.sub(r"[^A-Za-z0-9_.-]+", "-", given).strip("-.")[:80]
    if given:
        return given
    path = root / SESSION_REL
    tree = read(path).strip()
    if not re.fullmatch(r"[0-9a-f]{12}", tree):
        tree = secrets.token_hex(6)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tree + "\n", encoding="utf-8")
        except OSError:
            pass
    return f"{datetime.now(UTC):%Y-%m-%d}-{tree}"


def piece(root: Path, name: str) -> Path:
    return root / PIECES_REL / name / f"{session_id(root)}.md"


def pieces(root: Path, name: str) -> list[Path]:
    folder = root / PIECES_REL / name
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


def add(root: Path, name: str, entry: str) -> Path:
    """Add one entry to this session's file of the journal; the path written."""
    journal = JOURNALS[name]
    if not (LINE_RE if journal.lines else ENTRY_RE).match(entry.lstrip("\n")):
        raise ValueError(f"not an entry of the {name} journal: it starts with "
                         + ("`- <date> | `" if journal.lines else "`## <UTC time like 2026-10-10T06:30:00Z> — `"))
    path = piece(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = entry.strip("\n") + "\n"
    existing = read(path)
    if existing and not journal.lines:
        body = "\n" + body
    with path.open("a", encoding="utf-8") as handle:
        handle.write(body)
    return path


# ------------------------------------------------------------------ reading


def split(text: str, journal: Journal) -> tuple[str, list[str]]:
    """The heading of a journal file and its entries, in file order."""
    if journal.lines:
        head: list[str] = []
        entries: list[str] = []
        for line in text.splitlines():
            (entries if LINE_RE.match(line) else head).append(line)
        return ("\n".join(head) + "\n") if head else "", entries
    starts = [m.start() for m in ENTRY_RE.finditer(text)]
    if not starts:
        return text, []
    bounds = [*starts, len(text)]
    return text[:starts[0]], [text[a:b].strip("\n") for a, b in pairwise(bounds)]


def when(entry: str, journal: Journal) -> str:
    found = (LINE_RE if journal.lines else ENTRY_RE).match(entry)
    return found.group(1) if found else ""


def merged(journal: Journal, shared: str, more: Iterable[str]) -> tuple[str, list[str], bool]:
    """The heading and every entry once, ordered by time as the shared file orders them; and whether the
    session files added anything to the shared file."""
    head, entries = split(shared, journal)
    seen = {e.strip() for e in entries}
    added = False
    for text in more:
        stray, found = split(text, journal)
        stray = stray.strip("\n")
        if stray.strip() and stray not in shared and stray not in head:
            # Text past the entry format is kept, never dropped — in the heading, where it sticks to no entry
            # (after a fold it would otherwise join the entry above it, and that entry be read twice).
            head = head.rstrip("\n") + "\n\n" + stray + "\n"
            added = True
        for entry in found:
            if entry.strip() not in seen:
                seen.add(entry.strip())
                entries.append(entry)
                added = True
    entries.sort(key=lambda e: when(e, journal), reverse=journal.newest_first)   # stable: equal times keep their order
    return head, entries, added


def render(journal: Journal, head: str, entries: list[str]) -> str:
    if journal.lines:
        return head + "".join(e + "\n" for e in entries)
    if not entries:
        return head
    if journal.placeholder:
        head = "\n".join(line for line in head.split("\n") if line.strip() != journal.placeholder)
    return head.rstrip("\n") + "\n\n" + "\n".join(e.rstrip() + "\n" for e in entries)


def assemble(journal: Journal, shared: str, more: list[str]) -> str:
    """The whole journal from the shared file's text and the session files' texts. Without an entry
    beyond the shared file, the shared file exactly as it is. Pure: board_review.py reads through git."""
    head, entries, added = merged(journal, shared or journal.head, more)
    return render(journal, head, entries) if added else shared


def text(root: Path, name: str) -> str:
    """The journal whole: the shared file and every session's file."""
    journal = JOURNALS[name]
    return assemble(journal, read(root / journal.shared), [read(p) for p in pieces(root, name)])


# ------------------------------------------------------------------ the lesson queue


def resolutions(lines: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = {}
    for line in lines:
        match = RESOLVED_RE.match(line)
        if match:
            found.setdefault(match["id"], []).append(match.groupdict())
    return found


def open_candidates(lines: Iterable[str]) -> list[str]:
    """The candidate lines no resolution closes, in order — one per id: a candidate two sessions queued
    (the same source and essence on two branches, so two lines a date apart) is one candidate, the first met."""
    lines = list(lines)
    closed = resolutions(lines)
    first: dict[str, str] = {}
    for line in lines:
        match = CANDIDATE_RE.match(line)
        if match and not RESOLVED_RE.match(line) and match["id"] not in closed:
            first.setdefault(match["id"], line)
    return list(first.values())


def contradictions(lines: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    """Candidates two sessions triaged differently and nobody has settled: id → its resolutions."""
    return {ident: rows for ident, rows in resolutions(lines).items()
            if len({r["to"] for r in rows}) > 1 and not any(r["to"].startswith(SETTLED) for r in rows)}


def lesson_lines(root: Path) -> list[str]:
    return split(text(root, "lessons"), JOURNALS["lessons"])[1]


# ------------------------------------------------------------------ folding


def newest(path: Path, journal: Journal) -> datetime | None:
    stamps = [when(e, journal) for e in split(read(path), journal)[1]]
    stamps = [s for s in stamps if s]
    if not stamps:
        return None
    value = max(stamps)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ" if "T" in value else "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def fold(root: Path, now: datetime | None = None) -> list[str]:
    """Every session's entries into the shared files; the session files older than KEEP_DAYS removed.
    In the lesson queue a triaged candidate's line goes, its resolution line stays."""
    now = now or datetime.now(UTC)
    done: list[str] = []
    for journal in JOURNALS.values():
        files = pieces(root, journal.name)
        if not files:
            continue
        shared = root / journal.shared
        head, entries, _ = merged(journal, read(shared) or journal.head, [read(p) for p in files])
        if journal.lines:   # a triaged candidate goes, unless its triage is contradicted; every resolution stays
            keep, disputed = set(open_candidates(entries)), contradictions(entries)
            entries = [e for e in entries if not (m := CANDIDATE_RE.match(e)) or e in keep or m["id"] in disputed]
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(render(journal, head, entries), encoding="utf-8")
        gone = [p for p in files if (stamp := newest(p, journal)) is None or now - stamp > timedelta(days=KEEP_DAYS)]
        for path in gone:
            path.unlink()
        done.append(f"{journal.shared}: {len(files)} session file(s) folded, {len(gone)} removed")
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 2)[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="print one journal whole")
    show.add_argument("name", choices=sorted(JOURNALS))
    adding = commands.add_parser("add", help="add one `## <UTC time> — …` entry, read from stdin, to this session's file")
    adding.add_argument("name", choices=sorted(n for n, j in JOURNALS.items() if not j.lines))
    commands.add_parser("fold", help="write every session's entries into the shared files")
    commands.add_parser("contradictions", help="the lesson candidates two sessions triaged differently")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "show":
        sys.stdout.write(text(root, args.name))
    elif args.command == "add":
        entry = sys.stdin.read().strip("\n")
        if not ENTRY_RE.match(entry):
            print("journal: an entry starts with `## <UTC time like 2026-10-10T06:30:00Z> — `", file=sys.stderr)
            return 2
        print(add(root, args.name, entry + "\n").relative_to(root).as_posix())
    elif args.command == "fold":
        print("\n".join(fold(root)) or "nothing to fold: no session files")
    else:
        found = contradictions(lesson_lines(root))
        for ident, rows in found.items():
            print(f"#{ident}: " + "; ".join(f"{r['date']} {r['to']} ({r['note']})" for r in rows))
        return 1 if found else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
