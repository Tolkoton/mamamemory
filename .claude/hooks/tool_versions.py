#!/usr/bin/env python3
"""The exact versions of the outside tools whose answer decides a check of the engine (board 107).

On 2026-10-09 ruff 0.17.0 came out at 19:46 UTC; within the hour uvx, asked for ruff with no version
and so taking the latest release, turned tests/test_engine_lint.py red on the server with no change
to the code, while the cloud judged the same commit green with 0.16.8. A check whose verdict moves
with the release calendar is not a check. So every call of such a tool takes its version from VERSIONS below — the
one place they are written — and raising a version is a task of its own.

How a tool is found (`command`):
  1. a tool on PATH whose `--version` names the pinned version — no fetch, works offline;
  2. `uvx <tool>@<version>` — uv fetches exactly that release into its cache;
  3. neither: None and the reason. The check does not judge in silence with another version: the
     caller fails with that reason, or (a signal, a formatter) says it did not run.
A project that pins a tool itself keeps its own version: `project_tool` finds it in the project's
virtual environment, and gate.py runs `uv run` / `poetry run` where the lockfile names the tool and the
runner starts the project's own copy (board 108), and the project's LINT_CMD / TYPECHECK_CMD / FORMAT_CMD as written (docs/engine-limits.md).

pytest is pinned here only for the engine's own measurements (evals, the simplifier's sets): in a
project it runs the project's code and so belongs to the project's environment, never to uvx.

    python3 .claude/hooks/tool_versions.py              # every tool, its version, how it would run here
    python3 .claude/hooks/tool_versions.py ruff         # the argv prefix for one tool, or why not (exit 1)

Standard library only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSIONS: dict[str, str] = {
    "ruff": "0.17.0",
    "mypy": "2.4.0",
    "vulture": "2.16",
    "pylint": "4.1.2",
    "pytest": "9.1.1",
    "hypothesis": "6.168.5",
    "coverage": "7.16.2",
}

# The oldest Python the engine's own code must run under — what its hooks mean by «Python 3.11+». The one place
# it is written: the engine's lint hands it to ruff as --target-version and looks for that interpreter (board 751).
MIN_PYTHON = "3.11"

# Pinned like the rest, but no command of their own: they ride along with `uvx --with`.
LIBRARIES = {"hypothesis"}
VERSION_RE = re.compile(r"\d+(?:\.\d+)+")
VERSION_TIMEOUT_S = 30


def spec(tool: str) -> str:
    """`tool==version`, for `uvx --with` and `uvx --from`."""
    return f"{tool}=={VERSIONS[tool]}"


def installed_version(path: str) -> str:
    """The first version number `<path> --version` prints; empty when it prints none."""
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=VERSION_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    found = VERSION_RE.search(out.stdout + out.stderr)
    return found.group(0) if found else ""


def command(tool: str) -> tuple[list[str] | None, str]:
    """The argv prefix that runs `tool` at its pinned version, and "" — or None and why it cannot."""
    version = VERSIONS[tool]
    on_path = shutil.which(tool)
    found = installed_version(on_path) if on_path else ""
    if on_path and found == version:
        return [on_path], ""
    if shutil.which("uvx"):
        return ["uvx", "--quiet", f"{tool}@{version}"], ""
    if on_path:
        return None, (f"{tool} on PATH is {found or 'of a version it does not print'}, and the engine checks "
                      f"with {tool} {version} (.claude/hooks/tool_versions.py); install uv, whose uvx fetches "
                      f"exactly that release, or {tool} {version} itself")
    return None, (f"{tool} {version} cannot run here: neither uvx nor {tool} is on PATH; install uv "
                  "(uvx fetches the pinned release) or that version of the tool")


def project_tool(root: Path, tool: str) -> str | None:
    """The tool the project installed itself — in its virtual environment: the one activated
    (VIRTUAL_ENV) or `.venv/` / `venv/` in the project. Its version is the project's choice."""
    places = [Path(os.environ["VIRTUAL_ENV"])] if os.environ.get("VIRTUAL_ENV") else []
    places += [root / ".venv", root / "venv"]
    for place in places:
        candidate = place / "bin" / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def main(argv: list[str]) -> int:
    tools = argv or list(VERSIONS)
    unknown = [t for t in tools if t not in VERSIONS]
    if unknown:
        print(f"tool_versions: no pinned version for {', '.join(unknown)}", file=sys.stderr)
        return 2
    failed = 0
    for tool in tools:
        if tool in LIBRARIES:
            print(f"{tool} {VERSIONS[tool]}: a library, brought with `uvx --with {spec(tool)}`")
            continue
        prefix, why = command(tool)
        if prefix is None:
            failed = 1
        print(f"{tool} {VERSIONS[tool]}: {' '.join(prefix) if prefix else 'cannot run — ' + why}")
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
