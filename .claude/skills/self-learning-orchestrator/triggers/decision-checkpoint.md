# Trigger: Decision Checkpoint

A real engineering decision was about to be (or just was) made. Decide whether it warrants an ADR entry, and if so, capture it.

## When this fires

Three signals — any one is enough:

1. **Explicit user phrasing**: "we picked", "going with", "let's use X over Y", "trade-off", "why did we choose".
2. **Self-recognition in your own reasoning**: you just chose between real alternatives (not forced by constraints).
3. **Pre-commit check** (from `triggers/pre-commit-checkpoint.md`) noticed a substantive change without a corresponding ADR.

## Two-step filter

Before writing anything, run the filter. Most "decisions" are not ADRs.

### Filter 1: Was there really a choice?

If the answer was forced by external constraint (only one library available, regulation requires X, existing code already uses Y), this is a **constraint**, not a decision. Record it in CLAUDE.md's "Constraints" section, not in an ADR. Skip the rest of this trigger.

### Filter 2: Would someone re-litigate this in 6 months?

Imagine yourself or a teammate reading the code in 6 months, thinking "why did we do this when X seems obviously better?" If the answer is yes — write the ADR. If the answer is no (the choice is obvious in retrospect to anyone familiar with the domain) — skip; the code is self-documenting.

A useful heuristic: if you can explain the choice in a single inline comment, do that and skip the ADR. ADRs are for choices that *need a paragraph* of context.

## If both filters pass: write the ADR

Write it as `docs/adr/NNNN-short-kebab-title.md` — the next free number, never renumbered (create
the directory if missing). The format, the status lifecycle and the first ADR of a project are in
`.claude/skills/documentation/references/adr-template.md`; use that template, not a second one. This
is the ADR the overseer's check #8 looks for and the one `ADR_REQUIRED` asks for.

## When this trigger should ALSO update CLAUDE.md

If the decision establishes a **rule** that should apply automatically from now on (e.g., "all money handled as Decimal, never float"), the rule belongs in CLAUDE.md, with a cross-reference to the ADR:

```markdown
# CLAUDE.md
## Conventions
- Money is the `Money` dataclass; never raw Decimal or float. (See ADR-0007.)
```

Without the rule in CLAUDE.md, the decision lives in `docs/adr/` but Claude won't apply it consistently. The ADR is the WHY; the CLAUDE.md line is the WHAT.

## When this trigger should NOT update CLAUDE.md

- The decision is project-specific tactical (e.g., "use PostgreSQL 16 specifically, not 15") — that's a constraint, not a convention.
- The decision is one-off (we're doing X this once, not establishing a pattern).
- The decision is reversible cheaply (no need to bake into the steering doc).

## Show the user, then write

Even after the filters pass, never write an ADR silently. Show the proposed ADR. Get confirmation. Then commit it in the **same commit** as the code that implements the decision. Code without ADR loses the why; ADR without code is fantasy.

## Common mistakes to avoid

- **Writing 5 ADRs in one day.** This is decision-theatre. Most of them are tactical implementation choices. Re-run the filters.
- **Writing the ADR before the decision is real.** "We might use X" is not an ADR. Wait until you commit to it.
- **Writing the ADR and forgetting CLAUDE.md.** Then the rule doesn't get applied.
- **Writing the ADR but no cross-reference from the relevant code.** Future code archaeologist won't find it. At least put `# See ADR-NNNN` in the code.
- **Status: Proposed forever.** Either accept or reject. Drafts are noise.

## What about superseding an old decision?

If today's decision overrides an accepted ADR:

1. Write the new ADR as normal, with the line `Supersedes ADR-NNNN`.
2. In the old ADR, change only the status line to `Superseded by ADR-MMMM`.
3. In the new ADR's Context, briefly explain what changed.
4. **Do not delete or edit the old ADR's text.** The supersession chain is the history.

## After writing

Return to the task that prompted the decision. The detour was 5–15 minutes; that's the cost. The benefit is months of "wait, why did we do this?" avoided.
