#!/usr/bin/env python3
"""PreToolUse hook for Bash. Turns an ask-gated command into a PARK when
nobody is in the loop, and decides every push by environment.

WHY THIS EXISTS
---------------
settings.json's `permissions.ask` list is correct policy: a publish, a
dependency change, a `gh` state change genuinely needs a human, because it
spends money or changes shared state. But its MECHANISM is an interactive
permission prompt. Unattended that prompt is answered by nobody, so the whole
run hangs on one command instead of parking one item and continuing.

PreToolUse runs BEFORE permission evaluation, so denying here preempts the
prompt and hands the reason back to the agent, which parks the item and moves
on. Attended, this hook does nothing for those commands and the normal prompt
fires as designed.

THIS DOES NOT WEAKEN THE ASK LIST. The command still does not run. The
difference is that the agent gets a reason it can act on instead of a dialog
nobody will close.

PUSH, BY ENVIRONMENT (board 603, owner decision)
------------------------------------------------
`git push` is no longer on the ask list of the settings file: a rule there
prompts in every environment, and no hook can lift it (a hook's "allow" does
not override an ask rule), so a cloud session stopped on every push of its own
branch. The rule lives here now, and the push is found anywhere in the
command — after a separator, behind `git -C <dir>`, inside `bash -c`, `sh -c`
or `eval`:

  environment                                      | decision
  -------------------------------------------------+-------------------------------
  unattended (the board runner; the mode file or   | deny: the runner sends the
  CLAUDE_UNATTENDED_SESSION=1)                     | branch itself
  cloud (CLAUDE_CODE_REMOTE=true) with             | allow for `git push [-u] origin
  CLOUD_COMMIT_POLICY="session-branch"             | <the checked-out claude/ branch>`
                                                   | (or HEAD) as the whole command;
                                                   | none for it inside a longer one
                                                   | (an allow approves the whole
                                                   | call); deny, with the reason, for
                                                   | any other push
  local with the owner, or a cloud session with    | ask: the owner confirms, as the
  the switch off                                   | ask rule made them before

A forced push, the deletion of a remote branch and a push into main or stable
are refused by block-dangerous.sh in every environment, whatever this hook
says; in the cloud this hook refuses them too, being no allowed form.

WHY PYTHON AND NOT BASH
-----------------------
`jq` is NOT installed on every machine that runs this template — verified
absent on the authoring machine 2026-08-27. Every hook that parses its stdin
with `jq` degrades to a silent no-op there, because the idiom in use is
`jq ... 2>/dev/null || echo ""` followed by an empty-value early exit. A
security hook that silently does nothing is worse than no hook, so this one
uses the standard library only. See .claude/references/hooks.md.

Exit codes: 0 with JSON on stdout = decision; 0 with no stdout = allow.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Mirrored from .claude/settings.json permissions.ask. Keep in sync: an entry
# here that is NOT in the ask list would block work that should merely prompt.
# `git push` left the list (board 603): PUSH below decides it, in every
# environment (tests/test_push_by_environment.py checks the mirror).
ASK_GATED = [
    r"^\s*git\s+rebase(\s|$)",
    r"^\s*git\s+merge(\s|$)",
    r"^\s*git\s+cherry-pick(\s|$)",
    r"^\s*git\s+revert(\s|$)",
    # The project's own manager (uv/poetry/npm/yarn/pnpm/cargo/go/bundle add/remove) left the
    # list (board 302): the engineer picks the packages. What stays installs outside the
    # project's manifest and lock file.
    r"(^|\s)pip\s+(install|uninstall)(\s|$)",
    r"(^|\s)pipx\s+(install|uninstall)(\s|$)",
    r"(^|\s)npm\s+(install|i)\s+(.*\s)?(-g|--global)(\s|$)",
    r"(^|\s)pnpm\s+add\s+(.*\s)?(-g|--global)(\s|$)",
    r"(^|\s)yarn\s+global(\s|$)",
    r"(^|\s)docker\s+push(\s|$)",
    r"(^|\s)gh\s+pr\s+(create|merge)(\s|$)",
    r"(^|\s)gh\s+release(\s|$)",
    r"(^|\s)gh\s+repo\s+(create|delete)(\s|$)",
    r"(^|\s)gem\s+install(\s|$)",
]
ASK_GATED_RE = [re.compile(p) for p in ASK_GATED]

REASON_TEMPLATE = (
    "Ask-gated command in an unattended run: {cmd!r}. This needs a human — it "
    "spends money or changes shared state — and no human is in the loop "
    "(.claude/state/overseer/mode says unattended). Do NOT retry and do NOT work "
    "around it. Put it before the owner as a task of the board: `python3 "
    ".claude/unattended/board.py open-item --to blocked --title <what the command "
    "is for> --what <the exact command above, and what waits for it> --question "
    "<what you ask the owner> --source 'hook park-ask-gated.py'` (a project "
    "without tasks/: a PARKED entry through `python3 .claude/hooks/journal.py add parked` instead), then "
    "continue with the next unblocked item. Blocked by "
    ".claude/hooks/park-ask-gated.py; attended, this same command would simply "
    "prompt."
)

# --- push (board 603) ---------------------------------------------------------------------
PUSH_UNATTENDED_REASON = (
    "A push in an unattended run: {cmd!r}. Nobody is watching this session, and the board "
    "runner sends the branch itself when the task ends (tasks/README.md, the rules for the "
    "agent). Do NOT retry and do NOT work around it: commit with "
    ".claude/unattended/commit_checkpoint.sh and continue. Blocked by "
    ".claude/hooks/park-ask-gated.py (board 603)."
)
PUSH_CLOUD_REASON = (
    "Push refused in a cloud session: {why}. Command: {cmd!r}. A cloud session "
    "(CLAUDE_CODE_REMOTE=true, CLOUD_COMMIT_POLICY=\"session-branch\") pushes one thing without "
    "asking: its own checked-out claude/ branch to origin — `git push -u "
    "origin <that branch>` (or HEAD). Any other push from the cloud — another branch or remote, "
    "unattended/*, main, stable, --all, tags, a forced push, a deletion — is the owner's: ask "
    "them. If the push was only quoted — a message, a grep pattern — put that text in single "
    "quotes without a shell or interpreter in the same command, or in a file. "
    "Blocked by .claude/hooks/park-ask-gated.py (board 603)."
)
PUSH_UNREAD_REASON = (
    "A push this hook could not read: {cmd!r}. Unattended or in a cloud session it is refused, "
    "with the owner it asks. Blocked by .claude/hooks/park-ask-gated.py (board 603)."
)
PUSH_CLOUD_ALLOWED = (
    "The cloud session's own claude/ branch to origin: allowed without a question (board 603, "
    "the owner's decision; .claude/hooks/park-ask-gated.py)."
)
PUSH_ASK_REASON = (
    "A push needs the owner's confirmation: {cmd!r}. The rule moved from the ask list of "
    ".claude/settings.json into .claude/hooks/park-ask-gated.py (board 603); a forced push, the "
    "deletion of a remote branch and a push into main or stable are refused by "
    "block-dangerous.sh whatever the answer."
)

CLOUD_BRANCH_PREFIX = "claude/"
CLOUD_REMOTE = "origin"
# Options a cloud push may carry: they change what is printed or checked, never what is sent.
CLOUD_PUSH_OPTIONS = {"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose", "--progress",
                      "--no-progress", "-n", "--dry-run", "--porcelain"}
# git's own options that take the next word as their value (as block-dangerous.sh reads them).
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
# What ends a simple command once quotes are gone; `$(`, a backtick, a group, a pipe all count.
SEPARATORS = re.compile(r"[;&|()`\n]")
# A redirection with its target (`2>&1`, `>/dev/null`, `> log`): no word of the push, and its `&`
# would otherwise read as a separator.
REDIRECTION = re.compile(r"(?<![\w-])\d*(?:&>>?|>>?&?|<&?|>\|)\s*(?P<target>&?\d+\b|-|[^\s;&|()`<>]+)")
# A redirection that only joins or drops output: the one kind an explicit allow may carry.
QUIET_TARGET = re.compile(r"^(?:&?\d+|-|/dev/null)$")
GIT_ASSIGNMENT = re.compile(r"(^|[^\w$])GIT_\w*=")
POLICY_LINE = re.compile(r"""^[ \t]*CLOUD_COMMIT_POLICY=["']?([A-Za-z-]*)["']?""", re.MULTILINE)


@dataclass
class Push:
    """One `git … push` of the command: the words before `git` in its simple command, git's own
    options, the directory it runs in (a `cd` before it, then `git -C`; None when a variable or a
    substitution names it), and the words after `push`."""

    before: list[str]
    directory: str | None
    options: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)


def project_dir() -> Path:
    env_val = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_val:
        return Path(env_val).resolve()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0:
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.cwd()


def is_unattended(root: Path) -> bool:
    """True only when nobody is watching, as the one reader says (mode.py, board 097): the runner's
    CLAUDE_UNATTENDED_SESSION=1, or .claude/state/overseer/mode saying `unattended`. Absent,
    unreadable, or the reader missing -> attended, which is the safe default: the normal
    permission prompt fires and a human decides."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import mode

        return mode.unattended(root)[0]
    except ImportError:
        return False


def cloud_push_allowed(root: Path) -> bool:
    """A cloud session (CLAUDE_CODE_REMOTE=true) whose project switched CLOUD_COMMIT_POLICY in
    .claude/project.env to session-branch. The key is read, never sourced: a hook does not run
    a project file."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return False
    try:
        text = (root / ".claude" / "project.env").read_text(encoding="utf-8")
    except OSError:
        return False
    found = POLICY_LINE.findall(text)
    return bool(found) and found[-1] == "session-branch"


def judged_text(cmd: str) -> str:
    """The command with the text nothing runs emptied (shell_text.py, board 738): a push quoted
    in a commit message is not a push. The raw command when that cannot be done."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import shell_text  # a sibling module, found only once the path is set

        return shell_text.judged(cmd) or cmd
    except Exception:  # noqa: BLE001 — judge the raw command, which only finds more
        return cmd


def within(base: str | None, target: str) -> str | None:
    """`target` (a `cd` or `git -C` argument) seen from `base`; None when it cannot be read."""
    if not target or "$" in target or target == "-":
        return None
    path = Path(os.path.expanduser(target))
    if path.is_absolute():
        return str(path)
    return None if base is None else str(Path(base) / path)


def is_git(word: str) -> bool:
    return word == "git" or word.endswith("/git")


def simple_commands(text: str) -> list[list[str]]:
    """The words of every simple command of the judged text, as block-dangerous.sh reads them:
    quotes dropped — so what `bash -c`, `sh -c` or `eval` would run reads as typed —
    redirections dropped, split at every separator."""
    bare = REDIRECTION.sub(" ", text.replace('"', "").replace("'", ""))
    return [segment.split() for segment in SEPARATORS.split(bare) if segment.split()]


def pushes(text: str, base: str) -> list[Push]:
    """Every `git … push` of the judged command: in any simple command, git's own options
    skipped, a `cd` before it moving where it runs. `git stash push` is not one."""
    found: list[Push] = []
    here: str | None = base
    for words in simple_commands(text):
        if "cd" in words and not any(is_git(w) for w in words):   # `cd x`; `bash -c cd x` unquoted
            k = len(words) - 1 - words[::-1].index("cd")
            here = within(here, words[k + 1]) if k + 1 < len(words) else os.path.expanduser("~")
            continue
        for i, word in enumerate(words):
            if not is_git(word):
                continue
            push = Push(before=words[:i], directory=here)
            j = i + 1
            while j < len(words) and words[j].startswith("-"):
                push.options.append(words[j])
                if words[j] == "-C":
                    push.directory = within(push.directory, words[j + 1] if j + 1 < len(words) else "")
                j += 2 if words[j] in GIT_VALUE_OPTIONS else 1
            if j < len(words) and words[j] == "push":
                push.args = words[j + 1:]
                found.append(push)
    return found


def only_pushes(text: str, found: list[Push]) -> bool:
    """The command is nothing but its pushes (and a `cd`, `2>&1`, `>/dev/null`): an explicit allow
    approves the whole call, so it is given only when there is nothing else in it to approve."""
    plain = [words for words in simple_commands(text) if words[0] != "cd"]
    quiet = all(QUIET_TARGET.match(m.group("target"))
                for m in REDIRECTION.finditer(text.replace('"', "").replace("'", "")))
    return (quiet and len(plain) == len(found) and all(is_git(words[0]) for words in plain)
            and not any(p.before for p in found))


def checked_out(directory: str) -> str:
    """The branch checked out in `directory`; empty when none is, or it is no repository."""
    try:
        r = subprocess.run(["git", "-C", directory, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def short(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


def cloud_refusal(push: Push) -> str:
    """Why this push may not go from a cloud session; empty for the one allowed form."""
    assignment = next((w for w in push.before if "=" in w), "")
    if assignment:
        return f"an assignment before git ({assignment}) can redirect the push"
    other = [o for o in push.options if o != "-C"]
    if other:
        return f"git's own option {other[0]} can change where the push goes"
    unknown = [a for a in push.args if a.startswith("-") and a not in CLOUD_PUSH_OPTIONS]
    if unknown:
        return f"the option {unknown[0]} (a cloud push may carry only -u, -q, -v, --progress, --dry-run)"
    named = [a for a in push.args if not a.startswith("-")]
    if len(named) != 2:
        return ("the remote and exactly one branch are not named (a bare push follows configuration "
                "this hook cannot see)")
    remote, refspec = named
    if remote != CLOUD_REMOTE:
        return f"the remote {remote} is not {CLOUD_REMOTE}"
    if push.directory is None:
        return "the directory the push runs in is named by a variable or a substitution"
    branch = checked_out(push.directory)
    if not branch:
        return "no branch is checked out where the push runs"
    if not branch.startswith(CLOUD_BRANCH_PREFIX):
        return f"the checked-out branch {branch} is not the session's own {CLOUD_BRANCH_PREFIX} branch"
    source, colon, destination = refspec.partition(":")
    if short(source) not in (branch, "HEAD", "@"):
        return f"the refspec {refspec} does not send the checked-out branch {branch}"
    if colon and short(destination) != branch:
        return f"the refspec {refspec} sends {branch} into another branch ({destination or 'a deletion'})"
    return ""


def push_decision(cmd: str, root: Path, base: str) -> tuple[str, str] | None:
    """(decision, reason) for a command with a push in it; None when it holds none, or when it is
    the cloud session's own push inside a longer command, which the settings decide."""
    text = judged_text(cmd)
    found = pushes(text, base)
    if not found:
        return None
    if is_unattended(root):
        return "deny", PUSH_UNATTENDED_REASON.format(cmd=cmd)
    if cloud_push_allowed(root):
        assignment = GIT_ASSIGNMENT.search(text)
        if assignment:
            return "deny", PUSH_CLOUD_REASON.format(
                why="a GIT_* variable set in the same command can redirect the push", cmd=cmd)
        for push in found:
            why = cloud_refusal(push)
            if why:
                return "deny", PUSH_CLOUD_REASON.format(why=why, cmd=cmd)
        # Allowed. Said explicitly, so that neither a prompt nor the auto mode's classifier stops
        # it — but only for a command that holds nothing else; otherwise the settings decide.
        return ("allow", PUSH_CLOUD_ALLOWED) if only_pushes(text, found) else None
    return "ask", PUSH_ASK_REASON.format(cmd=cmd)


def emit(decision: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — cannot read the call: do not decide, never fail closed here
        # Cannot read the call -> do not decide. The ask prompt still fires;
        # this hook only ever converts a prompt into a park, never the reverse.
        sys.exit(0)

    cmd = ""
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        sys.exit(0)

    root = project_dir()
    base = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else str(root)
    try:
        push = push_decision(cmd, root, base)
    except Exception:  # noqa: BLE001 — a push this hook failed to read is never let through unasked
        push = None
        if re.search(r"\bgit\b.*\bpush\b", cmd):
            strict = is_unattended(root) or cloud_push_allowed(root)
            push = ("deny" if strict else "ask", PUSH_UNREAD_REASON.format(cmd=cmd))
    if push:
        emit(*push)

    if not is_unattended(root):
        sys.exit(0)

    for rx in ASK_GATED_RE:
        if rx.search(cmd):
            emit("deny", REASON_TEMPLATE.format(cmd=cmd))

    sys.exit(0)


if __name__ == "__main__":
    main()
