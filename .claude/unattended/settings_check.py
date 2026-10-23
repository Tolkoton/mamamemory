#!/usr/bin/env python3
"""The check of a settings proposal against the live settings — in any project (board 038).

    settings_check.py [--root DIR] [--applied]

An agent may not edit .claude/settings.json; it proposes the whole file in
docs/tasks/settings.json, and the owner's «так» has board-runner.sh copy it over the live one
(owner_action.py `apply-settings`). This is the check that travels with the engine: it reads
both files and says whether the proposal may become the live file, and whether it already is.

A proposal is refused when
- it is not a JSON object, or its `hooks` are not Claude Code's shape (an object of lists of
  groups, each with a list of handlers);
- a handler runs a script under .claude/ that the project does not have;
- the live file wires the overseer (`overseer_verdict.py guard` and `record`) and the proposal
  drops a handler: applied, no unit would be audited.

Then it names what differs (`hooks.Stop`, `permissions.allow` …) or says the live file is the
proposal. `--applied` also refuses a proposal that is not the live file yet.

owner_action.py runs this before the copy; a project that keeps a test of its own in
tests/test_settings_proposal.py (the engine's repository does) has that run after it.

Exit 0: the proposal is sound. 1: refused, each reason on its own line. 2: a file is missing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROPOSAL = "docs/tasks/settings.json"
LIVE = ".claude/settings.json"
OVERSEER_SCRIPT = "overseer_verdict.py"
SCRIPT = re.compile(r"\.claude/[\w./-]+\.(?:sh|py)\b")
EXIT_REFUSED, EXIT_MISSING = 1, 2


def handlers(settings: Any) -> list[tuple[str, str]]:
    """(event, command) of every command handler. Raises TypeError on a shape that is not Claude Code's."""
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("`hooks` is not an object")
    found: list[tuple[str, str]] = []
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise TypeError(f"`hooks.{event}` is not a list")
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                raise TypeError(f"a group of `hooks.{event}` has no list of handlers")
            for entry in entries:
                command = entry.get("command") if isinstance(entry, dict) else None
                if isinstance(command, str):
                    found.append((str(event), command))
    return found


def overseer_handlers(settings: Any) -> set[tuple[str, str]]:
    """(event, subcommand) of every handler that runs the verdict script; empty on an unreadable shape."""
    try:
        return {(event, command.split(OVERSEER_SCRIPT, 1)[1].strip(" \"'")) for event, command in handlers(settings) if OVERSEER_SCRIPT in command}
    except (TypeError, AttributeError):
        return set()


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def differences(live: Any, proposal: Any, prefix: str = "", depth: int = 2) -> list[str]:
    """The key paths, two levels deep, whose values differ."""
    if not (isinstance(live, dict) and isinstance(proposal, dict)) or depth == 0:
        return [] if live == proposal else [prefix.rstrip(".") or "the whole file"]
    out: list[str] = []
    for key in sorted(set(live) | set(proposal)):
        out += differences(live.get(key), proposal.get(key), f"{prefix}{key}.", depth - 1)
    return out


def defects(root: Path, proposal: Any, live: Any) -> list[str]:
    if not isinstance(proposal, dict):
        return [f"{PROPOSAL} is not a JSON object"]
    try:
        found = handlers(proposal)
    except TypeError as why:
        return [f"{PROPOSAL}: {why}"]
    out: list[str] = []
    for event, command in found:
        for script in sorted(set(SCRIPT.findall(command))):
            if not (root / script).is_file():
                out.append(f"{PROPOSAL}: a {event} handler runs {script}, which this project does not have")
    for event, sub in sorted(overseer_handlers(live) - overseer_handlers(proposal)):
        out.append(f"{PROPOSAL} drops the overseer's handler `{OVERSEER_SCRIPT} {sub}` ({event}) that {LIVE} has: no unit would be audited")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the settings proposal against the live settings.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--applied", action="store_true", help="also refuse a proposal that is not the live file yet")
    args = parser.parse_args()
    root = args.root.resolve()
    for rel in (PROPOSAL, LIVE):
        if not (root / rel).is_file():
            print(f"settings-check: {rel} is missing", file=sys.stderr)
            return EXIT_MISSING
    proposal, live = load(root / PROPOSAL), load(root / LIVE)
    found = defects(root, proposal, live)
    same = (root / PROPOSAL).read_bytes() == (root / LIVE).read_bytes()
    if same:
        print(f"settings-check: {LIVE} is the proposal; nothing to apply")
    else:
        print(f"settings-check: {PROPOSAL} differs from {LIVE} in: {', '.join(differences(live, proposal)) or 'formatting only'}")
        if args.applied:
            found.append(f"{PROPOSAL} is not applied: {LIVE} differs from it")
    for line in found:
        print(f"settings-check: REFUSED — {line}", file=sys.stderr)
    if found:
        return EXIT_REFUSED
    print(f"settings-check: {PROPOSAL} is sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
