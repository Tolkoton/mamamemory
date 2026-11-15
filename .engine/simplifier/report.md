# Simplifier — findings for the owner

Nothing listed here was removed.

## 2026-11-05T20:36:21Z — requirements, before M4

### confirm (0)

### flag_only (0)

## 2026-11-05T20:36:33Z — architecture, before M4

### confirm (0)

### flag_only (1)
- APPLIED BY THE ARCHITECT `F-a81ae2e0` **.engine/architecture/architecture-map.md:226-237** — duplication: The M2 convention 'Запис плану: один процес на план' restates the rule already given in M2's plain-words bullet at lines 54-58; the only new content is the base32hex event id and the events.list recognition. The M3 plan.py bullet adds a third copy. The repeated server allowlist rule at lines 238-239 duplicates lines 71-72 and 398-400.
  - applied to the plan 2026-11-05T20:36:49Z: конвенцію «Запис плану» скорочено до посилань і нових деталей (base32hex, events.list); дубль правила входу замінено посиланням — nothing is asked of the owner
  - evidence: read .engine/architecture/architecture-map.md:54 запис плану веде лише один процес; read .engine/architecture/architecture-map.md:226 Запис плану: один процес на план; read .engine/architecture/architecture-map.md:238 Сервер пропускає лише мамин акаунт
  - test safety none, reversal risk low, protected false, traces to: G1

## 2026-11-05T21:25:00Z — f1-skeleton architecture, before slices

### confirm (0)

### flag_only (0)

## 2026-11-05T21:25:05Z — f1-skeleton requirements, before slices

### confirm (0)

### flag_only (0)

## 2026-11-07T02:00:29Z — F3 plan — requirements

### confirm (0)

### flag_only (0)

## 2026-11-07T02:00:29Z — F3 plan — architecture

### confirm (0)

### flag_only (1)
- APPLIED BY THE ARCHITECT `F-503b525a` **.engine/architecture/feature/f3-cases-intake.md:99-100** — premature_abstraction: The material record carries both `pending_case: <назва>|null` and `closed_question: bool` for one state, whether a «створити справу?» is still open. No slice in the plan reads `closed_question` apart from `pending_case`: `cases.pending` (line 103), «не треба» (S3, line 87) and the move closing the question (S4, line 93) can all work by setting `pending_case` to null. So the bool could go, and two fields would no longer have to agree.
  - applied to the plan 2026-11-07T02:00:44Z: closed_question dropped from the materials schema; an open question is pending_case set, closed is pending_case null — nothing is asked of the owner
  - evidence: read .engine/architecture/feature/f3-cases-intake.md:99 schema lists both pending_case and closed_question; read .engine/architecture/feature/f3-cases-intake.md:122 the S1 to S3 contract names only `pending_case` and `created` as the waiting state that S3 reads through `cases.pending`; grep .engine/architecture/feature/f3-cases-intake.md:100 'closed_question' appears only in this schema line in the repository (board-runner.sh has an unrelated sweep_closed_questions); judgement  I found no reason written for the bool. One possible reason is keeping the proposed name after «не треба», but no slice reads that name. This is a lead for the owner, not proven redundancy.
  - test safety none, reversal risk low, protected false, traces to: none found for closed_question as a separate field; AC3/AC4 need only an open or closed question per material

## 2026-11-11T23:27:03Z — F4 plan — requirements

### confirm (0)

### flag_only (0)

## 2026-11-11T23:27:03Z — F4 plan — architecture

### confirm (1)
- APPLIED BY THE ARCHITECT `F-e5e6a020` **.engine/architecture/feature/f4-recall-worklog.md:103-108** — verbose_output: The 'Critic notes (appendix)' section can go. It states the same decision three times over: Build parameters lines 29-32 already say there is no record-to-case link and why, lines 33-35 already carry both must-fixes (the intents in ALWAYS/PHRASES/_dispatch and the guide lines), and escalations.md:267-274 already holds the full rationale and closes the decision. Removing it changes no slice, contract or criterion; it only takes out the author's narration of a failed edit.
  - applied to the plan 2026-11-11T23:27:13Z: прибрано розділ Critic notes з плану F4; рішення лишилось у Build parameters і escalations 2026-11-11 — nothing is asked of the owner
  - evidence: read .engine/architecture/feature/f4-recall-worklog.md:29 Build parameters already record the deviation (no link to the case, instrumental case, routing cannot see the catalog, critic's decision, P1) and cite escalations 2026-11-11; read .engine/architecture/feature/f4-recall-worklog.md:33 The must-fix intents (ROUTE_SCHEMA, ALWAYS, PHRASES, _dispatch, routing hint, for clarify) and the guide lines for S1/S3 are already a build parameter; read .engine/overseer/escalations.md:267 The AUTONOMOUS entry repeats the appendix almost word for word, including 'моя правка не застосувалась', and is CLOSED. The escalation log is the place this decision is recorded.; read .claude/commands/feature-architect.md:186 The feature artifact template has no Critic notes section. The appendix is outside the format the slices read.; judgement  Chesterton check: the appendix exists to record why the case_id seam was dropped. That reason lives both in the Build parameters and in the escalation entry, so nothing is lost. The signals given (S-f8fe5b4f, S-b4ba60e6) are about pyproject.toml, which is outside this scope, and are not used here.
  - test safety none, reversal risk low, protected false, traces to: none found (not a template section; the decision traces to escalations 2026-11-11, which already carries it)

### flag_only (0)

## 2026-11-15T11:43:35Z — code, nightly 2026-11-15

### confirm (1)
- `F-c4d6a784` **src/mamamemory/planning/__init__.py:30** — dead_code: The module constant TASK_ID = "t1" is never read anywhere in src, tests or scripts, and the literal "t1" appears nowhere else in src. Removing it changes nothing. It looks like a leftover from the one-task F1 draft, which the module docstring says is now a list.
  - evidence: signal S-cca419b5 vulture: unused variable 'TASK_ID' (60% confidence); grep src/mamamemory/planning/__init__.py:30 'TASK_ID' appears only at its definition across the repository, apart from the maintenance report tasks/done/403-maintain-2026-11-15/report.md:17,36, which already recommends removing it; read src/mamamemory/planning/__init__.py:1-6 the docstring says the F1 single task is now a list of one; no comment explains why the constant should stay
  - test safety characterization_exists, reversal risk low, protected false, traces to: none found

### flag_only (0)
