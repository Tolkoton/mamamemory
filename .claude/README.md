# Agentic system — map & integration guide

This is the **map** of the agentic system that operates on this repo: which
agent produces which artifact, who consumes it, and who hands off to whom.
Read it before adding a new agent — it shows where a new part fits and what
communication contract it must honour.

This file **maps**; it is not the source of truth for any agent's behaviour.
Each agent's behaviour lives in its own definition (see
[§7 Where definitions live](#7-where-the-definitions-live)). When this map and
a definition disagree, the definition wins — and this map is stale and should
be fixed.

**Tag legend:** `[project]` = repo-native, defined only in this repo's
`.claude/`. `[vendored]` = a skill **copied** into `.claude/skills/` from
`~/.claude/skills/` so the repo is self-contained — it is a **fork**; upstream
changes are not picked up automatically (see §8). `[global]` = still defined
only in `~/.claude/` (the subagents and some commands were not vendored).

---

## 1. The 30-second model

Agents communicate through **files (artifacts), never through chat**. There are
four cooperating layers:

| Layer | What it does | Lives in |
|---|---|---|
| **Design** | Turns intent into a task/slice plan | `.engine/architecture/`, `.engine/slices/` |
| **Build** | Writes code + tests under TDD | source dirs, `tests/`, `scripts/` |
| **Enforce** | Hooks + overseer keep discipline | `.claude/hooks/`, `.engine/overseer/` |
| **Remember** | Distils lessons across sessions | `.engine/PROGRESS.md`, memory files, `.engine/lesson-queue.md` |

One build pipeline is active:

**Slice flow.** `master-architect` (design) → `slice-builder` / the developer
agent (build) → `overseer` (audit). Plans live in
`.engine/slices/<slug>.md`; history in `.engine/PROGRESS.md`.

---

## 2. Component catalog

| Component | Tag | Kind | One-line role |
|---|---|---|---|
| `master-architect` | `[vendored]` | skill | 5-phase design → architecture handoff |
| `feature-architect` | `[vendored]` | skill | Splits an oversized task into a DAG of sub-tasks |
| `slice-builder` | `[vendored]` | skill | Builds one thin vertical slice (seam-first TDD) |
| `self-learning-orchestrator` | `[vendored]` | skill | Dispatches the memory lifecycle at each dev moment |
| `documentation` | `[vendored]` | skill | Maintains AGENTS.md / ADRs / `docs/` (this guide's skill) |
| `overseer` | `[project]` | skill | 12-check discipline audit of the last turn |
| `plan-slice` | `[project]` | command | Writes a slice contract before implementation |
| `business-analyst` | `[project]` | command + agent | Level 0: writes the goals document with the owner (command); answers an architect's request about it with a verbatim quote or a question for the owner (agent, read-only) |
| 9 hooks | `[engine]` | hooks | Enforcement (see [§4](#4-the-enforcement-layer-hooks)) |

---

## 3. Artifact catalog — who writes, who reads

Paths are **this repo's** locations. The `lifetime` column tells a builder how
volatile the artifact is.

| Artifact (this repo) | Producer(s) | Consumer(s) | Lifetime |
|---|---|---|---|
| `.engine/architecture/INDEX.md` | `master-architect` | architect, humans | per phase |
| `.engine/architecture/phase-0-brief.md`, `phase-1-system.md` | `master-architect` | `slice-builder` (context) | append/superseded |
| `.engine/architecture/phase-2..4*` | `master-architect`, `feature-architect` | `slice-builder` | created per phase |
| `.engine/architecture/PROGRESS.md` | `master-architect` | architect (resume) | per session |
| `.engine/goals.md` | `/business-analyst` with the owner; amended only on the owner's answer (`goals.py`) | the architects and their critics — never the slice level | sealed; numbers permanent |
| `.engine/goals/requests/NNN.md`, `proposed.md`, `to-review.md` | the architects (requests), the analyst (the amendment), `goals.py` (what to reread) | the agent `business-analyst`, the owner's review | per request / per amendment |
| `.engine/slices/<slug>.md` | `plan-slice`, developer | `overseer` (load-bearing), developer | per slice |
| `.engine/overseer/ledger.md` | `overseer` | `overseer` (counts PASS streak) | append-only |
| `.engine/overseer/MEMORY.md` | `overseer` | `overseer` | cross-slice, cited-or-pruned |
| `.engine/overseer/audit.md` | any agent (a proposal) | humans (ratify, Article 7) | append-only |
| `.engine/overseer/escalations.md`, `parked.md` | any agent (a decision already made; a park where there is no board) | `overseer` | history: append-only, nothing in them is closed — what is open is a task in `tasks/` |
| `.claude/state/overseer/state` | (manual / planning) | `overseer_stop.py` (phase guard) | ephemeral |
| `.claude/state/overseer/.last_audit_sha`, `.last_continue_sha` | `overseer_stop.py` | `overseer_stop.py` (recursion guard) | ephemeral |
| `.engine/artifacts/spikes/*` | developer, smoke/probe scripts | `.engine/PROGRESS.md`, ADRs | dated, kept |
| `.engine/artifacts/notes-during-session.md` | developer | developer | scratch |
| `.engine/PROGRESS.md` (root) | `slice-builder`, developer | `overseer`, `self-learning-orchestrator`, humans | append-only |
| `CLAUDE.md` (root) | `documentation`, `self-learning-orchestrator` (rare, confirmed) | **every agent** (always loaded) | rare |
| `AGENTS.md` (root) | `documentation` | every agent (via `@AGENTS.md`) | with code changes |
| `docs/adr/NNNN-*.md` | `documentation`, `master-architect`, developer | every agent, humans | **append-only / supersede** |
| `.claude/settings.json` + 9 hooks | `engine.py install` (shipped from the engine repository) | Claude Code harness (session start) | rare |
| `.engine/lesson-queue.md` | hooks (gate, overseer, parked, escalation) and the developer (`lesson_queue.py`, rule in `self-learning-orchestrator`) | the session-end trigger of the same skill | the overseer-PASS review request; drained by triage |
| `~/.claude/memory/<tech>/MEMORY.md` `[global]` | `self-learning-orchestrator` | all (session start) | per session-end |
| `claude-progress.md`, `<task>/reflections.md` | `self-learning-orchestrator` | same | created on demand |

---

## 4. The enforcement layer (hooks)

All 9 are `[engine]`, installed by `engine.py`, wired in
`.claude/settings.json`. They are the harness-executed guardrails every agent
runs inside.

| Hook | Event | Gates / effect | Artifacts touched |
|---|---|---|---|
| `block-dangerous.sh` | PreToolUse `Bash` | Blocks destructive patterns **and `git commit`** | — |
| `protect-paths.sh` | PreToolUse `Edit/Write/MultiEdit` | Blocks `.env`, `secrets/`, `migrations/`, `.git/`, workflows | — |
| `format-on-edit.sh` | PostToolUse `Edit/Write/MultiEdit` | `ruff format` + import-sort on `.py` | edited `.py` |
| `verify-on-stop.sh` | Stop | `ruff` + `mypy` + `pytest` on changed Python; blocks turn on fail | — |
| `overseer_stop.py` | Stop | Triggers the overseer audit on a unit-completion claim | reads/writes `.engine/overseer/{state,.last_*_sha}` |
| `auto-approve-web.py` | PreToolUse / PermissionRequest `WebFetch/WebSearch` | Auto-approves read-only web access | — |

`verify-on-stop.sh` enforces lint + type-check + tests on every turn where
Python files changed. See [§5](#5-cooperation--dataflow) for the full flow.

---

## 5. Cooperation & dataflow

### Slice flow

```mermaid
flowchart TD
  user([owner intent]) --> MA[master-architect]
  MA -->|writes| ARCH[".engine/architecture/* (phases, INDEX)"]
  MA <-->|split / overflow| FA[feature-architect]
  PS["/plan-slice"] -->|writes| SC[".engine/slices/&lt;slug&gt;.md"]
  SC --> SB[slice-builder / developer]
  ARCH --> SB
  SB -->|writes| CODE["&lt;source-dirs&gt; + tests/ + scripts/smoke_*"]
  SB -->|appends| PROG[.engine/PROGRESS.md]
  CODE --> STOP{{Stop hooks}}
  STOP --> VOS[verify-on-stop.sh]
  STOP --> OST[overseer_stop.py]
  OST -->|on unit-complete sentinel| OV[overseer skill]
  SC --> OV
  PROG --> OV
  OV -->|appends| LED[".engine/overseer/ledger.md"]
  OV -->|PASS| OST
  OST -->|re-inject 'continue'| SB
  OV -->|ESCALATE / ADR / BLOCK| user
```

### Memory lifecycle (cross-cutting)

```mermaid
flowchart LR
  moment([dev moment]) --> SLO[self-learning-orchestrator]
  SLO -->|session start, reads| MEM["MEMORY.md files + .engine/PROGRESS.md + docs/adr/"]
  LES["lesson capture (in flow)"] -->|append| LQ[".engine/lesson-queue.md"]
  WRAP["session end"] -->|drains| LQ
  WRAP -->|classify into| MEM
  STK["stuck protocol"] -.->|tier 2/3| dbg[debug loop / re-plan]
  MM["periodic maintenance"] -->|prune / promote| MEM
```

---

## 6. How to add a new agent

A new agent integrates by honouring the **artifact contract** above — not by
calling other agents directly. Checklist:

1. **Pick the layer** (design / build / enforce / remember). State it in the
   agent's own doc.
2. **Declare its artifacts.** List what it **produces** and **consumes** using
   the paths in [§3](#3-artifact-catalog--who-writes-who-reads). Reuse an
   existing artifact where possible; introduce a new one only if no existing
   contract fits. Prefer files under `.claude/` for this repo.
3. **Wire triggers & handoffs.** Decide what invokes it (user phrase, a hook,
   or another agent's handoff) and who it hands off to. If it joins the slice
   loop, it must respond to the overseer's `OVERSEER_PASS` → continue cycle and
   emit a halt marker (`OVERSEER_SLICE_AWAITING_OWNER:` etc.) when done.
4. **Respect the gates.** Anything that edits code passes
   `verify-on-stop.sh` (lint + type-check + tests) at turn end.
5. **Never commit.** `git commit` is hook-blocked; agents stage and report, the
   human commits.
6. **Register it.** A skill → `~/.claude/skills/<name>/SKILL.md` (or
   `.claude/skills/` if repo-local); a subagent → `~/.claude/agents/<name>.md`;
   a command → `.claude/commands/<name>.md`; a hook → `.claude/hooks/` **plus**
   an entry in `.claude/settings.json`.
7. **Update this map.** Add the component to [§2](#2-component-catalog) and its
   artifacts to [§3](#3-artifact-catalog--who-writes-who-reads). The change is
   not done until this guide reflects it.

---

## 7. Where the definitions live

This map points; it does not restate. For behaviour, read the source:

- Skills: all under `.claude/skills/<name>/SKILL.md` — `overseer` is
  repo-native; the other 5 are **vendored** copies (keep them in sync manually — see §8).
- Subagents (critic agents): `.claude/agents/*.md` — repo-native.
- Commands: `.claude/commands/{business-analyst,plan-slice,master-architect,feature-architect,mvp-architect,owner-review,onboard,bugfix,hotfix,maintain}.md`.
  The memory lifecycle has no slash commands: the `self-learning-orchestrator` skill reacts
  to the moments its SKILL.md lists (session start, a decision, being stuck, wrapping up).
- Hooks: `.claude/hooks/*` (wired in `.claude/settings.json`).
- Standing policy: `.claude/engine-rules.md` (imported by `CLAUDE.md`) + `AGENTS.md` (root).

---

## 8. Vendoring & path conventions

**All paths are under `.claude/`.** Every skill in this repo uses the `.claude/`
prefix for its artifacts: `.engine/architecture/`, `.engine/overseer/`,
`.engine/artifacts/`. There is no root-level `.architecture/` or `artifacts/`
directory. When reading a skill, all paths are taken as written.

**Note for `references/madr-format.md` and `references/c4-mermaid-syntax.md`.**
These describe `master-architect`'s default output location as `.architecture/`
because that skill is designed to be configurable per project. When using it here,
override to `.engine/architecture/`.

**Vendoring (the 5 `[vendored]` skills).** Copied from upstream into `.claude/skills/`
to make this template self-contained. No global `~/.claude/skills/` directory exists
on the machine, so there is no double-discovery issue. Consequences:

- **Fork / drift.** Copies do not track upstream automatically. If an upstream skill
  improves, re-copy it into `.claude/skills/` to pick up the change.
- **Single source.** The `.claude/skills/` copies are the only copies. Any project
  using this template gets exactly what is here.
