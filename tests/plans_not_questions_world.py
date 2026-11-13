"""Test helpers of the slice plans-not-questions: a model fake whose priorities and limits parse can carry
`is_answer` and records its prompts, a calendar that also answers `list_agenda`, a seeded draft.

Written by the slice tester from the sealed contract `.engine/slices/plans-not-questions.md`, no code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). Every time is written by hand in UTC.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.config import Config
from mamamemory.integrations.google_work import AgendaItem, GoogleWork, TaskItem
from mamamemory.integrations.store import Decide, InMemoryStore
from mamamemory.planning import schedule
from mamamemory.replies import Reply
from tests.google_tasks_world import TasksCalendar
from tests.stuck_question_world import Stuck, StuckAI
from tests.test_one_task_planning import NOW, make_config, make_session
from tests.time_limits_world import RecordingStore

BERLIN = "Europe/Berlin"
DOCTOR = "Лікар"
DOCTOR_LINE = "• 12:00 Лікар"
"""The doctor's event below starts 11:00Z = 12:00 in Berlin on Monday 9 November."""
TASKS_HEADER = "Задачі без часу:"
NOTHING_TODAY = "На сьогодні в календарі нічого немає."
IS_ANSWER_SENTENCE = (
    "чи мама взагалі відповідає на це питання; питання про плани, справи, роботу, нова задача — false"
)


def doctor_today() -> AgendaItem:
    return AgendaItem(DOCTOR, utc(2026, 11, 9, 11), date(2026, 11, 9), False)


class PromptAI(StuckAI):
    """`StuckAI` that records the prompt of every priorities and limits parse."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.parse_prompts: dict[str, list[str]] = {}

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if "priorit" in task_type or "limit" in task_type:
            self.parse_prompts.setdefault("priorities" if "priorit" in task_type else "limits", []).append(
                prompt
            )
        return super().generate_json(task_type, prompt, schema)


class AgendaTasksCalendar(TasksCalendar):
    """`TasksCalendar` that also answers `list_agenda` with `self.agenda` (whatever the window)."""

    def __init__(self, *open_tasks: TaskItem, agenda: tuple[AgendaItem, ...] = ()) -> None:
        super().__init__(*open_tasks, honour_409=True)
        self.agenda = list(agenda)
        self.agenda_calls = 0

    def list_agenda(self, time_min: datetime, time_max: datetime) -> list[AgendaItem]:
        self.agenda_calls += 1
        return list(self.agenda)


@dataclass
class Plans(Stuck):
    ai: PromptAI = field(default_factory=PromptAI)
    calendar: AgendaTasksCalendar = field(default_factory=AgendaTasksCalendar)
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

    def google_writes(self) -> tuple[int, int, int]:
        """Event creations tried, task insertions tried, closings tried."""
        return len(self.tc.insert_calls), self.tc.insert_task_calls, len(self.tc.complete_calls)


def plans(
    *open_tasks: TaskItem,
    agenda: tuple[AgendaItem, ...] = (),
    ask_limits: bool = False,
    ask_priorities: bool = True,
    use_tasks: bool = True,
) -> Plans:
    return Plans(
        PromptAI(),
        AgendaTasksCalendar(*open_tasks, agenda=agenda),
        RecordingStore(),
        ask_limits,
        ask_priorities,
        use_tasks,
    )


WRITES = ("insert_event", "insert_task", "complete_task")


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TasksAgenda:
    """Stands in for `GoogleWork` in `schedule.show`: `list_agenda` returns `agenda` (whatever the window),
    `list_open_tasks` returns `tasks` or raises `fail` when it is set. Every call is logged by name."""

    def __init__(
        self, *agenda: AgendaItem, tasks: tuple[TaskItem, ...] = (), fail: Exception | None = None
    ) -> None:
        self.agenda = list(agenda)
        self.tasks = list(tasks)
        self.fail = fail
        self.log: list[str] = []

    def timezone(self) -> str:
        self.log.append("timezone")
        return BERLIN

    def list_agenda(self, time_min: datetime, time_max: datetime) -> list[AgendaItem]:
        self.log.append("list_agenda")
        return list(self.agenda)

    def list_open_tasks(self) -> list[TaskItem]:
        self.log.append("list_open_tasks")
        if self.fail is not None:
            raise self.fail
        return list(self.tasks)

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        self.log.append("insert_event")
        return event_id

    def insert_task(self, title: str) -> str:
        self.log.append("insert_task")
        return "new-1"

    def complete_task(self, task_id: str) -> None:
        self.log.append("complete_task")

    def writes(self) -> list[str]:
        return [name for name in self.log if name in WRITES]


class WriteLogStore(InMemoryStore):
    """`InMemoryStore` that logs every write: `set`, a `transact` that writes, `delete`."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[str, str]] = []

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self.writes.append(("set", path))
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        written = super().transact(account_id, path, decide)
        if written is not None:
            self.writes.append(("transact", path))
        return written

    def delete(self, account_id: str, path: str) -> None:
        self.writes.append(("delete", path))
        super().delete(account_id, path)


def lines(reply: Reply) -> list[str]:
    """The reply's non-empty lines, apostrophes made one character, whitespace single spaces."""
    return [" ".join(re.sub("[’ʼ`]", "'", line).split()) for line in reply.text.splitlines() if line.strip()]


def tasks_config(use_tasks: bool = True) -> Config:
    return dataclasses.replace(make_config(), use_tasks=use_tasks)


def show_with(text: str, calendar: TasksAgenda, *, use_tasks: bool = True, now: datetime = NOW) -> Reply:
    """`schedule.show` with the slice's new `config`."""
    return schedule.show(
        make_session(), text, calendar=cast(GoogleWork, calendar), now=now, config=tasks_config(use_tasks)
    )


def seed_draft(store: InMemoryStore, *, state: str, mode: str | None) -> dict[str, Any]:
    """A plan draft of this state and mode (no `mode` field when `mode` is None), written straight in."""
    draft: dict[str, Any] = {
        "plan_id": "p-1",
        "state": state,
        "tasks": [
            {
                "task_id": "t1",
                "title": "подзвонити нотаріусу",
                "needs_time": True,
                "duration_min": 30,
                "start_local": None,
                "constraints": {"day": None},
                "order": 1,
                "source": "speech",
                "written": {"event_id": None, "tasks_id": None, "closed": False},
            }
        ],
    }
    if mode is not None:
        draft["mode"] = mode
    store.set(make_session().account_id, planning.DRAFT_PATH, draft)
    return draft
