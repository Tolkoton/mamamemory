---
name: slice-builder
description: Build ONE isolated testable logical piece (a "thin slice") of a larger system using strict per-test TDD (RED→GREEN→REFACTOR), paranoid-SRP (one method = one responsibility; multi-responsibility logic becomes a flow method orchestrating helpers), seam-first design, and dependency injection. Use this skill WHENEVER the user asks to "implement a small piece", "add a thin slice", "build the upload module", "build piece N of the pipeline", "wrap this API in a clean function", or otherwise wants controlled incremental progress on a known integration without architecture overhead. Output is one production module + integration tests derived from the method's distinct behaviors + one manual smoke script + a .engine/PROGRESS.md entry. Gates once on the behavior list, then runs every behavior to completion without stopping; evidence goes to the artifact and the ledger, not to chat. DO NOT use for greenfield architecture (→ master-architect), splitting oversized multi-file features (→ feature-architect), unknown-API exploration (→ spike, no skill), or single-file edits (→ user edits directly).
---

# Slice Builder

You are extending a known system one isolated logical piece at a time. The user already knows the rough shape (sometimes from `master-architect`, often just from being the system's owner). External dependencies are already accessible and validated — credentials live in `.env`, vendor docs are in the repo. You are NOT designing a system. You are adding ONE clean, testable, isolated module.

## Discipline (apply ALL of these)

1. **Seam-first.** Fix the function signature, types, and return shape BEFORE writing any code, and write them to the slice artifact. State what the component will **NOT** do — this is the boundary of the slice. Attended, show the seam and let the user amend it; unattended, the written seam plus the critic's pass is the record, and you proceed. The seam being *written down first* is the discipline; a human reading it in real time is not.

2. **Dependency injection always.** External clients, configs, time sources, and randomness are passed as arguments. NEVER import them inside the module under construction. This makes the module testable in isolation and prevents hidden coupling.

3. **Strict TDD per test.** RED → GREEN → REFACTOR per test. Capture pytest output at every transition into the ledger. Write ONE test at a time. NEVER write the next test before the previous one is green AND the code is refactored. Never write impl before its test. The ordering is absolute; the turn boundary is not — a transition is recorded, not reported to a human.

4. **Paranoid-SRP.** ONE method = ONE responsibility. No exceptions, no asking. If logic requires multiple responsibilities, it becomes a **flow method** that calls single-responsibility helpers in order — the flow method's responsibility is "orchestrate these steps", each helper's responsibility is one step. Helper functions for SRP are NOT premature abstraction (that's about ABCs/protocols/factories, see rule 5).

   Example. NOT this:
   ```python
   def upload_to_folder(file_path, folder_id, client) -> UploadResult:
       if not file_path.exists(): return UploadResult(False, error="missing")
       if file_path.stat().st_size > MAX: return UploadResult(False, error="too big")
       token = client.authenticate()
       resp = client.post(...)
       if resp.status != 200: return UploadResult(False, error=resp.text)
       return UploadResult(True, document_id=resp.json()["id"])
   ```
   THIS:
   ```python
   def upload_to_folder(file_path, folder_id, client) -> UploadResult:
       """Flow: validate → upload → map response."""
       if (err := _validate_file(file_path)) is not None:
           return UploadResult(success=False, error=err)
       raw = _do_upload(file_path, folder_id, client)
       return _map_response(raw)

   def _validate_file(p: Path) -> str | None: ...
   def _do_upload(p: Path, fid: str, c: RemoteClient) -> RawResponse: ...
   def _map_response(r: RawResponse) -> UploadResult: ...
   ```
   Each helper has one reason to change. The flow has one reason to change (orchestration order).

5. **No premature abstraction.** No ABCs, no protocols, no `*_Factory`, no plugin systems, no `*_Manager`, no generic `*_Service` indirection, no retry policies, no circuit breakers, no structured event emission. If the user asked for a function, write a function.

6. **Tests: derived from method behaviors, not from a quota.** Before writing tests, enumerate the distinct externally observable behaviors the method guarantees, then write one test per behavior. **The behavior list is the one gate in this skill** — write it to the slice artifact before the first RED. Attended, the user approves it; unattended, a critic pass on the written list is the approval. Once it is approved, every behavior on it runs to completion without a further gate. Heuristics by method type:

   - **Pure transformation / formatter** (no I/O, no branches): 1-2 tests — success + one boundary if a meaningful one exists.
   - **Single-responsibility helper with validation**: success + one test per distinct failure mode it can return.
   - **Flow method (orchestrator)**: success orchestration + one test per step that can short-circuit the flow + one test per branch the flow itself chooses.
   - **Thin wrapper over external API**: success + at least one error path that the wrapper maps (typically 2). The external API's own behavior space is not your test surface — sandbox the integration.

   What is NEVER added at slice level: mutmut / cosmic-ray mutation testing, exhaustive hypothesis property tests, wide-lens enumeration (security/performance/concurrency/encoding lenses) — those belong to a full-feature implementation effort. Adding them to a slice is scope creep.

7. **Manual smoke verification at the end.** A `scripts/smoke_test_<slice>.py` that exercises the real path against the real system, prints results, and gives the user explicit human-verifiable instructions. The slice is NOT complete until the smoke result is recorded. This is a genuine human-input dependency (reason 1) whenever the verification needs eyes on a real external system — so it **parks**, it does not halt: write the script, add a `PARKED / external-verification` entry to the parked log with `python3 .claude/hooks/journal.py add parked` (this session's own file of it, board 739), mark the slice `CODE COMPLETE — SMOKE PENDING` in `.engine/PROGRESS.md`, and move to the next unblocked item. If the smoke can be asserted programmatically against a sandbox, do that instead and close the slice without parking.

## When NOT to use this skill

| If the user wants... | Use instead |
|---|---|
| "Design the architecture for X from scratch" | `master-architect` |
| "Implement this large multi-file feature end-to-end" | `master-architect` + `feature-architect` |
| "Split t007 / this task is too big" | `feature-architect` |
| "Does API X even work? I have no creds/docs yet" | Spike work — no skill, direct conversation |
| "Fix this typo / rename this variable / one-line change" | No skill — user edits directly |
| Cross-module refactor of an existing feature | No skill — user-led, possibly with `master-architect` BACKTRACK |

**A task in the mode ескіз** (`python3 .claude/hooks/mode.py show`) is not a slice: it answers one
question and builds nothing that stays. Its code goes only into `sketches/<name>/` — the gates do not
check it, and nothing outside `sketches/`, `.engine/` and `tasks/` may change (gate.py blocks it).
What it leaves is the record `.engine/sketches/<name>.md` (`.claude/references/sketch-record.md`): the
question, what was tried, the command and its output, the answer. A fresh `reader` must PASS the
record before the task closes. Working code never imports, runs or opens a sketch; carrying a sketch
over is a new task in соло or конвеєр, where the code is written anew under this skill.

If invoked incorrectly, hand off directly: name the correct skill and invoke it. Skill routing is mechanical — the "DO NOT use for" list above already determines the answer, so there is nothing here only a human can supply. Do not stop to ask for a redirect. Note the handoff in one line so the switch is visible, and continue.

## Workflow

### Step 0 — Validate scope

Answer these four, in the slice artifact, before anything else:
- What's the seam? (function signature, input types, return type)
- What's the external dependency? Where are its docs? (path in repo)
- What does this slice **NOT** do? (List 3-5 deferred items.)
- Existing conventions in the repo to follow? (test layout, type strictness, Pydantic vs dataclass for what kinds of objects)

**Sources, in order:** the slice contract at `.engine/slices/<slug>.md`, then the feature artifact, then the existing code's conventions. Attended, ask all four at once and wait. Unattended, derive each from those sources and write it down; if the *seam itself* is underdetermined and no source settles it, that is a design fork — park it (`one-way-door` only if the signature is a published contract; otherwise decide, record the alternative you rejected, and continue).

**Do not wait.** The artifact write is the checkpoint.

### Step 1 — Read external docs

Read the vendor docs the user pointed to. Report back:
- Which API/function to call (exact name, expected request/response shape)
- Which credentials are needed (confirm they exist in `.env.example` or `.env`)
- Whether a test/sandbox environment exists, and what its config looks like
- Any constraints on inputs (file size, MIME, character encoding, etc.)

Record all four findings in the slice artifact.

**Missing test-environment details** (folder ID, account ID, sandbox URL) are the textbook human-only input — reason 1. If they are not in `.env`, `.env.example`, the slice contract, or the vendor docs: put a question on the task board (`python3 .claude/unattended/board.py open-item --to blocked --title … --what … --question …`) naming the exact values needed and where they should go, then move to the next unblocked item. Do not guess a credential and do not halt the run waiting for one.

### Step 2 — Skeleton

Write the module skeleton:
- Function signature with `raise NotImplementedError("slice in progress")`
- Value objects (frozen dataclasses, or Pydantic v2 if user requested cross-boundary type) — name them, give fields, give types
- Type hints, suitable for mypy strict
- Module-level docstring stating WHAT this module does and what it explicitly DOESN'T (echoes Step 0)

Run `pytest --collect-only` (or equivalent) — import must succeed. If it does not, fix it; a skeleton that will not import is not a checkpoint, it is a bug.

Continue straight to Step 3. No gate here.

### Step 2a — The testing manager, point (a) — only for a slice with a sealed contract

A slice planned by `/plan-slice` has a sealed contract, and then who writes its contract tests is not your decision. Before Step 3:

```
python3 .claude/hooks/testing.py request <slug> --point a     # prints TESTING_REQUEST <id>
```

Start the agent `test-manager` with exactly that line as its prompt. Its answer is recorded by the script (while the hooks are not wired in `settings.json`: save the agent's answer to a file and run `python3 .claude/hooks/testing.py record --answer <file>`). `python3 .claude/hooks/testing.py status <slug>` shows the decision. Without it the Stop hook requests no audit for this slice. That request also makes the slice the active one of your board task — the audit request, the contract's fingerprint check and the complexity budget read it from there, so run it before the first line of code and never for a slice you are not building yet.

- **`builder`** ("do not switch") — Steps 3–6 as written below. If the contract's «Invariants» section names rules (I1, I2…), each is a behaviour on your list with one test named `test_I<n>_…`, on example inputs you choose from its «Domain» — its edges, zero, the empty value, two lawful inputs combined — not on the inputs your code was written for; the overseer checks exactly that (#4). These are example tests: rule 6 stands.
- **`tester`** — Step 3 is the tester's, not yours: `python3 .claude/hooks/testing.py request <slug> --tester contract`, start the agent `slice-tester` with the line it prints. It hands in its questions to the contract, the list of behaviours and the contract tests; the script itself runs them against your skeleton (each must fail) and seals the test files. There is no critic pass over that list — its author is already fresh and blind. Then:
  - **Questions to the contract** go to the slice planner in one package (`/plan-slice`, "Questions from the tester"); a test that waits for an answer is not sealed, and no audit is requested until it is.
  - **Step 4** starts with RED already there: take the sealed tests one at a time to green, refactor after each. **You do not edit a sealed test file** — a changed one blocks the audit. Unit tests of your helpers go into a file of your own, test first, as always.
  - **You think a sealed test is wrong** — do not weaken it. Write ONE package with every disputed test (which test, which line of the contract, why) and run `python3 .claude/hooks/testing.py request <slug> --tester objection --package <file>`; a fresh `slice-tester` rules on each item: the test was wrong (it corrects it), the test was right (you correct the code), or the contract is ambiguous (the planner answers). Two rounds a slice; the script parks the slice on the third — go on with the next unblocked one. **Your sealed contract changes what another slice's sealed tests hold** (that slice parked or not): do not edit them and do not ask the owner — one package (which old test, which line of your contract changes it) and `python3 .claude/hooks/testing.py request <old-slug> --tester supersede --by <your-slug> --package <file>`; the tester of your contract rewrites them, with a counter of its own (board 304).

A slice without a sealed contract (the builder started directly) skips this step.

### Step 3 — Enumerate behaviors

Before writing any test, list the distinct externally observable behaviors the slice must guarantee. Use the heuristics from rule 6 to scope the list. For a flow method, list behaviors at the flow level — helpers will get their own tests if they're exposed, but typically helpers are tested THROUGH the flow.

Output format:
```
Behaviors of upload_to_folder:
  B1. Returns success=True + document_id when file uploads to valid folder
  B2. Returns success=False + error when file path doesn't exist
  B3. Returns success=False + error when folder_id is unknown to the remote service
  B4. Returns success=False + error when file size exceeds the service limit
```

**This is the gate — the only one in the build phase, and it fires once per seam, not once per behavior.** Write the list to the slice artifact under "Behaviors". Then:

- **Attended:** the user confirms, removes/adds, approves.
- **Unattended:** the list goes to the critic. A critic pass approves it. A critic block returns here once with the objection folded in; a second block on the same list parks the slice (`one-way-door` only if the disagreement is about a published contract) and you move on.

The behavior list is the test plan. Once approved it is a contract with itself: Step 4 runs the whole list without returning here.

### Step 4 — TDD per behavior (one cycle per behavior)

Once the behavior list is approved, run **every** behavior on it to completion in one continuous pass. For each behavior Bn in order:

- **RED**: Write ONE test for Bn. Run pytest. Capture the failing output to the ledger.
- **GREEN**: Minimal implementation to make Bn pass without breaking earlier behaviors. Run pytest (full slice suite). Capture all-green to the ledger.
- **REFACTOR**: Clean. If SRP rule 4 says a flow needs splitting into helpers — do it here. Run pytest. Still green. Capture to the ledger.

**The ordering constraint survives; the turn boundary does not.** Do NOT advance to Bn+1 until Bn is green AND refactored. That is a constraint on *your* sequencing within the approved list — never write the next test over a red or unrefactored predecessor — not a checkpoint that needs a human to have seen anything. The RED output in the ledger is what proves the cycle ran in order, and it is better evidence than a human skimming chat, because the overseer can audit it later (check #2).

**Missing behavior discovered mid-cycle.** Do not stop and do not ask. Append it to the behavior list in the slice artifact marked `self-added` (for a sealed contract the list lives beside it, in `.engine/slices/<slug>.behaviors.md` — the sealed file itself is never edited; the script counts the `self-added` marks at point (b)), record in the artifact's decision log what you observed that forced it and why it was not visible at Step 3, then continue the pass including the new behavior. This is a reversible local addition inside an approved list, not a contract amendment — the artifact diff is the review surface. It becomes a contract amendment, and therefore a park, only if the new behavior contradicts the seam or the "Out of scope" section.

### Step 5 — Smoke script

Write `scripts/smoke_test_<slice>.py`:
- Sets up real inputs (generate file, build payload, load real creds from `.env`)
- Calls the slice function with real DI dependencies
- Prints the result
- Prints an EXPLICIT human-verifiable instruction (e.g., "Open the admin panel at /uploads, look for file `smoke_<slice>_<timestamp>.txt`. Reply DONE or FAIL.")

Then take the cheapest path that closes the slice:

- **Assertable against a sandbox** — run it, capture the output to the ledger, close the slice. No park.
- **Needs human eyes on a real external system** — park it. Put it on the task board (`board.py open-item --to blocked`) with the exact command and the printed instruction, mark the slice `CODE COMPLETE — SMOKE PENDING` in `.engine/PROGRESS.md`, and move to the next unblocked item. The slice resumes when the smoke result comes back.

Never block the run on a smoke walkthrough, and never mark a slice DONE on an unrun smoke.

### Step 6 — PROGRESS update

Append to `.engine/PROGRESS.md` at repo root (create if missing) as soon as the code is complete — do not wait on the smoke result. If the smoke is parked, write the entry with `Smoke: PARKED — see tasks/blocked/<the task>` and update it in place when the result arrives:

```
## Slice N — <name> (DONE YYYY-MM-DD)

- Module: <path> (~NN LOC)
- Tests: N integration tests, all green
- Smoke: passed, <verification result>
- Surprises: <1-2 lines or "none">
- Open for next slice: <questions / tech debt / "none">
```

### Step 7 — The testing manager, point (b) — only for a slice with a sealed contract

When the slice is finished (every step, the smoke recorded): `python3 .claude/hooks/testing.py request <slug> --point b`, start `test-manager` with the line it prints. It decides, for each of three checks, `now`, deferred until a named event, or not needed — and the script refuses a decision that drops a mandatory one:

- **catch-up contract tests now** — `python3 .claude/hooks/testing.py request <slug> --tester contract`: the tester writes the tests the slice lacks (the code exists; it works from the contract). A test that fails is a finding for you, one package.
- **integration tests now** — `… request <slug> --tester block`: one test per connection between blocks and, at the close of the feature, per acceptance criterion. Failing tests come to you as one package.
- **a mutation run now** — `python3 .claude/hooks/testing.py mutation <slug>` runs the project's `MUTATION_CMD` over the files of the block (the engine installs no tool). The survivors are sorted by the manager's order: code under an owner's threshold, code of a hardest seam, code on a connection between blocks — those are handled (a fresh tester adds the test when the behaviour is in the contract; code nobody asked for is a finding for the simplifier; an equivalent mutant is closed with one line), the rest goes to the report as a list. Record the count: `… mutation-result <slug> --survived N --handled N`.
- **deferred** — the debt stands in `.engine/testing/ledger.md` and in the owner's review; the manager cannot defer it twice.

The next slice does not start without this decision, nor while a check it said to do **now** is not done (`testing.py request` refuses and names it); a feature does not close either.

Stage the slice's files with `git add`, print a one-line summary and a suggested conventional-commit message, and continue to the next unblocked item. Do NOT commit on the user's behalf: staging is a review checkpoint, not a stopping condition. Staged work accumulates for the human to review whenever they return; it does not gate the next slice.

## Anti-patterns (refuse politely if user requests these mid-slice)

If the user asks for any of the following DURING the slice, push them out of scope:

- Tests not derived from a stated behavior (vibe-based "while I'm here" tests)
- Mutation testing (mutmut, cosmic-ray)
- Wide test design (test lenses, exhaustive hypothesis property tests)
- New abstractions (ABCs, protocols, factories) when there's exactly one implementation
- Retry policy / circuit breaker / structured logging — defer to a future slice
- ADRs or architecture files — slices don't produce these
- Refactor of existing modules — separate slice or `master-architect` BACKTRACK
- Implementing the NEXT slice "since we're here"

Response template (attended):
> That's beyond the scope of this slice. Want me to (a) defer it to a follow-up slice (I'll note it in `.engine/PROGRESS.md` under "Open for next slice"), or (b) escalate to `master-architect` if it's actually architectural?

Unattended, do not ask — decide and log. Default to (a): note it in `.engine/PROGRESS.md` under "Open for next slice" and continue the current slice. Choose (b) only when it meets one of the Escalation-signal triggers below, in which case park it per that section. Deferring is a two-way door; the note is the record.

## Escalation signals

STOP and BACKTRACK to **`master-architect`** if during the slice you discover:
- The seam can't be implemented without a missing architectural decision
- The slice depends on a component that doesn't exist yet and wasn't in scope
- The external API has fundamentally different semantics than the seam assumes (sync vs async, eventual consistency, transactional contract differences)

STOP and ESCALATE to **`master-architect`** (or pause and discuss with the owner) if during the slice you discover:
- The slice as defined is actually L complexity (5+ production files needed, excluding private helpers in the same module; 3+ domain entities; requires real DDD)
- Behaviors span multiple concern categories that need different test approaches (functional + performance + security + concurrency invariants) — that's full-feature test discipline, not slice
- The user is asking for mutation testing / structured logging / observability as part of the slice (those are full-feature concerns)

In both cases, do NOT continue **this slice** — the trigger is real and the level is wrong. But do not halt the run either. Route through park-and-continue:

1. Put the item on the task board (`python3 .claude/unattended/board.py open-item --to blocked …`), saying whether it is a one-way door (a missing architectural decision, an API semantics mismatch) or something else that needs the owner, and naming which skill should pick it up (`master-architect` / `feature-architect`).
2. Record what you found in the slice artifact and in `.engine/PROGRESS.md`; mark the slice `BLOCKED`.
3. Leave the partial work as-is — never revert someone else's decision surface on your own.
4. Move to the next unblocked item.
5. Surface only per the thresholds of `.claude/references/unattended.md`: nothing else can move, a single one-way door, or three parked ratification items.

## Notes on test scope

**Default: integration tests against real external system** (test/sandbox endpoint).

Add a unit test with a fake/stub dependency ONLY if:
- The slice has non-trivial mapping/branching logic ABOVE the external call (so the unit test catches that logic without paying network cost), OR
- The external call is slow (>2s) and the TDD cycle would become painful

For thin wrappers (the typical slice), integration-only is correct. Don't introduce fakes for the sake of "proper" unit testing.

## Pydantic v2 vs dataclass — quick rule

- **Pydantic v2 `BaseModel`** → cross-boundary data (HTTP request/response bodies, external API DTOs, queue messages)
- **`@dataclass(frozen=True)`** → internal value objects, slice-local result types like `UploadResult`, `TokenIssued`

If the user's project has a different convention, follow it.
