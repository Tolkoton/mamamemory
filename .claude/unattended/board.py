#!/usr/bin/env python3
"""The task board in files: the one reader of tasks/ (package board).

The board is four directories under tasks/ — todo/, doing/, blocked/, done/. A task is one
file `NNN-name.md`; the number is its place in the queue, and its class x 100 + its place in
the class (task_classes.py, board 401: a new number is the next one of its class). Under the title it carries plain
lines — `Залежить від:` (task numbers), `Аудит потрібен: так|ні`, when the task may be worked
on only with the owner present, `Потрібна присутність власника: так`, and its mode, `Режим:` (read by
.claude/hooks/mode.py, see A MODE) — and its last section,
`## Питання до власника`, holds questions, each with an `Відповідь:` line. A finished task is
a directory done/NNN-name/ with task.md and report.md. tasks/README.md is the manual.

This module parses a task and makes every move that needs a decision, so that "which task is
next", "is it answered" and "does it ask for the paid audit" are decided in one place for the
runner (board-runner.sh), for the audit runner (evals/run_audit_scenarios.py) and for a person.
It never runs git: staging and committing belong to the runner and to the agent. The one
exception reads only: `review` takes the board from the work branch in origin (board_review.py).

    board.py next [--attended]       the task to work on: the one in doing/, else the first in
                                     todo/ whose dependencies are all in done/ — a task the owner
                                     answered before any other (THE OWNER'S ANSWERS FIRST), a task
                                     with extra sessions after every ordinary one.
                                     exit 3: todo/ is empty; exit 4: tasks wait, none is eligible;
                                     exit 5: only tasks with extra sessions could start, and the
                                     weekly sum is at its cap (A TASK WITH EXTRA SESSIONS)
    board.py start [--attended] <todo file>   move it to doing/ (refused while doing/ holds a task
                                     of the same side: see AN ATTENDED TASK)
    board.py where <NNN-name>        todo | doing | blocked | proposed | done | missing
    board.py import-inbox <dir>      take new task files in (see `import_inbox`); a file with the number
                                     of a proposal puts it to work (A PROPOSAL)
    board.py unblock                 blocked/ tasks whose every answer is filled go back to todo/
    board.py reviewed-reject --accepted <file> [--known <rev>]
                                     the runner's call before a pull and before a push: numbers in
                                     tasks/.reviewed that did not arrive from the owner are removed
                                     and printed (see WHAT THE OWNER LOOKED OVER)
    board.py reviewed-accept --accepted <file>   after the pull and the inbox: what is there is the owner's
    board.py reviewed-clean --accepted <file> [--known <rev>]
                                     exit 0 only when tasks/.reviewed as HEAD has it is a plain file
                                     that holds arrived numbers alone: the runner pushes on nothing else
    board.py audit-allowed           exit 0 only when this session's task in doing/ asks for the audit
    board.py extra-allowed           exit 0: one more extra session of Claude may start; exit 1: the
                                     weekly sum is at its cap. Prints the sum either way
    board.py extra-book <tool> <usd> book a session this session's task started without a tool that
                                     books it itself (a sandbox runner, `claude -p` by hand)
    board.py extra-wait              the weekly sum is at its cap: this session's task goes from
                                     doing/ back to todo/, marked, to wait there; exit 2 under the cap
    board.py extra-waits <NNN-name>  exit 0: that task lies in todo/, marked, and the sum is at its
                                     cap — it waits, the runner does not park it; exit 1 otherwise
    board.py gate-answers            the gate's questions in blocked/ that the owner answered
                                     «так»: one `name<TAB>stamp<TAB>sha256` line each
    board.py gate-done <name> <closed|absent|elsewhere>   such a task goes to done/ with its report
    board.py gate-closed             the gate's questions in blocked/ that nobody answered and whose
                                     escalation is closed already: one `name<TAB>stamp` line each
    board.py gate-reject <name>      its answer is wiped and the question asked again
    board.py gate-hold               the stamp of an open gate escalation that covers all work (see
                                     A GATE ESCALATION HOLDS A TASK); prints nothing when there is none
    board.py owner-actions           blocked/ tasks that carry an allowed action the owner answered
                                     «так» (a rule proposal: also «ні»): one
                                     `name<TAB>action<TAB>argument<TAB>sha256` line each
    board.py action-line <action>    the line an agent writes under its question to offer the action
    board.py maintain-task [--today YYYY-MM-DD]
                                     the runner's weekly call: put the maintenance task into todo/
                                     when it is due (see THE MAINTENANCE TASK); prints its path
    board.py architect-task          the runner's call after `seal-goals` applied: put the architecture
                                     task into todo/ in a new project (see THE ARCHITECTURE TASK); prints its path
    board.py cleanup-task [--today YYYY-MM-DD]
                                     the runner's call when nothing can be taken: put the cleanup
                                     task into todo/ when it is due (see THE CLEANUP TASK); prints its path
    board.py action-done <name> <applied|failed|stale>   the offer is replaced by what happened
    board.py action-reject <name>    its answer is wiped and the question asked again
    board.py park <NNN-name> <reason> [--detail N] [--stash SHA] [--wip BRANCH [--wip-remote NAME]]
                 [--verdicts FILE]   the runner gives up on a task, not on the board (see below)
    board.py open-item --to <blocked|proposed|todo|done> --title T --what W [--question Q] [--do D]
                 [--key K] [--source WHO]
                                     something open becomes a task of the board (see AN OPEN ITEM);
                                     `todo` is the old name of `proposed` and lands there (A PROPOSAL);
                                     prints its path; exit 1: no board, or nothing to ask
    board.py anomaly <task|-> <what happened> <what was done> [--source WHO]
                                     one entry in tasks/ANOMALIES.md; WHO wrote it: runner
                                     (the default), агент, gates, hook <name>
    board.py summary                 the board in a dozen lines, for the owner
    board.py check                   two files with one number in a column, or one number in proposed/
                                     and in todo/: the errors, exit 1 (board 065, board 111)
    board.py review [--since <commit|date>] [--offline]
                                     the owner's review: one markdown document about the work
                                     branch in origin; changes nothing (board_review.py)

A GATE QUESTION (board 005) is a task the Stop gate writes itself when it gives up after N
blocks in a row (`gate_question`, called by .claude/hooks/gate.py): tasks/blocked/NNN-gate-
escalation-<stamp>.md (a number of class 9), with the line `Ескалація gates: <stamp>` under its title and the question
«Закрити ескалацію?». The owner's answer «так» is acted on by board-runner.sh, which runs
`gate.py --close-escalation` — never by an agent, so `unblock` leaves such a task where it is.
Any other answer is an instruction: the task goes back to todo/ like every answered task.

CONSENT HAS ONE FORM (board 036), the same for closing an escalation, applying the settings
proposal and making a lesson a rule: the answer is exactly the one word «так» — case and
punctuation do not count (`is_word`). Everything else, «так, але…» included, is an instruction
for the agent and nothing is applied.

AN OWNER ACTION (board 008) is something only the owner may decide and no agent may do: applying
the settings proposal, (board 051) amending the approved goals document from
`.engine/goals/proposed.md` (`amend-goals`), and (board 787) the first seal on a goals document
written with nobody in the conversation (`seal-goals`, the sha256 of `.engine/goals.md` itself). The agent asks its question and writes under it the
line `Дія runner-а: apply-settings <sha256 of the proposal>` (`action-line` prints it). The
owner's answer «так» is acted on by board-runner.sh through owner_action.py, never by an agent;
`unblock` leaves such a task where it is until the runner has replaced the offer with the
outcome, and then the task returns to todo/ for the agent to check and report. The list of what
the runner may do on the owner's word is OWNER_ACTIONS and nothing outside it is ever run from a
task file. Any other answer is an instruction for the agent, as everywhere.

A RULE QUESTION (board 040) is how a lesson becomes a rule: never by itself, only on the owner's
word. `rule_question` (called by .claude/hooks/lesson_queue.py when a lesson is filed as a rule
proposal) writes tasks/blocked/NNN-rule-proposal-<id>.md (a number of class 8): the exact text of the rule, the
overseer's recommendation when there is one, the question «Зробити це правилом?» and the offer
`Дія runner-а: promote-rule <sha256 of the id and the text>`. «так» is the runner's to act on
(owner_action.py promote-rule → lesson_queue.promote), «ні» too (reject-rule: the proposal is
closed); either way the runner moves the task to done/ with a short report and no agent is
started. Any other answer is an instruction for the agent.

UPDATING DEPENDENCIES (board 076) is such an action too: `update-deps`, offered under the question
that ends a `/maintain` task, with the sha256 of the list `.engine/maintain/updates.json` the owner
saw. On «так» the runner runs owner_action.py, which updates patches and minor versions only, one
at a time, each checked by the full gate and committed on its own or rolled back.

THE MAINTENANCE TASK (board 076). Once a week the runner puts `NNN-maintain-<date>.md` into todo/
itself (`maintain-task`): a task that says to run `/maintain`. Not when one is already in todo/,
doing/ or blocked/; not sooner than MAINTAIN_EVERY_DAYS (`.claude/project.env`; empty — 7, `0` —
never) after the newest one, wherever it lies; and not in a project without the command
`.claude/commands/maintain.md`.

THE CLEANUP TASK (board 045). The runner's free time goes against complexity: when nothing can be
taken — todo/ is empty, or all that is left waits for the owner or the owner's presence — the
runner puts `NNN-cleanup-<date>.md` into todo/ itself (`cleanup-task`): a task that runs the
simplifier's nightly mode and acts by its rules. Not while a task is in doing/ or one can start;
not while a cleanup task waits in todo/, doing/ or blocked/; not sooner than CLEANUP_EVERY_DAYS
(`.claude/project.env`; empty — 1, `0` — never) after the newest one, wherever it lies; and not in
a project without `.claude/hooks/simplifier.py`. One already in todo/ waits the same way while the
owner's attended task is in doing/ (board 838): `next` does not offer it and `start` refuses it —
two authors in the same files would conflict at the merge.

THE ARCHITECTURE TASK (board 205). Sealed goals in a new project hand off to the architect without a
command from the owner. When the runner has put the first seal on the owner's «так» (`seal-goals`)
it asks `architect-task`, which puts `NNN-master-architect.md` into todo/: a task to run
`/master-architect`, with `Потрібна присутність власника: так` — the architect stops for the owner
at «Читання цілей», before anything is designed, so a session without the owner would only park;
the runner never takes it, the owner's review shows it as waiting for them. Not when the goals are
not sealed, not when the architecture has begun (the traceability matrix or a map exists — then an
amendment's `.engine/goals/to-review.md` is the architects' work, not a new start), not when one
already lies in any column. The engine schedules nothing else.

A GATE ESCALATION HOLDS A TASK (board 301). While the Stop gate's escalation is open the overseer's
PASS is not accepted for the work it covers (.claude/hooks/gate_allows.py, `escalation_over`), so a
session spent on such a task ends in a BLOCK whatever it does: on 2026-10-12 the runner took eleven
tasks one after another, and each came back with the same question. A task in todo/ whose verdict the
escalation would refuse is therefore not offered by `next` and not moved by `start`, and `summary`
says what it waits for: the task whose turn the gate gave up on (`work` in the escalation), a task
whose own earlier commits changed a file the escalation names, and — when the escalation names no
file and so covers all work — every task; then no cleanup task is placed either, and the runner
stops with `waiting-owner`. Only what can be told before the start is held: a task that will change
an escalated file for the first time is found by the overseer, not here. `--attended` is not held —
the owner is there to close the escalation. Without gate_allows.py beside the board nothing is held.

AN ATTENDED TASK (board 016) says `Потрібна присутність власника: так` under its title: work no
agent may do alone — above all a change to its own guards, which the permission classifier
rightly refuses without a person. `next` never offers one and `start` never moves one; the
runner therefore never takes it, and a task that depends on it waits. With `--attended` both do
— `next --attended` offers attended tasks only — and `--attended` is refused in an unattended
session (CLAUDE_UNATTENDED_SESSION=1, or `.claude/state/overseer/mode` says `unattended`), so
the flag is the owner's interactive session and nothing else. An attended task in doing/ is
that session's and stops nobody (board 049): a plain `next` neither continues it nor waits for
it — it offers the next task of todo/ — and a plain `start` puts the runner's task beside it, so
doing/ holds at most one task of each side. `summary` and the review call it «в роботі з
власником». The same holds the other way (board 740): the owner's session, which may sit in a
separate clone while the runner works, neither continues the runner's task nor is stopped by it —
`next --attended` and `start --attended` look at the attended tasks of doing/ only, and an ordinary
task started with `--attended` is still the runner's side's, refused beside another. Whoever asks «which
task is in hand» — the audit permission, the overseer's unit key, a hook's journal entry — gets
its own side's (`own`, board 712): an agent alone the plain one, the owner's session the attended
one, or the plain one when no attended task is there.

THE OWNER'S ANSWERS FIRST (board 049). A task the owner has just answered does not go to the end
of the queue, whatever its number — a gate question is of class 9. `unblock` appends the
names it returns to todo/ to `tasks/.first`, one per line; `next` takes the tasks named there
before every other, in the order answered, and the rest by number. Dependencies and the owner's
presence hold as for any task: an answered task that cannot start keeps its place for when it
can. `start` removes the name; a name that is not in todo/ means nothing. Every answered task —
a gate's, a rule's, an offered action's, a parked one, an open item — returns through `unblock`,
so the rule has one place. The file is committed with tasks/ like the move itself.

A PARKED TASK (board 021). One task never stops the board: when the runner gives up on a task —
attempts in a row without a commit, a task open too long, its budget spent, a task the agent put
back into todo/, three overseer BLOCKs in a row on one unit (board 031: the Stop hook leaves a
marker, `--verdicts` writes its verdicts into the task) — `park` moves it to blocked/ itself, with a section `## Чому зупинилась` (one
dated line per stop, placed before the questions) and a question to the owner with an empty
`Відповідь:`; any answer returns it to todo/ like every answered task. The same call writes the
event into THE ANOMALY JOURNAL, tasks/ANOMALIES.md: `## <UTC> — <task or task board>` with three lines
— what happened, what was done, who wrote it. Everything odd goes there instead of stopping the
work, whoever met it (board 035): the runner, the Stop gate when it escalates, a hook (`note`,
which gate.py and lesson_queue.py call), the agent (`anomaly … --source агент`). The runner
commits it with tasks/, and the review shows the new entries. The agent's uncommitted work of a
parked task is kept on a branch `wip/<task>/<UTC>` the runner pushed (`--wip`, `--wip-remote`)
and in a stash on the runner's machine (`--stash`); the task file and the journal name both.

AN OPEN ITEM (board 037). Everything that can be open is a file of the board, and it is closed
the way every task is: by moving to done/. `open_item` (the command `open-item`; called by
.claude/hooks/overseer_verdict.py when a unit is parked, and by an agent that an escalation or a
refused ask-gated command leaves with something only the owner can settle) writes
`NNN-open-item-<key>.md` (a number of class 7): into blocked/ with one question and an empty `Відповідь:` when the
owner must answer, into proposed/ when it is work an agent could do (A PROPOSAL), into done/ (task.md
and report.md) when it is recorded as already settled. With `--key` the line `Відкритий пункт: <key>` goes
under the title, and a second call with the key of a task still in proposed/, todo/, doing/ or blocked/
returns that task instead of writing another. The logs .engine/overseer/parked.md and escalations.md are
history: they are appended to where a project has no board, nothing in them is ever closed, and
nothing reads them to learn what is open.

A PROPOSAL (board 111, the owner's decision). New work is put to work by the owner alone. What an agent,
a hook or the overseer finds and could do later — an open item that is work, a test gap, the follow-up
of an urgent fix — is a file of the fifth column, tasks/proposed/, and nothing takes a task from there:
`next` and `start` read todo/ only. Its number is taken like any other (`taken`), so no new task gets
it; one number in proposed/ and in todo/ is an error `check` shows. The owner puts a proposal to work
through the inbox: a file with the proposal's number replaces it and lies in todo/ with the inbox text
(`import_inbox`). `summary` and the review count the proposals and name them. A question for the owner
goes to blocked/ as before.

A gate question whose escalation was CLOSED ANOTHER WAY (board 035) — the owner ran `gate.py
--close-escalation` in a terminal, so the stamp is among the closed ones in
.claude/state/gate/escalations.json — and that nobody answered asks nothing any more:
`gate-closed` lists it and the runner moves it to done/ (`gate-done <name> elsewhere`).

A TASK WITH EXTRA SESSIONS (board 110, the owner's decision) says `Додаткові сесії: так` under its
title: its work is sessions of Claude beyond its own — evals, measurements, a release audit, a full
pass of the simplifier. No leave is asked (board 078 stands), but: (1) `next` offers such a task only
when no ordinary task can start, the owner's answers included; (2) the extra sessions of all tasks
over the last seven days stay under the project's cap, EXTRA_SESSIONS_WEEK_USD in
`.claude/project.env` (no key, or not a number — no cap). The sum (board_state.extra_week) is every
session a tool booked to a task in extra-sessions.jsonl plus the own sessions of the marked tasks.
At the cap a marked task is not offered (`next` exits 5 when that is all that holds the board), the
cleanup task is not placed, and a tool starts no new session (board_state.extra_refusal). A task
that meets the cap in the middle of its work commits what is done and calls `extra-wait`: it goes
back to todo/ with the mark, with no question, and is taken again when the sum has fallen — the
runner does not park it. In the owner's own session (`--attended`) neither rule holds.

A MODE (board 097) is the task's: `Режим: ескіз|соло|конвеєр` under its title, соло without the
line. The mode itself is read by .claude/hooks/mode.py — the one reader of the mode and of «nobody
is watching»; here it decides one thing: a line that names no mode is nobody's clear word, so such a
task is not taken — `import-inbox` leaves the file in the inbox (with an entry in the journal) and
`next` passes it over (`summary` says why).

WHAT THE OWNER LOOKED OVER (board 100). A closed task that changed no working code hangs in the
review («Змінені документи й проєкти — переглянь», board_review.py) until its number stands in
tasks/.reviewed — one number a line (a name after it and a `#` comment are allowed). The file is the
owner's word, as an answer in blocked/ is: it arrives in the branch or as the file `.reviewed` in the
inbox (`import-inbox` adds its numbers and removes it), and an agent never writes it — the hooks
refuse the edit and the shell write (protected-path-list.sh), and a number that got there another
way is caught by the runner: `reviewed-accept` records, after every pull and inbox, the numbers that
arrived; `reviewed-reject` removes every number that is in the checkout — the file of the working
tree AND the file as HEAD has it, for a number may be committed and then taken out of the tree —
and was never recorded (it was written on this machine), says so in the anomaly journal and prints
them. A file that is no plain file (a link, a directory) is removed whole: git would store the
link's target as the content the review reads. With no record yet (a new machine) what `--known`
— the branch as origin had it — holds counts as arrived. The file is read as the review reads it
from git: bytes that are not UTF-8 are replaced, never an error — else one such byte would switch
the guard off. After the guard the runner asks `reviewed-clean` whether HEAD still holds such a number
and withholds its push when it does. All of this holds a number written in the ordinary way; a session
that works against the check on purpose is outside it (docs/engine-limits.md, «The same Linux user»).

`--root DIR` names the repository (default: the one this file is installed in).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # this file is also loaded by path: its sibling is found from here
import journal  # the anomaly journal: every session adds to its own file (board 739)
import mode as mode_reader  # the one reader of the mode and of «nobody is watching» (board 097)
import task_classes  # a task's number: its class x 100 + its place in the class (board 401)

PROPOSED = "proposed"  # tasks/proposed/: work somebody other than the owner found; nothing is taken from it (A PROPOSAL)
COLUMNS = ("todo", "doing", "blocked", "done", PROPOSED)
FIRST = ".first"  # tasks/.first: the todo/ tasks the owner answered (THE OWNER'S ANSWERS FIRST)
REVIEWED = ".reviewed"  # tasks/.reviewed: the closed tasks without working code the owner looked over (board 100)
REVIEWED_LINE = re.compile(r"^[ \t]*(\d{3,})(?![\w.])")
TASK_NAME = re.compile(r"^(\d{3,})-.+\.md$")
DONE_NAME = re.compile(r"^(\d{3,})-.+$")
DEPENDS = re.compile(r"^Залежить від:(.*)$", re.MULTILINE)
AUDIT = re.compile(r"^Аудит потрібен:\s*(\S+)", re.MULTILINE)
# A «Платні прогони:» line (board 053) is read no more: since board 078 a session of Claude a task
# starts — an eval, a measurement — is ordinary work, like a test, and needs no leave. An old task
# that carries the line works on: the line is ignored.
ATTENDED = re.compile(r"^Потрібна присутність власника:\s*(\S+)", re.MULTILINE)
EXTRA = re.compile(r"^Додаткові сесії:\s*(\S+)", re.MULTILINE)  # A TASK WITH EXTRA SESSIONS (board 110)
EXTRA_LINE, EXTRA_KEY = "Додаткові сесії: так", "EXTRA_SESSIONS_WEEK_USD"
KLASS = re.compile(r"^Клас:(.*)$", re.MULTILINE)  # A TASK'S CLASS (board 401): the value ends with its line
QUESTIONS = re.compile(r"^##\s+Питання до власника\s*$", re.MULTILINE)
HEADING = re.compile(r"^##\s", re.MULTILINE)
ANSWER = re.compile(r"^[\s>*_-]*Відповідь:[*_]*[ \t]*(.*)$", re.MULTILINE)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Both markers are read in the wording before board 053 too: a question already asked keeps working.
GATE = re.compile(r"^Ескалація (?:gates|воріт):\s*(\S+)", re.MULTILINE)
COUNT_WORDS = {2: "двох", 3: "трьох"}
CONSENT = "так"  # the one form of the owner's consent (board 036): see `is_word`
# What the runner may do on the owner's «так». `close-escalation` is offered by the gate's own
# question (the `Ескалація gates:` line), the rest by an action line.
OWNER_ACTIONS = ("apply-settings", "promote-rule", "amend-goals", "seal-goals", "update-deps", "close-escalation")
RULE_ACTION, RULE_DECLINE, RULE_NO = "promote-rule", "reject-rule", "ні"  # «ні» under a rule question closes the proposal
RULE = re.compile(r"^Пропозиція правила:\s*RP-(\w+)", re.MULTILINE)
ACTION = re.compile(r"^[\s>*_-]*Дія (?:runner-а|виконавця):[ \t]*`?([a-z][a-z-]*)(?:[ \t]+([0-9a-f]{64}))?`?[ \t]*$", re.MULTILINE)
DEPS_ACTION, DEPS_RESULT = "update-deps", ".engine/maintain/update-result.md"
SEAL_ACTION = "seal-goals"  # the first seal on the goals document (board 787)
ACTION_FILES = {"apply-settings": "docs/tasks/settings.json", "amend-goals": ".engine/goals/proposed.md",
                SEAL_ACTION: ".engine/goals.md", DEPS_ACTION: ".engine/maintain/updates.json"}  # the file whose sha256 the offer names
MAINTAIN_NAME = re.compile(r"^\d{3,}-maintain-(\d{4}-\d\d-\d\d)(?:\.md)?$")
MAINTAIN_COMMAND, MAINTAIN_DAYS = ".claude/commands/maintain.md", 7
ARCHITECT_NAME = re.compile(r"^\d{3,}-master-architect(?:\.md)?$")
CLEANUP_NAME = re.compile(r"^\d{3,}-cleanup-(\d{4}-\d\d-\d\d)(?:\.md)?$")
CLEANUP_SCRIPT, CLEANUP_DAYS = ".claude/hooks/simplifier.py", 1
ITEM = re.compile(r"^Відкритий пункт:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
OFFERS = {*ACTION_FILES, RULE_ACTION}  # what an action line may offer; the rule's sha256 is of its id and text
EXIT_REFUSED, EXIT_TODO_EMPTY, EXIT_NONE_ELIGIBLE, EXIT_EXTRA_WAIT = 2, 3, 4, 5


@dataclass(frozen=True)
class Task:
    depends: tuple[int, ...]
    audit: bool
    questions: str
    answers: tuple[str, ...]
    gate: str = ""
    action: str = ""
    action_arg: str = ""
    rule: str = ""
    attended: bool = False
    mode_error: str = ""  # the `Режим:` line names no mode: the task is not taken (A MODE)
    extra: bool = False  # «Додаткові сесії: так»: after the ordinary tasks, under the weekly sum
    klass: int | None = None  # the `Клас:` line (board 401); read only to number an inbox file that has no number
    class_error: str = ""  # why the `Клас:` line names no class; "" when it does or is absent

    @property
    def answered(self) -> bool:
        """Every question has its answer — and there is at least one: a task that asks nothing
        was answered by nobody."""
        return bool(self.answers) and all(self.answers)

    @property
    def closes(self) -> bool:
        """A gate question whose last answer is the one word «так»: the runner's to act on."""
        return bool(self.gate) and self.says(CONSENT)

    @property
    def approves(self) -> bool:
        """An offered action whose last answer is the one word «так»: the runner's to act on."""
        return bool(self.action) and not self.gate and self.says(CONSENT)

    @property
    def declines(self) -> bool:
        """A rule question whose last answer is the one word «ні»: the runner closes the proposal."""
        return self.action == RULE_ACTION and not self.gate and self.says(RULE_NO)

    @property
    def decided(self) -> str:
        """The action the runner is to take on the owner's answer, or ""."""
        return self.action if self.approves else RULE_DECLINE if self.declines else ""

    def says(self, word: str) -> bool:
        """Every question is answered and the last answer is nothing but `word`."""
        return self.answered and is_word(self.answers[-1], word)


def is_word(answer: str, word: str) -> bool:
    """`answer` is exactly the one word `word`: case and punctuation do not count, any other
    word does — «так, але інакше» is an instruction, not consent."""
    return re.sub(r"[\W_]+", " ", answer.lower()).split() == [word]


def parse(text: str) -> Task:
    text = COMMENT.sub("", text)
    first_heading = HEADING.search(text)
    header = text[: first_heading.start()] if first_heading else text
    depends = DEPENDS.search(header)
    audit = AUDIT.search(header)
    attended = ATTENDED.search(header)
    gate = GATE.search(header)
    extra = EXTRA.search(header)
    section = QUESTIONS.search(text)
    questions = ""
    if section:
        rest = text[section.end():]
        following = HEADING.search(rest)
        questions = rest[: following.start()] if following else rest
    rule = RULE.search(header)
    klass, class_error = _class_line(header)
    offers = [m for m in ACTION.finditer(questions) if m.group(1) in OFFERS]
    return Task(
        action=offers[-1].group(1) if offers else "",
        action_arg=(offers[-1].group(2) or "") if offers else "",
        depends=tuple(int(n) for n in re.findall(r"\d+", depends.group(1))) if depends else (),
        audit=audit is not None and audit.group(1).strip(".,;*_").lower() == "так",
        questions=questions.strip(),
        answers=tuple(a.strip() for a in ANSWER.findall(questions)),
        gate=gate.group(1) if gate else "",
        rule=rule.group(1) if rule else "",
        attended=attended is not None and attended.group(1).strip(".,;*_").lower() == "так",
        mode_error=mode_reader.parse(text).error,
        extra=extra is not None and extra.group(1).strip(".,;*_").lower() == "так",
        klass=klass, class_error=class_error,
    )


def _class_line(header: str) -> tuple[int | None, str]:
    """The class a task's header names and, when its `Клас:` line names none, why. The line is read
    for one thing only: to number an inbox file that came without a number."""
    values = [value.strip(" \t\r") for value in KLASS.findall(header)]
    if len(values) > 1:
        return None, "рядків «Клас:» два або більше — незрозуміло, котрий чинний"
    if values and not re.fullmatch(r"[0-9]+", values[0]):
        return None, f"«Клас: {values[0]}» — це не номер класу: потрібні лише цифри, як у tasks/{task_classes.CLASSES_FILE}"
    return (int(values[0]), "") if values else (None, "")


def first_rank(first: list[str]) -> Callable[[str], int]:
    """The sort key that moves the task files named in `first` to the front, in the order of
    `first`, and leaves the rest as they were. The one rule of THE OWNER'S ANSWERS FIRST, for the
    board and for the review."""
    rank = {n: i for i, n in enumerate(dict.fromkeys(first))}
    return lambda name: rank.get(name, len(rank))


def number_of(name: str) -> int | None:
    match = TASK_NAME.match(name) or DONE_NAME.match(name)
    return int(match.group(1)) if match else None


def read(path: Path) -> Task:
    return parse(path.read_text(encoding="utf-8"))


class Board:
    def __init__(self, tasks: Path) -> None:
        self.tasks = tasks
        self._unjudged: dict[str, str] | None = None   # gate_allows.unjudged, asked once for all of todo/

    def files(self, column: str) -> list[Path]:
        """The task files of todo/, doing/, blocked/ or proposed/, lowest number first."""
        found = [p for p in (self.tasks / column).glob("*.md") if p.is_file() and TASK_NAME.match(p.name)]
        return sorted(found, key=lambda p: (number_of(p.name) or 0, p.name))

    def done(self) -> list[Path]:
        """The folders of done/ that hold a task.md: a report written ahead of the move, for its reader
        (board 100), does not make the task done."""
        folder = self.tasks / "done"
        found = [p for p in folder.iterdir() if (p / "task.md").is_file() and DONE_NAME.match(p.name)] if folder.is_dir() else []
        return sorted(found, key=lambda p: (number_of(p.name) or 0, p.name))

    def numbers(self, column: str) -> set[int]:
        paths = self.done() if column == "done" else self.files(column)
        return {n for p in paths if (n := number_of(p.name)) is not None}

    def taken(self) -> set[int]:
        """Every number of the five columns: what a new task's number is counted from."""
        return {n for column in COLUMNS for n in self.numbers(column)}

    def unmet(self, task: Task) -> list[int]:
        finished = self.numbers("done")
        return [n for n in task.depends if n not in finished]

    def first(self) -> list[str]:
        """The names in tasks/.first: the tasks the owner answered, oldest answer first."""
        return _text(self.tasks / FIRST).split()

    def set_first(self, names: list[str]) -> None:
        """Rewrite tasks/.first with those of `names` that are in todo/; no such name — no file."""
        waiting = {p.name for p in self.files("todo")}
        kept = [n for n in dict.fromkeys(names) if n in waiting]
        if kept:
            (self.tasks / FIRST).write_text("".join(f"{n}\n" for n in kept), encoding="utf-8")
        else:
            (self.tasks / FIRST).unlink(missing_ok=True)

    def queue(self) -> list[Path]:
        """todo/ in the order it is taken: what the owner answered, then the rest by number."""
        rank = first_rank(self.first())
        return sorted(self.files("todo"), key=lambda p: rank(p.name))

    def in_hand(self, attended: bool = False) -> list[Path]:
        """The tasks of doing/ that are this side's: the owner's session holds the attended ones,
        an agent alone the others (AN ATTENDED TASK)."""
        return [p for p in self.files("doing") if read(p).attended == attended]

    def held_cleanup(self, path: Path) -> Path | None:
        """The owner's attended task in doing/ a cleanup task waits for (THE CLEANUP TASK); None — it does not wait."""
        owners = self.in_hand(True)
        return owners[0] if owners and CLEANUP_NAME.match(path.name) else None

    def gate_hold(self, path: Path | None = None) -> str | None:
        """The stamp of the open gate escalation that would refuse the task's verdict; with no path —
        of one that covers all work (A GATE ESCALATION HOLDS A TASK). None — nothing holds. Best effort."""
        try:
            import gate_allows

            root = self.tasks.parent
            entries = gate_allows.open_escalations(root)
            whole = [str(entry.get("stamp", "?")) for entry in entries if not entry.get("files")]
            if whole or path is None or not entries:
                return whole[0] if whole else None
            if self._unjudged is None:
                self._unjudged = gate_allows.unjudged(root)
            over = gate_allows.escalation_over(root, path.stem, tree=False, files=self._unjudged)
            return over[0] if over else None
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def ready(self, attended: bool = False) -> list[tuple[Path, Task]]:
        """The tasks of the queue that could start, in its order: for an agent alone, never an
        attended one; with attended=True (the owner's session), the attended ones."""
        return [(p, task) for p in self.queue() for task in [read(p)]
                if task.attended == attended and not self.unmet(task) and not task.mode_error and not self.held_cleanup(p)
                and (attended or not self.gate_hold(p))]

    def eligible(self, attended: bool = False) -> Path | None:
        """The first task that can start. For an agent alone a task with extra sessions comes after
        every ordinary one and not at all while the weekly sum is at its cap (A TASK WITH EXTRA SESSIONS)."""
        ready = self.ready(attended)
        if attended:
            return ready[0][0] if ready else None
        ordinary = [p for p, task in ready if not task.extra]
        if ordinary or not ready or extra_refusal(self.tasks):
            return ordinary[0] if ordinary else None
        return ready[0][0]

    def shown(self, path: Path) -> str:
        return path.relative_to(self.tasks.parent).as_posix()

    def with_number(self, column: str, number: int) -> list[Path]:
        return [p for p in self.files(column) if number_of(p.name) == number]


def unattended_session(root: Path) -> bool:
    """Nobody is watching: the runner's environment says so, or the mode file does (mode.py reads both)."""
    return mode_reader.unattended(root)[0]


def own(tasks: Path) -> list[Path]:
    """The tasks of doing/ that are the asking session's (board 712): an agent alone has the ones
    that need no owner; the owner's session has the attended ones and, with none there, the rest."""
    board = Board(tasks)
    if unattended_session(tasks.parent):
        return board.in_hand()
    return board.in_hand(True) or board.in_hand()


def attended_refusal(root: Path) -> str | None:
    """Why `--attended` may not be used here; None in a session the owner sits in."""
    if unattended_session(root):
        return ("--attended is for an interactive session with the owner present; this session is unattended "
                "(CLAUDE_UNATTENDED_SESSION=1 or .claude/state/overseer/mode)")
    return None


def cmd_next(board: Board, attended: bool = False) -> int:
    # An agent alone never sees the owner's session's task in doing/ (board 049): it is neither
    # continued nor in the way. Nor does the owner's session see the runner's (board 740): in a
    # separate clone that task is in doing/ while the runner works on it elsewhere.
    doing = board.in_hand(attended)
    if len(doing) > 1:
        print("board: tasks/doing/ holds more than one task (" + ", ".join(p.name for p in doing)
              + ") — one at a time; move the extra ones back to tasks/todo/", file=sys.stderr)
        return EXIT_REFUSED
    if doing:
        print(board.shown(doing[0]))
        return 0
    task = board.eligible(attended)
    if task is None:
        if not attended and board.ready():   # only tasks with extra sessions, held by the weekly sum
            return EXIT_EXTRA_WAIT
        return EXIT_NONE_ELIGIBLE if board.files("todo") else EXIT_TODO_EMPTY
    print(board.shown(task))
    return 0


def cmd_start(board: Board, root: Path, given: str, attended: bool = False) -> int:
    try:
        source = (root / given).resolve() if not Path(given).is_absolute() else Path(given).resolve()
    except RuntimeError:  # a symlink loop, up to Python 3.12: not a file, refused below
        source = root / given
    if source.parent != (board.tasks / "todo").resolve() or not source.is_file() or not TASK_NAME.match(source.name):
        print(f"board: {given} is not a task file in tasks/todo/", file=sys.stderr)
        return EXIT_REFUSED
    if read(source).attended and not attended:
        print(f"board: {source.name} needs the owner present («Потрібна присутність власника: так») — it is started only "
              "in an interactive session with the owner: board.py start --attended (tasks/README.md)", file=sys.stderr)
        return EXIT_REFUSED
    held = board.held_cleanup(source)
    if held:
        print(f"board: {source.name} is a cleanup task and waits while the owner's attended task {held.name} is in tasks/doing/ "
              "(two authors in the same files would conflict at the merge)", file=sys.stderr)
        return EXIT_REFUSED
    stamp = None if attended else board.gate_hold(source)
    if stamp:
        print(f"board: {source.name} waits for the owner to close the gate escalation {stamp}: while it is open the "
              "overseer's PASS is not accepted for this task's work (tasks/README.md, «Питання від gates»)", file=sys.stderr)
        return EXIT_REFUSED
    doing = board.in_hand(read(source).attended)   # the side is the task's: an ordinary one is the runner's even with --attended
    if doing:
        print(f"board: tasks/doing/ already holds {doing[0].name} — one task at a time", file=sys.stderr)
        return EXIT_REFUSED
    target = board.tasks / "doing" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    board.set_first(board.first())
    print(board.shown(target))
    return 0


def cmd_where(board: Board, stem: str) -> int:
    stem = stem.removesuffix(".md")
    for column in ("todo", "doing", "blocked", PROPOSED):
        if (board.tasks / column / f"{stem}.md").is_file():
            print(column)
            return 0
    print("done" if (board.tasks / "done" / stem / "task.md").is_file() else "missing")
    return 0


def import_inbox(board: Board, inbox: Path) -> list[str]:
    """Move the task files of `inbox` onto the board. One line per file:

    imported  a new number: into todo/
    replaced  the number is in todo/: the inbox file takes its place (the owner's newer text)
    taken from proposed/  the number is a proposal's (A PROPOSAL): the owner puts it to work — the
              proposal leaves proposed/ and the inbox file lies in todo/, with the owner's text
    answered  the number is in blocked/ and the inbox copy has every answer filled: it replaces
              the blocked file — this is how an answer arrives without git; `unblock` then moves it
    skipped   the number is in doing/ or done/ (nothing there is ever touched), or in blocked/
              while the copy is not fully answered (it would wipe the questions). The file stays
              in the inbox.
    A file taken is REMOVED from the inbox: a copy left behind would come back as a new task
    after the real one reached done/.

    TWO FILES WITH ONE NUMBER in the column (board 065) are an error of the board, and the number
    no longer says which of them is meant: the inbox file then stands for the one with its exact
    name, and replaces that one only. No such name — skipped, nothing is deleted, and the anomaly
    journal says so (once for a file that stays in the inbox).
    """
    lines: list[str] = []
    if not inbox.is_dir():
        return lines
    for source in sorted(inbox.glob("*.md"), key=lambda p: (number_of(p.name) or 0, p.name)):
        number = number_of(source.name) if TASK_NAME.match(source.name) else None
        if number is None or not source.is_file():
            continue
        content = source.read_bytes()
        wrong = parse(content.decode("utf-8", "replace")).mode_error
        if wrong:
            lines.append(f"{source.name} skipped: {wrong} — the board does not take it; the file stays in the inbox")
            _unread_mode(board, source.name, wrong)
            continue
        busy = next((c for c in ("doing", "done") if number in board.numbers(c)), None)
        blocked = board.with_number("blocked", number)
        if busy:
            lines.append(f"{source.name} skipped: {number:03d} is in {busy}/")
            continue
        todo = [] if blocked else board.with_number("todo", number)
        offered = [] if blocked or todo else board.with_number(PROPOSED, number)
        twins = blocked or todo or offered
        if len(twins) > 1:
            several = twins
            twins = [p for p in twins if p.name == source.name]
            blocked, todo, offered = (twins, [], []) if blocked else ([], twins, []) if todo else ([], [], twins)
            if not twins:
                lines.append(f"{source.name} skipped: {number:03d} is the number of several files in one column and none has this name")
                _ambiguous(board, source.name, several)
                continue
        if blocked:
            if not parse(content.decode("utf-8", "replace")).answered:
                lines.append(f"{source.name} skipped: {number:03d} is in blocked/ and this copy does not answer every question")
                continue
            column, verb, old = "blocked", "answered", blocked
        else:
            column, verb, old = "todo", "replaced" if todo else f"taken from {PROPOSED}/" if offered else "imported", todo or offered
        for path in old:
            path.unlink()
        target = board.tasks / column / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        source.unlink()
        lines.append(f"{source.name} {verb}: tasks/{column}/{source.name}")
    said = inbox / REVIEWED
    if said.is_file() and not said.is_symlink():   # the owner looked tasks over (board 100): the numbers join tasks/.reviewed
        have = reviewed_numbers(_reviewed_text(board.tasks / REVIEWED))
        new = [n for n in reviewed_numbers(_reviewed_text(said)) if n not in have]
        write_reviewed(board, have + new)
        said.unlink()
        lines.append(f"{REVIEWED} taken: {len(new)} new number(s) in tasks/{REVIEWED}")
    return lines + _take_unnumbered(board, inbox)


def _take_unnumbered(board: Board, inbox: Path) -> list[str]:
    """The inbox files that came WITHOUT a number and with a `Клас:` line (board 401): each gets the
    next number of its class and goes to todo/ — after every numbered file, and never with a number
    a numbered file still waiting in the inbox carries (that file would replace the task). A file
    without the line is no task: it is left where it is, without a word."""
    classes = task_classes.read_classes(board.tasks)
    files = sorted(p for p in inbox.glob("*.md") if p.is_file())
    return [line for source in files if not TASK_NAME.match(source.name) and (line := _take_one(board, source, files, classes))]


def _take_one(board: Board, source: Path, files: list[Path], classes: tuple[int, ...]) -> str:
    """The line of one unnumbered inbox file: skipped with its reason, imported with its number, "" when it is no task."""
    content = source.read_bytes()
    task = parse(content.decode("utf-8", "replace"))
    if task.klass is None and not task.class_error:
        return ""
    refusal = task.mode_error or _class_refusal(task, classes)
    if refusal:
        _unread_mode(board, source.name, refusal, "" if task.mode_error else CLASS_REMEDY)
        return f"{source.name} skipped: {refusal} — the board does not take it; the file stays in the inbox"
    waiting = {number_of(p.name) or 0 for p in files if TASK_NAME.match(p.name) and p.exists()}
    number = task_classes.next_number(board.taken() | waiting, task.klass or 0)
    target = board.tasks / "todo" / f"{number:03d}-{source.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_titled(content, number))
    source.unlink()
    return f"{source.name} imported: tasks/todo/{target.name}"


def _class_refusal(task: Task, classes: tuple[int, ...]) -> str:
    """Why a task's `Клас:` line gives it no class of the table; "" when it does."""
    if task.class_error or task.klass is None:
        return task.class_error
    try:
        task_classes.class_for(task.klass, classes)
    except ValueError as refusal:
        return f"«Клас: {task.klass}» — {refusal}"
    return ""


def _titled(content: bytes, number: int) -> bytes:
    """The task's text with its number in the template's first line, `# NNN — …`; nothing else changes."""
    placeholder = "# NNN —".encode()
    return f"# {number:03d} —".encode() + content[len(placeholder):] if content.startswith(placeholder) else content




def reviewed_numbers(text: str) -> list[int]:
    """The task numbers of a `.reviewed` text, in its order, each once: one a line, at the line's start."""
    found: list[int] = []
    for line in text.splitlines():
        number = REVIEWED_LINE.match(line)
        if number and int(number.group(1)) not in found:
            found.append(int(number.group(1)))
    return found


def write_reviewed(board: Board, numbers: list[int]) -> None:
    path = board.tasks / REVIEWED
    if numbers:
        path.write_text("".join(f"{n:03d}\n" for n in sorted(set(numbers))), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def _reviewed_text(path: Path) -> str:
    """A `.reviewed` file as the review reads it from git: bytes that are not UTF-8 are replaced, never an
    error (one such byte must not switch the guard off). Nothing for what is no plain file."""
    try:
        return path.read_bytes().decode("utf-8", "replace") if path.is_file() and not path.is_symlink() else ""
    except OSError:
        return ""


def reviewed_at(root: Path, rev: str) -> tuple[str, bool]:
    """(tasks/.reviewed as the commit `rev` has it, read as the review reads it; whether it is a plain file
    there). No such file, or no such commit: ("", True)."""
    rel = f"tasks/{REVIEWED}"
    entry = subprocess.run(["git", "-C", str(root), "ls-tree", rev, "--", rel], capture_output=True, check=False)
    if entry.returncode != 0 or not entry.stdout.strip():
        return "", True
    plain = entry.stdout.split()[:2] in ([b"100644", b"blob"], [b"100755", b"blob"])
    blob = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"], capture_output=True, check=False)
    return (blob.stdout.decode("utf-8", "replace") if blob.returncode == 0 and plain else ""), plain


def _arrived(root: Path, accepted: Path, known: str) -> list[int]:
    """The numbers that arrived from the owner: the runner's record; without one, the file as `known` has it."""
    if accepted.is_file():
        return reviewed_numbers(_reviewed_text(accepted))
    return reviewed_numbers(reviewed_at(root, known)[0]) if known else []


def reviewed_reject(board: Board, accepted: Path, known: str) -> list[str]:
    """Remove from tasks/.reviewed what did not arrive from the owner; what was removed is returned, a word
    each: a number, and `not-a-file` for a link or a directory. Both the file of the working tree and the
    file as HEAD has it are judged — the push sends HEAD. `accepted` is the runner's record of what arrived;
    without it, `known` — the revision whose file counts as arrived."""
    root, path = board.tasks.parent, board.tasks / REVIEWED
    committed, plain = reviewed_at(root, "HEAD")
    odd = path.is_symlink() or (path.exists() and not path.is_file()) or not plain
    here = reviewed_numbers(_reviewed_text(path))
    here += [n for n in reviewed_numbers(committed) if n not in here]
    arrived = _arrived(root, accepted, known)
    wrong = [n for n in here if n not in arrived]
    if not (wrong or odd):
        return []
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    write_reviewed(board, [n for n in here if n in arrived])
    removed = [f"{n:03d}" for n in wrong] + (["not-a-file"] if odd else [])
    shown = ", ".join(f"{n:03d}" for n in wrong) or "жодного номера"
    anomaly(board, "-", f"у `tasks/{REVIEWED}` з'явилися номери, які не прийшли від власника ні гілкою, ні через inbox: {shown} — їх записано на цій машині"
            + (f"; сам `tasks/{REVIEWED}` був не звичайним файлом (посилання чи тека)" if odd else ""),
            f"номери прибрано з `tasks/{REVIEWED}`; ці задачі й далі висять в огляді, доки власник сам не скаже «переглянув» (номер у "
            f"`tasks/{REVIEWED}` у гілці або файл `{REVIEWED}` в inbox)")
    return removed


def reviewed_clean(root: Path, accepted: Path, known: str) -> bool:
    """tasks/.reviewed as HEAD has it is a plain file (or absent) that holds arrived numbers alone. HEAD is
    what the runner's push sends while the checkout is on the work branch — the ordinary case."""
    committed, plain = reviewed_at(root, "HEAD")
    arrived = _arrived(root, accepted, known)
    return plain and all(n in arrived for n in reviewed_numbers(committed))


def _ambiguous(board: Board, name: str, twins: list[Path]) -> None:
    """The journal entry of an inbox file that names none of several same-numbered files."""
    column = twins[0].parent.name
    what = (f"файл `{name}` з inbox має номер, який у `{column}/` носять кілька файлів ({', '.join(f'`{p.name}`' for p in twins)}), "
            "і жоден з них не має такої самої назви")
    if " ".join(what.split()) not in journal.text(board.tasks.parent, "anomalies"):
        anomaly(board, "-", what, "нічого не видалено й не замінено; файл лишився в inbox. Назвіть його точно так, як файл у task board, "
                "якого він стосується, а однакові номери розведіть (`board.py check`)", "task board (import-inbox)")


CLASS_REMEDY = (f"файл лишився в inbox. Напишіть у рядку `Клас:` номер класу з `tasks/{task_classes.CLASSES_FILE}` "
                "(або дайте файлу номер у назві — тоді рядок не читається) і покладіть файл знову")


def _unread_mode(board: Board, name: str, wrong: str, remedy: str = "") -> None:
    """The journal entry of an inbox file that is not taken, once per file and reason: its `Режим:` line names
    no mode (A MODE) or — with the `remedy` of that case — its `Клас:` line names no class (board 401)."""
    what = f"файл `{name}` з inbox не взято: {wrong}"
    if " ".join(what.split()) not in journal.text(board.tasks.parent, "anomalies"):
        anomaly(board, "-", what, remedy or f"файл лишився в inbox. Виправте рядок на `Режим: {'|'.join(mode_reader.MODES)}` "
                "(або приберіть його — тоді соло) і покладіть файл знову", "task board (import-inbox)")


def duplicate_lines(columns: dict[str, list[str]]) -> list[str]:
    """TWO FILES WITH ONE NUMBER in one column (board 065), one line per number. `columns` maps a
    column to the names in it. The number is how the inbox, the dependencies and the owner name a
    task, so this is an error of the board — shown by `summary`, `check` and the review."""
    lines: list[str] = []
    for column, names in columns.items():
        groups: dict[int, list[str]] = {}
        for name in sorted(names):
            number = number_of(name)
            if number is not None:
                groups.setdefault(number, []).append(name)
        lines += [f"ПОМИЛКА: один номер {number:03d} у {COUNT_WORDS.get(len(group), 'кількох')} файлах у {column}/: {', '.join(group)} — "
                  "перенумеруйте всі, крім одного: відповідь через inbox і залежності знаходять задачу за номером"
                  for number, group in sorted(groups.items()) if len(group) > 1]
    return lines


def proposed_lines(columns: dict[str, list[str]]) -> list[str]:
    """ONE NUMBER IN proposed/ AND IN todo/ (A PROPOSAL), one line per number: the inbox file that puts
    a proposal to work would replace the task instead."""
    waiting = {number: name for name in sorted(columns.get("todo", [])) if (number := number_of(name)) is not None}
    return [f"ПОМИЛКА: один номер {number:03d} у todo/ і в {PROPOSED}/: todo/{waiting[number]}, {PROPOSED}/{name} — "
            "перенумеруйте один із них: файл з inbox із цим номером замінить задачу в todo/, а не поставить пропозицію в роботу"
            for name in sorted(columns.get(PROPOSED, [])) if (number := number_of(name)) in waiting]


def duplicates(board: Board) -> list[str]:
    columns = {c: [p.name for p in (board.done() if c == "done" else board.files(c))] for c in COLUMNS}
    return [*duplicate_lines(columns), *proposed_lines(columns)]


def errors(board: Board) -> list[str]:
    """The board's error lines, for `check` and `summary`: one number on two files, and what is wrong with the table of classes."""
    table = task_classes.table_errors(_text(board.tasks / task_classes.CLASSES_FILE))
    return [*duplicates(board), *(f"ПОМИЛКА: tasks/{task_classes.CLASSES_FILE}: {sentence}" for sentence in table)]


def unblock(board: Board) -> list[str]:
    moved: list[str] = []
    for path in board.files("blocked"):
        task = read(path)
        # A gate question answered «так» is closed by the runner, not handed to an agent;
        # an offered action answered «так» waits for the runner to act on it first.
        if task.answered and not task.closes and not task.decided:
            target = board.tasks / "todo" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
            moved.append(path.name)
    if moved:
        board.set_first([*board.first(), *moved])
    return moved


def gate_question(board: Board, stamp: str, blocks: int, slice_name: str, files: list[str],
                  reasons: list[str], report: str) -> Path | None:
    """The Stop gate's escalation as a question in blocked/. None when the project has no board;
    the task already written for this stamp when there is one."""
    if not board.tasks.is_dir():
        return None
    for path in [*(p for c in ("todo", "doing", "blocked") for p in board.files(c)), *(d / "task.md" for d in board.done())]:
        if path.is_file() and read(path).gate == stamp:
            return path
    number = task_classes.next_number(board.taken(), task_classes.GATES)

    def shown(lines: list[str], empty: str) -> str:
        return "\n".join(f"  - {line.replace('<!--', '<! --').strip()}" for line in lines) or f"  - {empty}"

    text = f"""# {number} — Gates зупинили роботу: потрібне ваше рішення

Залежить від: —
Аудит потрібен: ні
Ескалація gates: {stamp}

## Що сталося
Перевірки наприкінці ходу (gates) не пройшли {blocks} раз(и) поспіль, і агент не зміг цього
виправити. Хід завершено; зроблене лежить на диску. Поки це питання відкрите, overseer не
приймає роботу, яка зачіпає ці файли.

- Slice: {slice_name}
- Файли:
{shown(files, "(gates не назвали файлів)")}
- На чому зупинилося:
{shown(reasons, "(причину не записано)")}
- Повний звіт (на сервері): `{report}`

## Що зробити
Це питання поставили gates, а не агент. Агент на нього не відповідає і сам ескалацію не
закриває: відповідь «так» виконує runner. Якщо власник відповів інакше — це
вказівка агентові: виконай її, допиши внизу нове питання «Тепер закрити ескалацію?» з порожнім
рядком відповіді й поверни задачу в `tasks/blocked/`.

## Готово, коли
Власник відповів «так», і runner закрив ескалацію.

## Питання до власника
Варіанти відповіді:
- `так` — рівно це одне слово: зауваження gates прийнято або вже виправлено; ескалацію буде закрито,
  роботу з цими файлами можна приймати далі.
- будь-який інший текст (і «так, але…» теж) — вказівка агентові, що саме виправити; ескалація
  лишається відкритою.

1. Закрити ескалацію?
   Відповідь:
"""
    target = board.tasks / "blocked" / f"{number}-gate-escalation-{re.sub(r'[^0-9A-Za-z]', '', stamp)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def rule_question(board: Board, ident: str, rule: str, why: str, origin: str, advice: str, sha: str) -> Path | None:
    """A rule proposal as a question in blocked/ (board 040). None when the project has no board;
    the task already written for this proposal when there is one."""
    if not board.tasks.is_dir():
        return None
    for path in [*(p for c in ("todo", "doing", "blocked") for p in board.files(c)), *(d / "task.md" for d in board.done())]:
        if path.is_file() and read(path).rule == ident:
            return path
    number = task_classes.next_number(board.taken(), task_classes.RULES)

    def shown(text: str, empty: str) -> str:
        return " ".join(text.replace("<!--", "<! --").split()) or empty

    text = f"""# {number} — Зробити урок правилом? Пропозиція RP-{ident}

Залежить від: —
Аудит потрібен: ні
Пропозиція правила: RP-{ident}

## Що сталося
Із роботи над проєктом винесено урок, схожий на постійне правило. Уроки не стають правилами
самі: це правило з'явиться лише з вашої згоди. Overseer може радити, але не вирішує.

- Текст правила — саме так, слово в слово, він потрапить у `.engine/rules.md`, який читає кожна розмова:

  > {shown(rule, "(тексту немає)")}

- Чому: {shown(why, "(не записано)")}
- Звідки урок: {shown(origin, "(не записано)")}
- Рекомендація overseer-а: {shown(advice, "немає")}

## Що зробити
Це питання до власника, не робота для агента. Відповіді «так» і «ні» виконує runner.
Якщо власник відповів інакше — це вказівка агентові: виконай її (щоб змінити текст правила,
закрий цю пропозицію — `python3 .claude/hooks/lesson_queue.py reject {ident} --why "<слова власника>"` —
і подай нову), запиши у звіт і закрий задачу. Сам `promote` не запускай і `Відповідь:` не заповнюй.

## Готово, коли
Власник відповів, і runner записав правило або закрив пропозицію.

## Питання до власника
Варіанти відповіді:
- `так` — рівно це одне слово: урок стає правилом, рядок вище буде додано до `.engine/rules.md`.
- `ні` — правилом не стає; пропозицію закрито.
- будь-який інший текст (і «так, але…» теж) — вказівка агентові (наприклад, як переписати правило).

1. Зробити це правилом?
   Дія runner-а: {RULE_ACTION} {sha}
   Відповідь:
"""
    target = board.tasks / "blocked" / f"{number}-rule-proposal-{ident}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def open_item(board: Board, column: str, title: str, what: str, question: str = "", do: str = "",
              key: str = "", source: str = "") -> Path | None:
    """Something open as a task of the board (board 037): a question in blocked/, work as a proposal
    in proposed/ (`column` "proposed", or its old name "todo": only the owner puts work into todo/ —
    A PROPOSAL), or — settled already — a directory in done/ whose report is `do`. None when the
    project has no board or a question is asked without its text; the task that already carries
    `key` when one is still in proposed/, todo/, doing/ or blocked/."""
    column = PROPOSED if column == "todo" else column
    title, what, question, do, key, source = (" ".join(part.replace("<!--", "<! --").split()) for part in (title, what, question, do, key, source))
    if not board.tasks.is_dir() or not title or (column == "blocked" and not question):
        return None
    if key:
        for path in (p for c in ("todo", "doing", "blocked", PROPOSED) for p in board.files(c)):
            found = ITEM.search(path.read_text(encoding="utf-8").split("\n## ", 1)[0])
            if found and found.group(1) == key:
                return path
    number = task_classes.next_number(board.taken(), task_classes.OPEN_ITEMS)
    now = utc_now()
    slug = re.sub(r"[^0-9a-z]+", "-", (key or title).lower()).strip("-")[:40].strip("-") or re.sub(r"\D", "", now)
    work, ready = {
        "blocked": (("Це питання до власника, не робота для агента. Коли власник відповість, задача повернеться в чергу: "
                     "виконай відповідь, запиши її у звіт і закрий задачу."), "Власник відповів, і відповідь виконано."),
        PROPOSED: (do or "Розібратися з описаним вище і довести справу до кінця; чого без власника не вирішити — питанням у `tasks/blocked/`.",
                 "Описане вище зроблено і перевірено, або на нього є відповідь власника."),
        "done": ("Нічого: пункт записано вже закритим. Чому — у `report.md` поруч.", "Уже готово."),
    }[column]
    text = (f"# {number} — {title}\n\nЗалежить від: —\nАудит потрібен: ні\n" + (f"Відкритий пункт: {key}\n" if key else "")
            + f"\n## Що сталося\n{what or '(не записано)'}\n\n- Записано: {now}, {source or RUNNER}\n"
            + (PROPOSAL_NOTE if column == PROPOSED else "")
            + f"\n## Що зробити\n{work}\n\n## Готово, коли\n{ready}\n\n## Питання до власника\n"
            + (f"1. {question}\n   Відповідь:\n" if column == "blocked" else ""))
    name = f"{number}-open-item-{slug}"
    if column == "done":
        folder = board.tasks / "done" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.md").write_text(f"# {number} — {title}: звіт\n\n## Що змінилось для власника\n{do or what or '(не записано)'}\n", encoding="utf-8")
        target = folder / "task.md"
    else:
        target = board.tasks / column / f"{name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


PROPOSAL_NOTE = (f"- Це пропозиція, а не задача в черзі: runner із `tasks/{PROPOSED}/` нічого не бере. У роботу її ставить "
                 "власник — файлом із цим номером в inbox.\n")


def gate_answers(board: Board) -> list[str]:
    lines: list[str] = []
    for path in board.files("blocked"):
        task = read(path)
        if task.closes:
            lines.append(f"{path.name}\t{task.gate}\t{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return lines


def gate_closed(board: Board, root: Path) -> list[str]:
    """Unanswered gate questions in blocked/ whose escalation is recorded as closed. A stamp the
    state file does not know (another machine, a lost file) proves nothing and is left alone."""
    try:
        data = json.loads((root / ".claude/state/gate/escalations.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("closed") if isinstance(data, dict) else None
    closed = {str(e.get("stamp")) for e in rows if isinstance(e, dict)} if isinstance(rows, list) else set()
    lines: list[str] = []
    for path in board.files("blocked"):
        task = read(path)
        if task.gate in closed and not any(task.answers):
            lines.append(f"{path.name}\t{task.gate}")
    return lines


def gate_task(board: Board, name: str) -> Path | None:
    path = board.tasks / "blocked" / Path(name).name
    return path if path.is_file() and TASK_NAME.match(path.name) and read(path).gate else None


def gate_done(board: Board, path: Path, outcome: str) -> Path:
    """A gate question the runner has acted on: done/NNN-name/ with task.md and a report.md."""
    stamp = read(path).gate
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if outcome == "closed":
        changed = (f"Ескалацію gates {stamp} закрито за вашою відповіддю «так» ({now}, runner). "
                   "Overseer знову приймає роботу з цими файлами.")
    elif outcome == "elsewhere":
        changed = (f"Ескалацію gates {stamp} закрито іншим шляхом — командою `gate.py --close-escalation` у терміналі, "
                   f"а не відповіддю на це питання. Питання більше нічого не питає, тому runner сам прибрав його з task board ({now}).")
    else:
        changed = (f"Ескалація gates {stamp} на момент вашої відповіді вже не була відкрита (її закрито раніше "
                   f"або запису про неї немає). Питання прибрано з task board ({now}, runner).")
    target = board.tasks / "done" / path.stem
    target.mkdir(parents=True, exist_ok=True)
    path.rename(target / "task.md")
    (target / "report.md").write_text(
        f"# Звіт: {path.stem}\n\n## Що змінилось для власника\n- {changed}\n\n"
        "Цей звіт написав runner, не агент: жодної роботи тут не було"
        + (".\n" if outcome == "elsewhere" else ", лише ваша відповідь.\n"), encoding="utf-8")
    return target


def owner_actions(board: Board) -> list[str]:
    lines: list[str] = []
    for path in board.files("blocked"):
        task = read(path)
        if task.decided:
            lines.append(f"{path.name}\t{task.decided}\t{task.action_arg or '-'}\t{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return lines


def action_line(root: Path, action: str) -> str:
    """The offer an agent writes under its question: the action and the sha256 of what it applies."""
    return f"Дія runner-а: {action} {hashlib.sha256((root / ACTION_FILES[action]).read_bytes()).hexdigest()}"


def action_task(board: Board, name: str) -> Path | None:
    path = board.tasks / "blocked" / Path(name).name
    return path if path.is_file() and TASK_NAME.match(path.name) and read(path).action else None


STALE = ("Дію не виконано ({now}, runner): {action} — те, що застосовується, змінилося після запитання "
         "(інший sha256) або його немає; власник схвалював не це. Агентові: спитай знову з новим рядком дії.")
ACTION_OUTCOMES = {
    "applied": "Дію виконано ({now}, runner): {action} — застосовано за відповіддю власника «так», "
               "перевірка після застосування зелена. Агентові: переконайся і закрий задачу звітом.",
    "failed": "Дію не виконано ({now}, runner): {action} — перевірка червона: пропозицію не застосовано, на місці попередній "
              "файл (журнал на сервері: .claude/state/board/logs/owner-action.log). Агентові: виправ і спитай знову.",
    "stale": STALE,
}
RULE_OUTCOMES = {
    (DEPS_ACTION, "applied"): "Дію виконано ({now}, runner): {action} — за відповіддю власника «так» оновлення пройшли по одному: що оновлено "
                              f"(кожне окремим commit-ом), а що скасовано і з яким виводом — у `{DEPS_RESULT}`. Агентові: перенеси це у звіт і закрий задачу.",
    (DEPS_ACTION, "failed"): "Дію не виконано ({now}, runner): {action} — жодної залежності не оновлено: немає `DEPS_UPDATE_CMD`, робоче дерево "
                             f"було не чисте, перевірки не зелені ще до оновлень або гілка не `unattended/*` (подробиці — `{DEPS_RESULT}` або журнал на "
                             "сервері: .claude/state/board/logs/owner-action.log). Агентові: напиши причину у звіт; оновлювати знову — лише новим питанням.",
    (SEAL_ACTION, "applied"): "Дію виконано ({now}, runner): {action} — за відповіддю власника «так» документ цілей `.engine/goals.md` запечатано таким, "
                              "як він був у запитанні: він чинний; у новому проєкті runner поклав у todo/ задачу `/master-architect` з присутністю власника. "
                              "Агентові: переконайся (`goals.py status`) і закрий задачу звітом.",
    (SEAL_ACTION, "failed"): "Дію не виконано ({now}, runner): {action} — документ цілей не запечатано: у ньому немає жодного нумерованого рядка, номер "
                             "ужито двічі, або документ уже затверджували і відтоді змінили — тоді це поправка, `amend-goals` (журнал на сервері: "
                             ".claude/state/board/logs/owner-action.log). Агентові: виправ і спитай знову.",
    (RULE_ACTION, "applied"): "Дію виконано ({now}, runner): {action} — за відповіддю власника «так» правило додано до `.engine/rules.md`.",
    (RULE_ACTION, "failed"): "Дію не виконано ({now}, runner): {action} — правило не додано: постійний контекст перевищив би "
                             "200 рядків (журнал на сервері: .claude/state/board/logs/owner-action.log). Агентові: скороти "
                             "`.engine/rules.md` і спитай знову (`lesson_queue.py ask <id>`).",
    (RULE_DECLINE, "applied"): "Дію виконано ({now}, runner): {action} — за відповіддю власника «ні» пропозицію закрито; правилом вона не стала.",
}
RULE_REPORTS = {
    RULE_ACTION: "Урок став правилом за вашою відповіддю «так»: рядок додано до `.engine/rules.md` ({now}, runner).",
    RULE_DECLINE: "Пропозицію правила закрито за вашою відповіддю «ні»: правилом вона не стала ({now}, runner).",
}


def action_done(board: Board, path: Path, outcome: str) -> Path:
    """Replace the offer by what happened: the task is then an ordinary answered one (`unblock`)
    and the same answer can never run the action twice. A rule question the runner has acted on
    needs no agent: it goes to done/ with a report. Returns where the task is now."""
    task = read(path)
    action = task.decided or task.action
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = RULE_OUTCOMES.get((action, outcome), ACTION_OUTCOMES[outcome]).format(now=now, action=action)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [note if ACTION.match(line) else line for line in lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if action not in RULE_REPORTS or outcome != "applied":
        return path
    target = board.tasks / "done" / path.stem
    target.mkdir(parents=True, exist_ok=True)
    path.rename(target / "task.md")
    (target / "report.md").write_text(
        f"# Звіт: {path.stem}\n\n## Що змінилось для власника\n- {RULE_REPORTS[action].format(now=now)}\n\n"
        "Цей звіт написав runner, не агент: жодної роботи тут не було, лише ваша відповідь.\n",
        encoding="utf-8")
    return target


def _setting(root: Path, key: str) -> str:
    """The value of one key of `.claude/project.env`; empty when the key is not there."""
    found = re.search(rf'^{key}="?([^"\n]*)"?\s*$', _text(root / ".claude/project.env"), re.MULTILINE)
    return found.group(1).strip() if found else ""


def _every(root: Path, key: str, default: int) -> int:
    """How often, in days, the runner places a task of its own: the key of `.claude/project.env`, else the default."""
    raw = _setting(root, key)
    return int(raw) if raw.isdigit() else default


def task_file(tasks: Path, stem: str) -> Path | None:
    """Where the task `stem` lies now: its file in todo/, doing/, blocked/ or proposed/, or done/<stem>/task.md."""
    places = [tasks / column / f"{stem}.md" for column in ("todo", "doing", "blocked", PROPOSED)] + [tasks / "done" / stem / "task.md"]
    return next((p for p in places if p.is_file()), None)


def extra_sum(tasks: Path) -> tuple[float, float | None]:
    """(what the extra sessions of the last seven days cost, the project's cap or None) — A TASK WITH EXTRA SESSIONS."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import board_state  # here, not at the top: board_state books through this module

    def marked(stem: str) -> bool:
        path = task_file(tasks, stem)
        try:
            return path is not None and read(path).extra
        except (OSError, UnicodeDecodeError):
            return False

    raw = _setting(tasks.parent, EXTRA_KEY)
    cap = float(raw) if re.fullmatch(r"\d+(?:\.\d+)?", raw) else None
    state = Path(os.environ.get("BOARD_STATE_DIR") or tasks.parent / ".claude" / "state" / "board")
    return board_state.extra_week(state, marked), cap


def extra_words(spent: float, cap: float | None) -> str:
    return (f"додаткові сесії Claude за сім днів: {spent:.2f} USD"
            + (" (межі немає)" if cap is None else f" із {cap:.2f} USD (`{EXTRA_KEY}` у `.claude/project.env`)"))


def extra_refusal(tasks: Path) -> str | None:
    """Why no new extra session may start and no task with extra sessions is taken; None under the cap or with none."""
    spent, cap = extra_sum(tasks)
    if cap is None or spent < cap:
        return None
    return f"межу вичерпано — {extra_words(spent, cap)}; нова сесія і задачі з додатковими сесіями чекають, доки сума не спаде"


def extra_wait(board: Board) -> Path | str:
    """This session's task goes from doing/ back to todo/, marked, to wait for the weekly sum; a
    string — why not."""
    doing = own(board.tasks)
    if len(doing) != 1:
        return "tasks/doing/ holds no task of this session (or more than one)"
    if not extra_refusal(board.tasks):
        return "the weekly sum is under its cap — " + extra_words(*extra_sum(board.tasks)) + "; the task goes on"
    text = doing[0].read_text(encoding="utf-8")
    if not read(doing[0]).extra:
        heading = HEADING.search(text)
        head, rest = (text[: heading.start()], text[heading.start():]) if heading else (text, "")
        text = head.rstrip("\n") + f"\n{EXTRA_LINE}\n" + ("\n" + rest if rest else "")
    target = board.tasks / "todo" / doing[0].name
    target.write_text(text, encoding="utf-8")
    doing[0].unlink()
    return target


def _due(board: Board, name: re.Pattern[str], today: date, every: int) -> bool:
    """None of the runner's own tasks of this kind is open, and the newest one is `every` days old."""
    found = {c: [m.group(1) for p in (board.tasks / c).glob("*") if (m := name.match(p.name))] for c in COLUMNS}
    if found["todo"] or found["doing"] or found["blocked"]:
        return False
    return not found["done"] or (today - date.fromisoformat(max(found["done"]))).days >= every


def _own_number(board: Board) -> int:
    """The next number for a task the runner places itself: the next one of its class (board 401)."""
    return task_classes.next_number(board.taken(), task_classes.OWN)


def maintain_task(board: Board, root: Path, today: date) -> Path | None:
    """Put the weekly maintenance task into todo/ when it is due (THE MAINTENANCE TASK); None — not now."""
    every = _every(root, "MAINTAIN_EVERY_DAYS", MAINTAIN_DAYS)
    if every == 0 or not (root / MAINTAIN_COMMAND).is_file() or not _due(board, MAINTAIN_NAME, today, every):
        return None
    number = _own_number(board)
    path = board.tasks / "todo" / f"{number:03d}-maintain-{today.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""# {number:03d} — Регулярний догляд {today.isoformat()}

Залежить від: —
Потрібна присутність власника: ні
Аудит потрібен: ні

Цю задачу поклав runner: догляд — раз на {every} днів, якщо попередній уже закрито.

## Що зробити
Виконай `/maintain` (`.claude/commands/maintain.md`): звіт `.engine/maintain/{today.isoformat()}.md` — залежності,
складність проти минулого звіту, гарячі місця, знімок «як було», борги термінових виправлень,
черга уроків, пропозиції задач. Нічого не видаляй, не впорядковуй і не оновлюй.

## Готово, коли
- Звіт догляду написано, і в `report.md` — його головне для власника.
- Якщо є що оновити — задача в `blocked/` з питанням «Оновити ці N залежностей?» і рядком дії.

## Питання до власника
""", encoding="utf-8")
    return path


def architect_task(board: Board, root: Path) -> Path | None:
    """Put the architecture task into todo/ after the first seal in a new project (THE ARCHITECTURE TASK); None — not now."""
    import goals  # the hooks' directory is on the path (above)

    if goals.state(root) != "sealed" or goals.architecture_begun(root):
        return None
    if any(ARCHITECT_NAME.match(p.name) for column in COLUMNS for p in (board.tasks / column).glob("*")):
        return None
    number = _own_number(board)
    path = board.tasks / "todo" / f"{number:03d}-master-architect.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""# {number:03d} — Архітектура проєкту за запечатаними цілями

Залежить від: —
Потрібна присутність власника: так
Аудит потрібен: ні

Цю задачу поклав runner: власник відповів «так» на документ цілей (`seal-goals`), документ
запечатано, а архітектури в проєкті ще немає (задача 205). Без присутності власника її не беруть:
`/master-architect` спиняється у власника вже на першому кроці, «Читання цілей».

## Що зробити
Виконай `/master-architect` (`.claude/commands/master-architect.md`) разом із власником, від M1, крок 1 —
зупинки «Читання цілей». Автоматичний лише старт: кожне однобічне рішення, кінець кожного етапу
й читання цілей затверджує власник (constitution, Art. 5).

## Готово, коли
- Матриця `.engine/architecture/traceability.md` і карти етапів, які власник затвердив у розмові.
- У `report.md` — що затверджено і що лишилось на наступну сесію з власником.

## Питання до власника
""", encoding="utf-8")
    return path


def cleanup_task(board: Board, root: Path, today: date) -> Path | None:
    """Put the cleanup task into todo/ when the board is idle and it is due (THE CLEANUP TASK); None — not now."""
    every = _every(root, "CLEANUP_EVERY_DAYS", CLEANUP_DAYS)
    if every == 0 or not (root / CLEANUP_SCRIPT).is_file() or not _due(board, CLEANUP_NAME, today, every):
        return None
    if board.files("doing") or board.eligible() is not None:   # the owner's attended task too (board 723, the owner's answer)
        return None
    if board.gate_hold():   # an escalation that covers all work would refuse its units too (board 301)
        return None
    if extra_refusal(board.tasks):   # a simplifier pass is extra sessions: it waits for the weekly sum (board 110)
        return None
    number, often = _own_number(board), "раз на добу" if every == 1 else f"раз на {every} діб"
    path = board.tasks / "todo" / f"{number:03d}-cleanup-{today.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""# {number:03d} — Прибирання {today.isoformat()}

Залежить від: —
Потрібна присутність власника: ні
Аудит потрібен: ні
{EXTRA_LINE}

Цю задачу поклав runner: йому не було чого брати, а вільний час іде на боротьбу зі
складністю — не частіше ніж {often}.

## Що зробити
1. Запусти `python3 {CLEANUP_SCRIPT} nightly` і збережи його вивід для звіту.
2. Якщо у виводі є `SIMPLIFIER CALL:` — зроби один прохід simplifier-а, як написано в
   `.claude/references/simplifier.md` («One run»): запит `request --lens code`, агент `simplifier`,
   `validate`, друга думка (якщо ввімкнена), `route --title "code, nightly {today.isoformat()}"`.
   Якщо там `no sharp growth` — simplifier-а не запускай: на сьогодні це все.
3. Безпечне застосуй: знахідку `auto_remove` прибирай лише за всіх трьох умов із того самого
   документа («What happens to a finding») — по одній на commit, із рядком `Simplifier-Finding: <id>`.
   Бракує хоч однієї умови — не прибирай: це питання для власника.
4. Решту (`confirm`, `flag_only`) не чіпай: `route` уже записав її в `.engine/simplifier/report.md`
   для огляду власника.

## Готово, коли
- У `report.md`: вивід нічного режиму, що прибрано (commit-и) і що чекає огляду власника.
- Якщо щось прибрано — повний набір тестів зелений.

## Питання до власника
""", encoding="utf-8")
    return path


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def gate_reject(path: Path, word: str = CONSENT) -> None:
    """Wipe an answer that did not come from the owner and say so under the question."""
    lines = path.read_text(encoding="utf-8").splitlines()
    last = max(i for i, line in enumerate(lines) if ANSWER.match(line))
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines[last] = lines[last][: lines[last].index("Відповідь:")] + "Відповідь:"
    lines.insert(last, f"Примітка runner-а ({now}): відповідь «{word}» з'явилася на сервері, а не прийшла "
                       "через гілку чи inbox, тому її не прийнято. Дайте відповідь ще раз.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def audit_refusal(tasks: Path) -> str | None:
    """Why the overseer's audit run (evals/run_audit_scenarios.py) may NOT start for the work in
    hand; None when this session's task in doing/ says «Аудит потрібен: так» — the owner's own
    decision, kept apart from every other session of Claude (board 078). The other side's task
    beside it neither allows nor refuses anything."""
    doing = own(tasks)
    if not doing:
        return f"no task of this session is in {tasks}/doing/"
    if len(doing) > 1:
        return f"{tasks}/doing/ holds more than one task: " + ", ".join(p.name for p in doing)
    if not read(doing[0]).audit:
        return f"the task in doing/, {doing[0].name}, does not say «Аудит потрібен: так»"
    return None


def in_hand(tasks: Path) -> str:
    """The name (no .md) of this session's one task in doing/, for the books; empty with none or two."""
    doing = own(tasks) if tasks.is_dir() else []
    return doing[0].stem if len(doing) == 1 else ""


ANOMALIES_HEAD = journal.JOURNALS["anomalies"].head
RUNNER = "runner"  # who writes the journal unless told otherwise
WHY = "## Чому зупинилась"
# reason → (what happened, the question). {n} is the runner's number: attempts, dollars.
# No reason is about time (board 404): an old `deadline` record in a task or the journal is plain text and stays readable.
PARK_REASONS = {
    "no-commit": ("{n} спроб(и) поспіль не дали жодного commit-а",
                  ("Задача застрягла: агент кілька спроб поспіль нічого не закомітив. Що робити далі? Будь-яка відповідь поверне задачу "
                  "в чергу з новим лічильником спроб; вказівку агентові напишіть тут же.")),
    "budget": ("спрацював запобіжник runner-а від зациклення (`BOARD_MAX_USD`): задача витратила {n} USD",
               ("Задача дійшла до запобіжника від зациклення (`BOARD_MAX_USD`). Це не межа ціни: роботу не обрізано, її зупинено з "
               "питанням. Продовжити? Будь-яка відповідь поверне задачу в чергу й дасть їй ще стільки ж; якщо продовжувати не треба — "
               "не відповідайте або приберіть задачу.")),
    "three-blocks": ("overseer тричі поспіль відхилив один юніт ({n})",
                     ("Три overseer-и поспіль відхилили юніт цієї задачі; їхні вердикти — у розділі «Чому зупинилась». Що робити далі? "
                     "Будь-яка відповідь поверне задачу в чергу, і юніт отримає три нові спроби; вказівку агентові напишіть тут же.")),
    "returned": ("агент повернув задачу з `doing/` у `todo/`, не закінчивши її і нічого не спитавши",
                 ("Агент не закінчив задачу й не поставив питання. Що робити далі? Будь-яка відповідь поверне задачу в чергу; "
                 "вказівку агентові напишіть тут же.")),
    "reader-blocks": ("агент-читач тричі поспіль відхилив запис задачі ({n})",
                      ("Три агенти-читачі поспіль відхилили цей запис: запис ескізу — бо вивід у ньому не доводить його відповідь, звіт "
                      "задачі без робочого коду — бо в документах є хибне посилання, пункт без відповіді, питання без варіантів чи "
                      "перекладений термін; їхні вердикти — у розділі «Чому зупинилась». Що робити далі? Будь-яка відповідь поверне "
                      "задачу в чергу, і запис отримає три нові читання; вказівку агентові напишіть тут же.")),
    "protected": ("сесія агента змінила охоронювані файли ({n}), і gates цього не зупинили; runner повернув їх до стану перед сесією",
                  ("Сесія агента змінила охоронюваний файл (constitution, settings, `.engine/rules.md`, migrations, CI workflows). Runner "
                  "повернув файл до стану перед сесією; відкинуту зміну збережено латкою в `.claude/state/gate/protected/discarded/` "
                  "(на сервері runner-а), подія — в журналі аномалій. Що робити далі? Будь-яка відповідь поверне задачу в чергу; "
                  "вказівку агентові напишіть тут же. Якщо зміна потрібна — це пропозиція (`docs/tasks/settings.json`) і ваше «так».")),
    "minimum": ("задачу закрито без мінімуму її режиму, і після одного ходу назад його так і не було ({n})",
                ("Задачу закрито без мінімуму її режиму (board 098: `mode.py check-close`), і хід назад агентові цього не виправив. "
                "Що робити далі? Будь-яка відповідь поверне задачу в чергу; вказівку агентові напишіть тут же.")),
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def anomaly(board: Board, task: str, what: str, done: str, source: str = RUNNER) -> Path:
    """One entry of the anomaly journal, in this session's own file of it (board 739: tasks/ANOMALIES.md is
    what a fold gathered; `journal.py show anomalies` reads it whole). The path written."""
    what, done, source = (" ".join(part.split()) for part in (what, done, source or RUNNER))
    entry = (f"## {utc_now()} — {task if task and task != '-' else 'task board'}\n- Що сталося: {what}\n- Що зроблено: {done}\n"
             f"- Хто записав: {source}\n")
    return journal.add(board.tasks.parent, "anomalies", entry)


def note(root: Path, source: str, what: str, done: str) -> Path | None:
    """The journal entry of a hook or of the gate (board 035): filed under this session's task in
    doing/, else under the board. None when the project has no board. The runner commits it."""
    board = Board(root / "tasks")
    if not board.tasks.is_dir():
        return None
    doing = own(board.tasks)
    return anomaly(board, doing[0].stem if len(doing) == 1 else "-", what, done, source)


def blocks_of(marker: Path | None) -> tuple[str, list[str]]:
    """The unit and the overseers' verdicts from the marker the Stop hook left (overseer_stop.py,
    board 031), as lines for the task file. Nothing when there is no readable marker."""
    try:
        data = json.loads(marker.read_text(encoding="utf-8")) if marker else {}
    except (OSError, ValueError):
        data = {}
    blocks = [row for row in data.get("blocks", []) if isinstance(row, dict)] if isinstance(data, dict) else []
    lines = [f"  - BLOCK {n} ({row.get('utc') or 'час невідомий'}, запит `{row.get('request')}`"
             + (f", перевірка #{row['check']}" if row.get("check") else "") + f"): {' '.join(str(row.get('reason', '')).split())}"
             for n, row in enumerate(blocks, 1)]
    return (str(data.get("unit", "")) if isinstance(data, dict) else ""), lines


def saved_work(stash: str, wip: str, remote: str) -> str:
    """Where the runner put the agent's uncommitted work, with the command that brings it back."""
    if not (stash or wip):
        return ""
    parts = []
    if wip and remote:
        parts.append(f"у гілці `{wip}` в {remote} (повернути в робоче дерево: `git fetch {remote} {wip} && git cherry-pick -n FETCH_HEAD`)")
    elif wip:
        parts.append(f"у гілці `{wip}` — лише на сервері runner-а, надіслати її не вдалося (надіслати: `git push origin {wip}`)")
    if stash:
        parts.append(f"у сховку git на сервері runner-а (`git stash apply {stash}`)")
    return " Незакомічену роботу агента runner зберіг " + " і ".join(parts) + "."


def park(board: Board, stem: str, reason: str, detail: str, stash: str, verdicts: Path | None = None,
         wip: str = "", remote: str = "") -> Path | None:
    """The runner gives up on a task: doing/ (or todo/) → blocked/, with the reason, a question
    for the owner and an entry in the anomaly journal. None when the task is in neither.
    `verdicts` (reason three-blocks) is the hook's marker: its verdicts are written under the reason.
    A task closed into done/ without the minimum of its mode (reason minimum, board 098) comes back
    from done/<stem>/: task.md goes to blocked/, its report beside it as blocked/report-<stem>.md.
    So does a report written into done/<stem>/ ahead of the move, for its reader (board 100)."""
    stem = stem.removesuffix(".md")
    source = next((p for c in ("doing", "todo") for p in [board.tasks / c / f"{stem}.md"] if p.is_file()), None)
    closed = board.tasks / "done" / stem
    if source is None and reason == "minimum" and (closed / "task.md").is_file():
        source = closed / "task.md"
    if source is None:
        return None
    unit, refused = blocks_of(verdicts)
    what, question = (part.format(n=unit or detail) for part in PARK_REASONS[reason])
    saved = saved_work(stash, wip, remote)
    line = "\n".join([f"- {utc_now()} — {what}; runner переніс задачу в `blocked/` і взяв наступну.{saved}", *refused])
    text = source.read_text(encoding="utf-8").rstrip("\n") + "\n"
    if not QUESTIONS.search(text):
        text += "\n## Питання до власника\n"
    start = QUESTIONS.search(text)
    assert start is not None
    head, tail = text[: start.start()], text[start.start():]
    if re.search(rf"^{re.escape(WHY)}\s*$", head, re.MULTILINE):
        head = head.rstrip("\n") + "\n" + line + "\n\n"
    else:
        head = head.rstrip("\n") + f"\n\n{WHY}\n{line}\n\n"
    number = len(ANSWER.findall(parse(text).questions)) + 1
    tail = tail.rstrip("\n") + f"\n{number}. {question}\n   Відповідь:\n"
    target = board.tasks / "blocked" / f"{stem}.md"   # from done/<stem>/ the file is task.md
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(head + tail, encoding="utf-8")
    source.unlink()
    report = closed / "report.md"   # of a task closed without its minimum, or written ahead of the move for its reader (board 100)
    if report.is_file():
        report.replace(board.tasks / "blocked" / f"report-{stem}.md")
    if closed.is_dir() and not any(closed.iterdir()):
        closed.rmdir()
    anomaly(board, stem, what + ".", "задачу перенесено в `blocked/` з розділом «Чому зупинилась» і питанням до власника; "
            "runner узяв наступну задачу." + saved)
    return target


def first_open_question(task: Task) -> str:
    """The text of the first question whose answer is empty, for the summary."""
    lines = task.questions.splitlines()
    for index, line in enumerate(lines):
        answer = ANSWER.match(line)
        if answer and not answer.group(1).strip():
            asked = [text.strip() for text in lines[:index] if text.strip() and not ANSWER.match(text) and not ACTION.match(text)]
            return asked[-1] if asked else "(питання без тексту)"
    return "(питань не записано)"


def title_of(path: Path) -> str:
    """A task file's title without its number, for one line of the summary."""
    found = re.search(r"^#[ \t]+(?:\d+[ \t]*[—–-][ \t]*)?(\S.*?)[ \t]*$", _text(path), re.MULTILINE)
    return found.group(1) if found else "(без назви)"


def summary(board: Board) -> list[str]:
    todo, doing, blocked, done = board.files("todo"), board.files("doing"), board.files("blocked"), board.done()
    known = {n for column in COLUMNS for n in board.numbers(column)}
    offered = board.files(PROPOSED)
    lines = [f"todo: {len(todo)}   doing: {len(doing)}   blocked: {len(blocked)}   done: {len(done)}   {PROPOSED}: {len(offered)}", *errors(board)]
    lines += [f"в роботі з власником: {p.name}" if read(p).attended else f"в роботі: {p.name}" for p in doing]
    for path in blocked:
        lines.append(f"чекає відповіді власника: {path.name} — {first_open_question(read(path))}")
    held = extra_refusal(board.tasks)
    whole = board.gate_hold()
    if whole:
        lines.append(f"ескалація gates {whole} накриває всю роботу: поки власник її не закрив, overseer не приймає жодного PASS — "
                     "нові задачі не беруться (питання gates — у `blocked/`)")
    for path in todo:
        waiting = read(path)
        stamp = None if whole else board.gate_hold(path)
        if stamp:
            lines.append(f"чекає, поки власник закриє ескалацію gates {stamp}: {path.name} — доти overseer не прийме її PASS")
        if waiting.attended:
            lines.append(f"чекає на присутність власника: {path.name} — лише в інтерактивній сесії з власником")
        if board.held_cleanup(path):
            lines.append(f"чекає, поки закриється задача з присутнім власником: {path.name}")
        if waiting.mode_error:
            lines.append(f"не береться: {path.name} — {waiting.mode_error}")
        if waiting.extra:
            lines.append(f"з додатковими сесіями: {path.name} — " + (f"чекає: {held}" if held else "після звичайних задач"))
        unmet = board.unmet(waiting)
        if unmet:
            waits = ", ".join(f"{n:03d}" + ("" if n in known else " (такої задачі ніде немає)") for n in unmet)
            lines.append(f"чекає на залежності: {path.name} — {waits}")
    lines += [f"першою, бо власник відповів: {p.name}" for p in todo if p.name in board.first()]
    if offered:
        lines.append(f"пропозицій у `{PROPOSED}/`: {len(offered)} — runner їх не бере; у роботу пропозицію ставить власник: файл із її номером в inbox")
        lines += [f"пропозиція: {p.name} — {title_of(p)}" for p in offered]
    task = board.eligible() if not board.in_hand() else None
    if task:
        lines.append(f"наступна: {task.name}")
    spent, cap = extra_sum(board.tasks)
    if cap is not None:
        lines.append(extra_words(spent, cap))
    return lines


def cmd_review(root: Path, args: argparse.Namespace) -> int:
    import board_review  # here, not at the top: board_review reads this module's parser

    try:
        document = board_review.review(root, args.state_dir or root / ".claude/state", args.remote, args.branch,
                                       args.since, args.offline, datetime.now(UTC))
    except board_review.ReviewError as refusal:
        print(f"board: review: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    sys.stdout.write(document)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The task board in files (tasks/README.md).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="the repository that holds tasks/ (default: the one this file is in)")
    commands = parser.add_subparsers(dest="command", required=True)
    next_parser = commands.add_parser("next")
    next_parser.add_argument("--attended", action="store_true", help="the owner is present: offer the tasks that need them")
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--attended", action="store_true", help="the owner is present: a task that needs them may start")
    start_parser.add_argument("task")
    commands.add_parser("where").add_argument("name")
    commands.add_parser("import-inbox").add_argument("inbox", type=Path)
    commands.add_parser("unblock")
    for name in ("reviewed-reject", "reviewed-accept", "reviewed-clean"):
        reviewed_parser = commands.add_parser(name)
        reviewed_parser.add_argument("--accepted", type=Path, required=True, help="the runner's record of the numbers that arrived from the owner")
        reviewed_parser.add_argument("--known", default="", help="with no record yet: the revision whose tasks/.reviewed counts as arrived")
    commands.add_parser("audit-allowed").add_argument("--tasks-dir", type=Path, default=None)
    commands.add_parser("extra-allowed")
    book_parser = commands.add_parser("extra-book")
    book_parser.add_argument("tool", help="what started the session: a script's name, `claude -p`")
    book_parser.add_argument("usd", type=float, help="what the session reported it cost")
    commands.add_parser("extra-wait")
    commands.add_parser("extra-waits").add_argument("name")
    commands.add_parser("gate-hold")
    commands.add_parser("gate-answers")
    gate_done_parser = commands.add_parser("gate-done")
    gate_done_parser.add_argument("name")
    gate_done_parser.add_argument("outcome", choices=("closed", "absent", "elsewhere"))
    commands.add_parser("gate-closed")
    commands.add_parser("gate-reject").add_argument("name")
    commands.add_parser("owner-actions")
    commands.add_parser("action-line").add_argument("action", choices=sorted(ACTION_FILES))
    commands.add_parser("architect-task")
    commands.add_parser("maintain-task").add_argument("--today", default=os.environ.get("BOARD_TODAY") or None, help="YYYY-MM-DD (default: today, UTC)")
    commands.add_parser("cleanup-task").add_argument("--today", default=os.environ.get("BOARD_TODAY") or None, help="YYYY-MM-DD (default: today, UTC)")
    action_done_parser = commands.add_parser("action-done")
    action_done_parser.add_argument("name")
    action_done_parser.add_argument("outcome", choices=sorted(ACTION_OUTCOMES))
    commands.add_parser("action-reject").add_argument("name")
    park_parser = commands.add_parser("park")
    park_parser.add_argument("name")
    park_parser.add_argument("reason", choices=sorted(PARK_REASONS))
    park_parser.add_argument("--detail", default="", help="the runner's number: attempts, hours or dollars")
    park_parser.add_argument("--stash", default="", help="the stash commit that holds the agent's uncommitted work")
    park_parser.add_argument("--wip", default="", help="the branch that holds the agent's uncommitted work as one commit")
    park_parser.add_argument("--wip-remote", default="", help="the remote the branch was pushed to; empty: it is on this machine only")
    park_parser.add_argument("--verdicts", type=Path, default=None, help="three-blocks: the marker the Stop hook left, with the overseers' verdicts")
    anomaly_parser = commands.add_parser("anomaly")
    anomaly_parser.add_argument("task")
    anomaly_parser.add_argument("what")
    anomaly_parser.add_argument("done")
    anomaly_parser.add_argument("--source", default=RUNNER, help="who writes: runner (default), агент, gates, hook <name>")
    item_parser = commands.add_parser("open-item")
    item_parser.add_argument("--to", choices=("blocked", PROPOSED, "todo", "done"), required=True,
                             help="blocked: the owner must answer; proposed (todo is its old name): work an agent could do — a proposal the owner puts to work; done: settled already")
    item_parser.add_argument("--title", required=True)
    item_parser.add_argument("--what", required=True, help="what happened and what it waits for")
    item_parser.add_argument("--question", default="", help="the one question to the owner (required with --to blocked)")
    item_parser.add_argument("--do", default="", help="proposed: what to do; done: why it is settled (the report)")
    item_parser.add_argument("--key", default="", help="the item's own name: a second call with it returns the task still open")
    item_parser.add_argument("--source", default="агент", help="who writes: агент (default), hook <name>, overseer")
    commands.add_parser("summary")
    commands.add_parser("check")
    review_parser = commands.add_parser("review")
    review_parser.add_argument("--since", default=None, help="a commit or a date; default: the newest version tag")
    review_parser.add_argument("--offline", action="store_true", help="do not ask origin; show the state this clone saw last")
    review_parser.add_argument("--remote", default=os.environ.get("BOARD_REMOTE", "origin"))
    review_parser.add_argument("--branch", default=os.environ.get("BOARD_BRANCH", "unattended/work"))
    review_parser.add_argument("--state-dir", type=Path, default=None, help="the runner's state (default: .claude/state)")
    args = parser.parse_args()
    root: Path = args.root.resolve()
    if args.command == "review":
        return cmd_review(root, args)
    board = Board(root / "tasks")
    if args.command in ("next", "start") and args.attended:
        refusal = attended_refusal(root)
        if refusal:
            print(f"board: {refusal}", file=sys.stderr)
            return EXIT_REFUSED
    if args.command == "next":
        return cmd_next(board, args.attended)
    if args.command == "start":
        return cmd_start(board, root, args.task, args.attended)
    if args.command == "where":
        return cmd_where(board, args.name)
    if args.command == "reviewed-reject":
        removed = reviewed_reject(board, args.accepted, args.known)
        if removed:
            print(" ".join(removed))
        return 0
    if args.command == "reviewed-clean":
        return 0 if reviewed_clean(root, args.accepted, args.known) else EXIT_REFUSED
    if args.command == "reviewed-accept":
        args.accepted.parent.mkdir(parents=True, exist_ok=True)
        args.accepted.write_text("".join(f"{n:03d}\n" for n in reviewed_numbers(_reviewed_text(board.tasks / REVIEWED))), encoding="utf-8")
        return 0
    if args.command == "import-inbox":
        for line in import_inbox(board, args.inbox):
            print(line)
        return 0
    if args.command == "unblock":
        for name in unblock(board):
            print(name)
        return 0
    if args.command == "gate-answers":
        for line in gate_answers(board):
            print(line)
        return 0
    if args.command == "gate-closed":
        for line in gate_closed(board, root):
            print(line)
        return 0
    if args.command in ("gate-done", "gate-reject"):
        path = gate_task(board, args.name)
        if path is None:
            print(f"board: {args.name} is not a gate question in tasks/blocked/", file=sys.stderr)
            return EXIT_REFUSED
        if args.command == "gate-done":
            print(board.shown(gate_done(board, path, args.outcome)))
        else:
            gate_reject(path)
        return 0
    if args.command == "owner-actions":
        for line in owner_actions(board):
            print(line)
        return 0
    if args.command == "action-line":
        if not (root / ACTION_FILES[args.action]).is_file():
            print(f"board: {ACTION_FILES[args.action]} is missing; there is nothing to offer", file=sys.stderr)
            return EXIT_REFUSED
        print(action_line(root, args.action))
        return 0
    if args.command == "architect-task":
        placed = architect_task(board, root)
        if placed:
            print(board.shown(placed))
        return 0
    if args.command in ("maintain-task", "cleanup-task"):
        place = maintain_task if args.command == "maintain-task" else cleanup_task
        placed = place(board, root, date.fromisoformat(args.today) if args.today else datetime.now(UTC).date())
        if placed:
            print(board.shown(placed))
        return 0
    if args.command in ("action-done", "action-reject"):
        path = action_task(board, args.name)
        if path is None:
            print(f"board: {args.name} offers no action in tasks/blocked/", file=sys.stderr)
            return EXIT_REFUSED
        if args.command == "action-done":
            print(board.shown(action_done(board, path, args.outcome)))
        else:
            gate_reject(path, RULE_NO if read(path).declines else CONSENT)
        return 0
    if args.command == "park":
        parked = park(board, args.name, args.reason, args.detail, args.stash, args.verdicts, args.wip, args.wip_remote)
        if parked is None:
            print(f"board: {args.name} is in neither tasks/doing/ nor tasks/todo/ (nor, for `minimum`, tasks/done/)", file=sys.stderr)
            return EXIT_REFUSED
        print(board.shown(parked))
        return 0
    if args.command == "open-item":
        item = open_item(board, args.to, args.title, args.what, args.question, args.do, args.key, args.source)
        if item is None:
            print("no task written: the project has no tasks/ directory, the title is empty, or --to blocked came without --question", file=sys.stderr)
            return 1
        print(board.shown(item))
        return 0
    if args.command == "anomaly":
        print(board.shown(anomaly(board, args.task, args.what, args.done, args.source)))
        return 0
    if args.command == "audit-allowed":
        refusal = audit_refusal(Path(os.path.realpath(args.tasks_dir)) if args.tasks_dir else board.tasks)  # not resolve(): RuntimeError on a symlink loop up to Python 3.12
        if refusal:
            print(f"paid audit not allowed: {refusal}")
            return 1
        return 0
    if args.command == "extra-allowed":
        refusal = extra_refusal(board.tasks)
        print(refusal or extra_words(*extra_sum(board.tasks)))
        return 1 if refusal else 0
    if args.command == "extra-book":
        import board_state  # the script's own directory is on the path here

        board_state.book_extra(board.tasks, args.tool, args.usd)
        return 0
    if args.command == "extra-wait":
        waits = extra_wait(board)
        if isinstance(waits, str):
            print(f"board: extra-wait: {waits}", file=sys.stderr)
            return EXIT_REFUSED
        print(board.shown(waits))
        return 0
    if args.command == "gate-hold":
        print(board.gate_hold() or "", end="\n" if board.gate_hold() else "")
        return 0
    if args.command == "extra-waits":
        waiting = board.tasks / "todo" / f"{args.name.removesuffix('.md')}.md"
        return 0 if waiting.is_file() and read(waiting).extra and extra_refusal(board.tasks) else 1
    if args.command == "check":
        found = errors(board)
        print("\n".join(found), end="\n" if found else "")
        return 1 if found else 0
    print("\n".join(summary(board)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
