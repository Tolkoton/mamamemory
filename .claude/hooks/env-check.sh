#!/usr/bin/env bash
# SessionStart hook: say what this machine LACKS for the engine to enforce anything.
#
# Silent when nothing is missing (and, since package B, when the lesson digest is empty). SessionStart output is added to the context of every
# session, so a routine "all good" line would be paid for in every session forever; a
# missing tool, on the other hand, used to cost nothing up front and everything later —
# hooks that silently enforced nothing, or a lint gate that could only ever fail.
#
# Never blocks (a SessionStart hook cannot) and never fails: exit 0 always.

ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -n "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

have() { command -v "$1" >/dev/null 2>&1; }

MISSING=()

have git || MISSING+=("git — the hooks cannot read the branch or the diff: the commit policy falls back to blocking every commit, and verify-on-stop sees no changes and checks nothing.")

if ! have python3; then
  MISSING+=("python3 — overseer_stop.py, park-ask-gated.py and auto-approve-web.py cannot run: no audit is ever requested, and unattended runs hang on the first permission prompt.")
  have jq || MISSING+=("jq (and no python3 to fall back on) — block-dangerous.sh and protect-paths.sh will REFUSE every Bash and Edit call rather than let it through unchecked.")
fi

# Can the Stop gate run the tools the project itself configured? Mirrors the hook's own
# choice of runner: uv when uv.lock exists, poetry when poetry.lock exists, else bare tools.
if [ -f "$ROOT/pyproject.toml" ]; then
  RUNNER=""
  if [ -f "$ROOT/uv.lock" ]; then
    have uv && RUNNER="uv" || MISSING+=("uv — this project has uv.lock, so ruff, mypy and pytest are expected to come from \`uv run\`.")
  elif [ -f "$ROOT/poetry.lock" ]; then
    have poetry && RUNNER="poetry" || MISSING+=("poetry — this project has poetry.lock, so ruff, mypy and pytest are expected to come from \`poetry run\`.")
  fi
  if [ -z "$RUNNER" ] && [ ! -f "$ROOT/uv.lock" ] && [ ! -f "$ROOT/poetry.lock" ]; then
    for tool in ruff mypy; do
      if grep -q "\[tool\.${tool}" "$ROOT/pyproject.toml" 2>/dev/null && ! have "$tool"; then
        MISSING+=("${tool} — pyproject.toml configures it, there is no uv.lock or poetry.lock to run it through, and it is not on PATH: verify-on-stop will block every Python change with 'command not found'.")
      fi
    done
  fi
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "## engine environment check — missing on this machine"
  for line in "${MISSING[@]}"; do
    echo "- $line"
  done
  echo "Tell the user about the items above before relying on hook enforcement in this session."
fi

# Windows is supported through WSL2 only (the engine's docs/WINDOWS.md): inside it this is a
# Linux machine and nothing above differs. Two things still come from the Windows side, and
# neither is a missing tool. The kernel line is read from ENGINE_PROC_VERSION when set, so the
# suite can supply one; no file to read (macOS) means not WSL.
TRAPS=()
KERNEL=""
read -r KERNEL 2>/dev/null < "${ENGINE_PROC_VERSION:-/proc/version}" || true
case "$KERNEL" in *[Mm]icrosoft*)
  case "$ROOT/" in /mnt/[a-zA-Z]/*)
    TRAPS+=("the project is on a Windows disk ($ROOT) — from WSL every git command and test run there is many times slower, and file permissions are not kept: hooks lose their executable bit and git shows files as changed. Move it into the Linux home (for example ~/projects/) and open it from there.") ;;
  esac
  if have git; then
    case "$(cd "$ROOT" 2>/dev/null; git config --get core.autocrlf 2>/dev/null)" in true|True|TRUE|yes|on|1)
      TRAPS+=("git core.autocrlf is on — git rewrites line endings to CRLF on checkout, and a hook script with CRLF does not run ('bash\\r: No such file or directory'). Set \`git config --global core.autocrlf input\`, then check the project out again.") ;;
    esac
  fi ;;
esac

if [ "${#TRAPS[@]}" -gt 0 ]; then
  echo "## engine environment check — WSL"
  for line in "${TRAPS[@]}"; do
    echo "- $line"
  done
  echo "Tell the user about the items above: the engine's docs/WINDOWS.md has the steps."
fi

# Board 750 (owner): a cloud session starts from a shallow clone — no old commits, no tags — and every suite
# that reads git history then fails the Stop gate on each turn. In every cloud session (CLAUDE_CODE_REMOTE=true),
# the engine's repository and every installed project alike, the hook fetches the whole history and the tags,
# with no switch and nothing said when it works. A failed fetch leaves one line for the agent, not a question:
# the clone is still shallow, and the same command run again is the way on. A non-shallow clone is left alone.
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && have git \
   && [ "$(git -C "$ROOT" rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
  LIMIT=()
  have timeout && LIMIT=(timeout 50)   # under the hook's own time limit; an interrupted fetch leaves the clone as it was
  if ! "${LIMIT[@]}" git -C "$ROOT" fetch -q --unshallow --tags origin >/dev/null 2>&1; then
    echo "## engine environment check — git history"
    echo "- this cloud clone is shallow and \`git fetch --unshallow --tags origin\` failed: suites that read old commits or tags fail until it is run again and succeeds."
  fi
fi

# Package B: a bounded digest of the project's lessons (memory headings, the queue's size, the
# proposals waiting) and, when due, the proposal to run the clean-up protocol. Silent when there
# is nothing to say. Carried here because this is the SessionStart hook already wired; it needs
# python3 and says nothing without it.
if have python3 && [ -f "$ROOT/.claude/hooks/lesson_queue.py" ]; then
  CLAUDE_PROJECT_DIR="$ROOT" python3 "$ROOT/.claude/hooks/lesson_queue.py" session-start 2>/dev/null || true
fi

# Board 724: the snapshot of the guarded files (the constitution, the settings, .engine/rules.md,
# migrations, CI workflows) the Stop gate compares with at the end of every turn. The envelope on
# stdin names the session and why it starts; nothing above reads stdin. Taken at a start, a resume
# and a clear — not after a compaction, which is the middle of a turn. Silent.
GUARD="$(dirname "${BASH_SOURCE[0]}")/protected_guard.py"   # beside this hook, as the list it reads is
if have python3 && [ -f "$GUARD" ]; then
  python3 "$GUARD" --root "$ROOT" session-start 2>/dev/null || true
fi
exit 0
