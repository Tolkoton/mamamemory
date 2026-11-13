"""Test helpers of the slice work-recall: a model fake that answers `answer_work` as told and records its
prompt and schema, a calendar that logs `timezone` or raises from it, and a world around
`cases.worklog.recent`, `cases.worklog.answer` and `assistant.handle_message` over the working-on world.

Written by the slice tester from the sealed contract `.engine/slices/work-recall.md`, without the code.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Europe/Berlin, UTC+1 in November). Every expected text
and time is written by hand.
"""

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.cases import worklog
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.clarify_world import ClarifyCaseAI
from tests.working_on_world import SpyCalendar, Work

WORK = "work"
ANSWER_WORK = "answer_work"
NOTHING = "Поки нічого не записано про це."
NOW = datetime(2026, 11, 12, 9, 7, 0, tzinfo=UTC)


class CalendarDown(Exception):
    """What the broken calendar raises from `timezone`."""


class RecallAI(ClarifyCaseAI):
    """The clarify fake; `answer_work` is answered with `work_answer` (a copy), its schema is recorded."""

    def __init__(self) -> None:
        super().__init__()
        self.work_answer: dict[str, Any] = {
            "found": True,
            "answer": "Учора о 12:00 ви працювали над договором.",
        }
        self.schemas: dict[str, list[dict[str, Any]]] = {}

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.schemas.setdefault(task_type, []).append(copy.deepcopy(schema))
        if task_type == ANSWER_WORK:
            self.calls.append(task_type)
            return copy.deepcopy(self.work_answer)
        return super()._answer(task_type, prompt, schema)

    def work_prompts(self) -> list[str]:
        return self.prompts.get(ANSWER_WORK, [])

    def work_prompt(self) -> str:
        prompts = self.work_prompts()
        assert len(prompts) == 1, f"expected one answer_work call, got {len(prompts)}"
        return prompts[0]


class ZoneCalendar(SpyCalendar):
    """`SpyCalendar` in a given zone; `down` makes `timezone` raise `CalendarDown`."""

    def __init__(self, tz: str = "Europe/Berlin", down: bool = False) -> None:
        super().__init__()
        self.tz = tz
        self.down = down

    def timezone(self) -> str:
        self.log.append("timezone")
        if self.down:
            raise CalendarDown("timezone")
        return self.tz


@dataclass
class Recall(Work):
    ai: RecallAI = field(default_factory=RecallAI)
    calendar: ZoneCalendar = field(default_factory=ZoneCalendar)

    def put(self, entry_id: str, text: str, at: str | None, account_id: str | None = None) -> None:
        """A journal document `work/{entry_id}` as S1 writes it; `at=None` leaves the field out."""
        data: dict[str, Any] = {"text": text}
        if at is not None:
            data["at"] = at
        self.store.set(account_id or self.session.account_id, f"{WORK}/{entry_id}", data)

    def recent(self, now: datetime = NOW) -> list[worklog.WorkEntry]:
        return worklog.recent(self.session, store=self.store, now=now)

    def answer(self, question: str, now: datetime = NOW) -> Reply:
        return worklog.answer(
            self.session,
            question,
            store=self.store,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            now=now,
        )

    def ask(self, text: str, message_id: str, reply_to: Question | None = None, now: datetime = NOW) -> Reply:
        """A message the route names `work_question`."""
        self.ai.plain_intent("work_question")
        return self.message_any(text, message_id, reply_to, now)

    def written_state(self) -> dict[str, Any]:
        """What the intent may not change: the journal, the cases and materials, the plan draft."""
        state = self.cases_state()
        state["work"] = copy.deepcopy(self.entries())
        state["draft"] = copy.deepcopy(self.store.get(self.session.account_id, planning.DRAFT_PATH))
        return state


def iso(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    """An instant in UTC in the form S1 stores it."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC).isoformat()


def token(number: int) -> str:
    """A text no other text of the tests contains: `задача-K007Z`."""
    return f"задача-K{number:03d}Z"
