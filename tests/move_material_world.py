"""Test helpers of the slice move-material: a model fake that also answers `choose_material`, and a world
around `cases.move_material` with notes, photos and files made the lawful way (S1, S2).

Written by the slice tester from the sealed contract `.engine/slices/move-material.md`, without the code.
The `choose_material` fake reads the numbered catalogues of the prompt it is given: a material by the number
in front of the line that carries the first words of its text, a case by the number in front of its name on a
line that carries no material's text (a material line names its case too). So the tests do not fix how the
catalogues are numbered or laid out. Every description the fake answers is unique (`[опис N]`), and the prompt
it was built from is kept, so a test can read what a description was built from.
"""

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import cases as case_module
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Question, Reply
from tests.note_to_case_world import DEADLINE, Clock, Notes, fill
from tests.photo_and_file_world import PNG, FakeFiles, FileAI, Uploads
from tests.test_one_task_planning import NOW, make_config, make_session

WHAT = "Не зрозуміла, що саме перекласти. Скажіть, що це і куди."
WHERE = "Не зрозуміла, куди перекласти. Скажіть, у яку справу."
SNIPPET = 30
"""How many first characters of a material's text the fake looks for (the catalogue carries the first 80)."""


def moved(words: str, name: str) -> str:
    return f"Переклала «{words}» у «{name}»."


def already(name: str) -> str:
    return f"Це вже в «{name}»."


def ask(name: str) -> str:
    return f"Створити справу «{name}»?"


def placed(name: str) -> str:
    return f"Поклала в «{name}»."


def _leading_number(line: str) -> int | None:
    """The number a catalogue line starts with, else its first number."""
    leading = re.match(r"\s*[-*•]?\s*[\[(#№]?\s*(\d+)", line)
    if leading is not None:
        return int(leading.group(1))
    first = re.search(r"\d+", line)
    return int(first.group(0)) if first is not None else None


def material_number(prompt: str, text: str) -> int | None:
    """The number of the catalogue line that carries the first words of `text`, or None."""
    snippet = text[:SNIPPET]
    for line in prompt.splitlines():
        if snippet in line:
            return _leading_number(line)
    return None


def case_number(prompt: str, name: str, avoid: list[str]) -> int | None:
    """The number standing in front of `name` on a line that carries none of the texts in `avoid`, or None."""
    pattern = re.compile(r"\s*[-*•]?\s*[\[(#№]?\s*(\d+)\s*[\]).:\-—]?\s*[-—:.)]?\s*[«\"„]?" + re.escape(name))
    for line in prompt.splitlines():
        if any(snippet in line for snippet in avoid):
            continue
        found = pattern.match(line)
        if found is not None:
            return int(found.group(1))
    return None


class MoveAI(FileAI):
    """`FileAI` that answers `choose_material` as told and every `describe_case` with a unique description.

    `choose(material, case, new_case)`: `material` is a material's text (found in the catalogue) or a raw
    number; `case` a case's name (found in the catalogue) or a raw number; `new_case` the new name or None."""

    def __init__(self) -> None:
        super().__init__()
        self.pick: tuple[str | int | None, str | int | None, str | None] = (None, None, None)
        self.avoid: list[str] = []
        self.described: dict[str, str] = {}

    def choose(
        self, material: str | int | None, case: str | int | None = None, new_case: str | None = None
    ) -> None:
        self.pick = (material, case, new_case)

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "choose_material":
            self.calls.append(task_type)
            material, case, new_case = self.pick
            if isinstance(material, str):
                material = material_number(prompt, material)
            if isinstance(case, str):
                case = case_number(prompt, case, self.avoid)
            return {"material": material, "case": case, "new_case": new_case}
        if task_type == "describe_case":
            self.calls.append(task_type)
            description = f"[опис {len(self.descriptions) + 1}]"
            self.descriptions.append(description)
            self.described[description] = prompt
            return fill(schema, description)
        return super()._answer(task_type, prompt, schema)


@dataclass
class Moves:
    ai: MoveAI = field(default_factory=MoveAI)
    files: FakeFiles = field(default_factory=FakeFiles)
    store: InMemoryStore = field(default_factory=InMemoryStore)
    config: Config = field(default_factory=make_config)
    session: Session = field(default_factory=make_session)
    clock: Clock = field(default_factory=Clock)

    @property
    def notes(self) -> Notes:
        return Notes(ai=self.ai, store=self.store, config=self.config, session=self.session, clock=self.clock)

    @property
    def uploads(self) -> Uploads:
        return Uploads(
            ai=self.ai,
            files=self.files,
            store=self.store,
            config=self.config,
            session=self.session,
            clock=self.clock,
        )

    def other(self, account_id: str = "acc-2") -> "Moves":
        """A second account over the same store, files and model."""
        return Moves(
            ai=self.ai,
            files=self.files,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
        )

    # -------------------------------------------------------------- making the world the lawful way

    def seed(self, name: str, material_id: str) -> case_module.Case:
        """A case made by a note and «так». On an empty catalogue its name is not fixed (S1 Q1): read back."""
        before = {c.case_id for c in self.cases()}
        self.ai.new_case(name)
        self.ai.default_name = name
        self.notes.add(f"відкриваю справу {material_id}", material_id)
        self.notes.yes(material_id)
        made = [c for c in self.cases() if c.case_id not in before]
        assert len(made) == 1, made
        return made[0]

    def _aim(self, to: case_module.Case | str | None) -> None:
        if isinstance(to, case_module.Case):
            self.ai.file_to(to.name)
        elif isinstance(to, str):
            self.ai.new_case(to)
        else:
            self.ai.nowhere()

    def note(self, text: str, material_id: str, to: case_module.Case | str | None) -> case_module.Material:
        """A note into the case `to`, pending on the new name `to`, or unplaced (`to` None)."""
        self._aim(to)
        self.notes.add(text, material_id)
        return self.material(material_id)

    def photo(
        self, text: str, material_id: str, to: case_module.Case | str | None, mime: str = "image/png"
    ) -> case_module.Material:
        """A photo (or, with another mime, a file) read as `text`, filed like `note`."""
        self._aim(to)
        self.ai.read_text = text
        self.uploads.add(material_id, PNG, mime)
        return self.material(material_id)

    # -------------------------------------------------------------- the slice

    def move(
        self,
        material: str | int | None,
        case: case_module.Case | str | int | None = None,
        new_case: str | None = None,
        text: str = "переклади це туди",
    ) -> Reply:
        self.ai.choose(material, case.name if isinstance(case, case_module.Case) else case, new_case)
        self.ai.avoid = [m.text[:SNIPPET] for m in self.materials() if m.text]
        return case_module.move_material(
            self.session,
            text,
            ai=cast(AI, self.ai),
            store=self.store,
            now=NOW,
            config=self.config,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def try_move(self, *args: Any, **kwargs: Any) -> Reply | None:
        """`move` that may fail: None when it raised (a missing implementation is no lawful failure)."""
        try:
            return self.move(*args, **kwargs)
        except NotImplementedError:
            raise
        except Exception:
            return None

    def choose(self, material_id: str, text: str) -> Reply:
        """S3 `choose_case`: the answer naming a case to «У яку справу покласти?»."""
        return case_module.choose_case(
            self.session,
            material_id,
            text,
            ai=cast(AI, self.ai),
            store=self.store,
            now=NOW,
            config=self.config,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def message(
        self, text: str, message_id: str, reply_to: Question | None = None, now: datetime = NOW
    ) -> Reply:
        return self.notes.message(text, message_id, reply_to, now)

    # -------------------------------------------------------------- reading

    def materials(self) -> list[case_module.Material]:
        return case_module.materials_catalogue(self.session, self.store)

    def material(self, material_id: str) -> case_module.Material:
        found = [m for m in self.materials() if m.material_id == material_id]
        assert len(found) == 1, (material_id, found)
        return found[0]

    def cases(self) -> list[case_module.Case]:
        return case_module.catalogue(self.session, self.store)

    def case(self, case_id: str) -> case_module.Case:
        found = [c for c in self.cases() if c.case_id == case_id]
        assert len(found) == 1, (case_id, found)
        return found[0]

    def documents(self) -> dict[str, list[tuple[str, dict[str, Any]]]]:
        """Every case and material document of the account, as stored."""
        account = self.session.account_id
        return {
            "cases": copy.deepcopy(self.store.list(account, case_module.CASES)),
            "materials": copy.deepcopy(self.store.list(account, case_module.MATERIALS)),
        }

    def built_from(self, case_id: str) -> str:
        """The prompt the case's current description was built from (the description must be the fake's)."""
        description = self.case(case_id).description
        assert description in self.ai.described, (case_id, description)
        return self.ai.described[description]

    def question_ids(self) -> list[str]:
        ids = []
        for item in case_module.open_questions(self.session, self.store):
            assert item.reply.question is not None, item
            ids.append(item.reply.question.id)
        return ids

    def reset_clock(self) -> None:
        self.clock.at = NOW
