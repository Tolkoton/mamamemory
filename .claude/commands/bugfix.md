---
description: Fix one bug in full. Writes the bug record `.engine/bugs/<number-name>.md` (the contract and the report of the fix), reproduces the bug (three attempts, then parks — never a fix on a guess), writes a test that fails for the right reason, records the cause before the fix and searches for the same places, makes the smallest fix inside a ready budget (40 new lines is a signal that calls the simplifier, not a ceiling), proves mechanically with `bugfix.py prove` that the test fails without the fix and passes with it, goes through the gate and the overseer, and queues the lesson. Use when something that used to be specified behaves wrongly. Not for behaviour nobody wrote down (that is a question for the owner), not for new behaviour (→ /plan-slice).
---

You are running **/bugfix**: one bug, fixed in full. `$ARGUMENTS` is the report — what was seen,
or the path of a board task or an existing bug record to continue. Speak the owner's language;
write the record in the language of the project's documents.

A bug fix is the smallest change that makes specified behaviour true again. It is not a place to
improve the code around it, and it is not a guess: every step below leaves its evidence in the
bug record before the next one starts.

## When it is not a bug

A bug is a difference between what happens and what is **written**. Before step 2, find where
the expected behaviour is written: a document, a test, a contract in `.engine/slices/`, a
confirmed rule of `.engine/onboard/profile.md`, a line of `.engine/goals.md`, or the owner's own
words in the task. Cite it in the record.

If the expected behaviour is written nowhere and cannot be derived from the profile or the goals,
this is a product decision (Article 5): a question for the owner, not a fix. Attended — ask it
(`AskUserQuestion`), record the answer verbatim as the source, continue. Unattended — write the
question into the record and into the board task under «Питання до власника», move the task to
`tasks/blocked/`, and change no code. "It is obviously wrong" is not a source.

## 1. The record

Copy `.claude/templates/bug-record.md` to `.engine/bugs/<number-name>.md` — the next free
three-digit number, a short name in kebab-case. This file is the contract and the report of the
fix at once: the overseer audits the work against it.

- Fill in section 1: the symptom, the expected behaviour and where that is written, the actual
  behaviour, where it was seen.
- Before anything is changed, write `base_commit` in the record's budget section: the output of
  `git rev-parse HEAD`. The budget and the proof are both measured from that commit.
- Mark the work in `.engine/PROGRESS.md`: a block `## Bugfix <number-name> — IN PROGRESS` that
  names the record's path. That is how the budget script and the overseer find the record.

## 2. Reproduce

Show the bug: the exact command and the output in which it is visible, in section 2 of the
record. "I know where the bug is" without a reproduction is an unverified premise (Article 1).

- There are **three attempts**, and an attempt is a different way of making the bug appear —
  other input, another entry point, the reporter's environment as described — not the same
  command again. Each goes into the record with its command and output, reproduced or not.
- Not reproduced after the third attempt: the work is **parked**, with everything that was tried.
  The three attempts are a guard against an endless loop, so there is no fourth and there is no
  fix on a guess — no change to the working code at all. Set the record's status to `parked` and
  say what would let it resume (a log, a failing input, access to where it happens). With a
  board task: write that as the question for the owner and move the task to `tasks/blocked/`.
  Without one: a question on the board (`board.py open-item --to blocked`; a project with no
  `tasks/`: an entry of the parked log `.engine/overseer/parked.md`, `Class: human-input`, added through
  `python3 .claude/hooks/journal.py add parked`). Then stop this
  command and continue with the next unblocked item.

## 3. The failing test

Write one test that fails because of this bug — at the level where the user sees the bug (the
command, the endpoint, the public function), and for the right reason: its failure output is
the symptom of section 1, not an import error, a missing fixture or a typo. Run it, and put the
command and the failing line into section 3.

- If no test can reach the code: first a test that pins the present behaviour around it (shown
  to pass on the code as it is — `python3 .claude/hooks/bugfix.py pins --test … --cmd …`), and
  only then the smallest seam that lets the bug's test in. The pinning test stays.
- The separate tester (the agent that writes tests from a slice contract) is not called here: a
  bug has no slice contract. What replaces its blindness is the mechanical proof of step 6.
- The test is not weakened later to make it pass. If it turns out to test the wrong thing, say
  so in the record and write the right one.

## 4. The cause — before the fix

Write section 4 before the fix is written. It tells **where it showed** (the place the symptom
appears) from **why it happened** (the cause); when the two sentences are the same, the cause
has not been found yet.

Then search the project for the same cause — the same call, the same assumption, the copy of
that code — and write down the search you ran and what it found. A neighbour with the same cause
is fixed here, with its own failing test, if the whole fix stays inside the budget; otherwise it
becomes a proposal of a new task (`board.py open-item --to proposed`: a file in `tasks/proposed/` the
owner puts to work; or a line in the record when the project has no board) and is not touched.

## 5. The smallest fix

The record carries a ready budget: zero new files, zero new public names, zero new abstractions,
zero new dependencies, and 40 new lines of working code (tests are not counted). Make the fix,
then measure it:

```bash
python3 .claude/hooks/complexity_budget.py check
```

The budget is an expectation, not a ceiling: the 40 is a signal, like every complexity budget.
Going over any line does not forbid the fix — it calls the simplifier:

1. `python3 .claude/hooks/simplifier.py request --lens budget` prints the request. Start the
   agent `simplifier` with exactly that text and save its answer under `.engine/simplifier/`.
2. It finds the excess justified (nothing above `flag_only`): record it —
   `python3 .claude/hooks/simplifier.py accept --reason "<why>" --verdict <file>` — and go on.
3. The excess is not justified: first make the fix smaller. If it cannot be made smaller and still fix the
   bug, this is not a bug fix any more — it is a slice. Set the record's status to
   `became a slice`, keep the failing test, and plan it with `/plan-slice` (unattended: a new
   board task that names the record). Do not push a slice through as a bug fix.

Do not edit the numbers of the budget. No tidying on the way: no renaming, no reformatting of
lines the fix does not need, no helper "for later", no fix of something else you noticed — that
is another record.

## 6. The mechanical proof

That the test failed before the fix is not yours to claim; a script checks it:

```bash
python3 .claude/hooks/bugfix.py prove --record .engine/bugs/<number-name>.md \
        --test <the test file> --cmd "<the command that runs that test>" --expect "<the symptom, as the test prints it>"
```

In a temporary copy it takes the code before the fix together with the new test — the test must
fail, and with `--expect` fail showing that text; then the code with the fix — it must pass.
`--cmd` runs the new test alone, not the whole suite. Paste the command and its whole output
into the record, section 6.

`REFUSED` is not a proof and is not argued with: the test passes without the fix (it does not
catch the bug — back to step 3), fails with it (the fix does not fix — back to step 5), or fails
for another reason. A proof that cannot be made here (the test needs an environment a clean
copy does not have) is written down as exactly that, with the output; it is not replaced by a
sentence.

## 7. The gate and the overseer

As for any unit of work: stage the files, let the turn-end gate run — lint, types and tests no
worse than they were — and claim the unit (`=== UNIT 1 COMPLETE ===`) so that a fresh overseer
audits it against the record. It will run the proof again itself. Write both results into
section 7. The regression test stays in the suite for good: it is never deleted, skipped or
loosened afterwards.

## 8. The lesson

One question: **why was this not caught earlier?** One of four answers — a test was missing, the
contract was wrong, a rule was missing, or the cause is external (a dependency, the
environment, data). Write it into section 8 and queue it as a candidate:

```bash
python3 .claude/hooks/lesson_queue.py add --source agent --slice <number-name> "<the answer, one sentence>"
```

It is a candidate, nothing more: only the owner makes a lesson a rule. Set the record's status
to `fixed`, mark the block in `.engine/PROGRESS.md` done, and close with: the record's path, the
proof's first line, the neighbours that became tasks.
