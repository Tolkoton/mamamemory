"""Test helpers of the slice time-limits: a model fake that also answers the limits parse, a store that
records every write of `planning/limits`, and a world with `ask_limits=True`.

Written by the slice tester from `.engine/slices/time-limits.md`, without the code. The model fake answers
the limits parse for any task type that names limits (the contract names the parse `parse_limits`), so the
tests do not depend on the exact task-type string.
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import assistant, planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Decide, InMemoryStore
from mamamemory.replies import Question, Reply
from tests.several_tasks_world import CrashCalendar, Several, TasksAI
from tests.test_one_task_planning import NOW, make_config

LIMITS_PATH = "planning/limits"
ASK_LIMITS_FIRST = "Коли ви взагалі можете робити задачі? Наприклад: будні з дев'ятої до шостої."
AGAIN_PREFIX = "Як минулого разу — "
NOT_ACTUAL = "Це питання вже не актуальне."
WEEKDAYS = [0, 1, 2, 3, 4]


def plain(text: str) -> str:
    """The text with its apostrophes made one character: the contract does not fix the typography."""
    return text.replace("ʼ", "'").replace("’", "'")


def parsed(
    *,
    same_as_last: bool = False,
    days: list[int] | None = None,
    start_local: str | None = None,
    end_local: str | None = None,
) -> dict[str, Any]:
    """One answer of `parse_limits` as the model gives it."""
    return {
        "same_as_last": same_as_last,
        "days": list(days) if days is not None else [],
        "start_local": start_local,
        "end_local": end_local,
    }


def limits_doc(days: list[int], start_local: str, end_local: str) -> dict[str, Any]:
    return {"days": list(days), "start_local": start_local, "end_local": end_local}


def normal(doc: dict[str, Any] | None) -> tuple[list[int], str, str] | None:
    """A `planning/limits` document as (sorted days, start, end); the order of `days` is not fixed."""
    if doc is None:
        return None
    days = doc.get("days")
    assert isinstance(days, list), f"`days` must be a list, got {doc!r}"
    return sorted(int(d) for d in days), str(doc.get("start_local")), str(doc.get("end_local"))


class LimitsAI(TasksAI):
    """`TasksAI` that answers the limits parse with `self.limits` (an unparsable answer when unset)."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.limits: dict[str, Any] = parsed()

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if "limit" in task_type:
            self.calls.append(task_type)
            return dict(self.limits)
        return super().generate_json(task_type, prompt, schema)


class RecordingStore(InMemoryStore):
    """`InMemoryStore` that records every write of `planning/limits` (by `set` or by `transact`)."""

    def __init__(self) -> None:
        super().__init__()
        self.limits_writes: list[dict[str, Any]] = []

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        if path == LIMITS_PATH:
            self.limits_writes.append(dict(data))
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        written = super().transact(account_id, path, decide)
        if path == LIMITS_PATH and written is not None:
            self.limits_writes.append(dict(written))
        return written


@dataclass
class Limited(Several):
    ai: LimitsAI = field(default_factory=LimitsAI)
    calendar: CrashCalendar = field(default_factory=CrashCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        self.config = dataclasses.replace(make_config(), ask_limits=self.ask_limits)

    def answer_limits(
        self, plan_id: str, text: str = "будні з дев'ятої до шостої", now: datetime = NOW
    ) -> Reply:
        return planning.answer_limits(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def message(self, text: str, reply_to: Question | None, now: datetime = NOW) -> Reply:
        return assistant.handle_message(
            self.session,
            text,
            reply_to,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
        )

    def saved(self) -> tuple[list[int], str, str] | None:
        return normal(self.store.get(self.session.account_id, LIMITS_PATH))

    def seed_limits(self, days: list[int], start_local: str, end_local: str) -> None:
        """Limits saved by an earlier planning (written straight into the store, not recorded as a write)."""
        InMemoryStore.set(
            self.store, self.session.account_id, LIMITS_PATH, limits_doc(days, start_local, end_local)
        )


def limited(*tasks: dict[str, Any], ask_limits: bool = True) -> Limited:
    return Limited(LimitsAI(*tasks), CrashCalendar(honour_409=True), RecordingStore(), ask_limits)


def limits_question(reply: Reply) -> Question:
    assert reply.question is not None, f"expected the limits question, got {reply!r}"
    assert reply.question.kind == "limits", f"expected the limits question, got {reply!r}"
    assert reply.plan is None, f"the limits question shows no plan yet, got {reply!r}"
    return reply.question
