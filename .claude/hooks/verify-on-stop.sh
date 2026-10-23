#!/usr/bin/env bash
# Stop hook: a thin call to the one gate script, layer "stop" (.claude/hooks/gate.py).
# Everything it used to do inline — find the changed files, read .claude/project.env, run lint,
# types and tests, block with the real error — lives in gate.py now, with a retry counter that
# ends in an escalation and a guard against passing the gate by silencing it.
# Does NOT commit (commits are a human checkpoint).
#
# No python3 on the machine: refuse. A Stop gate that cannot run must not read as "verified".
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "verify-on-stop: python3 is required to run the gate (.claude/hooks/gate.py) and is not installed — the turn is not verified." >&2
  exit 2
fi

exec python3 "$HERE/gate.py" --layer stop --hook
