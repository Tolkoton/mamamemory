#!/usr/bin/env bash
# PostToolUse hook for Edit|Write|MultiEdit: a thin call to the one gate script, layer
# "post_write" (.claude/hooks/gate.py). It formats the file, lints it quickly, never blocks, and
# tells the model through additionalContext only when the formatter changed the file or the lint
# found something. Configuration: .claude/project.env (FORMAT_CMD, CODE_EXTENSIONS).
#
# No python3 on the machine: nothing is formatted, and the edit is never blocked.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠ format-on-edit: python3 not found — nothing formatted." >&2
  exit 0
fi

python3 "$HERE/gate.py" --layer post_write --hook || true
exit 0
