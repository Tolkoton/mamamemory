#!/usr/bin/env python3
"""The goals document (level 0) and what refers to it: the mechanics, and nothing but the mechanics.

    python3 .claude/hooks/goals.py status                    # is there a document, is it the approved one
    python3 .claude/hooks/goals.py seal [--owner-approved]   # after the owner approved it; the first one, in a new project: NEXT /master-architect
    python3 .claude/hooks/goals.py check [FILE ...]          # the document, and the decisions' «Звірка з цілями»
    python3 .claude/hooks/goals.py unreconciled              # decisions that cite no line of the document
    python3 .claude/hooks/goals.py affected ID [ID ...]      # decisions that cite these lines
    python3 .claude/hooks/goals.py quote REQUEST.md          # is the analyst's quote a line of the document
    python3 .claude/hooks/goals.py requests                  # the architects' requests and how each ended
    python3 .claude/hooks/goals.py proposal                  # is .engine/goals/proposed.md a lawful amendment
    python3 .claude/hooks/goals.py amend <sha256>            # the board runner's, on the owner's «так»
    python3 .claude/hooks/goals.py first-seal <sha256>       # the board runner's, on the owner's «так»
    python3 .claude/hooks/goals.py trace                     # the traceability matrix and the maps' element tables

WHY. `.engine/goals.md` is what the owner wants from the project: goals (G), principles (P),
non-goals (N), hard constraints (C), done-when (D), open questions (Q) — one numbered line each,
written with the business analyst and approved by the owner. Every decision of an architect
cites the lines it serves in a section «Звірка з цілями». A citation is only worth something if
the line it names exists, still stands, and says today what it said when it was cited. So:

  * the document is SEALED, like a slice contract: `seal` writes its SHA-256 into machine state
    (`.claude/state/goals/goals.sha256`). The first seal follows the owner's approval in the
    conversation with the analyst and is refused in an unattended session; with nobody in the
    conversation it is `first-seal` — the board runner's action on the owner's «так» under a
    question that offers `Дія runner-а: seal-goals <sha256 of .engine/goals.md>` (board 787): the
    document sealed is the one that sha256 names, and no other. A changed document
    is not in force until it is sealed again, and that is the owner's act: `--owner-approved`
    in the owner's own terminal, or `amend` — the board runner's action on the owner's «так»
    under a question that offers `Дія runner-а: amend-goals <sha256 of .engine/goals/proposed.md>`.
    Inside a Claude Code session none of the three works: an agent can type them all;
  * the first seal of a new project (no traceability matrix, no map yet) hands off to the architect
    (board 205): `seal` prints `NEXT: /master-architect`, and after `first-seal` the board runner puts
    the architecture task on the board (`board.py architect-task`). Not after an amendment: there
    `.engine/goals/to-review.md` lists what the architects reread;
  * numbers are permanent: a line that no longer holds stays, struck through (`- ~~G2. …~~`).
    `proposal` and `amend` refuse an amendment that drops or revives a number or does not raise
    the version;
  * after an amendment every decision that cited a changed line is written into
    `.engine/goals/to-review.md` (Article 8, done mechanically);
  * «the document already answers» is accepted from the analyst only with a verbatim quote of a
    line: `quote` compares it with the sealed document.

Whether a citation is HONEST — the line really says what the decision claims — is not judged
here; that is the blind critic's lens. This script counts, compares and lists.

Exit: 0 fine; 3 refused (changed document, bad citation, false quote, unlawful amendment, stale
sha256); 4 no goals document, or none sealed; 2 usage, or an owner's act attempted in a session.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mode as mode_reader  # the one reader of «nobody is watching» (board 097)

GOALS_REL = ".engine/goals.md"
PROPOSED_REL = ".engine/goals/proposed.md"
REVIEW_REL = ".engine/goals/to-review.md"
REQUESTS_PREFIX = ".engine/goals/requests/"
TRACE_REL = ".engine/architecture/traceability.md"
MAPS = (".engine/architecture/domain-map.md", ".engine/architecture/architecture-map.md")
STATE_REL = Path(".claude") / "state" / "goals" / "goals.sha256"
EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_NONE = 0, 2, 3, 4

KINDS = "GPNCDQ"
ITEM = re.compile(rf"^- (?P<strike>~~)?(?P<id>[{KINDS}]\d+)\. (?P<rest>.+)$")
ID = re.compile(rf"(?<![\w-])[{KINDS}]\d+(?![\w-])")
VERSION = re.compile(r"^(?:Версія|Version):\s*(\d+)", re.MULTILINE)
SECTION = re.compile(r"^#{2,4}\s*(?:Звірка з цілями|Goals check)\s*$", re.MULTILINE)
HEADING = re.compile(r"^#{1,4}\s", re.MULTILINE)
ANSWER = re.compile(r"^ANALYST_ANSWER:\s*(QUOTE|OWNER_DECISION|NOT_REQUIRED)\s*$", re.MULTILINE)
CORE = re.compile(r"^## (?:Ядро|Core)[ \t]*$", re.MULTILINE)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ADR_PATH = re.compile(r"docs/adr/[^\s|)\]]+\.md")
SOURCE_KINDS = "GPCD"
FIELD = r"^{name}:[ \t]*(.*)$"
REVIEW_HEADER = ("# Рішення, які треба переглянути\n\nКожен рядок дописав `goals.py` після поправки до документа цілей: рішення "
                 "посилалося на рядок, який змінився. Архітектор перечитує рішення і ставить `[x]`.\n\n")
IN_SESSION = ("refused inside a Claude Code session (CLAUDECODE is set): re-approving the goals document is the owner's "
              "act — their own terminal, or «так» under a question that offers `Дія runner-а: amend-goals <sha256>`")

Show = Callable[[str], str]


@dataclass(frozen=True)
class Item:
    id: str
    text: str
    struck: bool


@dataclass(frozen=True)
class Request:
    path: str
    reason: str
    outcome: str  # quote-valid | quote-invalid | owner | unanswered
    detail: str


# ------------------------------------------------------------------ the document


def items(text: str) -> dict[str, Item]:
    """The numbered lines of a goals document. A number that appears twice raises ValueError."""
    found: dict[str, Item] = {}
    for line in text.splitlines():
        match = ITEM.match(line.rstrip())
        if not match:
            continue
        rest = match["rest"]
        struck = bool(match["strike"])
        if struck:
            rest = rest.split("~~", 1)[0]
        if match["id"] in found:
            raise ValueError(f"{match['id']} is numbered twice: a number names one line for ever")
        found[match["id"]] = Item(match["id"], " ".join(rest.split()), struck)
    return found


def version(text: str) -> int:
    match = VERSION.search(text)
    return int(match.group(1)) if match else 0


def cited(text: str) -> tuple[bool, list[str]]:
    """(has a «Звірка з цілями» section, the line numbers cited in all such sections)."""
    ids: list[str] = []
    sections = list(SECTION.finditer(text))
    for match in sections:
        ids += ID.findall(_body(text, match))
    return bool(sections), list(dict.fromkeys(ids))


def citation_errors(path: str, text: str, lines: dict[str, Item]) -> list[str]:
    has_section, ids = citations(path, text)
    if not has_section:
        return ["the matrix has no row" if path == TRACE_REL else "no «Звірка з цілями» section"]
    if not ids:
        return ["«Звірка з цілями» cites no line of the goals document"]
    errors = [f"{i} is not a line of the goals document" for i in ids if i not in lines]
    return errors + [f"{i} is struck out of the goals document" for i in ids if i in lines and lines[i].struck]


def _body(text: str, match: re.Match[str]) -> str:
    """The body under a heading line, to the next heading or the end."""
    rest = text[match.end():]
    following = HEADING.search(rest)
    return rest[: following.start()] if following else rest


def core_error(text: str) -> str:
    """"" when `text` has a «## Ядро» naming a standing goal G, else why not (board 201)."""
    match = CORE.search(text)
    if not match:
        return "no «## Ядро» section: the owner names the goals without which the product loses its sense"
    lines = items(text)
    named = [i for i in ID.findall(COMMENT.sub("", _body(text, match))) if i[0] == "G"]
    for ident in named:
        if ident not in lines:
            return f"«Ядро» cites {ident}, which is not a line of the goals document"
        if lines[ident].struck:
            return f"«Ядро» cites {ident}, which is struck out"
    return "" if named else "«Ядро» names no standing goal G"


def _tables(text: str, first: tuple[str, ...]) -> list[tuple[list[str], list[tuple[str, list[str]]]]]:
    """Each table whose header's first cell is one of `first`: (its header cells, [(the section, its cells)]).
    A table is a block of consecutive `|` lines; its second line is the rule; the section is the last `## `."""
    found: list[tuple[list[str], list[tuple[str, list[str]]]]] = []
    section, block = "", []
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            block.append([cell.strip() for cell in line.strip().strip("|").split("|")])
            continue
        if block and block[0][0] in first:
            found.append((block[0], [(section, row) for row in block[2:]]))
        block = []
        if line.startswith("## "):
            section = line[3:].strip()
    return found


def _line_errors(where: str, ident: str, lines: dict[str, Item]) -> list[str]:
    if ident not in lines:
        return [f"{where}: {ident} is not a line of the goals document"]
    return [f"{where}: {ident} is struck out of the goals document"] if lines[ident].struck else []


def _matrix_rows(text: str) -> list[tuple[str, bool]] | None:
    """The first cells of the matrix's rows, each with «names a line»; None without a matrix."""
    tables = _tables(text, ("Рядок", "Line"))
    return [(row[0], bool(re.fullmatch(rf"[{KINDS}]\d+", row[0]))) for _, row in tables[0][1]] if tables else None


def _matrix_errors(text: str, lines: dict[str, Item]) -> list[str]:
    rows = _matrix_rows(text)
    if rows is None:
        return [f"{TRACE_REL}: no matrix (a table whose first column is «Рядок»)"]
    errors: list[str] = []
    seen: list[str] = []
    for cell, names in rows:
        if not names:
            errors.append(f"{TRACE_REL}: a row names no line: «{cell}»")
            continue
        errors += [f"{TRACE_REL}: {cell} has two rows"] if cell in seen else _line_errors(TRACE_REL, cell, lines)
        seen.append(cell)
    return errors + [f"{TRACE_REL}: {i} has no row" for i, item in lines.items() if not item.struck and i not in seen]


def _no_source(where: str, standing: list[str]) -> str:
    """The sentence for an element with no valid source: naming the non-goal when the cell named one."""
    tail = "remove it or move it to «## Пропозиції»"
    goal_less = [i for i in standing if i[0] == "N"]
    if goal_less:
        return f"{where}: its only source is the non-goal {goal_less[0]} — a non-goal is a boundary, not a source: {tail}"
    return f"{where} has no source (a G, P, C or D line, or an owner's decision in docs/adr/): {tail}"


def _source_errors(where: str, cell: str, lines: dict[str, Item], exists: Callable[[str], bool]) -> list[str]:
    ids, paths = ID.findall(cell), ADR_PATH.findall(cell)
    errors = [e for i in ids for e in _line_errors(where, i, lines)] + [f"{where}: {p} is not a file" for p in paths if not exists(p)]
    standing = [i for i in ids if i in lines and not lines[i].struck]
    valid = any(i[0] in SOURCE_KINDS for i in standing) or any(exists(p) for p in paths)
    return errors if valid else [*errors, _no_source(where, standing)]


def _map_errors(rel: str, text: str, lines: dict[str, Item], exists: Callable[[str], bool]) -> tuple[list[str], int]:
    tables = _tables(text, ("Елемент", "Element"))
    if not tables:
        return [f"{rel}: no element table (a table whose first column is «Елемент»)"], 0
    errors, counted = [], 0
    for header, rows in tables:
        column = next((n for n, cell in enumerate(header) if cell in ("Джерело", "Source")), None)
        if column is None:
            errors.append(f"{rel}: the element table has no «Джерело» column")
            continue
        for section, row in rows:
            if section in ("Пропозиції", "Proposals"):
                continue
            counted += 1
            cell = row[column] if column < len(row) else ""
            errors += _source_errors(f"{rel}: «{row[0]}»", cell, lines, exists)
    return errors, counted


def trace_errors(show: Show, lines: dict[str, Item], exists: Callable[[str], bool]) -> tuple[list[str], int]:
    """(why the matrix and the maps' element tables do not stand, the elements outside «Пропозиції»)."""
    errors, total = _matrix_errors(show(TRACE_REL), lines), 0
    for rel in MAPS:
        if exists(rel):
            found, counted = _map_errors(rel, show(rel), lines, exists)
            errors, total = errors + found, total + counted
    return errors, total


def citations(path: str, text: str) -> tuple[bool, list[str]]:
    """`cited(text)`, except for the traceability matrix, whose citations are its rows (board 201)."""
    if path != TRACE_REL:
        return cited(text)
    rows = _matrix_rows(text) or []
    return bool(rows), list(dict.fromkeys(cell for cell, names in rows if names))


def is_decision(path: str) -> bool:
    """What counts as an architect's decision: an ADR, the architecture map, a feature frame."""
    name = path.rsplit("/", 1)[-1].lower()
    if path.startswith("docs/adr/"):
        return name.endswith(".md") and name[:1].isdigit()
    return path in (*MAPS, TRACE_REL) or (path.startswith(".engine/architecture/feature/") and name.endswith(".md"))


def unreconciled(show: Show, files: Iterable[str]) -> list[tuple[str, str]]:
    """(decision, why it is not reconciled). Empty when there is no goals document to reconcile
    with — none at all, or the seed nobody has filled in yet."""
    lines = items(show(GOALS_REL))
    if not lines:
        return []
    out = []
    for path in sorted(p for p in files if is_decision(p)):
        errors = citation_errors(path, show(path), lines)
        if errors:
            out.append((path, "; ".join(errors)))
    return out


def affected(show: Show, files: Iterable[str], ids: Iterable[str]) -> list[tuple[str, str]]:
    """(decision, line) for every decision whose «Звірка з цілями» cites one of `ids`."""
    wanted = set(ids)
    return [(path, i) for path in sorted(p for p in files if is_decision(p)) for i in citations(path, show(path))[1] if i in wanted]


def changes(text: str) -> list[str]:
    """The lines of «Зміни»: one per version, what changed and why."""
    return [line[2:].strip() for line in text.splitlines() if re.match(r"^- v\d+\b", line)]


def to_review(show: Show) -> list[str]:
    """The unticked lines of the review list."""
    return [line[6:] for line in show(REVIEW_REL).splitlines() if line.startswith("- [ ] ")]


# ------------------------------------------------------------------ the analyst's answer


def field(text: str, *names: str) -> str:
    for name in names:
        match = re.search(FIELD.format(name=re.escape(name)), text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def quote_error(request: str, document: str) -> str:
    """Why the answer «the document already answers» does not stand, or ""."""
    line, quote = field(request, "Line", "Рядок"), field(request, "Quote", "Цитата")
    if not line or not quote:
        return "the answer names no `Line:` or no `Quote:`"
    lines = items(document)
    if line not in lines:
        return f"{line} is not a line of the goals document"
    if lines[line].struck:
        return f"{line} is struck out of the goals document"
    if " ".join(quote.strip("«»\"“”").split()) != lines[line].text:
        return f"the quote is not the text of {line}: the document says «{lines[line].text}»"
    return ""


def request_outcome(path: str, text: str, document: str) -> Request:
    reason = field(text, "Reason", "Привід") or "?"
    answers = ANSWER.findall(text)
    if not answers:
        return Request(path, reason, "unanswered", "")
    if answers[-1] == "OWNER_DECISION":
        return Request(path, reason, "owner", "")
    answer = text[list(ANSWER.finditer(text))[-1].end():]
    if answers[-1] == "NOT_REQUIRED":
        return Request(path, reason, "not-required", field(answer, "Lines", "Рядки"))
    error = quote_error(answer, document)
    if error:
        return Request(path, reason, "quote-invalid", error)
    return Request(path, reason, "quote-valid", f"{field(answer, 'Line', 'Рядок')}: {field(answer, 'Quote', 'Цитата')}")


def requests(show: Show, files: Iterable[str]) -> list[Request]:
    document = show(GOALS_REL)
    return [request_outcome(p, show(p), document) for p in sorted(files) if p.startswith(REQUESTS_PREFIX) and p.endswith(".md")]


# ------------------------------------------------------------------ amendments


def amendment(old: str, new: str) -> tuple[list[str], list[str]]:
    """(why `new` may not replace `old`, the numbers of the lines that changed or were struck)."""
    try:
        before, after = items(old), items(new)
    except ValueError as exc:
        return [str(exc)], []
    errors = []
    if version(new) <= version(old):
        errors.append(f"the version must grow: it is {version(old)}, the amendment says {version(new)}")
    elif not re.search(rf"^- v{version(new)}\b", new, re.MULTILINE):
        errors.append(f"«Зміни» has no line `- v{version(new)}, …` saying what changed and why")
    changed = []
    for ident, item in before.items():
        if ident not in after:
            errors.append(f"{ident} is gone: a line that no longer holds is struck through (`- ~~{ident}. …~~`), never removed")
        elif item.struck and after[ident] != item:
            errors.append(f"{ident} was struck out; a number is never used again — give the new line a new number")
        elif after[ident] != item:
            changed.append(ident)
    core = core_error(new)
    return errors + ([core] if core else []), changed


# ------------------------------------------------------------------ disk, state, commands


def project_root() -> Path:
    given = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if given and Path(given).is_dir():
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def disk(root: Path) -> tuple[Show, list[str]]:
    """How the commands read: a file's text ("" when absent) and the candidate paths."""

    def show(rel: str) -> str:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    found = [p.relative_to(root).as_posix() for top in ("docs/adr", ".engine/architecture", ".engine/goals")
             if (root / top).is_dir() for p in (root / top).rglob("*.md")]
    return show, found


def digest(path: Path) -> str:
    """The sha256 of the file's bytes — the same number `board.py action-line amend-goals` offers."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def state(root: Path) -> str:
    """absent | unsealed | sealed | changed."""
    document = root / GOALS_REL
    if not document.is_file():
        return "absent"
    recorded = root / STATE_REL
    if not recorded.is_file():
        return "unsealed"
    return "sealed" if recorded.read_text(encoding="utf-8").split()[0] == digest(document) else "changed"


STATE_TEXT = {
    "absent": f"no goals document ({GOALS_REL}): /business-analyst writes it with the owner",
    "unsealed": f"{GOALS_REL} exists and no approval is recorded on this machine: not in force until the owner approves it and it is sealed",
    "sealed": f"{GOALS_REL} is the document the owner approved",
    "changed": f"CHANGED: {GOALS_REL} differs from the document the owner approved; not in force until the owner approves it again",
}
STATE_EXIT = {"absent": EXIT_NONE, "unsealed": EXIT_NONE, "sealed": EXIT_OK, "changed": EXIT_REFUSED}


def unattended(root: Path) -> bool:
    return mode_reader.unattended(root)[0]


def write_seal(root: Path) -> str:
    value = digest(root / GOALS_REL)
    target = root / STATE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{value}  {GOALS_REL}\n", encoding="utf-8")
    return value


def architecture_begun(root: Path) -> bool:
    """A project whose architecture has a first file: the matrix or a map. Before it, a new project (board 205)."""
    return any((root / rel).is_file() for rel in (TRACE_REL, *MAPS))


HANDOFF = ("NEXT: /master-architect — a new project: the architecture starts now, without a command from the owner "
           "(board 205). The owner is in the conversation: start it in this session; nobody is: the board runner puts the task "
           "on the board. It begins with its stop «Читання цілей»: the start is automatic, the approvals stay the owner's.")


def cmd_seal(root: Path, owner_flag: bool, in_session: bool) -> int:
    now = state(root)
    if now == "absent":
        print(STATE_TEXT[now], file=sys.stderr)
        return EXIT_NONE
    try:
        found = items((root / GOALS_REL).read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if not found:
        print(f"REFUSED: {GOALS_REL} has no numbered line (`- G1. …`): nothing a decision could cite", file=sys.stderr)
        return EXIT_REFUSED
    if now == "sealed":
        print(STATE_TEXT[now])
        return EXIT_OK
    if now == "changed" and (in_session or not owner_flag):
        print(f"REFUSED: {STATE_TEXT[now]}. " + (IN_SESSION if in_session else "The owner runs `goals.py seal --owner-approved` in their own terminal."), file=sys.stderr)
        return EXIT_USAGE if in_session else EXIT_REFUSED
    if now == "unsealed" and unattended(root):
        print("REFUSED: the first approval of the goals document is given by the owner in the conversation with the analyst; "
              "nobody is here to give it (unattended session). Ask on the task board: a question in tasks/blocked/ with the line "
              "`board.py action-line seal-goals` prints; the owner's «так» has the board runner seal it", file=sys.stderr)
        return EXIT_USAGE
    core = core_error((root / GOALS_REL).read_text(encoding="utf-8"))
    if core:
        print(f"REFUSED: {core}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"sealed {GOALS_REL}  sha256 {write_seal(root)[:12]}…  -> {STATE_REL.as_posix()}")
    if now == "unsealed" and not architecture_begun(root):
        print(HANDOFF)
    return EXIT_OK


def cmd_status(root: Path) -> int:
    """Today's line; and, for a document with numbered lines and no core, what that means."""
    now = state(root)
    print(STATE_TEXT[now])
    text = (root / GOALS_REL).read_text(encoding="utf-8") if now != "absent" else ""
    try:
        core = core_error(text) if items(text) else ""
    except ValueError:
        core = ""
    if core:
        print(f"no core: {core} — " + ("the next amendment must add it" if now == "sealed" else "it is not sealed without one"))
    return STATE_EXIT[now]


def cmd_check(root: Path, paths: list[str]) -> int:
    now = state(root)
    print(STATE_TEXT[now], file=sys.stdout if now == "sealed" else sys.stderr)
    if now != "sealed":
        return STATE_EXIT[now]
    show, files = disk(root)
    try:
        lines = items(show(GOALS_REL))
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    bad = 0
    for rel in paths or sorted(p for p in files if is_decision(p)):
        path = Path(rel)
        real = Path(os.path.realpath(path))  # not resolve(): up to Python 3.12 it raises RuntimeError on a symlink loop
        rel = real.relative_to(root).as_posix() if path.is_absolute() and real.is_relative_to(root) else rel
        if not (root / rel).is_file():
            print(f"REFUSED: {rel}: no such file", file=sys.stderr)
            bad += 1
            continue
        errors = citation_errors(rel, show(rel), lines)
        bad += bool(errors)
        print(f"{'REFUSED' if errors else 'ok'}: {rel}" + (": " + "; ".join(errors) if errors else f" cites {', '.join(citations(rel, show(rel))[1])}"),
              file=sys.stderr if errors else sys.stdout)
    return EXIT_REFUSED if bad else EXIT_OK


def cmd_quote(root: Path, rel: str) -> int:
    now = state(root)
    if now != "sealed":
        print(f"REFUSED: {STATE_TEXT[now]} — a quote can only be compared with the approved document; the request goes to the owner", file=sys.stderr)
        return EXIT_REFUSED if now == "changed" else EXIT_NONE
    path = root / rel
    if not path.is_file():
        print(f"no such request: {rel}", file=sys.stderr)
        return EXIT_USAGE
    result = request_outcome(rel, path.read_text(encoding="utf-8"), (root / GOALS_REL).read_text(encoding="utf-8"))
    if result.outcome == "quote-valid":
        print(f"the quote stands — {result.detail}")
        return EXIT_OK
    if result.outcome == "not-required":
        print("REFUSED: the analyst answers NOT_REQUIRED: there is no quote to check", file=sys.stderr)
        return EXIT_REFUSED
    reasons = {"unanswered": "the request has no `ANALYST_ANSWER:` line", "owner": "the analyst asks for the owner's decision: there is no quote to check",
               "quote-invalid": result.detail}
    print(f"REFUSED: {reasons[result.outcome]}. The answer does not close the request; it goes to the owner.", file=sys.stderr)
    return EXIT_REFUSED


def cmd_proposal(root: Path) -> int:
    proposed = root / PROPOSED_REL
    if not proposed.is_file():
        print(f"no amendment is proposed ({PROPOSED_REL} absent)", file=sys.stderr)
        return EXIT_NONE
    show, files = disk(root)
    errors, changed = amendment(show(GOALS_REL), show(PROPOSED_REL))
    for error in errors:
        print(f"REFUSED: {error}", file=sys.stderr)
    if errors:
        return EXIT_REFUSED
    print(f"a lawful amendment: version {version(show(GOALS_REL))} -> {version(show(PROPOSED_REL))}; changed or struck: {', '.join(changed) or 'none'}")
    for path, ident in affected(show, files, changed):
        print(f"  will be marked for review: {path} (cites {ident})")
    print(f"sha256 {digest(proposed)}")
    return EXIT_OK


def amend(root: Path, approved: str, in_session: bool) -> int:
    """`.engine/goals/proposed.md` becomes the goals document, sealed, and what cited a changed line is listed for review."""
    if in_session:
        print(f"amend: {IN_SESSION}", file=sys.stderr)
        return EXIT_USAGE
    show, files = disk(root)
    new = show(PROPOSED_REL)
    if not new or digest(root / PROPOSED_REL) != approved:
        print(f"amend: {PROPOSED_REL} is {digest(root / PROPOSED_REL) or 'absent'}, the owner approved {approved or '(no sha256)'}; not applied", file=sys.stderr)
        return EXIT_REFUSED
    if state(root) == "changed":
        print(f"amend: {STATE_TEXT['changed']}; an amendment is applied to the approved document only", file=sys.stderr)
        return 1
    errors, changed = amendment(show(GOALS_REL), new)
    if errors:
        print("amend: " + "; ".join(errors), file=sys.stderr)
        return 1
    stale = affected(show, files, changed)
    (root / GOALS_REL).write_text(new, encoding="utf-8")
    (root / PROPOSED_REL).unlink()
    write_seal(root)
    if stale:
        review = root / REVIEW_REL
        text = review.read_text(encoding="utf-8") if review.is_file() else REVIEW_HEADER
        review.write_text(text + "".join(f"- [ ] v{version(new)} {ident} → {path}\n" for path, ident in stale), encoding="utf-8")
    print(f"amend: {GOALS_REL} is version {version(new)}, sealed; changed or struck: {', '.join(changed) or 'none'}; "
          f"{len(stale)} citation(s) marked for review in {REVIEW_REL}")
    return EXIT_OK


def first_seal(root: Path, approved: str, in_session: bool) -> int:
    """The first seal with nobody in the conversation: the document the owner said «так» to — the one `approved` names — is sealed as it is."""
    if in_session:
        print("first-seal: refused inside a Claude Code session (CLAUDECODE is set): approving the goals document is the owner's act — "
              "the conversation with the analyst, or «так» under a question that offers `Дія runner-а: seal-goals <sha256>`", file=sys.stderr)
        return EXIT_USAGE
    document = root / GOALS_REL
    if not approved or digest(document) != approved:
        print(f"first-seal: {GOALS_REL} is {digest(document) or 'absent'}, the owner approved {approved or '(no sha256)'}; not sealed", file=sys.stderr)
        return EXIT_REFUSED
    now = state(root)
    if now == "changed":
        print(f"first-seal: {STATE_TEXT[now]}; a document approved before changes by an amendment only (`amend-goals`)", file=sys.stderr)
        return 1
    try:
        found = items(document.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"first-seal: {exc}", file=sys.stderr)
        return 1
    if not found:
        print(f"first-seal: {GOALS_REL} has no numbered line (`- G1. …`): nothing a decision could cite", file=sys.stderr)
        return 1
    if now == "sealed":
        print(f"first-seal: {STATE_TEXT[now]}")
        return EXIT_OK
    core = core_error(document.read_text(encoding="utf-8"))
    if core:
        print(f"first-seal: {core}", file=sys.stderr)
        return 1
    print(f"first-seal: sealed {GOALS_REL}  sha256 {write_seal(root)[:12]}…  -> {STATE_REL.as_posix()}")
    return EXIT_OK


def cmd_trace(root: Path) -> int:
    """The matrix and the maps' element tables against the approved document; the count always printed."""
    now = state(root)
    if now != "sealed":
        print(STATE_TEXT[now], file=sys.stderr)
        return STATE_EXIT[now]
    show, _ = disk(root)
    try:
        errors, total = trace_errors(show, items(show(GOALS_REL)), lambda rel: (root / rel).is_file())
    except ValueError as exc:
        errors = [str(exc)]
        total = sum(sum(section not in ("Пропозиції", "Proposals") for section, _ in rows)
                    for rel in MAPS for _, rows in _tables(show(rel), ("Елемент", "Element")))
    for error in errors:
        print(f"REFUSED: {error}", file=sys.stderr)
    print(f"elements outside «Пропозиції»: {total}")
    return EXIT_REFUSED if errors else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "unreconciled", "requests", "proposal", "trace"):
        sub.add_parser(name)
    sub.add_parser("seal").add_argument("--owner-approved", action="store_true",
                                        help="the owner's flag, for the owner's own terminal; inside a Claude Code session it does not count")
    sub.add_parser("check").add_argument("files", nargs="*")
    sub.add_parser("affected").add_argument("ids", nargs="+")
    sub.add_parser("quote").add_argument("request")
    sub.add_parser("amend").add_argument("sha256")
    sub.add_parser("first-seal").add_argument("sha256")
    args = parser.parse_args(argv)
    root = project_root()
    in_session = bool(os.environ.get("CLAUDECODE"))
    show, files = disk(root)
    commands: dict[str, Callable[[], int]] = {
        "status": lambda: cmd_status(root), "seal": lambda: cmd_seal(root, args.owner_approved, in_session),
        "check": lambda: cmd_check(root, args.files), "quote": lambda: cmd_quote(root, args.request),
        "proposal": lambda: cmd_proposal(root), "amend": lambda: amend(root, args.sha256, in_session),
        "first-seal": lambda: first_seal(root, args.sha256, in_session), "trace": lambda: cmd_trace(root)}
    if args.command in commands:
        return commands[args.command]()
    if not show(GOALS_REL):
        print(STATE_TEXT["absent"], file=sys.stderr)
        return EXIT_NONE
    if args.command == "unreconciled":
        for path, why in unreconciled(show, files):
            print(f"{path}: {why}")
    elif args.command == "affected":
        for path, ident in affected(show, files, args.ids):
            print(f"{path}: cites {ident}")
    else:
        for req in requests(show, files):
            print(f"{req.path}\treason {req.reason}\t{req.outcome}" + (f"\t{req.detail}" if req.detail else ""))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
