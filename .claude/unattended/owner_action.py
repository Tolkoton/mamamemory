#!/usr/bin/env python3
"""The actions board-runner.sh may take on the owner's word — and it takes no other (board 008).

    owner_action.py [--root DIR] apply-settings <sha256>
    owner_action.py [--root DIR] promote-rule <sha256>
    owner_action.py [--root DIR] reject-rule <sha256>
    owner_action.py [--root DIR] amend-goals <sha256>
    owner_action.py [--root DIR] seal-goals <sha256>
    owner_action.py [--root DIR] update-deps <sha256>

`apply-settings` is the one way the shared settings change, in the engine's repository and in
every project it is installed into (board 038): settings_check.py, which ships with the engine,
judges the proposal docs/tasks/settings.json against the live file; a sound proposal is copied
over .claude/settings.json; and a project that keeps a test of its own in
tests/test_settings_proposal.py (the engine's repository does) has it run on the result.
`<sha256>` is the proposal the owner said «так» to (the agent wrote it under its question,
board.py `action-line`); a proposal that changed since is not the one that was approved and is
not applied. A refused proposal is never copied; a red test puts the previous file back.

`promote-rule` is the one way a lesson becomes a rule (board 040): the owner answered «так» under
a rule question, whose offer names the sha256 of the proposal's id and the exact rule text. The
PROPOSED proposal with that sha256 is promoted into .engine/rules.md by lesson_queue.promote,
which looks for the owner's answer itself; a proposal whose text changed since the question is
stale. `reject-rule` is the owner's «ні»: the proposal is marked REJECTED.

`amend-goals` is the one way an approved goals document changes without the owner's terminal
(board 051): the owner answered «так» under a question that offers the sha256 of the proposed
document `.engine/goals/proposed.md`. goals.py checks that it is a lawful amendment of the sealed
`.engine/goals.md` (no number dropped or reused, the version raised), puts it in its place, seals
it, and lists every decision that cited a changed line in `.engine/goals/to-review.md`.

`seal-goals` is the one way a goals document gets its first seal with nobody in the conversation
(board 787): the owner answered «так» under a question that offers the sha256 of `.engine/goals.md`
itself. goals.py seals that document as it is — a document that changed since the question is
stale, one no decision could cite (no numbered line, a number used twice) or one approved before
(that is `amend-goals`) is not sealed. The seal is machine state: nothing is left to commit.

`update-deps` is the one way the engine changes a project's packages (board 076): the owner
answered «так» under the question that ends a `/maintain` task, which lists the patches and minor
versions of `.engine/maintain/updates.json` and offers its sha256. A list that changed since is
not the one the owner saw: stale. The command is the project's own, `DEPS_UPDATE_CMD` in
`.claude/project.env`, run with one argument per dependency (`DEPS_UPDATE_SPEC`, by default
`{name}=={version}`). Only a patch or a minor version is updated — the class is computed again
from the two versions, so a major version in the list is skipped and reported. The checks must be
green before anything is touched; then the patches go as one group and every minor version alone,
each followed by the full gate (`gate.py --layer ci`: lint, types, the full tests, no worse than
the snapshot "as it was") and a commit of its own. An update the command or the gate refused is
rolled back (the files from git, then `DEPS_RESTORE_CMD` when the project names one, to bring the
installed packages back to the files); a group of patches that failed is tried again one by one.
What was updated, what was rolled back and with which output is written to
`.engine/maintain/update-result.md`, in a commit of its own. Commits are made on an `unattended/*`
branch only: a hook does not see a commit made from a script, so the check is here.

An agent may not edit .claude/settings.json (protect-paths.sh) and may not get there through
this script either: it refuses inside a Claude Code session, as gate.py --close-escalation does.
A hook sees the command an agent types, never one run from a script, so the check is here.

Exit 0: applied (or the live file already was the proposal). 1: the check refused the proposal
(the live file untouched) or the test went red (the previous file is back). 2: refused — inside a session, or not an action of the list. 3: stale — the
proposal is missing or is not the one the sha256 names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROPOSAL = "docs/tasks/settings.json"
LIVE = ".claude/settings.json"
CHECK = "settings_check.py"  # beside this file: it ships with the engine
TEST = "tests/test_settings_proposal.py"  # the project's own, when it keeps one
UPDATES = ".engine/maintain/updates.json"
UPDATE_RESULT = ".engine/maintain/update-result.md"
OUTSIDE_TASKS = (".", ":(exclude)tasks")  # the runner commits tasks/ itself
UPDATE_TIMEOUT_S = 900
EXIT_FAILED, EXIT_REFUSED, EXIT_STALE = 1, 2, 3


def apply_settings(root: Path, approved: str) -> int:
    proposal, live, test = root / PROPOSAL, root / LIVE, root / TEST
    if not (proposal.is_file() and live.is_file()):
        print(f"owner-action: apply-settings needs {PROPOSAL} and {LIVE}; one is missing", file=sys.stderr)
        return EXIT_STALE
    wanted = proposal.read_bytes()
    found = hashlib.sha256(wanted).hexdigest()
    if found != approved:
        print(f"owner-action: {PROPOSAL} is {found}, the owner approved {approved or '(no sha256)'}; not applied", file=sys.stderr)
        return EXIT_STALE
    check = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / CHECK), "--root", str(root)], capture_output=True, text=True, check=False)
    print(check.stdout[-2000:] + check.stderr[-2000:])
    if check.returncode != 0:
        print(f"owner-action: {CHECK} refused the proposal (exit {check.returncode}); {LIVE} is untouched", file=sys.stderr)
        return EXIT_FAILED
    if not test.is_file():
        live.write_bytes(wanted)
        print(f"owner-action: {PROPOSAL} ({found}) applied to {LIVE}; {CHECK} passes")
        return 0
    before = live.read_bytes()
    live.write_bytes(wanted)
    ran = subprocess.run([sys.executable, str(test)], cwd=root, capture_output=True, text=True, check=False)
    print(ran.stdout[-2000:] + ran.stderr[-2000:])
    if ran.returncode != 0:
        live.write_bytes(before)
        print(f"owner-action: {TEST} failed after the copy (exit {ran.returncode}); the previous {LIVE} is back", file=sys.stderr)
        return EXIT_FAILED
    print(f"owner-action: {PROPOSAL} ({found}) applied to {LIVE}; {CHECK} and {TEST} pass")
    return 0


def lessons() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    import lesson_queue

    return lesson_queue


def promote_rule(root: Path, approved: str) -> int:
    queue = lessons()
    ident = queue.proposal_by_sha(root, approved)
    if ident is None:
        print(f"owner-action: no PROPOSED rule proposal has the sha256 {approved or '(none)'}; the owner approved another text", file=sys.stderr)
        return EXIT_STALE
    done, message = queue.promote(root, ident)
    print(f"owner-action: {message}", file=sys.stdout if done else sys.stderr)
    return 0 if done else EXIT_FAILED


def reject_rule(root: Path, declined: str) -> int:
    queue = lessons()
    ident = queue.proposal_by_sha(root, declined)
    if ident is None:
        print(f"owner-action: no PROPOSED rule proposal has the sha256 {declined or '(none)'}; nothing to close", file=sys.stderr)
        return EXIT_STALE
    done, message = queue.reject(root, ident, "ні (the owner's answer on the task board)")
    print(f"owner-action: {message}", file=sys.stdout if done else sys.stderr)
    return 0 if done else EXIT_FAILED


def amend_goals(root: Path, approved: str) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    import goals

    return goals.amend(root, approved, in_session=False)  # main() has already refused a session


def seal_goals(root: Path, approved: str) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    import goals

    return goals.first_seal(root, approved, in_session=False)  # main() has already refused a session


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


def tail(out: str, lines: int = 40) -> str:
    return "\n".join(out.strip().splitlines()[-lines:]) or "(порожній вивід)"


def gate_check(root: Path) -> tuple[bool, str]:
    """The full gate on the tree as it is: lint, types and the full tests, no worse than the snapshot.
    A gate that ran no tests has checked nothing an update could break: that is a refusal too."""
    gate = Path(__file__).resolve().parent.parent / "hooks" / "gate.py"
    ran = subprocess.run([sys.executable, str(gate), "--layer", "ci"], cwd=root, capture_output=True, text=True, check=False,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})
    if ran.returncode != 0:
        return False, tail(ran.stdout + ran.stderr)
    try:
        steps = json.loads((root / ".claude/state/gate/last-report.json").read_text(encoding="utf-8"))["timings_ms"]["steps"]
    except (OSError, ValueError, KeyError):
        steps = {}
    return (True, "") if "tests" in steps else (False, "gates не запускали тестів: у проєкті немає команди тестів, тож оновлення нічим перевірити")


def untracked(root: Path) -> set[str]:
    return set(git(root, "ls-files", "--others", "--exclude-standard", "--", *OUTSIDE_TASKS).stdout.splitlines())


def roll_back(root: Path, before: set[str], restore: str) -> str:
    """Put the files back as the last commit has them and remove the files the update created;
    then the project's own command brings the installed packages back to the files."""
    git(root, "reset", "-q", "--", *OUTSIDE_TASKS)
    changed = git(root, "diff", "--name-only", "HEAD", "--", *OUTSIDE_TASKS).stdout.splitlines()
    if changed:
        git(root, "checkout", "-q", "HEAD", "--", *changed)
    for rel in untracked(root) - before:
        (root / rel).unlink(missing_ok=True)
    if not restore:
        return "файли повернуто з git; `DEPS_RESTORE_CMD` порожня — встановлені пакети команда оновлення могла лишити новішими за файли"
    ran = subprocess.run(["bash", "-c", restore], cwd=root, capture_output=True, text=True, check=False)
    return f"файли повернуто з git; `{restore}` — код завершення {ran.returncode}"


def update_group(root: Path, env: dict[str, str], group: list[dict[str, str]], kind: str, log: list[str]) -> int:
    """Update one group, check it, commit it — or roll it back. Returns how many were updated."""
    spec = env.get("DEPS_UPDATE_SPEC", "").strip() or "{name}=={version}"
    names = ", ".join(f"`{d['name']}` {d['current']} → {d['latest']}" for d in group)
    before = untracked(root)
    try:
        ran = subprocess.run(["bash", "-c", env["DEPS_UPDATE_CMD"] + ' "$@"', "update-deps", *(spec.format(name=d["name"], version=d["latest"]) for d in group)],
                             cwd=root, capture_output=True, text=True, check=False, timeout=UPDATE_TIMEOUT_S)
        ok, out = ran.returncode == 0, ran.stdout + ran.stderr
        why = f"команда оновлення завершилась з кодом {ran.returncode}"
    except subprocess.TimeoutExpired:
        ok, out, why = False, "", f"команда оновлення не відповіла за {UPDATE_TIMEOUT_S} с"
    if ok:
        ok, out = gate_check(root)
        why = "після оновлення gates «не гірше» червоні"
    if not ok:
        restored = roll_back(root, before, env.get("DEPS_RESTORE_CMD", "").strip())
        if len(group) > 1:
            log.append(f"- група латок ({names}) — СКАСОВАНО: {why}; {restored}. Далі кожна з них окремо.")
            return sum(update_group(root, env, [dep], kind, log) for dep in group)
        log += [f"- {names} — СКАСОВАНО: {why}; {restored}. Вивід:", "  ```", *("  " + line for line in tail(out).splitlines()), "  ```"]
        return 0
    git(root, "add", "-A", "--", *OUTSIDE_TASKS)
    if git(root, "diff", "--cached", "--quiet", "--", *OUTSIDE_TASKS).returncode == 0:
        log.append(f"- {names} — команда пройшла, перевірки зелені, але жодного файла проєкту вона не змінила: commit-а немає.")
        return len(group)
    plain = ", ".join(f"{d['name']} {d['current']} → {d['latest']}" for d in group)
    done = git(root, "commit", "-q", "-m", f"deps: {plain} — {kind} updated on the owner's answer; the full gate is green", "--", *OUTSIDE_TASKS)
    if done.returncode != 0:
        restored = roll_back(root, before, env.get("DEPS_RESTORE_CMD", "").strip())
        log.append(f"- {names} — СКАСОВАНО: commit не вдався ({tail(done.stderr, 3)}); {restored}.")
        return 0
    log.append(f"- {names} — оновлено, перевірки зелені, commit `{git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}`.")
    return len(group)


def update_deps(root: Path, approved: str) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    import complexity_budget
    import maintain

    path = root / UPDATES
    if not path.is_file():
        print(f"owner-action: update-deps needs {UPDATES}; it is missing", file=sys.stderr)
        return EXIT_STALE
    found = hashlib.sha256(path.read_bytes()).hexdigest()
    if found != approved:
        print(f"owner-action: {UPDATES} is {found}, the owner approved {approved or '(no sha256)'}; nothing is updated", file=sys.stderr)
        return EXIT_STALE
    if not git(root, "branch", "--show-current").stdout.strip().startswith("unattended/"):
        print("owner-action: update-deps commits every update, and commits are made on an unattended/* branch only", file=sys.stderr)
        return EXIT_REFUSED
    deps = maintain.read_updates(path.read_text(encoding="utf-8"))
    env = complexity_budget.project_env(root)
    log: list[str] = []

    def result(code: int, summary: str) -> int:
        target = root / UPDATE_RESULT
        head = f"Перелік: `{UPDATES}` ({approved}). Написав `owner_action.py update-deps` — runner за відповіддю власника «так»."
        target.write_text("\n".join(["# Оновлення залежностей: що вийшло", "", head, "", summary, "", *log, ""]), encoding="utf-8")
        git(root, "add", "--", UPDATE_RESULT)
        git(root, "commit", "-q", "-m", "maintain: the result of update-deps on the owner's answer", "--", UPDATE_RESULT)
        print(f"owner-action: update-deps — {summary} ({UPDATE_RESULT})", file=sys.stdout if code == 0 else sys.stderr)
        return code

    if deps is None:
        return result(EXIT_FAILED, f"Нічого не оновлено: `{UPDATES}` не читається як перелік оновлень.")
    if not env.get("DEPS_UPDATE_CMD", "").strip():
        return result(EXIT_FAILED, "Нічого не оновлено: `DEPS_UPDATE_CMD` у `.claude/project.env` порожня.")
    dirty = git(root, "status", "--porcelain", "--untracked-files=all", "--", *OUTSIDE_TASKS).stdout.strip()
    if dirty:
        return result(EXIT_FAILED, "Нічого не оновлено: у робочому дереві є незакомічені зміни, і невдале оновлення не було б чим скасувати:\n```\n" + tail(dirty, 20) + "\n```")
    green, out = gate_check(root)
    if not green:
        return result(EXIT_FAILED, "Нічого не оновлено: перевірки не зелені ще до оновлень, тож зламане оновлення не відрізнити від старої біди:\n```\n" + out + "\n```")
    for dep in deps:
        if dep["kind"] not in maintain.UPDATABLE:
            log.append(f"- `{dep['name']}` {dep['current']} → {dep['latest']} — НЕ ОНОВЛЮВАЛОСЬ: це не латка і не мала версія "
                       f"({maintain.KIND_WORDS.get(dep['kind'], 'версія не новіша')}); велика версія — завжди окрема задача.")
    patches = [d for d in deps if d["kind"] == "patch"]
    updated = update_group(root, env, patches, "patch", log) if patches else 0
    updated += sum(update_group(root, env, [dep], "minor", log) for dep in deps if dep["kind"] == "minor")
    return result(0, f"Оновлено {updated} з {len(deps)}.")


ACTIONS = {"apply-settings": apply_settings, "promote-rule": promote_rule, "reject-rule": reject_rule, "amend-goals": amend_goals,
           "seal-goals": seal_goals, "update-deps": update_deps}


def main() -> int:
    parser = argparse.ArgumentParser(description="The actions the board runner takes on the owner's word.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("action")
    parser.add_argument("argument", nargs="?", default="")
    args = parser.parse_args()
    if os.environ.get("CLAUDECODE"):
        print("owner-action: the owner's actions are refused inside a Claude Code session (CLAUDECODE is set). "
              "The board runner takes them, started from the owner's terminal or service.", file=sys.stderr)
        return EXIT_REFUSED
    if args.action not in ACTIONS:
        print(f"owner-action: '{args.action}' is not an allowed action ({', '.join(sorted(ACTIONS))})", file=sys.stderr)
        return EXIT_REFUSED
    return ACTIONS[args.action](args.root.resolve(), args.argument.strip("-"))


if __name__ == "__main__":
    sys.exit(main())
