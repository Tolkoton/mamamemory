#!/usr/bin/env bash
# The board runner: works through tasks/ one task at a time, each in a fresh conversation.
#
#   bash .claude/unattended/board-runner.sh            run until nothing can move, then stop
#   bash .claude/unattended/board-runner.sh --once     one task, then stop
#   bash .claude/unattended/board-runner.sh --no-push  never push (somebody else sends the branch)
#   bash .claude/unattended/board-runner.sh --status   print the status line and the summary, run nothing
#   bash .claude/unattended/board-runner.sh --stop-after-task   ask the working runner to stop once
#                                                      its current task is closed; run nothing
#   bash .claude/unattended/board-runner.sh --stop-after-attempt   …once the attempt in hand has
#                                                      ended: the task stays in doing/; run nothing
#
# WHAT IT DOES, in the order it does it (tasks/README.md is the board's manual):
#   before every task   fetch and `pull --rebase` the work branch — new tasks and the owner's
#                       answers arrive this way; take new files from the inbox into tasks/todo/
#                       (a file with the number of a proposal in tasks/proposed/ puts it to work: nothing else
#                       ever leaves that column — the runner takes no task from it, board 111)
#                       (one commit); close the gate escalations the owner answered «так»
#                       and take the actions the owner answered «так» (see below); move answered tasks from tasks/blocked/ back to todo/ (one commit)
#   the task            the first in todo/ whose dependencies are in done/ goes to doing/ in a
#                       commit of its own, then `claude -p` in a FRESH conversation. A task the
#                       owner has just answered is the first, whatever its number (board 049:
#                       `board.py unblock` writes tasks/.first, `board.py next` reads it). A task
#                       that needs the owner present is never taken, and one left in doing/ by
#                       the owner's session stops no task: it stays as it is, beside the runner's own task
#                       (only the cleanup task waits for it: not placed, board 723;
#                       one already in todo/ is not taken, board 838)
#   while it is open    a session that ended with the task still in doing/ is continued
#                       (--resume); a usage-limit notice waits 15 minutes and is not an attempt
#   the task is closed  when the agent moved it to done/ or blocked/. Then: the working tree is
#                       checked (see below), push, next task
#   a task is stuck     three attempts in a row without a new commit; a task older than twelve
#                       hours; the task's budget spent; three overseer BLOCKs in a row on one of
#                       its units: the runner PARKS the task and takes the next one (see below)
#                       — one task never stops the board
#   extra sessions      a task that says «Додаткові сесії: так» (evals, measurements, a release
#                       audit, a full simplifier pass) is taken only when no ordinary task can
#                       start, and not at all while the extra sessions of the last seven days are
#                       at the project's cap (EXTRA_SESSIONS_WEEK_USD, board 110). A task that met
#                       the cap mid-work went back to todo/ itself (`board.py extra-wait`): it
#                       WAITS there — not parked, nobody asked — and the next task is taken. When
#                       only such tasks are left: state=idle reason=extra-cap
#   nothing to take     once a day the runner puts a cleanup task into todo/ itself and takes it
#                       (THE CLEANUP TASK below)
#   it stops            todo/ empty or everything left waiting for the owner; a soft stop; and the
#                       few critical things below — always with a summary
#
# ONE TASK NEVER STOPS THE BOARD (board 021). A stuck task is moved to tasks/blocked/ by the runner
# itself (`board.py park`): a section «Чому зупинилась», a question to the owner, an entry in the
# anomaly journal tasks/ANOMALIES.md, one commit — and the next task is taken. Uncommitted work
# the agent left outside tasks/ is saved as one commit on a branch of its own, wip/<task>/<UTC>,
# pushed to the remote (board 035: a stash lives on this machine only), and put into a git stash
# as well; that section and the journal name both, so the next task starts on a clean tree and
# nothing is lost. The owner's answer returns the task to todo/ with a
# fresh clock and count (after a budget stop: with one more budget). Everything else that is odd
# — a push that failed, a task that vanished from the board — is written into the journal and the
# work goes on. THE WHOLE BOARD STOPS only on: a pull that conflicts (reason=pull-conflict);
# claude logged out (reason=logged-out; the task stays in doing/ and is continued by the next
# start); the guarded files could not be recorded, checked or put back around a session
# (reason=protected, board 724); a git or board.py failure after which nothing can be committed; the soft stop.
#
# THE GUARDED FILES AROUND EVERY SESSION (board 724). Before a session the runner records the
# constitution, the settings, .engine/rules.md, migrations and CI workflows (protected_guard.py
# `before`), after it it compares (`after`): a file that differs is put back, the discarded change
# kept as a patch under .claude/state/gate/protected/discarded/, the journal written, and the task
# parked in blocked/ with a question (reason `protected`); a file that cannot be put back, and a
# check that could not be made at all (before or after the session), stops the board
# (reason=protected). The comparison is made from what `before` printed, held in this process; a
# copy is kept in $GUARD_KEPT while the session runs, so that a runner that died meanwhile (a
# reboot, a kill) makes the comparison at its next start, before its first pull. This is the check
# left when a turn was cut short or the session's own hooks were switched off; what the runner
# itself applies on the owner's «так» (the settings proposal, a rule) happens between sessions and
# is not seen. WHAT IT HOLDS: a mistaken or naive change of a guarded file — the session only
# writes the file, by any means. Not a session that goes for the check itself (this script,
# protected_guard.py, $GUARD_KEPT, the runner's process): it runs as the same Linux user, and
# that is a documented limit (docs/engine-limits.md, "The same Linux user"), the owner's decision.
#
# ONE JOURNAL FOR EVERYTHING ODD (board 035). tasks/ANOMALIES.md is written by the runner, by the
# Stop gate (an escalation), by a hook (the stuck counter) and by the agent (`board.py anomaly …
# --source агент`); each entry says who wrote it. The runner commits what the others wrote before
# every pull and after every attempt. Every stop with state=error leaves an entry too — except
# when the checkout is not on the work branch (reason=branch): nothing is written into a foreign
# branch, the stop is in events.log and summary.md only. A gate question whose escalation was
# closed another way (the owner ran `gate.py --close-escalation` in a terminal) goes to done/ by
# itself, with an entry in the journal.
#
# THREE BLOCKS PARK THE TASK, AND THE RUNNER DOES IT (board 031). When three overseers in a row
# refused one unit, the Stop hook (overseer_stop.py) asks nothing of the agent: it leaves the marker
# .claude/state/board/three-blocks-<task>.json with the three verdicts and stops the session. The
# runner finds the marker and parks the task like any stuck one (reason three-blocks), with the
# verdicts written under «Чому зупинилась». The hook leaves the marker only for the task that is in
# doing/, so a runner that died before parking leaves it to the next one, which parks first.
#
# A TASK CLOSES WITH A CLEAN TREE (board 029). When the agent has moved its task to done/ or
# blocked/, the runner looks at `git status`. Files that are uncommitted now and were not before
# the task began are the task's: the agent gets the turn back ONCE, in the same conversation, with
# one request — commit what belongs to the task, remove the rest. If the tree is still dirty after
# that turn (or the task's budget buys no turn), the files are listed in the anomaly journal and
# the next task is taken. The runner deletes, stashes and commits none of them.
#
# STOPPING IT (board 019). Never by killing the process: the agent then loses the uncommitted
# work of its task. `--stop-after-task` puts the flag .claude/state/board/stop-after-task; the
# runner looks at it between tasks only, so the current task is finished and pushed first, then
# it stops with state=stopped reason=stop-after-task and removes the flag. `--stop-after-attempt`
# (board 035) puts stop-after-attempt: the runner looks at it before and after every attempt, so
# the session in hand ends by itself, what it committed is pushed, and the runner stops with
# reason=stop-after-attempt; the task stays in doing/ — with its conversation, clock and count —
# and the next start continues it. With no runner working
# either command sets nothing; a flag left by a runner that died is removed when the next one starts.
#
# WHAT THE OPERATOR READS, in .claude/state/board/:
#   status      one line: state=<running|waiting-limit|idle|waiting-owner|stopped|error>
#               task=<name|-> since=<UTC> [reason=<word>]
#   events.log  one UTC line per event      costs.json  per task: attempts, sessions, cost
#   summary.md  written at every stop       logs/       the raw output of every attempt
# A session whose stderr (logs/<task>-<n>.json.err) says the workspace is not trusted leaves one entry
# in the anomaly journal — once a project — and a line in summary.md (board 791); the work goes on.
# An open gate escalation that names no file covers all work (board 301): no task is started, the
# runner stops with state=waiting-owner reason=gate-escalation and summary.md names its stamp.
# Exit 0: idle, waiting-owner, stopped (--once, --stop-after-task, --stop-after-attempt). Exit 1: error.
#
# A GATE QUESTION (tasks/blocked/9NN-gate-escalation-*.md, written by gate.py when the Stop gate
# gives up) is the one task the runner finishes itself. It commits and pushes the question as
# soon as it appears; when the owner's answer «так» ARRIVES — by the pull or through the
# inbox — it runs `gate.py --close-escalation <stamp>` and moves the task to done/ with a
# two-line report. An answer that was already in the checkout before the pull was written on
# this machine, where the writer is the agent the gate judged: it is wiped and asked again.
# gate.py refuses the command inside a Claude Code session, so a runner an agent starts closes
# nothing.
#
# AN OWNER ACTION (board 008) is what the owner approved with «так» under a question that offers
# it (`Дія runner-а: <action> <sha256>`, see board.py). The runner takes it, never the agent,
# and only from the short list: `apply-settings` (owner_action.py: the settings proposal is
# copied over .claude/settings.json and its test run), `promote-rule` / `reject-rule` (board 040:
# the owner's «так» or «ні» under a rule question — a lesson becomes a rule in .engine/rules.md,
# or its proposal is closed), `update-deps` (board 076: the patches and minor versions the owner
# approved under the question of a /maintain task — owner_action.py updates them one at a time,
# each checked by the full gate and committed on its own or rolled back), `amend-goals` /
# `seal-goals` (boards 051, 787: goals.py puts an approved amendment in place of the goals document
# and seals it, or puts the first seal on the document the owner approved) and the gate's
# `close-escalation` above.
# The same rule for where the answer came from applies. The offer is then replaced by the
# outcome and the task returns to todo/ for the agent to check and report; a rule question the
# runner acted on goes straight to done/ with a short report, no agent is started for it.
#
# THE RUNNER MOVES A TASK INTO doing/; THE AGENT MOVES IT OUT — or the runner parks it in
# blocked/ when it is stuck. Gate questions and rule questions apart, the runner writes no report
# and judges no work. It commits nothing
# but tasks/ and, after apply-settings, .claude/settings.json, after a rule action
# .engine/rules.md and .engine/rule-proposals.md — and only on the work branch, which must
# be an unattended/* branch: hooks do not see a commit made from a script, so the check is here.
# (After update-deps the commits — one per update, one for the result — are owner_action.py's own.)
#
# THE WEEKLY MAINTENANCE TASK (board 076). Before every task the runner asks `board.py
# maintain-task`: once a week it puts NNN-maintain-<date>.md into todo/ — a task to run /maintain —
# unless one already waits in todo/, doing/ or blocked/. One commit. MAINTAIN_EVERY_DAYS in
# .claude/project.env (empty: 7; 0: never); BOARD_TODAY names another day (the tests).
#
# THE CLEANUP TASK (board 045). When nothing can be taken — todo/ is empty, or all that is left
# waits for the owner — the runner asks `board.py cleanup-task` before it stops: never while a task
# lies in doing/, the owner's attended one included (board 723), and not more than once
# a day it puts NNN-cleanup-<date>.md into todo/ — a task to run `simplifier.py nightly` and act by
# the simplifier's rules — writes that into the anomaly journal, commits both in one commit and
# takes the task. The next pass finds nothing due and stops as before. CLEANUP_EVERY_DAYS in
# .claude/project.env (empty: 1; 0: never); BOARD_TODAY names another day (the tests).
#
# Every number is an environment variable, so the tests run in seconds:
#   BOARD_BRANCH (unattended/work)  BOARD_REMOTE (origin)  BOARD_INBOX (~/engine-ops/tasks-inbox)
#   BOARD_CLAUDE (claude)  BOARD_LIMIT_WAIT_SEC (900)  BOARD_TASK_MAX_SEC (43200)
#   BOARD_STALL_ATTEMPTS (3)  BOARD_PAUSE_SEC (30, between attempts)
#   BOARD_MAX_USD (empty = no cap): the most one task may cost; passed on as --max-budget-usd

set -uo pipefail

ONCE=0; PUSH=1; STATUS_ONLY=0; STOP_REQUEST=""; JOURNALED=0
for arg in "$@"; do
  case "$arg" in
    --once) ONCE=1 ;;
    --no-push) PUSH=0 ;;
    --status) STATUS_ONLY=1 ;;
    --stop-after-task) STOP_REQUEST=task ;;
    --stop-after-attempt) STOP_REQUEST=attempt ;;
    *) echo "board-runner: unknown option '$arg' (see the head of this file)" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
cd "$PROJECT_ROOT" || exit 1

BRANCH="${BOARD_BRANCH:-unattended/work}"
REMOTE="${BOARD_REMOTE:-origin}"
INBOX="${BOARD_INBOX:-$HOME/engine-ops/tasks-inbox}"
CLAUDE_BIN="${BOARD_CLAUDE:-claude}"
LIMIT_WAIT="${BOARD_LIMIT_WAIT_SEC:-900}"
TASK_MAX="${BOARD_TASK_MAX_SEC:-43200}"
STALL_ATTEMPTS="${BOARD_STALL_ATTEMPTS:-3}"
PAUSE="${BOARD_PAUSE_SEC:-30}"
MAX_USD="${BOARD_MAX_USD:-}"

STATE="$PROJECT_ROOT/.claude/state/board"
MODE_FILE="$PROJECT_ROOT/.claude/state/overseer/mode"
MODE_BEFORE="$STATE/mode.before"
LOCK="$STATE/lock"
STOP_FLAG="$STATE/stop-after-task"
STOP_ATTEMPT_FLAG="$STATE/stop-after-attempt"
GATE_PY="$HERE/../hooks/gate.py"
GUARD_PY="$HERE/../hooks/protected_guard.py"   # board 724: the guarded files around every session
GUARD_BEFORE=""; GUARD_PARKS=0; PROTECTED=""
GUARD_KEPT="$STATE/guard-before"   # the task (line 1) and what `before` printed (line 2), while a session runs
ACCEPTED="$STATE/gate-accepted"   # answers that arrived from the owner: name, stamp, sha256
REVIEWED_ACCEPTED="$STATE/reviewed-accepted"   # the numbers of tasks/.reviewed that arrived from the owner (board 100)
DIRTY_BEFORE="$STATE/dirty-before" # what was uncommitted when the task in doing/ was started
UNTRUSTED_NOTED="$STATE/untrusted-workspace"   # board 791: the journal has its entry — one a project
UNTRUSTED_LOG=""   # the first log of this run in which claude said the workspace is not trusted
blocks_marker() { echo "$STATE/three-blocks-$1.json"; }   # left by overseer_stop.py after the third BLOCK
reader_marker() { echo "$STATE/reader-blocks-$1.json"; }   # left by reader.py after the third BLOCK on one record (board 099)
board() { python3 "$HERE/board.py" --root "$PROJECT_ROOT" "$@"; }
memo() { python3 "$HERE/board_state.py" "$STATE" "$@"; }

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
event() { echo "$(now) $*" >> "$STATE/events.log"; }
say() { echo "[board] $*"; }
status() {  # status <state> <task|-> [reason]
  echo "state=$1 task=$2 since=$(now)${3:+ reason=$3}" > "$STATE/status"
}

if [ "$STATUS_ONLY" -eq 1 ]; then
  cat "$STATE/status" 2>/dev/null || echo "state=never-ran"
  board summary
  exit 0
fi

# --- the soft stop is asked for here; taken between tasks (at the foot of the main loop) or ------
# --- between attempts (in run_task). ------------------------------------------------------------
if [ -n "$STOP_REQUEST" ]; then
  HOLDER=$(cat "$LOCK" 2>/dev/null || echo "")
  if [ -z "$HOLDER" ] || ! kill -0 "$HOLDER" 2>/dev/null; then
    echo "board-runner: no runner is working here; nothing to stop" >&2
    exit 1
  fi
  touch "$STATE/stop-after-$STOP_REQUEST" || exit 1
  event "stop-requested after-$STOP_REQUEST pid=$HOLDER"
  say "the runner (pid $HOLDER) will stop after its current $STOP_REQUEST: $(cat "$STATE/status" 2>/dev/null)"
  exit 0
fi

mkdir -p "$STATE/logs" "$(dirname "$MODE_FILE")"

# --- one runner at a time. The lock holds the PID; a lock whose PID is gone is reclaimed. -------
if [ -f "$LOCK" ]; then
  HOLDER=$(cat "$LOCK" 2>/dev/null || echo "")
  if [ -n "$HOLDER" ] && kill -0 "$HOLDER" 2>/dev/null; then
    echo "board-runner: another runner is working here (pid $HOLDER); see $STATE/status" >&2
    exit 1
  fi
  event "lock-reclaimed pid=${HOLDER:-unknown}"
fi
echo $$ > "$LOCK"
# A stop flag that is here before this runner took a task was meant for a runner that is gone.
if [ -f "$STOP_FLAG" ] || [ -f "$STOP_ATTEMPT_FLAG" ]; then rm -f "$STOP_FLAG" "$STOP_ATTEMPT_FLAG"; event "stop-flag-stale removed"; fi

# --- nobody is watching: say so for the lifetime of the runner, and put it back afterwards. -----
# A planning gate then parks instead of asking, and an ask-gated command is parked, not hung on.
# A leftover mode.before means a runner died without its trap (kill -9): heal first.
restore_mode() {
  [ -f "$MODE_BEFORE" ] || return 0
  if [ "$(cat "$MODE_BEFORE")" = "(absent)" ]; then rm -f "$MODE_FILE"; else cp "$MODE_BEFORE" "$MODE_FILE"; fi
  rm -f "$MODE_BEFORE"
}
restore_mode
if [ -f "$MODE_FILE" ]; then cp "$MODE_FILE" "$MODE_BEFORE"; else echo "(absent)" > "$MODE_BEFORE"; fi
echo unattended > "$MODE_FILE"
export CLAUDE_UNATTENDED_SESSION=1

CLAUDE_PID=""
cleanup() {
  if [ -n "$CLAUDE_PID" ]; then
    kill -TERM "$CLAUDE_PID" 2>/dev/null
    for _ in 1 2 3 4 5; do kill -0 "$CLAUDE_PID" 2>/dev/null || break; sleep 1; done
    kill -KILL "$CLAUDE_PID" 2>/dev/null
  fi
  restore_mode
  [ "$(cat "$LOCK" 2>/dev/null)" = "$$" ] && rm -f "$LOCK"
}
trap cleanup EXIT
# Killed: the entry is written, not committed — the next start commits it before its first pull.
trap 'event "killed"; board anomaly "${TASK_NAME:--}" "runner-а вбито сигналом (TERM або INT) посеред роботи; стан error, причина killed" "сесію агента зупинено разом із runner-ом; незакомічена робота лишилась у робочому дереві, задача — там, де була. Runner-а треба запустити знову; зупиняти його слід лише через --stop-after-task або --stop-after-attempt." > /dev/null 2>&1; status error "${TASK_NAME:--}" killed; exit 143' TERM INT

# finish <state> <task|-> <reason-word> <one sentence>: the summary, the status line, the exit code.
finish() {
  local state="$1" task="$2" reason="$3" sentence="$4" code=1
  case "$state" in idle|waiting-owner|stopped) code=0 ;; esac
  # Every stop with state=error is in the journal (board 035) — once, and never from a checkout
  # that is not on the work branch.
  if [ "$state" = error ] && [ "$JOURNALED" -eq 0 ] && [ "$reason" != branch ]; then
    JOURNALED=1
    note_anomaly "$task" "runner зупинився зі станом \`error\` (причина \`$reason\`): $sentence" \
      "task board зупинено; після усунення причини runner-а треба запустити знову. Подробиці на сервері: \`.claude/state/board/summary.md\`, \`events.log\`, \`logs/\`."
    push_branch quiet
  fi
  {
    echo "# Task board: підсумок запуску"
    echo
    echo "- Час (UTC): $(now)"
    echo "- Стан: \`$state\` — $sentence"
    [ "$task" = "-" ] || echo "- Задача: \`$task\`"
    echo "- Гілка: \`$BRANCH\` на \`$(git rev-parse --short HEAD 2>/dev/null)\`"
    [ -z "$UNTRUSTED_LOG" ] || echo "- Увага: теку проєкту не позначено довіреною — Claude Code не застосовує список \`allow\` з \`.claude/settings.json\` (так сказала сесія: \`$UNTRUSTED_LOG\`). Відкрийте Claude Code в цій теці один раз і прийміть trust dialog."
    echo
    echo "## Task board"
    echo
    board summary 2>&1 | sed 's/^/- /'
    echo
    echo "## Витрати"
    echo
    memo report 2>&1 | sed 's/^/- /'
  } > "$STATE/summary.md"
  rm -f "$STOP_FLAG" "$STOP_ATTEMPT_FLAG"   # whatever the reason, the runner has stopped: the request is answered
  status "$state" "$task" "$reason"
  event "stop $state $reason $task"
  say "$state ($reason): $sentence"
  say "summary: $STATE/summary.md"
  exit "$code"
}

# --- the branch. Commits are legal on unattended/* only; this runner works on one such branch. ---
case "$BRANCH" in
  unattended/*) ;;
  *) finish error - branch "BOARD_BRANCH is '$BRANCH'; the runner commits on an unattended/* branch only" ;;
esac
CURRENT=$(git branch --show-current 2>/dev/null || echo "")
if [ "$CURRENT" != "$BRANCH" ]; then
  git fetch -q "$REMOTE" 2>/dev/null
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git switch -q "$BRANCH" || finish error - branch "cannot switch from '${CURRENT:-detached}' to $BRANCH (uncommitted changes?)"
  elif git show-ref --verify --quiet "refs/remotes/$REMOTE/$BRANCH"; then
    git switch -q -c "$BRANCH" --track "$REMOTE/$BRANCH" || finish error - branch "cannot create $BRANCH from $REMOTE/$BRANCH"
  else
    finish error - branch "the work branch $BRANCH exists neither here nor on $REMOTE; create it first"
  fi
  event "switched ${CURRENT:-detached} -> $BRANCH"
fi

# board_commit <message>: commit tasks/ and nothing else, on the work branch and nowhere else.
board_commit() {
  [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] \
    || finish error "${TASK_NAME:--}" branch "the checkout left $BRANCH; nothing was committed"
  local paths=(tasks/)   # and the sessions' files of the anomaly journal: a board move's entry goes with it (board 739)
  [ -d .engine/journal/anomalies ] && paths+=(.engine/journal/anomalies)
  git add -A -- "${paths[@]}" || return 1
  if git diff --cached --quiet -- "${paths[@]}"; then return 0; fi
  git commit -q -m "$1" -- "${paths[@]}" || return 1
  event "commit $(git rev-parse --short HEAD) $1"
}

# commit_journal <message>: commit the anomaly journal when it has uncommitted entries — since board 739
# each session's own file of it under .engine/journal/anomalies/, and tasks/ANOMALIES.md a fold wrote. It
# never stops anything: a journal that cannot be committed now is committed with the next change.
commit_journal() {
  local paths=() path
  for path in tasks/ANOMALIES.md .engine/journal/anomalies; do [ -e "$path" ] && paths+=("$path"); done
  [ "${#paths[@]}" -gt 0 ] || return 0
  [ -n "$(git status --porcelain -- "${paths[@]}" 2>/dev/null)" ] || return 0
  [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] || return 0
  git add -- "${paths[@]}" >> "$STATE/logs/git.log" 2>&1 \
    && git commit -q -m "$1" -- "${paths[@]}" >> "$STATE/logs/git.log" 2>&1 \
    && event "commit $(git rev-parse --short HEAD) journal"
  return 0
}
# What a hook, the gate or the agent wrote into the journal (board 035) is committed by the runner.
JOURNAL_OTHERS="board: anomaly journal — entries written by a hook, the gate or the agent"

# note_anomaly <task|-> <what happened> <what was done>: one entry of the anomaly journal (the
# session's own file of it, board 739), in a commit of its own.
note_anomaly() {
  commit_journal "$JOURNAL_OTHERS"
  board anomaly "$1" "$2" "$3" > /dev/null || return 0
  event "anomaly $1 $2"
  commit_journal "board: anomaly — ${1/#-/the board}: $2"
}

# critical <task|-> <reason-word> <one sentence> <what happened, for the journal>: the few things
# that stop the whole board. The journal entry is committed and pushed first when that is possible.
critical() {
  JOURNALED=1
  note_anomaly "$1" "$4" "task board зупинено (причина \`$2\`): це одна з небагатьох речей, які зупиняють усю task board. Після усунення причини runner-а треба запустити знову."
  [ "$2" = pull-conflict ] || push_branch quiet
  finish error "$1" "$2" "$3"
}

push_branch() {  # push_branch [quiet]: quiet = a failure is an event only, no journal entry
  [ "$PUSH" -eq 1 ] || return 0
  # Board 100: before every push of the work branch a number of the reviewed file that was written here in
  # the ordinary way (into the file, committed or not) is removed. The guard repairs; the check after it
  # looks at HEAD once more and withholds the push when the number is still there. Both judge HEAD of the
  # checkout: a session that works against them on purpose is outside what they hold (docs/engine-limits.md,
  # «The same Linux user»).
  reviewed_guard
  if ! board reviewed-clean --accepted "$REVIEWED_ACCEPTED" --known "$REMOTE/$BRANCH" >> "$STATE/logs/git.log" 2>&1; then
    event "push-withheld $(git rev-parse --short HEAD) reviewed"
    say "the branch is NOT pushed: its commit holds numbers of tasks/.reviewed that did not arrive from the owner, and they could not be removed"
    return 0
  fi
  if git push -q "$REMOTE" "$BRANCH" >> "$STATE/logs/git.log" 2>&1; then
    event "pushed $(git rev-parse --short HEAD)"
  else
    event "push-failed $(git rev-parse --short HEAD)"; say "push failed (see $STATE/logs/git.log); it is tried again after the next task"
    [ -n "${1:-}" ] || note_anomaly "${TASK_NAME:--}" "гілку не вдалося надіслати в $REMOTE (push відхилено або $REMOTE недосяжний)" "роботу продовжено; надсилання буде повторено після наступної задачі"
  fi
}

# Fetch and rebase onto the remote branch. A remote without the branch yet is not an error.
sync_branch() {
  git fetch -q "$REMOTE" >> "$STATE/logs/git.log" 2>&1 || { event "fetch-failed"; return 0; }
  git show-ref --verify --quiet "refs/remotes/$REMOTE/$BRANCH" || return 0
  if ! git pull -q --rebase --autostash "$REMOTE" "$BRANCH" >> "$STATE/logs/git.log" 2>&1; then
    git rebase --abort >> "$STATE/logs/git.log" 2>&1
    critical "${TASK_NAME:--}" pull-conflict "pull --rebase of $BRANCH from $REMOTE did not apply cleanly; the rebase was aborted, nothing is lost. Resolve it by hand, then start the runner again" \
      "конфлікт під час pull --rebase гілки $BRANCH з $REMOTE; runner його не розв'язав, rebase скасовано, нічого не втрачено"
  fi
}

# A question the gate put on the board is committed and pushed at once, by itself: the owner
# reads the branch, not this machine, and the task the agent was on may never close.
publish_gate_questions() {
  local -a fresh=()
  local path
  # An escalation opened during a rebase or a merge has no question yet (board 065): ask it now.
  CLAUDE_PROJECT_DIR="$PROJECT_ROOT" python3 "$GATE_PY" --ask-waiting >> "$STATE/logs/gate.log" 2>&1 || true
  while IFS= read -r path; do
    case "$path" in tasks/blocked/[0-9]*-gate-escalation-*.md) fresh+=("$path") ;; esac
  done < <(git ls-files --others --exclude-standard -- tasks/blocked)
  [ "${#fresh[@]}" -gt 0 ] || return 0
  [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] \
    || finish error "${TASK_NAME:--}" branch "the checkout left $BRANCH; nothing was committed"
  git add -- "${fresh[@]}" && git commit -q -m "board: the gate asks the owner — ${#fresh[@]} question(s) in blocked/" -- "${fresh[@]}" \
    || finish error "${TASK_NAME:--}" commit "cannot commit the gate's question"
  event "gate-question $(git rev-parse --short HEAD) ${fresh[*]}"
  push_branch
}

# The «так» answers that are in the checkout NOW and did not arrive from the owner earlier.
# Called before the pull: whatever it lists was written here, not by the owner.
local_gate_answers() {
  local line
  { board gate-answers; board owner-actions; } | while IFS= read -r line; do
    grep -qxF -- "$line" "$ACCEPTED" 2>/dev/null || echo "$line"
  done
}

# Act on the owner's «так» (exactly that one word, board 036) under an offered action. Run here, by the runner — never by an agent;
# owner_action.py holds the list of what may be run and refuses inside a Claude Code session.
owner_actions() {
  local name action arg sum line rc outcome path
  local -a rules
  while IFS=$'\t' read -r name action arg sum; do
    [ -n "$name" ] || continue
    line="$name"$'\t'"$action"$'\t'"$arg"$'\t'"$sum"
    if grep -qxF -- "$line" <<< "$LOCAL_ANSWERS"; then
      board action-reject "$name" || finish error - action "board.py action-reject $name failed"
      event "action-answer-rejected $action $name written-here"
      say "$name: an answer written on this machine is not the owner's; wiped and asked again"
      board_commit "board: ${name%.md} — an answer written on this machine is not the owner's; asked again" \
        || finish error - commit "cannot commit the rejected answer"
      continue
    fi
    echo "$line" >> "$ACCEPTED"
    python3 "$HERE/owner_action.py" --root "$PROJECT_ROOT" "$action" "$arg" >> "$STATE/logs/owner-action.log" 2>&1; rc=$?
    case "$rc" in
      0) outcome=applied ;;
      1) outcome=failed ;;
      3) outcome=stale ;;
      *) event "action-refused $action $name rc=$rc"
         say "$name: owner_action.py refused $action (see $STATE/logs/owner-action.log); the question stays in blocked/"
         continue ;;
    esac
    board action-done "$name" "$outcome" > /dev/null || finish error - action "board.py action-done $name failed"
    event "action-$outcome $action $name"
    say "${name%.md}: $action on the owner's answer — $outcome"
    if [ "$outcome" = applied ] && ! git diff --quiet -- .claude/settings.json; then
      [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] \
        || finish error - branch "the checkout left $BRANCH; nothing was committed"
      git commit -q -m "settings: the proposal docs/tasks/settings.json applied on the owner's answer (${name%.md})" -- .claude/settings.json \
        || finish error - commit "cannot commit the applied settings"
      event "commit $(git rev-parse --short HEAD) settings applied"
    fi
    case "$action" in promote-rule|reject-rule)
      rules=()
      for path in .engine/rules.md .engine/rule-proposals.md; do [ -f "$path" ] && rules+=("$path"); done
      if [ "$outcome" = applied ] && [ "${#rules[@]}" -gt 0 ] && git add -- "${rules[@]}" && ! git diff --cached --quiet -- "${rules[@]}"; then
        [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] \
          || finish error - branch "the checkout left $BRANCH; nothing was committed"
        git commit -q -m "rules: $action on the owner's answer (${name%.md})" -- "${rules[@]}" \
          || finish error - commit "cannot commit the rule"
        event "commit $(git rev-parse --short HEAD) $action"
      fi ;;
    esac
    board_commit "board: ${name%.md} — $action on the owner's answer: $outcome" \
      || finish error - commit "cannot commit the outcome of the action"
  done <<< "$(board owner-actions)"
}

# Act on the owner's «так». The command is run here, by the runner — never by an agent.
close_escalations() {
  local name stamp sum line rc
  while IFS=$'\t' read -r name stamp sum; do
    [ -n "$name" ] || continue
    line="$name"$'\t'"$stamp"$'\t'"$sum"
    if grep -qxF -- "$line" <<< "$LOCAL_ANSWERS"; then
      board gate-reject "$name" || finish error - gate "board.py gate-reject $name failed"
      event "escalation-answer-rejected $stamp $name written-here"
      say "$name: an answer written on this machine is not the owner's; wiped and asked again"
      board_commit "board: ${name%.md} — an answer written on this machine is not the owner's; asked again" \
        || finish error - commit "cannot commit the rejected answer"
      continue
    fi
    echo "$line" >> "$ACCEPTED"
    CLAUDE_PROJECT_DIR="$PROJECT_ROOT" python3 "$GATE_PY" --close-escalation "$stamp" >> "$STATE/logs/gate.log" 2>&1; rc=$?
    case "$rc" in
      0) board gate-done "$name" closed > /dev/null || finish error - gate "board.py gate-done $name failed" ;;
      1) board gate-done "$name" absent > /dev/null || finish error - gate "board.py gate-done $name failed" ;;
      *) event "escalation-close-refused $stamp $name rc=$rc"
         say "$name: gate.py refused to close $stamp (see $STATE/logs/gate.log); the question stays in blocked/"
         continue ;;
    esac
    event "escalation-closed $stamp $name$([ "$rc" -eq 1 ] && echo ' was-not-open')"
    say "${name%.md}: gate escalation $stamp closed on the owner's answer"
    board_commit "board: ${name%.md} → done — gate escalation $stamp closed on the owner's answer" \
      || finish error - commit "cannot commit the closed gate question"
  done <<< "$(board gate-answers)"
}

# A gate question nobody answered whose escalation is closed already — the owner ran
# `gate.py --close-escalation` in a terminal — asks nothing any more (board 035): it goes to done/
# with a two-line report and an entry in the journal, in one commit.
sweep_closed_questions() {
  local name stamp
  while IFS=$'\t' read -r name stamp; do
    [ -n "$name" ] || continue
    board gate-done "$name" elsewhere > /dev/null || finish error - gate "board.py gate-done $name failed"
    board anomaly "${name%.md}" "питання gates лежало в \`blocked/\` без відповіді, а його ескалацію $stamp уже закрито іншим шляхом (командою \`gate.py --close-escalation\` у терміналі)" \
      "runner сам прибрав питання з \`blocked/\` у \`done/${name%.md}/\` зі звітом; відповідати на нього вже не треба." > /dev/null
    event "gate-question-swept $stamp $name"
    say "${name%.md}: its escalation $stamp was closed another way; the question is removed from blocked/"
    board_commit "board: ${name%.md} → done — gate escalation $stamp was closed another way; the question is removed" \
      || finish error - commit "cannot commit the removed gate question"
  done <<< "$(board gate-closed)"
}

# reviewed_guard: «the owner looked it over» is a task's number in tasks/.reviewed, and it arrives
# from the owner only — in the branch or through the inbox (board 100). A number that is in the
# checkout and never arrived was written on this machine: it is removed, with a journal entry, and
# the task stays in the owner's review. Called before the pull and, from push_branch, before EVERY push
# of the work branch — the end of a task, a stop after an attempt, a gate's question: the review reads
# origin, so a number written in the ordinary way must not get there. A failure here stops the board with
# state=error; that stop goes through push_branch as well, where REVIEWED_GUARDING keeps the guard from
# running inside itself and `board reviewed-clean` looks at HEAD once more. This holds a mistaken or naive
# mark, not a session that sets out to get past it (docs/engine-limits.md, «The same Linux user»).
REVIEWED_GUARDING=0
reviewed_guard() {
  local wrong
  [ "$REVIEWED_GUARDING" -eq 0 ] || return 0
  REVIEWED_GUARDING=1
  wrong=$(board reviewed-reject --accepted "$REVIEWED_ACCEPTED" --known "$REMOTE/$BRANCH") || finish error - reviewed "board.py reviewed-reject failed"
  if [ -n "$wrong" ]; then
    event "reviewed-rejected $wrong"
    say "tasks/.reviewed: $wrong written on this machine, not by the owner; removed"
    board_commit "board: tasks/.reviewed — a number written on this machine is not the owner's; removed ($wrong)" \
      || finish error - commit "cannot commit the removed numbers of tasks/.reviewed"
  fi
  REVIEWED_GUARDING=0
}

# New task files and the owner's answers, each in a commit of its own.
intake() {
  local taken answered placed
  publish_gate_questions
  taken=$(board import-inbox "$INBOX") || finish error - inbox "board.py import-inbox failed"
  if [ -n "$taken" ]; then
    while IFS= read -r line; do event "inbox $line"; done <<< "$taken"
    board_commit "board: from the inbox — $(echo "$taken" | grep -vc ' skipped: ') file(s) taken" \
      || finish error - commit "cannot commit the inbox files"
  fi
  board reviewed-accept --accepted "$REVIEWED_ACCEPTED" || finish error - reviewed "board.py reviewed-accept failed"   # what the pull and the inbox brought is the owner's
  close_escalations
  sweep_closed_questions
  owner_actions
  answered=$(board unblock) || finish error - unblock "board.py unblock failed"
  if [ -n "$answered" ]; then
    board_commit "board: answered, back to todo — $(echo "$answered" | tr '\n' ' ')" \
      || finish error - commit "cannot commit the answered tasks"
  fi
  placed=$(board maintain-task) || finish error - maintain "board.py maintain-task failed"
  if [ -n "$placed" ]; then
    event "maintain-task $placed"
    board_commit "board: the weekly maintenance task — $placed" || finish error - commit "cannot commit the maintenance task"
  fi
}

# save_wip <stem> <reason>: what is uncommitted outside tasks/ becomes ONE commit on top of HEAD,
# on the branch wip/<stem>/<UTC>, pushed to the remote (board 035). Built in an index of its own:
# the checkout, its index and the work branch are not touched. Sets WIP to the branch (empty:
# nothing to save, or git refused) and WIP_AT to the remote that has it (empty: this machine only).
save_wip() {
  local stem="$1" index="$STATE/wip-index" tree commit
  WIP=""; WIP_AT=""
  [ -n "$(git status --porcelain --untracked-files=all -- . ':(exclude)tasks' 2>/dev/null)" ] || return 0
  rm -f "$index"
  tree=$(GIT_INDEX_FILE="$index" git read-tree HEAD 2>> "$STATE/logs/git.log" \
    && GIT_INDEX_FILE="$index" git add -A -- . ':(exclude)tasks' 2>> "$STATE/logs/git.log" \
    && GIT_INDEX_FILE="$index" git write-tree 2>> "$STATE/logs/git.log")
  rm -f "$index"
  commit=$([ -n "$tree" ] && git commit-tree "$tree" -p HEAD -m "wip: $stem — the uncommitted work the runner found when it parked the task ($2)" 2>> "$STATE/logs/git.log")
  WIP="wip/$stem/$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -z "$commit" ] || ! git branch "$WIP" "$commit" >> "$STATE/logs/git.log" 2>&1; then
    event "wip-failed $stem"; WIP=""; return 0
  fi
  if [ "$PUSH" -eq 1 ] && git push -q "$REMOTE" "refs/heads/$WIP:refs/heads/$WIP" >> "$STATE/logs/git.log" 2>&1; then
    WIP_AT="$REMOTE"; event "wip-pushed $WIP $(git rev-parse --short "$commit")"
  else
    event "wip-local $WIP $(git rev-parse --short "$commit")"
  fi
}

# park_task <stem> <reason> <detail>: the runner gives up on this task, not on the board (board 021).
# What the agent left uncommitted outside tasks/ goes to a wip branch on the remote and into a
# stash, both named in the task file; the task goes to blocked/ with the reason and a question;
# the journal gets its entry; one commit.
park_task() {
  local stem="$1" reason="$2" detail="$3" stash="" before after
  local -a verdicts=()
  [ "$reason" != three-blocks ] || verdicts=(--verdicts "$(blocks_marker "$stem")")
  [ "$reason" != reader-blocks ] || verdicts=(--verdicts "$(reader_marker "$stem")")
  commit_journal "$JOURNAL_OTHERS"
  save_wip "$stem" "$reason"
  before=$(git rev-parse -q --verify refs/stash 2>/dev/null)
  git stash push -q -u -m "board: $stem parked ($reason)" -- . ':(exclude)tasks' >> "$STATE/logs/git.log" 2>&1
  after=$(git rev-parse -q --verify refs/stash 2>/dev/null)
  [ "$after" != "$before" ] && stash="$after"
  board park "$stem" "$reason" --detail "$detail" ${stash:+--stash "$stash"} ${WIP:+--wip "$WIP"} ${WIP_AT:+--wip-remote "$WIP_AT"} "${verdicts[@]}" > /dev/null \
    || finish error "$stem" park "board.py park $stem $reason failed"
  rm -f "$(blocks_marker "$stem")" "$(reader_marker "$stem")"
  [ "$reason" = budget ] && memo rebudget "$stem"
  board_commit "board: $stem → blocked — the runner parked it ($reason); the board goes on" \
    || finish error "$stem" commit "cannot commit the parked task"
  event "task-parked $stem $reason${stash:+ stash=$stash}${WIP:+ wip=$WIP}"
  say "$stem: parked in blocked/ ($reason)${WIP:+; uncommitted work kept in the branch $WIP (${WIP_AT:-this machine only})}${stash:+; stash $stash}"
  OUTCOME=blocked
}

# guard_session <stem>: the guarded files after an agent's session (board 724) — the constitution,
# the settings, .engine/rules.md, migrations, CI workflows. The deny hooks and the Stop gate work
# inside the session and only while its hooks are whole; a turn can be cut short, and a changed
# settings file would steer the NEXT session. So the runner compares with what it saw before the
# session: a file that differs is put back (protected_guard.py: a patch of the discarded change,
# the anomaly journal), and the task goes to blocked/ with a question — sets PROTECTED to the
# files for run_task, which parks it (GUARD_PARKS=1); from any other caller, and for a task that
# already left doing/, the question is an item of its own. What the runner saw before the session
# is held in GUARD_BEFORE. On the ordinary way nothing is passed over in silence: no snapshot —
# no session; a file that could not be put back, or a check that broke, stops the whole board.
# A change the agent also COMMITTED leaves the restored file different from HEAD, and only the
# runner may commit a guarded file: it does, in a commit of its own.
guard_session() {
  local stem="$1" rc list found
  local -a pending=()
  PROTECTED=$(python3 "$GUARD_PY" --root "$PROJECT_ROOT" after <<< "$GUARD_BEFORE" 2>> "$STATE/logs/protected.log"); rc=$?
  list=$(echo "$PROTECTED" | tr '\n' ' ' | sed 's/ $//')
  # Fail closed: only "nothing differs" (0) and "put back" (3) let the board go on. A file that could not be put
  # back (4) and a check that broke (anything else) both mean the next session might start on changed settings.
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
    critical "$stem" protected "the guarded files could not be checked or put back after the session of $stem (protected_guard.py after: exit $rc${list:+; files: $list}; see $STATE/logs/protected.log). Look at them by hand, then start the runner again: it compares once more with the record it kept ($GUARD_KEPT)" \
      "після сесії агента охоронювані файли не вдалося перевірити або повернути до стану перед сесією (\`protected_guard.py after\`: код $rc${list:+; файли: $list})"
  fi
  [ "$rc" -eq 3 ] || PROTECTED=""
  found=$(python3 "$GUARD_PY" --root "$PROJECT_ROOT" pending <<< "$GUARD_BEFORE" 2>> "$STATE/logs/protected.log") \
    || critical "$stem" protected "protected_guard.py pending failed after the session of $stem (see $STATE/logs/protected.log); look at the guarded files by hand, then start the runner again" \
      "після сесії агента не вдалося з'ясувати, чи змінив її commit охоронювані файли (\`protected_guard.py pending\`)"
  while IFS= read -r list; do [ -z "$list" ] || pending+=("$list"); done <<< "$found"
  if [ "${#pending[@]}" -gt 0 ]; then
    [ "$(git branch --show-current 2>/dev/null)" = "$BRANCH" ] && git add -A -- "${pending[@]}" 2>> "$STATE/logs/git.log" \
      && git commit -q -m "protected: ${pending[*]} put back as before the session of $stem — a commit of the session had changed it" -- "${pending[@]}" >> "$STATE/logs/git.log" 2>&1 \
      || critical "$stem" protected "a commit of the session of $stem changed guarded files (${pending[*]}); they are put back in the working tree, but the runner could not commit that. Commit it by hand, then start the runner again" \
        "commit сесії агента змінив охоронювані файли (${pending[*]}); у робочому дереві їх повернуто, але закомітити повернення runner не зміг"
    event "commit $(git rev-parse --short HEAD) protected-restored ${pending[*]}"
    note_anomaly "$stem" "commit сесії агента змінив охоронювані файли: ${pending[*]}" "файли повернуто до стану перед сесією, і runner закомітив це повернення окремим commit-ом"
  fi
  [ -n "$PROTECTED" ] || return 0
  list=$(echo "$PROTECTED" | tr '\n' ' ' | sed 's/ $//')
  event "protected-restored $stem $list"
  say "$stem: the session changed guarded files ($list); put back, the discarded change kept as a patch"
  if [ "$GUARD_PARKS" -eq 1 ] && [ "$(board where "$stem")" = "doing" ]; then return 0; fi   # run_task parks it
  board open-item --to blocked --key "protected-$stem" --source runner \
    --title "Сесія задачі $stem змінила охоронювані файли" \
    --what "Сесія агента в задачі $stem змінила охоронювані файли ($list), і gates цього не зупинили. Runner повернув їх до стану перед сесією; відкинуту зміну збережено латкою в .claude/state/gate/protected/discarded/ (на сервері runner-а; точний шлях — у журналі аномалій)." \
    --question "Що робити зі зміною охоронюваних файлів ($list), яку зробила сесія задачі $stem? Варіанти: (а) нічого — файли вже повернуто, напишіть «закрити»; (б) зміна потрібна — напишіть, яка саме, агент подасть її пропозицією (docs/tasks/settings.json) на ваше «так». Порада: (а), якщо ви цієї зміни не просили." > /dev/null \
    || event "protected-question-failed $stem"
  board_commit "board: $stem — the session changed guarded files ($list); put back, a question to the owner" \
    || finish error "$stem" commit "cannot commit the question about the guarded files"
  PROTECTED=""
}

# trust_check <stem>: claude said in the session's stderr that the workspace is not trusted, so the
# `allow` list of the settings is not applied (board 791). Nobody reads that log: the runner puts it
# into the anomaly journal — once a project, the marker in the state directory says it is there — and
# into the summary of every run in which a session said it. The work goes on.
trust_check() {
  local said
  said=$(grep -m1 'this workspace has not been trusted' "$OUT.err" 2>/dev/null) || return 0
  [ -n "$UNTRUSTED_LOG" ] || UNTRUSTED_LOG="${OUT#"$PROJECT_ROOT"/}.err"
  event "untrusted-workspace $1"
  [ ! -e "$UNTRUSTED_NOTED" ] || return 0
  now > "$UNTRUSTED_NOTED"
  note_anomaly "$1" "теку проєкту не позначено довіреною: сесія агента написала в stderr (\`${OUT#"$PROJECT_ROOT"/}.err\`) «$(printf '%s' "$said" | cut -c1-300)» — список \`allow\` з \`.claude/settings.json\` у такій теці не діє" \
    "роботу продовжено (сесія йде з \`--permission-mode auto\`). Власникові: відкрити Claude Code в теці проєкту один раз і прийняти trust dialog. Запис робиться один раз на проєкт; поки тека не довірена, про це каже підсумок кожного запуску runner-а."
}

# attempt <stem> <prompt of a fresh conversation> <prompt of a continued one>: one claude session
# for the task, booked in costs.json. Sets NOTE to `limit`, `auth` or nothing (board_state.py)
# and OUT to the file that holds the session's output.
attempt() {
  local stem="$1" session n before after
  local -a flags=(--settings .claude/settings.json --permission-mode auto --output-format json)
  [ -z "$MAX_USD" ] || flags+=(--max-budget-usd "$(memo get "$stem" left "$MAX_USD")")
  session=$(memo get "$stem" session)
  n=$(( $(memo get "$stem" attempts) + 1 ))
  OUT="$STATE/logs/$stem-$n.json"
  before=$(git rev-parse HEAD)
  status running "$stem"
  event "attempt $stem $n ${session:+resume=$session}"
  # No snapshot, no session: an unguarded session is not started. The comparison after the session
  # is made from this variable; the copy in $GUARD_KEPT is for a runner that dies before it gets there.
  GUARD_BEFORE=$(python3 "$GUARD_PY" --root "$PROJECT_ROOT" before 2>> "$STATE/logs/protected.log") && [ -n "$GUARD_BEFORE" ] \
    && printf '%s\n%s\n' "$stem" "$GUARD_BEFORE" > "$GUARD_KEPT.new" && mv -f "$GUARD_KEPT.new" "$GUARD_KEPT" \
    || critical "$stem" protected "the guarded files could not be recorded before a session of $stem (protected_guard.py before failed, or its record could not be kept; see $STATE/logs/protected.log); no session was started. Put that right, then start the runner again" \
      "перед сесією агента не вдалося записати стан охоронюваних файлів (\`protected_guard.py before\`); сесію не запущено"
  if [ -z "$session" ]; then
    "$CLAUDE_BIN" -p "$2" "${flags[@]}" < /dev/null > "$OUT" 2> "$OUT.err" &
  else
    "$CLAUDE_BIN" -p "$3" --resume "$session" "${flags[@]}" < /dev/null > "$OUT" 2> "$OUT.err" &
  fi
  CLAUDE_PID=$!
  wait "$CLAUDE_PID"
  CLAUDE_PID=""
  after=$(git rev-parse HEAD)
  NOTE=$(memo record "$stem" "$OUT" "$([ "$before" != "$after" ] && echo 1 || echo 0)")
  event "attempt-end $stem $n cost=$(memo get "$stem" cost) commit=$([ "$before" != "$after" ] && echo yes || echo no)${NOTE:+ $NOTE}"
  trust_check "$stem"
  guard_session "$stem"
  rm -f "$GUARD_KEPT"   # compared; a comparison that stopped the board left it for the next start
  publish_gate_questions
  commit_journal "$JOURNAL_OTHERS"
}

# stop_after_attempt <stem>: the soft stop between attempts (board 035). The task stays in doing/
# with its conversation, its clock and its count; what the attempts committed is pushed; what is
# uncommitted stays in the working tree for the next start, which continues the conversation.
stop_after_attempt() {
  [ -f "$STOP_ATTEMPT_FLAG" ] || return 0
  push_branch
  finish stopped "$1" stop-after-attempt "a stop was asked for (--stop-after-attempt); no attempt is running, the task stays in doing/ and the next start continues it"
}

# The paths `git status` shows as uncommitted, one a line, sorted.
dirty_paths() { git -c core.quotePath=false status --porcelain --untracked-files=all | cut -c4- | LC_ALL=C sort -u; }
# …of them, those that were not there when the task was started: the task's own.
task_leftovers() { LC_ALL=C comm -23 <(dirty_paths) <(LC_ALL=C sort -u "$DIRTY_BEFORE" 2>/dev/null); }

# close_clean <stem>: the agent closed its task; the tree must be clean now (board 029). If the
# task left uncommitted files, the agent gets the turn back once to commit or remove them; what is
# still there afterwards is listed in the anomaly journal. Nothing is deleted here.
close_clean() {
  local stem="$1" left shown count turn="агентові один раз повернуто хід із проханням закомітити те, що належить задачі, або прибрати зайве — дерево лишилося брудним"
  left=$(task_leftovers)
  [ -n "$left" ] || return 0
  count=$(wc -l <<< "$left" | tr -d ' ')
  event "dirty-tree $stem $count file(s)"
  say "$stem: closed with $count uncommitted file(s); the agent is asked once to commit or remove them"
  shown=$(head -n 40 <<< "$left")
  [ "$count" -le 40 ] || shown+=$'\n'"… and $((count - 40)) more (see git status)"
  local ask="The task $stem is closed (it is in tasks/$OUTCOME/), but it left the working tree dirty. git status still shows these uncommitted files:
$shown
Commit what belongs to this task (through .claude/unattended/commit_checkpoint.sh, on this branch) and remove what is not needed, so that git status is clean. Do nothing else: do not reopen the task, do not start another one, do not push. You are asked this once; whatever is still uncommitted after this turn is written into the anomaly journal as it is."
  while :; do
    if [ -n "$MAX_USD" ] && [ "$(memo get "$stem" left "$MAX_USD")" = "0.00" ]; then
      turn="хід агентові не повернуто: бюджет задачі ($MAX_USD USD) вичерпано"; break
    fi
    attempt "$stem" "$ask" "$ask"
    [ "$NOTE" = "limit" ] || break
    status waiting-limit "$stem"
    say "usage limit; waiting $LIMIT_WAIT s"
    sleep "$LIMIT_WAIT"
  done
  board_commit "board: $stem → $OUTCOME (changes under tasks/ left uncommitted by the cleaning turn)" \
    || finish error "$stem" commit "cannot commit the leftover changes under tasks/"
  left=$(task_leftovers)
  if [ -z "$left" ]; then event "dirty-tree-cleaned $stem"; return 0; fi
  count=$(wc -l <<< "$left" | tr -d ' ')
  event "dirty-tree-left $stem $count file(s)"
  note_anomaly "$stem" "задачу закрито (\`$OUTCOME/\`), але в робочому дереві лишилися її незакомічені файли: $count" \
    "$turn. Runner нічого не видаляв і не комітив і взяв наступну задачу. Файли: $(sed 's/.*/`&`/' <<< "$left" | paste -sd, - | sed 's/,/, /g')."
}

# check_minimum <stem>: the agent closed its task into done/; the minimum of its mode must be there
# (board 098: `mode.py check-close`, by files — report.md; in соло a PASS of the overseer on every
# commit with working code; without working code the reader's PASS on the report, board 100; in конвеєр
# also the feature artifact and sealed slice contracts). If it is
# not (exit 1), the agent gets the turn back once with what is missing; still missing afterwards — the
# task goes to blocked/ with the reason `minimum`. Any other exit (3: the check broke) is an anomaly
# and the task stays in done/ — never a park, never a stop.
check_minimum() {
  local stem="$1" missing rc
  [ "$OUTCOME" = done ] || return 0
  missing=$(python3 "$HERE/../hooks/mode.py" --root "$PROJECT_ROOT" check-close "$stem" 2>/dev/null); rc=$?
  [ "$rc" -eq 0 ] && return 0
  if [ "$rc" -ne 1 ]; then
    note_anomaly "$stem" "мінімум режиму задачі не перевірено: \`mode.py check-close\` відповів кодом $rc" "задачу лишено в \`done/\`; runner узяв наступну"
    return 0
  fi
  event "minimum-missing $stem"
  say "$stem: closed without the minimum of its mode; the agent is asked once to make it"
  local ask="The task $stem is in tasks/done/, but the minimum of its mode is not there (python3 .claude/hooks/mode.py check-close $stem):
$missing
Make what is missing — for a commit of working code with no PASS, get the overseer's audit of that code (claim the unit, as tasks/README.md and the engine rules say); for a task that changed no working code, the reader's PASS on its report (python3 .claude/hooks/reader.py request $stem --report, then the agent reader with the line it prints; after a BLOCK fix the documents and ask again); for конвеєр, the feature artifact and the seal of every slice contract — and commit it (through .claude/unattended/commit_checkpoint.sh, on this branch). Keep the task in tasks/done/; if it cannot be made without the owner, move the task to tasks/blocked/ with your question instead. Do not push. You are asked this once; if the minimum is still missing afterwards, the task goes to blocked/."
  while :; do
    if [ -n "$MAX_USD" ] && [ "$(memo get "$stem" left "$MAX_USD")" = "0.00" ]; then break; fi
    attempt "$stem" "$ask" "$ask"
    [ "$NOTE" = "limit" ] || break
    status waiting-limit "$stem"
    say "usage limit; waiting $LIMIT_WAIT s"
    sleep "$LIMIT_WAIT"
  done
  board_commit "board: $stem — what the minimum turn left uncommitted under tasks/" \
    || finish error "$stem" commit "cannot commit the leftover changes under tasks/"
  OUTCOME=$(board where "$stem")
  [ "$OUTCOME" = done ] || return 0
  missing=$(python3 "$HERE/../hooks/mode.py" --root "$PROJECT_ROOT" check-close "$stem" 2>/dev/null); rc=$?
  [ "$rc" -eq 0 ] && { event "minimum-made $stem"; return 0; }
  if [ "$rc" -ne 1 ]; then
    note_anomaly "$stem" "мінімум режиму задачі не перевірено після ходу назад: \`mode.py check-close\` відповів кодом $rc" "задачу лишено в \`done/\`; runner узяв наступну"
    return 0
  fi
  park_task "$stem" minimum "$(sed -n '2,$p' <<< "$missing" | sed 's/^- //' | paste -sd ';' - | sed 's/;/; /g')"
}

# run_task <tasks/doing/NAME.md>: attempts until the task left doing/ — moved by the agent to
# done/ or blocked/, or parked in blocked/ by the runner. Sets OUTCOME to done, blocked or missing.
# wait_task <stem>: the task met the weekly cap on extra sessions and went back to todo/ to wait for
# the sum to fall (board 110). Not parked: no question, no blocked/. What it left uncommitted
# outside tasks/ is kept the way a parked task's is — a wip branch and a stash, named in the journal.
wait_task() {
  local stem="$1" stash="" before after
  commit_journal "$JOURNAL_OTHERS"
  save_wip "$stem" extra-cap
  before=$(git rev-parse -q --verify refs/stash 2>/dev/null)
  git stash push -q -u -m "board: $stem waits (extra-cap)" -- . ':(exclude)tasks' >> "$STATE/logs/git.log" 2>&1
  after=$(git rev-parse -q --verify refs/stash 2>/dev/null)
  [ "$after" != "$before" ] && stash="$after"
  if [ -n "$WIP$stash" ]; then
    note_anomaly "$stem" "задача повернулась у \`todo/\` чекати тижневої межі додаткових сесій (\`EXTRA_SESSIONS_WEEK_USD\`) і лишила незакомічену роботу" \
      "роботу збережено${WIP:+: гілка \`$WIP\` (${WIP_AT:-лише на сервері})}${stash:+; git stash \`$stash\` на сервері}; задача чекає в \`todo/\`, runner узяв наступну"
  fi
  event "task-waiting $stem extra-cap${stash:+ stash=$stash}${WIP:+ wip=$WIP}"
  say "$stem: waits in todo/ for the weekly sum of extra sessions${WIP:+; uncommitted work kept in the branch $WIP (${WIP_AT:-this machine only})}"
  OUTCOME=waiting
}

run_task() {
  local file="$1" stem place
  stem=$(basename "$file" .md)
  local first="You are working from the task board, unattended: nobody will answer a question in this conversation. Your task is the file $file. Read tasks/README.md (the section «Правила для агента») and follow it. If work on this task has already begun (see git log and the working tree), continue it instead of starting over. The task is finished only when you have moved it to tasks/done/$stem/ (task.md and report.md) or, if it cannot proceed without the owner, to tasks/blocked/ with your questions, and committed that. Do not push. If the usage limit runs out, just end the turn; you will be continued."
  local mode
  mode=$(python3 "$HERE/../hooks/mode.py" --root "$PROJECT_ROOT" show --task "$file" 2>/dev/null) || mode=""   # board 097: the task's mode, from its one reader
  [ -z "$mode" ] || first+=" The task's mode, as python3 .claude/hooks/mode.py show reads it: $mode"
  local again="Continue the task $file from where you stopped. It is finished only when it is in tasks/done/$stem/ (task.md and report.md) or in tasks/blocked/ with your questions, and that is committed."
  while :; do
    place=$(board where "$stem")
    case "$place" in
      done|blocked) OUTCOME="$place"; CLOSED_BY=agent; return 0 ;;
      doing) stop_after_attempt "$stem" ;;
      todo)
        if board extra-waits "$stem"; then wait_task "$stem"; else park_task "$stem" returned ""; fi
        return 0 ;;
      *) note_anomaly "$stem" "задача зникла з task board: її немає ні в doing/, ні в done/, ні в blocked/, ні в todo/" "runner узяв наступну задачу; файл задачі можна повернути з історії git"
         OUTCOME=missing; return 0 ;;
    esac
    if [ -f "$(blocks_marker "$stem")" ]; then
      park_task "$stem" three-blocks ""; return 0
    fi
    if [ -f "$(reader_marker "$stem")" ]; then   # board 099, 100: three readers in a row refused the sketch's record or the task's report
      park_task "$stem" reader-blocks "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("record", ""))' "$(reader_marker "$stem")" 2>/dev/null)"; return 0
    fi
    if [ "$(memo get "$stem" age_sec)" -ge "$TASK_MAX" ]; then
      park_task "$stem" deadline "$((TASK_MAX / 3600))"; return 0
    fi
    if [ "$(memo get "$stem" idle)" -ge "$STALL_ATTEMPTS" ]; then
      park_task "$stem" no-commit "$STALL_ATTEMPTS"; return 0
    fi
    if [ -n "$MAX_USD" ] && [ "$(memo get "$stem" left "$MAX_USD")" = "0.00" ]; then
      park_task "$stem" budget "$MAX_USD"; return 0
    fi
    GUARD_PARKS=1; attempt "$stem" "$first" "$again"; GUARD_PARKS=0
    if [ -n "$PROTECTED" ]; then   # board 724: the session changed a guarded file and the task is still open
      park_task "$stem" protected "$(echo "$PROTECTED" | tr '\n' ' ' | sed 's/ $//')"; return 0
    fi
    if [ "$NOTE" = "auth" ] && [ "$(board where "$stem")" = "doing" ]; then
      critical "$stem" logged-out "claude is logged out (see $OUT); the task stays in doing/. Log in on this machine (claude, then /login), then start the runner again" \
        "claude розлогінився: сесія відповіла лише проханням увійти; задача лишилась у doing/"
    fi
    [ "$(board where "$stem")" != "doing" ] || stop_after_attempt "$stem"   # asked for during the attempt: no wait, no pause
    if [ "$NOTE" = "limit" ] && [ "$(board where "$stem")" = "doing" ]; then
      status waiting-limit "$stem"
      say "usage limit; waiting $LIMIT_WAIT s"
      sleep "$LIMIT_WAIT"
      continue
    fi
    [ "$(board where "$stem")" = "doing" ] && sleep "$PAUSE"
  done
}

event "start pid=$$ branch=$BRANCH once=$ONCE push=$PUSH${MAX_USD:+ max_usd=$MAX_USD}"
TASK_NAME="-"
FINISHED=0
# Board 724: the previous runner died while a session ran (a reboot, a kill) or stopped on a
# comparison it could not make — the guarded files were never compared with what it saw before
# that session. Compared now, before the first pull (what a pull brings is the owner's) and before
# any session: otherwise a file the dead runner's session changed would be the next `before`.
if [ -s "$GUARD_KEPT" ]; then
  TASK_NAME=$(head -n 1 "$GUARD_KEPT"); GUARD_BEFORE=$(tail -n +2 "$GUARD_KEPT")
  event "protected-leftover $TASK_NAME"
  guard_session "$TASK_NAME"
  rm -f "$GUARD_KEPT"
  GUARD_BEFORE=""; TASK_NAME="-"
fi
while :; do
  LOCAL_ANSWERS=$(local_gate_answers)
  reviewed_guard
  commit_journal "$JOURNAL_OTHERS"
  sync_branch
  # What the pull brought is the owner's — recorded before anything pushes again (a gate's question in intake).
  board reviewed-accept --accepted "$REVIEWED_ACCEPTED" || finish error - reviewed "board.py reviewed-accept failed"
  intake
  TASK=$(board next); RC=$?
  case "$RC" in
    0) ;;
    3|4|5)
      PLACED=$(board cleanup-task) || finish error - cleanup "board.py cleanup-task failed"
      if [ -n "$PLACED" ]; then
        event "cleanup-task $PLACED"
        board anomaly "$(basename "$PLACED" .md)" "task board вільна: runner-у нема чого брати (\`todo/\` порожня, або все, що лишилося, чекає власника чи його присутності)" \
          "runner сам поклав задачу прибирання \`$PLACED\` і взяв її: нічний режим simplifier-а, безпечне застосовується, решта — у звіт для власника. Наступна така — не раніше ніж за добу (\`CLEANUP_EVERY_DAYS\`)." > /dev/null \
          || event "anomaly-failed cleanup-task $PLACED"   # the journal never stops the board; the task is placed all the same
        board_commit "board: nothing to take — the cleanup task $PLACED" || finish error - commit "cannot commit the cleanup task"
        continue
      fi
      push_branch
      if [ "$RC" -eq 5 ]; then
        finish idle - extra-cap "what is left are tasks with extra sessions, and the extra sessions of the last seven days are at the cap (EXTRA_SESSIONS_WEEK_USD): they wait in tasks/todo/ until the sum falls, nobody is asked ($FINISHED task(s) closed in this run)"
      fi
      HOLD=$(board gate-hold)
      if [ "$RC" -eq 4 ] && [ -n "$HOLD" ]; then   # board 301: every session would end in a BLOCK
        finish waiting-owner - gate-escalation "the gate escalation $HOLD covers all work: until the owner closes it no OVERSEER_PASS is accepted, so no new task is started ($FINISHED task(s) closed in this run)"
      fi
      if [ "$RC" -eq 4 ] || [ -n "$(find tasks/blocked -maxdepth 1 -name '[0-9]*.md' 2>/dev/null | head -1)" ]; then
        finish waiting-owner - owner "nothing can move: what is left waits for the owner's answers, for the owner's presence or for tasks that are not done ($FINISHED task(s) closed in this run)"
      fi
      finish idle - todo-empty "tasks/todo/ is empty ($FINISHED task(s) closed in this run)"
      ;;
    *) finish error - board "board.py next refused (two tasks in tasks/doing/?); see its message above" ;;
  esac
  TASK_NAME=$(basename "$TASK" .md)
  case "$TASK" in
    tasks/todo/*)
      TASK=$(board start "$TASK") || finish error "$TASK_NAME" start "board.py start refused"
      board_commit "board: $TASK_NAME → doing" || finish error "$TASK_NAME" commit "cannot commit the move to doing/"
      dirty_paths > "$DIRTY_BEFORE"
      rm -f "$(blocks_marker "$TASK_NAME")" "$(reader_marker "$TASK_NAME")"   # a fresh start: a marker from before the owner's answer is stale
      memo retry "$TASK_NAME"
      ;;
    *) memo begin "$TASK_NAME" ;;
  esac
  OUTCOME=""; CLOSED_BY=""
  run_task "$TASK"
  # The agent moved the task but left the move uncommitted: commit tasks/, nothing else.
  board_commit "board: $TASK_NAME → $OUTCOME (the move was left uncommitted)" \
    || finish error "$TASK_NAME" commit "cannot commit the leftover changes under tasks/"
  [ "$CLOSED_BY" != agent ] || close_clean "$TASK_NAME"
  [ "$CLOSED_BY" != agent ] || check_minimum "$TASK_NAME"
  rm -f "$DIRTY_BEFORE"
  memo finish "$TASK_NAME" "$OUTCOME"
  event "task-$OUTCOME $TASK_NAME cost=$(memo get "$TASK_NAME" cost)"
  say "$TASK_NAME: $OUTCOME ($(memo get "$TASK_NAME" cost) USD)"
  [ "$OUTCOME" = waiting ] || FINISHED=$((FINISHED + 1))
  reviewed_guard   # with --no-push as well: the checkout does not keep the number either
  push_branch
  if [ "$ONCE" -eq 1 ]; then
    finish stopped "$TASK_NAME" once "one task was asked for (--once); it ended in $OUTCOME/"
  fi
  if [ -f "$STOP_FLAG" ]; then
    finish stopped "$TASK_NAME" stop-after-task "a stop was asked for (--stop-after-task); the task ended in $OUTCOME/ and no other was started"
  fi
  if [ -f "$STOP_ATTEMPT_FLAG" ]; then
    finish stopped "$TASK_NAME" stop-after-attempt "a stop was asked for (--stop-after-attempt); the attempt in hand closed the task ($OUTCOME/) and no other was started"
  fi
  TASK_NAME="-"
done
