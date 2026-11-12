"""Test helpers of the slice add-or-plan: a world whose `start` takes `week`, with Tasks, priorities,
limits and the route model (the voice-edits fake answers `route` with `intent`).

Written by the slice tester from the sealed contract `.engine/slices/add-or-plan.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1). Every time is written by hand in UTC.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from mamamemory.replies import Reply
from tests.google_tasks_world import BILLS, PARCEL, TasksCalendar
from tests.test_one_task_planning import NOW
from tests.time_limits_world import RecordingStore
from tests.voice_edits_world import EditAI, Editing

NO_TASKS_THIS_WEEK = "Задач на тиждень немає — скажіть, що треба зробити."
TK_BILLS = TaskItem("tk-1", BILLS)
TK_PARCEL = TaskItem("tk-2", PARCEL)


@dataclass
class AddOrPlan(Editing):
    ai: EditAI = field(default_factory=EditAI)
    calendar: TasksCalendar = field(default_factory=TasksCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = False
    ask_priorities: bool = True
    use_tasks: bool = True

    def start_in(self, text: str, *, week: bool, now: datetime = NOW) -> Reply:
        """`planning.start` with the slice's new `week`."""
        return planning.start(
            self.session,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
            week=week,
        )

    def add(self, *spoken: dict[str, Any], text: str = "додай задачу", now: datetime = NOW) -> Reply:
        """The model parses `spoken`; then `start(week=False)`."""
        self.ai.says(*spoken)
        return self.start_in(text, week=False, now=now)

    def plan_week(self, *spoken: dict[str, Any], text: str = "сплануй тиждень", now: datetime = NOW) -> Reply:
        """The model parses `spoken`; then `start(week=True)`."""
        self.ai.says(*spoken)
        return self.start_in(text, week=True, now=now)

    def mode(self) -> Any:
        current = self.draft()
        assert current is not None, "expected a draft"
        return current.get("mode", "week")

    def titles(self) -> list[str]:
        return [str(t["title"]) for t in self.tasks()]


def add_or_plan(
    *open_tasks: TaskItem,
    ask_limits: bool = False,
    ask_priorities: bool = True,
    use_tasks: bool = True,
) -> AddOrPlan:
    return AddOrPlan(
        EditAI(),
        TasksCalendar(*open_tasks, honour_409=True),
        RecordingStore(),
        ask_limits,
        ask_priorities,
        use_tasks,
    )


def no_priorities(reply: Reply) -> None:
    assert "Що з цього найважливіше?" not in reply.text, reply.text
    assert reply.question is None or reply.question.kind != "priorities", reply
