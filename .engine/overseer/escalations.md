# Overseer escalations log

> **History only.** Everything open lives on the task board (`tasks/`) and is closed by moving to `tasks/done/`. This file is only appended to; nothing in it is marked closed, and nothing reads it to learn what is open.

Records every PRODUCT_DECISION / BLOCKER_CLASSIFICATION / DESIGN_FORK /
ADR_RATIFICATION escalation and the human's resolution. Used in the
2-week audit to tune escalation thresholds.

## Entry format

```
## <ISO timestamp UTC> — <category> — <slice slug>
- Question: <text>
- Options offered: <list>
- Recommendation: <overseer's pick + one-line rationale>
- Human chose: <final decision>
- Latency to decision: <minutes/hours>
- Notes: <if human changed mind, if recommendation was wrong, etc.>
```

## Audit signal interpretation (re-read at the 2-week mark)

- **Human waved through immediately, picked recommendation as-is** → next
  time, this class of question can likely be handled without escalation.
  Propose change in audit.md.
- **Human reversed the recommendation** → overseer is over-confident on
  this class. Tune the check prompt; consider weakening the recommendation
  language.
- **Human deliberated long, chose other** → correct escalation, healthy
  use of human time.

---

## Second entry format — AUTONOMOUS two-way-door decisions

The format above has no slot for a decision the AI made itself: every field
(`Human chose`, `Latency to decision`) presumes a human answered. But the engine
rules' verdict routing says a two-way door is *logged here and continued*, not
escalated. A decision with nowhere to be recorded stays open in working memory
and gets re-raised turn after turn, which is a stop wearing a question mark.
Hence this second shape:

```
## <ISO timestamp UTC> — AUTONOMOUS — <item id>
- Decision: <what was decided, in one line>
- Door: two-way
- Cost to reverse: <concretely, what it would take>
- Why not escalated: <which Article 5 test it passes>
- Evidence: <what made this the right call>
- Falsified by: <the observation that would make this wrong>
- Status: CLOSED
```

**CLOSED means closed.** Once an entry exists here, the decision is not an open
question. Re-raising it with the owner is not diligence — it is an illegitimate
stop, because it asks a human to ratify something Article 5 assigns to the AI.
If new evidence genuinely falsifies it, append a NEW entry that supersedes this
one; do not reopen the old one in conversation.

---
