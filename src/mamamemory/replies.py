"""Форми відповіді асистента (S3): `ReplyTo`, `Question`, `PlanView`, `Reply`.

Не робить: жодної логіки — лише значення, які `planning` і `assistant` повертають, а `http` віддає як JSON.
"""

from dataclasses import dataclass
from typing import Literal

QuestionKind = Literal["duration", "plan"]


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


@dataclass(frozen=True)
class Reply:
    text: str
    question: Question | None = None
    plan: PlanView | None = None
