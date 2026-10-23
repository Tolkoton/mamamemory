---
description: An urgent fix that leaves a debt. Only the owner declares work urgent — the agent never does. First asks whether turning the guilty change back is simpler (prepares `git revert`, never runs it). Then the smallest fix inside a HARD limit (30 new lines, two files, no new file, dependency or public name, no deletion outside the functions fixed — over it the turn is blocked, the simplifier is not asked), with the way to roll it back written in the card. The test before the code, the record of the cause and the search for the same places are put off into a debt a script writes — a line in `.engine/debt.md` with a term of seven days and a follow-up board task, a full /bugfix. The gate and the overseer stay. With three debts open, starts with a question for the owner. Not for work nobody called urgent (→ /bugfix).
---

You are running **/hotfix**: one urgent fix. `$ARGUMENTS` is what is broken, or the path of the
board task that declares it. Speak the owner's language; write the card in the language of the
project's documents.

Urgency lifts the ceremony, not the checks. What may wait — the test before the code, the record
of the cause, the search for the same places — becomes a debt that a script writes down and the
owner sees. What does not wait: the gate, the bypass guard, the overseer, and a hard limit on the
size of the fix. An urgent fix that needs more than the limit is not an urgent fix.

## Only the owner declares it

A fix is urgent when the **owner** said so: a line in the board task (`/hotfix`, «термінове»,
"urgent"), or the owner's words in a session the owner sits in. You never name work urgent
yourself — not because it looks serious, not because it would be quicker; that would be a way
round the full process (Article 3). Work nobody declared urgent is `/bugfix`.
`hotfix.py start` checks this and refuses otherwise: unattended, only the task's line counts.

## 1. Roll back first

Before anything is fixed, find the change that brought the bug in: `git log` over the files
where it shows, `git bisect` when a command reproduces it. Then ask: is turning that change back
simpler and safer than fixing forward?

- It is: **prepare** the command — `git revert <sha>` — and propose exactly that. It is prepared,
  not run: `git revert` is the owner's act (ask-gated). Attended — show the command and what it
  undoes besides the bug, and let the owner decide. Unattended — write the command and the
  question into the board task under «Питання до власника», move the task to
  `tasks/blocked/`, and write no fix.
- It is not (the change is old and built upon, it carried something that must stay, or it was
  not found): say why in the card, section 3, and go on.

## 2. The card

```bash
python3 .claude/hooks/hotfix.py start --name <short-kebab-name> --task <the board task>
python3 .claude/hooks/hotfix.py start --name <short-kebab-name> --declared "<the owner's words, as said in this session>"
```

It writes the card `.engine/bugs/<number-name>.md` (type `hotfix`, the base commit, the hard
limit) and marks it IN PROGRESS in `.engine/PROGRESS.md`. The card is the contract of the fix
and its report; do not copy the template by hand and do not edit its type or its numbers.

With **three open debts** the script writes no card: it ends with exit 3 and prints a question
for the owner — otherwise "urgent" becomes the ordinary way to work. Attended — ask it now.
Unattended — write the printed question into the task and move the task to `tasks/blocked/`. When
the owner has answered that the fix should go on, run `start` again with
`--owner-answer "<the answer, word for word>"`; with `--task` the answer must stand in the task
file. An answer that says to close a debt first is an instruction: do that follow-up instead.

Fill in section 3 of the card with what step 1 found.

## 3. The symptom

Show what is broken, in section 2 of the card: the exact command and the output in which the bug
is visible. When there is no time or no way to reproduce it, the owner's words about the symptom
go there as they are, quoted — not your reading of them. One of the two is always there: a fix
for a symptom nobody stated is a guess.

## 4. The fix, inside the hard limit

Make the smallest change that removes the symptom. Then measure it:

```bash
python3 .claude/hooks/complexity_budget.py check
```

The limit is **hard**, unlike the budget of a slice or of a `/bugfix`: at most 30 new lines, in
at most two files, no new file, no new dependency, no new public name, and no code deleted
outside the functions being fixed (a deleted function, file or module-level line is such a
deletion; a line replaced by another is not). Every changed file counts except the tests. Over
any of these the turn is blocked — at every stop, whatever `COMPLEXITY_GATE` says; the
simplifier is not called and nothing it says lifts the block. The block reads:

> Це не термінове виправлення — або зменш, або `/bugfix`.

and those are the two ways on: make the fix smaller, or stop this command and do the work as
`/bugfix` (set the card's status to `became a bugfix`, mark its block in `.engine/PROGRESS.md`
accordingly, and tell the owner the urgent path did not hold it). Do not edit the card's numbers
or its type — the limits it began with stay in force.

A test written now is welcome and is never counted against the limit; it is only not required
before the code. No tidying on the way: no renaming, no reformatting, no helper "for later".

## 5. The way back

Write into the card, section 4, how to roll back **exactly this fix**: one command or one
commit — `git revert <the fix's commit>` when it is committed on its own, otherwise the precise
patch to turn back. Whoever reads the card at night must be able to undo the fix without
reading the code. `hotfix.py debt` refuses a card without it.

## 6. The gate and the overseer

Neither is put off, and there is no exception for urgency: stage the files and let the turn-end
gate run — lint, types and tests no worse than they were, the bypass guard, the delete guard.
An urgent fix does not get through on a `gate-allow`, a skipped test or a loosened check. Then
claim the unit (`=== UNIT 1 COMPLETE ===`) so that a fresh overseer audits it against the card.
Write both results into section 5.

## 7. The debt

```bash
python3 .claude/hooks/hotfix.py debt --record .engine/bugs/<number-name>.md
```

The script — not your memory — leaves both traces: a line in `.engine/debt.md` (what was put
off: the test before the code, the record of the cause, the search for the same places; the
commit; the date; the term — seven days) and, where the project has a task board, the follow-up
`tasks/proposed/NNN-hotfix-followup-<number-name>.md`: a full `/bugfix` of the same place, a proposal
the owner puts to work (a file with its number in the inbox; nothing takes a task from `proposed/`). It
refuses a fix over the limit, a card with no fix, and a card without its way back. Stage
`.engine/debt.md`, the follow-up task and the card together with the fix.

Run it after the fix is committed where commits are yours (an `unattended/*` branch), so the
line names the commit; elsewhere pass nothing and the line says the fix is not committed yet.
The debt is closed only by the follow-up — `hotfix.py close`, at the end of its `/bugfix`. The
owner's review shows open debts in its first section and overdue ones among the anomalies.

Close with: the card's path, the debt line, the follow-up task, and the command that rolls the
fix back.

## What /hotfix never does

- It does not deploy and does not push the branch: those are the owner's acts. "It is fixed"
  means fixed in the working tree (or the work branch), and you say so in those words.
- It does not touch migrations.
- It does not touch the settings of the checks: `.claude/project.env`, `.claude/settings.json`,
  the CI workflows, the linter's and the type checker's configuration, `.engine/baseline.json`.
  A fix that needs one of them changed is not an urgent fix.
- It does not run `git revert`, and it does not start a second urgent fix while its own is open.
