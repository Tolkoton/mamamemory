"""Показ запланованого (поправка F2 show-schedule): «які плани на сьогодні / завтра / тиждень»,
«наступний тиждень» — події календаря мами за період, по днях, і задачі Google Tasks з датою в періоді
(calm-open). Нічого не записує.
"""

import re
from datetime import date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.google_work import AgendaItem, GoogleWork, TaskItem
from mamamemory.replies import Card, CardItem, CardSection, Reply

HEADERS = {
    "today": "На сьогодні",
    "tomorrow": "На завтра",
    "week": "На цей тиждень",
    "next_week": "На наступний тиждень",
}
TASKS_HEADER = "Задачі без часу:"
LIST_HEADER = "Задачі в списку:"
NO_OPEN_TASKS = "Відкритих задач немає."
TASKS_OFF = "Список задач вимкнено."
NOTHING_ROW = "В календарі нічого немає."
TASKS_FAILED = "Не вдалося прочитати задачі, спробуйте ще раз."
WEEKDAYS = ("Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя")
MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)  # fmt: skip


def period(text: str) -> str:
    """`today`, `tomorrow`, `week` чи `next_week` — за цілими словами тексту."""
    words = re.findall(r"[\w'ʼ’]+", text.casefold())
    week = any(w.startswith(("тижд", "тижн")) for w in words)
    if "завтра" in words:
        return "tomorrow"
    if week and any(w.startswith("наступн") for w in words):
        return "next_week"
    return "week" if week else "today"


def show(session: Session, text: str, *, calendar: GoogleWork, now: datetime, config: Config) -> Reply:
    """Події календаря за період з тексту, по днях; немає — «На … в календарі нічого немає.»."""
    kind = period(text)
    tz = ZoneInfo(calendar.timezone())
    start, end = _window(kind, now.astimezone(tz))
    items = calendar.list_agenda(start, end)
    tasks = _due_in(_open_tasks(calendar), start.date(), end.date()) if config.use_tasks else []
    events = (
        [f"{HEADERS[kind]}:", *_lines(kind, items, start.date(), tz)]
        if items
        else [f"{HEADERS[kind]} в календарі нічого немає."]
    )
    listed = [TASKS_HEADER, *(f"• {task.title}" for task in tasks)] if tasks else []
    return Reply("\n".join([*events, *listed]), card=_schedule_card(kind, items, tasks, start.date(), tz))


def _schedule_card(
    kind: str, items: list[AgendaItem], tasks: list[TaskItem], first: date, tz: ZoneInfo
) -> Card | None:
    """Та сама відповідь карткою (agenda-card): розділи днів (тиждень) чи один розділ, далі задачі з датою."""
    if not items and not tasks:
        return None
    nothing = [CardSection(None, [CardItem(None, NOTHING_ROW)])]
    sections = _day_sections(kind, items, first, tz) if items else nothing
    if tasks:
        sections.append(CardSection(TASKS_HEADER.rstrip(":"), [CardItem(None, task.title) for task in tasks]))
    return Card(HEADERS[kind], sections)


def _day_sections(kind: str, items: list[AgendaItem], first: date, tz: ZoneInfo) -> list[CardSection]:
    """Події по днях, як `_lines`: для тижня — розділ на день із заголовком дня; інакше — один без
    заголовка."""
    sections: list[CardSection] = []
    shown: date | None = None
    for item in items:
        day = max(item.day, first)
        if not sections or (kind in ("week", "next_week") and day != shown):
            heading = f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"
            sections.append(CardSection(heading if kind in ("week", "next_week") else None, []))
        shown = day
        sections[-1].items.append(_card_item(item, tz))
    return sections


def _card_item(item: AgendaItem, tz: ZoneInfo) -> CardItem:
    if item.all_day or item.start is None:
        return CardItem("весь день", item.title)
    return CardItem(f"{item.start.astimezone(tz):%H:%M}", item.title)


def tasks(*, calendar: GoogleWork, config: Config) -> Reply:
    """«Які в мене задачі?» (tasks-list): усі відкриті задачі Google Tasks у порядку списку, з датою,
    де вона є. Будь-яка помилка читання — текст збою. Нічого не пише."""
    if not config.use_tasks:
        return Reply(TASKS_OFF)
    try:
        found = calendar.list_open_tasks()
    except Exception:
        return Reply(TASKS_FAILED)
    if not found:
        return Reply(NO_OPEN_TASKS)
    card = Card(LIST_HEADER.rstrip(":"), [CardSection(None, [_task_item(task) for task in found])])
    return Reply("\n".join([LIST_HEADER, *(_task_line(task) for task in found)]), card=card)


def _task_item(task: TaskItem) -> CardItem:
    due = f"до {task.due.day} {MONTHS[task.due.month - 1]}" if task.due is not None else None
    return CardItem(None, task.title, due)


def _task_line(task: TaskItem) -> str:
    if task.due is None:
        return f"• {task.title}"
    return f"• {task.title} — до {task.due.day} {MONTHS[task.due.month - 1]}"


def _due_in(tasks: list[TaskItem], first: date, end: date) -> list[TaskItem]:
    """Задачі з датою від `first` включно до `end` не включно (місцеві дати вікна), у порядку списку."""
    return [task for task in tasks if task.due is not None and first <= task.due < end]


def _open_tasks(calendar: GoogleWork) -> list[TaskItem]:
    """Відкриті задачі Google Tasks; будь-яка помилка — без розділу задач (календар лишається)."""
    try:
        return calendar.list_open_tasks()
    except Exception:
        return []


def _window(kind: str, local_now: datetime) -> tuple[datetime, datetime]:
    """Межі періоду в зоні календаря; кінець — наступна місцева північ (не включно)."""
    today = local_now.date()
    tz = local_now.tzinfo
    if kind == "tomorrow":
        return _midnight(today + timedelta(days=1), tz), _midnight(today + timedelta(days=2), tz)
    if kind == "week":
        return local_now, _midnight(today + timedelta(days=7 - today.weekday()), tz)
    if kind == "next_week":
        monday = today + timedelta(days=7 - today.weekday())
        return _midnight(monday, tz), _midnight(monday + timedelta(days=7), tz)
    return local_now, _midnight(today + timedelta(days=1), tz)


def _midnight(day: date, tz: tzinfo | None) -> datetime:
    return datetime.combine(day, time(), tzinfo=tz)


def _lines(kind: str, items: list[AgendaItem], first: date, tz: ZoneInfo) -> list[str]:
    """По днях (не раніше першого дня періоду); рядок дня — лише для тижня."""
    lines: list[str] = []
    shown: date | None = None
    for item in items:
        day = max(item.day, first)
        if kind in ("week", "next_week") and day != shown:
            lines.append(f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}:")
        shown = day
        lines.append(_item_line(item, tz))
    return lines


def _item_line(item: AgendaItem, tz: ZoneInfo) -> str:
    if item.all_day or item.start is None:
        return f"• весь день — {item.title}"
    return f"• {item.start.astimezone(tz):%H:%M} {item.title}"
