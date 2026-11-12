"""Test helpers of the slice voice-edits: a model fake that also answers the route and the edit parse, and a
world with `planning.edit_plan`.

Written by the slice tester from the sealed contract `.engine/slices/voice-edits.md`, without the code.
The contract gives the model a numbered list of the unwritten tasks and lets the model turn the task's name
into its number; the fake does the same: it reads the number standing in front of the title in the prompt it
is given (`1. подзвонити нотаріусу`, `1) …`), so the tests do not fix the order of that list. A title the
prompt does not list gets `number: null`. Every prompt of the edit parse is recorded.
"""

import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from mamamemory.replies import Reply
from tests.google_tasks_world import TasksCalendar, TimedAI, WithTasks
from tests.test_one_task_planning import NOW, make_config
from tests.time_limits_world import RecordingStore

NOT_UNDERSTOOD_EDIT = "Не зрозуміла правку, скажіть ще раз."
PLAN_EMPTY = "План порожній — нічого записувати."


class EditAI(TimedAI):
    """`TimedAI` that answers `route` with `{"intent": self.intent}` and the edit parse with `self.edit`.

    `self.edit_title` is the task the edit names: its number is read from the prompt. `self.edit_number`,
    when set, is given as it is (a number outside the list). `self.during_edit` runs inside the edit parse,
    before it answers (to run a concurrent request)."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.intent: str | None = None
        self.edit: dict[str, Any] = {
            "kind": "none",
            "day": None,
            "start_local": None,
            "not_before_local": None,
        }
        self.edit_title: str | None = None
        self.edit_number: int | None = None
        self.edit_prompts: list[str] = []
        self.route_prompts: list[str] = []
        self.during_edit: Callable[[], None] | None = None

    def wants(
        self,
        kind: str,
        title: str | None = None,
        *,
        number: int | None = None,
        day: str | None = None,
        start_local: str | None = None,
        not_before_local: str | None = None,
    ) -> None:
        self.edit_title = title
        self.edit_number = number
        self.edit = {
            "kind": kind,
            "day": day,
            "start_local": start_local,
            "not_before_local": not_before_local,
        }

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "route":
            self.calls.append(task_type)
            self.route_prompts.append(prompt)
            return {"intent": self.intent} if self.intent is not None else {}
        if "edit" in task_type:
            self.calls.append(task_type)
            self.edit_prompts.append(prompt)
            if self.during_edit is not None:
                hook, self.during_edit = self.during_edit, None
                hook()
            return dict(self.edit, number=self._number(prompt))
        return super().generate_json(task_type, prompt, schema)

    def _number(self, prompt: str) -> int | None:
        if self.edit_number is not None:
            return self.edit_number
        if self.edit_title is None:
            return None
        return listed_number(prompt, self.edit_title)


def listed_number(prompt: str, title: str) -> int | None:
    """The number standing in front of `title` in a numbered list of the prompt, or None."""
    found = re.search(rf"(\d+)\s*[.)\-—:]?\s*[«\"]?{re.escape(title)}", prompt)
    return int(found.group(1)) if found is not None else None


@dataclass
class Editing(WithTasks):
    ai: EditAI = field(default_factory=EditAI)
    calendar: TasksCalendar = field(default_factory=TasksCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = False
    ask_priorities: bool = False
    use_tasks: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        self.config = dataclasses.replace(
            make_config(),
            ask_limits=self.ask_limits,
            ask_priorities=self.ask_priorities,
            use_tasks=self.use_tasks,
        )

    def edit_plan(self, plan_id: str, text: str = "правка", now: datetime = NOW) -> Reply:
        return planning.edit_plan(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def edit(
        self,
        plan_id: str,
        kind: str,
        title: str | None = None,
        *,
        number: int | None = None,
        day: str | None = None,
        start_local: str | None = None,
        not_before_local: str | None = None,
        now: datetime = NOW,
    ) -> Reply:
        """The model reads the edit as given; then `edit_plan`."""
        self.ai.wants(
            kind, title, number=number, day=day, start_local=start_local, not_before_local=not_before_local
        )
        return self.edit_plan(plan_id, "правка", now=now)

    def writes(self) -> tuple[int, int, int, int]:
        """Every write to Google: event creations tried, tasks inserted (tried), closings tried."""
        return (
            len(self.tc.insert_calls),
            len(self.tc.created),
            self.tc.insert_task_calls,
            len(self.tc.complete_calls),
        )


def editing(
    *speech: dict[str, Any],
    open_tasks: tuple[TaskItem, ...] = (),
    use_tasks: bool = False,
    ask_limits: bool = False,
    honour_409: bool = True,
) -> Editing:
    return Editing(
        EditAI(*speech),
        TasksCalendar(*open_tasks, honour_409=honour_409),
        RecordingStore(),
        ask_limits,
        False,
        use_tasks,
    )
