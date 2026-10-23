#!/usr/bin/env bash
# Print the facts about THIS environment that the engine's policies decide on — and what
# the commit policy decides here. One `key=value` per line, nothing else, so the output can
# be pasted into a report or diffed between two environments.
#
#   bash .claude/unattended/env-probe.sh
#
# WHY. The commit policy depends on the environment (docs/plan/package-3b.md): attended
# machine, unattended run, cloud session. The cloud rule ships OFF because nobody has yet
# observed, from inside a real cloud session, which branch it checks out, what the remote
# is, whether CLAUDE_CODE_REMOTE is set the way the docs say, and which settings files are
# present. This probe is how that observation is made: the owner runs it there, pastes the
# output back, and the switch (CLOUD_COMMIT_POLICY in .claude/project.env) moves on
# evidence rather than on a guess.
#
# NEVER PRINTS A SECRET. Environment variables are reported by NAME; a value is printed
# only for the allow-listed, non-secret ones below (CLAUDE_CODE_REMOTE, the session id,
# the directories). Remote URLs have any user:token@ part masked. Keep it that way: the
# output is meant to be pasted into chats and reports.
#
# Read-only. Exit 0 always, so it can run anywhere, even where git or the hooks are absent.

SAFE_VALUE_VARS=(
  CLAUDE_CODE_REMOTE CLAUDE_CODE_REMOTE_SESSION_ID CLAUDE_PROJECT_DIR CLAUDE_CONFIG_DIR
  CLAUDE_UNATTENDED_SESSION HOME USER SHELL TERM_PROGRAM
)

out() { printf '%s=%s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }
mask_url() { sed -E 's#(://)[^@/]+@#\1***@#g'; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
PROJECT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

out probe_version 1
out utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
out hostname "$(hostname 2>/dev/null || echo unknown)"
out os "$(uname -s 2>/dev/null) $(uname -r 2>/dev/null)"
out user "$(id -un 2>/dev/null || echo unknown)"
out cwd "$(pwd)"
out probe_location "$HERE"

# --- what kind of session ---------------------------------------------------------------
# Whether anybody is watching is the reader's answer (.claude/hooks/mode.py, board 097), not this file's.
reader="$HERE/../hooks/mode.py"
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  out session_kind cloud
elif ! have python3 || [ ! -f "$reader" ]; then
  out session_kind "unknown (no python3 or no $reader to ask)"
else
  case "$(python3 "$reader" --root "$PROJECT" unattended 2>/dev/null)" in
    "unattended env") out session_kind unattended-supervised ;;
    "unattended mode-file") out session_kind unattended-mode-file ;;
    *) out session_kind attended-local ;;
  esac
fi
for v in "${SAFE_VALUE_VARS[@]}"; do
  if [ -n "${!v+x}" ]; then out "env.$v" "${!v}"; else out "env.$v" "<unset>"; fi
done
# Every CLAUDE_* / ANTHROPIC_* variable by NAME only — a value here could be a key.
names=$(env | sed -nE 's/^((CLAUDE|ANTHROPIC)[A-Z0-9_]*)=.*/\1/p' | sort | tr '\n' ' ')
out env_names_claude_anthropic "${names:-<none>}"
if [ -n "${ANTHROPIC_API_KEY+x}" ]; then out env.ANTHROPIC_API_KEY "<set, value withheld>"; else out env.ANTHROPIC_API_KEY "<unset>"; fi

# --- git ------------------------------------------------------------------------------
if have git && git -C "$PROJECT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  out git_toplevel "$(git -C "$PROJECT" rev-parse --show-toplevel 2>/dev/null)"
  out git_branch "$(git -C "$PROJECT" branch --show-current 2>/dev/null || echo '<detached>')"
  out git_head "$(git -C "$PROJECT" rev-parse --short HEAD 2>/dev/null || echo '<none>')"
  gitdir="$(git -C "$PROJECT" rev-parse --git-dir 2>/dev/null)"
  if [ -f "$PROJECT/.git" ]; then out git_checkout_kind worktree; elif [ -d "$PROJECT/.git" ]; then out git_checkout_kind main-checkout; else out git_checkout_kind "other ($gitdir)"; fi
  out git_remotes "$(git -C "$PROJECT" remote -v 2>/dev/null | awk '{print $1"="$2}' | sort -u | mask_url | tr '\n' ' ')"
  out git_upstream "$(git -C "$PROJECT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '<none>')"
  out git_user_name_set "$([ -n "$(git -C "$PROJECT" config user.name 2>/dev/null)" ] && echo yes || echo no)"
  out git_user_email_set "$([ -n "$(git -C "$PROJECT" config user.email 2>/dev/null)" ] && echo yes || echo no)"
  out git_status_dirty "$([ -n "$(git -C "$PROJECT" status --porcelain 2>/dev/null)" ] && echo yes || echo no)"
else
  out git_toplevel "<not a git work tree>"
fi

# --- settings files Claude Code would read here ----------------------------------------
out settings_user "$([ -f "$CONFIG_DIR/settings.json" ] && echo present || echo absent) ($CONFIG_DIR/settings.json)"
out settings_project "$([ -f "$PROJECT/.claude/settings.json" ] && echo present || echo absent)"
out settings_local "$([ -f "$PROJECT/.claude/settings.local.json" ] && echo present || echo absent)"
out hooks_dir "$([ -d "$PROJECT/.claude/hooks" ] && (cd "$PROJECT/.claude/hooks" && pwd -P) || echo '<absent>')"
out hooks_count "$(ls "$PROJECT/.claude/hooks" 2>/dev/null | wc -l | tr -d ' ')"
out mode_file "$(cat "$PROJECT/.claude/state/overseer/mode" 2>/dev/null || echo '<absent>')"
policy=$(sed -nE 's/^[[:space:]]*CLOUD_COMMIT_POLICY=["'"'"']?([A-Za-z-]*)["'"'"']?.*$/\1/p' "$PROJECT/.claude/project.env" 2>/dev/null | tail -1)
out cloud_commit_policy "${policy:-<unset: off>}"

# --- tools -------------------------------------------------------------------------------
for tool in git jq python3 uv claude; do
  if have "$tool"; then out "tool.$tool" "$("$tool" --version 2>&1 | head -1)"; else out "tool.$tool" "<not found>"; fi
done

# --- what the commit policy decides HERE -------------------------------------------------
hook="$PROJECT/.claude/hooks/block-dangerous.sh"
if [ -f "$hook" ]; then
  verdict=$(printf '{"tool_name":"Bash","tool_input":{"command":"git commit -m probe"}}' \
    | CLAUDE_PROJECT_DIR="$PROJECT" bash "$hook" 2>&1 >/dev/null); rc=$?
  if [ $rc -eq 0 ]; then out commit_policy_here "allow"; else out commit_policy_here "refuse (exit $rc): $(printf '%s' "$verdict" | head -1)"; fi
else
  out commit_policy_here "<no block-dangerous.sh in this project>"
fi
exit 0
