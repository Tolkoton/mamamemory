"""Test helpers of the slice note-to-case: a model fake for the route, the Розкладач and the case description,
a clock the fake can move past the deadline, and a world around `cases`.

Written by the slice tester from the sealed contract `.engine/slices/note-to-case.md`, without the code.
The Розкладач fake reads the number standing in front of a case's name in the numbered catalogue of the prompt
it is given, so the tests do not fix how the catalogue is numbered. The description fake answers every string
field of the schema it is given with the same new description, so the tests do not fix the field's name.
A failure is a plain exception raised by the fake; a model call made after the deadline is recorded.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

from mamamemory import assistant
from mamamemory import cases as case_module
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Question, Reply
from tests.test_one_task_planning import NOW, FakeAI, FakeCalendar, make_config, make_session

FAILED = "Не вдалося, спробуйте ще раз."
NOT_ACTUAL = "Це питання вже не актуальне."
NOT_UNDERSTOOD = "Не зрозуміла, до якої справи це. Скажіть з іменем чи назвою."
CANNOT = "Поки що я вмію записати одну задачу в календар."
DEADLINE = NOW + timedelta(seconds=10)


def placed(name: str) -> str:
    return f"Поклала в «{name}»."


def ask(name: str) -> str:
    return f"Створити справу «{name}»?"


def plain(text: str) -> str:
    """The text with its apostrophes made one character: the contract does not fix the typography."""
    return re.sub("[’ʼ`]", "'", text)


class ModelFailed(Exception):
    """What the fake raises when a call is told to fail."""


class Clock:
    def __init__(self, at: datetime = NOW) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def expire(self) -> None:
        self.at = DEADLINE + timedelta(seconds=1)


def listed_number(prompt: str, name: str) -> int | None:
    """The number standing in front of `name` in a numbered list of the prompt, or None."""
    found = re.search(rf"(\d+)\s*[.)\-—:]?\s*[«\"]?{re.escape(name)}", prompt)
    return int(found.group(1)) if found is not None else None


class CaseAI(FakeAI):
    """Answers `route` with `{"intent": self.intent}`, `classify_case` as told, `describe_case` with a new
    description; everything else as the F1 fake. `fail[task_type] = n` makes the next n calls of that type
    raise; `after[task_type]` runs after a call of that type has answered (to move a clock)."""

    def __init__(self) -> None:
        super().__init__()
        self.intent: str | None = None
        self.file_name: str | None = None
        self.file_number: int | None = None
        self.new_name: str | None = None
        self.default_name = "пані Шмідт"
        self.fail: dict[str, int] = {}
        self.after: dict[str, Callable[[], None]] = {}
        self.prompts: dict[str, list[str]] = {}
        self.descriptions: list[str] = []

    def file_to(self, name: str) -> None:
        """The Розкладач names the case `name` of the catalogue (by its number in the prompt)."""
        self.file_name, self.file_number, self.new_name = name, None, None

    def new_case(self, name: str) -> None:
        self.file_name, self.file_number, self.new_name = None, None, name

    def nowhere(self) -> None:
        self.file_name, self.file_number, self.new_name = None, None, None

    def number(self, number: int, new_name: str | None = None) -> None:
        self.file_name, self.file_number, self.new_name = None, number, new_name

    def count(self, task_type: str) -> int:
        return self.calls.count(task_type)

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.setdefault(task_type, []).append(prompt)
        if self.fail.get(task_type, 0) > 0:
            self.calls.append(task_type)
            self.fail[task_type] -= 1
            raise ModelFailed(task_type)
        answer = self._answer(task_type, prompt, schema)
        hook = self.after.pop(task_type, None)
        if hook is not None:
            hook()
        return answer

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "route":
            self.calls.append(task_type)
            return {"intent": self.intent} if self.intent is not None else {}
        if task_type == "classify_case":
            self.calls.append(task_type)
            number = self.file_number
            if self.file_name is not None:
                number = listed_number(prompt, self.file_name)
            return {"number": number, "new_name": self.new_name}
        if task_type == "describe_case":
            self.calls.append(task_type)
            description = f"опис справи {len(self.descriptions) + 1}"
            self.descriptions.append(description)
            return fill(schema, description)
        if task_type in ("parse_task", "parse_duration"):
            return super().generate_json(task_type, prompt, schema)
        self.calls.append(task_type)
        return fill(schema, self.default_name)


def fill(schema: dict[str, Any], value: str) -> dict[str, Any]:
    """Every string field of the schema gets `value`, every other field null."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return {"description": value}
    answer: dict[str, Any] = {}
    for name, spec in properties.items():
        kind = spec.get("type") if isinstance(spec, dict) else None
        is_string = kind == "string" or (isinstance(kind, list) and "string" in kind)
        answer[name] = value if is_string else None
    return answer


@dataclass
class Notes:
    ai: CaseAI = field(default_factory=CaseAI)
    store: InMemoryStore = field(default_factory=InMemoryStore)
    config: Config = field(default_factory=make_config)
    session: Session = field(default_factory=make_session)
    clock: Clock = field(default_factory=Clock)
    calendar: FakeCalendar = field(default_factory=FakeCalendar)

    def other(self, account_id: str = "acc-2") -> "Notes":
        """A second account over the same store and the same model."""
        return Notes(
            ai=self.ai,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
        )

    def add(self, text: str, message_id: str, now: datetime = NOW) -> Reply:
        return case_module.add_note(
            self.session,
            text,
            message_id,
            ai=cast(AI, self.ai),
            store=self.store,
            now=now,
            config=self.config,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def yes(self, material_id: str, now: datetime = NOW) -> Reply:
        return case_module.confirm_case(
            self.session,
            material_id,
            ai=cast(AI, self.ai),
            store=self.store,
            now=now,
            config=self.config,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def try_add(self, text: str, message_id: str, now: datetime = NOW) -> Reply | None:
        """`add_note` that may fail: None when it raised."""
        try:
            return self.add(text, message_id, now)
        except Exception:
            return None

    def try_yes(self, material_id: str, now: datetime = NOW) -> Reply | None:
        try:
            return self.yes(material_id, now)
        except Exception:
            return None

    def message(
        self, text: str, message_id: str, reply_to: Question | None = None, now: datetime = NOW
    ) -> Reply:
        # The skeleton's signature predates the slice; the contract names these three keywords.
        handle: Callable[..., Reply] = assistant.handle_message
        return handle(
            self.session,
            text,
            reply_to,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
            message_id=message_id,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def materials(self) -> list[case_module.Material]:
        return case_module.materials_catalogue(self.session, self.store)

    def material(self, material_id: str) -> case_module.Material:
        found = [m for m in self.materials() if m.material_id == material_id]
        assert len(found) == 1, (material_id, found)
        return found[0]

    def cases(self) -> list[case_module.Case]:
        return case_module.catalogue(self.session, self.store)

    def seed(self, name: str, message_id: str) -> case_module.Case:
        """A case made the lawful way: a note the Розкладач names a new case for, then «так».

        On an empty catalogue the contract does not say where the name of the new case comes from (question
        Q1 of this slice): every model call there answers `name`, the note's text is `name`, and the case is
        returned whatever its name — the tests read the first case's name from what is returned."""
        empty = not self.cases()
        self.ai.new_case(name)
        self.ai.default_name = name
        self.add(name if empty else f"перша нотатка про {name}", message_id)
        self.yes(message_id)
        if empty:
            made = self.cases()
        else:
            made = [c for c in self.cases() if c.name == name]
        assert len(made) == 1, made
        return made[0]


def failed(reply: Reply | None) -> bool:
    """A failure as the contract allows it at the level of `cases`: raised, or the failure reply."""
    return reply is None or reply.text == FAILED
