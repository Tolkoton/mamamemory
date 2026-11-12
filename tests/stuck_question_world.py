"""Test helpers of the slice stuck-question: a model fake whose duration parse can answer anything (a
non-positive number, nothing), and a world with `try_answer_*`, `start(replace_asking=…)` and the route.

Written by the slice tester from the sealed contract `.engine/slices/stuck-question.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). The world is the add-or-plan world: the route model
answers `intent`, the priorities parse answers `priorities`, the limits parse answers `limits`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.add_or_plan_world import AddOrPlan
from tests.google_tasks_world import TasksCalendar
from tests.test_one_task_planning import NOW
from tests.time_limits_world import RecordingStore
from tests.voice_edits_world import EditAI

TEA = "чай"
# guide Seam «Незрозуміле»: the text that replaced «Поки що я вмію записати одну задачу в календар.».
CANNOT_TEXT = "Не зрозуміла. Скажіть «що ти вмієш?» — розкажу."


def ask_named(title: str) -> str:
    """The duration question of the contract: it names the task, for one task too."""
    return f"Скільки часу займе «{title}»?"


class StuckAI(EditAI):
    """`EditAI` whose duration parse answers the next of `self.raw_durations` as it stands (None, 0, -5…);
    when that list is empty it answers as `TasksAI` does."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.raw_durations: list[Any] = []

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "parse_duration" and self.raw_durations:
            self.calls.append(task_type)
            return {"duration_min": self.raw_durations.pop(0)}
        return super().generate_json(task_type, prompt, schema)


@dataclass
class Stuck(AddOrPlan):
    ai: StuckAI = field(default_factory=StuckAI)
    calendar: TasksCalendar = field(default_factory=TasksCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = False
    ask_priorities: bool = True
    use_tasks: bool = False

    def start_replacing(self, text: str, *, week: bool, now: datetime = NOW) -> Reply:
        return planning.start(
            self.session,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
            week=week,
            replace_asking=True,
        )

    def try_duration(self, plan_id: str, text: str = "відповідь", now: datetime = NOW) -> Reply | None:
        return planning.try_answer_duration(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def try_priorities(self, plan_id: str, text: str = "відповідь", now: datetime = NOW) -> Reply | None:
        return planning.try_answer_priorities(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def try_limits(self, plan_id: str, text: str = "відповідь", now: datetime = NOW) -> Reply | None:
        return planning.try_answer_limits(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def say(
        self,
        text: str,
        reply_to: Question | None,
        *,
        intent: str,
        spoken: tuple[dict[str, Any], ...] = (),
        now: datetime = NOW,
    ) -> Reply:
        """A message: the route model reads `intent`, a task parse reads `spoken`."""
        self.ai.intent = intent
        self.ai.says(*spoken)
        return self.message(text, reply_to, now=now)

    def forget_asked_at(self) -> None:
        """The draft as a revision before F3 S3 wrote it: no `asked_at`."""
        current = self.draft()
        assert current is not None, "expected a draft"
        current = dict(current)
        current.pop("asked_at", None)
        self.store.set(self.session.account_id, planning.DRAFT_PATH, current)

    def set_field(self, name: str, value: Any) -> None:
        current = self.draft()
        assert current is not None, "expected a draft"
        self.store.set(self.session.account_id, planning.DRAFT_PATH, dict(current, **{name: value}))


def stuck(*, ask_limits: bool = False, ask_priorities: bool = True, use_tasks: bool = False) -> Stuck:
    return Stuck(
        StuckAI(),
        TasksCalendar(honour_409=True),
        RecordingStore(),
        ask_limits,
        ask_priorities,
        use_tasks,
    )


def asked(reply: Reply, kind: str) -> Question:
    assert reply.question is not None, f"expected the {kind} question, got {reply!r}"
    assert reply.question.kind == kind, f"expected the {kind} question, got {reply!r}"
    return reply.question


def cannot(reply: Reply) -> None:
    """`other`: `CANNOT_TEXT` (guide «Незрозуміле»), not a question."""
    assert reply.text.startswith(CANNOT_TEXT), reply
    assert reply.question is None, reply
    assert reply.plan is None, reply
