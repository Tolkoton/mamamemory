#!/usr/bin/env python3
"""The urgent fix and its debt — the script behind /hotfix (board 075).

    python3 .claude/hooks/hotfix.py start --name <kebab-name> (--task <board task> | --declared "<the owner's words>")
                                          [--owner-answer "<the owner's answer to the three-debts question>"]
    python3 .claude/hooks/hotfix.py debt  --record .engine/bugs/<number-name>.md [--commit <sha>]
    python3 .claude/hooks/hotfix.py close --record .engine/bugs/<number-name>.md --bugfix .engine/bugs/<the full fix>.md
    python3 .claude/hooks/hotfix.py list

WHY THIS EXISTS. Urgency lifts the ceremony, not the checks (the approved design of board 070,
section 4). An urgent fix may put off the test before the code, the record of the cause and the
search for the same places — and what is put off must not live in an agent's memory. So a script
writes both traces: a line in `.engine/debt.md` with a term of seven days, and a follow-up task
on the board — a full /bugfix of the same place. And "urgent" must not become the ordinary way
to work: the size of the fix is a hard limit (complexity_budget.py, the hard mode), and with
three debts open the next urgent fix starts with a question for the owner.

`start`  refuses unless the OWNER declared the work urgent: a board task that says so (`/hotfix`,
         «термінове», "urgent"), or the owner's words in an attended session. Unattended, only
         the task counts. With three debts open it writes no card: exit 3 and the question; the
         answer must then be given back with --owner-answer, and with --task it must stand in
         the task file. Otherwise it writes the card `.engine/bugs/<number-name>.md` from
         .claude/templates/hotfix-record.md (type hotfix, hard mode, the base commit) and marks
         it IN PROGRESS in `.engine/PROGRESS.md`, so that the limit is measured from the first change.
`debt`   refuses a fix over the hard limit, a card with no fix, and a card that does not say how
         to roll the fix back. Otherwise: the debt line, the follow-up task (when the project
         has a board), the card's status. A second run for the same card adds nothing.
`close`  closes the debt when the full fix exists: a bug record of type bugfix with status fixed.
`list`   the debts, open and overdue first. The owner's review reads the same file (board_review.py).

Exit: 0 done; 1 REFUSED (the work is not in a state to record); 2 REFUSED (the call itself is
wrong: who declares, the name, the files); 3 a question for the owner. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import complexity_budget as budget  # the measurement and the project root live there
import mode as mode_reader  # the task's mode and «nobody is watching» (board 097)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unattended"))
import task_classes  # a task's number: its class x 100 + its place in the class (board 401)

TERM_DAYS = 7
MAX_OPEN = 3
DEBT_REL = ".engine/debt.md"
BUGS_REL = ".engine/bugs"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "hotfix-record.md"
DEFERRED = "the test before the code; the record of the cause; the search for the same places"
DECLARED_RE = re.compile(r"hotfix|термінов|urgent", re.IGNORECASE)
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ANSWER_RE = re.compile(r"^[\s>*_-]*Відповідь:[*_\s]*(.*)$", re.MULTILINE)
DEBT_RE = re.compile(
    r"^- (?P<name>[\w.-]+) \| (?P<status>open|closed (?P<closed>\d{4}-\d\d-\d\d)[^|]*) \| recorded (?P<recorded>\d{4}-\d\d-\d\d)"
    r" \| due (?P<due>\d{4}-\d\d-\d\d) \| commit (?P<commit>[^|]+) \| deferred: (?P<deferred>[^|]+) \| follow-up: (?P<followup>.+)$",
    re.MULTILINE)
HEADER = """# Debts of urgent fixes

Written by `python3 .claude/hooks/hotfix.py debt` and closed by `… close`; not edited by hand.
One line per urgent fix (/hotfix): what was put off, the commit, the date, the term — seven days.
The owner's review shows the open ones and, among the anomalies, the overdue ones. With three
open, the next urgent fix starts with a question for the owner.

"""


@dataclass(frozen=True)
class Debt:
    name: str
    open: bool
    recorded: str
    due: str
    commit: str
    followup: str
    line: str

    def days_late(self, today: date) -> int:
        return (today - date.fromisoformat(self.due)).days if self.open else 0

    def overdue(self, today: date) -> bool:
        return self.days_late(today) > 0


def debts(text: str) -> list[Debt]:
    """The lines of .engine/debt.md, in the order written."""
    return [Debt(m["name"], m["status"] == "open", m["recorded"], m["due"], m["commit"].strip(), m["followup"].strip(), m.group(0))
            for m in DEBT_RE.finditer(text)]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def today() -> date:
    return datetime.now(UTC).date()


def unattended(root: Path) -> bool:
    """Nobody is watching: the runner's environment says so, or the mode file does (mode.py reads both)."""
    return mode_reader.unattended(root)[0]


def refuse(code: int, why: str) -> int:
    print(f"REFUSED: {why}")
    return code


def field_of(card: str, label: str) -> str:
    """What a card's `- Label: …` line says; '' while it still holds the template's placeholder."""
    found = re.search(rf"^- {re.escape(label)}:[ \t]*(.*)$", card, re.MULTILINE)
    value = found.group(1).strip() if found else ""
    return "" if value.startswith("<") else value


# ------------------------------------------------------------------ start


def question(open_debts: list[Debt]) -> str:
    listed = "\n".join(f"   - `{d.name}` — записано {d.recorded}, строк до {d.due}, продовження: `{d.followup}`" for d in open_debts)
    return (f"QUESTION FOR THE OWNER — {len(open_debts)} debts of urgent fixes are open; no card was written.\n"
            "Attended: ask it now. Unattended: write it into the task under «Питання до власника» and move the task to tasks/blocked/.\n"
            "Then run `start` again with --owner-answer \"<the owner's answer, word for word>\".\n\n"
            f"1. Відкрито {len(open_debts)} борги термінових виправлень (межа — {MAX_OPEN}):\n{listed}\n"
            "   Починати ще одне термінове виправлення, не закривши жодного з них, — чи спершу закрити борг\n"
            "   (повний `/bugfix` із задачі-продовження)? Раджу спершу закрити борг: інакше «терміново» стає звичайним способом працювати.\n"
            "   Відповідь:")


def declaration(root: Path, args: argparse.Namespace) -> tuple[str, str] | str:
    """(the owner's words, the task's text) — or the reason the work is not the owner's urgent one."""
    if bool(args.task) == bool(args.declared):
        return "name exactly one of --task <board task> and --declared \"<the owner's words>\": only the owner declares work urgent"
    if args.task:
        text = read(root / args.task)
        if not text:
            return f"{args.task} is not a file of this project"
        said = next((line.strip() for line in text.splitlines() if DECLARED_RE.search(line)), "")
        if not said:
            return (f"{args.task} does not call the work urgent (no `/hotfix`, «термінове» or \"urgent\" in it). Only the owner declares an "
                    "urgent fix; the agent never names work urgent itself. Do it as /bugfix, or ask the owner")
        return f"{said} ({args.task})", text
    if unattended(root):
        return "this session is unattended: nobody is in it to declare the work urgent — only a line in the board task counts (--task)"
    if len(args.declared.split()) < 2:
        return "--declared takes the owner's own words, as they were said"
    return f"{args.declared.strip()} (said in the session)", ""


def cmd_start(root: Path, args: argparse.Namespace) -> int:
    if not NAME_RE.fullmatch(args.name):
        return refuse(2, f"the name '{args.name}' is not kebab-case (lowercase words joined by hyphens)")
    declared = declaration(root, args)
    if isinstance(declared, str):
        return refuse(2, declared)
    words, task_text = declared
    forbidden = mode_reader.refusal(root, "hotfix", root / args.task if args.task else None)
    if forbidden:
        return refuse(2, forbidden)
    open_debts = [d for d in debts(read(root / DEBT_REL)) if d.open]
    answer = (args.owner_answer or "").strip()
    if len(open_debts) >= MAX_OPEN:
        if not answer:
            print(question(open_debts))
            return 3
        if args.task and answer not in [found.strip() for found in ANSWER_RE.findall(task_text)]:
            return refuse(2, f"{args.task} carries no «Відповідь:» line with exactly this answer. The answer to the three-debts question "
                             "is the owner's line in the task, not the agent's")
    base = budget.git(root, "rev-parse", "HEAD").strip()
    if not base:
        return refuse(2, "no commit to measure the fix from: the hard limit is counted from HEAD")
    template = read(TEMPLATE)
    if not template:
        return refuse(2, f"the card template {TEMPLATE} is missing")
    folder = root / BUGS_REL
    folder.mkdir(parents=True, exist_ok=True)
    taken = {int(m.group(1)) for p in folder.glob("*.md") if (m := re.match(r"(\d{3})-", p.name))}
    stem = f"{next(n for n in range(1, len(taken) + 2) if n not in taken):03d}-{args.name}"
    card = template
    for mark, value in (("<number-name>", stem), ("<the owner's words, as they are, and where they stand>", words), ("<date>", today().isoformat()),
                        ("<how many>", str(len(open_debts))), ("<base_commit>", base),
                        ("<the answer, word for word — only when three debts were open>", answer or "not asked: fewer than three debts were open")):
        card = card.replace(mark, value)
    (folder / f"{stem}.md").write_text(card, encoding="utf-8")
    progress = root / ".engine/PROGRESS.md"
    with open(progress, "a", encoding="utf-8") as handle:
        handle.write(("\n" if read(progress).strip() else "") + f"## Hotfix {stem} — IN PROGRESS\n- Record: `{BUGS_REL}/{stem}.md`\n")
    print(f"STARTED: {BUGS_REL}/{stem}.md — an urgent fix, measured from {base[:10]}")
    print("  hard limit: " + ", ".join(f"{key} {value}" for key, value in budget.HARD_LIMITS.items()) + "; no code deleted outside the functions being fixed")
    print(f"  open debts: {len(open_debts)} of {MAX_OPEN}")
    active = budget.active_contract(root)
    if active is None or active.name != f"{stem}.md":
        print(f"  WARNING: .engine/PROGRESS.md marks another unit IN PROGRESS first ({active.name if active else 'unreadable'}): "
              "the limit of this card is not measured at turn end until that block is closed")
    return 0


# ------------------------------------------------------------------ debt


def next_number(tasks: Path) -> int:
    """The follow-up's number: the next one of the class of tasks nobody gave a class (board 401)."""
    taken = {int(m.group(1)) for p in tasks.glob("*/*") if (m := re.match(r"(\d{3,})-", p.name))}
    return task_classes.next_number(taken, task_classes.UNCLASSED)


def followup_text(number: int, stem: str, commit: str, base: str, recorded: str, due: str) -> str:
    return f"""# {number:03d} — Продовження термінового виправлення {stem}: повний /bugfix

Залежить від: —
Потрібна присутність власника: ні
Аудит потрібен: ні

## Що зробити
Термінове виправлення `{stem}` (картка `{BUGS_REL}/{stem}.md`, commit `{commit}`, {recorded}) лишило борг:
тест перед кодом, запис причини й пошук таких самих місць відкладено. Строк боргу — **{due}** (сім днів).
- Пройти повний `/bugfix` для того самого місця, з власним записом помилки: відтворення; тест, що падає без
  виправлення (доказ — `bugfix.py prove --base {base[:12]}`: код до термінового виправлення мусить упасти);
  причина; пошук таких самих місць.
- Якщо повне виправлення показало, що термінове було хибним, — так і записати і виправити як слід.
- Наприкінці закрити борг:
  `python3 .claude/hooks/hotfix.py close --record {BUGS_REL}/{stem}.md --bugfix {BUGS_REL}/<новий запис>.md`

## Готово, коли
- Запис помилки `/bugfix` має стан `fixed`, у ньому доказ `PROVED`.
- У `{DEBT_REL}` рядок `{stem}` закрито.

## Питання до власника
"""


def cmd_debt(root: Path, args: argparse.Namespace) -> int:
    card_path = root / args.record
    card = read(card_path)
    stem = card_path.stem
    if not budget.HARD_TYPE_RE.search(card):
        return refuse(2, f"{args.record} is not the card of an urgent fix (no `type: hotfix`): only /hotfix leaves this debt")
    known = {d.name: d for d in debts(read(root / DEBT_REL))}
    if stem in known:
        print(f"ALREADY RECORDED: {known[stem].line}")
        return 0
    try:
        outcome = budget.evaluate(root, card_path)
    except budget.BudgetError as broken:
        return refuse(1, f"the card's budget section cannot be read: {broken}")
    if outcome is None or not outcome.base_commit:
        return refuse(1, outcome.text if outcome else "the card has no `## Complexity budget` section: the hard limit cannot be measured")
    if outcome.exceeded:
        return refuse(1, "the fix is over the hard limit; no debt is written for it.\n" + outcome.text)
    if not outcome.changed_files:
        return refuse(1, f"there is no fix: nothing but tests and records differs from {outcome.base_commit[:10]}. A debt is owed for a fix that exists")
    if not field_of(card, "Symptom"):
        return refuse(1, "the card does not say what is broken (`- Symptom:`): a reproduction, or the owner's words recorded as they are")
    if not field_of(card, "Roll back"):
        return refuse(1, "the card does not say how to roll back exactly this fix (`- Roll back:` — one command or one commit)")
    head = budget.git(root, "rev-parse", "HEAD").strip()
    if args.commit:
        commit = budget.git(root, "rev-parse", "--verify", "--quiet", f"{args.commit}^{{commit}}").strip()[:7]
        if not commit:
            return refuse(2, f"--commit {args.commit} is not a commit of this repository")
    else:
        commit = head[:7] if head != budget.git(root, "rev-parse", outcome.base_commit).strip() else f"not committed yet (on {head[:7]})"
    recorded, due = today(), today() + timedelta(days=TERM_DAYS)
    tasks = root / "tasks"
    followup = "none — the project has no task board; the full /bugfix is owed all the same"
    if (tasks / "todo").is_dir():
        number = next_number(tasks)
        # A proposal, not a task of todo/: new work is put to work by the owner alone (board 111).
        followup = f"tasks/proposed/{number:03d}-hotfix-followup-{stem}.md"
        (root / followup).parent.mkdir(parents=True, exist_ok=True)
        (root / followup).write_text(followup_text(number, stem, commit, outcome.base_commit, recorded.isoformat(), due.isoformat()), encoding="utf-8")
    line = f"- {stem} | open | recorded {recorded.isoformat()} | due {due.isoformat()} | commit {commit} | deferred: {DEFERRED} | follow-up: {followup}"
    path = root / DEBT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((read(path) or HEADER).rstrip("\n") + "\n" + line + "\n", encoding="utf-8")
    card = re.sub(r"^status:.*$", f"status: fixed, debt open — due {due.isoformat()}", card, count=1, flags=re.MULTILINE)
    card = re.sub(r"^- Debt line:.*$", lambda _: f"- Debt line: `{line}`", card, count=1, flags=re.MULTILINE)
    card = re.sub(r"^- Follow-up:.*$", lambda _: f"- Follow-up: {followup}", card, count=1, flags=re.MULTILINE)
    card_path.write_text(card, encoding="utf-8")
    print(f"DEBT RECORDED: {line}")
    print(f"  {DEBT_REL} and {followup} are part of this fix: stage them with it")
    return 0


# ------------------------------------------------------------------ close, list


def cmd_close(root: Path, args: argparse.Namespace) -> int:
    stem = Path(args.record).stem
    path = root / DEBT_REL
    text = read(path)
    debt = next((d for d in debts(text) if d.name == stem), None)
    if debt is None:
        return refuse(2, f"{DEBT_REL} has no debt named {stem}")
    if not debt.open:
        print(f"ALREADY CLOSED: {debt.line}")
        return 0
    full = read(root / args.bugfix)
    if Path(args.bugfix).stem == stem or not re.search(r"^type:[ \t]*bugfix[ \t]*$", full, re.MULTILINE):
        return refuse(1, f"{args.bugfix} is not the record of a full fix (`type: bugfix`, written by /bugfix): the urgent card cannot close its own debt")
    if not re.search(r"^status:[ \t]*fixed\b", full, re.MULTILINE):
        return refuse(1, f"{args.bugfix} does not have `status: fixed`: the debt is closed by a finished /bugfix, not by a started one")
    closed = debt.line.replace(" | open | ", f" | closed {today().isoformat()} by {args.bugfix} | ", 1)
    path.write_text(text.replace(debt.line, closed, 1), encoding="utf-8")
    card_path = root / args.record
    if card_path.is_file():
        card_path.write_text(re.sub(r"^status:.*$", f"status: debt closed {today().isoformat()} by {args.bugfix}", read(card_path), count=1, flags=re.MULTILINE),
                             encoding="utf-8")
    print(f"DEBT CLOSED: {closed}")
    return 0


def cmd_list(root: Path) -> int:
    found = debts(read(root / DEBT_REL))
    open_debts = [d for d in found if d.open]
    late = [d for d in open_debts if d.overdue(today())]
    print(f"open: {len(open_debts)} of {MAX_OPEN}; overdue: {len(late)}; closed: {len(found) - len(open_debts)}")
    for debt in open_debts:
        print(f"  {'OVERDUE ' if debt in late else ''}{debt.name} — due {debt.due}, commit {debt.commit}, follow-up: {debt.followup}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--name", required=True)
    start.add_argument("--task")
    start.add_argument("--declared")
    start.add_argument("--owner-answer")
    debt = commands.add_parser("debt")
    debt.add_argument("--record", required=True)
    debt.add_argument("--commit")
    close = commands.add_parser("close")
    close.add_argument("--record", required=True)
    close.add_argument("--bugfix", required=True)
    commands.add_parser("list")
    args = parser.parse_args()
    root = budget.project_root()
    if args.command == "start":
        return cmd_start(root, args)
    if args.command == "debt":
        return cmd_debt(root, args)
    if args.command == "close":
        return cmd_close(root, args)
    return cmd_list(root)


if __name__ == "__main__":
    sys.exit(main())
