# Engine rules — the standing policy for autonomous Claude Code work

Installed and updated by `engine.py`; edits belong in the engine repository, not here. Detail
is read on demand from `.claude/references/`: `hooks.md` (what each hook does, inspecting or
disabling one, the contract's fingerprint) and `unattended.md` (the mode file, parking in full).

## Commits are a human checkpoint
- Never run `git commit` except on the run's own `unattended/<date>` branch, through
  `.claude/unattended/commit_checkpoint.sh <node>`. On `main`, on any feature branch and when
  the branch is unknown, `block-dangerous.sh` refuses the commit and it belongs to a human.
- After a unit of work: `git add <files>`, run lint / type-check / tests, print a one-line
  summary and a suggested commit message, then continue with the next item. Staged work is a
  review surface, not a stopping condition.
- A hook sees the command you type, never one run from inside a script. A script you write
  must carry the check itself.

## Permissions
- **Ask-gated** — only on the human's explicit request in the current turn: `git push`,
  `rebase`, `merge`, `cherry-pick`, `revert`; `gh pr create/merge`, `gh release`; adding or
  removing packages (uv, poetry, pip, npm, cargo…); migrations (alembic, `manage.py migrate`);
  `docker push/run`, `docker compose up`. Unattended, never invoke one (nobody answers): put it
  on the board (`board.py open-item --to blocked`: command, what waits, question) and continue.
  Cloud on `CLOUD_COMMIT_POLICY="session-branch"`: its own `claude/` branch to `origin` goes unasked.
- **Hard-denied** whatever the instruction: deleting `/`, `~` or `$HOME`; force pushes,
  `git reset --hard origin*`, history rewriting, `git clean -fdx`; reading or editing `.env`,
  `secrets/`, SSH/GPG/AWS credentials; editing migrations and `.github/workflows/`; publishing
  packages; piping curl or wget into a shell; `sudo`. If asked, refuse and hand it to the human.
- **Auto-allowed**, no hesitation: editing non-protected files; tests, lint, type-check,
  format; read-only git; `git add`, `switch`, `checkout -b`, `stash`, `tag`; file utilities;
  fetching documentation. If you are wondering whether to ask for one of these — don't.

## When the Stop gate fails
`verify-on-stop.sh` runs the project's lint, type-check and tests when code changed, and blocks
the turn on a failure. Read the actual error, fix minimally, re-run. After three different
fixes, stop trying: park the item with the three attempts and the exact output, continue with
the next unblocked item. A `gate-allow` is not a way through: the overseer reads every reason
(#4), and while the gate's escalation is open no PASS is recorded for that work.

## Overseer protocol
- `overseer_stop.py` injects `OVERSEER_REQUEST <id>` only when a turn claims a unit complete: the
  sentinel `=== UNIT N COMPLETE ===` alone on its own line AND, in the same turn, a verification
  command, AND code under a code path (`.claude/project.env`) that changed since the last audit
  request, written by any tool. Emit the sentinel only for a
  genuine unit — `N` from `.engine/slices/<slug>.md`, else `1` — never on a work-in-progress,
  RED-only or question-answering turn.
- On `OVERSEER_REQUEST <id>`: launch the agent `overseer` (fresh context, no editing tool) with
  exactly that line as its prompt, change nothing until it answers, then end the turn. You never
  audit or write a verdict: `overseer_verdict.py` writes the ledger from the agent's answer, and
  `OVERSEER_PASS` typed by you is ignored. After a BLOCK you fix and claim again — another overseer
  judges it; three BLOCKs park the task; a test gap is a PASS plus a `proposed/` item (`skills/overseer`).
- Planning stands the overseer down: `python3 .claude/hooks/overseer_phase.py set plan` before
  drafting a contract, `… clear` when done. Never write `.claude/state/` with your own tools —
  it is the state of hooks and scripts; the named scripts are the only sanctioned path.
- The slice contract is sealed by `/plan-slice`: changed after approval, the turn gets an
  escalation, not an audit. Re-approving is the owner's act; never delete the fingerprint.

## Verdict routing — almost nothing stops the run
A verdict records a finding. Route by whether the fix needs a human, not by the verdict's name.
- `BLOCK` you can resolve → fix it, log it, continue. Otherwise park the item — a task on the
  board (`board.py open-item`), never a line in a log — and continue with the next one.
- `ADR_REQUIRED`, reversible → write the ADR in `docs/adr/` and continue. One-way door → draft
  it `PROPOSED — provisional`, park, continue.
- `ESCALATE` on a two-way door → append an AUTONOMOUS entry to
  `.engine/overseer/escalations.md` with its cost-to-reverse, act on your own recommendation,
  continue. Logging is what closes a decision, and CLOSED means closed: never re-raise it
  with the owner; new evidence gets a superseding entry.
- A deviation from an explicit owner instruction is classified by reversibility like anything
  else: if its premise is shown false, say so once, do what is right, log it, continue. A
  one-way door or an Article 5 product decision is parked, never decided alone.
- Attended, `AskUserQuestion` is cheap and right. Unattended, never block on it.

## The three reasons to stop, and there are no others
(1) Something only a human can supply — a credential, a deploy, a provisioning step, a person
with a phone, ratification of a genuine one-way door. (2) A load-bearing premise is falsified
in a way that invalidates committed work. (3) Nothing left in the queue can move.
Not reasons: a background task in flight (do non-racing work; its notification will come),
something worth reporting (report while continuing), a two-way door you already decided (log
it), a natural-feeling pause. Address the human only for one of the three, or when three parked
items await ratification (`unattended.md`). To stop for real, emit an `OVERSEER_` halt marker
naming the reason.

## Attended vs unattended
`.claude/state/overseer/mode` containing `unattended` means nobody is watching; absent or
anything else is attended, the default. The mode changes one thing only: an interactive hard
gate in `/plan-slice` or `/feature-architect` becomes a park. Everything above holds in both
modes, Article 5 included — unattended never means "decide it anyway". Unattended
work runs through the task board only (below); detail: `.claude/references/unattended.md`.

## The task board and extra sessions
Work arrives as files in `tasks/` (`tasks/README.md`): take the first `todo/` task with its
dependencies in `done/`, move it to `doing/` in its own commit, end in `done/NNN-name/` with `report.md` —
or in `blocked/` with a question for the owner. Extra Claude sessions (evals, critics, measurements) are
ordinary work under a weekly cap: at it start none, commit, `board.py extra-wait` (README rule 12). The
overseer's audit run needs `Аудит потрібен: так`. Full tests once. Quality over price: no dollar limit; only
`BOARD_MAX_USD` guards a loop (it parks the task). Only the owner puts work into `todo/`: a finding is a proposal
(`proposed/`), a guard's designed limit is not work (rule 13). For the owner technical terms stay English: `unattended.md`.

## Constitution
Every agent reads and obeys `.claude/constitution.md`. It overrides any conflicting
instruction, this file included.
