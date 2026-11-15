"""Test helpers of the slice add-simply: a model fake that also answers `parse_when`, and a world with
`planning.try_answer_when`.

Written by the slice tester from the sealed contract `.engine/slices/add-simply.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1). Every time is written by hand in UTC.
The fake answers the when parse for any task type that names `when` (the contract names it `parse_when`) and
records the task type, the prompt and the schema of every such call.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.google_tasks_world import TasksCalendar
from tests.stuck_question_world import Stuck, StuckAI
from tests.test_one_task_planning import BERLIN, NOW, instant
from tests.time_limits_world import RecordingStore

ASK_WHAT_TO_ADD = "Яку задачу додати?"
NOT_ACTUAL = "Це питання вже не актуальне."
NAMED_OUTSIDE = "Цей час уже минув або він далі ніж за тиждень."
BANNED_KINDS = frozenset({"priorities", "duration", "limits"})
TUESDAY = "2026-11-10"
WEDNESDAY = "2026-11-11"


def ask_when(title: str) -> str:
    """The contract's question when no day is known."""
    return f"Коли «{title}»? Скажіть день і годину."


def ask_hour(title: str) -> str:
    """The contract's question when the day is known."""
    return f"О котрій годині «{title}»?"


def when(*, is_answer: bool = True, day: str | None = None, start_local: str | None = None) -> dict[str, Any]:
    """One answer of `parse_when` as the model gives it."""
    return {"is_answer": is_answer, "day": day, "start_local": start_local}


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


class WhenAI(StuckAI):
    """`StuckAI` that answers the when parse with `self.when` (not an answer when unset)."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.when: dict[str, Any] = when(is_answer=False)
        self.when_types: list[str] = []
        self.when_prompts: list[str] = []
        self.when_schemas: list[dict[str, Any]] = []

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if "when" in task_type:
            self.calls.append(task_type)
            self.when_types.append(task_type)
            self.when_prompts.append(prompt)
            self.when_schemas.append(schema)
            return dict(self.when)
        return super().generate_json(task_type, prompt, schema)


@dataclass
class AddSimply(Stuck):
    ai: WhenAI = field(default_factory=WhenAI)
    calendar: TasksCalendar = field(default_factory=TasksCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = True
    ask_priorities: bool = True
    use_tasks: bool = False

    def try_when(self, plan_id: str, text: str = "відповідь", now: datetime = NOW) -> Reply | None:
        return planning.try_answer_when(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def answer_when(self, plan_id: str, answer: dict[str, Any], text: str = "відповідь") -> Reply | None:
        """The model reads the answer as `answer`; then `try_answer_when`."""
        self.ai.when = dict(answer)
        return self.try_when(plan_id, text)

    def plan_id(self) -> str:
        current = self.draft()
        assert current is not None, "expected a draft"
        return str(current["plan_id"])


def add_simply(*, ask_limits: bool = True, ask_priorities: bool = True) -> AddSimply:
    return AddSimply(
        WhenAI(), TasksCalendar(honour_409=True), RecordingStore(), ask_limits, ask_priorities, False
    )


def when_question(reply: Reply | None, w: AddSimply) -> Question:
    """`Question("when", plan_id, None)` with no plan shown."""
    assert reply is not None, "expected the when question, got None"
    assert reply.question == Question("when", w.plan_id(), None), reply
    assert reply.plan is None, reply
    return reply.question


def local(iso: str) -> datetime:
    return instant(iso).astimezone(BERLIN)
