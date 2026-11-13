#!/usr/bin/env python3
"""The owner's walk of a journey as a condition, not a note: the next feature waits for it.

    python3 .claude/hooks/owner_walk.py walk-card j-N [--feedback <record>]   # the card, as a question in tasks/blocked/
    python3 .claude/hooks/owner_walk.py gate <feature>                        # may <feature> start: 0 yes, 3 no
    python3 .claude/hooks/owner_walk.py status                                # every walk the stage requires, accepted or not

WHY (board 412; docs/research/2026-11-userflow/R4-flow-first-process.md §3.2). In mamamemory the card
«F2: пройти план тижня на телефоні» (721) hung in tasks/blocked/ from 07.11, nobody answered it, and F3,
F4, F5 and ten slices were built on top: a check by the owner that nothing waited for. Here the walk is
a dependency:

  * THE CARD. `walk-card j-N` writes `.engine/journeys/walks/j-N.md` from `.claude/templates/owner-walk.md`:
    the steps of the journey's sample dialog in the owner's words («зробіть → маєте побачити / почути»), the
    revision of the journey (the sha256 of its sealed file) and every feature built on it with the revision
    of the code its journeys passed on (`testing.py journey-close`, the testing ledger). It puts the card in
    tasks/blocked/ with the question and `Дія runner-а: accept-walk j-N <sha256 of the card>`; a card asked
    before and not answered is closed as replaced.
  * THE OWNER'S «так». Only the board runner accepts a walk: `owner_action.py accept-walk` calls `accept`,
    which appends a row to `.engine/journeys/acceptance.md` — the journey, its revision, the card, the
    features at their revisions, the date and the owner's word. Nobody else writes that file: it is in
    GUARDED_PATTERNS (protect-paths), the runner commits it. «так, але потім» is not consent (board.is_word):
    it comes back to the agent as feedback (`/owner-feedback`).
  * THE GATE. `gate <feature>` — the feature architect's pre-flight. A feature is built when its journeys
    closed (a `journey_close` row of `.engine/testing/ledger.md`). What needs a walk is the stage's
    (`.claude/project-stage`, stage.py) and the owner's word (2026-11-12, «За стадією»): internal — only
    the core journey (`Ядро:` of INDEX.md), whenever a built feature changed it; production — every journey
    a built feature cites. A pair (journey, built feature) is accepted when a row has the journey at its
    current revision and the feature at the revision of its last close. A journey changed since → red
    again («полагодили — перевірте ще раз»); the feature asked about is not required of itself.

Exit: 0 fine; 3 refused (a walk not accepted, a card that cannot be written, a stale «так»); 2 usage.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import string
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goals  # the project root and the sha256 of a file
import journey_e2e  # the journeys a feature cites
import journeys  # the journeys' files, their seals and the INDEX
import stage  # internal or production
import walker  # the user-walker's last walk of a journey, for the card

WALKS_REL = f"{journeys.DIR_REL}/walks"
ACCEPTANCE_REL = f"{journeys.DIR_REL}/acceptance.md"
LEDGER_REL = ".engine/testing/ledger.md"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "owner-walk.md"
LEDGER_ROW = re.compile(r"^<!-- row: (.*) -->$", re.MULTILINE)
FIELD_FEATURES = re.compile(r"^Функції:\s*(.*)$", re.MULTILINE)
FIELD_JOURNEY_SHA = re.compile(r"^Ревізія journey:\s*([0-9a-f]{64})\s*$", re.MULTILINE)
MAX_STEPS = 7
WORK = ("Це питання до власника. «так» виконує runner (`accept-walk`). Будь-яка інша відповідь — відгук: коли задача повернеться "
        "в чергу, розбери його `/owner-feedback` (кожне спостереження — запис у `.engine/feedback/`, `feedback.py check`), "
        "запиши у звіт і закрий задачу; нова картка проходу — наприкінці розбору.")
EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 2, 3
ACCEPTANCE_HEAD = (
    "# Прохід власника: що прийнято\n\n"
    "Пише лише `owner_walk.py accept` — board runner за відповіддю власника «так» під карткою проходу "
    "(`owner_action.py accept-walk`). Рядок приймає journey на ревізії, з якою його пройдено, і функції на ревізіях коду; "
    "змінений journey чи нове закриття функції вимагає нового проходу (`owner_walk.py gate`).\n\n"
    "| Journey | Ревізія journey | Картка | Функції | Коли (UTC) | Слово власника |\n|---|---|---|---|---|---|\n")


def closed_features(root: Path) -> dict[str, str]:
    """feature -> the code revision of its last journey close, read from the testing ledger (committed)."""
    path = root / LEDGER_REL
    found: dict[str, str] = {}
    for raw in LEDGER_ROW.findall(path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""):
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("type") == "journey_close" and row.get("feature"):
            found[str(row["feature"])] = str(row.get("sha", ""))[:12]
    return found


def built_on(root: Path, number: int, skip: str = "") -> dict[str, str]:
    """The built features (feature -> revision) whose acceptance criteria cite journey `number`."""
    return {f: rev for f, rev in closed_features(root).items() if f != skip and number in (journey_e2e.feature_journeys(root, f) or [])}


def core(root: Path) -> list[int]:
    return [int(n) for n in journeys.J_REF.findall(journeys.header(journeys._show(root)(journeys.INDEX_REL), "Ядро", "Core"))]


def journey_sha(root: Path, number: int) -> str:
    found = journeys.journeys(root).get(number)
    return goals.digest(root / found.rel) if found else ""


def accepted(root: Path) -> list[tuple[str, str, set[str]]]:
    """(unit, journey revision, {feature@revision}) of every acceptance row."""
    path = root / ACCEPTANCE_REL
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"j-\d+", cells[0]) and re.fullmatch(r"[0-9a-f]{64}", cells[1]):
            rows.append((cells[0], cells[1], {f.strip() for f in cells[3].split(",") if f.strip()}))
    return rows


def required(root: Path, skip: str = "") -> tuple[str, list[tuple[int, str, str]]]:
    """(stage, [(journey, feature, revision)]) — the walks the stage requires before another feature starts."""
    now, _ = stage.read_stage(root)
    cores = set(core(root))
    pairs = []
    for feature, rev in closed_features(root).items():
        if feature == skip:
            continue
        for number in journey_e2e.feature_journeys(root, feature) or []:
            if now == stage.PRODUCTION or number in cores:
                pairs.append((number, feature, rev))
    return now, sorted(pairs)


def missing(root: Path, skip: str = "") -> tuple[str, list[str]]:
    now, pairs = required(root, skip)
    rows = accepted(root)
    out = []
    for number, feature, rev in pairs:
        sha = journey_sha(root, number)
        if not any(unit == f"j-{number}" and seen == sha and f"{feature}@{rev}" in features for unit, seen, features in rows):
            kind = "the core journey" if number in core(root) else "a journey"
            out.append(f"J-{number} ({kind}) after {feature}@{rev}: no owner walk accepted for its revision {sha[:12] or '(no file)'} — "
                       f"`owner_walk.py walk-card j-{number}` puts the card in tasks/blocked/")
    return now, out


# ------------------------------------------------------------------ the card


def card_steps(journey: journeys.Journey) -> list[tuple[str, str, str]]:
    return [(row[0], row[1], row[2]) for row in journeys.table(journey.text, "Крок", "Step") if row and row[0].isdigit() and len(row) >= 3]


def card_text(root: Path, number: int, journey: journeys.Journey, features: dict[str, str], feedback: str) -> str:
    title = journey.text.splitlines()[0].lstrip("# ").strip() if journey.text.strip() else f"J-{number}"
    rows = "\n".join(f"| {n} | {do} | {see} |  |" for n, do, see in card_steps(journey))
    return string.Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        title=title, unit=f"j-{number}", journey_sha=goals.digest(root / journey.rel),
        features=", ".join(f"{f}@{rev}" for f, rev in sorted(features.items())),
        feedback=f"Після відгуку: {feedback}\n" if feedback else "", steps=rows, walker=walker.card_note(root, f"j-{number}"))


def walk_card(root: Path, unit: str, feedback: str) -> int:
    match = re.fullmatch(r"j-(\d+)", unit.lower())
    if not match:
        return _refuse(f"walk-card: «{unit}» is not a journey (j-N)", EXIT_USAGE)
    number, unit = int(match[1]), unit.lower()
    journey = journeys.journeys(root).get(number)
    if journey is None:
        return _refuse(f"walk-card: no journey J-{number} in {journeys.DIR_REL}/")
    if journeys.seal_state(root, unit) != "sealed":
        return _refuse(f"walk-card: {unit} is {journeys.seal_state(root, unit)} — the owner walks the journey they approved; "
                       "seal it first (`board.py action-line seal-journey`)")
    features = built_on(root, number)
    if not features:
        return _refuse(f"walk-card: nothing built on J-{number} has closed on its journeys (`testing.py journey-close <feature>`): "
                       "the owner walks a journey after the automatic one passed")
    steps = card_steps(journey)
    if len(steps) > MAX_STEPS:
        print(f"walk-card: J-{number} has {len(steps)} steps; a card longer than {MAX_STEPS} is a long walk — consider splitting the journey",
              file=sys.stderr)
    path = root / WALKS_REL / f"{unit}.md"
    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = card_text(root, number, journey, features, feedback)
    path.write_text(text, encoding="utf-8")
    sha = goals.digest(path)
    board = stage.board_module()
    if board is None or not (root / "tasks").is_dir():
        print(f"walk-card: {path.relative_to(root)} written (sha256 {sha}); no task board here — show the card to the owner")
        return EXIT_OK
    item = _ask(root, board, unit, text, sha)
    if item is None:
        return _refuse("walk-card: the card is written but no question could be put in tasks/blocked/")
    old = hashlib.sha256(before.encode("utf-8")).hexdigest()[:12] if before else ""
    if old and old != sha[:12]:
        board.close_item(board.Board(root / "tasks"), f"walk-{unit}-{old}", f"картку проходу {unit} замінено новою ({item.name})")
    line = f"Дія runner-а: accept-walk {unit} {sha}"
    task = item.read_text(encoding="utf-8")
    if line not in task:
        item.write_text(task.replace("\n   Відповідь:\n", f"\n   {line}\n   Відповідь:\n", 1), encoding="utf-8")
    print(f"walk-card: {path.relative_to(root)} → {item.relative_to(root)}  ({line})")
    return EXIT_OK


def _ask(root: Path, board: Any, unit: str, text: str, sha: str) -> Path | None:
    question = (f"Пройдіть картку проходу {unit} нижче на телефоні. Прийняти прохід? Варіанти: «так» — прохід прийнято, наступна "
                "функція стартує; будь-яка інша відповідь — ваш відгук, агент розбере його (`/owner-feedback`) і попросить пройти знову. "
                "Порада: «так», лише якщо кожен крок був таким, як у картці.")
    item: Path | None = board.open_item(board.Board(root / "tasks"), "blocked", f"Прохід власника {unit}",
                           f"Функції збудовано, автоматичні сценарії пройдено; наступна функція чекає вашого проходу (board 412). "
                           f"Картка: `{WALKS_REL}/{unit}.md`.", question=question, key=f"walk-{unit}-{sha[:12]}", source="owner_walk.py")
    if item is None:
        return None
    task = item.read_text(encoding="utf-8")
    if "## Картка проходу" not in task:
        work = re.compile(r"(\n## Що зробити\n)[^\n]*\n")
        item.write_text(work.sub(lambda m: f"\n## Картка проходу\n\n{text}{m[1]}{WORK}\n", task, count=1), encoding="utf-8")
    return item


# ------------------------------------------------------------------ the owner's «так» (the runner's, through owner_action.py)


def accept(root: Path, unit: str, approved: str) -> int:
    """Append the acceptance row when the card is the one the owner said «так» to. 0 accepted, 3 stale."""
    unit = unit.lower()
    match = re.fullmatch(r"j-(\d+)", unit)
    path = root / WALKS_REL / f"{unit}.md"
    if not match or not path.is_file():
        print(f"owner-action: accept-walk: no card {WALKS_REL}/{unit}.md", file=sys.stderr)
        return EXIT_REFUSED
    text = path.read_text(encoding="utf-8")
    found = goals.digest(path)
    if found != approved:
        print(f"owner-action: accept-walk: the card is {found}, the owner approved {approved or '(no sha256)'}; not accepted", file=sys.stderr)
        return EXIT_REFUSED
    seen = FIELD_JOURNEY_SHA.search(text)
    now = journey_sha(root, int(match[1]))
    if not seen or seen[1] != now:
        print(f"owner-action: accept-walk: J-{match[1]} changed since the card was written ({(seen[1] if seen else '?')[:12]} → {now[:12]}); "
              "the owner walked another revision: not accepted", file=sys.stderr)
        return EXIT_REFUSED
    features = FIELD_FEATURES.search(text)
    target = root / ACCEPTANCE_REL
    head = "" if target.is_file() else ACCEPTANCE_HEAD
    when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{head}| {unit} | {now} | {approved} | {features[1].strip() if features else ''} | {when} | "
                     "«так» — відповідь власника під карткою проходу (runner) |\n")
    print(f"owner-action: accept-walk: {unit} accepted at {now[:12]} → {ACCEPTANCE_REL}")
    return EXIT_OK


# ------------------------------------------------------------------ the gate


def gate(root: Path, feature: str) -> int:
    index = journeys._show(root)(journeys.INDEX_REL)
    if not index or journeys.interface(index) == "none":
        print("owner walk: no journeys a person walks here — nothing to wait for")
        return EXIT_OK
    now, reasons = missing(root, feature)
    for reason in reasons:
        print(f"REFUSED: {reason}", file=sys.stderr)
    if reasons:
        print(f"{feature} does not start: the owner has not walked what is built (stage {now}; board 412, the owner's «За стадією»). "
              "Attended: tell the owner what to walk. Unattended: the card in tasks/blocked/, "
              "`OVERSEER_SLICE_AWAITING_OWNER: owner walk`, and work that does not depend on it.", file=sys.stderr)
        return EXIT_REFUSED
    print(f"owner walk: every walk the stage ({now}) requires is accepted — {feature} may start")
    return EXIT_OK


def status(root: Path) -> int:
    now, pairs = required(root)
    gone = missing(root)[1]
    for number, feature, rev in pairs:
        print(f"J-{number}\t{feature}@{rev}\t{'waits' if any(r.startswith(f'J-{number} ') and f'{feature}@{rev}' in r for r in gone) else 'accepted'}")
    print(f"stage {now}: {len(pairs) - len(gone)} of {len(pairs)} walk(s) accepted")
    return EXIT_REFUSED if gone else EXIT_OK


def _refuse(message: str, code: int = EXIT_REFUSED) -> int:
    print(message, file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    card = sub.add_parser("walk-card")
    card.add_argument("unit")
    card.add_argument("--feedback", default="", help="the feedback record this card follows (`.engine/feedback/<name>.md`)")
    sub.add_parser("gate").add_argument("feature")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    root = goals.project_root()
    if args.command == "walk-card":
        return walk_card(root, args.unit, Path(args.feedback).stem if args.feedback else "")
    if args.command == "gate":
        return gate(root, args.feature)
    return status(root)


if __name__ == "__main__":
    sys.exit(main())
