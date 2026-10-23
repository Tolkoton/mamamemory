# Self-improvement audit log

Proposals to change what no agent may edit itself (constitution, Article 7): an
agent's or a skill's definition, the constitution, the hooks' rules. The agent
that sees the need appends a proposal here; only a human ratifies it and makes
the edit (propose → human-ratify → replay). Append-only.

The overseer does not write here. It is a separate agent without an editing
tool; its verdicts are recorded by `.claude/hooks/overseer_verdict.py`, and what
its BLOCKs teach goes to the lesson queue (`.claude/hooks/lesson_queue.py`). A
lesson that should become a standing rule is asked of the owner as a board task
(`tasks/blocked/8NN-rule-proposal-…`) and reaches `.engine/rules.md` only on the
answer «так». A settings change is proposed in `docs/tasks/` and applied by the
owner.

## Proposal format

```
## <ISO timestamp UTC> — <proposed change>
- Evidence: <ledger entries supporting this — minimum 3 cited>
- Rationale: <why this would improve the overseer>
- Risk: <how this could go wrong>
- Status: PROPOSED | RATIFIED | REJECTED
```

## When to propose

- A pattern fired 5+ times across 3+ slices and is not in the current
  12-check checklist → propose adding it.
- A current check fires often but is reversed by the human in
  escalations.md → propose tuning or removal.
- A class of escalation is consistently waved through → propose
  autonomous handling.

## What NOT to propose

- Removing any check just because it triggers BLOCKs frequently. Frequent
  BLOCKs are the point. Anti-Goodhart.
- Adding checks that mimic existing tooling (linters, type checks).
- Lowering the citation-or-prune threshold.

---
