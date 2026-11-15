#!/usr/bin/env python3
"""A live session that hit the subscription's limit goes on by itself once the limit resets (board 604).

    python3 .claude/unattended/session_watchdog.py --watch proj-remote=~/projects/proj
    python3 .claude/unattended/session_watchdog.py --watch a=/p/a --watch b=/p/b --dry-run

Run from the operator's cron every few minutes (docs/session-watchdog.md). For each `--watch
TMUX=PROJECT` it reads the newest interactive transcript of PROJECT under ~/.claude/projects/ and,
when the last message of the conversation is the CLI's «You've hit your session limit · resets …»,
sends `Продовжуй` into the tmux session TMUX once the reset time plus a margin (3 minutes) has
passed — one `tmux send-keys` per reset, never twice for the same one.

WHY. In mamamemory the live tmux session stood still after the limit four times, about 25 hours,
12.7 of them after the limit had already reset (~/engine-ops/mamamemory-stuck-analysis.md, B2):
Claude Code does not continue by itself, and the board runner, which waits out a limit on its own,
did not run there. The interactive session had nothing.

It does nothing when:
- the conversation went on after the limit (a later message: the owner wrote, a notification
  came, the session is working again) — the limit is no longer the last word;
- the reset time (plus the margin) has not come yet;
- this reset was already answered (the state file remembers the reset per tmux session);
- the reset is older than --max-age-hours (default 24): an old stuck conversation found on the
  first run is not woken up days later;
- the tmux session does not exist.
The reset time is the transcript's own `resetsAt` (epoch seconds); without it, the time in the
notice's text («resets 1:30am (UTC)»), the first such time after the notice.

- the pane runs `claude remote-control` — the conversation is driven from claude.ai, keys typed
  into the pane do not reach it (found on 2026-11-14: mamamemory-remote is such a bridge).
The newest transcript is taken as the live one: the entrypoint does not tell a live session from a
`claude -p` run (the remote-control child writes "sdk-cli" too), so in a project where the board
runner also works the newest may be the runner's (docs/session-watchdog.md, «Limits»). Exit 0 when every watch was read, 1 when a `tmux send-keys`
failed (the reset is then not marked, the next run tries again), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_state import USAGE_LIMIT  # the one definition of the limit notice

MESSAGE = "Продовжуй"
MARGIN_SECONDS = 180
TAIL_BYTES = 2_000_000  # a live transcript grows to tens of megabytes; the last messages are enough
RESET_TEXT = re.compile(
    r"resets\s+(?:(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<hour>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>am|pm)\s*(?:\((?P<tz>[^)]+)\))?",
    re.IGNORECASE)
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
Entry = dict[str, Any]


def transcripts_dir(project: Path) -> Path:
    """Claude Code keeps a project's transcripts under its path with every other character a dash."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project.resolve()))


def tail_entries(path: Path) -> list[Entry]:
    with path.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - TAIL_BYTES))
        raw = handle.read()
    lines = raw.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # the first line was cut in the middle
    entries = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def live_transcript(project: Path) -> tuple[Path, list[Entry]] | None:
    """The newest transcript of the project, with its last entries."""
    folder = transcripts_dir(project)
    candidates = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    return (candidates[-1], tail_entries(candidates[-1])) if candidates else None


def cmdline(pid: str) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def runs_remote_control(name: str) -> bool:
    """The pane runs `claude remote-control` (itself or as a child of its shell): its conversation
    comes from claude.ai, not from the pane's keyboard, so keys typed there never reach it."""
    shown = tmux("display-message", "-p", "-t", name, "#{pane_pid}")
    pid = shown.stdout.strip()
    if shown.returncode != 0 or not pid.isdigit():
        return False
    children: list[str] = []
    for task in Path(f"/proc/{pid}/task").glob("*/children"):
        try:
            children += task.read_text().split()
        except OSError:
            continue
    return any("remote-control" in cmdline(p) for p in (pid, *children))


def conversation(entries: list[Entry]) -> list[Entry]:
    return [e for e in entries if e.get("type") in ("user", "assistant") and not e.get("isSidechain")]


def text_of(entry: Entry) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def is_limit(entry: Entry) -> bool:
    if entry.get("type") != "assistant":
        return False
    if entry.get("apiError") == "usage_limit_reached":
        return True
    text = text_of(entry)
    return bool(entry.get("isApiErrorMessage")) and len(text) <= 400 and bool(USAGE_LIMIT.search(text))


def parse_stamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, AttributeError):
        return None


def reset_from_text(text: str, said: datetime) -> float | None:
    found = RESET_TEXT.search(text)
    if not found:
        return None
    try:
        zone = ZoneInfo(found["tz"].strip()) if found["tz"] else ZoneInfo("UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return None
    hour = int(found["hour"]) % 12 + (12 if found["ampm"].lower() == "pm" else 0)
    local = said.astimezone(zone)
    when = local.replace(hour=hour, minute=int(found["min"] or 0), second=0, microsecond=0)
    if found["mon"]:
        month = MONTHS.get(found["mon"].lower())
        if not month:
            return None
        when = when.replace(month=month, day=int(found["day"]))
        if when < local - timedelta(days=1):
            when = when.replace(year=when.year + 1)
    elif when <= local:
        when += timedelta(days=1)
    return when.timestamp()


def reset_of(entry: Entry) -> float | None:
    for holder in (entry.get("quotaLimits"), (entry.get("apiErrorParams") or {}).get("rate_limit_info")):
        if isinstance(holder, dict) and isinstance(holder.get("resetsAt"), (int, float)):
            return float(holder["resetsAt"])
    said = parse_stamp(str(entry.get("timestamp", "")))
    return reset_from_text(text_of(entry), said) if said else None


def load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


def tmux(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=False)


def decide(name: str, project: Path, now: float, state: dict[str, Any], max_age: float) -> tuple[str, float | None]:
    """What to do for one watch: ("send", reset) or (a reason to do nothing, None)."""
    found = live_transcript(project)
    if found is None:
        return f"no transcript in {transcripts_dir(project)}", None
    path, entries = found
    talk = conversation(entries)
    if not talk or not is_limit(talk[-1]):
        return f"working: the last message of {path.name} is not the limit notice", None
    reset = reset_of(talk[-1])
    if reset is None:
        return f"the limit notice in {path.name} names no reset time it can read", None
    if now < reset + MARGIN_SECONDS:
        return f"waiting: the limit resets at {stamp(reset)}, sends after {stamp(reset + MARGIN_SECONDS)}", None
    if now > reset + max_age:
        return f"too old: the limit reset at {stamp(reset)}, more than {max_age / 3600:g} h ago", None
    if state.get(name, {}).get("reset") == reset:
        return f"already sent for the reset at {stamp(reset)}", None
    if tmux("has-session", "-t", name).returncode != 0:
        return "no such tmux session", None
    if runs_remote_control(name):
        return "skipped: the pane runs `claude remote-control`; typed keys do not reach its conversation", None
    return "send", reset


def stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def default_state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "claude-engine" / "session-watchdog.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send «Продовжуй» into a live tmux session once its usage limit resets.")
    parser.add_argument("--watch", action="append", default=[], metavar="TMUX=PROJECT", help="a tmux session and the project it runs in")
    parser.add_argument("--state", type=Path, default=default_state_file(), help="which resets were answered")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now", type=float, default=None, help="epoch seconds (tests)")
    parser.add_argument("--dry-run", action="store_true", help="say what would be sent, send nothing")
    args = parser.parse_args(argv)
    if not args.watch or any("=" not in w or w.startswith("=") or w.endswith("=") for w in args.watch):
        parser.error("give at least one --watch TMUX=PROJECT")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now = time.time() if args.now is None else args.now
    state = load_state(args.state)
    failed = False
    for watch in args.watch:
        name, _, project = watch.partition("=")
        verdict, reset = decide(name, Path(project).expanduser(), now, state, args.max_age_hours * 3600)
        if verdict != "send" or reset is None:
            print(f"{name}: {verdict}")
            continue
        if args.dry_run:
            print(f"{name}: would send «{MESSAGE}» (the limit reset at {stamp(reset)})")
            continue
        sent = tmux("send-keys", "-t", name, MESSAGE, "Enter")
        if sent.returncode != 0:
            print(f"{name}: tmux send-keys failed: {sent.stderr.strip()}", file=sys.stderr)
            failed = True
            continue
        state[name] = {"reset": reset, "sent_utc": stamp(now)}
        save_state(args.state, state)
        print(f"{name}: sent «{MESSAGE}» (the limit reset at {stamp(reset)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
