#!/usr/bin/env python3
"""bugfix.py — the mechanical proof of a bug fix, and the same check the other way round.

    python3 .claude/hooks/bugfix.py prove --test tests/test_x.py --cmd "pytest tests/test_x.py" \\
            [--record .engine/bugs/NNN-name.md | --base COMMIT] [--expect "text of the symptom"]
    python3 .claude/hooks/bugfix.py pins  --test tests/test_x.py --cmd "pytest tests/test_x.py" [--base COMMIT]

WHY. "The test really failed before the fix" was a claim of the builder, which the overseer
checked against the records. Here a program checks it, and it costs seconds (board 074).

PROVE. Two throwaway copies of the project, both outside it:
  before  the code of the base commit (`git archive`), with the files named by `--test` laid
          over it as they are in the working tree. `--cmd` MUST FAIL here.
  after   the working tree as it is: every file git tracks or would track (ignored files are in
          neither copy). `--cmd` MUST PASS here.
The base is `--base`, else `base_commit` of the record's "## Complexity budget" section (the
commit the bug fix began from), else HEAD. Refused, exit 1: the test passes without the fix; it
fails with the fix too; nothing but the test differs from the base (there is no fix); the
command could not run (exit 126 or 127) or ran out of time — that is not a failing test; with
`--expect`, the failing output does not contain that text — the test fails, but not for the
reason the bug record names.

PINS. The delete guard's first way through (.claude/references/gate.md): a test that pins what
the code does today passes on the code BEFORE the change. One copy — the base (default HEAD)
with the `--test` files over it — and `--cmd` must pass there.

`--cmd` runs through `bash -c` in the copy; it should run the new test and nothing else — a whole
suite fails for reasons of its own. The copy is a clean checkout: a command that needs an
environment must create it (docs/engine-limits.md). Nothing in the project is written.

Exit: 0 proved / pinned, 1 refused, 2 the check could not be made (usage, no such commit or file).
Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 300
TAIL_LINES = 15
CANNOT_RUN = (126, 127)
BASE_RE = re.compile(r"^[-*\s`]*base_commit:\s*`?([0-9A-Za-z_./~^-]+)", re.MULTILINE)
BUDGET_RE = re.compile(r"^##\s+Complexity budget\s*$(.*?)(?=^## |\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)


class CannotCheck(Exception):
    """The check itself could not be made; nothing is said about the test."""


@dataclass
class Run:
    code: int | None  # None: ran out of time
    output: str

    @property
    def passed(self) -> bool:
        return self.code == 0

    @property
    def failed(self) -> bool:
        """A test that ran and failed — not a command that never started or never ended."""
        return self.code is not None and self.code != 0 and self.code not in CANNOT_RUN

    def exit(self) -> str:
        return "no exit (time limit)" if self.code is None else f"exit {self.code}"

    def tail(self) -> str:
        lines = self.output.strip().splitlines()[-TAIL_LINES:]
        return "\n".join(f"    | {line}" for line in lines) or "    | (no output)"


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


def project_root(given: str | None) -> Path:
    start = given or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    top = git(Path(start), "rev-parse", "--show-toplevel")
    if top.returncode != 0 or not top.stdout.strip():
        raise CannotCheck(f"{start} is not inside a git repository")
    return Path(top.stdout.strip())


def base_of_record(root: Path, record: str) -> str:
    try:
        body = (root / record).read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotCheck(f"the bug record {record} cannot be read: {exc}") from exc
    budget = BUDGET_RE.search(body)
    found = BASE_RE.search(budget.group(1)) if budget else None
    if not found:
        raise CannotCheck(f"{record} has no base_commit in its '## Complexity budget' section")
    return found.group(1)


def resolve_base(root: Path, base: str | None, record: str | None) -> str:
    wanted = base or (base_of_record(root, record) if record else "HEAD")
    sha = git(root, "rev-parse", "--verify", "--quiet", f"{wanted}^{{commit}}")
    if sha.returncode != 0:
        raise CannotCheck(f"'{wanted}' is not a commit in this repository")
    return sha.stdout.strip()


def test_files(root: Path, given: list[str]) -> list[str]:
    """The `--test` paths, relative to the root; each must be a file of the working tree."""
    found = []
    for name in given:
        try:
            path = (root / name).resolve()
        except RuntimeError:  # a symlink loop, up to Python 3.12
            path = root / name
        if not path.is_file() or not path.is_relative_to(root.resolve()):
            raise CannotCheck(f"the test file {name} is not a file of this project")
        found.append(path.relative_to(root.resolve()).as_posix())
    return found


def tree_files(root: Path) -> list[str]:
    """Every file git tracks or would track that exists in the working tree."""
    listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [rel for rel in listed.stdout.split("\0") if rel and (root / rel).is_file()]


def copy_files(root: Path, files: list[str], target: Path) -> None:
    for rel in files:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target / rel, follow_symlinks=False)


def checkout(root: Path, sha: str, target: Path) -> None:
    archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", sha], capture_output=True, check=False)
    if archive.returncode != 0 or subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=False).returncode != 0:
        raise CannotCheck(f"the code of {sha[:7]} could not be checked out into a temporary copy")


def the_fix(root: Path, sha: str, tests: list[str]) -> list[str]:
    """What differs from the base apart from the test files: the fix itself."""
    changed = set(git(root, "diff", "--name-only", "-z", sha).stdout.split("\0"))
    changed |= set(git(root, "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0"))
    return sorted(changed - set(tests) - {""})


def run_in(copy: Path, command: str, timeout: int) -> Run:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env |= {"CLAUDE_PROJECT_DIR": str(copy), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        done = subprocess.run(["bash", "-c", command], cwd=copy, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return Run(None, partial)
    return Run(done.returncode, done.stdout)


def run_before(root: Path, sha: str, tests: list[str], command: str, timeout: int, tmp: Path) -> Run:
    """The base commit with the test files of the working tree laid over it."""
    copy = tmp / "before"
    copy.mkdir()
    checkout(root, sha, copy)
    copy_files(root, tests, copy)
    return run_in(copy, command, timeout)


def run_after(root: Path, command: str, timeout: int, tmp: Path) -> Run:
    copy = tmp / "after"
    copy.mkdir()
    copy_files(root, tree_files(root), copy)
    return run_in(copy, command, timeout)


def not_a_test_run(run: Run, where: str, timeout: int) -> str | None:
    """Why this run says nothing about the test; None when the test really ran."""
    if run.code is None:
        return f"the command did not finish within the time limit of {timeout} s on {where}"
    if run.code in CANNOT_RUN:
        return f"the command could not run on {where} ({run.exit()}): that is not a failing test"
    return None


def refused(reason: str, *runs: tuple[str, Run]) -> int:
    print(f"REFUSED: {reason}")
    for label, run in runs:
        print(f"  {label}: {run.exit()}\n{run.tail()}")
    return 1


def cmd_prove(root: Path, args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mode  # the task's mode (board 097): a fix is never made in quarantine

    forbidden = mode.refusal(root, "bugfix")
    if forbidden:
        print(f"REFUSED: {forbidden}")
        return 1
    sha = resolve_base(root, args.base, args.record)
    tests = test_files(root, args.test)
    fix = the_fix(root, sha, tests)
    if not fix:
        return refused(f"there is no fix: nothing but the test differs from {sha[:7]}. If the fix is already "
                       "committed, name the commit it began from (--base, or --record with its base_commit).")
    tmp = Path(tempfile.mkdtemp(prefix="bugfix-prove-"))
    try:
        before = run_before(root, sha, tests, args.cmd, args.timeout, tmp)
        shown = [("before the fix", before)]
        problem = not_a_test_run(before, "the code before the fix", args.timeout)
        if problem:
            return refused(f"{problem}. This is not a proof.", *shown)
        if before.passed:
            return refused("the test passes on the code before the fix — it does not catch this bug. This is not a proof.", *shown)
        if args.expect and args.expect not in before.output:
            return refused(f"the test fails on the code before the fix, but not for the expected reason: «{args.expect}» "
                           "is not in its output. This is not a proof.", *shown)
        after = run_after(root, args.cmd, args.timeout, tmp)
        shown.append(("with the fix", after))
        if not after.passed:
            why = not_a_test_run(after, "the code with the fix", args.timeout) or "the test still fails on the code with the fix"
            return refused(f"{why}. This is not a proof.", *shown)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"PROVED: {', '.join(tests)} fails on {sha[:7]} and passes on the working tree"
          + (f"; the failure shows «{args.expect}»" if args.expect else ""))
    print(f"  command: {args.cmd}")
    print(f"  the fix: {', '.join(fix)}")
    for label, run in shown:
        print(f"  {label}: {run.exit()}\n{run.tail()}")
    return 0


def cmd_pins(root: Path, args: argparse.Namespace) -> int:
    sha = resolve_base(root, args.base, None)
    tests = test_files(root, args.test)
    tmp = Path(tempfile.mkdtemp(prefix="bugfix-prove-"))
    try:
        before = run_before(root, sha, tests, args.cmd, args.timeout, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shown = ("before the change", before)
    problem = not_a_test_run(before, "the code before the change", args.timeout)
    if problem:
        return refused(f"{problem}. It pins nothing.", shown)
    if not before.passed:
        return refused("the test fails on the code before the change — it does not describe what the code does today. "
                       "It pins nothing.", shown)
    print(f"PINNED: {', '.join(tests)} passes on {sha[:7]}, the code before the change")
    print(f"  command: {args.cmd}\n  before the change: {before.exit()}\n{before.tail()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--root", help="the project (default: CLAUDE_PROJECT_DIR, else the repository of the current directory)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prove", "pins"):
        p = sub.add_parser(name)
        p.add_argument("--test", action="append", required=True, help="a test file of the change (repeatable)")
        p.add_argument("--cmd", required=True, help="the command that runs that test, from the project root")
        p.add_argument("--base", help="the commit before the change")
        p.add_argument("--timeout", type=int, default=TIMEOUT_S, help=f"seconds for one run (default {TIMEOUT_S})")
        if name == "prove":
            p.add_argument("--record", help="the bug record; its base_commit is the base")
            p.add_argument("--expect", help="text the failing run must print: the symptom")
    args = parser.parse_args(argv)
    try:
        root = project_root(args.root)
        return cmd_prove(root, args) if args.command == "prove" else cmd_pins(root, args)
    except CannotCheck as exc:
        print(f"bugfix.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
