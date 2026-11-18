#!/usr/bin/env python3
"""The user journeys (level J, between the goals and the architecture): the mechanics, and nothing but the mechanics.

    python3 .claude/hooks/journeys.py status                       # each unit: sealed, unsealed or changed
    python3 .claude/hooks/journeys.py check [UNIT ...]             # the graph checks, no LLM; all units by default
    python3 .claude/hooks/journeys.py gate                         # may M4 cut features: 0 yes, 3 no, 4 nothing declared
    python3 .claude/hooks/journeys.py trace                        # every AC of a journey is cited by a feature, every feature AC cites one
    python3 .claude/hooks/journeys.py seal UNIT [--owner-approved] [--answer «…»] [--where …]  # after the owner approved it in the conversation
    python3 .claude/hooks/journeys.py first-seal UNIT <sha256>     # the board runner's, on the owner's «так»
    python3 .claude/hooks/journeys.py amend UNIT <sha256>          # the board runner's, on the owner's «так»

WHY (board 208; docs/research/2026-11-userflow/R1-user-journey.md). The goals say WHAT the owner
wants; nothing said what a person does, sees and hears, step by step, and how every question the
product asks is left. mamamemory lost a week to exactly that: buttons with no visible state, a
question that never let go, «додай задачу» that started the week's planning. The journeys in
`.engine/journeys/` write it down, and the architects cut features from them:

  * UNITS. `index` (`INDEX.md`: the declared interface, the core journey, the story map, the
    must-be expectations), `j-N` (`J-N-<name>.md`: one persona, one trigger, the sample dialog, the
    states, the extensions, the acceptance criteria) and, for a conversational product with two
    journeys or more, `interference` (`interference.md`: what wins when a phrase of one journey
    arrives while a question of another is pending). The format: `.claude/references/journey-template.md`.
  * CHECK — mechanical graph checks, the class of defect a reviewer (human or LLM) misses across
    screens: every state has an exit and every exit lands somewhere; every `question` state can be
    left by silence, by «something else» and by «stop»; every extension ends (back to a step, a
    success, an exit); every step is covered by an AC; every AC has Given/When/Then; every journey
    cites a standing line of the goals; every pending question appears in the interference matrix.
  * SEAL — like the goals (goals.py): a journey is a product decision (Article 5), so a unit is in
    force only when the owner approved it and it is sealed. The first seal inside a conversation
    with the owner is `seal`; with nobody in the conversation it is refused, and the owner's «так»
    under `Дія runner-а: seal-journey <unit> <sha256>` has the board runner run `first-seal` (or
    `amend`, for a unit that changed since its seal). A changed unit is out of force until then.
    The seal keeps a copy of the sealed text (machine state) so that `amend` can see what changed:
    an AC number is permanent (struck through, never removed), and every feature that cited a
    changed AC goes into `.engine/journeys/to-review.md`.
  * THE OWNER'S ANSWER IS THE APPROVAL (board 210). mamamemory: the owner answered all five open
    decisions of the journeys at 11:15, the agent wrote them down and waited for a separate «так»
    until 12:45 — the owner had just said how it is to be. Now the answer that closes the last open
    decisions is the approval: inside a conversation the first seal is refused without
    `--answer «<the owner's words, verbatim>»`, and the seal appends the date, the place, the unit,
    its sha256 and the quote to `.engine/journeys/approvals.md`. A yes with a reservation («так,
    але…») or an answer that asks back is refused (goals.answer_error): something is still open.
  * GATE — what `/master-architect` M4 and `/feature-architect` ask before cutting features: a
    product declared without a human-facing surface (`Інтерфейс: немає`, with a goals line as its
    ground) passes as before; a product with screens or a conversation passes only with every unit
    sealed and checked. Otherwise the feature parks with the draft and a question to the owner.
  * TRACE — every AC of every journey is cited by a feature (`J-N#AC-k`), and every acceptance
    criterion of a feature cites one, or is marked `[тех]` (a technical criterion).

Whether a journey is GOOD — a dead end the graph cannot see, four options per turn, two buttons
doing one thing, a must-be the owner never named — is the blind critic's (`journey-critic`).

Exit: 0 fine; 3 refused (a check failed, a unit not in force, a stale sha256, an unlawful change);
4 nothing to check (no `.engine/journeys/INDEX.md`, or no such unit); 2 usage, or an owner's act
attempted in a session. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goals  # the goals document's parser and the project root: one reading of them

DIR_REL = ".engine/journeys"
INDEX_REL = f"{DIR_REL}/INDEX.md"
INTERFERENCE_REL = f"{DIR_REL}/interference.md"
REVIEW_REL = f"{DIR_REL}/to-review.md"
APPROVALS_REL = f"{DIR_REL}/approvals.md"
FEATURES_REL = ".engine/architecture/feature"
STATE_DIR = Path(".claude") / "state" / "journeys"
EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_NONE = 0, 2, 3, 4

JOURNEY_FILE = re.compile(r"^J-(\d+)-[^/]+\.md$")
UNIT = re.compile(r"^(?:index|interference|j-\d+)$")
INTERFACES = {"екрани": "screens", "розмова": "conversation", "екрани і розмова": "both", "немає": "none",
              "screens": "screens", "conversation": "conversation", "screens and conversation": "both", "none": "none"}
STATE_ID = re.compile(r"^S\d+$")
J_REF = re.compile(r"(?<![\w-])J-(\d+)(?![\w-])")
AC_REF = re.compile(r"(?<![\w-])J-(\d+)#AC-(\d+)(?![\w-])")
AC_LINE = re.compile(r"^- (?P<strike>~~)?AC-(?P<n>\d+)\b(?P<rest>.*)$")
STEPS = re.compile(r"\((?:кроки?|steps?)\s+(?P<list>[\d\s,–-]+)\)")
EXTENSION = re.compile(r"^- (?P<step>\d+)(?P<letter>[a-z])\.\s*(?P<rest>.*)$")
END = re.compile(r"→\s*(?:(?:назад\s+до\s+)?кроку?\s+(?P<step>\d+)|(?:back\s+to\s+)?step\s+(?P<step_en>\d+)|(?P<other>успіх|вихід|success|exit))\b",
                 re.IGNORECASE)
TERMINAL = {"кінець", "end"}
KINDS = {"ideal", "empty", "loading", "partial", "error", "listening", "processing", "question", "no-input", "no-match", "offline"}
SILENCE, OTHER, STOP = ("мовчить", "no-input"), ("інше", "other", "no-match"), ("стоп", "stop")
GIVEN, WHEN, THEN = (r"\b(?:Given|Дано)\b", r"\b(?:When|Коли)\b", r"\b(?:Then|Тоді)\b")
TECH = re.compile(r"^\[(?:тех|tech)\]")
AC_HEADING = re.compile(r"^##\s*(?:Acceptance criteria|Критерії приймання)\b.*$", re.MULTILINE)
SEALS_TO_ASK = ("REFUSED: the first approval of a journey is given by the owner in the conversation; nobody is here to give it "
                "(unattended session). Park the feature with the draft: a question in tasks/blocked/ showing the journey, and under it "
                "the line `board.py action-line seal-journey {unit}` prints; the owner's «так» has the board runner seal it")
IN_SESSION = ("refused inside a Claude Code session (CLAUDECODE is set): approving a journey without the owner in the conversation "
              "is the owner's act — «так» under a question that offers `Дія runner-а: seal-journey {unit} <sha256>`")


@dataclass
class Journey:
    number: int
    rel: str
    text: str
    steps: list[int] = field(default_factory=list)
    states: dict[str, tuple[str, list[tuple[str, str]]]] = field(default_factory=dict)  # id -> (kind, [(label, target)])
    acs: dict[int, tuple[bool, str]] = field(default_factory=dict)  # n -> (struck, text)


# ------------------------------------------------------------------ reading


def header(text: str, *names: str) -> str:
    return goals.field(text, *names)


def section(text: str, *titles: str) -> str:
    """The body under the first `## <title>` (the title may be followed by more words)."""
    for title in titles:
        match = re.search(rf"^##\s*{re.escape(title)}\b.*$", text, re.MULTILINE | re.IGNORECASE)
        if match:
            return goals._body(text, match)
    return ""


def table(text: str, *first: str) -> list[list[str]]:
    """The rows (cells) of the first table whose header's first cell is one of `first`."""
    found = goals._tables(goals.COMMENT.sub("", text), first)
    return [row for _, row in found[0][1]] if found else []


def exits(cell: str) -> list[tuple[str, str]]:
    """`мовчить → S2; інше → J-2; → кінець` -> [(label, target)]; an entry without an arrow is (entry, "")."""
    out = []
    for entry in (e.strip() for e in cell.split(";")):
        if not entry or entry in ("—", "-"):
            continue
        label, arrow, target = entry.rpartition("→")
        out.append((label.strip().strip("«»\"").lower(), target.strip().strip("«»\"").split(" ")[0]) if arrow else (entry.lower(), ""))
    return out


def numbers(listed: str) -> list[int]:
    """`1, 3–5` -> [1, 3, 4, 5]."""
    out: list[int] = []
    for part in (p.strip() for p in listed.split(",")):
        span = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if span:
            out += list(range(int(span[1]), int(span[2]) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def parse(number: int, rel: str, text: str) -> Journey:
    journey = Journey(number, rel, text)
    for row in table(text, "Крок", "Step"):
        if row and row[0].isdigit():
            journey.steps.append(int(row[0]))
    for row in table(text, "Стан", "State"):
        if row and row[0]:
            journey.states[row[0]] = (row[1].lower() if len(row) > 1 else "", exits(row[-1]) if len(row) > 2 else [])
    for line in goals.COMMENT.sub("", section(text, "Приймання", "Acceptance")).splitlines():
        match = AC_LINE.match(line.rstrip())
        if match:
            journey.acs[int(match["n"])] = (bool(match["strike"]), match["rest"])
    return journey


def journeys(root: Path) -> dict[int, Journey]:
    """Every `J-N-<name>.md` of the journeys folder, by number. Two files with one number raise ValueError."""
    found: dict[int, Journey] = {}
    folder = root / DIR_REL
    for path in sorted(folder.glob("J-*.md")) if folder.is_dir() else []:
        match = JOURNEY_FILE.match(path.name)
        if not match:
            continue
        number = int(match[1])
        if number in found:
            raise ValueError(f"J-{number} is numbered twice ({found[number].rel}, {path.name}): a number names one journey for ever")
        found[number] = parse(number, f"{DIR_REL}/{path.name}", path.read_text(encoding="utf-8"))
    return found


def interface(index: str) -> str:
    """screens | conversation | both | none | "" (not declared, or not a known value)."""
    return INTERFACES.get(" ".join(header(index, "Інтерфейс", "Interface").lower().split()), "")


def question_states(found: dict[int, Journey]) -> list[str]:
    return [f"J-{j.number} {sid}" for j in found.values() for sid, (kind, _) in j.states.items() if kind == "question"]


def interference_required(index: str, found: dict[int, Journey]) -> bool:
    return interface(index) in ("conversation", "both") and len(found) >= 2


# ------------------------------------------------------------------ the checks


def journey_errors(journey: Journey, others: dict[int, Journey], lines: dict[str, goals.Item]) -> list[str]:
    """Why one journey does not stand, mechanically."""
    where, text = journey.rel, journey.text
    errors = [f"{where}: no `{names[0]}:` line" for names in (("Persona",), ("Тригер", "Trigger")) if not header(text, *names)]
    cited = goals.ID.findall(header(text, "Цілі", "Goals"))
    if not cited:
        errors.append(f"{where}: `Цілі:` cites no line of the goals document (a journey serves a G or a D)")
    for ident in cited:
        errors += [f"{where}: {e}" for e in goals._line_errors("Цілі", ident, lines)]
    if not journey.steps:
        errors.append(f"{where}: no sample dialog (a table whose first column is «Крок», one numbered row per step)")
    if not journey.states:
        errors.append(f"{where}: no states (a table whose first column is «Стан»)")
    for sid, (kind, outs) in journey.states.items():
        errors += _state_errors(where, sid, kind, outs, journey, others)
    for row in table(text, "Крок", "Step"):
        if row and row[0].isdigit() and row[-1] not in journey.states:
            errors.append(f"{where}: step {row[0]} is in state «{row[-1]}», which the states table does not have")
    errors += _extension_errors(journey)
    errors += _ac_errors(journey)
    return errors


def _state_errors(where: str, sid: str, kind: str, outs: list[tuple[str, str]], journey: Journey, others: dict[int, Journey]) -> list[str]:
    if not STATE_ID.match(sid):
        return [f"{where}: «{sid}» is not a state id (S1, S2, …)"]
    if kind not in KINDS:
        return [f"{where}: {sid} is of kind «{kind}»; the kinds are {', '.join(sorted(KINDS))}"]
    if not outs:
        return [f"{where}: {sid} has no exit — a dead end: name where the person goes from here (`→ S2`, `→ J-2`, `→ кінець`)"]
    errors = []
    for label, target in outs:
        if not target:
            errors.append(f"{where}: {sid}: the exit «{label}» names no target (`<what happens> → <S-k | J-N | кінець>`)")
        elif target.lower() in TERMINAL:
            continue
        elif J_REF.fullmatch(target):
            if int(target[2:]) not in others:
                errors.append(f"{where}: {sid}: the exit «{label}» goes to {target}, which is not a journey of this folder")
        elif target not in journey.states:
            errors.append(f"{where}: {sid}: the exit «{label}» goes to «{target}», which is not a state of this journey")
    if kind == "question":
        labels = [label for label, _ in outs]
        for words, what in ((SILENCE, "the person is silent (`мовчить → …`)"), (OTHER, "the person says something else (`інше → …`)"),
                            (STOP, "the person says stop (`стоп → …`)")):
            if not any(any(w in label for w in words) for label in labels):
                errors.append(f"{where}: {sid} asks a question and has no exit for when {what} — a question without a way out")
    return errors


def _extension_errors(journey: Journey) -> list[str]:
    errors = []
    for line in goals.COMMENT.sub("", section(journey.text, "Відхилення", "Extensions")).splitlines():
        match = EXTENSION.match(line.rstrip())
        if not match:
            continue
        name = f"{match['step']}{match['letter']}"
        if int(match["step"]) not in journey.steps:
            errors.append(f"{journey.rel}: extension {name} hangs off step {match['step']}, which the sample dialog does not have")
        ends = list(END.finditer(match["rest"]))
        if not ends:
            errors.append(f"{journey.rel}: extension {name} has no end — it ends `→ крок N`, `→ успіх: …` or `→ вихід: …`")
            continue
        step = ends[-1]["step"] or ends[-1]["step_en"]
        if step and int(step) not in journey.steps:
            errors.append(f"{journey.rel}: extension {name} goes back to step {step}, which the sample dialog does not have")
    return errors


def _ac_errors(journey: Journey) -> list[str]:
    where = journey.rel
    standing = {n: rest for n, (struck, rest) in journey.acs.items() if not struck}
    if not standing:
        return [f"{where}: no acceptance criterion (`- AC-1 (кроки 1–2). Given … When … Then …` under «## Приймання»)"]
    errors, covered = [], set()
    for n, rest in standing.items():
        missing = [word for word, pattern in (("Given", GIVEN), ("When", WHEN), ("Then", THEN)) if not re.search(pattern, rest)]
        if missing:
            errors.append(f"{where}: AC-{n} has no {'/'.join(missing)} (Given … When … Then …, or Дано … Коли … Тоді …)")
        steps = STEPS.search(rest)
        if not steps:
            errors.append(f"{where}: AC-{n} names no steps — `AC-{n} (кроки 1–3).`: every step is covered by an AC")
            continue
        for step in numbers(steps["list"]):
            if step in journey.steps:
                covered.add(step)
            else:
                errors.append(f"{where}: AC-{n} names step {step}, which the sample dialog does not have")
    uncovered = [str(s) for s in journey.steps if s not in covered]
    return errors + ([f"{where}: step(s) {', '.join(uncovered)} covered by no AC"] if uncovered else [])


def index_errors(index: str, found: dict[int, Journey], lines: dict[str, goals.Item]) -> list[str]:
    where = INDEX_REL
    kind = interface(index)
    if not kind:
        return [f"{where}: `Інтерфейс:` must be one of: екрани, розмова, екрани і розмова, немає"]
    if kind == "none":
        ground = goals.ID.findall(header(index, "Підстава", "Ground"))
        errors = [f"{where}: {e}" for i in ground for e in goals._line_errors("Підстава", i, lines)]
        return errors + ([] if ground else [f"{where}: `Інтерфейс: немає` needs `Підстава:` citing the goals line it rests on"])
    errors = []
    core = J_REF.findall(header(index, "Ядро", "Core"))
    if not core:
        errors.append(f"{where}: `Ядро:` names no journey — the core journey is built first (the walking skeleton)")
    errors += [f"{where}: `Ядро:` names J-{n}, which is not a journey of this folder" for n in core if int(n) not in found]
    mapped = [int(m[1]) for row in table(index, "Journey", "Шлях") if row for m in [J_REF.search(row[0])] if m]
    errors += [f"{where}: the story map names J-{n}, which is not a journey of this folder" for n in mapped if n not in found]
    errors += [f"{where}: J-{n} is not in the story map" for n in found if n not in mapped]
    if not found:
        errors.append(f"{where}: the product has a {('screen' if kind == 'screens' else 'conversation')} and no journey (J-N-<name>.md)")
    must = table(index, "Очікування", "Expectation")
    if not must:
        errors.append(f"{where}: no must-be table (first column «Очікування»): what a person expects of such a product without saying it")
    for row in must:
        place = row[-1] if len(row) > 1 else ""
        js, ids = J_REF.findall(place), goals.ID.findall(place)
        if not js and not [i for i in ids if i[0] == "N"]:
            errors.append(f"{where}: the must-be «{row[0]}» has neither a journey (J-N) nor a non-goal (N-k) the owner answered")
        errors += [f"{where}: the must-be «{row[0]}» names J-{n}, which is not a journey of this folder" for n in js if int(n) not in found]
        errors += [f"{where}: the must-be «{row[0]}»: {e}" for i in ids for e in goals._line_errors("Де", i, lines)]
    return errors


def interference_errors(text: str, found: dict[int, Journey]) -> list[str]:
    where = INTERFERENCE_REL
    rows = table(text, "У стані", "In state")
    if not rows:
        return [f"{where}: no matrix (a table whose first column is «У стані»)"]
    errors, named, pending = [], set(), question_states(found)
    for row in rows:
        place = " ".join(row[0].split())
        named.add(place)
        if len(row) < 3 or not row[2] or not row[1]:
            errors.append(f"{where}: the row «{place}» needs a phrase and what wins")
        if place not in pending:
            errors.append(f"{where}: the row «{place}» names no pending question (`J-N S-k`, a state of kind question)")
    return errors + [f"{where}: the pending question {q} has no row — what wins when a phrase of another journey arrives there"
                     for q in pending if q not in named]


def all_errors(root: Path) -> dict[str, list[str]]:
    """unit -> why it does not stand; every unit present (and `interference` when it is required)."""
    show = _show(root)
    try:
        lines = goals.items(show(goals.GOALS_REL))
        found = journeys(root)
    except ValueError as exc:
        return {"index": [str(exc)]}
    out: dict[str, list[str]] = {}
    if not lines:
        out["index"] = [f"no goals document with numbered lines ({goals.GOALS_REL}): a journey serves a goal, so the goals come first"]
    index = show(INDEX_REL)
    out["index"] = out.get("index", []) + index_errors(index, found, lines)
    for number, journey in found.items():
        out[f"j-{number}"] = journey_errors(journey, found, lines)
    if interference_required(index, found) or (root / INTERFERENCE_REL).is_file():
        out["interference"] = interference_errors(show(INTERFERENCE_REL), found)
    return out


# ------------------------------------------------------------------ seals


def _show(root: Path) -> goals.Show:
    return lambda rel: (root / rel).read_text(encoding="utf-8") if (root / rel).is_file() else ""


def unit_rel(root: Path, unit: str) -> str:
    """The file a unit names, "" when there is none."""
    unit = unit.lower()
    if unit == "index":
        return INDEX_REL
    if unit == "interference":
        return INTERFERENCE_REL
    match = re.fullmatch(r"j-(\d+)", unit)
    if match:
        try:
            journey = journeys(root).get(int(match[1]))
        except ValueError:
            return ""
        return journey.rel if journey else ""
    return ""


def units(root: Path) -> list[str]:
    try:
        found = journeys(root)
    except ValueError:
        found = {}
    index = _show(root)(INDEX_REL)
    extra = ["interference"] if interference_required(index, found) or (root / INTERFERENCE_REL).is_file() else []
    return ["index", *(f"j-{n}" for n in sorted(found)), *extra]


def seal_state(root: Path, unit: str) -> str:
    """absent | unsealed | sealed | changed."""
    rel = unit_rel(root, unit)
    if not rel or not (root / rel).is_file():
        return "absent"
    recorded = root / STATE_DIR / f"{unit}.sha256"
    if not recorded.is_file():
        return "unsealed"
    return "sealed" if recorded.read_text(encoding="utf-8").split()[0] == goals.digest(root / rel) else "changed"


def write_seal(root: Path, unit: str) -> str:
    rel = unit_rel(root, unit)
    value = goals.digest(root / rel)
    folder = root / STATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{unit}.sha256").write_text(f"{value}  {rel}\n", encoding="utf-8")
    (folder / f"{unit}.sealed.md").write_text((root / rel).read_text(encoding="utf-8"), encoding="utf-8")
    return value


def acs_of(text: str) -> dict[int, tuple[bool, str]]:
    return parse(0, "", text).acs


def change_errors(old: str, new: str) -> tuple[list[str], list[int]]:
    """(why `new` may not replace the sealed `old`, the numbers of the ACs that changed or were struck)."""
    errors = []
    if goals.version(new) <= goals.version(old):
        errors.append(f"the version must grow: it is {goals.version(old)}, the change says {goals.version(new)}")
    elif not re.search(rf"^- v{goals.version(new)}\b", new, re.MULTILINE):
        errors.append(f"«Зміни» has no line `- v{goals.version(new)}, …` saying what changed and why")
    before, after, changed = acs_of(old), acs_of(new), []
    for n, item in before.items():
        if n not in after:
            errors.append(f"AC-{n} is gone: an AC that no longer holds is struck through (`- ~~AC-{n} …~~`), never removed — features cite it")
        elif item[0] and after[n] != item:
            errors.append(f"AC-{n} was struck out; a number is never used again — give the new criterion a new number")
        elif after[n] != item:
            changed.append(n)
    return errors, changed


def citing(root: Path, number: int, acs: list[int]) -> list[tuple[str, str]]:
    """(feature artifact, `J-N#AC-k`) for every feature that cites one of `acs` of journey `number`."""
    folder = root / FEATURES_REL
    out = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        for j, k in AC_REF.findall(path.read_text(encoding="utf-8")):
            if int(j) == number and int(k) in acs:
                out.append((path.relative_to(root).as_posix(), f"J-{j}#AC-{k}"))
    return list(dict.fromkeys(out))


def _refuse(message: str, code: int = EXIT_REFUSED) -> int:
    print(message, file=sys.stderr)
    return code


def _unit_or_none(root: Path, unit: str, verb: str) -> str:
    """Why `unit` cannot be sealed before anything is read, or ""."""
    if not UNIT.match(unit.lower()):
        return f"{verb}: «{unit}» is not a unit (index, interference, j-N)"
    if seal_state(root, unit.lower()) == "absent":
        return f"{verb}: {unit} names no file in {DIR_REL}/"
    return ""


def cmd_seal(root: Path, unit: str, owner_flag: bool, in_session: bool, answer: str = "", where: str = "") -> int:
    why = _unit_or_none(root, unit, "seal")
    if why:
        return _refuse(why, EXIT_NONE)
    unit = unit.lower()
    now = seal_state(root, unit)
    if now == "sealed":
        print(f"{unit}: sealed — the text the owner approved")
        return EXIT_OK
    if now == "changed" and (in_session or not owner_flag):
        return _refuse(f"REFUSED: {unit} changed since the owner approved it; " +
                       (IN_SESSION.format(unit=unit) if in_session else f"the owner runs `journeys.py seal {unit} --owner-approved` in their own terminal"),
                       EXIT_USAGE if in_session else EXIT_REFUSED)
    if now == "unsealed" and goals.unattended(root):
        return _refuse(SEALS_TO_ASK.format(unit=unit), EXIT_USAGE)
    why = goals.answer_error(answer) if in_session or answer.strip() else ""
    if why:
        return _refuse(why)
    done = _apply_change(root, unit, "seal") if now == "changed" else _seal_checked(root, unit, "seal")
    if done == EXIT_OK and answer.strip():
        what = f"{unit} {unit_rel(root, unit)}"
        line = goals.record_approval(root, APPROVALS_REL, what, goals.digest(root / unit_rel(root, unit)), answer, where)
        print(f"the owner's answer -> {APPROVALS_REL}: {line}")
    return done


def _seal_checked(root: Path, unit: str, verb: str) -> int:
    errors = all_errors(root).get(unit, [])
    if errors:
        for error in errors:
            print(f"{verb}: REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{verb}: sealed {unit_rel(root, unit)}  sha256 {write_seal(root, unit)[:12]}…  -> {STATE_DIR.as_posix()}/{unit}.sha256")
    return EXIT_OK


def _approved(root: Path, unit: str, approved: str, verb: str, in_session: bool) -> str:
    """Why the owner's «так» does not apply to the unit as it is now, or ""."""
    if in_session:
        return f"{verb}: {IN_SESSION.format(unit=unit)}"
    why = _unit_or_none(root, unit, verb)
    if why:
        return why
    found = goals.digest(root / unit_rel(root, unit.lower()))
    return "" if approved and found == approved else f"{verb}: {unit} is {found}, the owner approved {approved or '(no sha256)'}; not sealed"


def first_seal(root: Path, unit: str, approved: str, in_session: bool) -> int:
    why = _approved(root, unit, approved, "first-seal", in_session)
    if why:
        return _refuse(why, EXIT_USAGE if in_session else EXIT_REFUSED)
    unit = unit.lower()
    now = seal_state(root, unit)
    if now == "sealed":
        print(f"first-seal: {unit} is sealed already")
        return EXIT_OK
    if now == "changed":
        return _refuse(f"first-seal: {unit} was approved before and changed since: that is `amend`", 1)
    return 1 if _seal_checked(root, unit, "first-seal") else EXIT_OK


def amend(root: Path, unit: str, approved: str, in_session: bool) -> int:
    why = _approved(root, unit, approved, "amend", in_session)
    if why:
        return _refuse(why, EXIT_USAGE if in_session else EXIT_REFUSED)
    unit = unit.lower()
    now = seal_state(root, unit)
    if now != "changed":
        return _refuse(f"amend: {unit} is {now}: an amendment applies to a unit sealed before and changed since", 1)
    return 1 if _apply_change(root, unit, "amend") else EXIT_OK


def _apply_change(root: Path, unit: str, verb: str) -> int:
    """Seal a changed unit the owner approved: the AC numbers stay, what cited a changed AC is listed for review."""
    snapshot = root / STATE_DIR / f"{unit}.sealed.md"
    new = (root / unit_rel(root, unit)).read_text(encoding="utf-8")
    stale: list[tuple[str, str]] = []
    if unit.startswith("j-"):
        old = snapshot.read_text(encoding="utf-8") if snapshot.is_file() else ""
        errors, changed = change_errors(old, new) if old else ([], sorted(acs_of(new)))  # no copy on this machine: every AC is reread
        if errors:
            return _refuse(f"{verb}: REFUSED: " + "; ".join(errors))
        stale = citing(root, int(unit[2:]), changed)
    if _seal_checked(root, unit, verb):
        return EXIT_REFUSED
    if stale:
        review = root / REVIEW_REL
        text = review.read_text(encoding="utf-8") if review.is_file() else (
            "# Функції, які треба переглянути\n\nКожен рядок дописав `journeys.py amend`: функція посилалася на критерій приймання "
            "journey, який змінився. Архітектор перечитує функцію і ставить `[x]`.\n\n")
        review.write_text(text + "".join(f"- [ ] {unit} v{goals.version(new)} {ref} → {path}\n" for path, ref in stale), encoding="utf-8")
    print(f"{verb}: {len(stale)} feature citation(s) marked for review in {REVIEW_REL}")
    return EXIT_OK


# ------------------------------------------------------------------ status, check, gate, trace


def cmd_status(root: Path) -> int:
    if not (root / INDEX_REL).is_file():
        return _refuse(f"no journeys ({INDEX_REL}): /journey-architect writes them with the owner", EXIT_NONE)
    states = {unit: seal_state(root, unit) for unit in units(root)}
    for unit, now in states.items():
        print(f"{unit}\t{now}\t{unit_rel(root, unit) or '-'}")
    return EXIT_OK if all(s == "sealed" for s in states.values()) else EXIT_REFUSED


def cmd_check(root: Path, wanted: list[str]) -> int:
    if not (root / INDEX_REL).is_file():
        return _refuse(f"no journeys ({INDEX_REL})", EXIT_NONE)
    errors = all_errors(root)
    unknown = [u for u in wanted if u.lower() not in errors]
    if unknown:
        return _refuse(f"no such unit: {', '.join(unknown)} (index, interference, j-N)", EXIT_NONE)
    bad = 0
    for unit in [u.lower() for u in wanted] or list(errors):
        for error in errors[unit]:
            print(f"REFUSED: {error}", file=sys.stderr)
        bad += bool(errors[unit])
        if not errors[unit]:
            print(f"ok: {unit}")
    return EXIT_REFUSED if bad else EXIT_OK


def gate_reasons(root: Path) -> tuple[int, list[str]]:
    """(exit, why not) for «may features be cut»: what M4 and the feature architect ask."""
    index = _show(root)(INDEX_REL)
    if not index:
        return EXIT_NONE, [(f"no {INDEX_REL}: declare `Інтерфейс:` (екрани | розмова | екрани і розмова | немає) — a product a person "
                            "sees or talks to gets its journeys from /journey-architect before features are cut")]
    errors = all_errors(root)
    if interface(index) == "none":
        return (EXIT_REFUSED, errors["index"]) if errors.get("index") else (EXIT_OK, [])
    reasons = [e for unit_errors in errors.values() for e in unit_errors]
    reasons += [f"{unit} is {seal_state(root, unit)}: not in force until the owner approves it" for unit in units(root) if seal_state(root, unit) != "sealed"]
    return (EXIT_REFUSED if reasons else EXIT_OK), reasons


def cmd_gate(root: Path) -> int:
    code, reasons = gate_reasons(root)
    for reason in reasons:
        print(f"REFUSED: {reason}", file=sys.stderr)
    if code == EXIT_OK:
        kind = interface(_show(root)(INDEX_REL))
        print("journeys: none required (Інтерфейс: немає)" if kind == "none" else "journeys: every unit sealed and checked — features are cut from them")
    elif code == EXIT_REFUSED:
        print("A feature with screens or a conversation is not built on unapproved journeys: park it with the draft and a question to the owner "
              "(owner's decision, board 208: «Ні, паркує»)", file=sys.stderr)
    return code


def trace_errors(root: Path) -> list[str]:
    found = journeys(root)
    standing = {(n, k) for n, j in found.items() for k, (struck, _) in j.acs.items() if not struck}
    struck = {(n, k) for n, j in found.items() for k, (s, _) in j.acs.items() if s}
    errors, cited = [], set()
    folder = root / FEATURES_REL
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        rel, text = path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")
        match = AC_HEADING.search(text)
        if not match:
            continue
        for line in goals.COMMENT.sub("", goals._body(text, match)).splitlines():
            item = line.strip()
            if not item.startswith("- "):
                continue
            refs = [(int(j), int(k)) for j, k in AC_REF.findall(item)]
            if not refs and not TECH.match(item[2:].strip()):
                errors.append(f"{rel}: «{item[2:62]}» cites no journey criterion (`J-N#AC-k`) and is not marked `[тех]` — "
                              "a product criterion the owner never approved")
            for ref in refs:
                if ref in struck:
                    errors.append(f"{rel}: J-{ref[0]}#AC-{ref[1]} is struck out of its journey")
                elif ref not in standing:
                    errors.append(f"{rel}: J-{ref[0]}#AC-{ref[1]} is not a criterion of a journey")
                cited.add(ref)
    return errors + [f"J-{n}#AC-{k} is cited by no feature: a step of the journey nobody builds" for n, k in sorted(standing - cited)]


def cmd_trace(root: Path) -> int:
    code, reasons = gate_reasons(root)
    if code != EXIT_OK:
        for reason in reasons:
            print(f"REFUSED: {reason}", file=sys.stderr)
        return code
    if interface(_show(root)(INDEX_REL)) == "none":
        print("journeys: none required (Інтерфейс: немає) — nothing to trace")
        return EXIT_OK
    errors = trace_errors(root)
    for error in errors:
        print(f"REFUSED: {error}", file=sys.stderr)
    if not errors:
        print("trace: every journey criterion is cited by a feature, every feature criterion cites one or is technical")
    return EXIT_REFUSED if errors else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "gate", "trace"):
        sub.add_parser(name)
    sub.add_parser("check").add_argument("units", nargs="*")
    seal = sub.add_parser("seal")
    seal.add_argument("unit")
    seal.add_argument("--owner-approved", action="store_true",
                      help="the owner's flag, for the owner's own terminal; inside a Claude Code session it does not count")
    seal.add_argument("--answer", default="", help="the owner's answer, verbatim — the approval the seal rests on (board 210)")
    seal.add_argument("--where", default="", help="where the owner said it: the session or the channel")
    for name in ("first-seal", "amend"):
        verb = sub.add_parser(name)
        verb.add_argument("unit")
        verb.add_argument("sha256", nargs="?", default="")
    args = parser.parse_args(argv)
    root = goals.project_root()
    in_session = bool(os.environ.get("CLAUDECODE"))
    if args.command == "status":
        return cmd_status(root)
    if args.command == "check":
        return cmd_check(root, args.units)
    if args.command == "gate":
        return cmd_gate(root)
    if args.command == "trace":
        return cmd_trace(root)
    if args.command == "seal":
        return cmd_seal(root, args.unit, args.owner_approved, in_session, args.answer, args.where)
    if args.command == "first-seal":
        return first_seal(root, args.unit, args.sha256, in_session)
    return amend(root, args.unit, args.sha256, in_session)


if __name__ == "__main__":
    sys.exit(main())
