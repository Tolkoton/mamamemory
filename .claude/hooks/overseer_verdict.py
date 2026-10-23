#!/usr/bin/env python3
"""overseer_verdict.py — the audit request, the guard around the `overseer` agent, and the one
writer of verdicts (board 015 / 018).

Every audit is done by a separate agent in a fresh context (`.claude/agents/overseer.md`: Read,
Grep, Glob, Bash — no editing tool). The builder never judges its own work and never writes a
verdict: a line `OVERSEER_PASS` in the builder's message means nothing.

    python3 .claude/hooks/overseer_verdict.py guard     # hook, PreToolUse on Agent
    python3 .claude/hooks/overseer_verdict.py record    # hook, SubagentStop of the agent `overseer`
    python3 .claude/hooks/overseer_verdict.py request --turn-file FILE [--unit N]   # an audit by hand
    python3 .claude/hooks/overseer_verdict.py status    # the pending (or just answered) request and the last verdicts

THE REQUEST. `overseer_stop.py` (or `request`, by hand) writes a package the agent reads instead of
the builder's conversation, under .claude/state/overseer/requests/<id>/:
  turn.md       the builder's final message — the claims to be checked
  evidence.md   the commands that really ran in that turn, in order, with the tail of their output,
                and the files that were edited; taken from the transcript, not from the message
  request.json  id, unit, attempt, the contract and its sha256, the gate-allow list, the open gate
                escalation, PASS verdicts in a row on the slice, the task's mode (mode.py show,
                board 097), the fingerprint of the tree, the moment it was written (`created_ns`:
                with the second in the id it says which request is the last one, board 752)
and names it in .claude/state/overseer/pending.json. The builder is told to launch the agent with
the prompt `OVERSEER_REQUEST <id>` and nothing else.

GUARD. The agent `overseer` starts only for the pending request and only with exactly that prompt:
the builder can neither hint at a conclusion nor aim the audit elsewhere. At that moment the tree
is fingerprinted. Inside the agent the Agent tool is refused; that it edits nothing and writes
nothing by shell outside a temporary directory is the perimeter hooks' (protect-paths.sh,
block-dangerous.sh with shell_readonly.py: board 055).

RECORD. The agent answers with one JSON object. This script — never a model — checks it against
the schema (the first failure goes back to the agent, the second is recorded INVALID), compares
the tree with the fingerprint (HEAD, `git status`, the content of every changed or untracked file;
ignored files do not count) and the contract with its sha256 — any difference makes the verdict
INVALID, nothing is rolled back — refuses a PASS while the Stop gate's escalation is open, and then
writes the entry into the ledger (this session's own file of it, .engine/journal/ledger/, board 739) and a row into
.claude/state/overseer/verdicts.jsonl. Hooks decide on the second file; the ledger is for people
and for the next overseer.

TEST GAPS (board 077, the owner's decision). A gap in the tests of code that does what the claim
says — a wrong implementation the tests let through, an edge case none tries — does not stop the
unit: the agent answers PASS and lists each gap in `test_gaps`, and this script opens one item per
gap in tasks/proposed/ (board.py open_item; the owner puts it to work, board 111; without a board the ledger alone keeps it). A BLOCK on
check #4 is refused unless it names a silenced check (a gate-allow and its kin): that is all #4
still blocks. So a test gap never counts toward the three BLOCKs that park a unit.

LIMIT. A hook cannot tell that it was started by Claude Code and not by the builder's own Bash: an
agent that deliberately feeds `record` a made-up envelope, or writes .claude/state/ itself, forges
a verdict. The rules forbid both; nothing here makes them impossible (docs/engine-limits.md).

Standard library only. A hook never breaks a turn over bad input: it exits 0 and decides nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import journal  # the ledger and the parked log: every session adds to its own file (board 739)

sys.path.insert(0, str(Path(__file__).resolve().parent))

JsonObj = dict[str, Any]

AGENT = "overseer"
REQUEST_WORD = "OVERSEER_REQUEST"
WIRING_MARK = "overseer_verdict.py"
STATE_REL = Path(".claude/state/overseer")
REQUESTS_REL = STATE_REL / "requests"
PENDING_REL = STATE_REL / "pending.json"
VERDICTS_REL = STATE_REL / "verdicts.jsonl"
LEDGER_REL = Path(".engine/overseer/ledger.md")
PARKED_REL = Path(".engine/overseer/parked.md")
# Where a person or an agent reads a verdict (board 739): the ledger whole — the shared file holds only what a fold
# gathered, the newest entries stand in the sessions' own files under .engine/journal/ledger/.
LEDGER_SHOWN = "the ledger, `python3 .claude/hooks/journal.py show ledger` (newest at the top)"
BOARD_STATE_REL = Path(".claude/state/board")   # the board runner's state: its lock, and the marker left for it
VERDICTS = ("PASS", "BLOCK", "ADR_REQUIRED", "ESCALATE")
INVALID = "INVALID"
CATEGORIES = ("strategy", "recovery", "optimization", "none")
MAX_BLOCKS = 3      # the owner's number (board 015, answer 4): three BLOCKs on one unit park the task
MAX_ASKS = 3        # the request itself and two repeats; then the item is parked and the turn ends
PASSES_FOR_ADVOCATE = 3
# What check #4 may still block (board 077): a silenced check — a gate-allow, a type-ignore or
# no-qa marker, a skip, a loosened setting. A missing or weak test is a test gap, never a BLOCK.
SILENCED_RE = re.compile(r"gate[- ]?allow|exemption|suppress|ignore|noqa|no-qa|skip|xfail|silenc|loosen", re.IGNORECASE)
GAP_FIELDS = ("check", "misses")
GAP_CHECK_CHARS = 2000   # a board item carries the check whole; an auditor's check runs to a few hundred characters
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
AGENT_TOOLS = frozenset({"Agent", "Task"})
OUTPUT_TAIL_LINES = 15
OUTPUT_TAIL_CHARS = 1500
FILE_LINE_RE = re.compile(r"^`?([\w./-]+\.[\w]+):(\d+)\b")
ENTRY_HEADER_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}T\S* — (?P<slice>.+?) — (?P<verdict>.+)$", re.MULTILINE)
# The ledger's Action line: what the verdict does next, which is the hook's doing, not the agent's.
ACTIONS = {
    "PASS": "unit accepted; the builder continues",
    "PASS+gaps": "unit accepted; the builder continues, and each test gap is an item of the board for an agent to write the test",
    "BLOCK": "returned to the builder: fix and claim again, another overseer judges it (BLOCK on attempt {attempt}; {limit} in a row park the unit)",
    "ADR_REQUIRED": "ADR draft handed to the builder for routing (.claude/engine-rules.md, Verdict routing)",
    "ESCALATE": "escalation handed to the builder for routing (.claude/engine-rules.md, Verdict routing)",
    INVALID: "no verdict: the audit is repeated by another overseer",
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_root() -> Path:
    env_val = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_val:
        return Path(env_val).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5, check=False)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.cwd()


def read_json(path: Path) -> JsonObj:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: JsonObj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def wired(root: Path) -> bool:
    """Is this script wired in the project's settings? `engine.py install` / `update` put its two
    handlers there (board 033). Where they are missing nothing can record a verdict, so
    `overseer_stop.py` makes no request and says so: there is no other way to audit."""
    for name in ("settings.json", "settings.local.json"):
        try:
            if WIRING_MARK in (root / ".claude" / name).read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


# ------------------------------------------------------------------ the tree's fingerprint


def tree_fingerprint(root: Path) -> JsonObj | None:
    """HEAD plus the status and content hash of every file git reports as changed or untracked.
    Ignored files (caches, .claude/state/) are not part of it. None outside a git repository."""
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],
            capture_output=True, timeout=30, check=False)
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "-q", "--verify", "HEAD"],
                              capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if status.returncode != 0:
        return None
    files: dict[str, str] = {}
    for record in status.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if len(record) < 4:
            continue
        code, rel = record[:2], record[3:]
        path = root / rel
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "absent"
        except OSError:
            digest = "unreadable"
        files[rel] = f"{code}:{digest}"
    return {"head": head.stdout.strip(), "files": files}


def fingerprint_diff(before: JsonObj | None, after: JsonObj | None) -> list[str]:
    """What differs between two fingerprints: file paths, and `HEAD` when the commit moved."""
    if before is None or after is None:
        return []
    changed = ["HEAD"] if before.get("head") != after.get("head") else []
    old, new = before.get("files") or {}, after.get("files") or {}
    return changed + sorted(rel for rel in set(old) | set(new) if old.get(rel) != new.get(rel))


# ------------------------------------------------------------------ the turn's evidence


def _is_turn_boundary(record: JsonObj) -> bool:
    message = record.get("message")
    return isinstance(message, dict) and isinstance(message.get("content"), str)


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def turn_events(transcript_path: str) -> list[JsonObj]:
    """The tool calls of the current turn, in the order they ran: {"tool", "input", "result",
    "is_error"}. The current turn is everything after the last genuine user message."""
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines() if transcript_path else []
    except OSError:
        return []
    records: list[JsonObj] = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("type") in ("user", "assistant"):
            records.append(record)
    start = max((i for i, r in enumerate(records) if r.get("type") == "user" and _is_turn_boundary(r)), default=-1)
    events: list[JsonObj] = []
    by_id: dict[str, JsonObj] = {}
    for record in records[start + 1:]:
        content = (record.get("message") or {}).get("content") if isinstance(record.get("message"), dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                event = {"tool": str(block.get("name", "")), "input": block["input"], "result": None, "is_error": False}
                events.append(event)
                by_id[str(block.get("id", ""))] = event
            elif block.get("type") == "tool_result" and str(block.get("tool_use_id", "")) in by_id:
                event = by_id[str(block["tool_use_id"])]
                event["result"] = _result_text(block.get("content"))
                event["is_error"] = bool(block.get("is_error"))
    return events


def launches_overseer(event: JsonObj) -> bool:
    return event["tool"] in AGENT_TOOLS and event["input"].get("subagent_type") == AGENT


def since_last_audit(events: list[JsonObj]) -> list[JsonObj]:
    """The events after the last launch of the overseer agent: what a NEW claim may rest on."""
    last = max((i for i, e in enumerate(events) if launches_overseer(e)), default=-1)
    return events[last + 1:]


def _tail(text: str) -> str:
    lines = text.rstrip("\n").splitlines()[-OUTPUT_TAIL_LINES:]
    return "\n".join(lines)[-OUTPUT_TAIL_CHARS:]


def render_evidence(events: list[JsonObj], have_transcript: bool) -> str:
    head = ("# What really ran in the audited turn\n\n"
            "Written by a script from the session's transcript, not by the builder. Output that the turn\n"
            "quotes but that is not below was not a tool result of this turn.\n\n")
    if not have_transcript:
        return head + ("No transcript was available: the turn was handed over as a recorded file. Nothing below was\n"
                       "observed to run — every command the turn quotes is a quotation; reproduce what matters.\n")
    if not events:
        return head + "No tool was called in this turn: no file edited, no command run.\n"
    out = [head.rstrip("\n"), ""]
    for number, event in enumerate(events, 1):
        tool, tool_input = event["tool"], event["input"]
        if tool in EDIT_TOOLS:
            out.append(f"{number}. {tool} `{tool_input.get('file_path') or tool_input.get('notebook_path') or '?'}`")
        elif tool == "Bash":
            out.append(f"{number}. Bash{' (FAILED)' if event['is_error'] else ''}: `{str(tool_input.get('command', '')).strip()[:400]}`")
            result = event["result"]
            if result is None:
                out.append("   (no result recorded)")
            elif result.strip():
                out.extend(["   output (tail):", *("       " + line for line in _tail(result).splitlines())])
            else:
                out.append("   (no output)")
        elif launches_overseer(event):
            out.append(f"{number}. — an overseer audit ran here (`{str(tool_input.get('prompt', ''))[:60]}`) —")
        else:
            out.append(f"{number}. {tool}")
    out.append("\nOrder matters for #5: a verification that ran BEFORE the last edit of the file it verifies is stale.")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ requests and verdict rows


def pending(root: Path) -> JsonObj | None:
    data = read_json(root / PENDING_REL)
    return data if data.get("id") else None


def drop_pending(root: Path) -> None:
    (root / PENDING_REL).unlink(missing_ok=True)


def request_dir(root: Path, request_id: str) -> Path:
    return root / REQUESTS_REL / request_id


def launch_line(request_id: str) -> str:
    return f"{REQUEST_WORD} {request_id}"


def last_request(root: Path) -> JsonObj | None:
    """The request written last, read from what the requests say — the second in the id, then
    `created_ns` — never from a file's modification time: two written in one moment, or an old
    file touched later, made the choice a matter of chance (board 752)."""
    def moment(folder: Path) -> tuple[str, int, str]:
        created = read_json(folder / "request.json").get("created_ns")
        return folder.name[:16], created if isinstance(created, int) else 0, folder.name

    folders = [f.parent for f in (root / REQUESTS_REL).glob("*/request.json")]
    return read_json(max(folders, key=moment) / "request.json") if folders else None


def rows(root: Path) -> list[JsonObj]:
    try:
        lines = (root / VERDICTS_REL).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found: list[JsonObj] = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            found.append(row)
    return found


def append_row(root: Path, row: JsonObj) -> None:
    path = root / VERDICTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def verdict_for(root: Path, request_id: str) -> JsonObj | None:
    """The last row recorded for a request (an INVALID one included), or None."""
    return next((row for row in reversed(rows(root)) if row.get("request") == request_id), None)


def last_blocks(root: Path, unit_key: str) -> list[JsonObj]:
    """The BLOCK rows on this unit since its last other verdict, oldest first; an INVALID row judged nothing."""
    found: list[JsonObj] = []
    for row in reversed(rows(root)):
        if row.get("unit_key") != unit_key or row.get("verdict") == INVALID:
            continue
        if row.get("verdict") != "BLOCK":
            break
        found.append(row)
    return found[::-1]


def blocks_in_a_row(root: Path, unit_key: str) -> int:
    return len(last_blocks(root, unit_key))


def passes_in_a_row(root: Path, slice_name: str) -> int:
    """PASS entries at the top of the ledger for this slice (check #12 counts them), the ledger whole:
    the shared file and every session's file (board 739)."""
    text = journal.text(root, "ledger")
    count = 0
    for match in ENTRY_HEADER_RE.finditer(text):
        if match["slice"].strip() != slice_name:
            continue
        if "PASS" not in match["verdict"]:
            break
        count += 1
    return count


def board_task(root: Path) -> str:
    """The task in doing/ this session works on (board.py own): the owner's session's task beside
    the runner's is not the runner's unit. `-` when there is none or the board cannot be read."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        names = [p.stem for p in board.own(root / "tasks")]
    except (ImportError, OSError, ValueError, AttributeError):
        names = []
    return names[0] if names else "-"


def mode_line(root: Path) -> str:
    """The session's task's mode as its one reader prints it (mode.py show, board 097); "" when it cannot be read."""
    try:
        import mode

        return str(mode.show_line(root))
    except (ImportError, OSError, ValueError):
        return ""


def contract_of(root: Path, slice_name: str | None) -> JsonObj | None:
    if not slice_name:
        return None
    path = root / ".engine" / "slices" / f"{slice_name}.md"
    try:
        return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    except OSError:
        return None


def active_slice(root: Path) -> str | None:
    try:
        import gate

        return gate.active_slice(root)
    except (ImportError, OSError, ValueError):
        return None


def make_request(root: Path, turn: str, *, origin: str, unit: str = "1", transcript_path: str = "",
                 gate_allows_text: str = "", gate_escalation: str = "") -> JsonObj:
    """Write the request package and make it the pending one. Returns request.json's content."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    request_id = f"{stamp}-{hashlib.sha256((stamp + turn).encode('utf-8')).hexdigest()[:6]}"
    slice_name = active_slice(root)
    unit_key = f"{slice_name or '-'}|{board_task(root)}|unit {unit}"
    events = turn_events(transcript_path)
    request: JsonObj = {
        "id": request_id, "origin": origin, "created_utc": utc_now(), "created_ns": time.time_ns(),
        "slice": slice_name or "unknown", "unit": unit, "unit_key": unit_key,
        "attempt": blocks_in_a_row(root, unit_key) + 1,
        "contract": contract_of(root, slice_name),
        "passes_in_a_row": passes_in_a_row(root, slice_name or "unknown"),
        "gate_allows": gate_allows_text.strip(), "gate_escalation": gate_escalation.strip(),
        "mode": mode_line(root), "tree": tree_fingerprint(root),
    }
    folder = request_dir(root, request_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "turn.md").write_text(turn.rstrip("\n") + "\n", encoding="utf-8")
    (folder / "evidence.md").write_text(render_evidence(events, bool(transcript_path)), encoding="utf-8")
    write_json(folder / "request.json", request)
    write_json(root / PENDING_REL, {"id": request_id, "origin": origin, "unit_key": unit_key, "asks": 1,
                                    "schema_errors": 0, "launched": 0})
    return request


# ------------------------------------------------------------------ guard (PreToolUse)


def deny(reason: str) -> JsonObj:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def guard(root: Path, envelope: JsonObj) -> JsonObj | None:
    tool = str(envelope.get("tool_name", ""))
    raw_input = envelope.get("tool_input")
    tool_input: JsonObj = raw_input if isinstance(raw_input, dict) else {}
    if envelope.get("agent_type") == AGENT:
        # Its edits and shell writes are refused by the perimeter hooks (protect-paths.sh,
        # block-dangerous.sh: board 055); what is left here is that it starts no agent.
        if tool in AGENT_TOOLS:
            return deny(f"The overseer agent is read-only: {tool} is refused. Judge what is there yourself; "
                        "an auditor that starts another agent is no longer the one fresh reader of the request.")
        return None
    if tool not in AGENT_TOOLS or tool_input.get("subagent_type") != AGENT:
        return None
    waiting = pending(root)
    if waiting is None:
        return deny("No audit request is pending, so the overseer agent is not started. A request is made by the Stop "
                    "hook when a turn claims a unit complete, or by hand: `python3 .claude/hooks/overseer_verdict.py "
                    "request --turn-file <file with the turn to audit>`.")
    line = launch_line(str(waiting["id"]))
    if str(tool_input.get("prompt", "")).strip() != line:
        return deny(f"The overseer agent is started with exactly this prompt and nothing else: `{line}`. It reads the "
                    "request package itself; anything added to the prompt would be the builder speaking to its auditor.")
    # The audit begins here: this is the tree the verdict will be compared against.
    path = request_dir(root, str(waiting["id"])) / "request.json"
    request = read_json(path)
    if request:
        write_json(path, request | {"tree": tree_fingerprint(root), "launched_utc": utc_now()})
    write_json(root / PENDING_REL, waiting | {"launched": int(waiting.get("launched", 0)) + 1})
    return None


# ------------------------------------------------------------------ record (SubagentStop)


def parse_reply(text: str) -> tuple[JsonObj | None, str]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None, "the answer holds no JSON object"
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError as exc:
        return None, f"the answer is not valid JSON ({exc})"
    return (obj, "") if isinstance(obj, dict) else (None, "the answer is not a JSON object")


def schema_errors(root: Path, obj: JsonObj, request: JsonObj) -> list[str]:
    errors: list[str] = []
    verdict = obj.get("verdict")
    if verdict not in VERDICTS:
        return [f"`verdict` must be one of {', '.join(VERDICTS)}; got {verdict!r}"]
    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip() or "\n" in reason.strip():
        errors.append("`reason` must be one non-empty line")
    check = obj.get("check")
    if verdict == "BLOCK" and not (isinstance(check, int) and not isinstance(check, bool) and 1 <= check <= 12):
        errors.append("a BLOCK names the check that fired: `check` must be an integer 1-12")
    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(e, str) and e.strip() for e in evidence):
        errors.append("`evidence` must be a non-empty list of strings (file:line, a command and its result, a ledger entry)")
    else:
        for item in evidence:
            found = FILE_LINE_RE.match(item.strip())
            if not found:
                continue
            path = root / found.group(1)
            try:
                count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                errors.append(f"evidence cites `{found.group(1)}:{found.group(2)}`, and there is no such file")
                continue
            if int(found.group(2)) < 1 or int(found.group(2)) > count:
                errors.append(f"evidence cites `{found.group(1)}:{found.group(2)}`, and the file has {count} lines")
    if obj.get("category", "none") not in CATEGORIES:
        errors.append(f"`category` must be one of {', '.join(CATEGORIES)}")
    advocate = obj.get("devils_advocate")
    if int(request.get("passes_in_a_row", 0) or 0) >= PASSES_FOR_ADVOCATE and not (isinstance(advocate, str) and len(advocate.strip()) >= 40):
        errors.append(f"the ledger shows {request.get('passes_in_a_row')} PASS verdicts in a row on this slice (check #12): "
                      "`devils_advocate` must be a paragraph with the strongest case that the builder is wrong")
    if verdict == "ADR_REQUIRED" and not (isinstance(obj.get("adr"), dict) and obj["adr"]):
        errors.append("ADR_REQUIRED carries the draft: `adr` must be an object (title, context, decision, consequences)")
    if verdict == "ESCALATE" and not (isinstance(obj.get("escalation"), dict) and obj["escalation"].get("question")):
        errors.append("ESCALATE carries the question: `escalation` must be an object with category, question, options, "
                      "your_recommendation, evidence")
    gaps = obj.get("test_gaps")
    if gaps is not None:
        if not isinstance(gaps, list) or not all(
                isinstance(g, dict) and all(isinstance(g.get(k), str) and g[k].strip() for k in GAP_FIELDS) for g in gaps):
            errors.append("`test_gaps` must be a list of objects, each with `check` (the test to add, by name) and "
                          "`misses` (the wrong implementation or the case today's tests let through); `where` may name the file")
        elif gaps and verdict not in ("PASS", "BLOCK"):
            errors.append("`test_gaps` go with a PASS (or beside a BLOCK for another defect)")
    if verdict == "BLOCK" and check == 4 and isinstance(reason, str) and not SILENCED_RE.search(reason):
        errors.append("a test gap is not a BLOCK (the owner, board 077): when the code does what the claim says and only a "
                      "test is missing or weak, answer PASS and put the gap in `test_gaps` (check, misses, where) — the "
                      "script opens a board item for it. Check #4 blocks only a silenced check: name the gate-allow")
    return errors


def one_line(text: object, limit: int = 600) -> str:
    return " ".join(str(text).split())[:limit]


def ledger_entry(row: JsonObj, obj: JsonObj | None) -> str:
    verdict = str(row["verdict"])
    gaps = row.get("test_gaps") or []
    action = "PASS+gaps" if verdict == "PASS" and gaps else verdict
    header = verdict if verdict == INVALID else f"OVERSEER_{verdict}"
    check = row.get("check")
    trigger = f"#{check} — {row['reason']}" if check else (str(row["reason"]) if verdict != "PASS" else f"none — {row['reason']}")
    evidence = "; ".join(one_line(e, 200) for e in (obj or {}).get("evidence") or []) or "—"
    lines = [f"## {row['utc']} — {row['slice']} — {header}",
             f"- Trigger: {one_line(trigger)}",
             f"- Evidence: {one_line(evidence, 900)}",
             f"- Action: {ACTIONS[action].format(attempt=row.get('attempt', 1), limit=MAX_BLOCKS)}",
             f"- Category: {(obj or {}).get('category', 'none')}"]
    if gaps:
        lines.append("- Test gaps: " + one_line("; ".join(
            f"{g['check']} — {g['misses']}" + (f" → {g['task']}" if g.get("task") else " (no task board: recorded here only)")
            for g in gaps), 1500))
    if obj and isinstance(obj.get("devils_advocate"), str) and obj["devils_advocate"].strip():
        lines.append(f"- Devil's advocate: {one_line(obj['devils_advocate'], 1200)}")
    if obj and verdict == "ADR_REQUIRED":
        lines.append(f"- ADR draft: {one_line(json.dumps(obj.get('adr'), ensure_ascii=False), 1500)}")
    if obj and verdict == "ESCALATE":
        lines.append(f"- Escalation: {one_line(json.dumps(obj.get('escalation'), ensure_ascii=False), 1500)}")
    lines += [f"- Request: {row['request']} (attempt {row.get('attempt', 1)}, {row.get('origin', 'hook')})",
              "- Auditor: overseer agent"]
    return "\n".join(lines) + "\n"


def write_ledger(root: Path, entry: str) -> None:
    """Into this session's own file of the ledger (board 739): the shared .engine/overseer/ledger.md is
    what a fold gathered, newest first, and every reader takes the two together (journal.text)."""
    journal.add(root, "ledger", entry)


def open_gate_escalation(root: Path) -> tuple[str, str] | None:
    try:
        import overseer_stop

        return overseer_stop._open_gate_escalation(root)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def settle(root: Path, row: JsonObj) -> None:
    """What the gate-allow collector and the lesson queue learn from a verdict. Best effort."""
    try:
        import gate_allows

        if row["verdict"] == "PASS" and row.get("origin") == "hook":
            gate_allows.record_pass(root)
        elif row.get("origin") == "hook":
            gate_allows.drop_request(root)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    if row["verdict"] != "BLOCK":
        return
    try:
        import lesson_queue

        lesson_queue.add_from_verdict(root, f"OVERSEER_BLOCK: #{row.get('check') or '-'} {row['reason']}")
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        pass


def gap_key(check: str) -> str:
    """The key of a test gap's board item: a readable slug of the check and a hash of the whole of it.
    The slug alone gave two checks one item — the same first 60 characters, or no Latin letter at all
    (every check written in Cyrillic was `test-gap-`) — and the second gap never reached the board (board 108)."""
    text = " ".join(check.split()).casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-")
    return "-".join(part for part in ("test-gap", slug, hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]) if part)


def open_test_gaps(root: Path, row: JsonObj, gaps: list[JsonObj]) -> list[JsonObj]:
    """One proposal in tasks/proposed/ per test gap (board 077; board 111: the owner puts it to work), named by the check to write; `task` is its
    path, or empty without a board. The item's key is the check, so the same gap found again by the
    next overseer returns the item still open instead of a second one. Best effort."""
    opened: list[JsonObj] = []
    board: Any = None
    tasks: Any = None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board as board_module

        board = board_module
        tasks = board.Board(root / "tasks") if (root / "tasks").is_dir() else None
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        tasks = None
    # The verdict as it is recorded: a gap named beside a BLOCK for another defect read «прийняв … (PASS…)» (board 757).
    told, found = ("прийняв", "знайшов") if row.get("verdict") == "PASS" else ("повернув", "назвав ще й")
    for gap in gaps:
        # The whole check: the key is taken of it and the item carries it — cut to 200 characters, two checks
        # that differ only after them were one key and read the same (board 108). Only the title is short.
        check, misses = one_line(gap["check"], GAP_CHECK_CHARS), one_line(gap["misses"], 600)
        where = one_line(gap.get("where") or "", 200)
        task = ""
        if tasks is not None and board is not None:
            try:
                made = board.open_item(
                    tasks, "proposed", f"Брак тесту (overseer): {one_line(check, 200)}",
                    f"Overseer {told} юніт `{row.get('unit_key') or row.get('slice')}` ({row['verdict']}, запит `{row['request']}`) "
                    f"і {found} брак тесту: {misses}" + (f" Де: `{where}`." if where else "")
                    + " Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.",
                    do=(f"Дописати перевірку «{check}»: тест червоніє на тому, що описано вище ({misses}), і зелений "
                        "на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; "
                        "швидкий набір тестів зелений."),
                    key=gap_key(str(gap["check"])),
                    source="overseer (overseer_verdict.py)")
                task = made.relative_to(root).as_posix() if made else ""
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                task = ""
        opened.append({"check": check, "misses": misses, "where": where, "task": task})
    return opened


def schema_reason(errors: list[str]) -> str:
    return ("VERDICT REFUSED — the answer does not fit the schema:\n- " + "\n- ".join(errors[:6]) + "\n"
            "Answer again with the ONE JSON object and nothing else (verdict, check, reason, evidence, category; "
            "devils_advocate, adr or escalation where they apply). A second answer that does not fit is recorded "
            "INVALID and the audit is repeated by another overseer.")


def _handed_back(transcript_path: object) -> str:
    """The reply of an agent whose envelope carries none. An agent that used a tool hands its answer
    back through the tool call `SubagentHandback` (seen live, Claude Code 2.1.289, board 705 / 706): the
    reply is then the `message` of the last such call in the agent's own transcript."""
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8").splitlines() if transcript_path else []
    except OSError:
        return ""
    found = ""
    for line in lines:
        try:
            content = json.loads(line)["message"]["content"]
        except (ValueError, KeyError, TypeError):
            continue
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("name") == "SubagentHandback" and isinstance(block.get("input"), dict):
                found = str(block["input"].get("message") or "")
    return found


def record(root: Path, envelope: JsonObj) -> JsonObj | None:
    if envelope.get("agent_type") != AGENT or envelope.get("hook_event_name") not in (None, "SubagentStop"):
        return None
    waiting = pending(root)
    if waiting is None:
        return None
    request_id = str(waiting["id"])
    previous = verdict_for(root, request_id)
    if previous is not None and previous.get("verdict") != INVALID:
        return None   # this request already has its verdict; a second agent's word changes nothing
    request = read_json(request_dir(root, request_id) / "request.json")
    row: JsonObj = {"utc": utc_now(), "request": request_id, "origin": request.get("origin", "hook"),
                    "slice": request.get("slice", "unknown"), "unit_key": request.get("unit_key", ""),
                    "attempt": request.get("attempt", 1), "agent_id": envelope.get("agent_id", "")}

    def finish(verdict: str, reason: str, obj: JsonObj | None = None, check: object = None, **extra: object) -> None:
        row.update({"verdict": verdict, "reason": one_line(reason), "check": check, **extra})
        if obj and verdict in ("PASS", "BLOCK") and obj.get("test_gaps"):
            row["test_gaps"] = open_test_gaps(root, row, obj["test_gaps"])
        write_ledger(root, ledger_entry(row, obj))
        append_row(root, row)
        settle(root, row)

    obj, problem = parse_reply(str(envelope.get("last_assistant_message") or _handed_back(envelope.get("agent_transcript_path"))))
    errors = [problem] if obj is None else schema_errors(root, obj, request)
    if errors:
        if int(waiting.get("schema_errors", 0)) == 0:
            write_json(root / PENDING_REL, waiting | {"schema_errors": 1})
            return {"decision": "block", "reason": schema_reason(errors)}
        finish(INVALID, "the answer does not fit the schema: " + "; ".join(errors[:3]))
        return None
    assert obj is not None
    changed = fingerprint_diff(request.get("tree"), tree_fingerprint(root))
    if changed:
        finish(INVALID, "tree changed during audit: " + ", ".join(changed[:12])
               + (f" and {len(changed) - 12} more" if len(changed) > 12 else ""), obj, changed=changed[:50])
        return None
    contract = request.get("contract")
    if isinstance(contract, dict) and contract_of(root, str(request.get("slice"))) != contract:
        finish(INVALID, f"the contract {contract.get('path')} changed between the request and the verdict", obj)
        return None
    verdict, check = str(obj["verdict"]), obj.get("check") if isinstance(obj.get("check"), int) else None
    escalation = open_gate_escalation(root) if verdict == "PASS" else None
    if escalation is not None:
        finish("BLOCK", f"gate escalation {escalation[0]} open ({escalation[1]}): the audit found no failing check, "
               "but a PASS is not accepted until the owner closes it (the answer «так» in tasks/blocked/, or their own terminal)", obj, gate_escalation=escalation[0])
        return None
    finish(verdict, str(obj["reason"]), obj, check)
    return None


# ------------------------------------------------------------------ parking (called by overseer_stop.py)


def park(root: Path, item: str, blocked_on: str, evidence: str) -> str:
    """The unit is put before the owner. Where the project has a task board the item is a question
    in tasks/blocked/ (board 037: everything open lives on the board) and its path is returned;
    without a board it is one more entry of the log .engine/overseer/parked.md, which is history."""
    asked = board_item(root, item, blocked_on, evidence)
    if asked:
        return asked
    entry = (f"## {utc_now()} — {item} — PARKED\n- Blocked on: {one_line(blocked_on)}\n- Class: human-input\n"
             f"- Evidence: {one_line(evidence)}\n- Unblocks when: the owner answers, or the audit is repeated and passes\n")
    try:
        return journal.add(root, "parked", entry).relative_to(root).as_posix()   # this session's file of the log (board 739)
    except OSError:
        return PARKED_REL.as_posix()


def board_item(root: Path, item: str, blocked_on: str, evidence: str) -> str | None:
    """The parked unit as a question in tasks/blocked/ (board.py open_item), or None: no board in
    this project, or it could not be written. Best effort: a problem here changes no verdict."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        task = board.open_item(
            board.Board(root / "tasks"), "blocked", f"Overseer відклав юніт: {item}",
            f"Юніт `{item}` відкладено до рішення власника: {one_line(blocked_on)}. Докази: `{one_line(evidence)}`; вердикти — у ledger: `python3 .claude/hooks/journal.py show ledger`.",
            "Що робити з цим юнітом далі? Будь-яка відповідь — вказівка агентові (наприклад: повторити audit, прийняти як є, переробити).",
            key=item, source="hook overseer-а (overseer_stop.py)")
        return task.relative_to(root).as_posix() if task else None
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def runner_alive(root: Path) -> bool:
    """The board runner (board-runner.sh) is working here: its lock names a live process."""
    try:
        os.kill(int((root / BOARD_STATE_REL / "lock").read_text(encoding="utf-8").strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def three_blocks_marker(root: Path, task: str) -> Path:
    """What the Stop hook leaves for the runner after the third BLOCK (board 031): the runner, not
    the builder, moves the task to tasks/blocked/ (`board.py park <task> three-blocks`)."""
    return root / BOARD_STATE_REL / f"three-blocks-{task}.json"


# ------------------------------------------------------------------ command line


def read_envelope() -> JsonObj:
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def manual_request(root: Path, turn_file: Path, unit: str) -> int:
    if not wired(root):
        print("overseer_verdict.py is not wired in .claude/settings.json, so nothing would record the agent's verdict. "
              "Run `engine.py update <this project>` first: it adds the two handlers (guard, record). Do not "
              "audit the turn yourself.", file=sys.stderr)
        return 3
    waiting = pending(root)
    if waiting is not None and (verdict_for(root, str(waiting["id"])) or {}).get("verdict") in (None, INVALID):
        print(f"a request is already waiting for its verdict — launch the agent `{AGENT}` with exactly this prompt:\n"
              f"{launch_line(str(waiting['id']))}", file=sys.stderr)
        return 1
    if not turn_file.is_absolute() and not turn_file.exists():
        turn_file = root / turn_file
    try:
        turn = turn_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read the turn: {exc}", file=sys.stderr)
        return 2
    if not turn.strip():
        print(f"{turn_file} is empty — there is no turn to audit", file=sys.stderr)
        return 2
    allows = ""
    try:
        import gate_allows

        allows = gate_allows.render(gate_allows.collect(root))
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        allows = f"the gate-allow collector failed ({type(exc).__name__}); read the diff for `gate-allow:` markers"
    escalation = open_gate_escalation(root)
    request = make_request(root, turn, origin="manual", unit=unit, gate_allows_text=allows,
                           gate_escalation=f"{escalation[0]}: {escalation[1]}" if escalation else "")
    print(f"request {request['id']} written to {(REQUESTS_REL / request['id']).as_posix()}/\n"
          f"Now launch the agent `{AGENT}` with exactly this prompt and nothing else:\n{launch_line(request['id'])}")
    return 0


def status(root: Path) -> int:
    waiting = pending(root)
    print(f"wired in settings: {'yes' if wired(root) else 'NO — nothing is audited until `engine.py update` adds the two handlers'}")
    # A request stays in pending.json until the Stop hook has handed its verdict over, so "pending"
    # alone would call an answered request unanswered (seen live: a PASS reported as still pending).
    answered = verdict_for(root, str(waiting["id"])) if waiting else None
    if waiting and answered is not None and answered.get("verdict") != INVALID:
        print("pending request:   none")
        print(f"answered request:  {waiting['id']} — {answered.get('verdict')} recorded; "
              "the Stop hook hands it over when the turn ends")
    else:
        print(f"pending request:   {waiting['id'] if waiting else 'none'}"
              + (f" (asked {waiting.get('asks')}, launched {waiting.get('launched')})" if waiting else ""))
    for row in rows(root)[-5:]:
        print(f"  {row.get('utc')}  {row.get('verdict'):12} {row.get('request')}  {one_line(row.get('reason', ''), 90)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The overseer's request, guard and verdict writer.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("guard")
    commands.add_parser("record")
    commands.add_parser("status")
    manual = commands.add_parser("request")
    manual.add_argument("--turn-file", type=Path, required=True, help="the file holding the turn to audit, verbatim")
    manual.add_argument("--unit", default="1")
    args = parser.parse_args(argv)
    root = project_root()
    if args.command == "request":
        return manual_request(root, args.turn_file, str(args.unit))
    if args.command == "status":
        return status(root)
    try:
        output = guard(root, read_envelope()) if args.command == "guard" else record(root, read_envelope())
    except Exception as exc:  # noqa: BLE001 — gate-allow: a hook must never break a turn; it reports and decides nothing
        print(f"overseer_verdict {args.command}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    if output:
        json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
