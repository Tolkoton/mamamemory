"""Test helpers of the slice tasks-list: a Calendar-and-Tasks fake whose `list_open_tasks` returns the tasks
it was given (or raises the error it was given) and logs every call, a model fake whose route answers a chosen
intent, and the calls of `schedule.tasks` and `assistant.handle_message` with `use_tasks` on or off.

Written by the slice tester from the sealed contract `.engine/slices/tasks-list.md`, without the code.
"""

from dataclasses import replace
from datetime import datetime
from typing import Any, cast

from mamamemory import assistant
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from mamamemory.planning import schedule
from mamamemory.replies import Reply
from tests.show_schedule_world import AgendaCalendar, WriteLogStore, lines, plain, utc
from tests.test_one_task_planning import make_config, make_session

__all__ = ["ListCalendar", "RouteAI", "WriteLogStore", "lines", "plain", "listed", "message", "config", "NOW"]

NOW = utc(2026, 11, 14, 11, 0)


class ListCalendar(AgendaCalendar):
    """Stands in for `GoogleWork`: `list_open_tasks` returns `tasks` in the order given, or raises `error`."""

    def __init__(self, *tasks: TaskItem, error: BaseException | None = None) -> None:
        super().__init__("Europe/Berlin")
        self.tasks = list(tasks)
        self.error = error

    def list_open_tasks(self) -> list[TaskItem]:
        self.log.append("list_open_tasks")
        if self.error is not None:
            raise self.error
        return list(self.tasks)


class RouteAI:
    """The route answers `{"intent": <intent>}`; every prompt is recorded by task type."""

    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.prompts: dict[str, list[str]] = {}

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.setdefault(task_type, []).append(prompt)
        if task_type == "route":
            return {"intent": self.intent}
        return {}


def config(use_tasks: bool = True) -> Config:
    return replace(make_config(), use_tasks=use_tasks)


def listed(calendar: ListCalendar, *, use_tasks: bool = True) -> Reply:
    """`schedule.tasks` over the fake."""
    return schedule.tasks(calendar=cast(GoogleWork, calendar), config=config(use_tasks))


def message(
    text: str, calendar: ListCalendar, ai: RouteAI, *, store: WriteLogStore | None = None, now: datetime = NOW
) -> Reply:
    """`assistant.handle_message` with `use_tasks` on and the given route."""
    return assistant.handle_message(
        make_session(),
        text,
        None,
        ai=cast(AI, ai),
        calendar=cast(GoogleWork, calendar),
        store=store or WriteLogStore(),
        config=config(True),
        now=now,
    )
