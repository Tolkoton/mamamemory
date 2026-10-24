# Unattended operation

Unattended work has one way in: the task board. The owner puts tasks as files into `tasks/`
(manual: `tasks/README.md`); `board-runner.sh` takes them one at a time, each in a fresh
conversation, and stops with a summary when nothing can move. There is no other loop: the
supervisor that executed a feature DAG node by node was retired by board 039, and the feature
DAG (`.engine/architecture/feature-dag.json`) is only what `/feature-architect` plans a feature
into.

Why the commit policy, the deny hook and the patch screen are the way they are:
[`unattended-decisions.md`](unattended-decisions.md).

## The board runner

```bash
bash .claude/unattended/board-runner.sh            # until nothing can move, then stop with a summary
bash .claude/unattended/board-runner.sh --once     # one task
bash .claude/unattended/board-runner.sh --status   # the status line and the board; runs nothing
bash .claude/unattended/board-runner.sh --stop-after-task      # stop a working runner once its task is closed
bash .claude/unattended/board-runner.sh --stop-after-attempt   # …or once the attempt in hand has ended
```

To stop a runner, never kill it — the agent loses the uncommitted work of its task. `--stop-after-task`
puts the flag `.claude/state/board/stop-after-task`; the runner looks at it between tasks, so the
current task is finished and pushed, then the runner stops with `state=stopped
reason=stop-after-task` and removes the flag. `--stop-after-attempt` is the quicker one: the flag
`stop-after-attempt` is looked at before and after every attempt, so the session in hand ends by
itself, what it committed is pushed, and the runner stops with `reason=stop-after-attempt`; the
task stays in `doing/` with its uncommitted work, its conversation, its clock and its count, and
the next start continues it (`--resume`). With no runner working either command sets nothing
and says so; a flag left by a runner that died is removed when the next one starts.

**Before the first start, trust the directory (board 791).** Open Claude Code in the project interactively once
and accept the trust dialog. Until then a headless session ignores the `allow` list of `.claude/settings.json`
and says so only in its stderr, `.claude/state/board/logs/<task>-<n>.json.err`. The task may pass all the same
(the sessions run with `--permission-mode auto`), so the runner reads that log after every session: the line
«this workspace has not been trusted» gives one entry in the anomaly journal — once a project, the marker is
`.claude/state/board/untrusted-workspace` — and a line «Увага: теку проєкту не позначено довіреною…» in
`summary.md` of every run in which a session said it. The work is not stopped.

Before every task it fetches and rebases the work branch (`unattended/work`), takes new files
from the inbox (`~/engine-ops/tasks-inbox/`, if it exists) into `tasks/todo/`, and returns
answered tasks from `tasks/blocked/`. It takes nothing from `tasks/proposed/` (board 111): what agents, hooks and
the overseer found waits there as proposals, and an inbox file with a proposal's number is the owner putting it to
work — it replaces the proposal and lands in `todo/`. An inbox file that comes without a number (`name.md`) and with a
`Клас:` line gets the next number of that class of `tasks/CLASSES.md` (board 401: a number is its class x 100
+ its place in the class; a full class goes on in the hundred a thousand higher, 799 -> 1701); a class the
table does not hold is a refusal — the file stays in the inbox, with an entry in the anomaly journal. A question the Stop gate put there after giving up
(`9NN-gate-escalation-*.md`) it commits and pushes at once; when the owner's answer `так`
arrives by the pull or the inbox, the runner itself runs `gate.py --close-escalation` and moves
that task to `done/` — no agent is started for it (`.claude/references/gate.md`). While a gate
escalation is open the runner does not spend a session on a task whose PASS it would refuse (board
301): the task whose turn the gate gave up on and a task whose own commits changed an escalated file
wait in `todo/` (`board.py summary` says for which escalation) while other tasks go on — their PASS is
accepted, and the escalated file stays unjudged; an escalation that names no file covers all work, so
the runner starts nothing, places no cleanup task and stops with `state=waiting-owner
reason=gate-escalation`, the stamp in `summary.md`. An action the
owner approved with `так` under a question that offers it (`Дія runner-а: apply-settings <sha256>`)
the runner takes itself, through `owner_action.py`, whose list is short: the settings
proposal is checked by `settings_check.py` (it ships with the engine, so this works in every
project), copied over `.claude/settings.json`, the project's own `tests/test_settings_proposal.py`
run when it keeps one, the file committed, and the task returned to `todo/` with the outcome in
place of the offer. `engine.py` gives a project its `docs/tasks/settings.json` as a copy of its
own live settings. An approved goals document is amended the same way (board 051): the offer
`Дія runner-а: amend-goals <sha256 of .engine/goals/proposed.md>`; on `так` the runner has `goals.py` check
that the proposal is a lawful amendment, put it in place of `.engine/goals.md`, seal it and list what cited a
changed line; the agent, when the task returns to it, commits the document. The first seal on a goals
document written with nobody in the conversation goes the same way (board 787): the offer
`Дія runner-а: seal-goals <sha256 of .engine/goals.md>` under a question that shows the whole document; on
`так` the runner has `goals.py` seal exactly that document — one that changed since the question is stale,
one already approved and changed is an amendment, not a first seal. In a new project (no traceability matrix,
no map) the runner then puts the architecture task into `todo/` itself, in a commit of its own (board 205,
`board.py architect-task`: `NNN-master-architect.md`, a task to run `/master-architect` with `Потрібна присутність
власника: так` — the architect stops for the owner at «Читання цілей», before any design); never after an
amendment, never while one lies in any column. A lesson
becomes a rule the same way and no other: the question `8NN-rule-proposal-*.md` carries the offer
`Дія runner-а: promote-rule <sha256>`; on the owner's `так` the runner has `lesson_queue.py` add
that exact text to `.engine/rules.md`, on `ні` it closes the proposal, commits, and moves the
question to `done/` with a short report — no agent is started. Dependencies are updated the
same way and no other (board 076): the question that ends a `/maintain` task carries the offer
`Дія runner-а: update-deps <sha256 of .engine/maintain/updates.json>`; on `так` `owner_action.py` checks
that the list is the one the owner saw, that the tree is clean and the full gate green, then runs the
project's `DEPS_UPDATE_CMD` — the patches as one group, every minor version alone, never a major one
— each followed by `gate.py --layer ci` and a commit of its own, or rolled back and written with its
output to `.engine/maintain/update-result.md`; the task then returns to the agent, which reports.
Once a week the runner puts the maintenance task into `todo/` itself (`board.py maintain-task`:
`NNN-maintain-<date>.md`, a task to run `/maintain`) — never while one waits in `todo/`, `doing/` or
`blocked/`, `MAINTAIN_EVERY_DAYS` in `project.env` (empty: 7, `0`: never). When nothing can be taken — `todo/` is
empty, or all that is left waits for the owner — it puts a cleanup task there instead of stopping
(`board.py cleanup-task`: `NNN-cleanup-<date>.md`, a task to run `simplifier.py nightly` and act by the
simplifier's rules), with an entry in the anomaly journal, in one commit — not more than once a day, never
while one waits in `todo/`, `doing/` or `blocked/`, never while any task lies in `doing/` (the owner's attended
one too, board 723), `CLEANUP_EVERY_DAYS` in `project.env` (empty: 1, `0`:
never); the pass after that task finds nothing due and stops as before. A task that says `Потрібна присутність
власника: так` it never takes (`board.py next` does not offer one): such a task is done in an interactive
session with the owner (`tasks/README.md`). Left in `doing/` it stops no task: the runner leaves it as it is,
takes the next tasks beside it (only the cleanup task waits for it: not placed, board 723, and one already in `todo/` not taken, board 838), and the review shows it as «у роботі з власником». A task the owner has just
answered is taken first after the one in hand, whatever its number (`tasks/.first`, written by `board.py unblock`).
It moves the task to `doing/` in its own commit and starts
`claude -p` with `--settings .claude/settings.json --permission-mode auto --output-format json`.
A session that ends with the task still open is continued (`--resume`); a usage-limit notice
waits 15 minutes. When the agent has moved the task to `done/` or `blocked/` the runner pushes
the branch and takes the next one.

One task never stops the board. After three attempts in a row without a commit, when the task's budget (`BOARD_MAX_USD`) is spent, or when three overseers in a
row answered BLOCK on one of its units (the Stop hook then leaves a marker with the verdicts and
stops the session; the agent is asked nothing), the runner parks the
task itself (`board.py park`): it goes to `tasks/blocked/` with a section `## Чому зупинилась` and
a question to the owner, the agent's uncommitted work outside `tasks/` becomes one commit on a
branch of its own, `wip/<task>/<UTC>`, pushed to origin (and a git stash on this machine as well) —
that section names both and gives the command that brings the work back in any clone —, the event
is written into the anomaly journal `tasks/ANOMALIES.md`, and the next task is taken. Any answer returns the task to `todo/` with a fresh clock and count — after a
budget stop, with one more budget of the same size. Everything else that is odd (a push that
failed, a task that vanished from the board) is one more journal entry, not a stop; the review
shows the new entries in a section of their own. The journal is the one place for everything odd:
the Stop gate writes its escalation there, the stuck counter its third identical failure, the agent
what it met (`board.py anomaly … --source агент`), and every entry says who wrote it; the runner
commits what the others wrote before every pull and after every attempt. Every stop with
`state=error` leaves an entry too (not when the checkout is off the work branch). A gate question
nobody answered whose escalation the owner closed in a terminal goes to `done/` by itself, with an
entry.

A task closes with a clean tree. When the agent has moved its task to `done/` or `blocked/`, the
runner looks at `git status`; files that are uncommitted now and were not when the task began are
the task's. The agent gets the turn back once, in the same conversation, with one request: commit
what belongs to the task, remove the rest. A tree still dirty after that turn is one journal entry
with the list of files, and the next task is taken; the runner deletes, stashes and commits none
of them.

A task whose record three readers in a row refused — a sketch's record, or the report of a task without working
code (reader.py leaves `.claude/state/board/reader-blocks-<task>.json`) — goes to `blocked/` with the reason
`reader-blocks`, as the overseer's three BLOCKs do (boards 099, 100). A report already written into
`done/<task>/` goes with it as `blocked/report-<task>.md`: a folder of `done/` counts as a finished task only
with its `task.md`.

A task closes into `done/` with the minimum of its mode (board 098). Right after the clean-tree
check the runner asks `python3 .claude/hooks/mode.py check-close <task>`, which judges by files:
`report.md` in every mode; in соло, for every commit of the task that changed working code (what
the Stop hook asks an audit for: under `SOURCE_DIRS`, else an extension of `CODE_EXTENSIONS`, else
every file; never `tasks/` or `.engine/`), in every stay of the task in `doing/` and in the turn
back, a PASS of the overseer whose audit saw exactly that code (a commit whose code a later commit of the task
with such a PASS replaced is covered too — board 754; so is a commit whose file a commit of another task changed later, when a
PASS of this task saw the file as that commit left it — board 1730); in конвеєр also the feature artifact and a matching seal on every slice contract the task
wrote; in ескіз the record `.engine/sketches/<name>.md` with a reader's PASS on it as it is and no change outside
`sketches/`, `.engine/`, `tasks/` (board 099); in соло and конвеєр, when no commit of the task changed working
code, a reader's PASS on its `report.md` as it is, read together with every document the task's commits changed,
each as it is now (board 100: `reader.py request <task> --report`; the board's own moves and the journals scripts
write are not documents). Missing — the agent gets the turn
back once with the list; still missing — the task goes to `blocked/` with the reason `minimum`, its
report beside it as `blocked/report-<task>.md`, and a journal entry. A task closed into `blocked/`,
and one the runner closes itself (a gate's escalation, an owner action), is not checked; a check that
breaks (exit 3, or any code but 0 and 1) is a journal entry and the task stays in `done/` — never a
park, never a stop.

A task that says `Додаткові сесії: так` (evals, measurements, a release audit, a full simplifier
pass — board 110) is taken only when no ordinary task can start, and not at all while the extra
sessions of the last seven days are at `EXTRA_SESSIONS_WEEK_USD` of `.claude/project.env` (no key:
no cap). A task that met the cap mid-work and went back to `todo/` through `board.py extra-wait`
waits there: it is not parked and nobody is asked; what it left uncommitted goes to a `wip/` branch
named in the journal. When only such tasks are left the runner stops with `state=idle
reason=extra-cap`, and the next start takes them once the seven-day sum has fallen.

«The owner looked it over» is the owner's word (board 100). A closed task without working code hangs in the
review (`board.py review`, «Змінені документи й проєкти — переглянь») until its number stands in
`tasks/.reviewed`. The file arrives from the owner only: in the branch, or as the file `.reviewed` in the inbox
(`board.py import-inbox` adds its numbers and removes it). After every pull and inbox the runner records the
numbers that arrived (`board.py reviewed-accept`, `.claude/state/board/reviewed-accepted`); before every pull
and before every push of the work branch (`push_branch`: the end of a task, a stop after an attempt, a gate's
question) it removes any number that is in the checkout — the working tree's file and the file as HEAD has it
— and was never recorded (`board.py reviewed-reject`: it was written on this machine — by an agent, or by hand
on the server), with a journal entry and a commit of its own, event `reviewed-rejected`. A file that is a link
or a directory is removed whole; bytes that are not UTF-8 are read as the review reads them. After the guard
`push_branch` asks once more (`board.py reviewed-clean`) whether HEAD still holds such a number, and if it does
the branch is not pushed (event `push-withheld … reviewed`; a guard that failed stops the board with
`state=error reason=reviewed`). On a machine with no record yet, what the branch in origin holds counts as
arrived. The hooks refuse an agent's edit and shell write of the file (`protected-path-list.sh`); the runner's
check is the second layer, for a write a hook never sees. What this holds is the ordinary way — a number
written into the file and committed. It does not hold against a session that sets out to get past the check
(it leaves the branch before the push, breaks the check, writes the runner's record): the session runs as the
same Linux user as the runner — `docs/engine-limits.md`, «The same Linux user».

It stops — always with `.claude/state/board/summary.md` — when `todo/` is empty or everything
left waits for the owner, or on a soft stop (exit 0); and with `state=error` (exit 1) only on what
it cannot work past: a pull that conflicts (`reason=pull-conflict`), claude logged out
(`reason=logged-out`; the task stays in `doing/` and the next start continues it), the guarded
files could not be recorded before a session, compared or put back after it (`reason=protected`,
board 724), a git or `board.py` failure after which nothing can be committed.

**The guarded files around every session (board 724).** The constitution, the settings,
`.engine/rules.md`, migrations and CI workflows are recorded before a session (`protected_guard.py
before`) and compared after it: a file that differs is put back, the discarded change kept as a patch
(`.claude/state/gate/protected/discarded/`), the journal written, the task parked with a question. The
record is also kept in `.claude/state/board/guard-before` while the session runs: a runner that died
meanwhile compares with it at its next start, before the first pull. This holds a mistaken or naive
change, not a session that goes for the check itself — `docs/engine-limits.md`, «The same Linux user».

What to read, in `.claude/state/board/`: `status` (one line: `state=… task=… since=<UTC>
[reason=…]`), `events.log`, `costs.json`, `summary.md`, `logs/`. The numbers and paths are
environment variables listed at the head of the script. `board.py` is the board's one reader
(`next`, `summary`, …); `board_state.py` keeps what the runner remembers about each task, and its
`report` — the summary's «Витрати» — also says what every UTC day cost: the day in progress and the
seven before it, a day with nothing spent at 0.00, an attempt recorded without a time on a line of its
own (board 106). No limit is set per day; `BOARD_MAX_USD` per task is as it was.

The owner's review — `python3 .claude/unattended/board.py review [--since <commit|date>]` — is
one markdown document about the work branch as origin has it (`board_review.py`). It writes
nothing, so it may run next to a runner in the middle of a task and from any clone; the
runner's state files are read when they are there. `/owner-review` walks it with the owner.

## Files

| File | Role |
|---|---|
| `board-runner.sh` | the loop: pull, inbox, unblock, one task per fresh session, park, push |
| `board.py` | the board's one reader and mover (`next`, `start`, `park`, `summary`, `review`, …) |
| `board_state.py` | what the runner remembers about each task (attempts, clock, cost) |
| `board_review.py` | the owner's review document |
| `owner_action.py` | the short list of actions the owner's `так` has the runner take |
| `settings_check.py` | judges a settings proposal before it is applied |
| `commit_checkpoint.sh` | the one sanctioned commit path, on `unattended/*` only |
| `env-probe.sh` | prints what kind of session this is (attended, unattended, cloud) |

Machine state is in `.claude/state/board/` and is never committed.
