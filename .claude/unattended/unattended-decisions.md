# Unattended-operation decisions

Calls made while building the unattended harness, with their reasoning and cost-to-reverse.
Pre-ratified by the owner's message of 2026-08-27 ("Decide everything, log to
unattended-decisions.md").

D-1 … D-20 were the design of the DAG supervisor (the restart loop, its caps, liveness, the
session contract, the Stop hook's continue guard). The owner retired that way of working in
board 039 — unattended work goes through the task board only — and those entries left with it;
they are in this file's git history. What stays below concerns mechanisms that are still live.
Where an entry mentions "the supervisor", it is that retired loop.

Format: **D-N. Decision.** Why. Alternative rejected. Cost to reverse.

---

**D-21. `block-dangerous.sh` matches at command position, and its false
positives are accepted rather than fixed.**
Four evasions were closed: a compound command walking past the caret anchor, a
git global option hiding the subcommand, a quoted or braced home variable, and a
tab-indented privilege escalation. The fix is a shared prefix meaning "start of
string, or just after a separator", plus an option group that tolerates a flag
carrying its own argument -- the two-token form was the single case that still
slipped through the first attempt, caught only because the regression suite
covered it.
*Verified:* 10 blocked / 9 allowed in `hook-checks/test_deny_gaps.py`, where the
9 exist to prove the widening did not start catching ordinary commands; the
pre-existing suite went from four documented GAPs to 62 PASS / 0 FAIL.
*Not fixed, deliberately:* the hook matches inside quoted literals and heredoc
bodies, so describing a dangerous command is blocked as if running it. This bit
twice during the work itself. Telling a real invocation from a quoted mention
needs shell parsing, and the obvious shortcut opens a genuine hole because a
heredoc fed to a shell executes its body. For a deny control a false positive is
a nuisance and a false negative is a breach.
*Cost to reverse:* trivial.

**D-22. A decision is closed by being logged, and `escalations.md` gained a
format that can represent an autonomous one.**
*The bug:* verdict routing says a two-way door is logged to `escalations.md` and
continued. But that file's only entry format had fields `Question`, `Options
offered`, `Recommendation`, `Human chose`, `Latency to decision` -- every one
presuming a human answered. There was no shape for "two-way door, decided
autonomously, no human needed". The rule pointed at a file that could not hold
the thing the rule described, so the log stayed at "(no entries yet)" while
decisions were being made.
*The consequence, observed:* the S3 reopening was decided, acted on, and
vindicated -- and then re-surfaced to the owner in three consecutive turns,
because nothing recorded it as settled. An unlogged decision is an open
decision, and an open decision becomes a stop wearing a question mark.
*The fix:* a second AUTONOMOUS entry format (decision / door / cost to reverse /
why not escalated / evidence / falsified by / Status), the S3 decision logged
retroactively as CLOSED, and the doctrine made explicit in CLAUDE.md: logging is
what closes a decision, CLOSED means closed, and a deviation from an owner
instruction is classified by reversibility like anything else -- "the owner said
X" does not make a cheap reversible call one-way.
*Enforced, not just written:* `hook-checks/test_decision_logged.py` fails when a
DAG node carrying `prior_evidence` -- the trace of an autonomous reopening -- has
no CLOSED entry naming it. Verified in both directions: passes on the real repo,
exits 1 against an empty log.
*Cost to reverse:* trivial.

**D-23. Sessions may repair the harness; they may not touch what limits them.**
Owner-ratified 2026-08-27. Edit/Write/MultiEdit granted under `.claude/hooks/`,
`.claude/unattended/` and `.claude/architecture/` in `settings.local.json`
(machine-local -- `settings.json` ships with the template). `constitution.md`,
`settings.json` and `settings.local.json` are denied in the permission list AND
independently by `protect-paths.sh`, because a permission list can be re-widened
by editing the file that defines it, and an agent that may edit its own
permissions has none.
*Paired with D-24, deliberately:* the grant is only safe if a session's patch is
screened before it lands.
*Verified:* `test_guardrail_paths.py`, 5 refused / 5 allowed.

**D-24. A patch proposed by a session is screened before it is applied.**
`hook-checks/lint_patch.py` flags the transformations that are almost always a
weakening, split into CRITICAL (fails, exit 1) and REVIEW (informational).
*The evidence it was built from:* the S3 patch contained
`PROJECT_ROOT=$(git rev-parse --show-toplevel >/dev/null 2>&1)`. In a command
substitution stdout IS the value, so the "fix" silently emptied the variable and
the hook fell back to the wrong directory. Every test in the session's own suite
still passed, because no test covered project-root detection. A human reading the
diff caught it; unattended it would have landed.
*Tuned for use, not for coverage:* the first version flagged 20 hunks on that
patch, 19 of them legitimate. A gate that fires on twenty when one matters trains
people to ignore it. Now: 1 CRITICAL, 19 informational.
*Verified both ways:* exit 1 on the real patch, exit 0 on a clean one.
*Honest limit:* it is a screen, not a proof. It catches a known shape of
weakening, not wrongness in general.

**D-25. Commits are legal on `unattended/<date>` and nowhere else.**
Owner-ratified 2026-08-27. The checkpoint is kept where it does work -- nothing
reaches `main` without a human reading the diff -- and removed where it only
made work pile up: over a night, every session was building on an unreviewed
index inherited from the session before it, so one bad change was silently
inherited by everything after, with no point to roll back to.
*Fails closed:* an undeterminable branch is refused, not allowed.
*Uses the S7 command-position pattern on both sides,* so `cd x && git commit` and
`git -C dir commit` are caught where they must be caught and permitted where
they are permitted.
*Stages `-u`, never `-A`:* an unattended run emits logs and scratch patches, and
sweeping those in makes the review surface unreadable.
*Verified:* `hook-checks/test_commit_policy.py`, 11/11 against real throwaway
repos with real branches checked out -- the hook reads the branch with
`git branch --show-current`, so faking it would only test the test.
*One step remains and it is not the AI's:* `settings.json` denies
`Bash(git commit*)`, deny beats allow, and D-23 made that file unwritable by the
AI. The last enabling edit belongs to the owner by construction.

**D-26. CORRECTION to D-25: hooks guard tool calls, not scripts.**
D-25 claimed `block-dangerous.sh` enforces the commit rule "independently". For
a command the agent types, true -- 11/11. For a command inside a script, false.
PreToolUse hooks and `permissions.deny` evaluate the Bash tool call that is
issued; a script's internal commands are never re-evaluated.
*Verified 2026-08-27, deliberately with a non-mutating probe:*
`git commit --dry-run` is refused by the harness at top level, and executed
untouched from a two-line script.
*Scope of the problem, which is wider than commits:* every hook in this repo is
bypassable this way -- `block-dangerous.sh`, `protect-paths.sh`, the deny list.
Any script an agent writes is a hole through all of them. This does not make the
hooks useless: they still catch the direct, ordinary, accidental case, which is
the common one. It makes "a hook enforces this" a claim that must be qualified.
*Fixed where it matters now:* `commit_checkpoint.sh` re-checks the branch itself
immediately before committing and refuses anything outside `unattended/*`,
rather than trusting the earlier switch or the hook. On that path those lines
are the only control there is.
*Recorded in AGENTS.md* so it reaches every session, not just this one.

**D-27. `settings.local.json` was committed since the repository's first commit,
contradicting its own header.**
The file states "Machine-local overrides. Gitignored — never committed, never
inherited by a project copied from this template", and the S4b park note gives
that as the reason the supervisor permission went there rather than into
`settings.json`. Both were wrong: `git log --diff-filter=A` puts it in `c9d348e`,
the initial commit, and no `.gitignore` rule ever matched it.
*What it actually shipped:* every clone of this template inherited permission to
auto-launch the supervisor loop, and after D-23 would have inherited write access
under `.claude/hooks`, `.claude/unattended` and `.claude/architecture` too --
precisely the "bad default" the earlier decision was written to prevent. The
reasoning was sound; the mechanism was never checked.
*Fixed:* added to `.gitignore` and `git rm --cached`. The file stays on disk, so
this machine keeps its grants; downstream projects now start with none.
*The general lesson, and it is the same one three times today:* a comment
asserting a mechanism is not the mechanism. `{NODE}` was never substituted, the
continue branch was unreachable, escalations.md could not record an autonomous
decision, and this file was never ignored -- each read as correct and none of
them was ever exercised.
