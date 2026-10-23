# Agents guide — <project name>

> Loaded into every session via `@AGENTS.md` from CLAUDE.md. Keep it short and true: CLAUDE.md,
> this file and everything they import should stay under 200 lines together.

## Project in one sentence

<What the project does.>

## Active agents and pipeline

`/business-analyst` (level 0: the owner's goals → `.engine/goals.md`; architects cite its lines; as `guardian` it checks the design against them) →
`/master-architect` (project design) → `/feature-architect` (feature → slice DAG) →
`/plan-slice` (slice contract) → `slice-builder` (TDD build) → `overseer` (audit,
auto-triggered by the Stop hook). Before the code of a planned slice the `test-manager` decides who writes its contract tests — the `slice-tester`, who never sees the code, or the builder — and after it what else is checked or deferred (`testing.py`). `/mvp-architect` designs the cheapest thing that answers one
question. `simplifier` finds what can go, on a signal only. Agents talk through files, never chat.

## Key paths

| Path | What it is |
|---|---|
| `.claude/constitution.md` | The rules every agent obeys. Human-only. |
| `.claude/engine-rules.md` | The engine's standing policy (installed by engine.py; do not edit here) |
| `.claude/references/` | Read on demand: `hooks.md`, `unattended.md`, the design playbooks |
| `.claude/project.env` | Source dirs, check commands and gates for the hooks |
| `.engine/goals.md` | The project's goals, approved by the owner; changed only by the owner's answer |
| `.engine/` | What the agent produces: records, slice contracts, architecture, premises, PROGRESS |
| `tasks/` | The task board: the owner drops task files, the agent works from them (`tasks/README.md`) |
| `<src/>`, `<tests/>` | The code and its tests |

## Verifying a change

`<the test command>`; `<the lint command>`; `<the type-check command>`. The Stop hook runs
them when code changed. A claim of "done" names the test and shows its output.
