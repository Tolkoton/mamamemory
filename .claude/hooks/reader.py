#!/usr/bin/env python3
"""reader.py — the fresh reader of a record (board 099; the approved design is board 080, §2 and §6).

    python3 .claude/hooks/reader.py request <task> --record <path>   # the package, then the launch line
    python3 .claude/hooks/reader.py request <task> --report          # the same for the task's report: tasks/done/<task>/report.md
    python3 .claude/hooks/reader.py guard                            # PreToolUse hook (stdin: the envelope)
    python3 .claude/hooks/reader.py record                           # SubagentStop hook, matcher `reader`
    python3 .claude/hooks/reader.py status                           # the pending request and the last verdicts

WHO. The agent `reader` (.claude/agents/reader.md): a fresh context, blind to the author's
conversation, read-only, on the session's model — a role of verification (P5). It is started with
one line this script prints — `READER_REQUEST <id>` — and nothing else; `guard` refuses any other
start, and refuses the reader any agent of its own.

WHAT. Two kinds of record. A sketch's `.engine/sketches/<name>.md` (the mode ескіз): the reader
checks one thing — does the output written in the record prove its answer («так», «ні»,
«не з'ясовано»)? And the report of a task that changed no working code (board 100; the design,
§6): `tasks/done/<task>/report.md`, written while the task is still in doing/. The package then
names the task file, every document the task changed (its commits and the working tree — never the
board's own moves or the journals scripts write) with its content, and the task's commits; the
reader checks four things — every reference says what is ascribed to it, every item of «Що зробити»
has its answer, every question for the owner is a fork with options and advice, technical terms are
English where the owner reads. Its answer is one JSON object: {"verdict": "PASS"|"BLOCK",
"reason": "…", "evidence": ["…"]}. `record` writes it — never the author: the row into
.claude/state/reader/verdicts.jsonl, an entry into the journal .engine/reader/ledger.md. A record
— or, for a report, any document of its package — that changed while it was read gets no verdict
(INVALID). An answer that does not fit goes back to the agent once, then is INVALID.

BLOCK. The author fixes the record and asks again: a new request, read by another reader, which
has seen neither the first reading nor the fix. Three BLOCKs in a row on one record: the board
runner parks the task — `record` leaves .claude/state/board/reader-blocks-<task>.json, and the
runner moves the task to blocked/ (`board.py park <task> reader-blocks`). With the marker `record`
appends a PARK row: the count restarts there, so after the owner's answer the record gets three
readings again, as the park question promises (the overseer's PARK row does the same).

`mode.py check-close` asks `passed()` here: a sketch closes only with a PASS on the record as it is;
a task without working code only with a PASS on its report as it is, read together with every
document the task changed, each as it is now. `board.py review` reads the journal for the verdict
it shows the owner beside each such task.
Standard library only. Exit: 0 done, 1 refused, 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import journal  # the journals scripts write: never a document a task changed
import overseer_verdict as ov  # the protocol's helpers: one reader of a reply, one way to write state

JsonObj = dict[str, Any]
AGENT = "reader"
STATE_REL = Path(".claude/state/reader")
REQUESTS_REL = STATE_REL / "requests"
PENDING_REL = STATE_REL / "pending.json"
VERDICTS_REL = STATE_REL / "verdicts.jsonl"
LEDGER_REL = Path(".engine/reader/ledger.md")
LEDGER_HEAD = "# Журнал агента-читача\n\nВердикти свіжого читача записів; пише `reader.py record` із відповіді агента, найновіший унизу.\n"
QUESTION = "Чи доводить вивід, записаний у записі, його відповідь («так», «ні», «не з'ясовано»)?"
SKETCH = re.compile(r"^\.engine/sketches/[^/]+\.md$")
REPORT = re.compile(r"^tasks/done/([^/]+)/report\.md$")
DOCUMENT_QUESTIONS = [
    "Чи кожне посилання в документах (файл і рядок, commit, команда, число) каже те, що йому приписано?",
    "Чи кожен пункт «Що зробити» із задачі має відповідь у документах?",
    "Чи кожне питання до власника — справжня розвилка з варіантами й порадою?",
    "Чи технічні терміни англійською там, де читає власник?",
]
# The board's own moves and the journals scripts write: what a task changes there is not its document.
BOOKKEEPING = ("tasks/todo/", "tasks/doing/", "tasks/blocked/", "tasks/done/", "tasks/proposed/", "tasks/.", ".engine/reader/",
               journal.PIECES_REL.as_posix() + "/", *(kind.shared for kind in journal.JOURNALS.values()))
BLOCKS_TO_PARK = 3
EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 1, 2


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def launch_line(request_id: str) -> str:
    return f"READER_REQUEST {request_id}"


def pending(root: Path) -> JsonObj | None:
    waiting = ov.read_json(root / PENDING_REL)
    return waiting if waiting.get("id") else None


def rows(root: Path) -> list[JsonObj]:
    try:
        text = (root / VERDICTS_REL).read_text(encoding="utf-8")
    except OSError:
        return []
    found = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            found.append(row)
    return found


def blocks_in_a_row(root: Path, record_rel: str) -> int:
    count = 0
    for row in reversed([r for r in rows(root) if r.get("record") == record_rel and r.get("verdict") in ("PASS", "BLOCK", "PARK")]):
        if row["verdict"] != "BLOCK":
            break
        count += 1
    return count


def passed(root: Path, record_rel: str, documents: list[str] | None = None) -> bool:
    """A PASS of a reader on the record as it is now (its content when it was read is its content now).
    A report's PASS also read the documents of its package: each is still what was read, and every one
    of `documents` — what the task's commits changed — was in the package."""
    now = digest(root / record_rel)

    def stands(row: JsonObj) -> bool:
        read = row.get("files")
        files: JsonObj = read if isinstance(read, dict) else {}
        return (row.get("verdict") == "PASS" and row.get("record") == record_rel and row.get("record_sha256") == now
                and all(digest(root / rel) == sha for rel, sha in files.items()) and all(rel in files for rel in documents or []))

    return any(stands(row) for row in rows(root))


def documents(paths: list[str], record_rel: str = "") -> list[str]:
    """Of the paths a task changed, the documents a reader reads: not the report itself (it is the
    record), not the board's moves, not a journal a script writes."""
    return sorted({rel for rel in paths if rel != record_rel and not rel.startswith(BOOKKEEPING)})


def _task_changes(root: Path, task: str) -> tuple[list[str], list[JsonObj]]:
    """(every path the task changed — its commits and the working tree —, its commits as sha and subject)."""
    import mode  # here, not at the top: mode.py asks this module at closing

    commits = mode.task_commits(root, task) or []
    paths = [rel for commit in commits for rel in mode._changed(root, commit)]
    tree = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-z", "--no-renames", "-uall"], capture_output=True, check=False)
    paths += [entry[3:] for entry in tree.stdout.decode("utf-8", "surrogateescape").split("\0") if len(entry) > 3]
    said = [{"sha": commit[:10], "subject": (mode._lines(mode._git(root, "log", "-1", "--format=%s", commit)) or ["?"])[0]} for commit in commits]
    return paths, said


def _report_package(root: Path, task: str, record_rel: str) -> JsonObj | str:
    """What a report's reader gets beside the report, or why this is no report of the task."""
    named = REPORT.match(record_rel)
    task_file = next((rel for rel in (f"tasks/doing/{task}.md", f"tasks/done/{task}/task.md") if (root / rel).is_file()), None)
    if not named or named.group(1) != task or task_file is None:
        return f"{record_rel} is not the report of the task {task} (tasks/done/{task}/report.md, the task in doing/ or done/)"
    paths, commits = _task_changes(root, task)
    return {"kind": "document", "task_file": task_file, "commits": commits, "questions": DOCUMENT_QUESTIONS,
            "files": {rel: digest(root / rel) for rel in documents(paths, record_rel)}}


def marker(root: Path, task: str) -> Path:
    return root / ov.BOARD_STATE_REL / f"reader-blocks-{task}.json"


def request(root: Path, task: str, record_rel: str) -> tuple[int, str]:
    record_path = root / record_rel
    task = task.removesuffix(".md")
    package: JsonObj | str = {"kind": "sketch", "question": QUESTION}
    if not record_path.is_file() or not (SKETCH.match(record_rel) or REPORT.match(record_rel)):
        return EXIT_REFUSED, (f"REFUSED: {record_rel} is neither a sketch record (.engine/sketches/<name>.md) nor a task's report "
                              "(tasks/done/<task>/report.md) of this project")
    if REPORT.match(record_rel):
        package = _report_package(root, task, record_rel)
    if isinstance(package, str):
        return EXIT_REFUSED, f"REFUSED: {package}"
    request_id = ov.utc_now().replace("-", "").replace(":", "") + "-" + secrets.token_hex(3)
    payload = {"id": request_id, "task": task, "record": record_rel, "record_sha256": digest(record_path), **package,
               "attempt": blocks_in_a_row(root, record_rel) + 1, "utc": ov.utc_now()}
    ov.write_json(root / REQUESTS_REL / request_id / "request.json", payload)
    ov.write_json(root / PENDING_REL, {"id": request_id})
    return EXIT_OK, (f"Reader request {request_id}: {record_rel} (attempt {payload['attempt']}). Launch the agent `reader` "
                     f"(Agent tool, subagent_type `reader`, run_in_background false) with exactly this prompt and nothing else:\n"
                     f"{launch_line(request_id)}")


def guard(root: Path, envelope: JsonObj) -> JsonObj | None:
    tool = str(envelope.get("tool_name", ""))
    raw = envelope.get("tool_input")
    tool_input: JsonObj = raw if isinstance(raw, dict) else {}
    if envelope.get("agent_type") == AGENT:
        return ov.deny(f"The reader is one fresh pair of eyes: {tool} starting another agent is refused.") if tool in ov.AGENT_TOOLS else None
    if tool not in ov.AGENT_TOOLS or tool_input.get("subagent_type") != AGENT:
        return None
    waiting = pending(root)
    if waiting is None:
        return ov.deny("No reader request is pending, so the reader is not started. A request is made by "
                       "`python3 .claude/hooks/reader.py request <task> --record .engine/sketches/<name>.md` (a sketch's record) "
                       "or `… request <task> --report` (the report of a task that changed no working code).")
    line = launch_line(str(waiting["id"]))
    if str(tool_input.get("prompt", "")).strip() != line:
        return ov.deny(f"The reader is started with exactly this prompt and nothing else: `{line}`. It reads the request "
                       "package itself; anything added would be the author speaking to its reader.")
    return None


def schema_errors(obj: JsonObj) -> list[str]:
    errors = []
    if obj.get("verdict") not in ("PASS", "BLOCK"):
        errors.append("`verdict` is PASS or BLOCK")
    if not isinstance(obj.get("reason"), str) or len(obj["reason"].strip()) < 12:
        errors.append("`reason` is a sentence (at least 12 characters)")
    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(e, str) and e.strip() for e in evidence):
        errors.append("`evidence` is a non-empty list of strings: the lines of the record the verdict rests on")
    return errors


def ledger(root: Path, row: JsonObj) -> None:
    path = root / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else LEDGER_HEAD
    entry = (f"\n## {row['utc']} — {row.get('task') or '-'} — READER_{row['verdict']}\n- Record: {row.get('record')}\n"
             f"- Reason: {ov.one_line(row.get('reason', ''))}\n- Request: {row['request']} (attempt {row.get('attempt', 1)})\n")
    path.write_text(text.rstrip("\n") + "\n" + entry, encoding="utf-8")


def record(root: Path, envelope: JsonObj) -> JsonObj | None:
    if envelope.get("agent_type") != AGENT or envelope.get("hook_event_name") not in (None, "SubagentStop"):
        return None
    waiting = pending(root)
    if waiting is None:
        return None
    request_id = str(waiting["id"])
    if any(r.get("request") == request_id and r.get("verdict") != "INVALID" for r in rows(root)):
        return None   # this request already has its verdict
    asked = ov.read_json(root / REQUESTS_REL / request_id / "request.json")
    row: JsonObj = {"utc": ov.utc_now(), "request": request_id, "task": asked.get("task", "-"), "record": asked.get("record", ""),
                    "record_sha256": asked.get("record_sha256", ""), "attempt": asked.get("attempt", 1), "agent_id": envelope.get("agent_id", "")}
    files: JsonObj = asked["files"] if isinstance(asked.get("files"), dict) else {}
    if asked.get("kind") == "document":
        row["files"] = files

    def finish(verdict: str, reason: str) -> None:
        row.update({"verdict": verdict, "reason": ov.one_line(reason)})
        ledger(root, row)
        path = root / VERDICTS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        ov.write_json(root / PENDING_REL, {})

    obj, problem = ov.parse_reply(str(envelope.get("last_assistant_message") or ov._handed_back(envelope.get("agent_transcript_path"))))
    errors = [problem] if obj is None else schema_errors(obj)
    if errors:
        if not waiting.get("schema_errors"):
            ov.write_json(root / PENDING_REL, waiting | {"schema_errors": 1})
            return {"decision": "block", "reason": "VERDICT REFUSED — the answer does not fit:\n- " + "\n- ".join(errors)
                    + "\nAnswer again with ONE JSON object: verdict, reason, evidence. A second answer that does not fit is INVALID."}
        finish("INVALID", "the answer does not fit: " + "; ".join(errors))
        return None
    assert obj is not None
    if digest(root / str(row["record"])) != row["record_sha256"]:
        finish("INVALID", f"the record {row['record']} changed while it was read")
        return None
    moved = [rel for rel, sha in files.items() if digest(root / rel) != sha]
    if moved:
        finish("INVALID", f"{', '.join(moved[:5])} changed while the report {row['record']} was read")
        return None
    finish(str(obj["verdict"]), str(obj["reason"]))
    if obj["verdict"] == "BLOCK" and blocks_in_a_row(root, str(row["record"])) >= BLOCKS_TO_PARK and row["task"] not in ("", "-"):
        blocks = [r for r in rows(root) if r.get("record") == row["record"] and r.get("verdict") == "BLOCK"][-BLOCKS_TO_PARK:]
        ov.write_json(marker(root, str(row["task"])), {"task": row["task"], "record": row["record"], "utc": ov.utc_now(),
                                                       "blocks": [{"utc": b["utc"], "request": b["request"], "reason": b["reason"]} for b in blocks]})
        with (root / VERDICTS_REL).open("a", encoding="utf-8") as handle:   # the count restarts here: three readings after the answer
            handle.write(json.dumps({"utc": ov.utc_now(), "request": request_id, "task": row["task"], "record": row["record"],
                                     "verdict": "PARK", "reason": f"{BLOCKS_TO_PARK} BLOCKs in a row: the task waits for the owner"},
                                    ensure_ascii=False) + "\n")
    return None


def status(root: Path) -> int:
    waiting = pending(root)
    print(f"pending request:   {waiting['id'] if waiting else 'none'}")
    for row in rows(root)[-5:]:
        print(f"  {row.get('utc')}  {row.get('verdict'):<8} {row.get('request')}  {row.get('record')}  {ov.one_line(row.get('reason', ''), 90)}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    asking = commands.add_parser("request")
    asking.add_argument("task")
    which = asking.add_mutually_exclusive_group(required=True)
    which.add_argument("--record", help=".engine/sketches/<name>.md, or tasks/done/<task>/report.md")
    which.add_argument("--report", action="store_true", help="the task's report, tasks/done/<task>/report.md")
    commands.add_parser("guard")
    commands.add_parser("record")
    commands.add_parser("status")
    args = parser.parse_args(argv)
    root = ov.project_root()
    if args.command == "request":
        code, said = request(root, args.task, args.record or f"tasks/done/{args.task.removesuffix('.md')}/report.md")
        print(said, file=sys.stdout if code == EXIT_OK else sys.stderr)
        return code
    if args.command == "status":
        return status(root)
    envelope = ov.read_envelope()
    answer = guard(root, envelope) if args.command == "guard" else record(root, envelope)
    if answer is not None:
        print(json.dumps(answer, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
