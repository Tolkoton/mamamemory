"""Test helpers of the slice google-tasks: a Calendar-and-Tasks fake, a model fake that answers `timed`, and a
world with `use_tasks=True` and `ask_priorities=True`.

Written by the slice tester from the sealed contract `.engine/slices/google-tasks.md`, without the code.
The fake keeps the open tasks of Google Tasks, counts every read, creation and closing, and can fail a step:
lose the answer of an event it created (by the event's title), fail a closing before it closes, fail the n-th
creation of a task before it creates it.
"""

import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import requests

from mamamemory import planning
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from tests.priorities_world import PrioritiesAI, Prioritized
from tests.several_tasks_world import CrashCalendar
from tests.test_one_task_planning import NOW, make_config
from tests.time_limits_world import RecordingStore

BILLS = "оплатити світло"
PARCEL = "забрати посилку"
TO_TASKS = "Задачі без часу — у Tasks."
CHOOSE_TIMED = "Назвіть і ті, що поставити на час."
PLAN_WRITTEN = "План записано."


class TasksCalendar(CrashCalendar):
    """Stands in for `GoogleWork` with Calendar and Tasks.

    `open_tasks` is what `list_open_tasks` returns; `complete_task` takes the task out of it (as Google does
    with `showCompleted=false`). `log` holds every successful write in the order made: `("event", title)`,
    `("close", task_id)`, `("task", title)`.
    """

    def __init__(self, *open_tasks: TaskItem, honour_409: bool = True) -> None:
        super().__init__(honour_409=honour_409)
        self.open_tasks: list[TaskItem] = list(open_tasks)
        self.list_calls = 0
        self.inserted: list[str] = []
        self.completed: list[str] = []
        self.complete_calls: list[str] = []
        self.log: list[tuple[str, str]] = []
        self.crash_title: str | None = None
        """The event of this title is created and its answer lost (once)."""
        self.fail_complete = False
        """The next `complete_task` fails before it closes anything (once)."""
        self.fail_insert_task_on: int | None = None
        """The n-th call of `insert_task` fails before it creates anything (once)."""
        self.insert_task_calls = 0
        self.on_complete: Callable[[str], None] | None = None
        """Called inside `complete_task` before anything is closed."""
        self.list_delegate: Callable[[], list[TaskItem]] | None = None

    def list_open_tasks(self) -> list[TaskItem]:
        self.list_calls += 1
        if self.list_delegate is not None:
            return self.list_delegate()
        return list(self.open_tasks)

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        repeated = self.honour_409 and any(e.id == event_id for e in self.events)
        if not repeated and self.crash_title is not None and title == self.crash_title:
            self.crash_title = None
            self.fail_after_create = True
        if not repeated:
            self.log.append(("event", title))
        return super().insert_event(event_id, title, start, end)

    def insert_task(self, title: str) -> str:
        self.insert_task_calls += 1
        if self.fail_insert_task_on is not None and self.insert_task_calls == self.fail_insert_task_on:
            self.fail_insert_task_on = None
            raise requests.exceptions.HTTPError("fake: Tasks answered 503")
        self.inserted.append(title)
        self.log.append(("task", title))
        return f"new-{len(self.inserted)}"

    def complete_task(self, task_id: str) -> None:
        self.complete_calls.append(task_id)
        if self.on_complete is not None:
            self.on_complete(task_id)
        if self.fail_complete:
            self.fail_complete = False
            raise requests.exceptions.ReadTimeout("fake: Tasks did not answer")
        self.completed.append(task_id)
        self.log.append(("close", task_id))
        self.open_tasks = [t for t in self.open_tasks if t.id != task_id]

    def free_all(self) -> None:
        """Take every foreign busy event out of the calendar."""
        self.events = [e for e in self.events if not e.id.startswith("otherbusy")]

    def event_titles(self) -> list[str]:
        return sorted(e.title for e in self.created)


class TimedAI(PrioritiesAI):
    """`PrioritiesAI` whose priorities answer may carry `timed`."""

    def choose(self, *, order: tuple[int, ...] = (), timed: tuple[int, ...] = (), same: bool = False) -> None:
        self.priorities = {"same": same, "order": list(order), "timed": list(timed)}


@dataclass
class WithTasks(Prioritized):
    ai: TimedAI = field(default_factory=TimedAI)
    calendar: TasksCalendar = field(default_factory=TasksCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = False
    ask_priorities: bool = True
    use_tasks: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        self.config = dataclasses.replace(
            make_config(),
            ask_limits=self.ask_limits,
            ask_priorities=self.ask_priorities,
            use_tasks=self.use_tasks,
        )

    @property
    def tc(self) -> TasksCalendar:
        return self.calendar

    def pick(
        self,
        plan_id: str,
        *,
        order: tuple[int, ...] = (),
        timed: tuple[int, ...] = (),
        same: bool = False,
        now: datetime = NOW,
    ) -> Any:
        self.ai.choose(order=order, timed=timed, same=same)
        return self.answer_priorities(plan_id, "відповідь про важливість", now=now)

    def find(self, title: str) -> dict[str, Any]:
        for t in self.tasks():
            if t.get("title") == title:
                return t
        raise AssertionError(f"no task {title!r} in the draft: {self.tasks()!r}")

    def opened(self, now: datetime = NOW) -> planning.OpenQuestion | None:
        def calendar() -> GoogleWork:
            return cast(GoogleWork, self.calendar)

        return planning.open_question(
            self.session, calendar=calendar, store=self.store, now=now, config=self.config
        )


def with_tasks(
    *speech: dict[str, Any],
    open_tasks: tuple[TaskItem, ...] = (),
    use_tasks: bool = True,
    ask_priorities: bool = True,
    honour_409: bool = True,
) -> WithTasks:
    return WithTasks(
        TimedAI(*speech),
        TasksCalendar(*open_tasks, honour_409=honour_409),
        RecordingStore(),
        False,
        ask_priorities,
        use_tasks,
    )


def number_of(text: str, title: str) -> int:
    """The number the priorities question gives `title` («3. оплатити світло» -> 3)."""
    found = re.search(rf"(\d+)\. {re.escape(title)}", text)
    assert found is not None, f"{title!r} is not numbered in {text!r}"
    return int(found.group(1))
