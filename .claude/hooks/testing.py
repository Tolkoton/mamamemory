#!/usr/bin/env python3
"""testing.py — the testing manager and the slice tester: who is called, what they said, what holds.

    python3 .claude/hooks/testing.py request <slug> --point a|b          # the manager: facts, then the launch line
    python3 .claude/hooks/testing.py request <slug> --tester contract|objection|block [--package FILE]
    python3 .claude/hooks/testing.py guard                               # PreToolUse hook (stdin: the envelope)
    python3 .claude/hooks/testing.py record [--answer FILE]              # SubagentStop hook; by hand only while not wired
    python3 .claude/hooks/testing.py validate DECISION.json --request ID # 0 allowed, 1 refused with the reasons
    python3 .claude/hooks/testing.py invariants CONTRACT.md              # the «Invariants» section: 0 well-formed, 1 not
    python3 .claude/hooks/testing.py answer <slug> <Q> --reading taken|other --text "…"
    python3 .claude/hooks/testing.py seal <slug> | check <slug> | gate <slug> | status [<slug>] | ledger
    python3 .claude/hooks/testing.py feature-close <feature>             # 0 the feature may close, 3 it may not
    python3 .claude/hooks/testing.py mutation <slug> [--timeout S] | mutation-result <slug> --survived N --handled N

WHO DECIDES WHAT (board 060, built by board 062). The script counts the facts and holds the
mandatory cases; the manager (`test-manager`, read-only) judges the rest and writes its reason;
the tester (`slice-tester`) writes contract tests from the sealed contract. Both agents are
started with one line this script prints — `TESTING_REQUEST <id>` — and nothing else.

TWO POINTS OF A SLICE. (a) the contract is sealed, no code yet: who writes the contract tests —
the independent tester or the builder. (b) the slice is finished: what else is checked now
(catch-up contract tests, integration tests, a mutation run), what is deferred and until which
event. The next slice does not start, and a feature does not close, without the decision of (b).

MANDATORY CASES — the manager cannot cancel them; `validate` refuses any other decision:
  O1  the contract names a hardest seam                                   -> the tester (a)
  O2  another slice consumes the output, or the contract is public        -> the tester (a)
  O3  the exit criterion carries a threshold the owner ratified           -> the tester (a)
  O4  the previous slice of the block: a dispute ended "the code was wrong", the tester found an
      ambiguity of the contract, or the overseer blocked on check #4      -> the tester (a)
  O5  the last block of the feature is closed                             -> integration tests now (b)
  O6  the event a debt was deferred to has come                           -> that check now (b)
  O7  (a) said "the builder", and the slice gave a self-added behaviour or a #4 block
                                                                          -> catch-up tests now (b)
  O8  the slice changes working code no test touches — at (a) by what the contract's «Seam»
      names and already exists, at (b) by the real diff, the slice's own tests counted; measured
      by test_touch.py, the way the delete guard measures it          -> the tester (a), catch-up now (b)

RED IS RUN HERE, NOT CLAIMED. `record` runs every contract test of a hand-in itself: each must
fail, and not on an import; a test marked `keeps` (behaviour the contract tells to preserve) must
pass. A test that depends on an unanswered question to the contract lives in a file of its own,
and that file is not sealed until the question is answered. Sealed files: `check` compares them
with their fingerprints, and overseer_stop.py asks `gate` before it requests an audit.

INVARIANTS (board 048, built by board 064). A contract planned by `/plan-slice` has a section
«Invariants»: numbered rules (I1, I2…) that hold for every input of a stated domain, each with
«Domain», «Source» and «Broken by» — or "None" with the reason. `invariants` checks that shape
before the contract is sealed; the manager gets them as facts; a contract hand-in of the tester
has a test named `test_I<n>_…` for every invariant and none for a number the contract does not
have. Every invariant is checked by examples: there is no property-based testing library here.
A contract sealed before the section existed has none, and that is a fact, not an error.

State: .claude/state/testing/ (machine state — written here only). The human journal:
.engine/testing/ledger.md. Exit: 0 ok, 1 refused, 2 usage, 3 blocked. Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_touch

JsonObj = dict[str, Any]

STATE_REL = Path(".claude/state/testing")
REQUESTS_REL = STATE_REL / "requests"
PENDING_REL = STATE_REL / "pending.json"
ROWS_REL = STATE_REL / "rows.jsonl"
SEALS_REL = STATE_REL / "seals"
LEDGER_REL = Path(".engine/testing/ledger.md")
MUTATION_REL = Path(".engine/testing/mutation")
OVERSEER_ROWS_REL = Path(".claude/state/overseer/verdicts.jsonl")
CONTRACT_SEALS_REL = Path(".claude/state/contracts")
FEATURES_REL = Path(".engine/architecture/feature")
REQUEST_WORD = "TESTING_REQUEST"
WIRING_MARK = "testing.py"
MANAGER, TESTER = "test-manager", "slice-tester"
AGENTS = (MANAGER, TESTER)
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
AGENT_TOOLS = frozenset({"Agent", "Task"})
MODES = ("contract", "objection", "block")
KINDS = ("catch_up", "integration", "mutation")
WHEN = ("now", "defer", "none")
VERDICTS = ("test_wrong", "test_right", "contract_ambiguous")
MAX_ROUNDS = 2          # the owner's number (board 060, answer 3): two rounds a slice, the third parks it
REVIEW_AFTER = 10       # the owner's number (board 060, answer 6): a review after ten live slices, not a verdict
RUN_TIMEOUT_S = 300
MUTATION_TIMEOUT_S = 3600
CANNOT_RUN = (126, 127)
TAIL_LINES = 12
NOT_A_TEST_RE = re.compile(
    r"ImportError|ModuleNotFoundError|SyntaxError|IndentationError|no tests ran|collected 0 items|"
    r"errors? during collection|Ran 0 tests|Cannot find module|cannot find package|No tests found", re.IGNORECASE)
RATIFIED_RE = re.compile(r"owner[- ]ratified|ratified by the owner|owner ratification pending|ратифік", re.IGNORECASE)
SLICE_LINE_RE = re.compile(r"^- \*\*(?P<id>S\d+)\b\s*(?P<name>[^*]*)\*\*(?P<rest>.*)$", re.MULTILINE)
EDGE_RE = re.compile(r"^- (?P<a>S\d+)\s*(?:→|->)\s*(?P<b>S\d+)\b", re.MULTILINE)
PATH_RE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z]{1,5})(?![\w/-])")
EVENT_RE = re.compile(r"^(?:block-closed:[\w.-]+|feature-closed)$")
INVARIANTS_TITLE = "Invariants"
INVARIANT_RE = re.compile(r"^[-*]\s*\*\*(?P<id>I\d+)\*\*\s*(?:[—–:-]\s*)?(?P<rule>.*)$")
INVARIANT_FIELDS = {"domain": "Domain", "source": "Source", "broken_by": "Broken by"}
INVARIANT_FIELD_RE = re.compile(r"^\s+[-*]\s*(?P<name>[A-Za-z][A-Za-z ]*?)\s*:\s*(?P<value>.*)$")
INVARIANT_NONE_RE = re.compile(r"^(?:[-*]\s*)?\**(?:none|немає)\b\**[\s.:—–-]*(?P<reason>.*)$", re.IGNORECASE | re.DOTALL)
INVARIANT_TEST_RE = re.compile(r"(?<![A-Za-z0-9])test_(I\d+)(?!\d)")
PLACEHOLDER_RE = re.compile(r"^[\s.…?—–-]*$|^\s*(?:<[^>]*>|\[[^\]]*\])[\s.]*$|^(?:tbd|todo|n/?a)\b", re.IGNORECASE)
LEDGER_HEADER = ("# Testing ledger\n\nWritten by `.claude/hooks/testing.py` only: every decision of the testing manager, every "
                 "hand-in of the tester, every dispute and its end, every debt. Read in the owner's review.\n")


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_root() -> Path:
    import gate

    return gate.project_root().resolve()


def load_env(root: Path) -> dict[str, str]:
    import gate

    return gate.load_env(root)


def read_json(path: Path) -> JsonObj:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: JsonObj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def one_line(text: object, limit: int = 500) -> str:
    return " ".join(str(text).split())[:limit]


def wired(root: Path) -> bool:
    """Are `guard` and `record` wired in the project's settings? Until the owner applies the
    proposal they are not, and `record --answer` by hand is the only way to record."""
    for name in ("settings.json", "settings.local.json"):
        try:
            if WIRING_MARK in (root / ".claude" / name).read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


# ------------------------------------------------------------------ rows and the ledger


def rows(root: Path, slug: str | None = None, kind: str | None = None) -> list[JsonObj]:
    try:
        lines = (root / ROWS_REL).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and (slug is None or row.get("slice") == slug) and (kind is None or row.get("type") == kind):
            found.append(row)
    return found


LEDGER_ROW_RE = re.compile(r"^<!-- row: (.*) -->$", re.MULTILINE)
LEDGER_DROPS = ("tests", "results", "manager_said", "run", "files", "rounds")


def ledger(root: Path, title: str, lines: list[str], row: JsonObj | None = None) -> None:
    """One entry of the human journal. The row rides along in a comment (without its bulky
    fields): the owner's review reads the journal from git, where machine state is not."""
    path = root / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(LEDGER_HEADER, encoding="utf-8")
    carried = ""
    if row is not None:
        compact = json.dumps({k: v for k, v in row.items() if k not in LEDGER_DROPS}, ensure_ascii=False)
        escaped = compact.replace("--", "-\\u002d")   # outside the f-string: a backslash in its expression needs Python 3.12
        carried = f"<!-- row: {escaped} -->\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {utc_now()} — {title}\n" + "".join(f"- {line}\n" for line in lines) + carried)


def ledger_rows(text: str) -> list[JsonObj]:
    """The rows the ledger carries, oldest first: what `board.py review` reads."""
    found = []
    for raw in LEDGER_ROW_RE.findall(text):
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            found.append(row)
    return found


def append_row(root: Path, row: JsonObj, title: str, lines: list[str]) -> JsonObj:
    """The one writer of a decision, a hand-in, a round, a debt: machine state and the ledger together."""
    row = {"utc": utc_now(), **row}
    path = root / ROWS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    ledger(root, title, lines, row)
    return row


def last(root: Path, slug: str, kind: str, **match: object) -> JsonObj | None:
    found = [r for r in rows(root, slug, kind) if all(r.get(k) == v for k, v in match.items())]
    return found[-1] if found else None


# ------------------------------------------------------------------ the contract and the feature artifact


def contract_path(root: Path, slug: str) -> Path:
    return root / ".engine" / "slices" / f"{slug}.md"


def contract_sealed(root: Path, slug: str) -> bool:
    return (root / CONTRACT_SEALS_REL / f"{slug}.sha256").is_file()


def section(text: str, title: str) -> str:
    """The body of the `## <title…>` section (the heading may go on: "Hardest seams (test-confidence…)")."""
    match = re.search(rf"^##\s+{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def invariants(text: str) -> JsonObj:
    """The «Invariants» section of a contract: `section` is `absent` (a contract sealed before the
    section existed), `none` (the planner said there are none, with `none_reason`) or `named`;
    `items` are the numbered rules with their fields; `problems` is what makes the section
    ill-formed. A problem is refused before the contract is sealed (`invariants`), never after."""
    if not re.search(rf"^##\s+{INVARIANTS_TITLE}\b", text, re.IGNORECASE | re.MULTILINE):
        return {"section": "absent", "items": [], "none_reason": "", "problems": ["the contract has no «Invariants» section"]}
    body = section(text, INVARIANTS_TITLE)
    items: list[JsonObj] = []
    last_key = ""
    for line in body.splitlines():
        head = INVARIANT_RE.match(line)
        part = INVARIANT_FIELD_RE.match(line) if items else None
        if head:
            items.append({"id": head.group("id"), "rule": head.group("rule").strip(), "fields": {}})
            last_key = "rule"
        elif part:
            last_key = part.group("name").strip().lower()
            items[-1]["fields"][last_key] = part.group("value").strip()
        elif items and line.strip() and last_key == "rule":
            items[-1]["rule"] = f"{items[-1]['rule']} {line.strip()}".strip()
        elif items and line.strip():
            items[-1]["fields"][last_key] = f"{items[-1]['fields'][last_key]} {line.strip()}".strip()
    problems = []
    none = INVARIANT_NONE_RE.match(body) if not items else None
    reason = one_line(none.group("reason"), 300) if none else ""
    if not items and not none:
        problems.append("the section names no invariant (`- **I1** — <rule>`) and does not say `None — <the reason>`")
    elif none and PLACEHOLDER_RE.match(reason):
        problems.append("`None` stands without its reason: say why this slice has no rule that holds for every input")
    seen: set[str] = set()
    for item in items:
        if item["id"] in seen:
            problems.append(f"{item['id']}: the number is used twice")
        seen.add(item["id"])
        if PLACEHOLDER_RE.match(item["rule"]):
            problems.append(f"{item['id']}: no rule — one sentence, in the words of the task")
        for key, name in INVARIANT_FIELDS.items():
            if PLACEHOLDER_RE.match(item["fields"].get(name.lower(), "")):
                problems.append(f"{item['id']}: no «{name}» — " + {
                    "domain": "for which inputs the rule holds",
                    "source": "the line of the goals, the feature artifact, an owner's decision or this contract's «Seam» the rule follows "
                              "from; an invariant without a source is an invented requirement",
                    "broken_by": "the wrong implementation the rule would catch; an invariant nobody can break checks nothing"}[key])
        if "check" in item["fields"]:
            problems.append(f"{item['id']}: there is no «Check» field — every invariant is checked by examples "
                            "(no property-based testing library is set up; board 064)")
    found = [{"id": i["id"], "rule": i["rule"]} | {key: i["fields"].get(name.lower(), "") for key, name in INVARIANT_FIELDS.items()} for i in items]
    return {"section": "named" if items else "none", "items": found, "none_reason": reason if not items else "", "problems": problems}


def invariant_facts(text: str) -> JsonObj:
    """What the manager and the ledger are told: how many invariants, their numbers, or why none."""
    found = invariants(text)
    facts: JsonObj = {"section": found["section"], "count": len(found["items"]), "ids": [i["id"] for i in found["items"]]}
    if found["section"] == "none":
        facts["none_reason"] = found["none_reason"]
    if found["section"] == "absent":
        facts["note"] = "the contract was sealed before the section existed: invariants were not named"
    elif found["problems"]:
        facts["problems"] = found["problems"]
    return facts


def check_invariants(path: Path) -> tuple[int, str]:
    try:
        found = invariants(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        return 2, f"cannot read the contract: {exc}"
    if found["problems"]:
        return 1, f"REFUSED: the «Invariants» section of {path.name} is not ready to be sealed:\n- " + "\n- ".join(found["problems"])
    if found["section"] == "none":
        return 0, f"well-formed: no invariants — {found['none_reason']}"
    return 0, f"well-formed: {len(found['items'])} invariant(s) — " + ", ".join(i["id"] for i in found["items"])


@dataclass
class Slice:
    id: str
    name: str
    deps: list[str] = field(default_factory=list)
    block: str = ""
    tracer: bool = False
    public: bool = False

    def is_slug(self, slug: str) -> bool:
        mine, theirs = norm(self.name), norm(slug)
        return bool(theirs) and (theirs in (mine, norm(self.id)) or (bool(mine) and theirs.endswith("-" + mine)))


@dataclass
class Feature:
    name: str
    slices: list[Slice]
    edges: list[tuple[str, str]]   # producer -> consumer
    acceptance: str

    def of(self, slug: str) -> Slice | None:
        return next((s for s in self.slices if s.is_slug(slug)), None)

    def block_of(self, item: Slice) -> list[Slice]:
        return [s for s in self.slices if s.block == item.block]

    def blocks(self) -> list[str]:
        return list(dict.fromkeys(s.block for s in self.slices))


def parse_feature(name: str, text: str) -> Feature:
    """The slices of «Slices (the DAG)»: id, name, `depends on:`, `block:` (no labels — the whole
    feature is one block), the tracer mark; the edges of «Inter-slice contracts» and of `depends on`."""
    slices = []
    for match in SLICE_LINE_RE.finditer(section(text, "Slices (the DAG)")):
        rest = match.group("rest")
        fields = {k.strip().lower(): v.strip() for k, _, v in (part.partition(":") for part in rest.split("·")) if v}
        slices.append(Slice(
            id=match.group("id"), name=match.group("name").strip(" []"), deps=re.findall(r"S\d+", fields.get("depends on", "")),
            block=fields.get("block", "").strip("[]` ") or name, tracer="TRACER BULLET" in rest.upper(),
            public="public" in fields.get("contract out", "").lower()))
    edges = {(dep, s.id) for s in slices for dep in s.deps}
    edges |= {(m.group("a"), m.group("b")) for m in EDGE_RE.finditer(section(text, "Inter-slice contracts"))}
    return Feature(name, slices, sorted(edges), section(text, "Acceptance criteria"))


def feature_of(root: Path, slug: str) -> tuple[Feature, Slice] | None:
    folder = root / FEATURES_REL
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        feature = parse_feature(path.stem, path.read_text(encoding="utf-8", errors="replace"))
        item = feature.of(slug)
        if item is not None:
            return feature, item
    return None


def slug_of(root: Path, item: Slice) -> str | None:
    """The slug the slice was planned under: the contract in .engine/slices/ that names it."""
    folder = root / ".engine" / "slices"
    return next((p.stem for p in sorted(folder.glob("*.md")) if item.is_slug(p.stem)), None) if folder.is_dir() else None


def finished(root: Path, item: Slice) -> bool:
    slug = slug_of(root, item)
    return slug is not None and last(root, slug, "decision", point="b") is not None


# ------------------------------------------------------------------ O8: code no test touches


def is_working_code(env: dict[str, str], rel: str) -> bool:
    import delete_guard

    return delete_guard.is_working_code(env, rel)


def touch(root: Path, env: dict[str, str], files: dict[str, set[int]], overlay: dict[str, str]) -> list[JsonObj]:
    """For every file: does a test touch it? `files` maps a path to the lines that matter (empty:
    any line of the file). With COVERAGE_CMD — exactly, on HEAD with `overlay` laid over it;
    without it, or when it leaves no report — the coarser check of the delete guard."""
    if not files:
        return []
    command = env.get(test_touch.COVERAGE_KEY, "").strip()
    report = test_touch.run_coverage(root, "HEAD", command, overlay) if command else None
    tests = test_touch.TestIndex(root, "HEAD", {})
    found = []
    for rel, lines in sorted(files.items()):
        if report is not None:
            entry = report.get(rel, {"executed": set(), "missing": set()})
            measured = lines & (entry["executed"] | entry["missing"]) if lines else entry["executed"] | entry["missing"]
            hit = (lines & entry["executed"]) if lines else entry["executed"]
            # Changed lines that hold no statement (a comment, a blank) cannot be executed by anything.
            why = f"tests executed {len(hit)} of its lines" if hit else ("" if measured or not lines else "no statement changed")
            how = "coverage"
        else:
            why, how = test_touch.coarse_reason(tests, rel), "coarse"
        found.append({"file": rel, "touched": bool(why), "why": why or "no test touches it", "how": how})
    return found


def named_code(root: Path, env: dict[str, str], text: str) -> dict[str, set[int]]:
    """The existing files of working code a contract's «Seam» names. Code that is not there yet
    does not count: the slice's own tests will cover it."""
    found: dict[str, set[int]] = {}
    for candidate in PATH_RE.findall(text):
        rel = candidate.lstrip("./")
        if (root / rel).is_file() and is_working_code(env, rel):
            found[rel] = set()
    return found


def changed_code(root: Path, env: dict[str, str], base: str) -> tuple[dict[str, set[int]], JsonObj]:
    """The working code the slice changed since `base` (the new line numbers), and the counts."""
    diff = test_touch.git(root, "diff", "--unified=0", "--no-color", base, "--").stdout
    untracked = test_touch.git(root, "ls-files", "-o", "--exclude-standard").stdout.splitlines()
    files: dict[str, set[int]] = {}
    counts = {"code_lines": 0, "test_lines": 0, "code_files": 0, "test_files": 0}
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else ""
            if current:
                files.setdefault(current, set())
        elif line.startswith("@@") and current:
            match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                start, count = int(match.group(1)), int(match.group(2) or "1")
                files[current] |= set(range(start, start + count))
    for rel in untracked:
        try:
            files[rel] = set(range(1, len((root / rel).read_text(encoding="utf-8", errors="replace").splitlines()) + 1))
        except OSError:
            continue
    code: dict[str, set[int]] = {}
    for rel, lines in files.items():
        if not (root / rel).is_file():
            continue
        if test_touch.is_test_path(rel):
            counts["test_lines"] += len(lines)
            counts["test_files"] += 1
        elif is_working_code(env, rel):
            code[rel] = lines
            counts["code_lines"] += len(lines)
            counts["code_files"] += 1
    return code, counts


def tree_overlay(root: Path) -> dict[str, str]:
    """Everything that differs from HEAD, as it is now: laid over the checkout before coverage runs."""
    names = test_touch.git(root, "diff", "--name-only", "HEAD", "--").stdout.splitlines()
    names += test_touch.git(root, "ls-files", "-o", "--exclude-standard").stdout.splitlines()
    files = {}
    for rel in names:
        try:
            files[rel] = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return files


# ------------------------------------------------------------------ the facts


def overseer_blocks_4(root: Path, slug: str) -> int:
    count = 0
    try:
        lines = (root / OVERSEER_ROWS_REL).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        # A test gap counts as much as a BLOCK on #4 did: since board 077 it is a PASS with `test_gaps`.
        if isinstance(row, dict) and row.get("slice") == slug and (
                (row.get("verdict") == "BLOCK" and row.get("check") == 4) or row.get("test_gaps")):
            count += 1
    return count


def history(root: Path, slug: str) -> JsonObj:
    """What the testing of one slice showed: the facts O4 and the manager read about earlier slices."""
    decision = last(root, slug, "decision", point="a")
    handins = [r for r in rows(root, slug, "handin") if r.get("accepted")]
    rounds = rows(root, slug, "round")
    outcomes = [str(item.get("verdict")) for r in rounds for item in r.get("items", [])]
    try:
        text = contract_path(root, slug).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return {
        "slice": slug, "decision_a": decision.get("decision") if decision else None,
        "hardest_seams": len(re.findall(r"^\s*[-*]\s*\*\*(.+?)\*\*", section(text, "Hardest seams"), re.MULTILINE)),
        "ratified_thresholds": sum(1 for line in section(text, "Exit criterion").splitlines() if RATIFIED_RE.search(line)),
        "invariants": invariant_facts(text),
        "questions_to_contract": sum(len(r.get("questions", [])) for r in handins),
        "dispute_outcomes": outcomes, "code_was_wrong": "test_right" in outcomes,
        "contract_ambiguous": "contract_ambiguous" in outcomes,
        "overseer_blocks_check_4": overseer_blocks_4(root, slug), "parked": last(root, slug, "parked") is not None,
    }


def block_facts(root: Path, slug: str) -> JsonObj:
    """Where the slice stands in its feature: consumers, the tracer mark, its block and what of it is built."""
    found = feature_of(root, slug)
    if found is None:
        return {"feature": None, "note": "no feature artifact names this slice: it stands alone, one block"}
    feature, item = found
    block = feature.block_of(item)
    done = [s for s in feature.slices if s.id != item.id and finished(root, s)]
    done_ids = {s.id for s in done}
    others = [s for s in feature.slices if s.id != item.id]
    neighbours = {b if a in {s.id for s in block} else a for a, b in feature.edges
                  if (a in {s.id for s in block}) != (b in {s.id for s in block})}
    ready_blocks = sorted({s.block for s in feature.slices if s.id in neighbours and s.block != item.block
                           and all(o.id in done_ids for o in feature.slices if o.block == s.block)})
    earlier = [slug_of(root, s) for s in block if s.id in done_ids]
    return {
        "feature": feature.name, "slice_id": item.id, "tracer_bullet": item.tracer,
        "consumers": sorted(b for a, b in feature.edges if a == item.id), "public_contract": item.public,
        "block": item.block, "blocks_of_feature": feature.blocks(),
        "block_slices": [s.id for s in block], "block_built": [s.id for s in block if s.id in done_ids],
        "closes_block": all(s.id in done_ids for s in block if s.id != item.id),
        "closes_feature": all(s.id in done_ids for s in others),
        "connected_blocks": sorted({s.block for s in feature.slices if s.id in neighbours}),
        "connected_ready_blocks": ready_blocks,
        "earlier_in_block": [history(root, s) for s in earlier if s],
        "acceptance_criteria": feature.acceptance,
    }


def facts_a(root: Path, env: dict[str, str], slug: str) -> JsonObj:
    text = contract_path(root, slug).read_text(encoding="utf-8", errors="replace")
    seams = re.findall(r"^\s*[-*]\s*\*\*(.+?)\*\*", section(text, "Hardest seams"), re.MULTILINE)
    ratified = [one_line(line, 300) for line in section(text, "Exit criterion").splitlines() if RATIFIED_RE.search(line)]
    named = named_code(root, env, section(text, "Seam"))
    existing: object = touch(root, env, named, {}) if named else "unknown: the «Seam» names no existing file; decided at point (b) by the diff"
    return {
        "point": "a", "slice": slug, "contract": contract_path(root, slug).relative_to(root).as_posix(),
        "hardest_seams": seams, "ratified_thresholds": ratified, "invariants": invariant_facts(text), **block_facts(root, slug),
        "expected_size": section(text, "Complexity budget") or "the contract has no «Complexity budget»",
        "existing_code_the_slice_changes": existing,
    }


def self_added(root: Path, slug: str) -> int:
    folder = root / ".engine" / "slices"
    count = 0
    for path in sorted(folder.glob(f"{slug}*.md")) if folder.is_dir() else []:
        count += sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if "self-added" in line.lower())
    return count


def branching_functions(root: Path, files: list[str]) -> int:
    import complexity_budget

    count = 0
    for rel in files:
        if not rel.endswith(".py"):
            continue
        try:
            tree = complexity_budget.parse_py((root / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if tree is not None:
            count += sum(1 for cyclomatic, _ in complexity_budget.function_metrics(tree).values() if cyclomatic > 1)
    return count


def open_debts(root: Path) -> list[JsonObj]:
    return debts_of(rows(root, kind="decision"))


def debts_of(decisions: list[JsonObj]) -> list[JsonObj]:
    """Every check a manager deferred and nobody ran since: kind, the event it waits for, whose slice."""
    debts: dict[tuple[str, str], JsonObj] = {}
    for row in decisions:
        if row.get("type") != "decision" or row.get("point") != "b":
            continue
        for kind, entry in (row.get("checks") or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("when") == "now":
                for key in [k for k in debts if k[0] == kind and row.get("events_due") and k[1] in row["events_due"]]:
                    del debts[key]
            elif entry.get("when") == "defer":
                debts[(kind, str(entry.get("until")))] = {"kind": kind, "until": entry.get("until"), "slice": row.get("slice"),
                                                         "since": row.get("utc"), "reason": entry.get("reason", "")}
    return list(debts.values())


def events_due(block: JsonObj) -> list[str]:
    due = []
    if block.get("feature") and block.get("closes_block"):
        due.append(f"block-closed:{block['block']}")
    if block.get("feature") and block.get("closes_feature"):
        due.append("feature-closed")
    return due


def block_slugs(root: Path, slug: str) -> list[str]:
    found = feature_of(root, slug)
    if found is None:
        return [slug]
    return [s for s in (slug_of(root, item) for item in found[0].block_of(found[1])) if s]


def block_base(root: Path, slug: str) -> str:
    """The code before the first slice of the block: the base its changed files are counted from."""
    bases = [str(r["base"]) for s in block_slugs(root, slug) for r in rows(root, s, "opened")]
    return bases[0] if bases else "HEAD"


def block_numbers(root: Path, env: dict[str, str], slug: str) -> JsonObj:
    """Numbers about the whole block — facts for the manager's judgement «is it large», never a limit."""
    code, counts = changed_code(root, env, block_base(root, slug))
    slugs = block_slugs(root, slug)
    return {"slices": len(slugs), "code_lines": counts["code_lines"], "branching_functions": branching_functions(root, sorted(code)),
            "hardest_seams": sum(history(root, s)["hardest_seams"] for s in slugs),
            "ratified_thresholds": sum(history(root, s)["ratified_thresholds"] for s in slugs),
            "slices_tested_after_the_code": sum(1 for s in slugs if history(root, s)["decision_a"] == "builder")}


def facts_b(root: Path, env: dict[str, str], slug: str) -> JsonObj:
    opened = last(root, slug, "opened")
    base = str(opened["base"]) if opened else "HEAD"
    code, counts = changed_code(root, env, base)
    block = block_facts(root, slug)
    due = events_due(block)
    decision = last(root, slug, "decision", point="a")
    runs = [r for r in rows(root, kind="mutation") if r.get("block") == block.get("block")]
    return {
        "point": "b", "slice": slug, "contract": contract_path(root, slug).relative_to(root).as_posix(), "base": base,
        "decision_at_point_a": decision.get("decision") if decision else None,
        "changed": counts | {"branching_functions": branching_functions(root, sorted(code))},
        "block_numbers": block_numbers(root, env, slug),
        "self_added_behaviours": self_added(root, slug), **history(root, slug), **block,
        "events_due": due, "debts": [d | {"due": d["until"] in due} for d in open_debts(root)],
        "mutation_cmd_set": bool(env.get("MUTATION_CMD", "").strip()),
        "last_mutation_run_of_block": runs[-1] if runs else None,
        "changed_code_and_tests": touch(root, env, code, tree_overlay(root)),
    }


# ------------------------------------------------------------------ the mandatory cases and validate


def mandatory(facts: JsonObj) -> dict[str, str]:
    """The mandatory cases the facts trigger: {case: why}. The manager is not shown this — it must
    arrive there itself; `validate` catches it when it does not."""
    fired: dict[str, str] = {}
    untouched = [f["file"] for f in facts.get("existing_code_the_slice_changes", []) if isinstance(f, dict) and not f["touched"]]
    if facts.get("point") == "a":
        if facts.get("hardest_seams"):
            fired["O1"] = f"the contract names {len(facts['hardest_seams'])} hardest seam(s)"
        if facts.get("consumers") or facts.get("public_contract"):
            fired["O2"] = "the output is consumed by " + (", ".join(facts.get("consumers") or []) or "a public contract")
        if facts.get("ratified_thresholds"):
            fired["O3"] = "the exit criterion carries a threshold the owner ratified"
        previous = (facts.get("earlier_in_block") or [])[-1:]
        for item in previous:
            why = [text for flag, text in ((item.get("code_was_wrong"), "a dispute ended «the code was wrong»"),
                                           (item.get("contract_ambiguous") or item.get("questions_to_contract"), "the tester found an ambiguity of the contract"),
                                           (item.get("overseer_blocks_check_4"), "the overseer found a test gap or blocked on check #4")) if flag]
            if why:
                fired["O4"] = f"on the previous slice of the block ({item.get('slice')}): " + "; ".join(why)
        if untouched:
            fired["O8"] = "the slice changes existing code no test touches: " + ", ".join(untouched)
        return fired
    if facts.get("closes_feature"):
        fired["O5"] = "the last block of the feature is closed: integration tests on the acceptance criteria cannot be deferred further"
    for debt in facts.get("debts", []):
        if debt.get("due"):
            fired[f"O6:{debt['kind']}"] = f"the {debt['kind']} check of {debt.get('slice')} was deferred until {debt['until']}, and that has come"
    if facts.get("decision_at_point_a") == "builder" and (facts.get("self_added_behaviours") or facts.get("overseer_blocks_check_4")):
        fired["O7"] = "point (a) said «the builder», and the slice gave a self-added behaviour or a test gap (check #4)"
    untested = [f["file"] for f in facts.get("changed_code_and_tests", []) if not f["touched"]]
    if untested:
        fired["O8"] = "the slice changed working code no test touches: " + ", ".join(untested)
    return fired


def required_now(fired: dict[str, str]) -> dict[str, list[str]]:
    """Point (b): which checks the fired cases demand now, with the cases that demand each."""
    need: dict[str, list[str]] = {}
    for case in fired:
        kind = "integration" if case == "O5" else case.partition(":")[2] if case.startswith("O6") else "catch_up"
        need.setdefault(kind, []).append(case)
    return need


def schema_errors(decision: object, facts: JsonObj) -> list[str]:
    if not isinstance(decision, dict):
        return ["the decision is not a JSON object"]
    errors = []
    if decision.get("point") != facts.get("point") or decision.get("slice") != facts.get("slice"):
        errors.append(f"`point` and `slice` must repeat the request: {facts.get('point')!r}, {facts.get('slice')!r}")
    if not str(decision.get("reason", "")).strip():
        errors.append("`reason` is empty: a decision names the fact it rests on")
    if facts.get("point") == "a":
        if decision.get("decision") not in ("tester", "builder"):
            errors.append("`decision` is `tester` or `builder`")
        elif decision["decision"] == "builder" and not (str(decision.get("small", "")).strip() and str(decision.get("uniform", "")).strip()):
            errors.append("`builder` (do not switch) needs BOTH conditions named: `small` and `uniform`, each a sentence about this slice")
        return errors
    checks = decision.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(KINDS):
        return [*errors, f"`checks` holds exactly these keys: {', '.join(KINDS)}"]
    for kind in KINDS:
        entry = checks[kind]
        if not isinstance(entry, dict) or entry.get("when") not in WHEN or not str(entry.get("reason", "")).strip():
            errors.append(f"`checks.{kind}` needs `when` ({' | '.join(WHEN)}) and a `reason`")
        elif entry["when"] == "defer" and not EVENT_RE.match(str(entry.get("until", ""))):
            errors.append(f"`checks.{kind}.until` names the event: `block-closed:<block>` or `feature-closed`")
        elif entry["when"] == "defer" and entry["until"] in facts.get("events_due", []):
            errors.append(f"`checks.{kind}` is deferred until {entry['until']}, and that event has already come")
    return errors


def violations(decision: JsonObj, facts: JsonObj) -> list[str]:
    """Where the decision contradicts a mandatory case. Empty: the decision is the manager's to make."""
    fired = mandatory(facts)
    if facts.get("point") == "a":
        if decision.get("decision") == "tester":
            return []
        return [f"{case}: {why} — the tester is called, the manager cannot cancel it" for case, why in fired.items()]
    found = []
    checks = decision.get("checks") or {}
    for kind, cases in required_now(fired).items():
        if (checks.get(kind) or {}).get("when") != "now":
            found += [f"{case}: {fired[case]} — `{kind}` is done now, the manager cannot defer or drop it" for case in cases]
    if (checks.get("mutation") or {}).get("when") == "now" and not facts.get("mutation_cmd_set"):
        found.append("mutation: MUTATION_CMD is empty in .claude/project.env — there is nothing to run; the answer is `none`, and the ledger says so")
    return found


def validate(decision: object, facts: JsonObj) -> list[str]:
    errors = schema_errors(decision, facts)
    return errors or violations(decision if isinstance(decision, dict) else {}, facts)


def enforced(decision: JsonObj | None, facts: JsonObj, why: str) -> JsonObj:
    """The decision the script records when the manager's own was refused twice: every mandatory
    case as it must be, and — where nothing is mandatory — the cautious answer (in doubt, the tester)."""
    fired = mandatory(facts)
    base: JsonObj = {"point": facts["point"], "slice": facts["slice"], "by_script": True, "manager_said": decision,
                     "reason": f"written by the script: {why}"}
    if facts["point"] == "a":
        return base | {"decision": "tester"}
    need = required_now(fired)
    given = (decision or {}).get("checks")
    said: JsonObj = given if isinstance(given, dict) else {}
    checks = {}
    for kind in KINDS:
        entry: JsonObj | None = said[kind] if isinstance(said.get(kind), dict) and said[kind].get("when") in WHEN else None
        if kind in need:
            entry = {"when": "now", "reason": "; ".join(fired[c] for c in need[kind])}
        elif entry is None or (kind == "mutation" and entry["when"] == "now" and not facts.get("mutation_cmd_set")) \
                or (entry["when"] == "defer" and (not EVENT_RE.match(str(entry.get("until", ""))) or entry["until"] in facts.get("events_due", []))):
            entry = {"when": "none", "reason": "no valid decision of the manager for this check"}
        checks[kind] = entry
    return base | {"checks": checks}


# ------------------------------------------------------------------ requests


def pending(root: Path) -> JsonObj | None:
    data = read_json(root / PENDING_REL)
    return data if data.get("id") else None


def request_dir(root: Path, request_id: str) -> Path:
    return root / REQUESTS_REL / request_id


def launch_line(request_id: str) -> str:
    return f"{REQUEST_WORD} {request_id}"


def new_request(root: Path, payload: JsonObj) -> JsonObj:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    seed = json.dumps(payload, sort_keys=True, ensure_ascii=False) + str(time.time_ns())
    request_id = f"{stamp}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:6]}"
    request = {"id": request_id, "created_utc": utc_now(), **payload}
    write_json(request_dir(root, request_id) / "request.json", request)
    write_json(root / PENDING_REL, {"id": request_id, "agent": request["agent"], "rejections": 0})
    return request


def unfinished(root: Path, slug: str) -> str | None:
    """Another slice whose point (a) was decided and whose point (b) was not: the next slice does not start."""
    opened = {str(r.get("slice")) for r in rows(root, kind="decision") if r.get("point") == "a"}
    closed = {str(r.get("slice")) for r in rows(root, kind="decision") if r.get("point") == "b"}
    parked = {str(r.get("slice")) for r in rows(root, kind="parked")}
    left = sorted(opened - closed - parked - {slug})
    return left[0] if left else None


def opened_slice(root: Path, task: str) -> str | None:
    """The slice a board task has in hand — the last one opened under it — for the scripts that ask
    which slice is active when no card IN PROGRESS says (gate.active_slice, board 789). It stays the
    task's until the next one opens: its audit may follow point (b). None with no task, with no such
    row (a row written before 789 names no task), for a parked slice and for a contract that is gone."""
    mine = [r for r in rows(root, kind="opened") if task and r.get("task") == task]
    slug = str(mine[-1].get("slice")) if mine else ""
    if not re.fullmatch(r"[\w.-]+", slug) or last(root, slug, "parked") is not None or not contract_path(root, slug).is_file():
        return None
    return slug


def undone(root: Path, slug: str) -> list[str]:
    """The checks the manager said to do NOW at point (b) of this slice that nobody did since:
    a decision is not the check. Empty when there is no such decision or everything was done."""
    every = rows(root)
    at = max((i for i, r in enumerate(every) if r.get("type") == "decision" and r.get("slice") == slug and r.get("point") == "b"), default=None)
    if at is None or last(root, slug, "parked") is not None:
        return []
    later = [r for r in every[at + 1:] if r.get("slice") == slug]
    checks = every[at].get("checks") or {}
    done = {"catch_up": any(r.get("type") == "handin" and r.get("accepted") and r.get("mode") == "contract" for r in later),
            "integration": any(r.get("type") == "handin" and r.get("accepted") and r.get("mode") == "block" for r in later),
            "mutation": any(r.get("type") == "mutation" for r in later)}
    how = {"catch_up": f"`testing.py request {slug} --tester contract`", "integration": f"`testing.py request {slug} --tester block`",
           "mutation": f"`testing.py mutation {slug}`"}
    return [f"{kind} of {slug}: the manager said «now», and it was not done ({how[kind]})" for kind in KINDS
            if (checks.get(kind) or {}).get("when") == "now" and not done[kind]]


def request_manager(root: Path, env: dict[str, str], slug: str, point: str) -> tuple[int, str]:
    if not contract_path(root, slug).is_file():
        return 2, f"no such contract: .engine/slices/{slug}.md"
    if not contract_sealed(root, slug):
        return 1, (f"REFUSED: the contract of {slug} is not sealed (`contract_fingerprint.py seal`). A slice without a sealed "
                   "contract is built as before: there is nothing for the manager to judge.")
    if last(root, slug, "decision", point=point) is not None:
        return 1, f"REFUSED: point ({point}) of {slug} already has its decision (`testing.py status {slug}`)."
    if point == "a":
        other = unfinished(root, slug)
        if other:
            return 3, (f"BLOCKED: the slice {other} has no decision of point (b). The next slice does not start before it: "
                       f"`python3 .claude/hooks/testing.py request {other} --point b`.")
        owed = [line for name in sorted({str(r.get("slice")) for r in rows(root, kind="decision")} - {slug}) for line in undone(root, name)]
        if owed:
            return 3, "BLOCKED: the next slice does not start while a check decided at point (b) is not done:\n- " + "\n- ".join(owed)
        if last(root, slug, "opened") is None:
            head = test_touch.git(root, "rev-parse", "HEAD").stdout.strip()
            import gate

            task = gate.work_in_hand(root)   # whose slice it is: gate.active_slice reads it (board 789)
            append_row(root, {"type": "opened", "slice": slug, "base": head, "task": task}, f"{slug} — the slice opens",
                       [f"the code before it: {head[:12]}", f"the board task: {task or 'none'}"])
        facts = facts_a(root, env, slug)
    else:
        if last(root, slug, "decision", point="a") is None:
            return 1, f"REFUSED: point (a) of {slug} was never decided; point (b) follows it."
        facts = facts_b(root, env, slug)
    request = new_request(root, {"agent": MANAGER, "point": point, "slice": slug, "facts": facts})
    return 0, launch_line(str(request["id"]))


def rounds_of(root: Path, slug: str) -> int:
    return len(rows(root, slug, "round"))


def park_slice(root: Path, slug: str) -> str:
    """The third round parks the slice with both earlier rounds; the work goes on with the next one."""
    earlier = [f"round {i}: " + "; ".join(f"{item.get('test')} — {item.get('verdict')}" for item in r.get("items", []))
               for i, r in enumerate(rows(root, slug, "round"), 1)]
    append_row(root, {"type": "parked", "slice": slug, "rounds": earlier}, f"{slug} — PARKED after {MAX_ROUNDS} rounds of dispute",
               [*earlier, "a third round is not held: the slice waits for the owner, the work goes on with the next unblocked slice"])
    board = root / ".claude" / "unattended" / "board.py"
    if board.is_file() and (root / "tasks").is_dir():
        subprocess.run(
            [sys.executable, str(board), "open-item", "--to", "blocked", "--key", f"testing-parked-{slug}", "--source", "hook testing.py",
             "--title", f"slice {slug}: третя суперечка про contract tests",
             "--what", (f"Два кола суперечки між builder-ом і tester-ом не розв'язали slice {slug}: " + " | ".join(earlier)
                        + ". Третє коло не проводиться: slice відкладено, робота йде далі з наступним. Обидва кола стоять у .engine/testing/ledger.md."),
             "--question", f"Хто правий у суперечці про тести slice-а {slug} — тест, код чи slice contract слід уточнити?"],
            cwd=root, capture_output=True, text=True, check=False)
    return f"PARKED: {slug} had {MAX_ROUNDS} rounds of dispute already; the third parks the slice. Go on with the next unblocked slice."


def request_tester(root: Path, slug: str, mode: str, package: Path | None) -> tuple[int, str]:
    if not contract_path(root, slug).is_file():
        return 2, f"no such contract: .engine/slices/{slug}.md"
    a, b = last(root, slug, "decision", point="a"), last(root, slug, "decision", point="b")
    payload: JsonObj = {"agent": TESTER, "mode": mode, "slice": slug, "contract": f".engine/slices/{slug}.md"}
    if mode == "contract":
        catch_up = b is not None and (b.get("checks") or {}).get("catch_up", {}).get("when") == "now"
        if not catch_up and (a is None or a.get("decision") != "tester"):
            return 1, (f"REFUSED: nobody decided that {slug} needs the tester. The manager decides at point (a) "
                       f"(`testing.py request {slug} --point a`); the tester does not decide whether it is called.")
        code_exists = catch_up or a is None or a.get("decision") != "tester"
        payload |= {"expect": "recorded" if code_exists else "red",
                    "note": ("CATCH-UP: the code exists. You do not read it — the contract and the public signatures only." if code_exists
                             else "No implementation exists: the skeleton only."),
                    "untested_code": [f["file"] for f in (read_json(request_dir(root, str(b.get("request"))) / "request.json").get("facts", {})
                                                          .get("changed_code_and_tests", []) if b else []) if not f["touched"]]}
    elif mode == "objection":
        if package is None or not package.is_file():
            return 2, "an objection is one package: --package FILE (every disputed test, its contract line, why)"
        if last(root, slug, "parked") is not None or rounds_of(root, slug) >= MAX_ROUNDS:
            return 3, park_slice(root, slug) if last(root, slug, "parked") is None else f"PARKED: {slug} is parked already."
        payload |= {"round": rounds_of(root, slug) + 1, "package": package.read_text(encoding="utf-8", errors="replace"),
                    "sealed": sorted(read_json(root / SEALS_REL / f"{slug}.json").get("files", {}))}
    else:
        if b is None or (b.get("checks") or {}).get("integration", {}).get("when") != "now":
            return 1, f"REFUSED: integration tests are written when the manager said `integration: now` at point (b) of {slug}."
        found = feature_of(root, slug)
        payload |= {"feature": f"{FEATURES_REL.as_posix()}/{found[0].name}.md" if found else None,
                    "block": found[1].block if found else None, "expect": "recorded"}
    request = new_request(root, payload)
    return 0, launch_line(str(request["id"]))


# ------------------------------------------------------------------ guard (PreToolUse)


def deny(reason: str) -> JsonObj:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def guard(root: Path, envelope: JsonObj) -> JsonObj | None:
    tool = str(envelope.get("tool_name", ""))
    raw_input = envelope.get("tool_input")
    tool_input: JsonObj = raw_input if isinstance(raw_input, dict) else {}
    inside = envelope.get("agent_type")
    if inside == MANAGER and (tool in EDIT_TOOLS or tool in AGENT_TOOLS):
        return deny(f"The testing manager decides and writes nothing: {tool} is refused. Its decision is its answer; testing.py records it.")
    if inside == TESTER:
        if tool in AGENT_TOOLS:
            return deny("The tester starts no agent.")
        target = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        real = Path(os.path.realpath(target))  # not resolve(): up to Python 3.12 it raises RuntimeError on a symlink loop
        rel = real.relative_to(root).as_posix() if target and real.is_relative_to(root) else target
        if tool in EDIT_TOOLS and not test_touch.is_test_path(rel):
            return deny(f"The tester writes test files only: {rel} is not one. It does not write the implementation and does not edit the contract.")
        return None
    if tool not in AGENT_TOOLS or tool_input.get("subagent_type") not in AGENTS:
        return None
    agent = str(tool_input["subagent_type"])
    waiting = pending(root)
    if waiting is None or waiting.get("agent") != agent:
        return deny(f"No request is pending for the agent `{agent}`, so it is not started. A request is made by the script: "
                    "`python3 .claude/hooks/testing.py request <slug> --point a|b` (the manager) or `… --tester contract|objection|block` "
                    "(the tester). Whether the tester is called is the manager's decision, not the builder's.")
    line = launch_line(str(waiting["id"]))
    if str(tool_input.get("prompt", "")).strip() != line:
        return deny(f"The agent `{agent}` is started with exactly this prompt and nothing else: `{line}`. It reads the request itself; "
                    "anything added to the prompt would be the builder speaking to the one who checks it.")
    return None


# ------------------------------------------------------------------ running tests


@dataclass
class Run:
    test: str
    code: int | None
    output: str

    @property
    def outcome(self) -> str:
        if self.code is None:
            return "no result (time limit)"
        if self.code in CANNOT_RUN:
            return f"could not run (exit {self.code})"
        if self.code == 0:
            return "passed"
        return "not a test failure (import or collection)" if NOT_A_TEST_RE.search(self.output) else "failed"

    def tail(self) -> str:
        return " | ".join(self.output.strip().splitlines()[-3:])[:300]


def run_test(root: Path, template: str, test: str) -> Run:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"PYTHONDONTWRITEBYTECODE": "1"}
    try:
        done = subprocess.run(["bash", "-c", template.replace("{test}", test)], cwd=root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace", timeout=RUN_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return Run(test, None, "")
    return Run(test, done.returncode, done.stdout)


# ------------------------------------------------------------------ the tester's hand-in


def parse_answer(text: str) -> tuple[JsonObj | None, str]:
    """The last JSON object of the answer (in a ```json fence or bare)."""
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    for candidate in [*reversed(fenced), text[text.find("{"):text.rfind("}") + 1] if "{" in text else ""]:
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj, ""
    return None, "the answer holds no JSON object: answer with the one object the definition describes, in a ```json fence"


def in_text(needle: str, haystack: str) -> bool:
    return bool(one_line(needle, 10_000)) and one_line(needle, 10_000) in one_line(haystack, 10_000_000)


def handin_errors(root: Path, request: JsonObj, handin: JsonObj) -> list[str]:
    """What is wrong with the shape of a contract or block hand-in, before anything is run."""
    errors = []
    tests = handin.get("tests")
    if handin.get("mode") != request.get("mode") or handin.get("slice") != request.get("slice"):
        errors.append(f"`mode` and `slice` must repeat the request: {request.get('mode')!r}, {request.get('slice')!r}")
    if "{test}" not in str(handin.get("run", "")):
        errors.append("`run` is the command that runs ONE test, with `{test}` where the test's id goes")
    if not isinstance(tests, list) or not tests or not all(isinstance(t, dict) for t in tests):
        return [*errors, "`tests` is a non-empty list of objects"]
    questions = handin.get("questions", [])
    if not isinstance(questions, list) or not all(isinstance(q, dict) and str(q.get("id", "")).strip() and str(q.get("text", "")).strip()
                                                  and str(q.get("reading_taken", "")).strip() for q in questions):
        return [*errors, "`questions` is a list of {id, text, reading_taken} — or an empty list"]
    known = {str(q["id"]) for q in questions}
    sources = [contract_path(root, str(request["slice"])).read_text(encoding="utf-8", errors="replace")]
    if request.get("feature"):
        sources.append((root / str(request["feature"])).read_text(encoding="utf-8", errors="replace"))
    seen: set[str] = set()
    by_file: dict[str, set[bool]] = {}
    for test in tests:
        name = str(test.get("test", "")).strip()
        rel = str(test.get("file", "")).strip()
        if not name or not str(test.get("behaviour", "")).strip():
            errors.append("every test has `test` (its id for `run`) and `behaviour`")
            continue
        if name in seen:
            errors.append(f"{name}: listed twice — one test per behaviour")
        seen.add(name)
        if not any(in_text(str(test.get("contract_line", "")), source) for source in sources):
            errors.append(f"{name}: `contract_line` is not a line of the contract, word for word — a behaviour with no line "
                          "behind it is an invented requirement and is not accepted")
        if not rel or not (root / rel).is_file() or not test_touch.is_test_path(rel):
            errors.append(f"{name}: `file` {rel or '(none)'} is not an existing test file")
        if test.get("question") is not None and str(test.get("question")) not in known:
            errors.append(f"{name}: `question` {test.get('question')!r} is not the id of one of `questions`")
        if request.get("expect") == "recorded" and not str(test.get("catches", "")).strip():
            errors.append(f"{name}: the code exists, so RED cannot be shown — `catches` names the breakage this test would catch")
        by_file.setdefault(rel, set()).add(test.get("question") is not None)
    if request.get("mode") == "contract":
        errors += invariant_test_errors(sources[0], seen)
    for rel, kinds in by_file.items():
        if len(kinds) > 1:
            errors.append(f"{rel}: holds both disputed and undisputed tests — a disputed test (one that depends on a question to the "
                          "contract) goes into a file of its own: whole files are sealed, and that one is not sealed before the answer")
    return errors


def invariant_test_errors(contract: str, tests: set[str]) -> list[str]:
    """Every invariant of the contract has a test with its number in the name (`test_I1_…`), and no
    test carries a number the contract does not have: the tester does not add invariants of its
    own. A contract without the section (sealed before it existed) is not judged here."""
    found = invariants(contract)
    if found["section"] == "absent":
        return []
    named = {i["id"] for i in found["items"]}
    tested: dict[str, list[str]] = {}
    for name in sorted(tests):
        for ident in INVARIANT_TEST_RE.findall(name):
            tested.setdefault(ident, []).append(name)
    errors = [f"{ident}: the contract names this invariant and no test carries its number — one test named `test_{ident}_…`, on inputs "
              "you choose from its «Domain»" for ident in sorted(named - set(tested), key=lambda i: int(i[1:]))]
    errors += [f"{', '.join(names)}: the contract has no invariant {ident} — "
               + ("its «Invariants» section says `None`, so no invariant test is written; " if found["section"] == "none" else "")
               + "the tester does not add an invariant of its own: a rule that seems missing is a question to the contract"
               for ident, names in sorted(tested.items()) if ident not in named]
    return errors


def red_errors(root: Path, request: JsonObj, handin: JsonObj) -> tuple[list[str], list[JsonObj]]:
    """Run every test. Before code exists each must FAIL in its body; one marked `keeps` must pass."""
    errors, results = [], []
    for test in handin["tests"]:
        run = run_test(root, str(handin["run"]), str(test["test"]))
        results.append({"test": test["test"], "outcome": run.outcome, "keeps": bool(test.get("keeps"))})
        if run.outcome not in ("passed", "failed"):
            errors.append(f"{test['test']}: {run.outcome} — that is not a result of the test ({run.tail()})")
        elif request.get("expect") != "red":
            continue
        elif test.get("keeps") and run.outcome != "passed":
            errors.append(f"{test['test']}: marked `keeps` (behaviour the contract tells to preserve), so it must pass before the change — it fails ({run.tail()})")
        elif not test.get("keeps") and run.outcome == "passed":
            errors.append(f"{test['test']}: PASSES against the skeleton — a contract test that is green before the code exists is broken "
                          "(or the implementation is already there). Mark it `keeps` only if the contract tells to preserve that behaviour")
    return errors, results


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_files(root: Path, slug: str, files: list[str], held: dict[str, list[str]]) -> None:
    path = root / SEALS_REL / f"{slug}.json"
    state = read_json(path)
    sealed = dict(state.get("files", {})) | {rel: digest(root / rel) for rel in files}
    kept = {rel: qs for rel, qs in (dict(state.get("held", {})) | held).items() if rel not in files}
    write_json(path, {"slice": slug, "files": sealed, "held": kept})


def record_tests(root: Path, request: JsonObj, handin: JsonObj) -> list[str]:
    """A contract or block hand-in: shape, the run, the seal. Returns the reasons it is refused."""
    errors = handin_errors(root, request, handin)
    if errors:
        return errors
    errors, results = red_errors(root, request, handin)
    if errors:
        return errors
    slug = str(request["slice"])
    held: dict[str, list[str]] = {}
    for test in handin["tests"]:
        if test.get("question") is not None:
            held.setdefault(str(test["file"]), []).append(str(test["question"]))
    files = sorted({str(t["file"]) for t in handin["tests"]} - set(held))
    seal_files(root, slug, files, {rel: sorted(set(qs)) for rel, qs in held.items()})
    failing = [r["test"] for r in results if r["outcome"] == "failed"]
    questions = handin.get("questions", [])
    lines = [f"{len(handin['tests'])} test(s), one per behaviour; sealed: {', '.join(files) or 'nothing'}"]
    tested = sorted({i for t in handin["tests"] for i in INVARIANT_TEST_RE.findall(str(t["test"]))}, key=lambda i: int(i[1:]))
    if request["mode"] == "contract" and tested:
        lines.append(f"a test for every invariant of the contract: {', '.join(tested)}")
    lines += [f"question to the contract {q['id']}: {one_line(q['text'], 300)} — reading taken: {one_line(q['reading_taken'], 200)}" for q in questions]
    lines += [f"NOT SEALED until its question is answered: {rel} ({', '.join(qs)})" for rel, qs in held.items()]
    if request.get("expect") == "red":
        lines.append("RED run by the script: every test fails in its body" + ("; `keeps`: " + ", ".join(str(t["test"]) for t in handin["tests"] if t.get("keeps"))
                                                                              if any(t.get("keeps") for t in handin["tests"]) else ""))
    elif failing:
        lines.append("FINDING — these tests fail against the code that exists; they go to the builder as one package: " + ", ".join(failing))
    else:
        lines.append("the code exists: every test passes; what each would catch is written in the hand-in")
    append_row(root, {"type": "handin", "slice": slug, "mode": request["mode"], "accepted": True, "request": request["id"],
                      "expect": request.get("expect"), "tests": handin["tests"], "results": results, "run": handin["run"],
                      "questions": questions, "sealed": files, "held": held, "failing": failing},
               f"{slug} — the tester's hand-in ({request['mode']}{', catch-up' if request['mode'] == 'contract' and request.get('expect') == 'recorded' else ''})", lines)
    return []


def record_objection(root: Path, request: JsonObj, answer: JsonObj) -> list[str]:
    items = answer.get("items")
    if answer.get("mode") != "objection" or answer.get("slice") != request.get("slice"):
        return [f"`mode` and `slice` must repeat the request: 'objection', {request.get('slice')!r}"]
    if not isinstance(items, list) or not items or not all(
            isinstance(i, dict) and str(i.get("test", "")).strip() and i.get("verdict") in VERDICTS and str(i.get("reason", "")).strip() for i in items):
        return [f"`items` is a non-empty list of {{test, verdict, reason}}; verdict is one of: {', '.join(VERDICTS)}"]
    slug = str(request["slice"])
    state = read_json(root / SEALS_REL / f"{slug}.json")
    changed = [rel for rel, value in state.get("files", {}).items() if not (root / rel).is_file() or digest(root / rel) != value]
    if changed and not any(i["verdict"] == "test_wrong" for i in items):
        return [f"sealed test files changed ({', '.join(changed)}) though no item says `test_wrong`: a test is corrected only when it is wrong"]
    seal_files(root, slug, [rel for rel in changed if (root / rel).is_file()], {})
    words = {"test_wrong": "the test was wrong — corrected, sealed anew", "test_right": "THE TEST WAS RIGHT — a real error in the code, the builder fixes the code",
             "contract_ambiguous": "the contract is ambiguous — the question goes to the slice planner"}
    append_row(root, {"type": "round", "slice": slug, "round": request.get("round"), "request": request["id"], "items": items, "resealed": changed},
               f"{slug} — dispute, round {request.get('round')} of {MAX_ROUNDS}",
               [f"{i['test']}: {words[i['verdict']]} — {one_line(i['reason'], 300)}" for i in items])
    return []


# ------------------------------------------------------------------ the manager's decision


def review_numbers(root: Path, slugs: set[str]) -> str:
    """What the live slices showed about invariants, as far as a script can count it: the review
    task carries these numbers to the owner's two questions (stateful testing; the library)."""
    named = [history(root, slug)["invariants"] for slug in sorted(slugs)]
    tested = {str(r.get("slice")) for r in rows(root, kind="handin") if r.get("accepted") and r.get("mode") == "contract"} & slugs
    late = sum(len(r.get("failing", [])) for r in rows(root, kind="handin") if r.get("accepted") and r.get("slice") in tested and r.get("mode") == "block")
    return (f"Invariants: записано {sum(n['count'] for n in named)} у {sum(1 for n in named if n['section'] == 'named')} slice-ах; "
            f"«немає — причина» — {sum(1 for n in named if n['section'] == 'none')}; slice contract без розділу — "
            f"{sum(1 for n in named if n['section'] == 'absent')}. Помилки в коді, який уже пройшов contract tests tester-а ({len(tested)} slice-ів): "
            f"overseer заблокував за перевіркою №4 — {sum(overseer_blocks_4(root, slug) for slug in sorted(tested))}; "
            f"інтеграційних тестів упало — {late}.")


def review_task(root: Path) -> None:
    """After ten slices with a decision of the manager: a review task on the board — once."""
    done = {str(r.get("slice")) for r in rows(root, kind="decision") if r.get("point") == "b"}
    if len(done) < REVIEW_AFTER or rows(root, kind="review_task"):
        return
    board = root / ".claude" / "unattended" / "board.py"
    if board.is_file() and (root / "tasks").is_dir():
        subprocess.run(
            [sys.executable, str(board), "open-item", "--to", "proposed", "--key", "testing-review", "--source", "hook testing.py",
             "--title", "розбір тестування після десяти slice-ів",
             "--what", f"У журналі тестування .engine/testing/ledger.md набралося {len(done)} slice-ів із рішенням test manager-а. " + review_numbers(root, done),
             "--do", ("Розбір, а не вирок: що впіймали незалежні тести, чого не впіймано понад overseer-а, де test manager помилився (скільки разів "
                      "«не перемикатися» довелося наздоганяти). Результат — пропозиції змін до визначень test-manager і slice-tester; затверджує власник. "
                      "Окремо порахуй і покажи у звіті, що показали живі slices про invariants: скільки помилок знайдено на входах, яких не було "
                      "серед прикладів tester-а (числа вище рахує скрипт; до них додай записи .engine/bugs/ про код цих slices — прочитай кожен і "
                      "скажи, чи був той вхід в області якогось invariant). Розбір закінчи двома питаннями до власника, кожне з цими числами і з "
                      "посиланням на звіт spike tasks/done/063-property-tests-spike/report.md: (1) «Чи братися за stateful testing — invariants на "
                      "кілька slices, перевірка послідовностями операцій?» (відкладено відповіддю 5 на задачу 048); (2) «Чи повертатися до бібліотеки "
                      "property-based testing?» (spike 063: приклади з розділом «Invariants» ловили стільки ж, скільки бібліотека; повний проєкт — "
                      "tasks/done/048-property-tests-design/report.md, розділ 9).")],
            cwd=root, capture_output=True, text=True, check=False)
    append_row(root, {"type": "review_task", "slices": sorted(done)}, "review after ten slices", [f"{len(done)} slices have a decision; the review task is on the board"])


def decision_lines(decision: JsonObj, facts: JsonObj, fired: dict[str, str]) -> list[str]:
    lines = []
    if decision.get("by_script"):
        lines.append("WRITTEN BY THE SCRIPT — the manager's own decision was refused: " + one_line(json.dumps(decision.get("manager_said"), ensure_ascii=False), 300))
    lines += [f"mandatory case {case}: {why}" for case, why in fired.items()]
    if facts["point"] == "a":
        named = facts.get("invariants")
        if isinstance(named, dict):
            lines.append({"absent": "invariants: not named — the contract was sealed before the section existed",
                          "none": f"invariants: none — {named.get('none_reason', '')}"}.get(
                              str(named.get("section")), f"invariants: {named.get('count')} ({', '.join(named.get('ids', []))})"))
        lines.append(("the tester writes the contract tests" if decision["decision"] == "tester" else "NOT SWITCHING — the builder writes the tests")
                     + f": {one_line(decision['reason'])}")
        if decision["decision"] == "builder":
            lines += [f"small: {one_line(decision.get('small'))}", f"uniform: {one_line(decision.get('uniform'))}"]
        return lines
    for kind in KINDS:
        entry = decision["checks"][kind]
        when = {"now": "NOW", "none": "not needed", "defer": f"DEFERRED until {entry.get('until')} (a debt)"}[entry["when"]]
        lines.append(f"{kind}: {when} — {one_line(entry['reason'], 300)}")
    if decision.get("block_large") and facts.get("closes_block") and not facts.get("mutation_cmd_set"):
        lines.append(f"a large block ({facts.get('block')}) WITHOUT a mutation check: MUTATION_CMD is not set")
    return lines


def record_decision(root: Path, request: JsonObj, decision: JsonObj) -> None:
    facts = request["facts"]
    fired = mandatory(facts)
    slug = str(facts["slice"])
    row = {k: decision.get(k) for k in ("point", "slice", "decision", "reason", "small", "uniform", "checks", "block_large", "by_script", "manager_said")
           if decision.get(k) is not None}
    append_row(root, {"type": "decision", **row, "request": request["id"], "mandatory": fired, "events_due": facts.get("events_due", []),
                      "block": facts.get("block"), "feature": facts.get("feature"),
                      **({"invariants": facts["invariants"]} if isinstance(facts.get("invariants"), dict) else {})},
               f"{slug} — the manager's decision, point ({facts['point']})", decision_lines(decision, facts, fired))
    if facts["point"] == "b":
        review_task(root)


# ------------------------------------------------------------------ record (SubagentStop, or by hand while not wired)


def record(root: Path, agent: str, text: str) -> tuple[int, str]:
    """Record the answer of the agent the pending request was made for. (0, note) recorded;
    (1, reasons) refused once — the same agent may answer again; (3, note) refused for good."""
    waiting = pending(root)
    if waiting is None or waiting.get("agent") != agent:
        return 0, ""
    request = read_json(request_dir(root, str(waiting["id"])) / "request.json")
    answer, problem = parse_answer(text)
    again = int(waiting.get("rejections", 0)) > 0
    if agent == MANAGER:
        errors = [problem] if answer is None else validate(answer, request["facts"])
        if errors and not again:
            write_json(root / PENDING_REL, waiting | {"rejections": 1})
            return 1, "The decision is refused:\n- " + "\n- ".join(errors) + "\nAnswer again with the corrected decision, the JSON object only."
        final = enforced(answer, request["facts"], "; ".join(errors)) if errors else answer
        assert final is not None
        record_decision(root, request, final)
        (root / PENDING_REL).unlink(missing_ok=True)
        return 0, f"recorded: point ({request['point']}) of {request['slice']}" + (" — by the script, the manager's decision was refused twice" if errors else "")
    errors = [problem] if answer is None else (record_objection if request.get("mode") == "objection" else record_tests)(root, request, answer)
    if not errors:
        (root / PENDING_REL).unlink(missing_ok=True)
        return 0, f"recorded: the tester's hand-in for {request['slice']} ({request.get('mode')})"
    if not again:
        write_json(root / PENDING_REL, waiting | {"rejections": 1})
        return 1, "The hand-in is refused:\n- " + "\n- ".join(errors) + "\nCorrect it and answer again with the JSON object."
    append_row(root, {"type": "handin", "slice": request.get("slice"), "mode": request.get("mode"), "accepted": False, "request": request["id"], "errors": errors},
               f"{request.get('slice')} — the tester's hand-in REFUSED", [one_line(e, 300) for e in errors])
    (root / PENDING_REL).unlink(missing_ok=True)
    return 3, "The hand-in was refused twice and is not accepted:\n- " + "\n- ".join(errors) + "\nA fresh tester is asked: make the request again."


def handed_back(envelope: JsonObj) -> str:
    text = str(envelope.get("last_assistant_message") or "")
    if text:
        return text
    try:
        import overseer_verdict

        return overseer_verdict._handed_back(envelope.get("agent_transcript_path"))
    except (ImportError, OSError, ValueError, AttributeError):
        return ""


def record_hook(root: Path, envelope: JsonObj) -> JsonObj | None:
    agent = str(envelope.get("agent_type", ""))
    if agent not in AGENTS or envelope.get("hook_event_name") not in (None, "SubagentStop"):
        return None
    code, note = record(root, agent, handed_back(envelope))
    return {"decision": "block", "reason": note} if code == 1 else None


# ------------------------------------------------------------------ questions, seals, the audit gate


def answer_question(root: Path, slug: str, question: str, reading: str, text: str) -> tuple[int, str]:
    state = read_json(root / SEALS_REL / f"{slug}.json")
    if not any(question in qs for qs in state.get("held", {}).values()):
        return 1, f"REFUSED: no unsealed test of {slug} waits for the question {question}."
    append_row(root, {"type": "answer", "slice": slug, "question": question, "reading": reading, "text": text},
               f"{slug} — the planner answers the question {question}",
               [("the reading the test took stands" if reading == "taken" else "THE OTHER READING — the disputed test is rewritten by a fresh tester") + f": {one_line(text, 300)}"])
    return 0, f"recorded; now `python3 .claude/hooks/testing.py seal {slug}`"


def answers(root: Path, slug: str) -> dict[str, str]:
    return {str(r["question"]): str(r["reading"]) for r in rows(root, slug, "answer")}


def seal_held(root: Path, slug: str) -> tuple[int, str]:
    """Seal the files that waited for answers. Only a file whose every question was answered with
    the reading its test took; another reading means the file is rewritten by a fresh tester first."""
    state = read_json(root / SEALS_REL / f"{slug}.json")
    given = answers(root, slug)
    ready, waiting, other = [], [], []
    for rel, questions in state.get("held", {}).items():
        if any(q not in given for q in questions):
            waiting.append(f"{rel} ({', '.join(q for q in questions if q not in given)})")
        elif any(given[q] != "taken" for q in questions):
            other.append(rel)
        else:
            ready.append(rel)
    if ready:
        seal_files(root, slug, ready, {})
        ledger(root, f"{slug} — sealed after the answers", [f"{rel}: its questions were answered with the reading the test took" for rel in ready])
    if other:
        return 3, (f"NOT SEALED: {', '.join(other)} — the planner chose the other reading, so the test is wrong as written. A fresh tester "
                   f"rewrites it: `python3 .claude/hooks/testing.py request {slug} --tester contract`.")
    if waiting:
        return 3, "NOT SEALED, waiting for the answer to: " + "; ".join(waiting)
    return 0, f"sealed: {', '.join(ready) or 'nothing was waiting'}"


def check_seal(root: Path, slug: str) -> tuple[int, str]:
    state = read_json(root / SEALS_REL / f"{slug}.json")
    files = state.get("files", {})
    if not files:
        return 4, f"no sealed contract tests for {slug}"
    changed = [rel for rel, value in files.items() if not (root / rel).is_file() or digest(root / rel) != value]
    if changed:
        return 3, (f"CHANGED: the sealed contract tests of {slug} differ from what the tester handed in: {', '.join(changed)}. The builder "
                   "does not edit them. An objection goes as one package: `python3 .claude/hooks/testing.py request "
                   f"{slug} --tester objection --package FILE`.")
    return 0, f"match: {len(files)} sealed test file(s) of {slug}"


def audit_block(root: Path, slug: str | None) -> str | None:
    """Why no audit is requested for this slice yet; None when testing does not stand in the way.
    overseer_stop.py asks before it makes an audit request. A slice without a sealed contract is
    built as before."""
    if not slug or not contract_path(root, slug).is_file() or not contract_sealed(root, slug):
        return None
    decision = last(root, slug, "decision", point="a")
    if decision is None:
        return (f"the slice {slug} has a sealed contract and no decision of the testing manager at point (a): who writes its contract "
                f"tests was never decided. Run `python3 .claude/hooks/testing.py request {slug} --point a` and start the agent `{MANAGER}` "
                "with the line it prints")
    request = read_json(request_dir(root, str(decision.get("request"))) / "request.json")
    broken = violations(decision, request["facts"]) if request.get("facts") else []
    if broken:
        return f"the recorded decision of point (a) for {slug} contradicts a mandatory case: " + "; ".join(broken)
    catch_up = last(root, slug, "decision", point="b")
    needs = decision.get("decision") == "tester" or (catch_up is not None and (catch_up.get("checks") or {}).get("catch_up", {}).get("when") == "now")
    if not needs:
        return None
    accepted = [r for r in rows(root, slug, "handin") if r.get("accepted") and r.get("mode") == "contract"]
    if not accepted:
        return (f"the testing manager decided that the independent tester writes the contract tests of {slug}, and no hand-in of the "
                f"tester was accepted. Run `python3 .claude/hooks/testing.py request {slug} --tester contract` and start the agent `{TESTER}`")
    code, note = check_seal(root, slug)
    if code == 3:
        return note
    held = read_json(root / SEALS_REL / f"{slug}.json").get("held", {})
    if held:
        return (f"contract tests of {slug} still wait for answers to the tester's questions to the contract and are not sealed: "
                + "; ".join(f"{rel} ({', '.join(qs)})" for rel, qs in held.items())
                + f". The slice planner answers (`testing.py answer {slug} <Q> --reading taken|other --text …`), then `testing.py seal {slug}`")
    return None


def feature_close(root: Path, name: str) -> tuple[int, str]:
    path = root / FEATURES_REL / f"{name}.md"
    if not path.is_file():
        return 2, f"no such feature artifact: {path.relative_to(root)}"
    feature = parse_feature(name, path.read_text(encoding="utf-8", errors="replace"))
    problems = []
    for item in feature.slices:
        slug = slug_of(root, item)
        if slug and contract_sealed(root, slug) and last(root, slug, "decision", point="b") is None and last(root, slug, "parked") is None:
            problems.append(f"{item.id} ({slug}): no decision of point (b)")
        problems += undone(root, slug) if slug else []
    due = {"feature-closed"} | {f"block-closed:{b}" for b in feature.blocks()}
    ours = {slug_of(root, s) for s in feature.slices}
    problems += [f"debt: the {d['kind']} check deferred at {d['slice']} until {d['until']} was never run" for d in open_debts(root)
                 if d["until"] in due and d["slice"] in ours]
    if problems:
        return 3, f"BLOCKED: the feature {name} does not close:\n- " + "\n- ".join(problems)
    return 0, f"the feature {name} may close: every slice has its decision of point (b), no debt is due"


# ------------------------------------------------------------------ the mutation run


def mutation(root: Path, env: dict[str, str], slug: str, timeout: int) -> tuple[int, str]:
    command = env.get("MUTATION_CMD", "").strip()
    decision = last(root, slug, "decision", point="b")
    if decision is None or (decision.get("checks") or {}).get("mutation", {}).get("when") != "now":
        return 1, f"REFUSED: a mutation run is the manager's decision at point (b) (`mutation: now`), and {slug} has none."
    if not command:
        return 1, "REFUSED: MUTATION_CMD is empty in .claude/project.env. The engine installs no tool: the project's owner chooses one."
    found = feature_of(root, slug)
    files = sorted(changed_code(root, env, block_base(root, slug))[0])
    started = time.monotonic()
    try:
        done = subprocess.run(["bash", "-c", command], cwd=root, env=os.environ | {"MUTATION_FILES": " ".join(files)}, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout, check=False)
        output, code = done.stdout, str(done.returncode)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        code = f"time limit of {timeout} s"
    seconds = round(time.monotonic() - started)
    out = root / MUTATION_REL / f"{slug}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output, encoding="utf-8")
    block = found[1].block if found else slug
    append_row(root, {"type": "mutation", "slice": slug, "block": block, "seconds": seconds, "exit": code, "files": files,
                      "output": out.relative_to(root).as_posix()},
               f"{block} — mutation run", [(f"{seconds} s, exit {code}, {len(files)} file(s) of the block; the survivors, without a score or a "
                                            f"threshold: {out.relative_to(root).as_posix()}")])
    return 0, f"mutation run recorded: {seconds} s, exit {code}; the list of survivors is in {out.relative_to(root).as_posix()}"


def mutation_result(root: Path, slug: str, survived: int, handled: int, note: str) -> tuple[int, str]:
    run = last(root, slug, "mutation")
    if run is None:
        return 1, f"REFUSED: no mutation run is recorded for {slug}."
    append_row(root, {"type": "mutation_result", "slice": slug, "block": run.get("block"), "survived": survived, "handled": handled, "note": note},
               f"{run.get('block')} — surviving mutants", [(f"{survived} survived, {handled} handled (a test added, a finding for the simplifier, or "
                                                            f"an equivalent mutant explained); the rest is a list in the report. {one_line(note, 300)}")])
    return 0, "recorded"


# ------------------------------------------------------------------ status


def status(root: Path, slug: str | None) -> str:
    waiting = pending(root)
    lines = [f"wired in settings: {'yes' if wired(root) else 'NO — guard and record wait for the owner (docs/tasks/settings.json)'}",
             f"pending request: {launch_line(str(waiting['id'])) + ' for ' + str(waiting['agent']) if waiting else 'none'}"]
    for name in sorted({str(r.get("slice")) for r in rows(root) if r.get("slice")} if slug is None else {slug}):
        a, b = last(root, name, "decision", point="a"), last(root, name, "decision", point="b")
        lines.append(f"{name}: (a) {a.get('decision') if a else '—'}; hand-ins accepted {sum(1 for r in rows(root, name, 'handin') if r.get('accepted'))}; "
                     f"rounds {rounds_of(root, name)}; (b) {'decided' if b else '—'}; seal: {check_seal(root, name)[1]}"
                     + ("; PARKED" if last(root, name, "parked") else ""))
        lines += [f"  NOT DONE — {line}" for line in undone(root, name)]
    debts = open_debts(root)
    lines += [f"debt: {d['kind']} of {d['slice']} until {d['until']}" for d in debts] or ["debts: none"]
    return "\n".join(lines)


# ------------------------------------------------------------------ the command line


def read_envelope() -> JsonObj:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("request")
    p.add_argument("slug")
    p.add_argument("--point", choices=("a", "b"))
    p.add_argument("--tester", choices=MODES)
    p.add_argument("--package", type=Path)
    sub.add_parser("guard")
    p = sub.add_parser("record")
    p.add_argument("--answer", type=Path, help="the agent's answer in a file — by hand, only while the hooks are not wired")
    p = sub.add_parser("validate")
    p.add_argument("decision", type=Path)
    p.add_argument("--request", required=True, help="the id of the request, or the path of a request.json")
    sub.add_parser("invariants").add_argument("contract", type=Path)
    p = sub.add_parser("answer")
    p.add_argument("slug")
    p.add_argument("question")
    p.add_argument("--reading", choices=("taken", "other"), required=True)
    p.add_argument("--text", required=True)
    for name in ("seal", "check", "gate"):
        sub.add_parser(name).add_argument("slug")
    sub.add_parser("status").add_argument("slug", nargs="?")
    sub.add_parser("ledger")
    sub.add_parser("feature-close").add_argument("feature")
    p = sub.add_parser("mutation")
    p.add_argument("slug")
    p.add_argument("--timeout", type=int, default=MUTATION_TIMEOUT_S)
    p = sub.add_parser("mutation-result")
    p.add_argument("slug")
    p.add_argument("--survived", type=int, required=True)
    p.add_argument("--handled", type=int, required=True)
    p.add_argument("--note", default="")
    return parser


def finish(result: tuple[int, str]) -> int:
    code, text = result
    if text:
        print(text, file=sys.stdout if code == 0 else sys.stderr)
    return code


def cmd_record(root: Path, answer: Path | None) -> int:
    if answer is None:
        out = record_hook(root, read_envelope())
        if out is not None:
            print(json.dumps(out))
        return 0
    if wired(root):
        return finish((1, "REFUSED: the hooks are wired, so the answer is recorded when the agent stops — never by hand."))
    waiting = pending(root)
    if waiting is None:
        return finish((1, "REFUSED: no request is pending."))
    return finish(record(root, str(waiting["agent"]), answer.read_text(encoding="utf-8", errors="replace")))


def cmd_validate(root: Path, decision: Path, request: str) -> int:
    path = Path(request) if request.endswith(".json") else request_dir(root, request) / "request.json"
    facts = read_json(path).get("facts")
    if not isinstance(facts, dict):
        return finish((2, f"no facts in {path}"))
    try:
        errors = validate(json.loads(decision.read_text(encoding="utf-8")), facts)
    except (OSError, ValueError) as exc:
        return finish((2, f"cannot read the decision: {exc}"))
    return finish((1, "REFUSED:\n- " + "\n- ".join(errors)) if errors else (0, "allowed: the decision contradicts no mandatory case"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()
    if args.command == "guard":
        out = guard(root, read_envelope())
        if out is not None:
            print(json.dumps(out))
        return 0
    if args.command == "record":
        return cmd_record(root, args.answer)
    if args.command == "validate":
        return cmd_validate(root, args.decision, args.request)
    if args.command == "invariants":
        return finish(check_invariants(args.contract))
    if args.command == "request":
        if bool(args.point) == bool(args.tester):
            return finish((2, "one of --point a|b (the manager) or --tester contract|objection|block"))
        if args.point:
            return finish(request_manager(root, load_env(root), args.slug, args.point))
        return finish(request_tester(root, args.slug, args.tester, args.package))
    if args.command == "answer":
        return finish(answer_question(root, args.slug, args.question, args.reading, args.text))
    if args.command == "seal":
        return finish(seal_held(root, args.slug))
    if args.command == "check":
        return finish(check_seal(root, args.slug))
    if args.command == "gate":
        reason = audit_block(root, args.slug)
        return finish((3, "BLOCKED: " + reason) if reason else (0, f"testing does not stand in the way of an audit of {args.slug}"))
    if args.command == "status":
        return finish((0, status(root, args.slug)))
    if args.command == "ledger":
        path = root / LEDGER_REL
        return finish((0, path.read_text(encoding="utf-8") if path.is_file() else "(the testing ledger is empty)"))
    if args.command == "feature-close":
        return finish(feature_close(root, args.feature))
    if args.command == "mutation":
        return finish(mutation(root, load_env(root), args.slug, args.timeout))
    return finish(mutation_result(root, args.slug, args.survived, args.handled, args.note))


if __name__ == "__main__":
    sys.exit(main())
