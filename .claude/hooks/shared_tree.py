#!/usr/bin/env python3
"""Whose work does the Stop gate judge when a board runner works in the same tree? (board 305)

The owner may sit in a Claude Code session in the project's directory while the board runner
builds a task in that same working tree. The Stop gate judges the files a turn changed, and git
shows the runner's unfinished, red work as changed too: the owner's session was blocked on code
it never touched, and its third block in a row opened an escalation that held the runner's task.

The tree is SHARED when a live runner holds `.claude/state/board/lock` and this session is not
one the runner started (CLAUDE_UNATTENDED_SESSION is not 1 — the runner exports it). Then the
gate judges only the files this session's own tool calls wrote, read from its transcript (the
hook envelope's `transcript_path`) and from the transcripts of the subagents it launched:
  * the file of every Edit, Write, MultiEdit and NotebookEdit call;
  * every path a Bash command writes, read from its text (shell_readonly.written_paths).
Anything that cannot be read for certain gives None, and the gate judges the whole tree as it
always did: no transcript, a Bash write whose target the text does not show (a variable, a
formatter, a git command that changes files), a launched subagent with no transcript. A write
made by a script that a command only starts (`python3 gen.py`) is not seen at all: in a shared
tree such a write goes unjudged (docs/engine-limits.md). Code work beside a running runner
belongs in a separate clone (tasks/README.md); the SessionStart hook says so (env-check.sh).
Standard library only; best effort — any failure here reads as None.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

LOCK_REL = Path(".claude/state/board/lock")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
AGENT_TOOLS = {"Agent", "Task"}


def runner_pid(root: Path) -> int | None:
    """The PID of the live board runner of this tree; None with no lock or a dead holder."""
    try:
        pid = int((root / LOCK_REL).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except PermissionError:
        return pid
    except (OSError, OverflowError):
        return None
    return pid


def shared(root: Path, environ: dict[str, str] | None = None) -> bool:
    """A live runner works in this tree, and this session is not one it started."""
    environ = dict(os.environ) if environ is None else environ
    return environ.get("CLAUDE_UNATTENDED_SESSION") != "1" and runner_pid(root) is not None


def tool_uses(path: Path) -> list[tuple[str, dict[str, Any], str]]:
    """(tool, input, cwd) of every tool call in one transcript file."""
    uses: list[tuple[str, dict[str, Any], str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                uses.append((str(block.get("name", "")), block["input"], str(record.get("cwd") or "")))
    return uses


def relative(root: Path, path: str) -> str | None:
    """`path` as a path inside the project, or None when it lies outside."""
    full = Path(os.path.realpath(path if os.path.isabs(path) else root / path))
    try:
        return full.relative_to(root).as_posix()
    except ValueError:
        return None


def written(root: Path, uses: list[tuple[str, dict[str, Any], str]]) -> set[str] | None:
    """The project's files these tool calls wrote; None when one of them does not show it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import shell_readonly
    import shell_text

    files: set[str] = set()
    for tool, tool_input, cwd in uses:
        targets: set[str] | None = set()
        if tool in EDIT_TOOLS:
            target = tool_input.get("file_path") or tool_input.get("notebook_path")
            targets = {str(target)} if target else None
        elif tool == "Bash":
            command = shell_text.judged(str(tool_input.get("command", "")))
            targets = shell_readonly.written_paths(command, cwd or str(root), dict(os.environ), str(root))
        if targets is None:
            return None
        files.update(rel for rel in (relative(root, t) for t in targets) if rel)
    return files


def own_files(root: Path, transcript_path: str) -> set[str] | None:
    """The files this session wrote, its subagents included; None when that cannot be told."""
    if not transcript_path:
        return None
    try:
        main = Path(transcript_path)
        uses = tool_uses(main)
        agents = sorted((main.parent / main.stem / "subagents").glob("agent-*.jsonl"))
        if sum(tool in AGENT_TOOLS for tool, _, _ in uses) > len(agents):
            return None
        for agent in agents:
            uses.extend(tool_uses(agent))
        return written(root.resolve(), uses)
    except (ImportError, OSError, ValueError, TypeError, AttributeError, RecursionError):
        return None


def judged_files(root: Path, envelope: dict[str, Any], environ: dict[str, str] | None = None) -> set[str] | None:
    """What the Stop gate may judge: this session's own files in a shared tree; None — everything."""
    if not shared(root, environ):
        return None
    return own_files(root, str(envelope.get("transcript_path") or ""))
