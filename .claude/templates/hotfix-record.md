# Hotfix <number-name>

type: hotfix
status: declared
<!-- status: declared → fixed, debt open → debt closed (by the follow-up /bugfix); or
     revert proposed (step 1: turning the change back was simpler); or became a bugfix (the fix
     did not fit the hard limit). Written by `hotfix.py start`, never copied by hand.
     This card is the contract of the urgent fix and its report: the overseer audits against it. -->

## 1. Declared by the owner
- The owner's words: <the owner's words, as they are, and where they stand>
- Recorded: <date>
- Open debts when it began: <how many>
- The owner's answer to the three-debts question: <the answer, word for word — only when three debts were open>

## 2. Symptom
A reproduction — the exact command and the output that shows the bug — or, when there is no time
for one, the owner's words about what is broken, recorded as they are.
- Symptom: <what is broken, as it is seen>
- Where it was seen: <environment, input, version>

## 3. Roll back first
- The change that brought the bug in: <the commit, or "not found" and how it was looked for>
- Turning it back instead: <the prepared command `git revert <sha>` — prepared, never run by the agent — or why turning it back does not help>
- Decision: <fix forward | revert proposed to the owner>

## 4. Fix
- What changed: <files and the one-sentence reason for each>
- Roll back: <one command or one commit that undoes exactly this fix>
- Nothing else: no tidying on the way, no renaming, no new helper, no deletion outside the functions fixed.

The limit below is hard, unlike the budget of a slice or of a /bugfix: going over any line blocks
the turn — the simplifier is not called and nothing lifts it. Then this is not an urgent fix:
either make it smaller, or do the work as `/bugfix`. The numbers and the type are not edited; the
script keeps the ones the card began with.

## Complexity budget
mode: hard
base_commit: <base_commit>
max_new_files: 0
max_changed_files: 2
max_added_lines: 30
max_new_public_symbols: 0
max_new_dependencies: 0
justification: none

## 5. Gate and overseer
Neither is put off, and there is no exception for urgency.
- Gate: <the result of the turn-end checks — no worse than it was>
- Overseer: <the verdict and its ledger entry>

## 6. Debt
Written by `python3 .claude/hooks/hotfix.py debt --record <this card>`, not by hand.
- Deferred: the test before the code; the record of the cause; the search for the same places
- Debt line: <the line the script wrote into `.engine/debt.md`>
- Follow-up: <the board task the script made — a full /bugfix of the same place>
