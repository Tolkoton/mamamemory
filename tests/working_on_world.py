"""Test helpers of the slice working-on: a calendar fake that logs every call (Calendar and Tasks), and a
world around `cases.worklog.add` and `assistant.handle_message` over the clarify world's model fake.

Written by the slice tester from the sealed contract `.engine/slices/working-on.md`, without the code.
`NOW` is Monday 9 November 2026, 09:07Z; every expected text and time is written by hand.
"""

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import assistant
from mamamemory import cases as case_module
from mamamemory.cases import worklog
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import Event, GoogleWork
from mamamemory.replies import Question, Reply
from tests.clarify_world import Clarify
from tests.note_to_case_world import DEADLINE
from tests.test_one_task_planning import NOW, FakeCalendar, make_session, shown

WORK = "work"
NOW_ISO = "2026-11-09T09:07:00+00:00"


class TasksCalled(Exception):
    """What the spy raises when a Tasks method is called: the fake keeps no tasks."""


class SpyCalendar(FakeCalendar):
    """`FakeCalendar` that logs the name of every call it gets, Calendar and Tasks alike."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[str] = []

    def timezone(self) -> str:
        self.log.append("timezone")
        return super().timezone()

    def list_events(self, time_min: datetime, time_max: datetime) -> list[Event]:
        self.log.append("list_events")
        return super().list_events(time_min, time_max)

    def get_event(self, event_id: str) -> Event | None:
        self.log.append("get_event")
        return super().get_event(event_id)

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        self.log.append("insert_event")
        return super().insert_event(event_id, title, start, end)

    def list_open_tasks(self) -> list[Any]:
        self.log.append("list_open_tasks")
        return []

    def insert_task(self, title: str) -> str:
        self.log.append("insert_task")
        raise TasksCalled(title)

    def complete_task(self, task_id: str) -> None:
        self.log.append("complete_task")
        raise TasksCalled(task_id)

    def writes(self) -> list[str]:
        return [name for name in self.log if name in ("insert_event", "insert_task", "complete_task")]


def recorded(text: str) -> str:
    """«Записала: <text>.»"""
    return f"Записала: {text}."


def plain(text: str) -> str:
    """Whitespace made single spaces, apostrophes and ellipses one form: the contract fixes the words."""
    text = re.sub("[’ʼ`]", "'", text).replace("...", "…")
    return " ".join(text.split())


@dataclass
class Work(Clarify):
    calendar: SpyCalendar = field(default_factory=SpyCalendar)

    def other_work(self, account_id: str = "acc-2") -> "Work":
        """A second account over the same store, model and calendar."""
        return Work(
            ai=self.ai,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
            calendar=self.calendar,
        )

    def log(self, text: str, entry_id: str, now: datetime = NOW) -> Reply:
        return worklog.add(self.session, text, entry_id, store=self.store, now=now)

    def working(
        self, text: str, message_id: str | None, reply_to: Question | None = None, now: datetime = NOW
    ) -> Reply:
        """A message the route names `working_on`."""
        self.ai.plain_intent("working_on")
        return self.message_any(text, message_id, reply_to, now)

    def message_any(
        self, text: str, message_id: str | None, reply_to: Question | None = None, now: datetime = NOW
    ) -> Reply:
        return assistant.handle_message(
            self.session,
            text,
            reply_to,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
            message_id=message_id,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def entries(self) -> list[tuple[str, dict[str, Any]]]:
        return self.store.list(self.session.account_id, WORK)

    def entry(self, entry_id: str) -> dict[str, Any] | None:
        return self.store.get(self.session.account_id, f"{WORK}/{entry_id}")

    def cases_state(self) -> dict[str, Any]:
        """What the intent may not touch: the materials and the cases of the account."""
        account = self.session.account_id
        return {
            "materials": copy.deepcopy(self.store.list(account, case_module.MATERIALS)),
            "cases": copy.deepcopy(self.store.list(account, case_module.CASES)),
        }

    def plan_question(self) -> Question:
        """A plan shown the lawful way (F1 `planning.start`); its question."""
        plan_id, fingerprint = shown(self.plan.start())
        return Question("plan", plan_id, fingerprint)
