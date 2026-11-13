"""Test helpers of the slice show-schedule: a calendar fake that answers `list_agenda` like Google Calendar
(overlap with the window) and logs every call, a store that logs every write, a model fake whose route answers
`schedule`, and readers of the reply's lines.

Written by the slice tester from the sealed contract `.engine/slices/show-schedule.md`, without the code.
Every instant is written by hand in UTC; the fake only decides which events overlap the window it is given.
November 2026: Monday 9, Sunday 15, Monday 16, Sunday 22, Monday 30; Europe/Berlin is UTC+1 in November.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from mamamemory import assistant
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import AgendaItem, Event, GoogleWork, TaskItem
from mamamemory.integrations.store import Decide, InMemoryStore
from mamamemory.planning import schedule
from mamamemory.replies import Question, Reply
from tests.test_one_task_planning import make_config, make_session

WRITES = ("insert_event", "insert_task", "complete_task")


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@dataclass(frozen=True)
class CalEvent:
    """One event of the fake calendar: its overlap interval in UTC and what `list_agenda` returns for it."""

    title: str
    begin: datetime
    end: datetime
    day: date
    all_day: bool = False


def timed(title: str, begin: datetime, end: datetime, day: date) -> CalEvent:
    return CalEvent(title, begin, end, day, False)


def all_day(title: str, begin: datetime, end: datetime, day: date) -> CalEvent:
    """`begin` / `end` are the local midnights of the first day and of the day after the last, in UTC."""
    return CalEvent(title, begin, end, day, True)


class AgendaCalendar:
    """Stands in for `GoogleWork`: `list_agenda` returns the events that overlap the window (as Calendar does
    with `timeMin`/`timeMax`), in the order they were given. Every call is logged by name."""

    def __init__(self, tz: str, *events: CalEvent) -> None:
        self.tz = tz
        self.events = list(events)
        self.log: list[str] = []
        self.windows: list[tuple[datetime, datetime]] = []

    def timezone(self) -> str:
        self.log.append("timezone")
        return self.tz

    def list_agenda(self, time_min: datetime, time_max: datetime) -> list[AgendaItem]:
        self.log.append("list_agenda")
        self.windows.append((time_min, time_max))
        return [
            AgendaItem(e.title, None if e.all_day else e.begin, e.day, e.all_day)
            for e in self.events
            if e.end > time_min and e.begin < time_max
        ]

    def list_events(self, time_min: datetime, time_max: datetime) -> list[Event]:
        self.log.append("list_events")
        return []

    def get_event(self, event_id: str) -> Event | None:
        self.log.append("get_event")
        return None

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        self.log.append("insert_event")
        return event_id

    def list_open_tasks(self) -> list[TaskItem]:
        self.log.append("list_open_tasks")
        return [TaskItem("tk-1", "оплатити світло"), TaskItem("tk-2", "забрати посилку")]

    def insert_task(self, title: str) -> str:
        self.log.append("insert_task")
        return "new-1"

    def complete_task(self, task_id: str) -> None:
        self.log.append("complete_task")

    def writes(self) -> list[str]:
        return [name for name in self.log if name in WRITES]

    def window(self) -> tuple[datetime, datetime]:
        assert len(self.windows) == 1, f"expected one list_agenda call, got {self.windows!r}"
        return self.windows[0]


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


class ScheduleAI:
    """The route answers `{"intent": "schedule"}`; every prompt is recorded by task type."""

    def __init__(self) -> None:
        self.prompts: dict[str, list[str]] = {}

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.setdefault(task_type, []).append(prompt)
        if task_type == "route":
            return {"intent": "schedule"}
        return {}


def show(text: str, calendar: AgendaCalendar, now: datetime) -> Reply:
    """`schedule.show` with `use_tasks` off (the default of `make_config`): the reply holds the calendar only
    (plans-not-questions: open tasks are read and shown only when `config.use_tasks`)."""
    return schedule.show(
        make_session(), text, calendar=cast(GoogleWork, calendar), now=now, config=make_config()
    )


def message(
    text: str,
    calendar: AgendaCalendar,
    now: datetime,
    *,
    reply_to: Question | None = None,
    ai: ScheduleAI | None = None,
    store: WriteLogStore | None = None,
    config: Config | None = None,
) -> Reply:
    """`assistant.handle_message` with a route that answers `schedule`."""
    return assistant.handle_message(
        make_session(),
        text,
        reply_to,
        ai=cast(AI, ai or ScheduleAI()),
        calendar=cast(GoogleWork, calendar),
        store=store or WriteLogStore(),
        config=config or make_config(),
        now=now,
    )


def plain(text: str) -> str:
    """Apostrophes made one character, whitespace single spaces: the contract fixes the words."""
    return " ".join(re.sub("[’ʼ`]", "'", text).split())


def lines(reply: Reply) -> list[str]:
    """The reply's non-empty lines, each made `plain`."""
    return [plain(line) for line in reply.text.splitlines() if line.strip()]


def is_bullet(line: str) -> bool:
    return line.startswith("•")


def sections(reply: Reply) -> list[tuple[str, list[str]]]:
    """Day lines with the bullets under them, after the header line; a day line with no bullet is dropped
    (whether empty days are listed is question Q3, tested in the disputed file only)."""
    found: list[tuple[str, list[str]]] = []
    for line in lines(reply)[1:]:
        if is_bullet(line):
            assert found, f"a bullet before any day line: {reply.text!r}"
            found[-1][1].append(line)
        else:
            found.append((line, []))
    return [(day, bullets) for day, bullets in found if bullets]


def bullets(reply: Reply) -> list[str]:
    return [line for line in lines(reply) if is_bullet(line)]


def count_title(reply: Reply, title: str) -> int:
    """How many bullet lines of the reply end with this title."""
    return sum(1 for line in bullets(reply) if line.endswith(" " + title))
