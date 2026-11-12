"""Test helpers of the slice several-tasks: a model fake that answers with several tasks, a Calendar fake
that can lose the answer of the n-th created event, and a world with `planning`'s calls.

Written by the slice tester from `.engine/slices/several-tasks.md`, without the code. The model fake reads
the response schema the code passes: the list of `TaskDraft` goes under the schema's array property, so the
tests do not fix the name of that property (the contract does not name it).
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.planning import OpenQuestion
from mamamemory.replies import Reply
from tests.test_one_task_planning import NOW, FakeCalendar, make_config, make_session

NOTARY = "подзвонити нотаріусу"
SEEDS = "купити насіння"
DOCTOR = "до лікаря"
MEDICINE = "купити ліки"
SISTER = "зателефонувати сестрі"
GARDEN = "полити город"

ASK_DURATION = "Скільки часу це займе?"
WRITTEN = "Записала в календар."
TASKS_LATER = "Ці задачі запишу в Tasks пізніше."
NOT_UNDERSTOOD = "Не зрозуміла задачу, скажіть ще раз."
WRITING_NOW = "Записую, хвилинку."
PARTLY_WRITTEN = "Записано не повністю — ось решта:"


def ask_named(title: str) -> str:
    return f"Скільки часу займе «{title}»?"


def task(
    title: str,
    *,
    needs_time: bool = True,
    duration_min: int | None = 30,
    start_local: str | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    """One `TaskDraft{title, needs_time, start_local, day, duration_min}` as the model gives it."""
    return {
        "title": title,
        "needs_time": needs_time,
        "start_local": start_local,
        "day": day,
        "duration_min": duration_min,
    }


def _array_key(schema: dict[str, Any]) -> str | None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    for name, prop in properties.items():
        kind = prop.get("type") if isinstance(prop, dict) else None
        if kind == "array" or (isinstance(kind, list) and "array" in kind):
            return str(name)
    return None


class TasksAI:
    """Stands in for `AI`. A task parse (`parse_task…`) answers with `self.tasks`; `parse_duration` with
    the next of `self.durations` (30 when none is left); anything else with `{}`."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        self.tasks: list[dict[str, Any]] = list(tasks)
        self.durations: list[int] = []
        self.calls: list[str] = []

    def says(self, *tasks: dict[str, Any]) -> None:
        self.tasks = list(tasks)

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(task_type)
        if task_type == "parse_duration":
            return {"duration_min": self.durations.pop(0) if self.durations else 30}
        if task_type.startswith("parse_task"):
            drafts = [dict(t) for t in self.tasks]
            key = _array_key(schema)
            if key is None:
                return drafts[0] if drafts else {}
            return {key: drafts}
        return {}


class CrashCalendar(FakeCalendar):
    """The S3 fake; `crash_on = n` loses the answer of the n-th event really created (it stays created)."""

    def __init__(self, *, honour_409: bool = True) -> None:
        super().__init__(honour_409=honour_409)
        self.crash_on: int | None = None

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        repeated = self.honour_409 and any(e.id == event_id for e in self.events)
        if not repeated and self.crash_on is not None and len(self.created) + 1 == self.crash_on:
            self.crash_on = None
            self.fail_after_create = True
        return super().insert_event(event_id, title, start, end)

    def titles(self) -> Counter[str]:
        return Counter(e.title for e in self.created)


@dataclass
class Several:
    ai: TasksAI
    calendar: CrashCalendar = field(default_factory=CrashCalendar)
    store: InMemoryStore = field(default_factory=InMemoryStore)

    def __post_init__(self) -> None:
        self.config = make_config()
        self.session = make_session()

    def start(self, text: str = "кілька задач", now: datetime = NOW) -> Reply:
        return planning.start(
            self.session,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def answer(self, plan_id: str, text: str = "пів години", now: datetime = NOW) -> Reply:
        return planning.answer_duration(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def confirm(self, plan_id: str, fingerprint: str, now: datetime = NOW) -> Reply:
        return planning.confirm(
            self.session,
            plan_id,
            fingerprint,
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def open(self, now: datetime = NOW) -> OpenQuestion | None:

        def calendar() -> GoogleWork:
            return cast(GoogleWork, self.calendar)

        return planning.open_question(
            self.session, calendar=calendar, store=self.store, now=now, config=self.config
        )

    def draft(self) -> dict[str, Any] | None:
        return self.store.get(self.session.account_id, planning.DRAFT_PATH)

    def tasks(self) -> list[dict[str, Any]]:
        current = self.draft()
        assert current is not None, "expected a draft"
        tasks = current.get("tasks")
        assert isinstance(tasks, list), f"expected `tasks: [Task]`, got {current!r}"
        return cast(list[dict[str, Any]], tasks)

    def task_id(self, title: str) -> str:
        for t in self.tasks():
            if t.get("title") == title:
                return str(t["task_id"])
        raise AssertionError(f"no task {title!r} in the draft")


def several(*tasks: dict[str, Any], honour_409: bool = True) -> Several:
    return Several(TasksAI(*tasks), CrashCalendar(honour_409=honour_409))


def items(reply: Reply) -> dict[str, tuple[str, str]]:
    """The plan's timed items as title -> (start ISO, end ISO)."""
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    found = {str(i["title"]): (str(i["start"]), str(i["end"])) for i in reply.plan.items}
    assert len(found) == len(reply.plan.items), f"an item shown twice: {reply.plan.items!r}"
    return found
