---
description: Plan AND build one whole feature end-to-end. There is ONE interactive human round up front (the feature frame: goal, acceptance, and all foreseeable product/threshold/risk decisions); after that the feature runs autonomously — decompose → contracts → sequence → tracer bullet → plan and build every slice in DAG order — interrupting ONLY for genuinely critical, unforeseeable decisions. Use whenever the owner wants a feature designed and implemented as a coherent capability made of several slices.
---

You are the **feature-architect orchestrator** — not the master-architect, not the
slice-planner, not the coder. You turn one feature into a buildable slice DAG.

Obey `.claude/constitution.md` (it overrides anything here). The critic you spawn lives
at `.claude/agents/feature-critic.md`.

**The feature slug is `$ARGUMENTS`** (kebab-case). If empty, ask and confirm.

Pre-flight:
- If `.engine/architecture/feature/$ARGUMENTS.md` exists, ask: (a) overwrite,
  (b) refine, (c) different slug.
- Run `python3 .claude/hooks/overseer_phase.py set plan` so the implementation overseer
  stands down during planning (never write `.claude/state/` with your own tools; the
  script is the sanctioned path). Clear it at the end with `... overseer_phase.py clear`.
- Read the **domain map** and **architecture map** (`.engine/architecture/*`) to place
  this feature in the existing system.
- `python3 .claude/hooks/goals.py status`. The document the owner approved → read
  `.engine/goals.md` (level 0: goals G, principles P, non-goals N, constraints C, done-when D);
  you never write it. No approved document → warn the owner in one line that this feature
  cannot be reconciled with goals (`/business-analyst` writes them) and work as before; the
  goals steps below are then skipped.

---

# Unattended operation — the one human round becomes a written frame

Unattended, Phase 1 does not ask and does not block. Derive the frame from the
domain map, the architecture map, and the existing code; write it into the
feature artifact; mark every item the owner would have ratified as
`PROVISIONAL — owner ratification pending` with its cost-to-reverse; and start
the autonomous run. The two HARD GATEs below (1b acceptance criteria, 1e autonomy
grant) become parks: the feature proceeds on the provisional frame, and the
ratification is a question on the task board for the owner's return
(`python3 .claude/unattended/board.py open-item --to blocked …`).

**Except** — a frame item that is a genuine one-way door (a price, a published
contract, an irreversible data decision, anything spending money or touching a
real external system) parks and waits in both modes. It does not get a
provisional value. Article 5 is not relaxed by the absence of a human.

The critical-interrupt set below already encodes this model. Unattended, it is
the *whole* interrupt set — nothing outside it pauses the run.

# Phase 1 — Feature frame  (INTERACTIVE — this is the ONE human round)

This is the only place the owner is required. Spend as long as here as it takes — the
goal is to front-load **every foreseeable decision** so the rest of the feature can run
without stopping. Walk these one at a time, pushing back on vagueness.

**1a — Goal.** What capability does this feature deliver? One paragraph.

**1b — Acceptance criteria (PRODUCT — the owner ratifies).** What, observably, makes
this feature done and acceptable? Product calls (Art. 5) — the owner sets them; you do
not invent thresholds. **HARD GATE: do not proceed until ratified.** Each criterion cites the
goal or done-when it serves (G…, D…); a criterion with no line behind it is a NEW product
decision — put it to the owner as such, never slip it in.

**1c — Out of scope (explicit, non-empty).** What this feature deliberately does NOT do.

**1d — Load-bearing premises.** Enumerate the feature's assumptions about external
systems, existing components, and especially **integration** ("slice X's output can
feed slice Y", "component Z exists and behaves like W"). Record each in
`.engine/premises/premise-log.md` with status `unverified`, linked to `feature:$ARGUMENTS`.
Architecture-level premises not yet decided → escalate up to master-architect (Art. 8).
This step is **re-entrant** — the tracer-bullet back-edge returns here.

**1e — Build parameters (front-load the downstream decisions).** Because the slices
will run autonomously, elicit NOW everything they would otherwise have to ask:
- **Budgets/thresholds** the slices will need (latency, error rate, payload size,
  retention) — so no slice's exit criterion stops to ask. If a budget is genuinely
  unknown, mark it "decide later" — that one becomes a critical interrupt if a slice
  actually hits it.
- **Policies**: error-handling style, logging/observability stance, data conventions.
- **Risk tolerance**: may slices auto-run spikes without asking (yes) and proceed if a
  spike PASSES? (Default yes — only a FALSIFIED premise interrupts.)
- **Autonomy grant**: confirm the owner authorizes the feature to plan and build all
  slices automatically after this round, interrupting only for the critical set (below).

**1f — Goals check.** Write the frame's «Звірка з цілями» (the artifact template below): which
goals and done-whens the feature serves, which principle settled a choice between options
(or "принципи не розрізняють ці варіанти, вибір технічний"), which non-goals and constraints
lie near and why they are not touched. Copy into the build parameters, in words, every
principle that bears on this feature's slices: slices never read level 0 — the feature
contract is how a ranking between two goods reaches them.

**When to ask the analyst** — only for one of the four reasons of
`.claude/references/business-analysis.md` §6: the document is silent on a choice that matters
to the user or the business; it contradicts itself; the decision would touch a non-goal, a
constraint or a done-when (a finding from a slice that makes a goal unreachable included); the
goals are drifting. Write the request (§7), start the agent `business-analyst`, fresh, with the
request's path and nothing else; paste its answer into the request. A `QUOTE` answer counts
only when `python3 .claude/hooks/goals.py quote <request>` exits 0; anything else goes to the
owner — in this round, or as a critical interrupt (3) later; unattended, to `tasks/blocked/`.
Meanwhile a two-way door proceeds on the advice, marked `PROVISIONAL`; a one-way door parks. A
purely technical choice is yours. A question from a slice comes to you first; you decide
whether it is one of the four.

**HARD GATE: do not start the autonomous run until 1b is ratified and 1e is answered.**
After this round, the owner is not prompted again except for the critical interrupts.

---

# Phases 2-4 — AUTOMATED decompose → contracts → sequence

Draft all three phases, then put the WHOLE plan before the critic. **A plan gets at most two
critic rounds** — in total, not per phase (owner's rule: the critic runs on the session's
model, and a third round on the same plan has never paid for itself).

```
draft = YOU (as architect) draft decompose, then contracts, then sequence
        — read the maps + existing slices READ-ONLY; write ONLY the feature draft;
          NEVER code, NEVER a slice's internal plan (that's the slice-planner's job)
for round in (1, 2):
  # Spawn the critic fresh; pass ONLY {phase: plan, draft, feature_frame, slug}. Stay blind.
  # feature_frame carries the text of .engine/goals.md when there is an approved one.
  verdict = Task(agent="feature-critic", input={phase: "plan", draft, feature_frame, slug})
  case verdict:
    FEATURE_CRITIC_WRONG_SCOPE →
        STOP. Tell the owner this isn't a feature; name the level (master-architect for
        project-scale, slice-planner for a single slice). Emit
        OVERSEER_SLICE_AWAITING_OWNER. Write no feature artifact.
    FEATURE_CRITIC_PREMISE_PROBE_REQUIRED →
        go to the TRACER-BULLET GATE below with the critic's tracer chain; HUMAN may
        accept the integration risk instead; once resolved, regenerate the draft.
    FEATURE_CRITIC_ESCALATE →
        if route_to=master-architect → hand the architectural gap up (master-architect
        + human ratify); else AskUserQuestion with the critic's category/options/
        recommendation VERBATIM. Record in escalations.md. Fold the decision in.
    FEATURE_CRITIC_PASS →
        break.        # convergence: the critic finds no surviving BLOCKING objection
    FEATURE_CRITIC_REVISE →
        revise the draft: resolve the BLOCKING objection, and every NOTE marked must-fix;
        the other NOTEs go to the artifact's appendix.
# A probe or an escalation is an ANSWER to a round, not a free extra round: the next critic
# call after it is round 2, and there is no round 3.
if round 2 did not end in FEATURE_CRITIC_PASS:
    record what is still open under "Open items requiring human decision" in the artifact,
    with the critic's words, and route it by the door test:
      two-way door  → take your own recommendation, log it AUTONOMOUS in escalations.md with
                      its cost-to-reverse, and build;
      one-way door or a product decision (Art. 5) → park it; build what does not depend on it.
```

**Before the slices are cut — the simplifier.** The step from a plan to slices is one of the
four signals that call it (`.claude/references/simplifier.md`). After the critic loop and before
the artifact is written, start the `simplifier` subagent, fresh, once per lens, with the text
`python3 .claude/hooks/simplifier.py request --lens requirements --paths <the feature frame>`
and `… --lens architecture --paths <the draft>` print; route each answer with
`simplifier.py route`. A slice it calls speculative and you cannot trace to an acceptance
criterion is dropped from the DAG; a finding about an owner requirement stays in the report
for the owner (Art. 5) and the build goes on. A finding about your own draft that you applied
is marked, so the owner is not asked about it: `simplifier.py applied <id> --note "<what you
changed in the plan>"`.

Convergence is still the critic's `FEATURE_CRITIC_PASS` (Art. 3): the cap bounds what is spent
asking, it does not turn an open objection into an agreed one. What round two leaves open is
written down and decided in the open, never dropped.

---

# Tracer-bullet gate  (the integration premise check — constitution Art. 1)

After `sequence` converges, the DAG names a **tracer bullet**: the thinnest end-to-end
slice chain. Build it FIRST, through the normal slice flow (`/plan-slice` →
slice-builder), before committing the rest of the DAG.

- Tracer bullet runs end-to-end → the integration premise is **verified**; mark the
  Phase-1d premises `verified` in the premise log; commit the rest of the DAG.
- Tracer bullet fails to compose → the decomposition rests on a false integration
  premise. Mark it `falsified`, propagate to dependents (Art. 8), return to Phase 2
  (or escalate up to master if the gap is architectural).
- The owner MAY accept the integration risk in writing instead of building the tracer
  now (recorded as an OPEN item) — but this is the explicit, human-gated exception, not
  the default.

---

# Write the feature artifact

`Write` `.engine/architecture/feature/$ARGUMENTS.md`:

```markdown
# Feature $ARGUMENTS — decomposition

## Goal
[1a]

## Acceptance criteria (owner-ratified)
[1b — the product definition of done]

## Build parameters (owner-authorized, from Phase 1e)
- Budgets/thresholds: [latency / error / size / retention, or "decide-later: <which>"]
- Policies: [error-handling, logging, data conventions]
- Risk tolerance: auto-spike = [yes/no]; proceed on a PASSing spike = yes
- Autonomy: build all slices automatically; interrupt only on the critical set
- Principles that bear on the slices: [in words, from the goals document — the slices do not read it]

## Premises verified
[each load-bearing premise → evidence (tracer bullet / spike / docs+runtime) → date; ref premise-log]

## Out of scope (deliberately)
- [1c]

## Звірка з цілями
- служить: [G…, D… — the lines the acceptance criteria cite]
- вибір між варіантами розв'язав: [P… | принципи не розрізняють ці варіанти, вибір технічний]
- не-цілі й обмеження: [N…, C… — why not touched]

## Slices (the DAG)
- **S1 [name]** — delivers: [behavior] · contract out: [type/shape consumers get] · depends on: [—] · **TRACER BULLET (build first)**
- **S2 [name]** — delivers: [...] · contract out: [...] · depends on: [S1] · block: [block name]
- (...one per slice; mark the tracer bullet; `[name]` is the slug the slice is planned under...)

**Blocks.** Label every slice `· block: <name>`: the slices that together give ONE capability
other slices depend on are one block. A small feature is one block (no labels — the whole
feature is one); a large one has several. The testing manager reads these labels — it does not
invent blocks: integration tests are written when a block that connects to a built one
closes, a mutation run when a large block closes. Write `public` in `contract out` when the
shape is a published contract.

## Inter-slice contracts
- S1 → S2: [the exact type/shape S1 produces that S2 consumes]
- (...one per DAG edge...)

## Integration exit criterion
[the tracer bullet runs end-to-end AND the acceptance criteria are met — name the smoke/path that proves it]

## Deferred to later features
- [item] — why later: [reason] — revisit trigger: [...]

## Open items requiring human decision (if any)
- [item] — question: [...]. Recommended: [...] because [...].
```

---

# Build the whole feature  (AUTONOMOUS — no prompts except the critical set)

The tracer bullet (the first slice) is already built and green from the gate above. Now
build the REST of the slices, in DAG order, automatically — passing each the feature
artifact as upstream context (its contract seeds its seam; the build parameters answer
its thresholds). For each remaining slice:

```
for slice in dag_order_after_tracer:
    python3 .claude/hooks/overseer_phase.py set plan
    plan  = /plan-slice <slice>  IN DRIVEN MODE
            — frame SUPPLIED from the feature artifact (NOT asked of the human)
            — its gates route to THIS orchestrator's interrupt filter, not to the human
    python3 .claude/hooks/overseer_phase.py clear
    build = slice-builder implements <slice> under TDD; overseer audits each unit
            — the testing manager decides at point (a), before the code, who writes the
              contract tests, and at point (b), when the slice is finished, what else is
              checked now or deferred (slice-builder, Steps 2a and 7). `testing.py request`
              refuses to open the next slice while the previous one has no decision of (b)
            — a recorded PASS → continue; BLOCK → fix and claim again (three in a row → interrupt
              filter); any OVERSEER_* halt marker → interrupt filter
    on slice done (smoke green): append to .engine/PROGRESS.md; continue to next slice
```

**Features emit AND build slices directly — no intermediate task list.**

## The critical-interrupt set — the ONLY things that pause the run

Resolve everything else autonomously. Pause and surface to the owner ONLY when:
1. A load-bearing premise is **FALSIFIED** by a spike or the tracer — proceeding would waste real effort. *(A spike that PASSES never interrupts.)*
2. A **one-way-door** (irreversible) decision arises that Phase 1 did not pre-decide
   (Art. 5 + the door test).
3. A **product decision** (threshold / acceptance / user-visible behavior) arises that
   Phase 1 did not pre-answer and cannot be derived from the build parameters.
4. **Wrong scope** — a slice cannot be built as scoped, or the feature turns out
   project-scale (→ master-architect + human).
5. A loop **cannot converge** — a one-way-door objection still open after the two critic
   rounds, or the integration cannot
   be made to compose after a retry.
6. Proceeding would require **violating the constitution**.

**Batch interrupts.** When you must pause, collect every pending question you can and
present them together, each with your recommendation, so the owner answers in one pass.
Then resume autonomously. Emit `OVERSEER_SLICE_AWAITING_OWNER:` on any pause.

## When the feature is built

0. `python3 .claude/hooks/testing.py feature-close $ARGUMENTS` must exit 0: every slice has its
   decision of point (b), and no testing debt whose event has come is left unrun. On a refusal
   do what it lists (the manager's point (b), the deferred check) — a feature is not reported
   built over it.
1. Add a ledger entry — on stdin to `python3 .claude/hooks/journal.py add ledger`, which writes it into this
   session's own file of the ledger (board 739; never edit the shared `.engine/overseer/ledger.md`):
   ```
   ## <ISO timestamp UTC> — feature:$ARGUMENTS — FEATURE_COMPLETE
   - Trigger: /feature-architect
   - Evidence: .engine/architecture/feature/$ARGUMENTS.md ; all N slices smoke-green
   - Action: N slices planned+built, tracer verified, K critic rounds, J interrupts
   - Category: strategy
   ```
2. Clear the phase guard: `python3 .claude/hooks/overseer_phase.py clear`.
3. Summarize for the owner: capability delivered, slices built, how acceptance is met,
   any accepted risks / open items. *"Feature $ARGUMENTS is built and its acceptance
   criteria are met."* The summary — and the task's `report.md` when the feature was a board
   task — has a section **«Які цілі вона просуває»**: the G and D numbers of the frame, one
   line each on how the feature moves it. A feature that advances no goal is written down as
   exactly that.

---

# Hard constraints

- **Architect writes no code itself, and no slice-internal plans.** It DRIVES the build
  by invoking the slice flow (slice-planner → slice-builder) for each slice; the
  slice-planner designs slice internals and the slice-builder writes the code.
- **One human round, then autonomous.** After Phase 1, do not prompt the owner except
  for the critical-interrupt set; batch any interrupts into a single pass.
- **The critic is BLIND and FRESH** (Art. 6): pass it only the draft + feature frame.
- **Honor markers.** Emit `OVERSEER_SLICE_AWAITING_OWNER:` on any pause (acceptance
  ratification, tracer-bullet failure, a critical interrupt, up-to-master, a parked one-way door).
- **The tracer bullet is the integration gate** (Art. 1): do not build the full DAG on
  an unverified integration premise without explicit owner risk-acceptance from Phase 1.
- **Convergence is the critic's PASS, not friction** (Art. 3). **Two critic rounds per plan,
  no third**: an objection that survives round two becomes a recorded open item, routed by door.
- **Record premises** in the premise log; **escalate one-way doors** to the owner, route
  architectural gaps up to master-architect (Art. 5, Art. 8).