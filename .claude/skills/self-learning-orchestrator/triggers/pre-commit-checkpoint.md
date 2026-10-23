# Trigger: Pre-Commit Checkpoint

About to commit, or to declare a task "done". This is the densest learning moment in the dev cycle: the diff is in front of you, everything that just happened is fresh, and the cost of writing down what you learned now is much lower than ever again.

## When this fires

Any of:
- User says "ready to commit", "commit this", "let's commit", "review my changes".
- User says "done", "looks good", "are we done", "wrap this up".
- You finished implementing a sub-task and the diff is non-trivial.
- The `Stop` hook fires (Claude finishes a turn that produced a meaningful diff).

## Procedure

This trigger orchestrates two concerns in the right order: memory updates, then handing the staged work over. Lint, types and tests are the Stop gate's job (the project's own commands from `.claude/project.env`).

### Step 1 — Memory checks

Ask three quick questions:

**Q1: Did this change establish a new convention?**

If yes — propose adding a line to CLAUDE.md. Show the user the exact text. Wait for confirmation.

Examples of new conventions:
- "All HTTP clients now use httpx instead of requests" → CLAUDE.md line.
- "Tests for handlers go in `tests/handlers/`" → CLAUDE.md line (or layout section).
- "We commit lockfile changes in a separate commit" → CLAUDE.md commit-discipline line.

Examples that look like conventions but aren't:
- "This particular function uses generators" → that's code, not a convention.
- "We use Pydantic v2 in this module" → if it's already a project-wide rule, skip; if it's a new rule, add it.

**Q2: Was there a substantive decision in this change?**

If yes — follow `triggers/decision-checkpoint.md`. The ADR is staged together with the code that implements it.

**Q3: Was there a non-obvious bug found and fixed in this work?**

If yes — add it to the lesson queue (the command writes this session's own file of it, board 739):

```bash
python3 .claude/hooks/lesson_queue.py add --source agent --slice <slice> "<what was non-obvious and what is actually true>"
```

Defer the full lesson processing to session-end-dreaming. Do not stop now to write a full MEMORY.md entry — the lesson queue exists exactly to avoid this interruption.

### Step 2 — Update progress file

If a `claude-progress.md` exists for this task:

1. Move items from "What's left" to "Files affected" (mark touched).
2. Update "Last working state": new commit SHA, tests passing, branch position.
3. Refresh "Next session: pick up here" if more work remains.
4. If the task is fully complete, mark `Status: completed` and add a "Result" section with PR link or final commit.

The progress file should always reflect the *current* state of the staged work. If you skip this step, the next session start will use stale information.

### Step 3 — Stage and suggest the commit message

The commit itself is a human checkpoint (`.claude/engine-rules.md`, "Commits are a human checkpoint"):
`git add <files>`, print a one-line summary and a suggested message in conventional-commits format,
then continue with the next item.

```
<type>(<scope>): <short description>

<body — why, not what>

<footer — refs, breaking changes>
```

If a decision (Q2) or convention (Q1) was added in this trigger, stage it with the code change: one logical unit including the memory updates.

If a lesson was queued (Q3), it'll be processed at session-end.

## Sequencing rules

- Memory checks BEFORE staging: ADRs and convention lines belong to the same unit as the code.
- Progress file update BEFORE the suggested message: the file's state should match what is staged.

## Skip conditions

If ALL of the following are true, skip everything except the suggested commit message:
- Diff < 30 LOC.
- Single file changed.
- No new public API.
- No new dependency.
- Obviously a typo / minor fix / version bump.

In that case: stage it and suggest the message. The full checklist is overhead for trivial changes.

## Failure modes

- **Convention added to CLAUDE.md but not to behavior.** You wrote "always use X" but the code still has Y in 5 places. Either fix Y first, or don't add the rule yet.
- **ADR with no code reference.** Someone reading the code later won't know to look in docs/adr/. At minimum add `# See ADR-NNNN` near the relevant code.
- **Progress.md left stale.** "Tests passing" written before tests were re-run. Always update progress.md *after* the quality gates pass, not before.
- **Lesson written as memory entry instead of queued.** Premature classification. The queue gives you the benefit of seeing patterns across the session.
- **Commit message describing WHAT not WHY.** "Add function foo" tells future-you nothing. "Add foo because Y was too slow on batch sizes > 1000" is useful.

## After the hand-over

If the queue has lesson candidates:
- Continue with the next task.
- Process the queue at session-end (`triggers/session-end-dreaming.md`).

If this unit completed the task:
- Trigger session-end-dreaming now, even if the session continues with a different task.
- Memory hygiene is per-task, not per-session.

## What this trigger does NOT do

- Does not run `git commit` or `git push`. The engine rules say who commits and where.
- Does not open a PR. That's a separate trigger if you have one.
- Does not write MEMORY.md entries directly. Those go through session-end-dreaming with classification.
- Does not run the full periodic-maintenance review. That's a different cadence.
