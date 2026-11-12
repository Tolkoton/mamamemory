"""Test helpers of the slice case-questions: a world around `cases.decline_case`, `cases.leave_without_case`,
`cases.choose_case`, `cases.open_questions` and `assistant.open_questions`, with a plan draft over the same
account and store.

Written by the slice tester from the sealed contract `.engine/slices/case-questions.md`, without the code.
The model fake is the S1 one (`tests/note_to_case_world.py`); `nameless` makes `name_case` answer no name.
`BrokenStore` makes the listing of the materials raise, so the case source of the open questions fails while
the plan draft is still read. A plan is driven through the F1 `World` over the same store and session.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import assistant
from mamamemory import cases as case_module
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Question, Reply
from tests.note_to_case_world import DEADLINE, CaseAI, Clock, Notes
from tests.test_one_task_planning import NOW, FakeCalendar, World, make_config, make_session

WHICH = "У яку справу покласти?"
LEFT = "Гаразд, лишила без справи."


class MaterialsBroken(Exception):
    """What `BrokenStore` raises when the materials are listed while it is broken."""


class BrokenStore(InMemoryStore):
    """An in-memory store whose listing of the materials raises while `broken` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.broken = False

    def list(self, account_id: str, collection: str) -> list[tuple[str, dict[str, Any]]]:
        if self.broken and collection == case_module.MATERIALS:
            raise MaterialsBroken(collection)
        return super().list(account_id, collection)


class QuestionAI(CaseAI):
    """The S1 fake; `nameless` makes `name_case` answer `{"name": None}`."""

    def __init__(self) -> None:
        super().__init__()
        self.nameless = False

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "name_case" and self.nameless:
            self.calls.append(task_type)
            return {"name": None}
        return super()._answer(task_type, prompt, schema)


class Lazy:
    """The `calendar` argument of the open: returns the fake or raises what it is told to."""

    def __init__(self, calendar: FakeCalendar, raises: BaseException | None = None) -> None:
        self.calendar = calendar
        self.raises = raises

    def __call__(self) -> GoogleWork:
        if self.raises is not None:
            raise self.raises
        return cast(GoogleWork, self.calendar)


def case_q(material_id: str) -> Question:
    return Question("case", material_id, None)


@dataclass
class Asks(Notes):
    ai: QuestionAI = field(default_factory=QuestionAI)
    store: BrokenStore = field(default_factory=BrokenStore)
    config: Config = field(default_factory=make_config)
    session: Session = field(default_factory=make_session)
    clock: Clock = field(default_factory=Clock)
    calendar: FakeCalendar = field(default_factory=FakeCalendar)

    def other_account(self, account_id: str = "acc-2") -> "Asks":
        """A second account over the same store, model and calendar."""
        return Asks(
            ai=self.ai,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
            calendar=self.calendar,
        )

    @property
    def plan(self) -> World:
        """The F1 planning world over the same account, store, model and calendar."""
        return World(self.calendar, self.ai, self.store, self.config, self.session)

    def pending_note(self, material_id: str, name: str, now: datetime = NOW) -> Reply:
        """A note that ends `pending` with `name` proposed (on any catalogue: a new name)."""
        self.ai.new_case(name)
        self.ai.default_name = name
        reply = self.add(f"нотатка {material_id} про {name}", material_id, now)
        assert reply.question == case_q(material_id), reply
        return reply

    def decline(self, material_id: str) -> Reply:
        return case_module.decline_case(self.session, material_id, store=self.store)

    def leave(self, material_id: str) -> Reply:
        return case_module.leave_without_case(self.session, material_id, store=self.store)

    def choose(self, material_id: str, text: str, now: datetime = NOW) -> Reply:
        return case_module.choose_case(
            self.session,
            material_id,
            text,
            ai=cast(AI, self.ai),
            store=self.store,
            now=now,
            config=self.config,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def case_questions(self) -> list[case_module.CaseQuestion]:
        return case_module.open_questions(self.session, self.store)

    def question_ids(self) -> list[str]:
        """The material ids of the open case questions, sorted (a doubled id shows twice)."""
        ids = []
        for item in self.case_questions():
            assert item.reply.question is not None, item
            ids.append(item.reply.question.id)
        return sorted(ids)

    def open_all(
        self,
        now: datetime,
        raises: BaseException | None = None,
        *,
        calendar: Callable[[], GoogleWork] | None = None,
    ) -> assistant.OpenQuestions:
        lazy = calendar if calendar is not None else Lazy(self.calendar, raises)
        return assistant.open_questions(
            self.session, calendar=lazy, store=self.store, now=now, config=self.config
        )

    def doc(self, material_id: str) -> dict[str, Any] | None:
        return self.store.get(self.session.account_id, f"{case_module.MATERIALS}/{material_id}")


def question_replies(replies: list[Reply]) -> list[Reply]:
    return [r for r in replies if r.question is not None]
