#!/usr/bin/env python3
"""What the board runner remembers about each task, in .claude/state/board/costs.json.

board-runner.sh is a shell loop; everything it must remember across attempts — and across its
own restarts — is kept here, per task: when the task was started (set once, so the twelve-hour
limit is the task's and not the process's), the conversation to continue, how many attempts in
a row made no commit, and what every attempt reported as its cost.

    board_state.py <state-dir> begin  <task>                 make the entry (keeps an existing one)
    board_state.py <state-dir> retry  <task>                 a fresh clock and a fresh count
    board_state.py <state-dir> record <task> <output> <0|1>  book one attempt; 1 = it made a commit.
                                                             prints `limit` when the session only
                                                             answered with a usage-limit notice,
                                                             `auth` when it only said that claude
                                                             is logged out
    board_state.py <state-dir> rebudget <task>               what is spent so far no longer counts
                                                             against the cap (the owner answered a
                                                             task parked for its budget)
    board_state.py <state-dir> get    <task> <field> [cap]   age_sec | session | idle | cost | attempts
                                                             | left (cap minus what was spent since
                                                             the last rebudget, two decimals)
    board_state.py <state-dir> finish <task> <outcome>       done | blocked: close the entry
    board_state.py <state-dir> report                        one line per task, the total, and what every
                                                             UTC day cost: the day in progress and the seven
                                                             before it (BOARD_TODAY=YYYY-MM-DD names "today")

THE EXTRA SESSIONS (board 078). A session of Claude that a tool starts while a task is in hand — an
eval, a measurement — is ordinary work and needs no leave; so that one can see where the limit goes,
every such tool books it with `book_extra` into extra-sessions.jsonl beside costs.json: the time, the
task in doing/ (empty when the tool was started by hand), the tool, what the session reported it
cost. `report` adds the count and the sum to each task's line.

THE WEEKLY SUM (board 110, the owner's decision after 11 October). `extra_week` is what the extra
sessions of the last seven days cost: every booked session of a task, and the own sessions of the
tasks that carry the line «Додаткові сесії: так» (board.py, A TASK WITH EXTRA SESSIONS). A project
names its cap in `.claude/project.env`, EXTRA_SESSIONS_WEEK_USD; `extra_refusal` is what a tool
asks before it starts one more session for the task in hand. With no key there is no cap.

COST. `total_cost_usd` of a continued conversation is taken to be that conversation's running
total (premise PR-board-02: seen in the operator's log, not provable without a paid call), so a
task costs the sum, over its conversations, of the highest figure each one reported. Every
attempt's raw figure is stored next to its session id: the other reading can be recomputed.

THE DAYS (board 106, the owner's answer 5 to board 083: no limit, but show the pace). An attempt
cost what its conversation's running total grew by, and that is put on the UTC day of the attempt's
own `utc`; the days of every task add up to the tasks' costs. A day with nothing spent is shown as
0.00, not left out. An attempt with no time (a record older than the field) is not put on any day:
it is a line of its own. Nothing stops and nothing warns: BOARD_MAX_USD per task stays as it is.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

JsonObj = dict[str, Any]
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The same notice evals/run_audit_scenarios.py looks for. A session that hit the limit answers
# with a short notice and does nothing else; a long reply that merely talks about limits is work.
USAGE_LIMIT = re.compile(r"hit your (?:session|usage|weekly|daily|monthly|\w+) limit|usage limit (?:reached|exceeded)", re.IGNORECASE)
# What a logged-out claude answers instead of working (premise PR-board-07: the wording is taken
# from the CLI's messages, not from a live logged-out run). Not the task's fault and not an attempt.
LOGGED_OUT = re.compile(r"please run /login|invalid api key|not logged in|authentication_error|OAuth token (?:has expired|has been revoked|revoked)",
                        re.IGNORECASE)
NOTICE_MAX_CHARS = 400


def now() -> str:
    return datetime.now(UTC).strftime(STAMP)


def load(path: Path) -> JsonObj:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tasks": {}}
    return data if isinstance(data, dict) and isinstance(data.get("tasks"), dict) else {"tasks": {}}


def save(path: Path, data: JsonObj) -> None:
    data["total_cost_usd"] = round(sum(float(t.get("cost_usd", 0.0)) for t in data["tasks"].values()), 4)
    data["updated_utc"] = now()
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


def entry(data: JsonObj, task: str) -> JsonObj:
    found: JsonObj = data["tasks"].setdefault(task, {})
    found.setdefault("started_utc", now())
    found.setdefault("session_id", "")
    found.setdefault("attempts_without_commit", 0)
    found.setdefault("cost_usd", 0.0)
    found.setdefault("attempts", [])
    return found


def read_output(path: Path) -> tuple[JsonObj | None, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, ""
    try:
        payload = json.loads(text)
    except ValueError:
        return None, text
    return (payload if isinstance(payload, dict) else None), text


def is_limit_notice(payload: JsonObj | None, text: str) -> bool:
    if payload is None:
        return bool(USAGE_LIMIT.search(text[:2000]))
    reply = str(payload.get("result") or "")
    return len(reply) <= NOTICE_MAX_CHARS and bool(USAGE_LIMIT.search(reply))


def is_logged_out(payload: JsonObj | None, text: str) -> bool:
    if payload is None:
        return bool(LOGGED_OUT.search(text[:2000]))
    reply = str(payload.get("result") or "")
    return bool(payload.get("is_error")) and len(reply) <= NOTICE_MAX_CHARS and bool(LOGGED_OUT.search(reply))


def cost_of(attempts: list[JsonObj]) -> float:
    highest: dict[str, float] = {}
    for index, attempt in enumerate(attempts):
        key = str(attempt.get("session_id") or f"(no session {index})")
        highest[key] = max(highest.get(key, 0.0), float(attempt.get("reported_usd", 0.0)))
    return round(sum(highest.values()), 4)


def record(found: JsonObj, output: Path, committed: bool) -> str:
    """Book one attempt. Returns `limit`, `auth` or "" — the first two are not the task's attempts."""
    payload, text = read_output(output)
    limit = is_limit_notice(payload, text)
    auth = not limit and is_logged_out(payload, text or read_output(output.with_name(output.name + ".err"))[1])
    reported = (payload or {}).get("total_cost_usd", 0.0)
    session = str((payload or {}).get("session_id") or "")
    found["attempts"].append({
        "utc": now(), "session_id": session, "committed": committed, "limit": limit, "auth": auth,
        "reported_usd": float(reported) if isinstance(reported, (int, float)) else 0.0,
        "output": output.name,
    })
    # No session id in the output (not JSON, or an error before a session existed): the next
    # attempt starts a fresh conversation rather than resuming one that may not exist.
    found["session_id"] = session
    found["cost_usd"] = cost_of(found["attempts"])
    if committed:
        found["attempts_without_commit"] = 0
    elif not limit and not auth:
        found["attempts_without_commit"] = int(found["attempts_without_commit"]) + 1
    return "limit" if limit else "auth" if auth else ""


def get(found: JsonObj, field: str, cap: str) -> str:
    if field == "age_sec":
        started = datetime.strptime(str(found["started_utc"]), STAMP).replace(tzinfo=UTC)
        return str(int((datetime.now(UTC) - started).total_seconds()))
    if field == "session":
        return str(found["session_id"])
    if field == "idle":
        return str(int(found["attempts_without_commit"]))
    if field == "cost":
        return f"{float(found['cost_usd']):.4f}"
    if field == "attempts":
        return str(len(found["attempts"]))
    if field == "left":
        return f"{max(0.0, float(cap) - (float(found['cost_usd']) - float(found.get('budget_from', 0.0)))):.2f}"
    raise SystemExit(f"board_state: unknown field {field!r}")


def stamped(text: object) -> datetime | None:
    try:
        return datetime.strptime(str(text), STAMP).replace(tzinfo=UTC)
    except ValueError:
        return None


def growth(found: object) -> list[tuple[datetime | None, float]]:
    """One task's attempts as (when, what the conversation's running total grew by); None — no time."""
    highest: dict[str, float] = {}
    grown: list[tuple[datetime | None, float]] = []
    attempts = found.get("attempts") if isinstance(found, dict) else None
    for index, attempt in enumerate(attempts if isinstance(attempts, list) else []):
        if not isinstance(attempt, dict):
            continue
        key = str(attempt.get("session_id") or f"(no session {index})")
        reported = attempt.get("reported_usd", 0.0)
        figure = float(reported) if isinstance(reported, (int, float)) else 0.0
        grown.append((stamped(attempt.get("utc")), max(0.0, figure - highest.get(key, 0.0))))
        highest[key] = max(highest.get(key, 0.0), figure)
    return grown


def spending(tasks: JsonObj) -> tuple[dict[str, float], float]:
    """(UTC day → what the attempts of that day cost, what attempts with no time cost) — THE DAYS."""
    days: dict[str, float] = {}
    untimed = 0.0
    for found in tasks.values():
        for when, grew in growth(found):
            if when is None:
                untimed += grew
            else:
                days[when.date().isoformat()] = days.get(when.date().isoformat(), 0.0) + grew
    return days, untimed


def daily(tasks: JsonObj, today: date, before: int = 7) -> list[str]:
    """The day in progress and the `before` days before it, newest first, each with what it cost;
    then what was spent earlier, later (a clock ahead) and with no time, when there is any (THE DAYS)."""
    days, untimed = spending(tasks)
    shown = [(today - timedelta(days=n)).isoformat() for n in range(before + 1)]
    lines = [f"доба {day} (UTC{', триває' if day == shown[0] else ''}): {days.get(day, 0.0):.2f} USD" for day in shown]
    earlier = sum(cost for day, cost in days.items() if day < shown[-1])
    later = sum(cost for day, cost in days.items() if day > shown[0])   # a clock that was ahead: said, not lost
    if earlier:
        lines.append(f"раніше за {shown[-1]}: {earlier:.2f} USD")
    if later:
        lines.append(f"пізніше за {shown[0]} (годинник ішов уперед?): {later:.2f} USD")
    if untimed:
        lines.append(f"без часу запису (старий запис), не приписано жодній добі: {untimed:.2f} USD")
    return lines


def today_utc() -> date:
    given = os.environ.get("BOARD_TODAY", "")
    return date.fromisoformat(given) if given else datetime.now(UTC).date()


EXTRA_FILE = "extra-sessions.jsonl"


def note_extra_session(state_dir: Path, task: str, tool: str, cost_usd: float) -> None:
    """Append one extra session to the books; written once, never rewritten."""
    state_dir.mkdir(parents=True, exist_ok=True)
    row = {"utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "task": task, "tool": tool,
           "cost_usd": round(float(cost_usd or 0.0), 4)}
    with (state_dir / EXTRA_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def book_extra(tasks_dir: Path, tool: str, cost_usd: float) -> None:
    """What every tool that starts a session of Claude calls after it: the session is booked to the
    task this session has in doing/ of `tasks_dir`, in that project's .claude/state/board/
    (BOARD_STATE_DIR names another directory). A board with no project's .claude/ beside it (a test
    fixture, a stray directory) is booked nowhere: no .claude/ is made for it. Best effort: a run
    never fails over its books."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import board

        tasks = Path(os.path.realpath(tasks_dir))
        named = os.environ.get("BOARD_STATE_DIR")
        if not named and not (tasks.parent / ".claude").is_dir():
            return
        state = Path(named or tasks.parent / ".claude" / "state" / "board")
        note_extra_session(state, board.in_hand(tasks), tool, cost_usd)
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        pass


def extra_rows(state_dir: Path) -> list[tuple[str, float, datetime | None]]:
    """The booked sessions: (task, what it cost, when); a broken line is stepped over."""
    rows: list[tuple[str, float, datetime | None]] = []
    try:
        lines = (state_dir / EXTRA_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
            rows.append((str(row.get("task") or ""), float(row.get("cost_usd") or 0.0), stamped(row.get("utc"))))
        except (ValueError, TypeError, AttributeError):
            continue
    return rows


def extra_sessions(state_dir: Path) -> dict[str, tuple[int, float]]:
    """task -> (how many extra sessions, what they cost); "" is the sessions started with no task."""
    found: dict[str, tuple[int, float]] = {}
    for task, cost, _ in extra_rows(state_dir):
        count, spent = found.get(task, (0, 0.0))
        found[task] = (count + 1, spent + cost)
    return found


EXTRA_DAYS = 7


def extra_week(state_dir: Path, marked: Callable[[str], bool], now: datetime | None = None) -> float:
    """THE WEEKLY SUM: the booked sessions of tasks in the last seven days (one started by hand, with
    no task, is the owner's own and is not counted), plus the own sessions of the tasks `marked` names."""
    since = (now or datetime.now(UTC)) - timedelta(days=EXTRA_DAYS)
    spent = sum(cost for task, cost, when in extra_rows(state_dir) if task and when is not None and when > since)
    for name, found in load(state_dir / "costs.json")["tasks"].items():
        if marked(name):
            spent += sum(grew for when, grew in growth(found) if when is not None and when > since)
    return round(spent, 4)


def extra_refusal(tasks_dir: Path) -> str | None:
    """Why a tool may NOT start one more session of Claude: this session has a task in doing/ of
    `tasks_dir` and THE WEEKLY SUM is at the project's cap. None — start it (no cap, under it, or a
    run by hand with no task)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import board

        tasks = Path(os.path.realpath(tasks_dir))
        return board.extra_refusal(tasks) if board.in_hand(tasks) else None
    except (ImportError, OSError):
        return None


def extra_words(count: int, spent: float) -> str:
    return f"додаткових сесій Claude: {count} ({spent:.2f} USD)"


def report(data: JsonObj, today: date | None = None, extra: dict[str, tuple[int, float]] | None = None) -> list[str]:
    extra = extra or {}
    lines = []
    for name, found in sorted(data["tasks"].items()):
        line = (f"{name}: {float(found.get('cost_usd', 0.0)):.2f} USD, {len(found.get('attempts', []))} attempt(s), "
                f"{found.get('outcome', 'in work')}")
        lines.append(line + (f", {extra_words(*extra[name])}" if name in extra else ""))
    for name in sorted(n for n in extra if n and n not in data["tasks"]):
        lines.append(f"{name}: {extra_words(*extra[name])} (сесія з власником)")
    if "" in extra:
        lines.append(f"без задачі (запуск руками): {extra_words(*extra[''])}")
    lines.append(f"total: {float(data.get('total_cost_usd', 0.0)):.2f} USD")
    return lines + daily(data["tasks"], today or today_utc())


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    path, command, rest = Path(argv[1]) / "costs.json", argv[2], argv[3:]
    data = load(path)
    if command == "report":
        save(path, data)
        print("\n".join(report(data, extra=extra_sessions(path.parent))))
        return 0
    if not rest:
        print(f"board_state: {command} needs a task", file=sys.stderr)
        return 2
    if command == "retry":
        old = data["tasks"].get(rest[0], {})
        data["tasks"][rest[0]] = {"cost_usd": old.get("cost_usd", 0.0), "attempts": old.get("attempts", []),
                                  "budget_from": old.get("budget_from", 0.0)}
    found = entry(data, rest[0])
    if command in ("begin", "retry"):
        pass
    elif command == "rebudget":
        found["budget_from"] = float(found["cost_usd"])
    elif command == "record" and len(rest) == 3:
        note = record(found, Path(rest[1]), rest[2] == "1")
        if note:
            print(note)
    elif command == "get" and len(rest) >= 2:
        print(get(found, rest[1], rest[2] if len(rest) > 2 else "0"))
        return 0
    elif command == "finish" and len(rest) == 2:
        found["outcome"], found["finished_utc"] = rest[1], now()
    else:
        print(f"board_state: cannot {command} {' '.join(rest)}", file=sys.stderr)
        return 2
    save(path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
