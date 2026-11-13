"""Журнал роботи (F4 S1 working-on): «зараз працюю над …» — запис `work/{entry_id}` `{text, at}` під акаунтом.

Без виклику моделі. Той самий `entry_id` (повтор повідомлення) перезаписує той самий документ.
F4 S2 work-recall: `recent` — до 100 найновіших записів; `answer` — відповідь із журналу (Flash-Lite).
Не робить: пригадування справи (S3), прив'язки до справи.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from mamamemory.access import Session
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.replies import Reply

WORK = "work"
RECENT_LIMIT = 100  # threshold owner-ratified (2026-11-12)
NOTHING = "Поки нічого не записано про це."
# Слово власника 2026-11-13 («можна на ти»): звертання в обох відповідях (S2 work-recall, S3 case-recall).
ADDRESS = (
    "Звертайся до мами на «ти», у другій особі однини («ти працювала», «твої записи»); не «ви» і не «мама» в "
    "третій особі."
)


@dataclass(frozen=True)
class WorkEntry:
    id: str
    text: str
    at: datetime


def add(session: Session, text: str, entry_id: str, *, store: Store, now: datetime) -> Reply:
    """Записати, над чим мама працює; відповідь «Записала: …»."""
    said = text.strip()
    store.set(session.account_id, f"{WORK}/{entry_id}", {"text": said, "at": now.astimezone(UTC).isoformat()})
    return Reply(f"Записала: {said}.")


def recent(session: Session, *, store: Store, now: datetime) -> list[WorkEntry]:
    """До `RECENT_LIMIT` найновіших записів, найновіші спершу, без межі в часі (`now` — для відкладеного вікна
    періоду); понад `RECENT_LIMIT` — рядок журналу `WorkLogOver100` (лише вид і число, C1)."""
    entries = [
        entry for doc_id, data in store.list(session.account_id, WORK) if (entry := _entry(doc_id, data))
    ]
    if len(entries) > RECENT_LIMIT:
        print(json.dumps({"event": "notice", "kind": "WorkLogOver100", "count": len(entries)}), flush=True)
    return sorted(entries, key=lambda entry: entry.at, reverse=True)[:RECENT_LIMIT]


def answer(
    session: Session, question: str, *, store: Store, ai: AI, calendar: GoogleWork, now: datetime
) -> Reply:
    """Відповідь на питання про роботу з записів журналу; немає — `NOTHING`."""
    entries = recent(session, store=store, now=now)
    if not entries:
        return Reply(NOTHING)
    tz = ZoneInfo(calendar.timezone())
    result = ai.generate_json("answer_work", _answer_prompt(question, entries, now, tz), ANSWER_SCHEMA)
    text = str(result.get("answer") or "").strip()
    if result.get("found") is not True or not text:
        return Reply(NOTHING)
    return Reply(text)


ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "чи є в записах відповідь на питання"},
        "answer": {"type": "string", "description": "відповідь мамі з датами й часом записів"},
    },
    "required": ["found", "answer"],
}
WEEKDAYS = ("понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя")
MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)  # fmt: skip


def _entry(doc_id: str, data: dict[str, Any]) -> WorkEntry | None:
    """Запис журналу; без чинного `at` — `None`."""
    try:
        at = datetime.fromisoformat(str(data["at"]))
    except (KeyError, ValueError):
        return None
    if at.tzinfo is None:
        return None
    return WorkEntry(doc_id, str(data.get("text", "")), at)


def when(moment: datetime, tz: ZoneInfo) -> str:
    """День тижня, дата й час у зоні — як записи стоять у підказках (S2, S3)."""
    local = moment.astimezone(tz)
    return f"{WEEKDAYS[local.weekday()]}, {local.day} {MONTHS[local.month - 1]} {local.year}, {local:%H:%M}"


def _answer_prompt(question: str, entries: list[WorkEntry], now: datetime, tz: ZoneInfo) -> str:
    lines = "\n".join(f"- {when(entry.at, tz)}: {entry.text}" for entry in entries)
    return (
        f"Зараз {when(now, tz)}. Записи журналу роботи мами (найновіші спершу):\n{lines}\n"
        f"{ADDRESS}\n"
        f"Мама питає: «{question}». Відповідай лише з цих записів, суттю й повно, називаючи дату й час "
        "кожного запису, на який спираєшся (як вони написані вище). Якщо мама назвала період («вчора», "
        "«у вівторок») — бери лише записи цього періоду. Якщо в записах відповіді немає — found: false."
    )
