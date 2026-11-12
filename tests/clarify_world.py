"""Test helpers of the slice clarify: model fakes whose route can answer `unsure` with `options` and whose
`choose_option` answers `{option: …}`; worlds around `handle_message` and `answer_clarify` of `assistant`.

Written by the slice tester from the sealed contract `.engine/slices/clarify.md`, without the code.
The `choose_option` fake answers every call whose response schema has the property `option` (the contract
fixes `{option: 1|2|null}`, not how the task is named in the code). Every prompt is recorded by its task type.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z).
"""

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from mamamemory import assistant, planning
from mamamemory import cases as case_module
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.case_questions_world import Asks, QuestionAI
from tests.google_tasks_world import TasksCalendar
from tests.note_to_case_world import DEADLINE
from tests.stuck_question_world import Stuck, StuckAI
from tests.test_one_task_planning import NOW
from tests.time_limits_world import LIMITS_PATH, RecordingStore

CLARIFY_PATH = "clarify/current"
NOT_ACTUAL = "Це питання вже не актуальне."

PHRASES = {
    "new_task": "поставити задачею в календар",
    "note": "записати нотаткою до справи",
    "plan_week": "спланувати тиждень",
    "edit": "змінити показаний план",
    "move": "перекласти матеріал в іншу справу",
    "case_name": "покласти в названу справу",
    "yes": "погодитись",
    "no": "відмовитись",
    "not_needed": "лишити без справи",
}


def asked_text(first: str, second: str) -> str:
    """«Не зовсім зрозуміла: <A> чи <B>?» for two intents."""
    return f"Не зовсім зрозуміла: {PHRASES[first]} чи {PHRASES[second]}?"


def has_option(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return isinstance(properties, dict) and "option" in properties


class ClarifyCaseAI(QuestionAI):
    """The case-questions fake; `route_answer`, when set, is the route's whole answer; `option` is what
    `choose_option` answers."""

    def __init__(self) -> None:
        super().__init__()
        self.route_answer: dict[str, Any] | None = None
        self.option: int | None = None

    def unsure(self, *options: Any) -> None:
        self.route_answer = {"intent": "unsure", "options": list(options)}

    def plain_intent(self, intent: str) -> None:
        self.route_answer = None
        self.intent = intent

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "route" and self.route_answer is not None:
            self.calls.append(task_type)
            return copy.deepcopy(self.route_answer)
        if has_option(schema):
            self.calls.append(task_type)
            self.prompts.setdefault("option", []).append(prompt)
            return {"option": self.option}
        return super()._answer(task_type, prompt, schema)


@dataclass
class Clarify(Asks):
    ai: ClarifyCaseAI = field(default_factory=ClarifyCaseAI)

    def say(self, text: str, message_id: str, reply_to: Question | None = None, now: datetime = NOW) -> Reply:
        return self.message(text, message_id, reply_to, now)

    def button(self, clarify_id: str, option: int, now: datetime = NOW) -> Reply:
        return assistant.answer_clarify(
            self.session,
            clarify_id,
            option,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
            deadline=DEADLINE,
            clock=self.clock,
        )

    def current(self) -> dict[str, Any] | None:
        return self.store.get(self.session.account_id, CLARIFY_PATH)

    def routes(self) -> int:
        return self.ai.calls.count("route")

    def everything_else(self) -> dict[str, Any]:
        """What a clarification may not change: the notes, the cases, the plan draft, the saved limits."""
        account = self.session.account_id
        return {
            "materials": copy.deepcopy(self.store.list(account, case_module.MATERIALS)),
            "cases": copy.deepcopy(self.cases()),
            "draft": copy.deepcopy(self.store.get(account, planning.DRAFT_PATH)),
            "limits": copy.deepcopy(self.store.get(account, LIMITS_PATH)),
        }


def clarified(reply: Reply) -> Question:
    assert reply.question is not None, f"expected the clarify question, got {reply!r}"
    assert reply.question.kind == "clarify", f"expected the clarify question, got {reply!r}"
    assert reply.question.fingerprint is None, reply
    return reply.question


class ClarifyStuckAI(StuckAI):
    """The stuck-question fake with the same `route_answer` and `option` as `ClarifyCaseAI`; every prompt is
    recorded by task type."""

    def __init__(self) -> None:
        super().__init__()
        self.route_answer: dict[str, Any] | None = None
        self.option: int | None = None
        self.prompts: dict[str, list[str]] = {}

    def unsure(self, *options: Any) -> None:
        self.route_answer = {"intent": "unsure", "options": list(options)}

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.setdefault(task_type, []).append(prompt)
        if task_type == "route" and self.route_answer is not None:
            self.calls.append(task_type)
            self.route_prompts.append(prompt)
            return copy.deepcopy(self.route_answer)
        if has_option(schema):
            self.calls.append(task_type)
            self.prompts.setdefault("option", []).append(prompt)
            return {"option": self.option}
        return super().generate_json(task_type, prompt, schema)


@dataclass
class StuckClarify(Stuck):
    ai: ClarifyStuckAI = field(default_factory=ClarifyStuckAI)

    def button(self, clarify_id: str, option: int, now: datetime = NOW) -> Reply:
        return assistant.answer_clarify(
            self.session,
            clarify_id,
            option,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
        )

    def current(self) -> dict[str, Any] | None:
        return self.store.get(self.session.account_id, CLARIFY_PATH)


def stuck_clarify() -> StuckClarify:
    return StuckClarify(
        ClarifyStuckAI(), TasksCalendar(honour_409=True), RecordingStore(), False, True, False
    )
