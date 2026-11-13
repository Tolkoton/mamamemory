#!/usr/bin/env python3
"""The owner's feedback, taken at the level of the journey and the class — not one phrase.

    python3 .claude/hooks/feedback.py check [<record> ...]   # every record of .engine/feedback/ by default: 0 / 3

WHY (board 412; docs/research/2026-11-userflow/R4-flow-first-process.md §3.3). mamamemory, 11.11 18:45:
«Я сказав, які в нас плани на сьогодні? А воно … сказало. Скільки часу це займає?» — a pending question
caught the next phrase. The fix closed the question of duration only; on 12.11 the questions of the
week's plan did the same. A complaint was patched as a phrase. `/owner-feedback` takes it as a class, and
this script checks the record mechanically (`.claude/templates/feedback-record.md`):

  * THE QUOTE — a date and the owner's words verbatim in «».
  * THE PLACE — a journey J-N of `.engine/journeys/` and a step of its sample dialog. A class
    «відсутній J» instead names the question to the owner (`Питання власникові: tasks/…`): behaviour no
    journey has is a product decision (Article 5), not a slice — and nothing else is asked of the record.
  * THE CLASS — one of CLASSES.
  * THE SAME PLACES — a table over the WHOLE inventory of states: every `J-N S-k` of every journey (only
    those of the kind `Обсяг:` names, when it names one), each with «так» or «ні» and its evidence. A state
    missing from the table is the class left open — the 12.11 bug.
  * THE JOURNEY FIRST — unless the class is «модель» (the conversation model, not the journey, was wrong),
    the journey's version is above `J до:`: the journey changed before the code.
  * THE TEST ON THE CLASS — `Тест:` is a file that names every state answered «так».
  * THE CORPUS — with a conversation model (`.engine/architecture/conversation-model.json`), `Корпус:` names
    ids found in `tests/conversations/corpus.json` or `complaints.json`: the phrase stays in the corpus.
  * THE NEW WALK — `Картка:` is the walk card of that journey, written after this record
    (`Після відгуку: <record>`, `owner_walk.py walk-card j-N --feedback <record>`) at the journey's current revision.

Exit: 0 every record stands; 3 a record does not; 4 no records. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goals  # the project root, a field of a document, its version
import journeys  # the journeys, their states and steps

FEEDBACK_REL = ".engine/feedback"
MODEL_REL = ".engine/architecture/conversation-model.json"
CORPORA = ("tests/conversations/corpus.json", "tests/conversations/complaints.json")
CLASSES = ("стан", "перехід", "вихід", "відсутній j", "текст", "поріг", "дубль", "модель")
MISSING_J, MODEL = "відсутній j", "модель"
QUOTE = re.compile(r"\d{4}-\d\d-\d\d.*«[^»]*\S[^»]*»")
STATE_REF = re.compile(r"^J-(\d+)\s+(S\d+)$")
EXIT_OK, EXIT_REFUSED, EXIT_NONE = 0, 3, 4


def field(text: str, *names: str) -> str:
    return goals.field(text, *names).strip()


def inventory(found: dict[int, journeys.Journey], scope: str) -> list[str]:
    """Every state `J-N S-k` of every journey, of the kind `scope` names (all when it names none)."""
    return [f"J-{n} {sid}" for n, j in sorted(found.items()) for sid, (kind, _) in j.states.items() if scope in ("", "усі", "all") or kind == scope]


def same_places(text: str) -> dict[str, tuple[str, str]]:
    """`J-N S-k` -> (так | ні | what was written, the evidence) of the table «Ті самі місця»."""
    rows = journeys.table(journeys.section(text, "Ті самі місця", "Same places"), "Стан", "State")
    return {" ".join(row[0].split()): (row[1].strip().lower() if len(row) > 1 else "", row[2].strip() if len(row) > 2 else "")
            for row in rows if row and row[0]}


def errors(root: Path, path: Path) -> list[str]:
    text = goals.COMMENT.sub("", path.read_text(encoding="utf-8"))
    out = [] if QUOTE.search(field(text, "Цитата", "Quote")) else ["no `Цитата:` with a date and the owner's words verbatim in «»"]
    kind = field(text, "Клас", "Class").lower()
    if kind not in CLASSES:
        return out + [f"`Клас:` is «{kind}»; the classes are {', '.join(CLASSES)}"]
    if kind == MISSING_J:
        asked = field(text, "Питання власникові", "Question to the owner")
        return out + ([] if asked and (root / asked).is_file() else
                      [(f"class «відсутній J»: `Питання власникові:` names no task ({asked or 'nothing'}) — behaviour no journey has is "
                        "the owner's question (Article 5), not a slice")])
    try:
        found = journeys.journeys(root)
    except ValueError as exc:
        return out + [str(exc)]
    ref = journeys.J_REF.fullmatch(field(text, "Journey"))
    journey = found.get(int(ref[1])) if ref else None
    if journey is None:
        return out + [f"`Journey:` names no journey of {journeys.DIR_REL}/ (J-N); a step no journey has is the class «відсутній J»"]
    step = field(text, "Крок", "Step")
    if not step.isdigit() or int(step) not in journey.steps:
        out.append(f"`Крок:` «{step}» is not a step of J-{journey.number}'s sample dialog ({', '.join(map(str, journey.steps))})")
    out += _class_errors(root, text, found, kind)
    out += _journey_first(text, journey, kind)
    out += _corpus_errors(root, text)
    out += _card_errors(root, text, path, journey)
    return out


def _class_errors(root: Path, text: str, found: dict[int, journeys.Journey], kind: str) -> list[str]:
    scope = field(text, "Обсяг", "Scope").lower()
    if scope not in ("", "усі", "all") and scope not in journeys.KINDS:
        return [f"`Обсяг:` «{scope}» is not a kind of state ({', '.join(sorted(journeys.KINDS))}) nor «усі»"]
    wanted, table = inventory(found, scope), same_places(text)
    out = []
    left = [s for s in wanted if s not in table]
    if left:
        out.append(f"the same places cover {len(wanted) - len(left)} of {len(wanted)} states of the inventory"
                   f"{' (' + scope + ')' if scope not in ('', 'усі', 'all') else ''}; not looked at: {', '.join(left)} — "
                   f"the class «{kind}» is checked in every state, not in the one where it showed")
    for state, (said, why) in table.items():
        if said not in ("так", "ні", "yes", "no"):
            out.append(f"the same places: {state} — «{said}»; the answer is «так» or «ні»")
        elif not why:
            out.append(f"the same places: {state} has no evidence")
    yes = [s for s, (said, _) in table.items() if said in ("так", "yes")]
    test = field(text, "Тест", "Test")
    if not test or not (root / test).is_file():
        return out + [f"`Тест:` names no file ({test or 'nothing'}): the test is on the class, over every state answered «так»"]
    body = (root / test).read_text(encoding="utf-8", errors="replace")
    for state in yes:
        ref = STATE_REF.match(state)
        number, sid = (ref[1], ref[2]) if ref else ("", state)
        if f"J-{number}" not in body or not re.search(rf"\b{sid}\b", body):
            out.append(f"the test {test} does not name {state}, which has the same defect: the test is on the whole class")
    return out


def _journey_first(text: str, journey: journeys.Journey, kind: str) -> list[str]:
    if kind == MODEL:
        return []
    before = re.fullmatch(r"v?(\d+)", field(text, "J до", "J before"))
    if not before:
        return ["no `J до: v<N>` — the version of the journey when the feedback came"]
    now = goals.version(journey.text)
    if now > int(before[1]):
        return []
    return [f"J-{journey.number} is still v{now}: the class «{kind}» changes the journey first (its Given/When/Then), before the code"]


def _corpus_errors(root: Path, text: str) -> list[str]:
    if not (root / MODEL_REL).is_file():
        return []
    ids = [i for i in re.split(r"[,\s]+", field(text, "Корпус", "Corpus")) if i and i not in ("—", "-")]
    corpus = "".join((root / rel).read_text(encoding="utf-8", errors="replace") for rel in CORPORA if (root / rel).is_file())
    if not ids:
        return ["`Корпус:` names no case: with a conversation model the owner's phrase goes into the corpus for ever"]
    return [f"`Корпус:` {i} is in neither {' nor '.join(CORPORA)}" for i in ids if f'"{i}"' not in corpus]


def _card_errors(root: Path, text: str, path: Path, journey: journeys.Journey) -> list[str]:
    rel = field(text, "Картка", "Card") or f"{journeys.DIR_REL}/walks/j-{journey.number}.md"
    card = root / rel
    if not card.is_file():
        return [f"no new walk card ({rel}): `owner_walk.py walk-card j-{journey.number} --feedback {path.relative_to(root)}`"]
    body = card.read_text(encoding="utf-8")
    if f"Після відгуку: {path.stem}" not in body:
        return [f"the walk card {rel} was not written after this record (no `Після відгуку: {path.stem}`)"]
    if f"Ревізія journey: {goals.digest(root / journey.rel)}" not in body:
        return [f"the walk card {rel} is of another revision of J-{journey.number}: write it again"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").add_argument("records", nargs="*")
    args = parser.parse_args(argv)
    root = goals.project_root()
    folder = root / FEEDBACK_REL
    paths = [root / r if not Path(r).is_absolute() else Path(r) for r in args.records] or (sorted(folder.glob("*.md")) if folder.is_dir() else [])
    if not paths:
        print(f"no feedback records ({FEEDBACK_REL}/)", file=sys.stderr)
        return EXIT_NONE
    bad = 0
    for path in paths:
        if not path.is_file():
            print(f"REFUSED: no such record {path}", file=sys.stderr)
            bad += 1
            continue
        found = errors(root, path)
        for error in found:
            print(f"REFUSED: {path.name}: {error}", file=sys.stderr)
        if not found:
            print(f"ok: {path.name}")
        bad += bool(found)
    return EXIT_REFUSED if bad else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
