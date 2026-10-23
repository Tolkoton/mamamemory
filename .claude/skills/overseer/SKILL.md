---
name: overseer
description: |
  How to get a developer turn audited against the 12-check discipline checklist
  (false-DONE, fabricated RED, decision conflation, masked test gaps, stale
  evidence, soft verdicts on hard data, missed alternatives, chat-only designs,
  handoff WHY missing, hardest seams unnamed, scope drift, bias-toward-agreement).
  Invoke this skill FIRST whenever you are asked to "run overseer", "review the
  last turn" or "apply overseer checks", or when the Stop hook answers
  OVERSEER_REQUEST: you do not audit yourself — the skill gives the two steps
  (make the request with a script, launch the agent `overseer`) that do.
---

# Overseer — how an audit is asked for

The audit is never done by the session that did the work. It is done by the
agent `overseer` (`.claude/agents/overseer.md`: the 12 checks, fresh context,
no editing tool), and its verdict is written into the ledger (this session's own file of it,
`.engine/journal/ledger/<session>.md`, board 739) by a script, `.claude/hooks/overseer_verdict.py`, from the agent's own answer.
You do not audit, you do not write the ledger, and a line `OVERSEER_PASS` typed
by you means nothing. Citing a check number (#1–#12) in your own reasoning is
just a reference; it needs no ledger entry.

## Claiming a unit complete (the Stop-hook trigger)

When to emit `=== UNIT N COMPLETE ===` and what to do on `OVERSEER_REQUEST <id>`
is in `.claude/engine-rules.md` § "Overseer protocol". What that section does
not say:

- Launch the agent with the Agent tool, `subagent_type: overseer`,
  `run_in_background: false`. A hook refuses any prompt but the request line:
  the auditor reads the request package (your final message, the commands that
  really ran, the contract), not your explanation.
- No valid verdict (the agent was not launched, its answer did not fit the
  schema, the tree changed during the audit) — the request is repeated, twice
  at most; then the item is parked and the turn ends.

## Asking for an audit by hand

"Run overseer on the last turn", "review the last turn":

1. The turn to audit must be a file. A turn recorded in a file is used as it
   is; a turn that exists only in this conversation you first write out
   VERBATIM, without tools of judgement — no summary, no correction — into
   `.engine/artifacts/overseer/turn-<date>.md`.
2. `python3 .claude/hooks/overseer_verdict.py request --turn-file <file> --unit <N>`
   — it writes the request package and prints the line to launch the agent
   with.
3. Launch the agent `overseer` with exactly that line, in the foreground.
4. Report its verdict to whoever asked: the verdict, the check, the reason —
   as the agent gave them — and its test gaps: since board 077 a missing or weak
   test is a PASS whose gaps the script has opened as proposals in `tasks/proposed/`
   (the owner puts one to work, board 111), never a BLOCK. Do NOT act on the verdict (no fix, no next unit)
   unless asked: an audit asked for by hand is a report.

`python3 .claude/hooks/overseer_verdict.py status` shows the pending request
and the last verdicts.

## Stopping the run — the builder's halt markers

These are the builder's statements that the run cannot continue, not verdicts.
On its own line, the Stop hook lets the turn end:

- `OVERSEER_SLICE_AWAITING_OWNER: <reason>` — the slice's remaining work is
  owner-driven (parked smoke, walkthrough, formal report) **and** no other
  slice is unblocked. If another slice can start, start it.
- `OVERSEER_SLICE_COMPLETE: <slug>` — the slice is closed: exit criterion met,
  smoke recorded, `.engine/PROGRESS.md` updated. Move to the next slice in the
  DAG; halt only if there is none.
- `OVERSEER_BLOCK: #N <reason>` / `OVERSEER_ESCALATE: <JSON>` /
  `OVERSEER_ADR_REQUIRED: <ADR>` — a finding you cannot resolve, a one-way door
  or an Article 5 product decision at a surface threshold, an ADR that needs
  the owner's ratification — **and** parking it leaves nothing that can move.

**Before any halt marker, check the queue.** A halt is a claim that nothing
else can move. A halt marker beside a unit-completion sentinel does not skip
the audit: the unit is audited first.

Attended, an escalation is surfaced with `AskUserQuestion`, options and
recommendation verbatim. Unattended, it is routed as the engine rules say; the
classification is made by the agent that benefits from classifying generously,
so when the door is ambiguous, treat it as one-way and park.

While the Stop gate has an open escalation on files of this work, no PASS is
recorded for it (the script writes a BLOCK instead). Only the owner closes the
escalation (`gate.py --close-escalation`, refused inside a session, or the
answer `так` under the gate's question in `tasks/blocked/`).

## A project whose settings lack the handlers

`overseer_verdict.py` works through two hooks in `.claude/settings.json`
(`SubagentStop` and `PreToolUse`); `engine.py install` and `update` put them
there, also into a settings file the project edited. Without them nothing can
record a verdict, and there is no other way to audit: the Stop hook answers a
claim with `OVERSEER NOT WIRED`, and `overseer_verdict.py request` refuses.
Do not audit the turn yourself — park the unit (human-only: `engine.py update`
adds the handlers) and take the next one. `overseer_verdict.py status` says
whether the project is wired.
