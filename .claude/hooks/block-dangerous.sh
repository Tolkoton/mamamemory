#!/usr/bin/env bash
# PreToolUse hook for Bash. Blocks destructive commands, git commit, a command that clears the
# owner's variable (CLAUDECODE), the dangerous forms of a
# push (forced, deleting a remote branch, into a protected branch), and a shell write to a
# protected path or a read of a secret one (the list: protected-path-list.sh).
# Exit 2 = block + show reason to Claude via stderr.
# Exit 0 = allow.
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

if ! CMD=$(read_field tool_input.command 2>/dev/null); then
  echo "BLOCKED by the engine safety hook (block-dangerous.sh): the tool call could not be read." >&2
  echo "Neither jq nor python3 parsed the hook input, so this command cannot be checked." >&2
  echo "Install jq (or python3) and retry. Until then Bash calls are refused on purpose:" >&2
  echo "an unchecked command is a breach, a refused one is a nuisance." >&2
  exit 2
fi

if [ -z "$CMD" ]; then
  exit 0
fi

# What is judged (board 738). Until then every check below read the raw command, quoted strings
# and heredoc bodies included, so a commit message, a file of test cases written with `cat`, a
# grep pattern or the text of a board item was refused for what it only MENTIONED. shell_text.py
# now empties such text first, and every check reads $JUDGED. The bias has not moved — a false
# positive is a nuisance, a false negative a breach: text is emptied only where a known command
# takes it and never runs it, only when it holds no substitution, and only when nothing in the
# whole command could run it (no shell, interpreter, script, substitution, group or keyword
# anywhere). `bash -c '…'`, `python3 - <<EOF`, `echo '…' | sh`, a heredoc written and then run
# in the same command are judged whole, as before. Without python3, or when the script fails,
# the raw command is judged. The refusal still shows the command as it was typed.
HOOK_DIR="$(dirname "${BASH_SOURCE[0]}")"
JUDGED="$CMD"
case "$CMD" in
  *\'*|*\"*|*'<<'*)
    if command -v python3 >/dev/null 2>&1 && [ -f "$HOOK_DIR/shell_text.py" ]; then
      JUDGED=$(printf '%s' "$CMD" | python3 "$HOOK_DIR/shell_text.py" 2>/dev/null) || JUDGED="$CMD"
      [ -n "$JUDGED" ] || JUDGED="$CMD"
    fi
    ;;
esac

# Command-position prefix used below is (^|[;&|(`])[[:space:]]* — start of the
# command OR just after a separator. A bare ^ let a compound command walk past
# the check, and a leading tab defeated both anchored forms.

# Truly destructive patterns. Order: most specific first.
# `-rf` and `-fr` are the same flags in either order, so every rm pattern accepts both:
# until package 3b the hook knew only `-rf` while the deny list refused `rm -fr <anything>`,
# and the two disagreed about which spelling was dangerous. The ROOT patterns are what let
# the deny list drop its `rm -rf /` + `*` rule — whose `*` matched any text, so a delete
# under /tmp was refused too — in favour of the exact root rule: here `/` followed by
# end-of-line or by a character that cannot start a path component (`*`, `;`, a space) is
# the root, and `/tmp/...` is not (tests/test_root_delete_deny.py).
DANGEROUS_PATTERNS=(
  'rm -(rf|fr) /[^a-zA-Z0-9_.]'
  'rm -(rf|fr) /$'
  'rm -(rf|fr) ~'
  'rm[[:space:]]+-[a-z]*[rf][a-z]*[[:space:]]+["'"'"']?\$\{?HOME\}?'
  'rm -(rf|fr) \*'
  'rm -(rf|fr) \.\s*$'
  'rm -(rf|fr) \./\*'
  'rm -(rf|fr) \$\('
  'rm -r \$\('
# NOTE: the git-commit pattern is deliberately NOT in this unconditional list.
# It lives in the branch-aware commit policy near the end of the file, because
# after 2026-08-27 a commit is legal on an unattended/<date> branch and illegal
# everywhere else. Putting it here would block it on every branch, including the
# one where it is now the point.
  'git push --force'
  'git push -f '
  'git push --force-with-lease'
  'git reset --hard origin'
  'git reset --hard HEAD~'
  'git filter-branch'
  'git clean -fdx'
  'git clean -fX'
  'git update-ref -d'
  'chmod -R 777'
  'chmod 777 '
  ':\(\)\{ :\|:& \};:'
  'curl [^|]+\| (sh|bash|zsh|fish)'
  'wget [^|]+\| (sh|bash|zsh|fish)'
  '(^|[;&|(`])[[:space:]]*sudo[[:space:]]'
  'mkfs\.'
  'dd if=.*of=/dev/(sd|disk|nvme|hd)'
  '> /dev/(sda|sdb|disk|nvme|hd)'
  'shred '
  'wipefs '
  'twine upload'
  'uv publish'
  'poetry publish'
  'python -m twine upload'
  'npm publish'
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$JUDGED" | grep -qE "$pattern"; then
    echo "BLOCKED by the engine safety hook (block-dangerous.sh)." >&2
    echo "Pattern matched: $pattern" >&2
    echo "Command: $CMD" >&2
    echo "" >&2
    echo "If this is genuinely needed, ask the user to run it manually outside Claude Code." >&2
    exit 2
  fi
done

# The owner's variable (board 056). CLAUDECODE is set in every shell an agent's tools start, and
# by it the board runner, engine.py and the owner-only commands (promote, apply-settings, the
# audit run's --owner-approved, baseline record…) tell the owner's terminal from an agent. A
# command that clears or replaces it would speak with the owner's voice, so it is refused:
# unset, `env -u`, `env -i`, an assignment of anything but 1 (before a command, with export or
# declare), `export -n`, and inline code that pops, deletes or overwrites it. Reading it
# (`echo $CLAUDECODE`, `env | grep`, `printenv`) and `CLAUDECODE=1 <command>` pass.
# A script the command only starts is not seen (docs/engine-limits.md).
OWNER_VARIABLE="CLAUDECODE"
OWNER_VARIABLE_PATTERNS=(
  "(^|[^[:alnum:]_])unset([[:space:]]+-[a-z]+)*([[:space:]]+[A-Za-z_][A-Za-z0-9_]*)*[[:space:]]+[\"']?${OWNER_VARIABLE}([^[:alnum:]_]|\$)"
  "(^|[^[:alnum:]_])env[[:space:]]([^;&|]*[[:space:]])?(-u[[:space:]]*|--unset[=[:space:]])[\"']?${OWNER_VARIABLE}([^[:alnum:]_]|\$)"
  "(^|[^[:alnum:]_])env[[:space:]]+([^;&|]*[[:space:]])?(-i|--ignore-environment|-)([[:space:]]|\$)"
  "(^|[^[:alnum:]_])exec[[:space:]]+-[a-z]*c"
  "(^|[^[:alnum:]_\$])${OWNER_VARIABLE}=([^1\"']|1[^[:space:];&|)]|[\"'][^1]|[\"']1[^\"']|\$)"
  "(^|[^[:alnum:]_])(export|declare|typeset)[[:space:]]+(-n|\\+x)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*[[:space:]]+)*${OWNER_VARIABLE}([^[:alnum:]_]|\$)"
  "(pop|unsetenv|delenv|delete|del|remove|unset)[^;&|]*${OWNER_VARIABLE}"
  "environ\\[[\"']${OWNER_VARIABLE}[\"']\\][[:space:]]*="
  "env\\.${OWNER_VARIABLE}[[:space:]]*="
  "putenv[^;&|]*${OWNER_VARIABLE}"
)
for pattern in "${OWNER_VARIABLE_PATTERNS[@]}"; do
  if printf '%s\n' "$JUDGED" | grep -qE -e "$pattern"; then
    echo "BLOCKED by the engine safety hook (block-dangerous.sh): the command clears or replaces ${OWNER_VARIABLE}," >&2
    echo "the variable that tells the owner's terminal from an agent's shell." >&2
    echo "Command: $CMD" >&2
    echo "" >&2
    echo "What only the owner may start is started by the owner, in their own terminal — or by the board" >&2
    echo "runner after their answer in tasks/blocked/. Put the question there." >&2
    exit 2
  fi
done

# Push (board 017, owner decision): park-ask-gated.py decides an ordinary push by environment
# (board 603: the owner asks locally, the cloud session's own claude/ branch goes, the runner is
# refused), but the dangerous forms are refused HERE, in every environment, whatever that hook or
# a prompt would answer. The three literal patterns above knew one spelling each: `git -C dir push --force`,
# a flag after the refspec, `-uf`, `+branch`, `--mirror`, `--delete`, `:branch` and
# `git push -f` at the end of a line all passed. Now every `git … push` in the command is read
# word by word, up to the next separator:
#   * a force push: --force, --force-with-lease, --force-if-includes, --mirror, a short-flag
#     cluster with `f` (-f, -uf), a refspec that starts with `+`;
#   * the deletion of a remote branch: --delete, a cluster with `d`, a refspec that starts with `:`;
#   * a push into main or stable: a refspec whose destination is one of them (main, HEAD:main,
#     x:refs/heads/main), --all and --branches, and a push that names no refspec (or HEAD)
#     while the checked-out branch is one of them.
# A push that is only quoted in a message is text (board 738, above); one handed to `bash -c`
# is judged. A push from inside a script is not seen (docs/engine-limits.md).
#
# Which branches: PUSH_PROTECTED_BRANCHES in .claude/project.env, space- or comma-separated
# ("main master production"); unset or empty means main and stable. Read with sed rather than
# `source` — a deny hook must not execute a project file — and guarded by the gate: the work
# being judged may not change the key (gate.py, SCOPE_KEYS).
push_protected_branches() {
  local env_file="${CLAUDE_PROJECT_DIR:-.}/.claude/project.env" value=""
  if [ -f "$env_file" ]; then
    value=$(sed -nE 's/^[[:space:]]*PUSH_PROTECTED_BRANCHES=["'"'"']?([A-Za-z0-9_.\/, -]*)["'"'"']?.*$/\1/p' "$env_file" | tail -1 | tr ',' ' ')
  fi
  [ -n "${value// /}" ] || value="main stable"
  printf '%s' "$value"
}
read -ra PUSH_PROTECTED <<<"$(push_protected_branches)"

push_protected() {
  local name="${1#refs/heads/}" protected
  for protected in "${PUSH_PROTECTED[@]}"; do
    [ "$name" = "$protected" ] && return 0
  done
  return 1
}

# The branch a push without a refspec sends: the one checked out where the command runs.
push_branch() {
  local dir="$1" base
  base=$(read_field cwd 2>/dev/null || true)
  base="${base:-${CLAUDE_PROJECT_DIR:-.}}"
  case "$dir" in
    "") dir="$base" ;;
    /*) ;;
    *) dir="$base/$dir" ;;
  esac
  git -C "$dir" branch --show-current 2>/dev/null || true
}

# Prints why the push in the words given is refused; prints nothing for a push that may go on.
# $1 — the directory of `git -C`, the rest — the words after `push`.
push_refusal() {
  local dir="$1"; shift
  local -a positional=()
  local word flags all="" skip=""
  for word in "$@"; do
    if [ -n "$skip" ]; then skip=""; continue; fi
    case "$word" in
      --force|--force-with-lease|--force-with-lease=*|--force-if-includes|--mirror)
        echo "a force push ($word)"; return ;;
      --delete)
        echo "the deletion of a remote branch ($word)"; return ;;
      --all|--branches)
        all="$word" ;;
      --repo|--push-option|--receive-pack|--exec)
        skip=1 ;;
      --*) ;;
      -[A-Za-z0-9]*)
        flags="${word%%o*}"                      # `-o <option>`: what follows the o is its value
        case "$flags" in *f*) echo "a force push ($word)"; return ;; esac
        case "$flags" in *d*) echo "the deletion of a remote branch ($word)"; return ;; esac
        [ "$word" = "${flags}o" ] && skip=1 ;;
      +*)
        echo "a force push (the refspec $word starts with +)"; return ;;
      :?*)
        echo "the deletion of a remote branch (the refspec $word)"; return ;;
      *) positional+=("$word") ;;
    esac
  done
  if [ -n "$all" ]; then
    echo "a push of every branch, ${PUSH_PROTECTED[*]} among them ($all)"; return
  fi
  local branch="" refspec dst implicit=""
  [ "${#positional[@]}" -le 1 ] && implicit=1
  for refspec in "${positional[@]:1}"; do
    dst="${refspec##*:}"
    case "$dst" in HEAD|@) implicit=1; continue ;; esac
    if push_protected "$dst"; then
      echo "a push into ${dst#refs/heads/} (the refspec $refspec)"; return
    fi
  done
  if [ -n "$implicit" ]; then
    branch=$(push_branch "$dir")
    if [ -n "$branch" ] && push_protected "$branch"; then
      echo "a push into $branch (no other branch is named, and $branch is checked out)"
    fi
  fi
}

if printf '%s' "$JUDGED" | grep -q 'push'; then
  while IFS= read -r SEGMENT; do
    read -ra WORDS <<<"$SEGMENT" || true
    for ((i = 0; i < ${#WORDS[@]}; i++)); do
      case "${WORDS[i]}" in git|*/git) ;; *) continue ;; esac
      GIT_DIR_ARG=""
      j=$((i + 1))
      while [ "$j" -lt "${#WORDS[@]}" ]; do      # git's own options stand before the subcommand
        case "${WORDS[j]}" in
          -C) GIT_DIR_ARG="${WORDS[j+1]:-}"; j=$((j + 2)) ;;
          -c|--git-dir|--work-tree|--namespace|--config-env) j=$((j + 2)) ;;
          -*) j=$((j + 1)) ;;
          *) break ;;
        esac
      done
      [ "${WORDS[j]:-}" = "push" ] || continue
      REASON=$(push_refusal "$GIT_DIR_ARG" "${WORDS[@]:j+1}")
      if [ -n "$REASON" ]; then
        echo "BLOCKED by the engine safety hook (block-dangerous.sh): $REASON." >&2
        echo "Command: $CMD" >&2
        echo "" >&2
        echo "An ordinary push of a working branch is not refused here (park-ask-gated.py decides it by environment)." >&2
        echo "If this one is genuinely needed, ask the user to run it manually outside Claude Code." >&2
        exit 2
      fi
    done
  done < <(printf '%s\n' "$JUDGED" | tr ';&|()`' '\n\n\n\n\n\n' | tr -d "\"'")
fi

# Protected paths (board 714). protect-paths.sh refuses them to Edit|Write|MultiEdit; a shell
# command wrote and read them freely, because this hook did not know the list. Both hooks now
# source the one list. Here: a command none of whose words matches the list goes on untouched
# (two cheap processes); one that names a protected path is handed to shell_paths.py, which
# refuses a WRITE to any protected path and any mention of a SECRET one, and lets a read of a
# guarded file through (`git diff -- .claude/settings.json`, `grep` in it). What the text of a
# command cannot show — a path in a variable, a write made inside a script — it does not catch.
if [ ! -f "$HOOK_DIR/protected-path-list.sh" ]; then
  echo "BLOCKED by the engine safety hook (block-dangerous.sh): the list of protected paths" >&2
  echo "(protected-path-list.sh) is missing beside the hook, so this command cannot be checked." >&2
  echo "Restore it: python3 engine.py update." >&2
  exit 2
fi
# shellcheck source=/dev/null
. "$HOOK_DIR/protected-path-list.sh"

join_patterns() { local IFS='|'; printf '%s' "$*"; }

NAMED=$(printf '%s\n' "$JUDGED" | tr ' \t;&|()<>"'"'"'`,=[]{}' '[\n*]' \
  | grep -E -e "$(join_patterns "${PROTECTED_PATTERNS[@]}")" \
  | grep -vE -e "$(join_patterns "${ALLOWED_PATTERNS[@]}")" || true)
NAMED="${NAMED%%$'\n'*}"
if [ -n "$NAMED" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "BLOCKED by the engine safety hook (block-dangerous.sh): the command names a protected path" >&2
    echo "($NAMED) and there is no python3 to tell a read from a write, so it is refused." >&2
    echo "Command: $CMD" >&2
    exit 2
  fi
  HOOK_CWD=$(read_field cwd 2>/dev/null || true)
  if ! REASON=$(printf '%s' "$JUDGED" | PP_ALLOWED=$(printf '%s\n' "${ALLOWED_PATTERNS[@]}") \
      PP_SECRET=$(printf '%s\n' "${SECRET_PATTERNS[@]}") PP_GUARDED=$(printf '%s\n' "${GUARDED_PATTERNS[@]}") \
      python3 "$HOOK_DIR/shell_paths.py" "${HOOK_CWD:-$PWD}" "${CLAUDE_PROJECT_DIR:-}" 2>&1); then
    echo "${REASON:-BLOCKED by the engine safety hook (block-dangerous.sh): shell_paths.py failed.}" >&2
    echo "Command: $CMD" >&2
    echo "" >&2
    echo "The same paths are refused to Edit and Write (protect-paths.sh). If the change is genuinely" >&2
    echo "needed, ask the user to make it outside Claude Code. If the command only MENTIONS the path" >&2
    echo "in a message and was refused all the same, something in it could run the text (shell_text.py);" >&2
    echo "put the text in a file with the Write tool and pass the file." >&2
    exit 2
  fi
fi

# The overseer agent is read-only (board 055). It has Bash — the tests have to run — and until
# now nothing judged what that Bash wrote: only the tree's fingerprint, after the fact. Inside
# the agent a command may write under a temporary directory and nowhere else (shell_readonly.py).
if [ "$(read_field agent_type 2>/dev/null || true)" = "overseer" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "BLOCKED by the engine safety hook (block-dangerous.sh): the overseer agent is read-only, and" >&2
    echo "there is no python3 to tell a read from a write, so its shell commands are refused." >&2
    exit 2
  fi
  HOOK_CWD=$(read_field cwd 2>/dev/null || true)
  if ! REASON=$(printf '%s' "$JUDGED" | python3 "$HOOK_DIR/shell_readonly.py" "${HOOK_CWD:-$PWD}" "${CLAUDE_PROJECT_DIR:-}" 2>&1); then
    echo "${REASON:-BLOCKED by the engine safety hook (block-dangerous.sh): shell_readonly.py failed.}" >&2
    echo "Command: $CMD" >&2
    echo "" >&2
    echo "Judge what is there. To reproduce a RED, work in a copy: cp -r . /tmp/audit-copy && cd /tmp/audit-copy" >&2
    exit 2
  fi
fi

# Block a direct git commit on a protected branch (defense-in-depth). An ordinary push is not
# blocked here: park-ask-gated.py decides it by environment (board 603); its dangerous forms
# were refused above (board 017).
BRANCH=""
# Ask git, do not look for a .git DIRECTORY: in a `git worktree` checkout .git is a FILE.
# With the old `[ -d .../.git ]` the branch stayed unknown there, and a legitimate commit
# on an unattended/<date> branch was refused (evals: bd-commit-on-unattended-branch-in-worktree).
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && git -C "$CLAUDE_PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BRANCH=$(git -C "$CLAUDE_PROJECT_DIR" branch --show-current 2>/dev/null || echo "")
fi

# Commit only. Push left this block on 2026-10-01 (owner decision, docs/plan/package-3b-finish.md):
# then the settings file's `Bash(git push:*)` in permissions.ask prompted for it; since board 603
# park-ask-gated.py decides it by environment, the ask rule gone. Board 017 put the dangerous
# forms back into the hook, in the push section above: a forced push, the deletion of a remote
# branch and a push into main or stable (PUSH_PROTECTED_BRANCHES) are refused whatever the
# prompt would be answered; a release is the operator's, outside Claude Code.
PROTECTED_BRANCHES=("main" "master" "production" "prod" "release")
for protected in "${PROTECTED_BRANCHES[@]}"; do
  if [ "$BRANCH" = "$protected" ]; then
    if echo "$JUDGED" | grep -qE '(^|[;&|(`])[[:space:]]*git[[:space:]]+(-[^[:space:]]+[[:space:]]+([^-][^[:space:]]*[[:space:]]+)?)*commit([[:space:]]|$)'; then
      # Name the subcommand that matched, not the command's second word: for
      # `git -C dir commit` the second word is `-C`.
      echo "BLOCKED: direct git commit on protected branch '$BRANCH'." >&2
      echo "Create a feature branch first: git checkout -b feat/<slug>" >&2
      exit 2
    fi
  fi
done

# Commit policy — by environment. Owner-ratified 2026-08-27 (unattended branch) and
# docs/plan/package-3b.md (the environment table).
#
#   environment                         | commit                       | push
#   ------------------------------------+------------------------------+------------------------
#   attended, the owner's machine       | refused: the commit is the   | park-ask-gated.py asks
#                                       | owner's review checkpoint    | force push: denied
#   unattended (the board runner)       | allowed on unattended/* only | refused by
#                                       |                              | park-ask-gated.py
#   cloud session (CLAUDE_CODE_REMOTE)  | allowed on the session's own | the same switch: its own
#                                       | non-protected branch, ONLY   | claude/ branch to origin
#                                       | when CLOUD_COMMIT_POLICY in  | goes, any other push is
#                                       | .claude/project.env says     | refused (park-ask-gated.py);
#                                       | session-branch; ships "off"  | switch off: asks
#
# The unattended branch is the opt-in in both local modes: nothing reaches `main` without
# a human reading the diff, and a long run still builds each session on a committed base
# instead of an unreviewed index inherited from the session before. The cloud rule is a
# SWITCH, not a default, because the shape of a cloud session (which branch it checks
# out, what the remote is) has not been observed yet: .claude/unattended/env-probe.sh
# prints those facts, the owner runs it in a real cloud session, and only then does the
# switch move. A cloud session reads the shared .claude/settings.json and so runs this
# hook; it does not read ~/.claude/settings.json or settings.local.json
# (code.claude.com/docs/en/claude-code-on-the-web). CLAUDE_CODE_REMOTE is "true" there
# (code.claude.com/docs/en/env-vars).
#
# The pattern is the command-position form from S7: a bare `^` let `cd x && git
# commit` walk straight past the old check, and `git -C dir commit` hid the
# subcommand behind a global option. Both are covered here.
cloud_commit_policy() {
  # One key, read with sed rather than `source`: a deny hook must not execute a project file.
  local env_file="${CLAUDE_PROJECT_DIR:-.}/.claude/project.env"
  [ -f "$env_file" ] || { echo off; return; }
  local value
  value=$(sed -nE 's/^[[:space:]]*CLOUD_COMMIT_POLICY=["'"'"']?([A-Za-z-]*)["'"'"']?.*$/\1/p' "$env_file" | tail -1)
  echo "${value:-off}"
}

if echo "$JUDGED" | grep -qE '(^|[;&|(`])[[:space:]]*git[[:space:]]+(-[^[:space:]]+[[:space:]]+([^-][^[:space:]]*[[:space:]]+)?)*commit([[:space:]]|$)'; then
  case "$BRANCH" in
    unattended/*)
      : # allowed — an unattended run's own branch
      ;;
    *)
      if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && [ -n "$BRANCH" ] && [ "$(cloud_commit_policy)" = "session-branch" ]; then
        : # allowed — a cloud session on its own branch; protected branches were refused above
      else
        echo "BLOCKED: commits are allowed only on an 'unattended/<date>' branch." >&2
        echo "Current branch: '${BRANCH:-unknown}'." >&2
        if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
          echo "This is a cloud session (CLAUDE_CODE_REMOTE=true). Commits on the session's branch are" >&2
          echo "allowed only when CLOUD_COMMIT_POLICY=\"session-branch\" in .claude/project.env; it is" >&2
          echo "'$(cloud_commit_policy)'. The owner flips it after running .claude/unattended/env-probe.sh here." >&2
        else
          echo "On any other branch a commit is a human review checkpoint: stage with 'git add <files>'," >&2
          echo "summarise the change, suggest a message, and let the user run the commit themselves." >&2
          echo "For an unattended run, switch first: git switch -c unattended/\$(date -u +%Y-%m-%d)" >&2
        fi
        exit 2
      fi
      ;;
  esac
fi

exit 0
