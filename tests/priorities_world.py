"""Test helpers of the slice priorities: a model fake that also answers `parse_priorities`, and a world with
`ask_priorities=True` (and `ask_limits` as asked).

Written by the slice tester from `.engine/slices/priorities.md`, without the code. The model fake answers the
priorities parse for any task type that names priorities (the contract names the parse `parse_priorities`
and its answer `{same: bool, order: [int]}`), so the tests do not depend on the exact task-type string.
"""

import contextlib
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.several_tasks_world import CrashCalendar
from tests.test_one_task_planning import NOW, make_config
from tests.time_limits_world import Limited, LimitsAI, RecordingStore

ASK_PRIORITIES = "Що з цього найважливіше?"


def ranked(*numbers: int, same: bool = False) -> dict[str, Any]:
    """One answer of `parse_priorities` as the model gives it: numbers from the list, most important first."""
    return {"same": same, "order": list(numbers)}


class PrioritiesAI(LimitsAI):
    """`LimitsAI` that answers the priorities parse with `self.priorities` (nothing valid when unset)."""

    def __init__(self, *tasks: dict[str, Any]) -> None:
        super().__init__(*tasks)
        self.priorities: dict[str, Any] = ranked()

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if "priorit" in task_type:
            self.calls.append(task_type)
            return dict(self.priorities, order=list(self.priorities["order"]))
        return super().generate_json(task_type, prompt, schema)


@dataclass
class Prioritized(Limited):
    ai: PrioritiesAI = field(default_factory=PrioritiesAI)
    calendar: CrashCalendar = field(default_factory=CrashCalendar)
    store: RecordingStore = field(default_factory=RecordingStore)
    ask_limits: bool = False
    ask_priorities: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        self.config = dataclasses.replace(
            make_config(), ask_limits=self.ask_limits, ask_priorities=self.ask_priorities
        )

    def answer_priorities(self, plan_id: str, text: str = "друге", now: datetime = NOW) -> Reply:
        return planning.answer_priorities(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def rank(self, plan_id: str, *numbers: int, same: bool = False, now: datetime = NOW) -> Reply:
        """The model reads the answer as `numbers` (or `same`)."""
        self.ai.priorities = ranked(*numbers, same=same)
        return self.answer_priorities(plan_id, "відповідь про важливість", now=now)

    def orders(self) -> dict[str, Any]:
        """title -> `order` of every task of the draft."""
        return {str(t["title"]): t["order"] for t in self.tasks()}

    def open_titles(self) -> list[str]:
        """Titles of the unwritten tasks in the order the draft's `tasks` list holds them."""
        return [str(t["title"]) for t in self.tasks() if not t["written"]["event_id"]]

    def by_order(self) -> list[str]:
        """Titles of the unwritten tasks sorted by their `order`."""
        open_tasks = [t for t in self.tasks() if not t["written"]["event_id"]]
        return [str(t["title"]) for t in sorted(open_tasks, key=lambda t: t["order"])]


def prioritized(
    *tasks: dict[str, Any], ask_limits: bool = False, ask_priorities: bool = True, honour_409: bool = True
) -> Prioritized:
    return Prioritized(
        PrioritiesAI(*tasks),
        CrashCalendar(honour_409=honour_409),
        RecordingStore(),
        ask_limits,
        ask_priorities,
    )


def priorities_question(reply: Reply) -> Question:
    assert reply.question is not None, f"expected the priorities question, got {reply!r}"
    assert reply.question.kind == "priorities", f"expected the priorities question, got {reply!r}"
    assert reply.question.fingerprint is None, f"the priorities question has no fingerprint, got {reply!r}"
    assert reply.plan is None, f"the priorities question shows no plan yet, got {reply!r}"
    return reply.question


def listed(text: str, *titles: str) -> None:
    """The text asks «Що з цього найважливіше?» and numbers exactly these titles, from 1, in this order."""
    assert ASK_PRIORITIES in text, text
    positions = []
    for n, title in enumerate(titles, start=1):
        line = f"{n}. {title}"
        assert line in text, f"{line!r} is not in {text!r}"
        positions.append(text.index(line))
    assert positions == sorted(positions), f"the list is not in the order {titles!r}: {text!r}"
    assert f"{len(titles) + 1}. " not in text, f"more than {len(titles)} tasks listed: {text!r}"


def yes_ignoring_crash(w: Prioritized, plan_id: str, fingerprint: str, now: datetime = NOW) -> None:
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint, now=now)
