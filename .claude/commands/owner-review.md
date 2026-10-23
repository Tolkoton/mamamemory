---
description: The owner's review session. Runs `board.py review` (read-only), walks the document with the owner section by section, and prepares the owner's answers, new tasks and the list of the documents they looked over as files the owner then copies into the board's inbox with one command. Changes nothing else. Use when the owner wants to look at what was planned, what is done and what waits for them.
---

You are running the **owner's review** of the task board. The owner reviews when they have time,
not when a task ends; the runner may be in the middle of a task right now, and that is fine.

This session has exactly two effects: the owner sees the picture, and files for the board's inbox
are prepared in a directory under `/tmp`, which the owner copies in with one command of their own.
An agent never writes into the inbox: an answer there is the owner's word, and the hooks refuse
the write (board 056). **Nothing else changes**: no edit in the repository, no `git add`, commit, push, pull,
fetch or switch, no `board.py` command other than `review`, nothing under `.claude/state/`, no
task moved between the board's directories. The runner takes the inbox in before its next task,
once the owner has copied the files there.

Speak the owner's language (the board is in Ukrainian). `$ARGUMENTS` is passed to the review as
is — typically `--since <commit|date>`; empty means "since the newest version tag".

## 1. Make the document

```bash
python3 .claude/unattended/board.py review $ARGUMENTS
```

It reads the work branch in origin through git and writes nothing. Exit 2 means there is no
document: show the owner the reason and stop. If the head of the document says origin was out of
reach, tell the owner the picture may be stale before anything else.

Note the commit in the line «Джерело» — the answers below are written against that commit.

## 2. Walk it with the owner, one section at a time

Give each section in a few sentences of your own, then the details the owner asks for, and wait
for the owner before moving on (`AskUserQuestion` is right here). Do not paste the whole document.

1. **Стан зараз** — what the runner is on, for how long, what it has cost, whether it stopped and why.
   The attempt in hand has no cost in the state files until it ends; say so, do not estimate it.
   The line about the debts of urgent fixes (`/hotfix`): how many are open and until when; at three, the next urgent fix starts with a question.
2. **Зроблено** — per finished task: what changed for the owner, then the decisions the agent
   took alone. Ask whether any of those decisions should be reversed — a reversal is a new task.
3. **Змінені документи й проєкти — переглянь** — the closed tasks that changed no working code: no overseer judged them, a fresh
   `reader` read each report before the task closed, and each hangs here until the owner has looked it over. Per task: the title,
   what the documents are (open the report or a document when the owner asks — `git show <commit>:<path>`), the reader's verdict;
   a task with no verdict, or with a BLOCK, say so first. Ask of each: looked over, a problem found, or later. «Looked over» is
   the owner's word for that task only — never infer it from silence or from a remark about another task; it goes into the file
   `.reviewed` (below). A problem is a new task (below); the closed task is never reopened, and whether it also counts as
   looked over is the owner's to say. «Later» writes nothing: the entry stays.
4. **Чекає на власника** — every open question, one at a time, with its context and options. The
   owner may answer, or leave it for later. Also the tasks that need the owner present (the runner
   never takes them; they are done in an interactive session, not in this one), the settings proposals, the gate's open escalations
   and the rule proposals (each names its question in `blocked/`): each either gets an answer, becomes a new task, or waits.
   Everything open is a task of the board; the logs `escalations.md` and `parked.md` are history and are not part of the review.
   Last in the section, «Пропозиції нової роботи»: what agents, hooks and the overseer found, in `tasks/proposed/` — the runner
   takes none of it. For each, the owner says: to work (a file with the proposal's number for the inbox, below), or let it lie.
5. **Аномалії** — first the overdue debts of urgent fixes (the seven days passed and the full `/bugfix` is not done: ask
   whether the follow-up task should move up the queue); then what the runner, the gate, a hook or the agent found odd, wrote into
   the anomaly journal (`tasks/ANOMALIES.md` and the sessions' files `.engine/journal/anomalies/`) and worked past (each entry says who wrote it): a task the runner parked in
   `blocked/` itself (its question is in the section above; its uncommitted work is on the `wip/…`
   branch the entry names), a failed push, a gate escalation, a stop of the whole board. Say each in a sentence; one that needs a fix is a new task.
6. **План** — the order of `todo/` and what stands on a dependency. A change of order or a
   rewritten task is a file for the inbox (below).
7. **Кандидати в нові задачі** — for each: a task now, later, or never.
8. **Здоров'я** — say it plainly; a red number is a candidate for a task. The test and golden-set
   lines come from the machine records of the runs themselves (time, commit, green of all); where
   the document says there is no record, say that, do not fill it in from memory.

Never answer for the owner and never guess an answer from an earlier remark. Consent has one
form: the answer that is exactly the one word `так` (case and punctuation do not count). It acts
by itself — under a question with the line «Дія runner-а: …» the runner applies the settings
proposal or makes the lesson a rule, on a question of the gate («Закрити ескалацію?») it closes
the escalation — so read it back and get an explicit yes before writing it. Anything else,
«так, але…» included, is an instruction for the agent and applies nothing: write `так` alone
only when the owner means plain consent, and their words verbatim otherwise.

## 3. Prepare the answers and the new tasks; the owner copies them into the inbox

Write the files into a fresh directory of this session, `/tmp/owner-review-<date>-<time>/`
(`mkdir -p` it; never a directory an earlier session left). **Do not write into the inbox
yourself** — not with Write, not with a shell command: `block-dangerous.sh` and
`protect-paths.sh` refuse it, and working around them is forbidden. A file there is the owner's
word, so the owner's own hand puts it there.

The inbox is `$BOARD_INBOX`, by default `~/engine-ops/tasks-inbox`. It must be the inbox of the
machine the runner works on; if this session is elsewhere, say so and give the owner the files
to deliver instead of pretending they arrived.

**An answer** is the blocked task's own file with the `Відповідь:` lines filled:

- take the text exactly as origin has it: `git show <commit>:tasks/blocked/<name>.md`;
- write the owner's words after `Відповідь:` on that same line, verbatim, and change nothing else
  in the file — the line «Дія runner-а: …» least of all;
- save it under the same name in the session's directory, and only when **every** answer in
  that file is filled: the board does not accept a copy that leaves a question open. If the owner answered
  only some, write nothing for that task and tell them which questions remain.

**The tasks the owner looked over** are one file named `.reviewed`: the number of each such task, one a line, nothing else. Write
it into the session's directory only when the owner said «looked over» of at least one task, with exactly those numbers. If the
inbox already holds a `.reviewed` the runner has not taken yet (reading the inbox is allowed), start from its numbers — the
owner's copy replaces that file. The runner adds the numbers to `tasks/.reviewed` of the board; you never write that file — the
hooks refuse it, and the runner removes a number that was written on its machine in the ordinary way (the limit: `docs/engine-limits.md`, «The same Linux user»).

**A new task** is a file `NNN-short-latin-name.md` made from `tasks/TEMPLATE.md`:

- the number sets its place in the queue and is its class x 100 + its place in the class (`tasks/CLASSES.md`):
  take the next one after the largest of the owner's class in every column of the board and the inbox — never in
  classes 7, 8 or 9 (700–999 and their continuations 1701…, 1801…, 1901…: open items, rule questions, the gate's).
  Or leave the number out: a file `short-latin-name.md` with a line `Клас: <class>` under its title gets its number
  when the runner takes the inbox. A number that is already in `todo/` **replaces**
  that task — use it only when the owner wants that task rewritten; a number that is in `proposed/` **puts that
  proposal to work** — the file (the proposal's own text from origin, or the owner's) lands in `todo/` in its place;
- fill `Залежить від:` and `## Що зробити` / `## Готово, коли` from what the owner said;
  `Аудит потрібен: ні` unless the owner asked for the paid audit; no other line is needed for
  extra sessions (evals, measurements: board 078); «спершу проєкт» when
  the owner wants a design first; technical terms in English (`.claude/references/unattended.md`);
- show the owner the text and write it once they agree.

## 4. Close the session

List every file prepared (path, and one line on what it is) and every question left unanswered.
Then give the owner the ONE command that delivers them, to type with the `!` prefix so that it
runs as the owner's own — the directory is this session's, the files are named in full, no
wildcard:

```
! mkdir -p ~/engine-ops/tasks-inbox && cp /tmp/owner-review-<date>-<time>/<file 1> /tmp/owner-review-<date>-<time>/<file 2> ~/engine-ops/tasks-inbox/
```

Never run it yourself and never report the files as delivered: say they wait for that command.
Print the command for the next review — the last line of the document. Then stop: starting the
runner, pushing, or applying anything is not part of the review.
