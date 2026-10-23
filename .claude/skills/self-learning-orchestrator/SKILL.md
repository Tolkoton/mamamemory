---
name: self-learning-orchestrator
description: Orchestrates the self-learning loop across a Claude Code dev cycle — knows WHEN to read, update, or distill the project's living memory (CLAUDE.md, the ADRs in docs/adr/, MEMORY.md files, claude-progress.md, reflections.md) and dispatches to the right sub-skill at each moment. Use this skill at session start (read prior learning), when a substantive decision is being made, when stuck for more than ~20 minutes, before any commit, at session/task end (distill lessons), and on periodic maintenance days. Also use whenever the user mentions "session start", "session end", "wrap up", "done for now", "/clear", "/bye", "stuck", "tried everything", "we picked", "going with", "trade-off", "ready to commit", "review my changes", "wrap up the task", "memory maintenance", "review CLAUDE.md", "this took forever to debug", "remember this for next time", "lesson learned", or whenever you notice a workflow moment (just opened a new session, just fixed a non-obvious bug, just completed a task) where memory should be consulted or updated. Proactively detect these moments even if the user has not explicitly asked.
---

# Self-Learning Orchestrator

Orchestrate the project's living memory across the development lifecycle. This skill is the *trigger dispatcher*: it recognizes WHICH self-learning moment is happening and routes to the right protocol. The protocols themselves are the files in `triggers/`.

## What this skill manages

A layered memory stack with deliberately different update frequencies:

| Artifact | Scope | Lifetime | Update cadence |
|---|---|---|---|
| `CLAUDE.md` | project | forever | rare, deliberate |
| `docs/adr/NNNN-*.md` (ADR) | project | append-only, superseded never edited | per substantive decision (~weekly) |
| `.engine/overseer/MEMORY.md` | project | every entry cites two ledger entries, or is pruned | on the hook's lesson review (`resolve --to memory`) |
| `~/.claude/memory/<tech>/MEMORY.md` | global per-tech | append-only forever, periodic consolidate | per session-end |
| `claude-progress.md` | task | deleted on completion | per commit |
| `<task>/reflections.md` | task | archived on completion | per failed attempt |

Mismatching the cadence is the most common failure mode. CLAUDE.md is not a place to log every bug; MEMORY.md is not a place to record every commit. The triggers below map each moment to the correct artifact.

## How to dispatch (the only rule)

When invoked, identify which moment is happening and read the matching trigger file:

| If the moment is... | Read |
|---|---|
| New session starting / first message after `/clear` | `triggers/session-start.md` |
| About to make a real choice with alternatives | `triggers/decision-checkpoint.md` |
| Tried ≥3 approaches without progress | `triggers/stuck-protocol.md` |
| About to commit / "done with this" | `triggers/pre-commit-checkpoint.md` |
| User said "/clear", "/bye", "wrap up", or task is complete | `triggers/session-end-dreaming.md` |
| User asked for memory maintenance or a periodic review | `triggers/periodic-maintenance.md` |
| User said "lesson learned: ..." or "remember this for next time" | `lesson_queue.py add`, see "Lesson capture" below |

Read **only the trigger file that applies**. Do not preload everything — each trigger has independent context needs.

## Lesson capture (lightweight, inline) — the queue is filled by hooks too

The lesson queue is one line per candidate: `- <date UTC> | <source> | <slice> | <essence> #<id>` — each session's lines in
its own file `.engine/journal/lessons/<session>.md`, the folded ones in `.engine/lesson-queue.md` (board 739); read it
with `python3 .claude/hooks/lesson_queue.py list`
(source: gate, overseer, parked, escalation, agent). **Hooks fill it without you**: a Stop block of the
gate, an `OVERSEER_BLOCK` verdict, a parked item and an escalation are added automatically, once each
(`.claude/hooks/lesson_queue.py`). You add a line yourself only when you found a **non-obvious cause** —
something a fresh session would not guess from the code:

```bash
python3 .claude/hooks/lesson_queue.py add --source agent --slice <slice> "<what was non-obvious and what is actually true>"
```

Do not queue what the code, the tests or git history already say, and do not stop to write an ADR.

**Triage is the hook's request, not yours to schedule.** After an overseer verdict of PASS the hook appends
`LESSON_REVIEW_REQUESTED` to the continue text when the queue is not empty. For each candidate run
`python3 .claude/hooks/lesson_queue.py resolve <id> --to memory|rule|engine|discard`:
`memory` needs `--text` and two `--cite` ledger entries (the memory file's citation-or-prune rule);
`rule` needs `--text` and `--why` (and takes `--recommend`, the overseer's advice) and writes a **proposal** to
`.engine/rule-proposals.md` plus a question for the owner in `tasks/blocked/`; `engine` writes
`.engine/engine-feedback.md`; `discard` just removes it. A resolved candidate leaves the queue.

**Stuck.** Three identical failures in a row make a hook hand you the stuck protocol
(`triggers/stuck-protocol.md`) as additional context; a success resets the count. Follow it; it never blocks.

**Session start.** A short digest (latest memory headings, queue size, proposals waiting) arrives as
session context; when it says MEMORY CLEAN-UP DUE, run `triggers/periodic-maintenance.md`, then
`python3 .claude/hooks/lesson_queue.py cleanup-done`.

**Nothing reaches the persistent context by itself, and a lesson becomes a rule only with the owner's consent.**
A rule proposal is a task in `tasks/blocked/` asking «Зробити це правилом?» with the exact text. The overseer may
recommend; it does not decide. On the owner's «так» the board runner runs `promote`, which appends the rule to
`.engine/rules.md` (imported by CLAUDE.md under a 200-line budget); on «ні» it closes the proposal. Never run
`promote` yourself (it refuses inside a session), never fill the answer, never edit CLAUDE.md for a lesson.

## Hard rules

1. **Always read CLAUDE.md and the relevant MEMORY.md files at session start.** Skipping this is the single largest learning leak — every subsequent decision is uninformed by prior lessons.
2. **Never write to CLAUDE.md, an ADR, or MEMORY.md silently.** Attended: show the user what you propose to add and where, and get explicit confirmation. Unattended, or in answer to the hook's `LESSON_REVIEW_REQUESTED`: that request is the confirmation for `.engine/overseer/MEMORY.md` (through `resolve --to memory`, which refuses without two ledger citations) and for the two proposal files; **CLAUDE.md and `.engine/rules.md` are never written by hand or by a hook — only `promote` writes the latter, after an overseer PASS.** Memory pollution is irreversible without git archaeology.
3. **One artifact per piece of knowledge.** A specific fact lives in exactly one of: CLAUDE.md (rule), an ADR in `docs/adr/` (rationale), MEMORY.md (experience), reflections.md (per-task), code comment (per-line). Duplication causes drift. See `references/artifact-scope-decision-tree.md`.
4. **Defer non-blocking captures to the queue.** Bug fix in flow with a non-obvious cause? `lesson_queue.py add`, do not stop to write a full ADR. The queue is triaged when the hook asks (after an overseer PASS) and at session-end.
5. **Session-end is non-optional.** Skipping session-end-dreaming silently drops all lesson candidates accumulated during the session. If a session is ending and the queue is non-empty, process it before `/clear`.
6. **Periodic maintenance is non-optional.** Without prune, MEMORY.md and CLAUDE.md rot to the point of being ignored. Schedule weekly or monthly, treat as real work.
7. **Promotion path is one-way and rare.** A pattern in MEMORY.md may *eventually* be promoted to a Skill, but only after appearing in 3+ projects. Inverse demotion (skill → memory) never happens.

## What this skill does NOT do

- It does NOT replace `master-architect` for architectural design. Master-architect handles Phase 1–4 architectural work and writes its own `.engine/architecture/` artifacts. Self-learning-orchestrator coordinates the *cross-cutting* memory lifecycle around it.
- It does NOT replace `slice-builder` for implementation. Self-learning-orchestrator handles the memory lifecycle around implementation — ad-hoc bug fixes, refactors, exploration sessions — not the slice itself.
- It does NOT write code. It coordinates the memory layer that informs all code work.

## When to skip this skill entirely

- Throwaway scripts in `/tmp/`.
- Single-line typo fixes that need no context.
- User explicitly says "just do it, no protocol".
- Interactive REPL sessions with no commit at the end.

For everything else — every real coding session — run at minimum the session-start trigger.

## References

- `references/artifact-scope-decision-tree.md` — which artifact a given fact belongs in
- `references/lesson-classification.md` — tech vs project vs both vs discard (used in session-end-dreaming)
- `references/memory-pollution-prevention.md` — limits, anti-patterns, when to prune
- `references/promotion-paths.md` — memory → skill, lesson → ADR, draft → rule
- `checklists/session-end.md` — quick checklist before `/clear` or `/bye`
