"""Пригадування справи (F4 S3 case-recall): «що ми знаємо про пані Шмідт?» — справа з каталогу (3.8 Flash),
відповідь з її опису, матеріалів і записів журналу про неї (Flash-Lite). Нічого не записує.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from mamamemory import cases
from mamamemory.access import Session
from mamamemory.cases import worklog
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.replies import Reply

NOT_FOUND = "Не знайшла такої справи. Скажіть ім'я чи назву інакше."
CHOOSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"number": {"type": ["integer", "null"], "description": "номер справи з каталогу"}},
    "required": ["number"],
}
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "чи є в матеріалах і записах відповідь"},
        "answer": {"type": "string", "description": "відповідь мамі з датами й часом записів"},
    },
    "required": ["found", "answer"],
}
KINDS = {"note": "нотатка", "photo": "фото", "file": "файл"}


def recall(
    session: Session, question: str, *, store: Store, ai: AI, calendar: GoogleWork, now: datetime
) -> Reply:
    """Справа з питання → відповідь з її матеріалів і записів журналу про неї; немає — `NOT_FOUND`."""
    known = cases.catalogue(session, store)
    if not known:
        return Reply(NOT_FOUND)
    case = _chosen(known, ai.generate_json("classify_case", _choose_prompt(known, question), CHOOSE_SCHEMA))
    if case is None:
        return Reply(NOT_FOUND)
    nothing = Reply(f"Про «{case.name}» поки нічого не записано.")
    materials = cases.texts(session, case.case_id, store)
    entries = worklog.recent(session, store=store, now=now)
    if not case.description and not materials and not entries:
        return nothing
    tz = ZoneInfo(calendar.timezone()) if entries else None
    prompt = _answer_prompt(case, materials, entries, question, tz)
    result = ai.generate_json("answer_case", prompt, ANSWER_SCHEMA)
    text = str(result.get("answer") or "").strip()
    if result.get("found") is not True or not text:
        return nothing
    return Reply(text)


def _chosen(known: list[cases.Case], answer: dict[str, Any]) -> cases.Case | None:
    """Справа за номером моделі: лише ціле (не `bool`) в межах каталогу."""
    number = answer.get("number")
    if type(number) is not int or not 1 <= number <= len(known):
        return None
    return known[number - 1]


def _choose_prompt(known: list[cases.Case], question: str) -> str:
    listed = "\n".join(f"{n}. {c.name} — {c.description}" for n, c in enumerate(known, start=1))
    return (
        "Мама веде справи — пацієнтів і проєкти. Ось каталог справ (номер. назва — опис):\n"
        f"{listed}\n"
        "Про яку справу питає мама — те саме прізвище чи проєкт, зокрема в іншому відмінку? number — номер "
        "справи з каталогу, якщо питання про неї, інакше null.\n"
        f"Питання: {question}"
    )


def _answer_prompt(
    case: cases.Case,
    materials: list[cases.Material],
    entries: list[worklog.WorkEntry],
    question: str,
    tz: ZoneInfo | None,
) -> str:
    texts = "\n".join(
        f"- {KINDS.get(m.kind, m.kind)}, {m.created.astimezone(UTC).date():%Y-%m-%d}: {m.text}"
        for m in materials
    )
    journal = "\n".join(f"- {worklog.when(e.at, tz)}: {e.text}" for e in entries) if tz else ""
    return (
        f"Справа «{case.name}». Опис: {case.description or '(немає)'}\n"
        f"Матеріали справи:\n{texts or '(немає)'}\n"
        f"Записи журналу роботи мами (про різні справи, найновіші спершу):\n{journal or '(немає)'}\n"
        f"{worklog.ADDRESS}\n"
        f"Мама питає: «{question}». Відповідай суттю й повно лише з матеріалів цієї справи і лише тих "
        "записів журналу, що про цю справу; називай дату й час кожного використаного запису (як вони "
        "написані вище). Питання «що ми знаємо», «що з'ясували», «нагадай» — про все, що є про справу: "
        "розкажи все суттєве з опису, матеріалів і записів про неї. found: true, якщо в описі, матеріалах чи "
        "записах про цю справу є хоч щось; found: false — лише коли про неї нічого немає."
    )
