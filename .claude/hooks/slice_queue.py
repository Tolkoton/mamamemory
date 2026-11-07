#!/usr/bin/env python3
"""Which slice of the feature DAG can start now — the question a halt marker claims is answered "none".

Board 314. A builder halted with `OVERSEER_SLICE_AWAITING_OWNER: smoke and G4 are owner-driven` while the
next slice of the DAG could start (mamamemory, four times in a day): the Stop hook's own continue text told it
to. The hook now asks this module before it lets an AWAITING_OWNER / SLICE_COMPLETE halt end the turn.

Where the DAG is read from, in this order:
  1. `.engine/architecture/feature-dag.json` — `{"nodes": [{"id", "deps", "status"}]}`, the engine's own form;
  2. otherwise every feature artifact `.engine/architecture/feature/*.md`, its section «Slices (the DAG)» —
     `- **S2 slug** — … · depends on: S1, S3` (`/feature-architect`'s template) — with each slice's state taken
     from its card `## Slice … slug (STATUS …)` in `.engine/PROGRESS.md`; a slice without a card is not started.

A status is read by words, one rule for both sources (`state`): done / complete / superseded and a slice whose
code is complete with only its smoke or deploy waiting — `satisfied`: it lets the slices after it start;
parked / blocked — `stopped`; todo / pending / planned / ready / none — `not started`; anything else, «IN
PROGRESS» among it, — `active`. A slice can start when it is not started and every dependency is satisfied.

`python3 .claude/hooks/slice_queue.py` prints the slices that can start, one per line (exit 0 either way).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SATISFIED, STOPPED, NOT_STARTED, ACTIVE = "satisfied", "stopped", "not started", "active"

_SATISFIED_RE = re.compile(r"\b(?:done|complete|completed|superseded|closed)\b|\b(?:smoke|deploy)[-_ ](?:parked|pending)\b")
_STOPPED_RE = re.compile(r"\b(?:parked|blocked)\b")
_NOT_STARTED_RE = re.compile(r"^(?:|todo|to do|pending|planned|ready|not[-_ ]started|new)$")
_SLICE_LINE_RE = re.compile(r"^- \*\*(S\d+)\s+([^*\s]+)\*\*(.*)$", re.DOTALL)
_DEPENDS_RE = re.compile(r"depends on:\s*([^·\n]*)")
_RANGE_RE = re.compile(r"S(\d+)\s*[–-]\s*S?(\d+)")
_CARD_RE = re.compile(r"^## Slice\s+(.+?)\s*(?:\((.*)\))?\s*$", re.MULTILINE)


def state(status: str) -> str:
    """The state a status word (a DAG node's `status`, a PROGRESS card's parenthesis) stands for."""
    text = status.strip().lower()
    if _SATISFIED_RE.search(text):
        return SATISFIED
    if _STOPPED_RE.search(text):
        return STOPPED
    return NOT_STARTED if _NOT_STARTED_RE.match(text) else ACTIVE


def _dep_ids(text: str) -> list[str]:
    """`S1, S3` and `S1–S5` → the ids; `—` or nothing → none."""
    ids = [f"S{n}" for lo, hi in _RANGE_RE.findall(text) for n in range(int(lo), int(hi) + 1)]
    return ids + re.findall(r"S\d+", _RANGE_RE.sub("", text))


def _from_json(path: Path) -> list[tuple[str, list[str], str]]:
    nodes = json.loads(path.read_text(encoding="utf-8")).get("nodes", [])
    return [(str(n["id"]), [str(d) for d in n.get("deps", [])], state(str(n.get("status", ""))))
            for n in nodes if isinstance(n, dict) and "id" in n]


def _cards(progress: str) -> dict[str, str]:
    """slug → state, from the `## Slice …` headings of PROGRESS.md: `S3 — slug (STATUS)` or `slug — STATUS`
    (gate.active_slice's form); the last word before the status is the slug. A card with no status is active."""
    found: dict[str, str] = {}
    for title, status in _CARD_RE.findall(progress):
        parts = [part.strip() for part in title.split("—") if part.strip()]
        if not status and len(parts) > 1 and parts[-1].isupper():
            status = parts.pop()
        words = " ".join(parts).split()
        if words:
            found[words[-1]] = state(status) if status else ACTIVE
    return found


def _from_artifact(text: str, cards: dict[str, str]) -> list[tuple[str, list[str], str]]:
    section = text.partition("## Slices (the DAG)")[2].split("\n## ", 1)[0]
    bullets = re.split(r"\n(?=- )", section.replace("\n  ", " "))   # a bullet goes on over its indented lines
    slices = [m for m in (_SLICE_LINE_RE.match(bullet.strip()) for bullet in bullets) if m]
    slugs = {m.group(1): m.group(2) for m in slices}
    out = []
    for m in slices:
        depends = _DEPENDS_RE.search(m.group(3))
        deps = [slugs.get(d, d) for d in _dep_ids(depends.group(1) if depends else "")]
        out.append((m.group(2), deps, cards.get(m.group(2), NOT_STARTED)))
    return out


def nodes(project_dir: Path) -> list[tuple[str, list[str], str]]:
    """(id, dependency ids, state) of every slice of the DAG; [] when there is none or it cannot be read."""
    architecture = project_dir / ".engine" / "architecture"
    try:
        if (architecture / "feature-dag.json").is_file():
            return _from_json(architecture / "feature-dag.json")
        progress = project_dir / ".engine" / "PROGRESS.md"
        cards = _cards(progress.read_text(encoding="utf-8")) if progress.is_file() else {}
        return [node for artifact in sorted((architecture / "feature").glob("*.md"))
                for node in _from_artifact(artifact.read_text(encoding="utf-8"), cards)]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def startable(project_dir: Path) -> list[str]:
    """The slices that can start now: not started, every dependency satisfied."""
    found = nodes(project_dir)
    states = {node_id: node_state for node_id, _, node_state in found}
    return [node_id for node_id, deps, node_state in found
            if node_state == NOT_STARTED and all(states.get(dep) == SATISFIED for dep in deps)]


if __name__ == "__main__":
    print("\n".join(startable(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
