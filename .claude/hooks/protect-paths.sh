#!/usr/bin/env bash
# PreToolUse hook for Edit|Write|MultiEdit (and NotebookEdit, where the settings wire it). The same paths are refused to a shell command by
# block-dangerous.sh; both read protected-path-list.sh.
# Defense-in-depth for paths that should never be written to from a Claude session.
# Emits JSON with permissionDecision: "deny" so Claude sees the reason.
set -euo pipefail

INPUT=$(cat)


# Read one string field from the hook envelope: jq when present, python3 otherwise.
# Exit status 0 = read (the value may be empty, and input that is not JSON reads as empty —
# pinned by tests ROBUST-*); 97 = no parser on this machine at all.
# WHY: the old idiom `jq ... 2>/dev/null || echo ""` turned "jq is not installed" into "the
# field is empty", and the hook then allowed everything. Measured with evals/: without jq
# every block of this hook became an allow. A deny control that
# cannot read its input must refuse, not wave the call through.
read_field() {
  if command -v jq >/dev/null 2>&1; then
    local expr="" path
    for path in "$@"; do expr="${expr:+$expr // }.${path}"; done
    printf '%s' "$INPUT" | jq -r "(${expr}) // \"\"" 2>/dev/null || true
  elif command -v python3 >/dev/null 2>&1; then
    printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    data = json.loads(sys.stdin.read())
except ValueError:
    sys.exit(0)
for path in sys.argv[1:]:
    node = data
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    if isinstance(node, str) and node:
        sys.stdout.write(node)
        break
' "$@"
  else
    return 97
  fi
}

if ! FILE_PATH=$(read_field tool_input.file_path tool_input.path tool_input.notebook_path 2>/dev/null); then
  echo "BLOCKED by protect-paths.sh: the tool call could not be read." >&2
  echo "Neither jq nor python3 parsed the hook input, so the target path cannot be checked." >&2
  echo "Install jq (or python3) and retry." >&2
  exit 2
fi

# The overseer agent is read-only (board 055): whatever the path, no editing tool works inside
# it. Until then this lived in overseer_verdict.py's guard, outside the perimeter.
if [ "$(read_field agent_type 2>/dev/null || true)" = "overseer" ]; then
  REASON="The overseer agent is read-only: an editing tool is refused, whatever the path (${FILE_PATH:-no path}). Judge what is there; a temporary copy under /tmp, made with a shell command, is the place to reproduce a RED. Enforced by .claude/hooks/protect-paths.sh."
  if ! command -v jq >/dev/null 2>&1; then
    echo "$REASON" >&2
    exit 2
  fi
  jq -n --arg reason "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
  exit 0
fi

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# The lists live in one file shared with block-dangerous.sh (board 714): ALLOWED_PATTERNS is the
# narrow allowlist checked BEFORE the deny patterns, PROTECTED_PATTERNS what is denied.
LIST="$(dirname "${BASH_SOURCE[0]}")/protected-path-list.sh"
if [ ! -f "$LIST" ]; then
  echo "BLOCKED by protect-paths.sh: the list of protected paths (protected-path-list.sh) is missing" >&2
  echo "beside the hook, so the target path cannot be checked. Restore it: python3 engine.py update." >&2
  exit 2
fi
# shellcheck source=/dev/null
. "$LIST"

for allowed in "${ALLOWED_PATTERNS[@]}"; do
  if echo "$FILE_PATH" | grep -qE "$allowed"; then
    exit 0
  fi
done

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if echo "$FILE_PATH" | grep -qE "$pattern"; then
    # Encode with jq, not a heredoc. Most patterns of the list contain a
    # backslash (\.env$, \.pem$, /\.ssh/, ...), and interpolating one raw into
    # a JSON string produces an invalid escape — the harness then cannot parse
    # the decision and the deny is silently lost. Verified 2026-08-27: a write
    # to .env emitted 406 bytes of malformed JSON and was NOT denied.
    if ! command -v jq >/dev/null 2>&1; then
      # No jq to encode the JSON decision. A PreToolUse hook may equally deny with exit
      # code 2 and the reason on stderr — no encoding, so nothing to get wrong.
      echo "Path $FILE_PATH matches protected pattern $pattern. This is enforced by .claude/hooks/protect-paths.sh as defense-in-depth. If you genuinely need to edit this file, ask the user to do it manually outside Claude Code, or rename/move the file if the protection is wrong for your project." >&2
      exit 2
    fi
    jq -n --arg path "$FILE_PATH" --arg pattern "$pattern" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:"Path \($path) matches protected pattern \($pattern). This is enforced by .claude/hooks/protect-paths.sh as defense-in-depth. If you genuinely need to edit this file, ask the user to do it manually outside Claude Code, or rename/move the file if the protection is wrong for your project."}}'
    exit 0
  fi
done

exit 0
