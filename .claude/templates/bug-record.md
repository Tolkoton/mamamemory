# Bug <number-name>

type: bugfix
status: recorded
<!-- status: recorded → reproduced → fixed; or parked (not reproduced in three attempts);
     or question for the owner (the expected behaviour is written nowhere); or became a slice.
     This file is the contract of the fix and its report at once: the overseer audits against it.
     Sections 1–4 are written before the fix exists. -->

## 1. Record
- Symptom: <what was seen, in the words of whoever saw it>
- Expected: <what should have happened>
- Where the expected is written: <file:line of a document, a test, the profile, the goals, or the owner's words quoted — never "obviously">
- Actual: <what happens instead>
- Where it was seen: <environment, input, version, who reported it and where>

## 2. Reproduction
Three attempts, each a different way. Reproduced — stop at that attempt. Not reproduced after
the third — the status becomes `parked`, nothing below is filled in and no code is changed.

### Attempt 1
- Command: <the exact command>
- Output: <the tail that shows the bug, or shows it did not appear>
- Result: reproduced | not reproduced

### Attempt 2
- What is different from attempt 1:
- Command:
- Output:
- Result:

### Attempt 3
- What is different from attempts 1 and 2:
- Command:
- Output:
- Result:

## 3. Failing test
- Test: <path::name> — at the level where the user sees the bug
- Command that runs it: <the command, run from the project root>
- It fails with: <the line of its output that is the symptom>
- Tests written first to pin the present behaviour around the code (only when no test could reach it): <paths, or none>

## 4. Cause
Written before the fix.
- Where it showed: <file:line — the place the symptom appears>
- Why it happened: <the cause; not the same sentence as above>
- Same places: <the search that was run, and every other place with the same cause — fixed here, or the task it became>

## 5. Fix
- What changed: <files and the one-sentence reason for each>
- Nothing else: no tidying on the way, no renaming, no new helper for later.

The budget below is the ready small budget of a bug fix. The 40 is a signal, not a ceiling —
going over any line calls the simplifier; when it does not find the excess justified, this
stops being a bug fix and becomes a slice through `/plan-slice`. The numbers are not edited.

## Complexity budget
base_commit: <output of `git rev-parse HEAD` before the first change>
max_new_files: 0
max_net_new_lines: 40
max_new_public_symbols: 0
max_new_abstractions: 0
max_new_dependencies: 0
justification: none

## 6. Proof
The command and the whole output of `python3 .claude/hooks/bugfix.py prove …`, pasted. `REFUSED` is not a proof.

```
<output>
```

## 7. Gate and overseer
- Gate: <the result of the turn-end checks — no worse than it was>
- Overseer: <the verdict and its ledger entry>
- The regression test stays in the suite: <path::name>

## 8. Lesson
Why was this not caught earlier — one of: a test was missing | the contract was wrong | a rule was missing | external.
- Answer: <which, and one sentence>
- Queued: <the line `lesson_queue.py add` printed>
