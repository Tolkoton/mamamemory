#!/usr/bin/env python3
"""lesson_queue.py — event-driven self-learning: the queue, its collectors, the review, the stuck counter.

    python3 .claude/hooks/lesson_queue.py add --source agent --slice S "what was non-obvious"
    python3 .claude/hooks/lesson_queue.py collect          # scan the sources, add new candidates
    python3 .claude/hooks/lesson_queue.py list
    python3 .claude/hooks/lesson_queue.py review-request   # the triage request, or nothing
    python3 .claude/hooks/lesson_queue.py resolve ID --to memory|rule|engine|discard [--text T] [--cite C C] [--why W] [--recommend R]
    python3 .claude/hooks/lesson_queue.py ask ID           # (re)write the owner's question for a pending proposal
    python3 .claude/hooks/lesson_queue.py promote ID       # a proposal the OWNER approved -> .engine/rules.md
    python3 .claude/hooks/lesson_queue.py reject ID --why W   # the owner said no: the proposal is closed
    python3 .claude/hooks/lesson_queue.py session-start    # hook: a bounded digest, a cleanup proposal
    python3 .claude/hooks/lesson_queue.py cleanup-done
    python3 .claude/hooks/lesson_queue.py stuck            # hook (PostToolUse / PostToolUseFailure): the stuck counter

THE QUEUE. One line per candidate:
    - <date UTC> | <source> | <slice> | <essence> #<id>
Since board 739 a session adds its lines to its own file, `.engine/journal/lessons/<session>.md`, and
`.engine/lesson-queue.md` is what a fold gathered (journal.py): branches merge without a conflict. A
triaged candidate is not removed: its resolution is one more line, `- <date> | resolved:<where> |
<note> #<id>`, and the queue is the candidates without one. Two sessions that triaged one candidate
differently are a contradiction the script does not settle: `collect` puts it on the board for an agent,
whose decision is `settle <id> --keep <where>`.
source is one of gate, overseer, parked, escalation, agent, simplifier, analyst (what the business analyst
should have asked and the owner had to correct). A candidate is added once: the id is a
hash of source + the normalised essence, and every id ever seen is kept in machine state
(`.claude/state/lessons/seen.json`), so a candidate that was triaged and removed does not come back
when its source is scanned again. No model is involved in collecting.

THE COLLECTORS (`collect`, called by the Stop gate and the overseer hook): the blocking findings of
`.claude/state/gate/last-report.json`, the PARKED entries of `.engine/overseer/parked.md` and the
open items of the task board (the tasks that carry `Відкритий пункт:`, board 037), the
non-AUTONOMOUS entries of `.engine/overseer/escalations.md`; the overseer hook adds an
`OVERSEER_BLOCK:` verdict itself (`add_from_verdict`). The agent adds a line when it finds a
non-obvious cause (the rule is in the self-learning-orchestrator skill, not in the persistent context).

THE REVIEW. After an overseer verdict of PASS, `review_request()` is appended to the hook's
"continue" text when the queue is not empty: file each candidate with `resolve` — into the project
memory (`.engine/overseer/MEMORY.md`, which demands two ledger citations), a rule proposal
(`.engine/rule-proposals.md`), feedback for the engine (`.engine/engine-feedback.md`) or discard it.
A resolved candidate leaves the queue.

NEVER INTO THE PERSISTENT CONTEXT AUTOMATICALLY — A LESSON BECOMES A RULE ONLY ON THE OWNER'S WORD
(board 040). Nothing here writes CLAUDE.md or `.claude/`. A rule proposal is put to the owner as a
task in `tasks/blocked/` (board.py `rule_question`): the question «Зробити це правилом?», the exact
text of the rule, and the offer `Дія runner-а: promote-rule <sha256 of the id and that text>`.
The overseer may add a recommendation (`--recommend`); it decides nothing, and no ledger entry
opens the way. `promote` needs the owner's «так» under that very offer, refuses inside a Claude
Code session (the board runner takes the action, through owner_action.py, after it has checked
that the answer arrived from the owner), and refuses when the persistent context would pass 200
lines. The rule lands in `.engine/rules.md`, which CLAUDE.md imports. A project without a task
board has one way: the owner's own terminal, `promote ID --owner-approved`.

STUCK. The same failure three times in a row (the key is the failure's normalised fingerprint) makes
`stuck` answer with the stuck protocol as additionalContext; a success resets the counter. It never
blocks. The Stop gate and the post-write lint feed the same counter (`note_failure` / `note_success`).

Standard library only; Python 3.11+. Hooks never fail the session: every hook entry exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import journal  # every session's own file of the queue (board 739)

SOURCES = ("gate", "overseer", "parked", "escalation", "agent", "simplifier", "analyst")
MEMORY_REL = Path(".engine/overseer/MEMORY.md")
PROPOSALS_REL = Path(".engine/rule-proposals.md")
FEEDBACK_REL = Path(".engine/engine-feedback.md")
RULES_REL = Path(".engine/rules.md")
LEDGER_REL = Path(".engine/overseer/ledger.md")
STATE_REL = Path(".claude/state/lessons")
GATE_REPORT_REL = Path(".claude/state/gate/last-report.json")
CLEANUP_DAYS = 14
CLEANUP_ENTRIES = 30
DIGEST_LIMIT = 1200
ESSENCE_LIMIT = 200
STUCK_AT = 3
BUDGET = 200
QUEUE_HEADER = journal.JOURNALS["lessons"].head
AT_RE = re.compile(r"(?:(?<=\s)|^)@\S")
LINE_RE = re.compile(
    r"^- (?P<date>\d{4}-\d{2}-\d{2}) \| (?P<source>\w+) \| (?P<slice>[^|]*?) \| (?P<essence>.*) #(?P<id>[0-9a-f]{8})$"
)
RULE_ACTION = "promote-rule"
OWNER_YES = "так"
IN_SESSION = (
    "refused inside a Claude Code session (CLAUDECODE is set): a lesson becomes a rule on the owner's word, "
    "and the board runner acts on it, never an agent"
)
STUCK_TEXT = (
    "STUCK PROTOCOL: the same failure has now happened {n} times in a row ({what}). Stop retrying the "
    "same fix. Write down what you tried and what actually happens, re-read project memory "
    "(`.engine/overseer/MEMORY.md`), and change the hypothesis, not the wording of the attempt — see "
    ".claude/skills/self-learning-orchestrator/triggers/stuck-protocol.md. If the cause was not "
    "obvious, add it to the lesson queue: `python3 .claude/hooks/lesson_queue.py add --source agent "
    "--slice <slice> \"<cause>\"`. This message never blocks."
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def today() -> str:
    return utc_now().strftime("%Y-%m-%d")


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text.lower())).strip()


def item_id(source: str, essence: str) -> str:
    return hashlib.sha256(f"{source}|{normalise(essence)}".encode()).hexdigest()[:8]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ state


def state_file(root: Path, name: str) -> Path:
    return root / STATE_REL / name


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def seen_ids(root: Path) -> list[str]:
    ids = load_json(state_file(root, "seen.json")).get("ids", [])
    return [i for i in ids if isinstance(i, str)]


def remember(root: Path, ident: str) -> None:
    ids = seen_ids(root)
    if ident not in ids:
        ids.append(ident)
    write(state_file(root, "seen.json"), json.dumps({"ids": ids[-20000:]}) + "\n")


# ------------------------------------------------------------------ the queue


def entries(root: Path) -> list[dict[str, str]]:
    """The candidates waiting for triage, from every session's file, without the ones a resolution closes."""
    found: list[dict[str, str]] = []
    for line in journal.open_candidates(journal.lesson_lines(root)):
        match = LINE_RE.match(line)
        if match:
            found.append(match.groupdict())
    return found


def current_slice(root: Path) -> str:
    progress = read(root / ".engine" / "PROGRESS.md")
    for line in progress.splitlines():
        if re.search(r"IN PROGRESS", line, re.IGNORECASE):
            match = re.search(r"[Ss]lice\s+`?([\w.-]+)`?", line)
            if match:
                return match.group(1)
    slices = sorted((root / ".engine" / "slices").glob("*.md"), key=lambda p: p.stat().st_mtime)
    return slices[-1].stem if slices else "-"


def clean_essence(text: str) -> str:
    one = re.sub(r"\s+", " ", text.replace("|", "/").replace("#", "no.")).strip()
    return one[:ESSENCE_LIMIT]


def add(root: Path, source: str, slice_name: str, essence: str, queue: bool = True) -> str | None:
    """Append one candidate. Returns its id, or None when it is empty or already known.
    queue=False only marks it seen (the seeding pass)."""
    essence = clean_essence(essence)
    if source not in SOURCES or not essence:
        return None
    ident = item_id(source, essence)
    # Known: seen on this machine, or in the journal at all — queued or triaged by any session (board 739).
    if ident in seen_ids(root) or any(line.endswith(f"#{ident}") for line in journal.lesson_lines(root)):
        return None
    if not queue:
        remember(root, ident)
        return ident
    slice_name = re.sub(r"[|\s]+", "-", slice_name.strip()) or "-"
    journal.add(root, "lessons", f"- {today()} | {source} | {slice_name} | {essence} #{ident}")
    remember(root, ident)
    return ident


def collect_gate(root: Path, slice_name: str) -> int:
    report = load_json(root / GATE_REPORT_REL)
    if report.get("layer") != "stop" or report.get("result") not in ("block", "escalated"):
        return 0
    added = 0
    for finding in [f for f in report.get("findings", []) if f.get("severity") == "block"][:3]:
        where = f" {finding.get('file')}:{finding.get('line')}" if finding.get("line") else (
            f" {finding.get('file')}" if finding.get("file") else "")
        if add(root, "gate", slice_name, f"{finding.get('rule')}{where}: {finding.get('message', '')}"):
            added += 1
    return added


def blocks(text: str, header: re.Pattern[str]) -> list[tuple[re.Match[str], str]]:
    heads = list(header.finditer(text))
    return [(m, text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)])
            for i, m in enumerate(heads)]


def bullet(body: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}:\s*(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def collect_parked(root: Path, queue: bool = True) -> int:
    header = re.compile(r"^## (?P<ts>\S+) — (?P<item>.+?) — PARKED[ \t]*$", re.MULTILINE)
    text = journal.text(root, "parked")
    resumed = set(re.findall(r"^## \S+ — (.+?) — RESUMED[ \t]*$", text, re.MULTILINE))
    added = 0
    for match, body in blocks(text, header):
        if match["item"] in resumed:
            continue
        if add(root, "parked", match["item"], f"{match['item']}: {bullet(body, 'Blocked on') or 'parked'}", queue):
            added += 1
    # Board 037: where the project has a task board a parked item is a task with the line
    # `Відкритий пункт: <item>` — in blocked/, todo/ or proposed/ while it is open — and no entry in the log.
    for path in sorted(p for column in ("blocked", "todo", "proposed") for p in (root / "tasks" / column).glob("*.md")):
        head = read(path).split("\n## ", 1)[0]
        item = re.search(r"^Відкритий пункт:[ \t]*(\S.*?)[ \t]*$", head, re.MULTILINE)
        title = re.search(r"^# \d+ — (.+)$", head, re.MULTILINE)
        if item and add(root, "parked", item.group(1), f"{item.group(1)}: {title.group(1).strip() if title else 'parked'}", queue):
            added += 1
    return added


def collect_escalations(root: Path, slice_name: str, queue: bool = True) -> int:
    header = re.compile(r"^## (?P<ts>\S+) — (?P<kind>[A-Z_]+)(?: \([^)]*\))? — (?P<title>.+?)[ \t]*$", re.MULTILINE)
    added = 0
    for match, body in blocks(read(root / ".engine/overseer/escalations.md"), header):
        if match["kind"] == "AUTONOMOUS" or re.search(r"^- Status:\s*(CLOSED|RESUMED|RESOLVED)", body, re.MULTILINE):
            continue
        detail = bullet(body, "Decision") or bullet(body, "Why not escalated")
        if add(root, "escalation", slice_name, f"{match['kind']} {match['title']}" + (f": {detail}" if detail else ""), queue):
            added += 1
    return added


def collect(root: Path) -> int:
    """Scan every automatic source. No model, no network; safe to call on every Stop.

    The first call on a project (no seen-ids file yet) only SEEDS: what the sources already hold
    is history, not a lesson from an event, so it is marked seen without being queued. The queue
    holds what happens from then on."""
    slice_name = current_slice(root)
    first = not state_file(root, "seen.json").is_file()
    if first:
        collect_parked(root, queue=False)
        collect_escalations(root, slice_name, queue=False)
        remember(root, "seeded")
    raise_contradictions(root)
    return (collect_gate(root, slice_name) + collect_parked(root)
            + collect_escalations(root, slice_name))


def raise_contradictions(root: Path) -> list[str]:
    """A candidate two sessions triaged differently goes before an agent as a task of the board, once
    while it stays open: the script never chooses (board 739, the owner). The tasks' paths."""
    lines = journal.lesson_lines(root)
    found = journal.contradictions(lines)
    board = board_module() if found else None
    if board is None:
        return []
    raised: list[str] = []
    for ident, rows in found.items():
        candidate = next((ln for ln in lines if journal.CANDIDATE_RE.match(ln) and ln.endswith(f"#{ident}")), f"#{ident}")
        how = "; ".join(f"{r['date']} → {r['to']} ({r['note']})" for r in rows)
        path = board.open_item(
            board.Board(root / "tasks"), "proposed", f"Дві сесії по-різному розібрали кандидата уроку #{ident}",
            f"Кандидат: {candidate}. Розбори: {how}. Скрипт не вибирає між ними (задача 739).",
            do=("Вирішити — справа агента: зважити обидва розбори й лишити один. Наслідки іншого прибрати руками (запис у "
                "`.engine/overseer/MEMORY.md`, пропозицію правила в `.engine/rule-proposals.md` разом із питанням у `tasks/blocked/`, "
                f"запис у `.engine/engine-feedback.md`), а рішення записати: `python3 .claude/hooks/lesson_queue.py settle {ident} "
                "--keep <memory|rule|engine|discard> --why \"…\"`."),
            key=f"lesson-contradiction-{ident}", source="lesson_queue.py")
        if path:
            raised.append(path.relative_to(root).as_posix())
    return raised


VERDICT_BLOCK_RE = re.compile(r"^[ \t]*OVERSEER_BLOCK:\s*(?P<why>.+?)[ \t]*$", re.MULTILINE)


def add_from_verdict(root: Path, message: str) -> int:
    """An OVERSEER_BLOCK verdict on its own line becomes a candidate."""
    match = VERDICT_BLOCK_RE.search(message)
    if not match:
        return 0
    return 1 if add(root, "overseer", current_slice(root), f"BLOCK {match['why']}") else 0


# ------------------------------------------------------------------ the review


def pending_proposals(root: Path) -> list[str]:
    return re.findall(r"^## RP-(\w+) — \S+ — PROPOSED", read(root / PROPOSALS_REL), re.MULTILINE)


def review_request(root: Path, track: bool = False) -> str:
    """The triage request; with track=True (the overseer hook) it repeats only when the queue
    changed since it was last made, or on every third PASS, so an item the agent cannot triage does
    not cost tokens forever. A pending proposal asks for nothing here: it waits for the owner."""
    queue = entries(root)
    if not queue:
        return ""
    if track:
        key = sorted(e["id"] for e in queue)
        state = load_json(state_file(root, "review.json"))
        passes = int(state.get("passes", 0)) if isinstance(state.get("passes", 0), int) else 0
        if state.get("key") == key and passes < 2:
            write(state_file(root, "review.json"), json.dumps({"key": key, "passes": passes + 1}) + "\n")
            return ""
        write(state_file(root, "review.json"), json.dumps({"key": key, "passes": 0}) + "\n")
    return _request_text(queue, pending_proposals(root))


def _request_text(queue: list[dict[str, str]], proposals: list[str]) -> str:
    shown = "\n".join(f"  #{e['id']}  {e['date']}  [{e['source']}] {e['slice']}: {e['essence'][:110]}" for e in queue[:12])
    more = f"\n  … and {len(queue) - 12} more (`lesson_queue.py list`)" if len(queue) > 12 else ""
    return (
        f"LESSON_REVIEW_REQUESTED — {len(queue)} candidate(s) in the lesson queue (`lesson_queue.py list`). Triage them now, "
        "briefly, before the next unit (a candidate with no lasting value: discard it):\n"
        f"{shown}{more}\n"
        "For each: `python3 .claude/hooks/lesson_queue.py resolve <id> --to <where> ...` with where = "
        "memory (project memory; needs --text and two --cite ledger entries), rule (a proposal for a standing "
        "rule; needs --text and --why, and takes --recommend, the overseer's advice to the owner), engine "
        "(feedback for the engine's own repository; --text) or discard. A resolved candidate leaves the queue. "
        "A rule proposal becomes a question to the owner in tasks/blocked/ and a rule only on the owner's «так»; "
        "the overseer recommends, it does not decide. Never run `promote` and never edit CLAUDE.md for it."
        + (f"\nWaiting for the owner, nothing to do: {', '.join('RP-' + p for p in proposals)}." if proposals else "")
    )


def close(root: Path, ident: str, to: str, note: str) -> None:
    """The candidate leaves the queue: a resolution line in this session's file, never a removed line (board 739)."""
    journal.add(root, "lessons", f"- {today()} | resolved:{to} | {clean_essence(note) or to} #{ident}")


def settle(root: Path, ident: str, keep: str, why: str) -> tuple[bool, str]:
    """The agent's decision on a candidate two sessions triaged differently."""
    rows = journal.resolutions(journal.lesson_lines(root)).get(ident)
    if not rows:
        return False, f"#{ident} has no resolution to settle"
    if not why.strip():
        return False, "settle needs --why: the reason the kept triage stands"
    close(root, ident, journal.SETTLED + keep, why)
    return True, f"#{ident} settled: {keep}"


def append(path: Path, text: str, header: str = "") -> None:
    existing = read(path) or header
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write(path, existing + text)


def proposal_sha(ident: str, rule: str) -> str:
    """What the owner says «так» to: the proposal and the exact text of its rule."""
    return hashlib.sha256(f"RP-{ident}\n{rule.strip()}\n".encode()).hexdigest()


def proposal(root: Path, ident: str) -> tuple[re.Match[str], str] | None:
    """The header of RP-<ident> in the proposals file and its body."""
    text = read(root / PROPOSALS_REL)
    match = re.search(rf"^## RP-{re.escape(ident)} — (?P<date>\S+) — (?P<state>\w+)[ \t]*$", text, re.MULTILINE)
    return (match, text[match.end():].split("\n## ", 1)[0]) if match else None


def proposal_by_sha(root: Path, sha: str) -> str | None:
    """The id of the PROPOSED proposal whose id and rule text make this sha256."""
    for ident in pending_proposals(root):
        found = proposal(root, ident)
        if found and proposal_sha(ident, bullet(found[1], "Rule")) == sha:
            return ident
    return None


def board_module() -> Any:
    """board.py (the one reader of tasks/), or None where the engine was installed without it."""
    folder = Path(__file__).resolve().parent.parent / "unattended"
    if not (folder / "board.py").is_file():
        return None
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    import board

    return board


def ask_owner(root: Path, ident: str) -> tuple[bool, str]:
    """Put a PROPOSED proposal to the owner: a task in tasks/blocked/ with the exact rule and the offer."""
    found = proposal(root, ident)
    if not found:
        return False, f"no proposal RP-{ident} in {PROPOSALS_REL}"
    if found[0]["state"] != "PROPOSED":
        return False, f"RP-{ident} is already {found[0]['state']}"
    body, board = found[1], board_module()
    rule = bullet(body, "Rule")
    path = board.rule_question(board.Board(root / "tasks"), ident, rule, bullet(body, "Why"), bullet(body, "From"),
                               bullet(body, "Overseer recommends"), proposal_sha(ident, rule)) if board else None
    if path is None:
        return False, (f"this project has no task board (tasks/): the owner decides RP-{ident} in their own terminal, "
                       f"`python3 .claude/hooks/lesson_queue.py promote {ident} --owner-approved`")
    return True, f"RP-{ident} is asked of the owner: {path.relative_to(root).as_posix()}"


def owner_said_yes(root: Path, ident: str, rule: str) -> bool:
    """A task in tasks/blocked/ offers promote-rule for exactly this proposal and this text, and the
    owner's answer under it is «так». Where the answer came from is the runner's check, not this one."""
    board = board_module()
    if board is None:
        return False
    wanted = proposal_sha(ident, rule)
    for path in board.Board(root / "tasks").files("blocked"):
        task = board.read(path)
        if task.action == RULE_ACTION and task.action_arg == wanted and task.approves:
            return True
    return False


def resolve(root: Path, ident: str, to: str, text: str, cite: list[str], why: str, recommend: str = "") -> tuple[bool, str]:
    found = [e for e in entries(root) if e["id"] == ident]
    if not found:
        return False, f"no candidate #{ident} in the queue"
    entry = found[0]
    origin = f"lesson #{ident} ({entry['source']}, {entry['slice']}, {entry['date']})"
    if to == "memory":
        if not text or len(cite) < 2:
            return False, "memory needs --text and at least two --cite ledger entries (date + slice): the file's citation-or-prune rule"
        append(root / MEMORY_REL, f"\n## {today()} — {text.splitlines()[0][:90]}\n\n{text}\n\nCited: {'; '.join(cite)}. Origin: {origin}.\n")
    elif to == "rule":
        if text and AT_RE.search(text):
            return False, "a rule text may not contain an @path (CLAUDE.md would load it as an import)"
        if not text or not why:
            return False, "a rule proposal needs --text (the rule, imperative, one line) and --why"
        advice = f"- Overseer recommends: {' '.join(recommend.split())}\n" if recommend.strip() else ""
        append(root / PROPOSALS_REL, f"\n## RP-{ident} — {today()} — PROPOSED\n- Rule: {text.splitlines()[0]}\n- Why: {' '.join(why.split())}\n- From: {origin}\n{advice}"
               "- Status: PROPOSED (the owner decides: the question is in tasks/blocked/; only the owner's «так» lets `lesson_queue.py promote` through)\n",
               "# Rule proposals\n\nCandidates for the standing rules. Never loaded into the persistent context; "
               "the ones the owner approves are promoted into `.engine/rules.md`.\n")
        close(root, ident, to, text)
        return True, f"#{ident} -> rule proposal. " + ask_owner(root, ident)[1]
    elif to == "engine":
        if not text:
            return False, "engine feedback needs --text"
        append(root / FEEDBACK_REL, f"\n## {today()} — {text.splitlines()[0][:90]}\n\n{text}\n\nFrom: {origin}.\n",
               "# Feedback for the engine\n\nWhat the work learned that belongs in the engine's own repository.\n")
    elif to != "discard":
        return False, "--to must be memory, rule, engine or discard"
    close(root, ident, to, text)
    return True, f"#{ident} -> {to}"


def context_lines(root: Path) -> int:
    """Lines of CLAUDE.md and everything it imports (the persistent context), as the budget test counts."""
    imports = re.compile(r"(?:(?<=\s)|^)@([^\s`]+)", re.MULTILINE)
    fence = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
    span = re.compile(r"`[^`\n]*`")
    seen: list[Path] = []

    def walk(path: Path, hops: int) -> None:
        try:
            path = path.resolve()
        except RuntimeError:  # a symlink loop, up to Python 3.12: not a file, nothing to count
            return
        if path in seen or not path.is_file():
            return
        seen.append(path)
        if hops >= 4:
            return
        for token in imports.findall(span.sub("", fence.sub("", read(path)))):
            target = Path(token.rstrip(".,;:)")).expanduser()
            walk(target if target.is_absolute() else path.parent / target, hops + 1)

    walk(root / "CLAUDE.md", 0)
    return sum(len(read(p).splitlines()) for p in seen)


def promote(root: Path, ident: str, owner_flag: bool = False, in_session: bool = False) -> tuple[bool, str]:
    """A proposal becomes a rule. Only on the owner's word: «так» under the question in tasks/blocked/
    (the board runner then calls this, outside any session), or `--owner-approved` typed in the owner's
    own terminal. Inside a Claude Code session neither counts — an agent can write both."""
    found = proposal(root, ident)
    if not found:
        return False, f"no proposal RP-{ident} in {PROPOSALS_REL}"
    match, body = found
    if match["state"] != "PROPOSED":
        return False, f"RP-{ident} is already {match['state']}"
    rule = bullet(body, "Rule")
    if AT_RE.search(rule):
        return False, "the rule text contains an @path, which CLAUDE.md would load as an import"
    if not owner_flag and not owner_said_yes(root, ident, rule):
        return False, (f"the owner has not said «{OWNER_YES}» to RP-{ident}: no task in tasks/blocked/ offers "
                       f"`Дія runner-а: {RULE_ACTION} {proposal_sha(ident, rule)}` with that answer. A lesson becomes a rule "
                       f"only with the owner's consent (`lesson_queue.py ask {ident}` writes the question; the overseer's "
                       "opinion opens nothing)")
    if in_session:
        return False, f"promote: {IN_SESSION}"
    rules_path = root / RULES_REL
    before = read(rules_path) or "# Rules approved from lessons\n\nPromoted by `lesson_queue.py promote` on the owner's «так». Each line is a standing rule.\n\n"
    new_text = before.rstrip("\n") + f"\n- {rule} (RP-{ident}, {today()})\n"
    original = read(rules_path)
    write(rules_path, new_text)
    if context_lines(root) > BUDGET:
        if original:
            write(rules_path, original)
        else:
            rules_path.unlink()
        return False, f"promoting would take the persistent context past {BUDGET} lines — trim .engine/rules.md first"
    close_proposal(root, match, "APPROVED", "")
    return True, f"RP-{ident} promoted into {RULES_REL}"


def close_proposal(root: Path, match: re.Match[str], state: str, note: str) -> None:
    text = read(root / PROPOSALS_REL)
    header = match.group(0).replace("— PROPOSED", f"— {state}")
    write(root / PROPOSALS_REL, text.replace(match.group(0), header + (f"\n- Owner: {note}" if note else ""), 1))


def reject(root: Path, ident: str, why: str) -> tuple[bool, str]:
    """The owner said no: the proposal is closed and never becomes a rule."""
    found = proposal(root, ident)
    if not found:
        return False, f"no proposal RP-{ident} in {PROPOSALS_REL}"
    if found[0]["state"] != "PROPOSED":
        return False, f"RP-{ident} is already {found[0]['state']}"
    close_proposal(root, found[0], "REJECTED", " ".join(why.split()) or "declined")
    return True, f"RP-{ident} rejected"


# ------------------------------------------------------------------ session start


def last_cleanup(root: Path) -> datetime | None:
    stamp = load_json(state_file(root, "cleanup.json")).get("last_utc")
    try:
        return datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def mark_cleanup(root: Path) -> None:
    write(state_file(root, "cleanup.json"), json.dumps({"last_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")


def cleanup_due(root: Path) -> str:
    """The reason to propose the clean-up protocol, or "". The first call only starts the clock."""
    count = len(entries(root))
    if count > CLEANUP_ENTRIES:
        return f"{count} candidates in the queue (over {CLEANUP_ENTRIES})"
    last = last_cleanup(root)
    if last is None:
        mark_cleanup(root)
        return ""
    age = (utc_now() - last).days
    has_material = count or re.search(r"^## \d{4}-", read(root / MEMORY_REL), re.MULTILINE)
    if age > CLEANUP_DAYS and has_material:
        return f"{age} days since the last clean-up (over {CLEANUP_DAYS})"
    return ""


def digest(root: Path) -> str:
    lines: list[str] = []
    queue = entries(root)
    memory = [ln[3:].strip() for ln in read(root / MEMORY_REL).splitlines() if re.match(r"^## \d{4}-\d{2}-\d{2}", ln)]
    proposals = len(pending_proposals(root))
    if memory:
        lines.append("Project memory (.engine/overseer/MEMORY.md), latest: " + " · ".join(m[:70] for m in memory[-4:]))
    if queue:
        lines.append(f"Lesson queue: {len(queue)} candidate(s), oldest {queue[0]['date']} (`python3 .claude/hooks/lesson_queue.py list`).")
    if proposals:
        lines.append(f"{proposals} rule proposal(s) wait for the owner's answer in tasks/blocked/ (.engine/rule-proposals.md); nothing for an agent to do.")
    due = cleanup_due(root)
    if due:
        lines.append(
            f"MEMORY CLEAN-UP DUE ({due}): run the clean-up protocol — triage the whole queue, prune uncited or "
            "stale entries of .engine/overseer/MEMORY.md and .engine/rules.md (.claude/skills/self-learning-orchestrator/"
            "triggers/periodic-maintenance.md), then `python3 .claude/hooks/lesson_queue.py cleanup-done`."
        )
    if not lines:
        return ""
    text = "## lessons\n" + "\n".join(f"- {ln}" for ln in lines)
    return text if len(text) <= DIGEST_LIMIT else text[: DIGEST_LIMIT - 1] + "…"


# ------------------------------------------------------------------ stuck


# What changes from one run of the same failure to the next (board 035), most specific first: a
# scratch directory, a clock, an id, a duration, a count. Each is replaced by a fixed mark BEFORE
# anything is cut to length, so a longer path or a later hour cannot move the cut.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
VOLATILE = tuple((re.compile(pattern, re.IGNORECASE), mark) for pattern, mark in (
    (r"(?:/private)?(?:/var/folders|/var/tmp|/tmp|/dev/shm)/[^\s'\"`:;,)\]]*", "<tmp>"),   # a scratch path, whole
    (r"\b(?:tmp|pytest-of-|pytest-)[\w.-]{4,}", "<tmp>"),                                # mkdtemp / pytest names
    (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<id>"),       # a UUID
    (r"\b0x[0-9a-f]+\b", "<id>"),                                                        # an address
    (r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,64}\b", "<id>"),                   # a commit, a digest
    (r"\b\d{4}-\d\d-\d\d[t ]\d\d:\d\d(?::\d\d)?(?:[.,]\d+)?(?:z|[+-]\d\d:?\d\d)?", "<time>"),
    (r"\b\d{8}t\d{6}z?\b", "<time>"),
    (rf"\b(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+)?(?:{_MONTH}\s+\d{{1,2}}|\d{{1,2}}\s+{_MONTH})(?:,?\s+\d{{4}})?", "<time>"),
    (r"\b\d{4}-\d\d-\d\d\b", "<time>"),
    (r"\b\d{1,2}:\d\d(?::\d\d)?(?:[.,]\d+)?(?:\s?[ap]m\b)?", "<time>"),
    (r"\d+(?:[.,]\d+)?\s?(?:ms|µs|us|ns|s|sec|secs|seconds?|min|minutes?|h|hours?)\b", "<n>"),
    (r"\d+(?:[.,]\d+)*", "<n>"),
))


def stable(text: str) -> str:
    """The failure's text without what varies between two runs of the same failure."""
    for pattern, mark in VOLATILE:
        text = pattern.sub(mark, text)
    return re.sub(r"(?:<time>[\s,]*)+", "<time> ", re.sub(r"\s+", " ", text.lower())).strip()


def failure_key(text: str) -> str:
    return hashlib.sha256(stable(text)[:300].encode()).hexdigest()[:12]


def anomaly(root: Path, what: str, done: str) -> None:
    """The hook's entry in the board's anomaly journal (board 035). Best effort: no board, no entry."""
    try:
        board = board_module()
        if board is not None:
            board.note(root, "hook lesson_queue.py (лічильник «застряг»)", what, done)
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        pass


def note_failure(root: Path, text: str) -> str:
    """Count an identical failure in a row. Returns the stuck protocol text on the third one."""
    if not text.strip():
        return ""
    key = failure_key(text)
    state = load_json(state_file(root, "stuck.json"))
    previous = state.get("count", 0)
    count = (previous if isinstance(previous, int) else 0) + 1 if state.get("key") == key else 1
    if count >= STUCK_AT:
        write(state_file(root, "stuck.json"), json.dumps({"key": key, "count": 0}) + "\n")
        anomaly(root, f"та сама невдача {count} раз(и) поспіль: {clean_essence(stable(text))[:160]}",
                "агентові показано протокол «застряг» (змінити гіпотезу, а не повторювати спробу); лічильник скинуто, роботу продовжено")
        return STUCK_TEXT.format(n=count, what=clean_essence(text)[:90])
    write(state_file(root, "stuck.json"), json.dumps({"key": key, "count": count}) + "\n")
    return ""


def note_success(root: Path) -> None:
    if load_json(state_file(root, "stuck.json")).get("count"):
        write(state_file(root, "stuck.json"), json.dumps({"key": "", "count": 0}) + "\n")


def tool_failure_text(envelope: dict[str, Any]) -> str | None:
    """The failure's text for a PostToolUse / PostToolUseFailure envelope; None for a success."""
    event = str(envelope.get("hook_event_name", ""))
    response = envelope.get("tool_response")
    tool = str(envelope.get("tool_name", ""))
    detail = ""
    if isinstance(response, dict):
        detail = str(response.get("error") or response.get("stderr") or "")
        failed = bool(response.get("is_error")) or response.get("exit_code") not in (None, 0) or (
            bool(response.get("error")))
    else:
        detail = str(response or "")
        failed = False
    if event == "PostToolUseFailure":
        failed = True
        detail = detail or str(envelope.get("error", ""))
    if not failed:
        return None
    command = ""
    tool_input = envelope.get("tool_input")
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or tool_input.get("file_path") or "")
    return f"{tool} {stable(command)[:80]} :: {stable(detail)[:160]}"


def run_stuck(root: Path, envelope: dict[str, Any]) -> dict[str, Any]:
    failure = tool_failure_text(envelope)
    if failure is None:
        note_success(root)
        return {}
    protocol = note_failure(root, failure)
    if not protocol:
        return {}
    event = str(envelope.get("hook_event_name") or "PostToolUse")
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": protocol}}


# ------------------------------------------------------------------ command line


def project_root() -> Path:
    import subprocess

    given = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if given and Path(given).is_dir():
        return Path(given)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def read_envelope() -> dict[str, Any]:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("--source", default="agent", choices=SOURCES)
    p_add.add_argument("--slice", default="")
    p_add.add_argument("text", nargs="+")
    for name in ("collect", "list", "review-request", "session-start", "cleanup-done", "stuck"):
        sub.add_parser(name)
    p_res = sub.add_parser("resolve")
    p_res.add_argument("id")
    p_res.add_argument("--to", required=True, choices=("memory", "rule", "engine", "discard"))
    p_res.add_argument("--text", default="")
    p_res.add_argument("--cite", nargs="*", default=[])
    p_res.add_argument("--why", default="")
    p_res.add_argument("--recommend", default="", help="the overseer's recommendation to the owner; it decides nothing")
    p_set = sub.add_parser("settle", help="an agent's decision on a candidate two sessions triaged differently")
    p_set.add_argument("id")
    p_set.add_argument("--keep", required=True, choices=("memory", "rule", "engine", "discard"))
    p_set.add_argument("--why", default="")
    sub.add_parser("ask").add_argument("id")
    p_pro = sub.add_parser("promote")
    p_pro.add_argument("id")
    p_pro.add_argument("--owner-approved", action="store_true",
                       help="the owner's flag, for the owner's own terminal; inside a Claude Code session it does not count")
    p_rej = sub.add_parser("reject")
    p_rej.add_argument("id")
    p_rej.add_argument("--why", default="")
    args = parser.parse_args(argv)
    root = project_root()
    hook_commands = ("session-start", "stuck", "collect")
    try:
        if args.command == "add":
            ident = add(root, args.source, args.slice or current_slice(root), " ".join(args.text))
            print(f"#{ident} added" if ident else "not added (empty, or already known)")
        elif args.command == "collect":
            print(f"{collect(root)} new candidate(s)")
        elif args.command == "list":
            for e in entries(root):
                print(f"#{e['id']} {e['date']} [{e['source']}] {e['slice']}: {e['essence']}")
        elif args.command == "review-request":
            text = review_request(root)
            if text:
                print(text)
        elif args.command == "resolve":
            done, message = resolve(root, args.id.lstrip("#"), args.to, args.text, args.cite, args.why, args.recommend)
            print(message, file=sys.stdout if done else sys.stderr)
            return 0 if done else 1
        elif args.command == "settle":
            done, message = settle(root, args.id.lstrip("#"), args.keep, args.why)
            print(message, file=sys.stdout if done else sys.stderr)
            return 0 if done else 1
        elif args.command in ("ask", "promote", "reject"):
            ident = args.id.lstrip("#").removeprefix("RP-")
            if args.command == "ask":
                done, message = ask_owner(root, ident)
            elif args.command == "promote":
                done, message = promote(root, ident, args.owner_approved, bool(os.environ.get("CLAUDECODE")))
            else:
                done, message = reject(root, ident, args.why)
            print(message, file=sys.stdout if done else sys.stderr)
            return 0 if done else 1
        elif args.command == "session-start":
            text = digest(root)
            if text:
                print(text)
        elif args.command == "cleanup-done":
            mark_cleanup(root)
            print("clean-up recorded")
        elif args.command == "stuck":
            output = run_stuck(root, read_envelope())
            if output:
                print(json.dumps(output, ensure_ascii=False))
    except OSError as exc:
        print(f"lesson_queue: {exc}", file=sys.stderr)
        return 0 if args.command in hook_commands else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
