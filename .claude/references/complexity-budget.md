# Complexity budget — how to set one

Read this when `/plan-slice` reaches the budget step (only when `.claude/project.env` has
`COMPLEXITY_GATE` set to `warn` or `call`).

The budget is agreed BEFORE the code exists. It is the smallest shape of change that can
satisfy the slice's exit criterion — not a forecast of what will probably get written.

It is a stated expectation, not a ceiling. Going over it does not forbid the change: it calls
the simplifier, which either finds the excess justified (the reason is recorded) or sends the
change back to be made smaller.

A bug record (`.engine/bugs/<number-name>.md`, written by `/bugfix` from
`.claude/templates/bug-record.md`) carries the same section, ready-made and small: no new files,
names, abstractions or dependencies, 40 new lines. It is measured the same way while
`.engine/PROGRESS.md` marks that record IN PROGRESS, and `complexity_budget.py check` reports it
whatever `COMPLEXITY_GATE` says. (A slice needs no card: without one the budget measures the
slice the board task has open — `testing.py request <slug> --point a` opens it.) An overrun the simplifier does not justify makes the fix a slice.

The card of an urgent fix (`/hotfix`, written by `hotfix.py start` from
`.claude/templates/hotfix-record.md`) is the one budget that IS a ceiling. Its section says
`mode: hard`, and the card says `type: hotfix`; either makes it hard, and a card seen hard stays
hard whatever it is edited to say. The limits cannot be set above these: `max_new_files: 0`,
`max_changed_files: 2`, `max_added_lines: 30`, `max_new_public_symbols: 0`,
`max_new_dependencies: 0`. It is measured whole — every changed file except the tests and the
engine's own records (`.engine/`, `tasks/`, `.claude/state/`), not only `SOURCE_DIRS`; added lines, not net ones —
and code may not be deleted outside the functions being fixed. Over it the turn is blocked at
every stop, whatever `COMPLEXITY_GATE` says; the simplifier is not called and
`simplifier.py accept` refuses. The two ways on are a smaller fix or `/bugfix`.

## The section to add to the slice contract

```
## Complexity budget
base_commit: <output of `git rev-parse HEAD` right now>
max_new_files: 1
max_net_new_lines: 80
max_new_public_symbols: 2
max_new_abstractions: 0
max_new_dependencies: 0
max_cyclomatic_per_function: 10
max_nesting_depth: 3
justification: none
```

Plain `key: value` lines, whole numbers. A misspelt key is an error, not a missing limit.

## How to choose the numbers

1. Write down, in one or two sentences, the simplest change that meets the exit criterion:
   which existing file it goes into, which function it adds. Count from that.
2. **New files:** 0 if the behaviour belongs in a file that exists. A new file needs a reason
   the existing layout cannot absorb it.
3. **Net new lines** count production code only. Tests are measured and reported but never
   limited: a test adds lines and removes risk. Deleting code pays lines back.
4. **New public symbols:** the names the exit criterion itself mentions, no more.
5. **New abstractions** (a base class, a Protocol, an abstract method): 0 unless TWO users
   exist today. Name both in `justification`. "We will need it later" is not a user.
6. **New dependencies:** 0. Anything else names the dependency and the reason in
   `justification`, and the owner sees it when approving the contract.
7. **Complexity and nesting:** leave the two lines out to take the project's defaults
   (`COMPLEXITY_MAX_CYCLOMATIC`, `COMPLEXITY_MAX_NESTING` in project.env — calibrated on the
   project's own functions, applied by the owner; 10 and 3 until then). They apply only to
   functions this slice adds or makes worse; old complexity in a file you touch is not charged.

## After writing the section

Run `python3 .claude/hooks/complexity_budget.py validate <contract path>` and fix what it
reports. Show the owner the budget together with the rest of the contract.

## During the slice

`python3 .claude/hooks/complexity_budget.py check` prints the current usage at any time.

When the turn is held on an overrun (`COMPLEXITY_GATE="call"`):

1. `python3 .claude/hooks/simplifier.py request --lens budget` prints the request: the figures,
   the changed files, the signals. Start the `simplifier` subagent with exactly that text — no
   explanation of your own; it judges the change blind.
2. Save its answer to a file under `.engine/simplifier/`.
3. It found something to remove or confirm: the overrun is not justified. Make the change
   smaller and end the turn again.
4. It found nothing above `flag_only`: record its verdict —
   `python3 .claude/hooks/simplifier.py accept --reason "<why the excess is needed>" --verdict <file>`.
   The reason goes to `.engine/slices/overruns/<slug>.md` (the contract itself is sealed and
   is not edited) and to the ledger; the turn ends. Growing past the accepted figure calls
   the simplifier again.

Do not edit the numbers — the limits the slice began with stay in force, and a raised number
is reported, not honoured.
