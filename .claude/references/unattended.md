# Unattended work — the detail behind the rules

Read this when `.claude/state/overseer/mode` says `unattended`, when the board runner started
the session, or when you must park an item. The rules themselves are in
`.claude/engine-rules.md`; the runner's own documentation is `.claude/unattended/README.md`,
the board's manual `tasks/README.md`.

## The mode file

`.claude/state/overseer/mode` with the content `unattended` declares that nobody is in the
loop. Absent, or any other content, means attended — the default, so an interactive session
behaves exactly as before and a server run opts in explicitly
(`echo unattended > .claude/state/overseer/mode`).

What the mode changes, and only this: an interactive hard gate in `/plan-slice` or
`/feature-architect` becomes a park. The item waits, work continues elsewhere, and the gate is
surfaced at the next legitimate interruption. What it does **not** change — these hold in both
modes: the slice-builder cadence (one gate on the behavior list, then run the list through);
verdict routing (resolvable findings are fixed and logged, not escalated); the three reasons to
stop; Article 5 — a genuine one-way door (money, a real external system, irreversible data, a
published contract) parks and waits in **both** modes.

## Parking an item

Everything that can be open is a file of the task board, and it is closed the way every task is:
by moving to `tasks/done/`. To park an item, put it there:

```bash
python3 .claude/unattended/board.py open-item --to blocked --title "<the item, in a line>" \
    --what "<what happened, the exact thing needed, the evidence>" --question "<what you ask the owner>"
```

`--to blocked` is a question for the owner (`7NN-open-item-….md` with an empty `Відповідь:`; any
answer returns it to `todo/` as an instruction); `--to proposed` is work an agent could do later
(`--do` says what) — a proposal in `tasks/proposed/`, which the runner never takes and only the owner
puts to work (a file with its number in the inbox; board 111; `--to todo` is the old name and lands there too); `--key <item id>` names the item, so a second call returns the task still
open instead of writing another. If the item is your own board task, ask in that task and move
it to `tasks/blocked/` instead (`tasks/README.md`, rule 4).

For an ask-gated command: the exact command in `--what`, and the question is whether the owner
runs it. `park-ask-gated.py` denies such a command unattended and hands you this instruction if
you forget. A push is not one of them: the runner sends the branch itself, and the hook refuses
a push of the session's own, anywhere in the command (board 603).

`.engine/overseer/parked.md` and `.engine/overseer/escalations.md` are history. They are only
appended to (since board 739 a script's parked entry goes into the session's own file `.engine/journal/parked/`) — an AUTONOMOUS decision, closed by being logged, still goes to `escalations.md`;
a project without `tasks/` parks in `parked.md` — nothing in them is ever marked closed, and
nothing reads them to learn what is open: the owner's review shows `tasks/blocked/`.

Surface what is parked to the human when, and only when: nothing in the unblocked queue
can move; a single item is parked on a one-way door; three or more items are parked awaiting
ratification (the contract is systematically under-specified); or a premise in
`.engine/premises/premise-log.md` flips to `falsified` and committed work depends on it.

## Unattended work is the task board

There is one way to work with nobody watching: the task board. `.claude/unattended/board-runner.sh`
takes the tasks in `tasks/todo/` one at a time and starts a fresh session for each, with the mode
file saying `unattended` and `CLAUDE_UNATTENDED_SESSION=1` in the environment. Such a session
follows the «Правила для агента» of `tasks/README.md`: it ends with its task in `tasks/done/`
(with `report.md`) or in `tasks/blocked/` (with questions for the owner), committed through
`.claude/unattended/commit_checkpoint.sh`. A session that ends with the task still in
`tasks/doing/` is continued by the runner; one that cannot move is parked by the runner, never
by waiting. The feature DAG (`.engine/architecture/feature-dag.json`) is a plan `/feature-architect`
writes and follows inside a task — nothing executes it by itself.

## The owner's two rules (board 053)

**Quality over price.** Quality is the base of the system, not price. A task carries no dollar
limit: extra Claude sessions — evals, measurements, the critics' and the simplifier's checks — take
what an honest result needs, and since board 078 they need no leave: they are ordinary work, like a
test. A «Платні прогони:» line in an old task is ignored. Every such session is booked to the task in
hand (`.claude/state/board/extra-sessions.jsonl`), and the runner's summary and the review show how
many each task started and what they cost. One decision stays the owner's: the overseer's audit run
(`run_audit_scenarios.py`) needs `Аудит потрібен: так` in the task, or `--owner-approved` by hand outside
a session. Since board 110 such work has its place and its weekly sum: a task that says
`Додаткові сесії: так` is taken only when no ordinary task can start, and the extra sessions of all
tasks over the last seven days — every session booked to a task, plus the own sessions of the marked
tasks — stay under `EXTRA_SESSIONS_WEEK_USD` of `.claude/project.env` (no key: no cap). At the cap
the eval runners start no new session and marked tasks wait in `tasks/todo/`; a task that meets it
mid-work commits what is done and runs `board.py extra-wait` — it is not parked and nobody is asked
(`board.py`, A TASK WITH EXTRA SESSIONS). Only the runner's per-task
guard (`BOARD_MAX_USD`) stands against a loop: it does not cut the work, it parks the task with a
question, and the owner's answer continues it with the same budget again. Where something
proves too long or too dear — measure first, then simplify in a task of its own.

**Technical terms in English, wherever the owner reads** — a report's «Що змінилось для власника»,
a question in `blocked/`, the review, whatever a script writes for the owner. The terms as
practitioners use them: overseer, simplifier, critic, planner, builder, tester, test manager,
business analyst, slice, slice contract, gates, hook, runner, task board, inbox, audit, golden
set, invariant, property-based testing, mutation testing, spike, sandbox, and the like. In a
Ukrainian sentence the term keeps its English form and takes a hyphenated ending when it must
(`runner-а`, `slice-ів`, `audit-у`). A rare term may get a short Ukrainian gloss; the term itself
stays English. No invented Ukrainian translations («наглядач», «ворота», «зріз», «виконавець»…).
The lines the board reads — `Аудит потрібен:`, `Відповідь:` — are written as they are.
