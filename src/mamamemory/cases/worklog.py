"""Журнал роботи (F4 S1 working-on): «зараз працюю над …» — запис `work/{entry_id}` `{text, at}` під акаунтом.

Без виклику моделі. Той самий `entry_id` (повтор повідомлення) перезаписує той самий документ.
Не робить: відповідей із журналу (S2), пригадування справи (S3), прив'язки до справи.
"""

from datetime import UTC, datetime

from mamamemory.access import Session
from mamamemory.integrations.store import Store
from mamamemory.replies import Reply

WORK = "work"


def add(session: Session, text: str, entry_id: str, *, store: Store, now: datetime) -> Reply:
    """Записати, над чим мама працює; відповідь «Записала: …»."""
    said = text.strip()
    store.set(session.account_id, f"{WORK}/{entry_id}", {"text": said, "at": now.astimezone(UTC).isoformat()})
    return Reply(f"Записала: {said}.")
