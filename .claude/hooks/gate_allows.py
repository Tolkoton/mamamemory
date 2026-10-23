#!/usr/bin/env python3
"""gate_allows.py — every gate exemption a slice's diff adds, laid in front of the overseer.

    python3 .claude/hooks/gate_allows.py            # the list as text; nothing when there is none
    python3 .claude/hooks/gate_allows.py --json     # {"base": ..., "allows": [...]}
    python3 .claude/hooks/gate_allows.py --base REF # diff against REF instead of the slice's base

WHY. The bypass guard of gate.py lets a suppression through when a `gate-allow: <reason>` stands
next to it, and all it can check of the reason is its shape (12 characters, two words). Whether
the reason is TRUE is a judgement, and until package costs nobody who judges ever saw it: an
agent passed the gate by typing any sentence. This script is the deterministic half of the fix —
it collects, it does not judge. `overseer_stop.py` puts its list into OVERSEER_REQUEST, and the
overseer skill tells an overseer asked by hand to run it; the overseer judges every reason.

WHAT COUNTS. Lines the diff ADDS (working tree + index + untracked files against the base):
  code      in a .py file, a COMMENT token carrying the marker — a string or a docstring that
            mentions it is not an exemption. `what` is the suppression it stands beside
            (type-ignore, noqa, skip, xfail), on its own line or the line below a comment line.
  config    an added line of pyproject.toml / ruff.toml / mypy.ini / .claude/project.env.
  contract  an added suppression (or a changed config file) that carries no marker of its own
            and passes the gate because a SEALED slice contract grants its kind: listed at the
            line that uses the grant, with the contract's reason. Also any marker line a
            contract gains in the diff, and a changed PROJECT_MARKER / CODE_EXTENSIONS, which
            passes on the contract's grant of that key alone.
A marker with no reason at all is listed too (`reason` empty); `reason_ok` says whether gate.py
would accept the reason's shape.

NEW MEANS NOT YET JUDGED. A checkpoint commit must not hide an exemption from the overseer, so
the base is not HEAD. In order: `--base REF`; the commit of the last audit request that ended in
an ACCEPTED OVERSEER_PASS; the `base_commit` the active slice contract names; the merge-base with
the main branch; HEAD. Judged means SHOWN AND PASSED, nothing less: when overseer_stop.py issues
an audit request it records what the request listed (`record_request`, a pending file); only an
accepted PASS that follows promotes exactly that list and that commit (`record_pass`). A PASS
with no request behind it, an exemption added after the request, a verdict other than PASS —
none of them marks anything judged. Judged exemptions are remembered by fingerprint (file, kind,
reason, and which occurrence) and not listed again; `--all` lists them too. Running this script
by hand records nothing. State: .claude/state/overseer/gate-allows-{judged,pending}.json.
Exit 0 always — except 2 for a base that is not a commit.

AN OPEN GATE ESCALATION HOLDS ITS OWN WORK ONLY (board 301). The base is one for the whole
branch, so a file the Stop gate gave up on stayed in the range of every later unit, whichever task
it belonged to, and no PASS could move the base while the escalation was open: on 2026-10-12
eleven tasks were refused for one file of a twelfth. Now `escalation_over` asks whose the change
is. An escalation covers a unit when a file it names is still unjudged AND is the unit's own: the
task in hand changed it in one of its commits (every stay of the task in tasks/doing/,
mode.task_commits) or it differs from HEAD in the working tree; the task the gate gave up on
(`work` in the escalation) is covered while the file is unjudged at all. With no board task
nobody can tell whose a change is, and the escalation covers the whole range, as it did. An
escalation that names no file covers everything.
What a PASS of other work must not do is accept the escalated change behind the owner's back, so
such a file is SET ASIDE: the request does not list its exemptions, and the accepted PASS, which
moves the base past the change, writes the file into `held` with the commit its change is counted
from. A held file stays in the unjudged range (`unjudged`) and its exemptions stay unjudged until
a request that does not set it aside is passed — the first audit after the owner closed the
escalation, whose request says the file is back and from where to read its diff.

Standard library only; imports gate.py so the two can never disagree about a diff or a reason.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gate

# Looser than gate.ALLOW_RE on purpose: a marker with an empty reason must be SEEN here.
MARKER_RE = re.compile(r"gate-allow:[ \t]*(?P<reason>.*)", re.IGNORECASE)
CONTRACT_LINE_RE = re.compile(
    r"^\s*gate-allow:\s*(?P<what>[\w./-]+)\s+[—–-]+\s*(?P<reason>.*)$", re.IGNORECASE
)
BASE_COMMIT_RE = re.compile(r"^\s*base_commit:\s*`?([0-9a-fA-F]{7,40})`?\s*$", re.MULTILINE)
SLICES_PREFIX = ".engine/slices/"
UNATTACHED = "nothing beside it"
JUDGED_REL = Path(".claude/state/overseer/gate-allows-judged.json")
PENDING_REL = Path(".claude/state/overseer/gate-allows-pending.json")
MAIN_BRANCHES = ("origin/main", "main", "origin/master", "master")
JUDGED_CAP = 5000
HEADER = (
    "GATE-ALLOW REVIEW — the slice's diff adds {n} gate exemption(s). The gate checked only the "
    "shape of each reason; whether it is true is yours to judge (overseer check #4: a silenced "
    "check is a masked gap). For EACH one, open the line. A reason is weak when it only says the "
    "check was in the way (\"to make mypy pass\", \"temporary\", \"for now\", \"legacy\"), restates "
    "what the suppression does, or names no cause that makes the check wrong at THIS line. A weak "
    "or missing reason is `OVERSEER_BLOCK: #4 masked gap — gate-allow at <file>:<line>: <what is "
    "missing>`; the ledger entry names every exemption you judged."
)


@dataclass
class Allow:
    file: str
    line: int
    source: str
    what: str
    reason: str
    reason_ok: bool
    # Which one of several identical exemptions in a file this is (1, 2, ...): a reason that was
    # accepted once does not cover the next suppression that copies it.
    ordinal: int = 1

    @property
    def fingerprint(self) -> str:
        key = f"{self.file}\x1f{self.source}\x1f{self.what}\x1f{self.reason}\x1f{self.ordinal}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def clean(reason: str) -> str:
    return reason.strip().rstrip("`").strip()


def changed_since(root: Path, base: str) -> list[str]:
    names: set[str] = set()
    names.update(gate.lines_of(gate.git(root, "diff", "--name-only", "--diff-filter=ACMR", base)))
    names.update(gate.lines_of(gate.git(root, "diff", "--name-only", "--cached", "--diff-filter=ACMR", base)))
    names.update(gate.lines_of(gate.git(root, "ls-files", "--others", "--exclude-standard")))
    return sorted(n for n in names if (root / n).is_file())


def added_since(root: Path, rel: str, base: str) -> set[int] | None:
    """Line numbers the diff against `base` adds to `rel`; None = every line (no version at base)."""
    if gate.git(root, "cat-file", "-e", f"{base}:{rel}").returncode != 0:
        return None
    out = gate.git(root, "diff", base, "-U0", "--no-color", "--", rel)
    if out.returncode != 0:
        return None
    added: set[int] = set()
    for hunk in gate.HUNK_RE.finditer(out.stdout):
        start = int(hunk.group("start"))
        count = 1 if hunk.group("count") is None else int(hunk.group("count"))
        added.update(range(start, start + count))
    return added


def suppressions_by_line(text: str, comments: dict[int, str]) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for line, comment in comments.items():
        for kind, pattern in gate.SUPPRESSIONS:
            if pattern.search(comment):
                found.setdefault(line, []).append(kind)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and gate.dotted(node) in gate.SKIP_NAMES:
            kind = gate.SKIP_NAMES[gate.dotted(node)]
            if kind not in found.setdefault(node.lineno, []):
                found[node.lineno].append(kind)
    return found


def from_python(rel: str, text: str, added: set[int] | None, grants: dict[str, tuple[str, str]]) -> list[Allow]:
    comments = gate.comment_map(text)
    if comments is None:
        return []
    source_lines = text.splitlines()
    beside = suppressions_by_line(text, comments)

    def comment_only(line: int) -> bool:
        return 1 <= line <= len(source_lines) and source_lines[line - 1].lstrip().startswith("#")

    allows: list[Allow] = []
    marked: set[int] = set()
    for line in sorted(comments):
        match = MARKER_RE.search(comments[line])
        if not match:
            continue
        target = line if beside.get(line) or not comment_only(line) else line + 1
        marked.add(target)
        if added is not None and line not in added:
            continue
        reason = clean(match["reason"])
        kinds = "+".join(beside.get(target, [])) or UNATTACHED
        allows.append(Allow(rel, line, "code", kinds, reason, gate.valid_reason(reason)))
    # A suppression with no marker of its own that the gate lets through on a contract's grant.
    for line in sorted(beside):
        if line in marked or (added is not None and line not in added):
            continue
        for kind in beside[line]:
            if kind in grants:
                name, reason = grants[kind]
                allows.append(Allow(rel, line, "contract", f"{kind} (granted by {name})", reason, True))
    return sorted(allows, key=lambda a: a.line)


def from_lines(rel: str, text: str, added: set[int] | None, source: str) -> list[Allow]:
    allows: list[Allow] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if added is not None and number not in added:
            continue
        match = MARKER_RE.search(line)
        if not match:
            continue
        what, reason = "config", clean(match["reason"])
        if source == "contract":
            granted = CONTRACT_LINE_RE.match(line)
            what = granted["what"].lower() if granted else "?"
            reason = clean(granted["reason"]) if granted else reason
        allows.append(Allow(rel, number, source, what, reason, gate.valid_reason(reason)))
    return allows


def is_commit(root: Path, ref: str) -> bool:
    return gate.git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}").returncode == 0


def read_judged(root: Path) -> tuple[str, set[str]]:
    """(commit of the last accepted PASS, fingerprints judged so far); ("", empty) when none."""
    try:
        data = json.loads((root / JUDGED_REL).read_text(encoding="utf-8"))
        return str(data.get("commit", "")), {str(x) for x in data.get("judged", [])}
    except (OSError, ValueError, AttributeError, TypeError):
        return "", set()


def read_held(root: Path) -> dict[str, str]:
    """file → the commit its unjudged change is counted from, for the files an accepted PASS set
    aside (AN OPEN GATE ESCALATION HOLDS ITS OWN WORK ONLY); empty when none."""
    try:
        held = json.loads((root / JUDGED_REL).read_text(encoding="utf-8")).get("held")
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
    return {str(rel): str(since) for rel, since in held.items()} if isinstance(held, dict) else {}


def default_base(root: Path) -> str:
    """Where "not yet judged" starts: the last accepted PASS, else the slice's base_commit, else
    the point this branch left the main one, else HEAD."""
    commit, _ = read_judged(root)
    if commit and is_commit(root, commit):
        return commit
    slug = gate.active_slice(root)
    if slug:
        try:
            text = (root / ".engine" / "slices" / f"{slug}.md").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        named = BASE_COMMIT_RE.search(text)
        if named and is_commit(root, named.group(1)):
            return named.group(1)
    for branch in MAIN_BRANCHES:
        if is_commit(root, branch):
            merge = gate.git(root, "merge-base", "HEAD", branch).stdout.strip()
            if merge:
                return merge
    return "HEAD"


def differs(root: Path, rel: str, since: str) -> bool:
    """`rel` is a file now and is not what the commit `since` has."""
    if not (root / rel).is_file():
        return False
    return (gate.git(root, "cat-file", "-e", f"{since}:{rel}").returncode != 0
            or gate.git(root, "diff", "--quiet", since, "--", rel).returncode != 0)


def unjudged(root: Path) -> dict[str, str]:
    """Every file no accepted PASS has covered → the commit its change is counted from: the base,
    and for a file a PASS set aside, the base of that time."""
    if not gate.has_head(root):
        return {}
    base = default_base(root)
    files = {rel: base for rel in changed_since(root, base)} if is_commit(root, base) else {}
    for rel, since in read_held(root).items():
        if is_commit(root, since) and differs(root, rel, since):
            files[rel] = since
    return files


def own_files(root: Path, task: str, tree: bool = True) -> set[str] | None:
    """What the task changed itself: the files of its commits and, with `tree`, whatever differs
    from HEAD in the working tree. None — whose a change is cannot be told: no board task, or one
    git never saw in tasks/doing/. Without `tree` (a task that waits in todo/) such a task has
    changed nothing."""
    if not task:
        return None
    try:
        import mode

        commits = mode.task_commits(root, task)
        if commits is None:
            return None if tree else set()
        files = {rel for commit in commits for rel in mode._changed(root, commit)}
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return None
    return files | set(changed_since(root, "HEAD")) if tree else files


def open_escalations(root: Path) -> list[dict[str, Any]]:
    return [e for e in gate.read_escalations(root)["open"] if isinstance(e, dict)]


def escalation_over(root: Path, task: str | None = None, tree: bool = True,
                    files: dict[str, str] | None = None) -> tuple[str, str] | None:
    """(timestamp, scope text) of the open gate escalation a verdict on the task's work runs into,
    or None (AN OPEN GATE ESCALATION HOLDS ITS OWN WORK ONLY). `task` — the session's task in
    doing/ unless named; `tree=False` asks for a task that waits in todo/, whose work is its
    commits alone; `files` — `unjudged(root)` when the caller has it."""
    entries = open_escalations(root)
    if not entries:
        return None
    task = gate.work_in_hand(root) if task is None else task
    own: set[str] | None = None
    asked = False
    for entry in entries:
        stamp, raised_in = str(entry.get("stamp", "?")), str(entry.get("slice", gate.NO_SLICE))
        where = f"raised in slice `{raised_in}`" if raised_in != gate.NO_SLICE else "raised outside any slice"
        named = {str(f) for f in entry.get("files") or []}
        if not named:
            return stamp, f"{where}, on no particular file — it covers all work"
        if not asked:
            files = unjudged(root) if files is None else files
            own, asked = own_files(root, task, tree), True
        covered = named & set(files or {})
        if own is not None and task != str(entry.get("work") or ""):
            covered &= own
        if covered:
            return stamp, f"{where}, on " + ", ".join(sorted(covered)[:5])
    return None


def set_aside(root: Path, files: dict[str, str] | None = None) -> dict[str, str]:
    """The unjudged files of open gate escalations that the unit in hand does not answer for →
    the commit their change is counted from. Empty when an escalation covers the unit: its
    verdict cannot be PASS, and nothing is kept from its auditor."""
    entries = open_escalations(root)
    if not entries:
        return {}
    files = unjudged(root) if files is None else files
    if escalation_over(root, files=files) is not None:
        return {}
    named = {str(f) for entry in entries for f in entry.get("files") or []}
    return {rel: since for rel, since in files.items() if rel in named}


def collect(root: Path, base: str | None = None, include_judged: bool = False) -> list[Allow]:
    """Every gate exemption the diff against the base adds and no accepted PASS has seen — but
    for the files set aside. Raises ValueError for a base that is no commit."""
    if not gate.has_head(root):
        return []
    ref = base or default_base(root)
    if not is_commit(root, ref):
        raise ValueError(f"base '{ref}' is not a commit in this repository")
    grants = gate.contract_grants(root)
    allows: list[Allow] = []
    since = {rel: ref for rel in changed_since(root, ref)} if base else unjudged(root)
    aside = {} if base else set_aside(root, since)
    for rel, start in sorted(since.items()):
        if rel in aside:
            continue
        is_contract = rel.startswith(SLICES_PREFIX) and rel.endswith(".md")
        if not (rel.endswith(".py") or gate.is_config_file(rel) or is_contract):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        added = added_since(root, rel, start)
        if rel.endswith(".py"):
            allows.extend(from_python(rel, text, added, grants))
            continue
        found = from_lines(rel, text, added, "contract" if is_contract else "config")
        if not found and not is_contract:
            grant = grants.get(rel.lower()) or grants.get(Path(rel).name.lower())
            if grant:
                found = [Allow(rel, 1, "contract", f"config change (granted by {grant[0]})", grant[1], True)]
        if rel == ".claude/project.env":
            # PROJECT_MARKER / CODE_EXTENSIONS pass on the contract's grant alone: show it where it is used.
            before, after = gate.parse_env_text(gate.git(root, "show", f"{start}:{rel}").stdout), gate.parse_env_text(text)
            for name in gate.SCOPE_KEYS:
                grant = grants.get(name.lower())
                if grant and before.get(name, "") != after.get(name, ""):
                    found.append(Allow(rel, 1, "contract", f"{name} change (granted by {grant[0]})", grant[1], True))
        allows.extend(found)
    seen: dict[tuple[str, str, str, str], int] = {}
    for allow in allows:
        key = (allow.file, allow.source, allow.what, allow.reason)
        seen[key] = allow.ordinal = seen.get(key, 0) + 1
    if include_judged or base:
        return allows
    _, judged = read_judged(root)
    return [a for a in allows if a.fingerprint not in judged]


def record_request(root: Path) -> list[Allow]:
    """Called by overseer_stop.py when it issues an audit request: collect, and remember what
    this request shows and at which commit. Only an accepted PASS turns that into "judged"."""
    allows = collect(root)
    head = gate.git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()
    # `held` is the whole of it after this request: a file held before and not set aside now is shown now.
    gate.write_json(root / PENDING_REL, {"commit": head, "shown": sorted(a.fingerprint for a in allows),
                                         "held": set_aside(root), "requested_utc": gate.utc_now()})
    return allows


ASIDE_NOTE = (
    "SET ASIDE — an open gate escalation holds {files}, changed by other work and not by this unit. "
    "They are not part of this audit: a PASS here accepts nothing in them, and their gate exemptions "
    "are not listed. They stay unjudged until the owner closes the escalation."
)
BACK_NOTE = (
    "BACK IN THIS AUDIT — {files}: changed while a gate escalation was open on them, and set aside "
    "by every PASS since. No PASS has covered that change; it is part of this audit, whichever "
    "task made it. Read it with `git diff <commit> -- <file>`."
)


def aside_note(root: Path) -> str:
    """What the overseer is told about the files an open escalation keeps out of this audit, and
    about the held files this audit gets back; the empty string when there are neither."""
    files = unjudged(root)
    aside, held = set_aside(root, files), read_held(root)
    back = sorted(rel for rel in held if rel in files and rel not in aside)
    notes = [ASIDE_NOTE.format(files=", ".join(sorted(aside)))] if aside else []
    if back:
        notes.append(BACK_NOTE.format(files=", ".join(f"{rel} (since {held[rel][:12]})" for rel in back)))
    return "\n\n".join(notes)


def drop_request(root: Path) -> None:
    """A verdict other than an accepted PASS judged nothing: forget the pending request."""
    (root / PENDING_REL).unlink(missing_ok=True)


def record_pass(root: Path) -> bool:
    """Called by overseer_stop.py when it ACCEPTS an OVERSEER_PASS. Promotes the pending request —
    exactly what it showed, at the commit it was made — and nothing else. False (and no change)
    when no request is pending: a PASS nobody asked for has judged nothing."""
    try:
        pending = json.loads((root / PENDING_REL).read_text(encoding="utf-8"))
        commit, shown = str(pending["commit"]), {str(x) for x in pending["shown"]}
        held = pending.get("held")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    previous, judged = read_judged(root)
    gate.write_json(root / JUDGED_REL, {"commit": commit or previous, "judged": sorted(judged | shown)[-JUDGED_CAP:],
                                        "held": held if isinstance(held, dict) else read_held(root),
                                        "updated_utc": gate.utc_now()})
    drop_request(root)
    return True


def render(allows: list[Allow]) -> str:
    """The list as the overseer reads it; the empty string when there is nothing to judge."""
    if not allows:
        return ""
    lines = [HEADER.format(n=len(allows))]
    for number, allow in enumerate(allows, start=1):
        if not allow.reason:
            reason = "MISSING"
        elif allow.reason_ok:
            reason = f'"{allow.reason}"'
        else:
            reason = f'"{allow.reason}" (too short for the gate itself)'
        lines.append(f"  {number}. {allow.file}:{allow.line} [{allow.source}: {allow.what}] reason: {reason}")
    return "\n".join(lines)


def unit_files(root: Path) -> set[str]:
    """Files changed since the base, and the held ones — the range no accepted PASS has covered."""
    return set(unjudged(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--base", default=None, help="diff base (default: see NEW MEANS NOT YET JUDGED)")
    parser.add_argument("--all", action="store_true", help="also list exemptions an accepted PASS has already seen")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    root = gate.project_root()
    try:
        allows = collect(root, args.base, include_judged=args.all)
    except ValueError as exc:
        print(f"gate_allows: {exc}", file=sys.stderr)
        return 2
    if args.json:
        payload = {"base": args.base or default_base(root), "allows": [asdict(a) for a in allows]}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif allows:
        print(render(allows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
