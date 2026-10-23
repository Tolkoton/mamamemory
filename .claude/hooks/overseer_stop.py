#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Stop hook: auto-trigger an overseer 12-check audit on unit completion.

Redesign of the abandoned bash `overseer-on-stop.sh`. The bash hook reconstructed
the last assistant message by parsing the transcript JSONL named in the Stop
envelope — but the transcript is flushed asynchronously, so the hook raced the
writer and read a stale or empty turn (anthropics/claude-code#15813).

Claude Code now ships the finished turn's text directly on the Stop envelope as
`last_assistant_message` (field probe PASS, 2026-05-22 — see
.engine/artifacts/spikes/auto-overseer-redesign-2026-05-22.md). This hook reads that
field for the *completion text* and consults the transcript only for the
*structural tool-use signal*, which is a stable historical record by the time
Stop fires.

TRIGGER — both signals required:
  1. text sentinel: `=== UNIT N COMPLETE ===` on its own line in the message.
  2. tool signal:   in the current turn, an Edit/Write/MultiEdit on a code
                    path (configured via SOURCE_DIRS / CODE_EXTENSIONS in
                    .claude/project.env) — or a code path that differs in the
                    TREE from what the last audit request saw, whichever tool
                    wrote it (a shell command, a script) — AND a Bash
                    verification command (configured via CHECK_CMDS, or
                    built-in broad default).

RECURSION GUARDS — per-branch, by design:
  - Audit request    — `.claude/state/overseer/.last_audit_sha`, the SHA of the last message whose
                       claim was answered; the same message does not claim twice.
  - Typed markers    — `.claude/state/overseer/.last_continue_sha`, the SHA of the last message
                       that was told its typed `OVERSEER_PASS` / `OVERSEER_REQUEST` means nothing.
  - Halt markers (BLOCK / ESCALATE / ADR_REQUIRED / SLICE_AWAITING_OWNER /
    SLICE_COMPLETE) silent-pass — owner takes over.

  `stop_hook_active` is deliberately not a guard: every hook-initiated turn arrives with it set,
  so it would make the request and the "continue" unreachable in the autonomous loop.

PHASE GUARD: `.claude/state/overseer/state` containing `plan` suppresses the audit — the
developer is designing, not completing units of work.

WHO AUDITS (board 015 / 018 / 033). Never the builder: on the trigger above this hook writes a
request package and tells the builder to launch the agent `overseer` (fresh context, no editing
tool) with the prompt `OVERSEER_REQUEST <id>`. The verdict is recorded by `overseer_verdict.py
record` from the agent's own answer; this hook continues, hands back a BLOCK or routes an ADR /
escalation only on that record. `OVERSEER_PASS` typed by the builder is refused. That script works
through two handlers in the project's settings, which `engine.py install` / `update` put there.
A project whose settings lack them cannot be audited at all — there is no second protocol — so a
claim there is answered with NOT_WIRED_REASON: say so, park the unit, never audit yourself.

Output: `{"decision":"block","reason":...}` on stdout (exit 0) injects the audit
request and continues the turn; empty stdout (exit 0) passes the turn through.

Invoked by Claude Code as `python3 .claude/hooks/overseer_stop.py` (see
.claude/settings.json Stop hooks). The `uv run` shebang only applies when the
file is executed directly; either way it needs no third-party dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# `=== UNIT 7 COMPLETE ===` on its own line; surrounding horizontal space is
# tolerated so the sentinel survives minor formatting.
UNIT_NUMBER_RE = re.compile(r"^[ \t]*=== UNIT (\d+) COMPLETE ===[ \t]*$", re.MULTILINE)
# A marker typed by the builder.
#
# ANCHORED TO LINE START, deliberately, exactly as UNIT_NUMBER_RE above is.
# Before this, `re.compile(r"OVERSEER_PASS\b")` matched the token ANYWHERE in
# the message, including inside prose and code spans. Any turn that documented,
# reviewed, or taught the protocol therefore entered the autonomous continue
# loop — and this repo is the protocol's own template, so those turns are
# routine here. Observed 2026-08-27: a turn that only *described* the markers
# consumed .last_continue_sha and injected a continue instruction against a
# slice that did not exist.
#
# SKILL.md's "Verdict format" section already requires a marker to be "on its
# own line", so this makes the hook enforce what the contract always stated.
# Leading horizontal space is tolerated, matching UNIT_NUMBER_RE.
_MARKER_PREFIX = r"^[ \t]*OVERSEER_"

# Halt markers — owner takes over, hook silent-passes
HALT_MARKER_RE = re.compile(
    _MARKER_PREFIX + r"(?:BLOCK|ESCALATE|ADR_REQUIRED|SLICE_AWAITING_OWNER|SLICE_COMPLETE)\b",
    re.MULTILINE,
)
# Pass marker — typed by the builder it is refused: only a recorded verdict continues the run
PASS_MARKER_RE = re.compile(_MARKER_PREFIX + r"PASS\b", re.MULTILINE)
# File-mutating tools — the other half of the tool signal.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

# Built-in broad default: covers Python, JS/TS, Go, Rust, Swift stacks.
_DEFAULT_CHECK_CMDS = "pytest ruff mypy npm jest vitest go cargo swift"


def _get_project_dir() -> Path:
    """Resolve the project root: CLAUDE_PROJECT_DIR → git → CWD.
    Never returns a relative path — always .resolve()d."""
    env_val = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_val:
        return Path(env_val).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.cwd()


def _load_project_env(project_dir: Path) -> dict[str, str]:
    """.claude/project.env as gate.py reads it (one reader for every hook).
    Prints a stderr warning when the file is absent; returns {} on any error."""
    env_path = project_dir / ".claude" / "project.env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        print(
            f"⚠ overseer_stop: .claude/project.env not found at {env_path} — "
            "using built-in defaults. See docs/TEMPLATE-SETUP.md.",
            file=sys.stderr,
        )
        return {}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    return gate.parse_env_text(text)


def _split_list(raw: str) -> list[str]:
    """Split a config list value on commas and/or whitespace, so ".ts,.tsx",
    "ts tsx", and ".ts .tsx" all yield the same tokens. Empty tokens dropped."""
    return [tok for tok in re.split(r"[,\s]+", raw.strip()) if tok]


def _build_check_cmd_re(cfg: dict[str, str]) -> re.Pattern[str]:
    """Build the check-command regex from project config.
    Falls back to the built-in broad default when CHECK_CMDS is empty or
    does not parse into any usable name."""
    raw = cfg.get("CHECK_CMDS", "").strip()
    names = _split_list(raw) if raw else []
    if raw and not names:
        print(
            f"⚠ overseer_stop: CHECK_CMDS='{raw}' did not parse into any usable "
            "command name — falling back to built-in defaults.",
            file=sys.stderr,
        )
    if not names:
        names = _DEFAULT_CHECK_CMDS.split()
    pattern = "|".join(re.escape(n) for n in names)
    return re.compile(rf"\b(?:{pattern})\b")


def _build_source_dirs(cfg: dict[str, str]) -> list[str]:
    """Return the configured source dirs, normalized with trailing slash.
    Empty list means "match any directory" (use CODE_EXTENSIONS fallback)."""
    raw = cfg.get("SOURCE_DIRS", "").strip()
    if not raw:
        return []
    dirs = [tok.rstrip("/") + "/" for tok in _split_list(raw) if tok.rstrip("/")]
    if not dirs:
        print(
            f"⚠ overseer_stop: SOURCE_DIRS='{raw}' did not parse into any usable "
            "directory. Treating as unset — any code-extension match counts.",
            file=sys.stderr,
        )
    return dirs


def _build_code_extensions(cfg: dict[str, str]) -> frozenset[str]:
    """Return the set of code file extensions (without dot).
    Empty set means "match all files"."""
    raw = cfg.get("CODE_EXTENSIONS", "").strip()
    if not raw:
        return frozenset()
    exts = frozenset(
        tok.lstrip(".").lower() for tok in _split_list(raw) if tok.lstrip(".")
    )
    if not exts:
        print(
            f"⚠ overseer_stop: CODE_EXTENSIONS='{raw}' did not parse into any "
            "usable extension. Treating as unset — all edited files count.",
            file=sys.stderr,
        )
    return exts


def _is_code_path(
    file_path: str,
    source_dirs: list[str],
    code_extensions: frozenset[str],
) -> bool:
    """True if the path counts as a code edit for the overseer trigger.

    Decision tree:
    1. If source_dirs is configured: the path must lie under one of them.
    2. If source_dirs is empty: path must match code_extensions (if configured).
    3. If both are empty: any edit counts.

    A source dir (normalized to a trailing slash by _build_source_dirs) matches when
    "/<dir>/" occurs in "/<path>": that covers the relative form (src/foo.py), the absolute
    form Claude Code actually sends (/work/proj/src/foo.py) and a multi-segment entry
    (backend/src, .claude/hooks) alike, and never a look-alike prefix (src2/, srcfoo/).
    Until package 3c's fix round the multi-segment case matched relative paths only, so the
    documented monorepo example was inert in a real session.
    """
    normalized = "/" + file_path.replace("\\", "/").lstrip("/")

    if source_dirs:
        return any(("/" + d) in normalized for d in source_dirs)

    if code_extensions:
        suffix = Path(normalized).suffix.lstrip(".").lower()
        return suffix in code_extensions

    # No constraints configured — any edit counts.
    return True


CONTINUE_REASON = (
    "OVERSEER_PASS recorded. Proceed with the next unit per the active slice plan in .engine/slices/. "
    "Do the next pending UNIT's work (code edits + verification commands), then emit `=== UNIT N COMPLETE ===` on its own line. "
    "If the slice has no more code units (only smoke / G4 owner-driven steps remain), or if you are uncertain what UNIT N is, "
    "emit `OVERSEER_SLICE_AWAITING_OWNER: <reason>` on its own line to halt and request owner input. "
    "If the slice's last code unit is complete and smoke / G4 are next, emit `OVERSEER_SLICE_AWAITING_OWNER: smoke and G4 are owner-driven; awaiting owner walkthrough.`"
)

# --- the texts the builder gets ---------------------------------------------------------------
FRESH_REQUEST_REASON = (
    "OVERSEER_REQUEST {id} (auto-triggered by the Stop hook on a unit-completion claim). The audit is "
    "not yours to do: a separate agent in a fresh context does it.\n"
    "Launch the agent `overseer` (Agent tool, subagent_type `overseer`, run_in_background false) with "
    "exactly this prompt and nothing else:\n"
    "OVERSEER_REQUEST {id}\n"
    "Add nothing to the prompt — a hook refuses any other text. Do not audit the work yourself and do "
    "not write a verdict: `OVERSEER_PASS` typed by you means nothing, and the ledger is written by a "
    "script from the agent's answer. Change nothing in the tree until the agent has answered — a tree "
    "that changes during the audit makes the verdict invalid. When it has answered, end the turn: this "
    "hook reads the recorded verdict and says what follows."
)
FRESH_REQUEST_AGAIN_REASON = (
    "OVERSEER_REQUEST {id} — still without a valid verdict ({why}); request {asks} of {limit}. Launch "
    "the agent `overseer` (subagent_type `overseer`, run_in_background false) with exactly this prompt "
    "and nothing else:\nOVERSEER_REQUEST {id}\n"
    "Leave the tree as it is until the agent has answered, then end the turn."
)
FRESH_BLOCK_REASON = (
    "OVERSEER_BLOCK (request {id}; BLOCK {count} of {limit} on this unit): {finding}\n"
    "The verdict is the overseer agent's and is recorded in the ledger (`python3 .claude/hooks/journal.py show ledger`). Route it as "
    ".claude/engine-rules.md § \"Verdict routing\" says. If you can resolve it: fix it, verify, and "
    "claim the unit again (`=== UNIT N COMPLETE ===`) — another overseer, which has seen neither this "
    "audit nor your fix, will judge the result. If you cannot: put the item on the task board — `python3 "
    ".claude/unattended/board.py open-item --to blocked --title … --what … --question …` (a question for the "
    "owner; `--to proposed` when it is work an agent could do: a proposal the owner puts to work) — and take the next "
    "unblocked one. Do not record a "
    "verdict yourself."
)
FRESH_THREE_BLOCKS_REASON = (
    "OVERSEER_BLOCK — the third in a row on one unit ({unit}; request {id}): {finding}\n"
    "Three overseers refused this unit, so it is no longer yours to retry: it is parked for the owner, "
    "and this hook has already put it before the owner ({parked}). Tell the human "
    "plainly, in your next message: which unit was refused three times, the three reasons below, what "
    "you tried. If a board task is in tasks/doing/: write that as a question under «Питання до власника» "
    "in the task, leave `Відповідь:` empty and move the task to tasks/blocked/. Then take the next "
    "unblocked item, or end the turn with `OVERSEER_SLICE_AWAITING_OWNER: three BLOCKs on {unit}` on "
    "its own line.\n{reasons}"
)
# To the person at the terminal (attended; under the board runner the owner reads tasks/blocked/
# instead), in the owner's language like everything the board says to the owner.
THREE_BLOCKS_HUMAN = (
    "Overseer тричі поспіль відхилив один юніт ({unit}). Повторювати його агент більше не буде: юніт "
    "відкладено до вашого рішення (запис — {parked}, вердикти — у ledger: "
    "`python3 .claude/hooks/journal.py show ledger`).\n{reasons}"
)
# Under the board runner nothing is asked of the builder: the session is stopped and the runner
# moves the task (board 031 — the rule is carried out by a script, not by an agent on its word).
THREE_BLOCKS_RUNNER_STOP = (
    "OVERSEER_BLOCK — the third in a row on one unit ({unit}; request {id}): {finding}\n"
    "Three overseers refused this unit. The session is stopped here: the board runner moves the task "
    "{task} to tasks/blocked/ with the three verdicts and a question to the owner, and takes the next task.\n{reasons}"
)
FRESH_ROUTE_REASON = (
    "OVERSEER_{verdict} (request {id}): {finding}\n"
    "The draft ADR or the escalation is in the newest entry of the ledger, at the top of what "
    "`python3 .claude/hooks/journal.py show ledger` prints (the shared .engine/overseer/ledger.md alone may not hold it yet). Route it as "
    ".claude/engine-rules.md § \"Verdict routing\" says: reversible — write the ADR in docs/adr/, or "
    "log the AUTONOMOUS entry in .engine/overseer/escalations.md (a log of decisions already made), and "
    "continue; a one-way door or an Article 5 product decision — ask the owner on the task board (`python3 "
    ".claude/unattended/board.py open-item --to blocked --title … --what … --question …`) and take the next "
    "unblocked item."
)
FRESH_PASS_IGNORED_REASON = (
    "OVERSEER_PASS IGNORED. A verdict typed by the builder means nothing: every audit is done by the "
    "agent `overseer` in a fresh context and recorded by a script (.claude/hooks/overseer_verdict.py). "
    "If a unit is complete, end the message with `=== UNIT N COMPLETE ===` on its own line, after the "
    "code edit and its verification, and the audit will be requested. To stop for real, emit an "
    "OVERSEER_ halt marker naming the reason. Otherwise carry on with the work."
)
FRESH_REQUEST_TYPED_REASON = (
    "OVERSEER_REQUEST typed by you starts nothing: a request is made by a script, and the audit by the "
    "agent `overseer`. To have a turn audited by hand (.claude/skills/overseer/SKILL.md): (1) the turn "
    "must be a file — a recorded turn as it is, a turn from this conversation written out verbatim; "
    "(2) run `python3 .claude/hooks/overseer_verdict.py request --turn-file <file> --unit <N>`; (3) launch "
    "the agent `overseer` (Agent tool, subagent_type `overseer`, run_in_background false) with exactly "
    "the line that command prints; (4) report the agent's verdict as it gave it. Do not audit the turn "
    "yourself."
)
NOT_WIRED_REASON = (
    "OVERSEER NOT WIRED — this unit cannot be audited. Every audit is done by the agent `overseer` and "
    "recorded by .claude/hooks/overseer_verdict.py, which works only through two handlers in "
    ".claude/settings.json; this project's settings do not carry them, so no request was made.\n"
    "Do NOT audit the unit yourself and do NOT type a verdict: neither counts. You cannot fix this "
    "either — the settings file is the owner's. Put the unit before the owner as a task of the board "
    "(`python3 .claude/unattended/board.py open-item --to blocked --title … --what … --question …`; what "
    "unblocks it: `python3 <engine>/engine.py update <this project>` has been run — it adds "
    "the two handlers — or they are added by hand: PreToolUse, matcher "
    "`Agent|Task|Edit|Write|MultiEdit|NotebookEdit`, command `python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/"
    "overseer_verdict.py\" guard`; SubagentStop, matcher `overseer`, the same command with `record`). If a "
    "board task is in tasks/doing/: write that as a question under «Питання до власника» in the task, "
    "leave `Відповідь:` empty and move the task to tasks/blocked/. Then "
    "take the next unblocked item, or end the turn with `OVERSEER_SLICE_AWAITING_OWNER: the overseer is "
    "not wired in the settings` on its own line."
)
# To the person at the terminal (attended; unattended the builder asks on the board, as the reason
# above says), in the owner's language like everything the board says to the owner.
NOT_WIRED_HUMAN = (
    "Overseer не підключений у .claude/settings.json цього проєкту, тому юніт ніхто не перевірив. "
    "Запустіть `engine.py update <проєкт>` — він додасть два обробники overseer_verdict.py (guard і record) — "
    "і перезапустіть Claude Code."
)
REQUEST_TYPED_RE = re.compile(r"^[ \t>*`]*OVERSEER_REQUEST\b", re.MULTILINE)

GATE_OPEN_NOTICE = (
    "\n\nGATE ESCALATION OPEN ({scope}; opened {stamp}). "
    "OVERSEER_PASS will not be accepted for this work until the owner closes it — by answering "
    "«так» under the gate's question in tasks/blocked/ (the board runner then closes it), or with "
    "`gate.py --close-escalation` in their own terminal. Neither is yours to do: audit as usual, "
    "but the verdict cannot be PASS."
)
COLLECTOR_FAILED_NOTICE = (
    "\n\nGATE-ALLOW REVIEW — the collector failed ({error}), so this request does NOT show the "
    "gate exemptions the diff adds. Run `python3 .claude/hooks/gate_allows.py` yourself, or read "
    "the diff for `gate-allow:` markers, and judge every reason before the verdict (check #4)."
)
NO_SLICE = "(none)"


def _open_gate_escalation(project_dir: Path) -> tuple[str, str] | None:
    """(timestamp, scope text) of the Stop gate's open escalation that covers the work a verdict
    would now speak for, or None.

    Package costs. When gate.py gives up after GATE_MAX_BLOCKS blocks in a row it records the
    escalation in .claude/state/gate/escalations.json (and parks an entry for the human). Machine
    state, not the park queue: the queue is the agent's own file, and its template tells the agent
    to mark entries RESUMED. Only `gate.py --close-escalation`, which refuses inside a Claude Code
    session, takes an escalation out of `open`: the owner runs it in their own terminal, or the
    board runner does on the owner's answer «так» under the gate's question in tasks/blocked/.

    Covers — by FILES, never by the slice's name: the active slice is whatever .engine/PROGRESS.md
    says, and the agent writes that file. An escalation holds the unit whose own change to a file
    the gate blocked on is still in the range no accepted PASS has covered; the work of another
    board task, which did not touch those files, passes, and its PASS leaves them unjudged (board
    301: gate_allows.escalation_over, where the rule and its reasons are). An escalation that
    recorded no file holds for everything. The slice is named in the message only."""
    try:
        import gate_allows

        return gate_allows.escalation_over(project_dir)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    try:   # cannot tell whose the work is: the lock holds rather than opens
        data = json.loads(
            (project_dir / ".claude" / "state" / "gate" / "escalations.json").read_text(encoding="utf-8")
        )
        entry = next(e for e in data.get("open", []) if isinstance(e, dict))
    except (OSError, ValueError, AttributeError, StopIteration):
        return None
    return str(entry.get("stamp", "?")), "its files could not be compared with this work — it covers all work"


def _gate_allow_review(project_dir: Path) -> str:
    """Package costs: the gate exemptions no accepted PASS has seen yet, for the overseer to judge.

    Empty when there are none, so the request text is unchanged for every turn that silenced
    nothing. A collector that fails says so in the request: silence there would read as "none"."""
    try:
        import gate_allows

        listing = gate_allows.render(gate_allows.record_request(project_dir))
        # Board 301: the files an open escalation keeps out of this audit, and the held ones it gets back.
        listing = "\n\n".join(part for part in (listing, gate_allows.aside_note(project_dir)) if part)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return COLLECTOR_FAILED_NOTICE.format(error=f"{type(exc).__name__}: {exc}"[:160])
    return f"\n\n{listing}" if listing else ""


def _drop_request(project_dir: Path) -> None:
    """What the last audit request showed becomes "judged" only through a recorded PASS (the
    verdict script promotes it); a request that ends any other way judged nothing. Best effort."""
    try:
        import gate_allows

        gate_allows.drop_request(project_dir)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        pass


DRY_RUN_REASON = (
    "DRY-RUN: would have blocked — the overseer Stop hook is wired and live. "
    "No real unit-completion was evaluated; this is a smoke-test injection."
)


def _emit_block(reason: str, system_message: str = "") -> NoReturn:
    """Print the block decision and exit 0 — Claude injects `reason` and
    continues the turn. `system_message` is shown to the person at the terminal."""
    json.dump({"decision": "block", "reason": reason} | ({"systemMessage": system_message} if system_message else {}),
              sys.stdout, ensure_ascii=False)
    sys.exit(0)


def _emit_halt(reason: str) -> NoReturn:
    """Stop the session outright (`continue: false` outranks any hook's block): nothing is
    injected and the builder gets no further turn."""
    json.dump({"continue": False, "stopReason": reason}, sys.stdout, ensure_ascii=False)
    sys.exit(0)


def _passthrough() -> NoReturn:
    """Exit silently with no decision — the turn ends normally."""
    sys.exit(0)


def _read_envelope() -> dict[str, object]:
    """Parse the Stop envelope from stdin. A malformed or non-object payload
    degrades to an empty envelope, never a crash — a hook must not break a
    turn over bad input."""
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items()}


def _str_field(envelope: dict[str, object], key: str) -> str:
    """Read a string field from the envelope, or `""` if absent / wrong type."""
    value = envelope.get(key)
    return value if isinstance(value, str) else ""


def _phase_is_plan(project_dir: Path) -> bool:
    """True if `.claude/state/overseer/state` exists and names the planning phase."""
    try:
        content = (project_dir / ".claude" / "state" / "overseer" / "state").read_text(
            encoding="utf-8"
        )
    except OSError:
        return False
    return "plan" in content.lower()


def _audit_sha_file(project_dir: Path) -> Path:
    return project_dir / ".claude" / "state" / "overseer" / ".last_audit_sha"


def _message_digest(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _already_audited(project_dir: Path, message: str) -> bool:
    """True if an audit was already requested for this exact message text."""
    try:
        recorded = _audit_sha_file(project_dir).read_text(encoding="utf-8")
    except OSError:
        return False
    return recorded.strip() == _message_digest(message)


def _record_audit(project_dir: Path, message: str) -> None:
    """Persist this message's digest so the SHA guard suppresses a re-fire."""
    sha_file = _audit_sha_file(project_dir)
    sha_file.parent.mkdir(parents=True, exist_ok=True)
    sha_file.write_text(_message_digest(message) + "\n", encoding="utf-8")


def _same_continue_message(project_dir: Path, message: str) -> bool:
    """The PASS branch's recursion guard: True when this exact message already got its answer
    (continue, or refused); otherwise records it and returns False."""
    sha_file = project_dir / ".claude" / "state" / "overseer" / ".last_continue_sha"
    digest = _message_digest(message)
    try:
        if sha_file.read_text(encoding="utf-8").strip() == digest:
            return True
    except OSError:
        pass
    try:
        sha_file.parent.mkdir(parents=True, exist_ok=True)
        sha_file.write_text(digest + "\n", encoding="utf-8")
    except OSError:
        pass
    return False


CONTRACT_CHANGED_REASON = (
    "CONTRACT CHANGED AFTER APPROVAL — no audit was run. The active slice contract {contract} "
    "no longer matches the fingerprint sealed when the planner-critic loop approved it "
    "({fingerprint}). An audit against a moved goalpost proves nothing, so this turn is "
    "ESCALATED instead: put it before the owner as a task of the board (`python3 .claude/unattended/board.py "
    "open-item --to blocked --title … --what … --question …`), naming the "
    "contract, what changed (git diff it), and who changed it; then either restore the "
    "approved contract, or have the OWNER delete the fingerprint and re-plan the slice with "
    "/plan-slice. Do not delete the fingerprint yourself. The owner may not be at the terminal: if a "
    "board task is in tasks/doing/, write that as a question under «Питання до власника» in the task, "
    "leave `Відповідь:` empty and move the task to tasks/blocked/. End the turn with OVERSEER_ESCALATE: "
    '{{"reason": "contract changed after approval", "contract": "{contract}"}}.'
)


TESTING_REASON = (
    "TESTING NOT SETTLED — no audit was run. {reason}. A slice with a sealed contract is audited only after "
    "the testing manager decided at point (a) who writes its contract tests and, when that is the independent "
    "tester, after its hand-in was accepted and the sealed tests are unchanged (.claude/hooks/testing.py holds "
    "this; `python3 .claude/hooks/testing.py status` shows where the slice stands). Do that, then claim the unit "
    "again. If it cannot be done without the owner, put it before them as a task of the board (`python3 "
    ".claude/unattended/board.py open-item --to blocked --title … --what … --question …`) and go on with the "
    "next unblocked item."
)


def _testing_block(project_dir: Path) -> str | None:
    """Why testing.py lets no audit be requested for the active slice yet; None when it does (and
    when the slice has no sealed contract, or the script cannot be read: testing never breaks the audit)."""
    try:
        import gate
        import testing

        return testing.audit_block(project_dir.resolve(), gate.active_slice(project_dir))
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        return None


def _active_contract(project_dir: Path) -> Path | None:
    """The contract of the slice .engine/PROGRESS.md marks IN PROGRESS; gate.active_slice owns
    the convention."""
    import gate

    slug = gate.active_slice(project_dir)
    return project_dir / ".engine" / "slices" / f"{slug}.md" if slug else None


def _contract_changed(project_dir: Path) -> tuple[Path, Path] | None:
    """(contract, fingerprint) when the active contract no longer matches its sealed
    fingerprint; None when it matches, has no fingerprint, or there is no active slice."""
    contract = _active_contract(project_dir)
    if contract is None or not contract.is_file():
        return None
    fingerprint = project_dir / ".claude" / "state" / "contracts" / f"{contract.stem}.sha256"
    if not fingerprint.is_file():
        return None
    try:
        recorded = fingerprint.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None
    actual = hashlib.sha256(contract.read_bytes()).hexdigest()
    return None if recorded == actual else (contract, fingerprint)


def _lesson_request(project_dir: Path) -> str:
    """The triage request a recorded PASS adds to "continue" (the queue itself was fed when the
    verdict was recorded). Best effort."""
    try:
        import lesson_queue

        lesson_queue.collect(project_dir)
        request = lesson_queue.review_request(project_dir, track=True)
        return f"\n\n{request}" if request else ""
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return ""


def _code_changed_in_tree(project_dir: Path, source_dirs: list[str], code_extensions: frozenset[str]) -> bool:
    """The edit signal read from the tree, whichever tool wrote the file (board 707: a unit written
    with `cat > file` or by a script left no Edit call and was never audited). True when a code
    path differs from what the last audit request saw — its content then, or the commit that
    request stood on; with no request yet, when one is among the files no accepted PASS has covered."""
    import gate
    import gate_allows
    import overseer_verdict as ov

    def changed(rel: str, seen: str) -> bool:
        path = project_dir / rel
        return seen != (hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "absent")

    def is_code(rel: str) -> bool:
        return _is_code_path(rel, source_dirs, code_extensions)

    try:
        now = ov.tree_fingerprint(project_dir) or {}
        before = (ov.last_request(project_dir) or {}).get("tree")
        if not now or not before:
            return any(is_code(rel) for rel in gate_allows.unit_files(project_dir))
        old, names = dict(before["files"]), set(before["files"]) | set(now["files"])
        if before["head"] != now["head"]:
            names.update(gate.lines_of(gate.git(project_dir, "diff", "--name-only", str(before["head"]), str(now["head"]))))
        return any(is_code(rel) and changed(rel, str(old.get(rel, "")).partition(":")[2]) for rel in names)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _claimed_unit(project_dir: Path, envelope: dict[str, object], message: str) -> str | None:
    """The unit number when this message is a NEW completion claim: the sentinel, not yet answered,
    and — since the last overseer audit of this turn — a code edit plus a verification command."""
    import overseer_verdict

    found = UNIT_NUMBER_RE.search(message)
    if not found or _already_audited(project_dir, message):
        return None
    cfg = _load_project_env(project_dir)
    source_dirs, code_extensions = _build_source_dirs(cfg), _build_code_extensions(cfg)
    check_cmd_re = _build_check_cmd_re(cfg)
    events = overseer_verdict.since_last_audit(overseer_verdict.turn_events(_str_field(envelope, "transcript_path")))
    edited = any(e["tool"] in EDIT_TOOLS and _is_code_path(str(e["input"].get("file_path", "")), source_dirs, code_extensions)
                 for e in events) or _code_changed_in_tree(project_dir, source_dirs, code_extensions)
    checked = any(e["tool"] == "Bash" and check_cmd_re.search(str(e["input"].get("command", ""))) for e in events)
    return found.group(1) if edited and checked else None


def _three_blocks(project_dir: Path, unit: str, request_id: str, finding: str, blocks: list[dict[str, object]]) -> NoReturn:
    """Three overseers in a row refused one unit. Under the board runner the task is the runner's to
    move: a marker with the verdicts is left for it and the session is stopped — the builder is asked
    nothing. Anywhere else the park entry is written here and the person at the terminal is told."""
    import overseer_verdict as ov

    kept = [{"utc": row.get("utc"), "request": row.get("request"), "check": row.get("check"), "reason": row.get("reason")} for row in blocks]
    reasons = "\n".join(f"BLOCK {n}: " + (f"#{row['check']} " if row["check"] else "") + str(row["reason"]) for n, row in enumerate(kept, 1))
    task = ov.board_task(project_dir)
    if task != "-" and ov.runner_alive(project_dir):
        ov.write_json(ov.three_blocks_marker(project_dir, task), {"task": task, "unit": unit, "utc": ov.utc_now(), "blocks": kept})
        _emit_halt(THREE_BLOCKS_RUNNER_STOP.format(unit=unit, id=request_id, finding=finding, task=task, reasons=reasons))
    parked = ov.park(project_dir, unit, "three BLOCKs in a row — " + "; ".join(reasons.splitlines()), ov.LEDGER_SHOWN)
    _emit_block(FRESH_THREE_BLOCKS_REASON.format(unit=unit, id=request_id, finding=finding, reasons=reasons, parked=parked),
                THREE_BLOCKS_HUMAN.format(unit=unit, reasons=reasons, parked=parked))


def _answer_pending(project_dir: Path, envelope: dict[str, object], message: str, waiting: dict[str, object]) -> str | None:
    """A request is waiting. Returns the text that hands its verdict to the builder, or None when
    the verdict ends the matter without a word (a manual audit: the report is the human's).
    Does not return when the request must be repeated, waits for a running agent, or is parked."""
    import overseer_verdict as ov

    request_id = str(waiting["id"])
    row = ov.verdict_for(project_dir, request_id)
    if row is None or row.get("verdict") == ov.INVALID:
        if HALT_MARKER_RE.search(message):   # the builder stops for real: the request dies with the turn
            ov.drop_pending(project_dir)
            _drop_request(project_dir)
            _passthrough()
        if row is None and waiting.get("launched") and envelope.get("background_tasks"):
            _passthrough()   # the agent runs in the background; its end re-invokes the session
        asks = int(str(waiting.get("asks", 1)))
        why = str(row["reason"]) if row else ("the agent left no verdict" if waiting.get("launched") else "the agent was not launched")
        if asks >= ov.MAX_ASKS:
            ov.park(project_dir, str(waiting.get("unit_key") or request_id),
                    f"audit request {request_id} got no valid verdict in {asks} requests: {why}",
                    (ov.REQUESTS_REL / request_id).as_posix())
            ov.drop_pending(project_dir)
            _drop_request(project_dir)
            _passthrough()
        ov.write_json(project_dir / ov.PENDING_REL, dict(waiting) | {"asks": asks + 1, "schema_errors": 0})
        _emit_block(FRESH_REQUEST_AGAIN_REASON.format(id=request_id, why=why[:300], asks=asks + 1, limit=ov.MAX_ASKS))
    ov.drop_pending(project_dir)
    if waiting.get("origin") == "manual":
        return None
    verdict, check = str(row["verdict"]), row.get("check")
    finding = (f"#{check} " if check else "") + str(row.get("reason", ""))
    if verdict == "PASS":
        return CONTINUE_REASON + _lesson_request(project_dir)
    if verdict == "BLOCK":
        unit = str(row.get("unit_key", ""))
        count = ov.blocks_in_a_row(project_dir, unit)
        if count >= ov.MAX_BLOCKS:
            # The row restarts the count: after the owner's answer the unit gets three attempts again.
            blocks = ov.last_blocks(project_dir, unit)
            ov.append_row(project_dir, {"utc": ov.utc_now(), "request": request_id, "unit_key": unit, "verdict": "PARK",
                                        "reason": f"{count} BLOCKs in a row"})
            _record_audit(project_dir, message)
            _three_blocks(project_dir, unit, request_id, finding, blocks)
        return FRESH_BLOCK_REASON.format(id=request_id, count=count, limit=ov.MAX_BLOCKS, finding=finding)
    return FRESH_ROUTE_REASON.format(verdict=verdict, id=request_id, finding=finding)


def _main_fresh(envelope: dict[str, object], project_dir: Path) -> NoReturn:
    """The overseer is a separate agent (see the module docstring, WHO AUDITS)."""
    import overseer_verdict as ov

    message = _str_field(envelope, "last_assistant_message")
    waiting = ov.pending(project_dir)
    answer = _answer_pending(project_dir, envelope, message, waiting) if waiting is not None else None
    if waiting is not None and answer is None:
        _passthrough()

    # A new claim is audited whatever else the message says — a halt marker beside the sentinel
    # does not buy the unit out of its audit.
    unit = None if _phase_is_plan(project_dir) else _claimed_unit(project_dir, envelope, message)
    if unit is not None:
        _record_audit(project_dir, message)
        changed = _contract_changed(project_dir)
        if changed is not None:
            contract, fingerprint = changed
            _emit_block(CONTRACT_CHANGED_REASON.format(contract=contract.relative_to(project_dir).as_posix(),
                                                       fingerprint=fingerprint.relative_to(project_dir).as_posix()))
        testing_reason = _testing_block(project_dir)
        if testing_reason is not None:
            _emit_block(TESTING_REASON.format(reason=testing_reason[:1].upper() + testing_reason[1:]))
        escalation = _open_gate_escalation(project_dir)
        request = ov.make_request(
            project_dir, message, origin="hook", unit=unit, transcript_path=_str_field(envelope, "transcript_path"),
            gate_allows_text=_gate_allow_review(project_dir),
            gate_escalation=f"{escalation[0]}: {escalation[1]}" if escalation else "")
        text = FRESH_REQUEST_REASON.format(id=request["id"])
        if escalation is not None:
            text += GATE_OPEN_NOTICE.format(stamp=escalation[0], scope=escalation[1])
        _emit_block((f"{answer}\n\nYour message already claims the unit again, so the next audit is requested now.\n\n"
                     if answer and "OVERSEER_PASS recorded" not in answer else "") + text)
    if answer is not None:
        _emit_block(answer)

    if HALT_MARKER_RE.search(message):
        _drop_request(project_dir)
        _passthrough()
    if PASS_MARKER_RE.search(message) and not _same_continue_message(project_dir, message):
        _emit_block(FRESH_PASS_IGNORED_REASON)
    if REQUEST_TYPED_RE.search(message) and not _same_continue_message(project_dir, message):
        _emit_block(FRESH_REQUEST_TYPED_REASON)
    _passthrough()


def _main_unwired(envelope: dict[str, object], project_dir: Path) -> NoReturn:
    """The project's settings lack the overseer's handlers: nothing could record a verdict, so no
    request is made. A claim is answered once with the way out; everything else is as usual."""
    message = _str_field(envelope, "last_assistant_message")
    if not _phase_is_plan(project_dir) and _claimed_unit(project_dir, envelope, message) is not None:
        _record_audit(project_dir, message)
        _emit_block(NOT_WIRED_REASON, NOT_WIRED_HUMAN)
    _passthrough()


def main() -> NoReturn:
    envelope = _read_envelope()
    if "--dry-run" in sys.argv[1:]:
        _emit_block(DRY_RUN_REASON)

    import overseer_verdict

    project_dir = _get_project_dir()
    if not overseer_verdict.wired(project_dir):
        _main_unwired(envelope, project_dir)
    _main_fresh(envelope, project_dir)


if __name__ == "__main__":
    main()
