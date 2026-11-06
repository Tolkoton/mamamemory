"""Асистент (S3): маршрутизація повідомлення мами до `planning`.

Не робить: голосу (S2), незакритих питань (S4), правок плану (F2).
"""

from datetime import datetime
from typing import Any

from mamamemory import planning
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.replies import Reply, ReplyTo

CANNOT_TEXT = "Поки що я вмію записати одну задачу в календар."

ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"intent": {"type": "string", "enum": ["yes", "new_task", "other"]}},
    "required": ["intent"],
}


def handle_message(
    session: Session,
    text: str,
    reply_to: ReplyTo | None,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    config: Config,
    now: datetime,
) -> Reply:
    """Flow: відповідь на питання про тривалість → `answer_duration`; інакше модель маршрутизації."""
    if reply_to is not None and reply_to.kind == "duration":
        return planning.answer_duration(
            session, reply_to.id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
        )
    intent = ai.generate_json("route", _route_prompt(text, reply_to), ROUTE_SCHEMA).get("intent")
    if intent == "yes" and reply_to is not None and reply_to.kind == "plan" and reply_to.fingerprint:
        return planning.confirm(
            session, reply_to.id, reply_to.fingerprint, calendar=calendar, store=store, now=now, config=config
        )
    if intent == "new_task":
        return planning.start(session, text, ai=ai, calendar=calendar, store=store, now=now, config=config)
    return Reply(CANNOT_TEXT)


def _route_prompt(text: str, reply_to: ReplyTo | None) -> str:
    asked = "Асистент щойно запропонував план і спитав «Записати?». " if reply_to is not None else ""
    return (
        f"{asked}Мама сказала: «{text}». Визнач intent: yes — вона погоджується з планом; "
        "new_task — це нова задача, яку треба поставити в календар; other — щось інше."
    )
