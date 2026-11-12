"""Форми відповіді асистента (S3): `ReplyTo`, `Question`, `PlanView`, `Reply`.

Не робить: жодної логіки — лише значення, які `planning` і `assistant` повертають, а `http` віддає як JSON.
"""

from dataclasses import dataclass, field
from typing import Literal

QuestionKind = Literal["duration", "plan", "limits", "priorities", "case", "clarify"]


@dataclass(frozen=True)
class Question:
    kind: QuestionKind
    id: str
    fingerprint: str | None


ReplyTo = Question
"""`reply_to` повідомлення — те саме питання, на яке мама відповідає."""


@dataclass(frozen=True)
class PlanView:
    plan_id: str
    title: str
    start: str
    end: str
    fingerprint: str
    items: list[dict[str, str]] = field(default_factory=list)
    """Кожна поставлена задача на час: task_id, title, start, end (F2)."""
    untimed: list[dict[str, str]] = field(default_factory=list)
    unplaced: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Reply:
    text: str
    question: Question | None = None
    plan: PlanView | None = None
    choices: list[str] | None = None
    """Фрази двох варіантів під питанням `clarify` — для двох кнопок (clarify)."""
