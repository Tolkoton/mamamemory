#!/usr/bin/env bash
# Commit a unit of work onto the run's own branch. Owner-ratified 2026-08-27.
#
# WHY THIS EXISTS
# ---------------
# Before this, an unattended run staged everything and committed nothing. Over a
# night that means every session builds on top of an unreviewed index it
# inherited from the session before it, so one bad change is silently inherited
# by all the work that follows and there is no point to roll back to.
#
# The fix is not "let the agent commit". It is "let the agent commit somewhere a
# human still has to approve before it counts". Nothing reaches `main` without a
# person reading the diff -- the checkpoint is preserved exactly where it does
# work, and removed exactly where it only caused work to pile up.
#
# block-dangerous.sh enforces the same rule independently: a commit outside an
# `unattended/*` branch is refused regardless of what this script does. See
# tests/test_commit_policy.py, 11 cases.
#
# Usage:  commit_checkpoint.sh [--staged] <node-id> [message]
#   --staged   commit exactly what is already in the index; do not `git add -u`.
#              For a run that creates NEW files: `-u` never stages an untracked file,
#              so a checkpoint of "the slice I just wrote" has to be staged by hand
#              (`git add <files>`, as the engine rules' unit-of-work steps say) and then
#              committed as staged. Without the flag the behaviour is unchanged.
# Exit 0 when it committed AND when there was nothing to commit -- both are
# normal. Non-zero only on a real failure.

set -uo pipefail

STAGED_ONLY=0
if [ "${1:-}" = "--staged" ]; then
  STAGED_ONLY=1
  shift
fi
NODE="${1:-unknown}"
MESSAGE="${2:-}"

# The repository this script lives in, unless the harness names one. In a session
# that works on another clone than the one it was started in, CLAUDE_PROJECT_DIR is
# the SESSION's repository, which is the wrong one to commit in; the caller passes
# CLAUDE_PROJECT_DIR=<that clone> explicitly, and the branch guard below still holds.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
cd "$PROJECT_ROOT" || exit 1

CURRENT=$(git branch --show-current 2>/dev/null || echo "")

# Never commit on a branch a human is using. A branch that already matches
# `unattended/*` is the run's own and is kept as it is: a run may be given a
# branch with a suffix (`unattended/<date>-<package>`), and forcing today's date
# would silently fork the run onto a second branch nobody asked for. Otherwise
# create or switch to today's -- the working tree carries over unchanged.
# The cloud rule mirrors block-dangerous.sh: in a cloud session (CLAUDE_CODE_REMOTE=true),
# with CLOUD_COMMIT_POLICY="session-branch" in .claude/project.env, the session's own
# non-protected branch is the checkpoint branch. The switch ships off.
cloud_commit_policy() {
  local value
  value=$(sed -nE 's/^[[:space:]]*CLOUD_COMMIT_POLICY=["'"'"']?([A-Za-z-]*)["'"'"']?.*$/\1/p' .claude/project.env 2>/dev/null | tail -1)
  echo "${value:-off}"
}
cloud_branch_allowed() {
  [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || return 1
  [ "$(cloud_commit_policy)" = "session-branch" ] || return 1
  case "$1" in ""|main|master|production|prod|release) return 1 ;; esac
  return 0
}

case "$CURRENT" in
  unattended/*)
    BRANCH_NAME="$CURRENT"
    ;;
  *)
    if cloud_branch_allowed "$CURRENT"; then
      BRANCH_NAME="$CURRENT"
      echo "[checkpoint] cloud session: committing on its own branch $BRANCH_NAME"
    else
      BRANCH_NAME="unattended/$(date -u +%Y-%m-%d)"
      if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
        git switch -q "$BRANCH_NAME" || { echo "[checkpoint] cannot switch to $BRANCH_NAME" >&2; exit 1; }
      else
        git switch -qc "$BRANCH_NAME" || { echo "[checkpoint] cannot create $BRANCH_NAME" >&2; exit 1; }
      fi
      echo "[checkpoint] on $BRANCH_NAME (was ${CURRENT:-detached})"
    fi
    ;;
esac

# Stage tracked modifications only. Deliberately NOT `git add -A`: an unattended
# run generates logs, patches and scratch files, and sweeping them in wholesale
# is how a review surface becomes unreadable.
if [ "$STAGED_ONLY" -eq 0 ]; then
  git add -u
  # The journals' session files (board 739: .engine/journal/<journal>/<session>.md) are new files the
  # work's own hooks and scripts wrote — records of this work, not scratch — so they go with it.
  [ -d .engine/journal ] && git add -- .engine/journal
fi

# A guarded file never goes into an agent's commit (board 724): the constitution, the settings,
# .engine/rules.md, migrations, CI workflows — the GUARDED_PATTERNS of the list the deny hooks
# read. `git add -u` above takes every tracked change, the agent's own write to such a file and
# the owner's uncommitted edit of it alike; after the commit a comparison with HEAD sees nothing.
# The owner commits these files, and the board runner after the owner's «так» — neither through
# this script. Without the list nothing is committed: a commit that cannot be checked is refused.
GUARDED_LIST="$HERE/../hooks/protected-path-list.sh"
if [ ! -f "$GUARDED_LIST" ]; then
  echo "[checkpoint] REFUSING to commit: the list of guarded paths ($GUARDED_LIST) is missing." >&2
  exit 1
fi
. "$GUARDED_LIST"
GUARDED_STAGED=()
while IFS= read -r -d '' path; do
  for pattern in "${GUARDED_PATTERNS[@]}"; do
    if [[ "$path" =~ $pattern ]]; then GUARDED_STAGED+=("$path"); break; fi
  done
done < <(git diff --cached --no-renames --name-only -z)   # a rename would list the new name only: the old one is the guarded file
if [ "${#GUARDED_STAGED[@]}" -gt 0 ]; then
  if [ "$STAGED_ONLY" -eq 1 ]; then
    echo "[checkpoint] REFUSING to commit: a guarded file is staged, and only the owner or the board runner commits one:" >&2
    printf '[checkpoint]   %s\n' "${GUARDED_STAGED[@]}" >&2
    echo "[checkpoint] Unstage it (git restore --staged <file>) and commit again. Nothing was committed." >&2
    exit 1
  fi
  git reset -q -- "${GUARDED_STAGED[@]}" || { echo "[checkpoint] cannot unstage the guarded files" >&2; exit 1; }
  printf '[checkpoint] guarded file left out of the commit (only the owner or the board runner commits it): %s\n' "${GUARDED_STAGED[@]}"
fi

if git diff --cached --quiet; then
  echo "[checkpoint] nothing staged for $NODE — nothing to commit"
  exit 0
fi

if [ -z "$MESSAGE" ]; then
  MESSAGE="checkpoint($NODE): unattended unit complete"
fi

# LAST LINE OF DEFENCE, and on this path the ONLY one.
#
# PreToolUse hooks and the permission deny-list evaluate the Bash tool call the
# agent issues. They do NOT see commands run from inside a script: verified
# 2026-08-27 with `git commit --dry-run`, which the harness refuses at top level
# and which executed untouched from a two-line script. So block-dangerous.sh
# does NOT protect this file, whatever the policy says -- the branch rule holds
# here only because these lines hold it.
#
# Re-check rather than trust the switch above: a `git switch` that fails leaves
# us on the previous branch, and committing there is precisely the outcome the
# whole policy exists to prevent.
FINAL_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
case "$FINAL_BRANCH" in
  unattended/*)
    ;;
  *)
    if ! cloud_branch_allowed "$FINAL_BRANCH"; then
      echo "[checkpoint] REFUSING to commit on branch '${FINAL_BRANCH:-unknown}'." >&2
      echo "[checkpoint] Commits are legal only on unattended/<date>, or on a cloud session's own" >&2
      echo "[checkpoint] branch when CLOUD_COMMIT_POLICY says session-branch. Nothing was committed." >&2
      exit 1
    fi
    ;;
esac

if git commit -q -m "$MESSAGE"; then
  echo "[checkpoint] committed $(git rev-parse --short HEAD) on $BRANCH_NAME"
  exit 0
fi

echo "[checkpoint] commit failed for $NODE" >&2
exit 1
