#!/usr/bin/env python3
"""The sanctioned way for an agent to set the overseer's phase guard.

    python3 .claude/hooks/overseer_phase.py set plan     # planning: the Stop hook stands down
    python3 .claude/hooks/overseer_phase.py clear        # back to building: audits resume
    python3 .claude/hooks/overseer_phase.py show         # prints the phase, or "(none)"

WHY THIS EXISTS. `.claude/state/` is the state of hooks and scripts: Claude Code shows the
owner (or its classifier) every write an agent makes there with its own tools, and refuses a
direct `printf plan > .claude/state/overseer/state` as self-modification — correctly. The
planning commands (/plan-slice, /feature-architect) still need the overseer to stand down
while a contract is being drafted, or every drafting turn would be audited as a false DONE.
This script is the one path the engine rules name for that write: a named, reviewable
action with no other effect, read by `overseer_stop.py` (`_phase_is_plan`: the file contains
the word "plan"). The alternative — a UserPromptSubmit hook that sets the phase when the
prompt invokes a planning command — needs a `.claude/settings.json` change, which is the
owner's; it is recorded as the alternative in the package-2b escalations entry.

Exit 0 on success, 2 on a usage error. Standard library only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

STATE_REL = Path(".claude") / "state" / "overseer" / "state"


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


def state_file(root: Path) -> Path:
    return root / STATE_REL


def set_phase(root: Path, phase: str) -> Path:
    path = state_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(phase + "\n", encoding="utf-8")
    return path


def clear_phase(root: Path) -> Path:
    path = state_file(root)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return path


def show_phase(root: Path) -> str:
    try:
        return state_file(root).read_text(encoding="utf-8").strip() or "(empty)"
    except OSError:
        return "(none)"


def main(argv: list[str]) -> int:
    root = project_root()
    if len(argv) == 2 and argv[0] == "set" and argv[1] == "plan":
        path = set_phase(root, "plan")
        print(f"phase set to plan: {path} — the overseer Stop hook stands down until `clear`")
        return 0
    if argv == ["clear"]:
        path = clear_phase(root)
        print(f"phase cleared: {path} removed — audits resume")
        return 0
    if argv == ["show"]:
        print(show_phase(root))
        return 0
    print("usage: overseer_phase.py set plan | clear | show", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
