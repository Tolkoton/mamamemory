#!/usr/bin/env python3
"""baseline.py — the snapshot "as it was", so the gate can ask "no worse than it was".

    python3 .claude/hooks/baseline.py record     # take the snapshot (the owner's command)
    python3 .claude/hooks/baseline.py tighten    # drop what was fixed, lower the counts
    python3 .claude/hooks/baseline.py show       # what is left, read from the file

The file is `.engine/baseline.json`, committed with the project and written by this script only:

    tests   the names of the tests that fail on the day of the snapshot
    lint    the number of findings per (file, rule)
    types   the same for the type checker

With the file present gate.py blocks only what got WORSE: a failing test that is not on the
list, a (file, rule) count above the recorded one. Without the file everything is as before:
"must be clean". Test coverage is not in the snapshot.

`record` runs the gate's full commands (those of the pre_commit / ci layers) and writes what it
saw. It may LOOSEN the snapshot — a new name, a higher count — so it is the owner's command:
refused inside a Claude Code session (CLAUDECODE is set in every shell the agent's tools start)
whenever the result is looser than the file on disk. A first snapshot loosens nothing, and
whether the project has one is the owner's decision all the same: in a session `record` shows
what the first snapshot would record and writes nothing. Run in the owner's
terminal it also writes the approval, `.claude/state/baseline/approved.sha256`; the gate's
bypass guard lets a loosening diff of the snapshot through only when that approval matches.

`tighten` runs the same commands and only ever removes: a listed test that no longer fails
leaves the list, a count that went down is lowered. Anyone may run it.

What is read from a command's output:
    tests   `FAILED <name>` / `ERROR <name>` (pytest's short summary), `FAIL: <name>` /
            `ERROR: <name>` (unittest)
    lint, types   `<file>:<line>[:<col>]: <message>`; the rule is a leading code (`F401`), else
            a trailing `[code]`, else `other`. A `note:` line is not counted.
A command that fails with nothing readable in its output is not in the snapshot: the gate keeps
blocking on it, as it does without a snapshot.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = 1
BASELINE_REL = Path(".engine/baseline.json")
SEAL_REL = Path(".claude/state/baseline/approved.sha256")
COUNTED = ("lint", "types")
STEP_PART = {"lint": "lint", "typecheck": "types", "tests": "tests"}
FAILED_TEST_RE = re.compile(r"^(?:FAILED|ERROR|FAIL):? +(?P<name>\S.*?)(?: - .*)?$", re.MULTILINE)
DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>[^\s:][^:\n]*\.\w+):(?P<line>\d+)(?::\d+)?:?\s+(?P<msg>.+)$", re.MULTILINE
)
LEADING_RULE_RE = re.compile(r"^(?P<rule>[A-Z]+[0-9]+)\b")
TRAILING_RULE_RE = re.compile(r"\[(?P<rule>[\w./-]+)\]\s*$")
EXITFIRST_RE = re.compile(r"(?:^|\s)(?:-x|--exitfirst|--maxfail(?:=|\s+)\d+|--failfast)(?=\s|$)")

Counts = dict[str, dict[str, int]]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ the file


def empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "tests": [], "lint": {}, "types": {}}


def parse(text: str | None) -> dict[str, Any] | None:
    """The snapshot in `text`, normalised; None when there is none or it cannot be read."""
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tests", []), list):
        return None
    snapshot = empty() | {k: v for k, v in data.items() if k not in ("tests", *COUNTED)}
    snapshot["tests"] = sorted({str(name) for name in data.get("tests", [])})
    for part in COUNTED:
        table = data.get(part, {})
        if not isinstance(table, dict):
            return None
        for file, rules in table.items():
            if not isinstance(rules, dict):
                return None
            kept = {str(r): n for r, n in rules.items() if isinstance(n, int) and n > 0}
            if kept:
                snapshot[part][str(file)] = dict(sorted(kept.items()))
        snapshot[part] = dict(sorted(snapshot[part].items()))
    return snapshot


def load(root: Path) -> tuple[dict[str, Any] | None, str]:
    """(snapshot, problem). No file: (None, ""). An unreadable file: (None, why) — the gate then
    asks for "clean", the strict side."""
    path = root / BASELINE_REL
    if not path.is_file():
        return None, ""
    try:
        snapshot = parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{BASELINE_REL} cannot be read: {exc}"
    return (snapshot, "") if snapshot is not None else (None, f"{BASELINE_REL} is not a snapshot this script wrote")


def render(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sealed(root: Path, text: str | None) -> bool:
    """True when the owner's `record` approved exactly this text of the snapshot."""
    if text is None:
        return False
    try:
        recorded = (root / SEAL_REL).read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return False
    return recorded == digest(text)


# ------------------------------------------------------------------ reading a command's output


def failed_tests(out: str) -> set[str]:
    return {m["name"].strip() for m in FAILED_TEST_RE.finditer(out)}


def rule_of(message: str) -> str | None:
    if message.startswith("note:"):
        return None
    found = LEADING_RULE_RE.match(message) or TRAILING_RULE_RE.search(message)
    return found["rule"] if found else "other"


def diagnostic_counts(out: str, root: Path) -> Counts:
    counts: Counts = {}
    for match in DIAGNOSTIC_RE.finditer(out):
        rule = rule_of(match["msg"].strip())
        if rule is None:
            continue
        file = match["file"]
        if os.path.isabs(file):
            file = os.path.relpath(file, root)
        file = Path(file).as_posix().removeprefix("./")
        counts.setdefault(file, {})
        counts[file][rule] = counts[file].get(rule, 0) + 1
    return counts


def stops_at_first(command: str) -> bool:
    """A test command that stops at the first failure hides every failure after an old one."""
    return EXITFIRST_RE.search(command) is not None


# ------------------------------------------------------------------ comparing


def worse_counts(now: Counts, was: Counts) -> list[tuple[str, str, int, int]]:
    """(file, rule, now, was) for every pair whose count is above the snapshot's."""
    return [(file, rule, n, was.get(file, {}).get(rule, 0))
            for file, rules in sorted(now.items()) for rule, n in sorted(rules.items())
            if n > was.get(file, {}).get(rule, 0)]


def fixed_counts(now: Counts, was: Counts) -> list[tuple[str, str, int, int]]:
    """(file, rule, now, was) for every pair of the snapshot whose count went down."""
    return [(file, rule, now.get(file, {}).get(rule, 0), n)
            for file, rules in sorted(was.items()) for rule, n in sorted(rules.items())
            if now.get(file, {}).get(rule, 0) < n]


def loosened(old_text: str | None, new_text: str | None) -> list[str]:
    """What the new text of the snapshot permits that the old one did not. A missing or
    unreadable snapshot permits nothing, on either side."""
    old, new = parse(old_text) or empty(), parse(new_text) or empty()
    found = [f"a test added to the list: {name}" for name in new["tests"] if name not in old["tests"]]
    for part in COUNTED:
        found += [f"{part} {file} [{rule}]: {was} -> {n}" for file, rule, n, was in worse_counts(new[part], old[part])]
    return found


def remaining(snapshot: dict[str, Any]) -> tuple[int, int, int]:
    lint, types = (sum(sum(r.values()) for r in snapshot[p].values()) for p in COUNTED)
    return len(snapshot["tests"]), lint, types


# ------------------------------------------------------------------ measuring


def measure(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Run the gate's full commands. Returns (what was seen, per part: "ok" | "unreadable"); a part
    with no command is in neither."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    env = gate.load_env(root)
    seen: dict[str, Any] = {"measured": {}}
    state: dict[str, str] = {}
    for kind, command in gate.check_steps(root, env, [], True, gate.Report(layer="ci", root=root), snapshot=True):
        part = STEP_PART[kind]
        rc, out, ms = gate.run_shell(root, command)
        found: Any = sorted(failed_tests(out)) if part == "tests" else diagnostic_counts(out, root)
        if rc == 0:
            found = [] if part == "tests" else {}
        seen[part] = found
        state[part] = "unreadable" if rc != 0 and not found else "ok"
        seen["measured"][part] = {"command": command}
        if part == "tests":
            seen["measured"][part]["duration_s"] = round(ms / 1000, 1)
            if stops_at_first(command):
                print(f"baseline: the test command stops at the first failure ({command}); failures after it "
                      "are not seen — drop that option", file=sys.stderr)
        if state[part] == "unreadable":
            print(f"baseline: {kind} fails ({command}) and nothing in its output names a test or a "
                  "`file:line: message` — not in the snapshot; the gate keeps blocking on it", file=sys.stderr)
    return seen, state


def write(root: Path, text: str) -> None:
    path = root / BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def summary(snapshot: dict[str, Any]) -> str:
    tests, lint, types = remaining(snapshot)
    return f"{tests} failing test(s), {lint} lint finding(s), {types} type finding(s)"


def entries(snapshot: dict[str, Any]) -> list[str]:
    """One line per thing the snapshot lists: a failing test, a (file, rule) count."""
    return [f"test   {name}" for name in snapshot["tests"]] + [
        f"{part:6} {file} [{rule}] {n}"
        for part in COUNTED for file, rules in snapshot[part].items() for rule, n in rules.items()]


def in_session() -> bool:
    return bool(os.environ.get("CLAUDECODE"))


def cmd_record(root: Path) -> int:
    current, _ = load(root)
    seen, _ = measure(root)
    snapshot = empty() | {"recorded_utc": utc_now(), "measured": seen["measured"]}
    for part in ("tests", *COUNTED):
        snapshot[part] = seen.get(part, (current or empty())[part])
    snapshot = parse(render(snapshot)) or empty()
    try:
        old_text = (root / BASELINE_REL).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        old_text = None
    text = render(snapshot)
    first = current is None
    looser = entries(snapshot) if first else loosened(old_text, text)
    if (first or looser) and in_session():
        print(f"baseline: measured {summary(snapshot)}.", file=sys.stderr)
        head = ("there is no snapshot yet; this is what the first one would record:" if first
                else "`record` would loosen the snapshot:")
        more = [f"  … and {len(looser) - 20} more"] if len(looser) > 20 else []
        print(f"baseline: {head}", *[f"  - {line}" for line in looser[:20]] or ["  nothing: no check fails today"],
              *more, sep="\n", file=sys.stderr)
        print(f"baseline: {'whether the project has a snapshot' if first else 'that'} is the owner's decision: "
              "`record` is refused inside a Claude Code session (CLAUDECODE is set). The owner runs "
              "`python3 .claude/hooks/baseline.py record` in their own terminal. Nothing was written.", file=sys.stderr)
        return 2
    write(root, text)
    if not in_session():
        seal = root / SEAL_REL
        seal.parent.mkdir(parents=True, exist_ok=True)
        seal.write_text(f"{digest(text)}  {BASELINE_REL}\n", encoding="utf-8")
    print(f"baseline: recorded {summary(snapshot)} in {BASELINE_REL}. Commit it with the project.")
    return 0


def cmd_tighten(root: Path) -> int:
    current, problem = load(root)
    if current is None:
        print(f"baseline: {problem or f'no {BASELINE_REL} — nothing to tighten'}", file=sys.stderr)
        return 1 if problem else 0
    seen, state = measure(root)
    snapshot = json.loads(json.dumps(current))
    removed: list[str] = []
    if state.get("tests") == "ok":
        removed = [name for name in current["tests"] if name not in seen["tests"]]
        snapshot["tests"] = [name for name in current["tests"] if name in seen["tests"]]
    lowered = 0
    for part in COUNTED:
        if state.get(part) != "ok":
            continue
        for file, rule, now, _was in fixed_counts(seen[part], current[part]):
            snapshot[part][file][rule] = now
            lowered += 1
    snapshot = parse(render(snapshot)) or empty()
    if snapshot == current:
        print(f"baseline: nothing was fixed since the snapshot; {summary(current)} left.")
        return 0
    snapshot["tightened_utc"] = utc_now()
    write(root, render(snapshot))
    for name in removed:
        print(f"baseline: fixed, off the list — {name}")
    print(f"baseline: tightened ({len(removed)} test(s) off the list, {lowered} count(s) lowered); "
          f"{summary(snapshot)} left. Commit {BASELINE_REL}.")
    return 0


def cmd_show(root: Path) -> int:
    current, problem = load(root)
    if current is None:
        print(f"baseline: {problem or f'no {BASELINE_REL}: the gate asks for clean'}")
        return 1 if problem else 0
    print(f"baseline: {summary(current)} (recorded {current.get('recorded_utc', '?')})")
    for line in entries(current):
        print(f"  {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("command", choices=("record", "tighten", "show"))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate

    root = gate.project_root()
    return {"record": cmd_record, "tighten": cmd_tighten, "show": cmd_show}[args.command](root)


if __name__ == "__main__":
    sys.exit(main())
