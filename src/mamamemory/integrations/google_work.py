"""Google Calendar через REST (S3, `integrations.google_work`): часовий пояс, події, створення з власним `id`.

`AuthorizedSession` з облікових даних сесії; кожен виклик — з таймаутом `CALL_TIMEOUT_S`, ланцюжок запиту — з
дедлайном. Не робить: Google Tasks (F2), повторів створення.
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TIMEZONE_URL = "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"
UNTITLED = "(без назви)"
TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"


@dataclass(frozen=True)
class Event:
    id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AgendaItem:
    """Подія для показу (show-schedule): назва, початок (UTC; `None` — на весь день), день у зоні."""

    title: str
    start: datetime | None
    day: date
    all_day: bool


@dataclass(frozen=True)
class TaskItem:
    id: str
    title: str
    due: date | None = None


class DeadlinePassed(Exception):
    """Немає часу на ще один виклик у межах запиту."""


def event_id(plan_id: str, task_id: str) -> str:
    """`base32hex(plan_id + task_id)` малими літерами без `=`."""
    return base64.b32hexencode((plan_id + task_id).encode()).decode().lower().rstrip("=")


class GoogleWork:
    def __init__(
        self, session: Any, *, call_timeout_s: float, deadline: datetime, now: Callable[[], datetime]
    ) -> None:
        """`session` — `AuthorizedSession` (або підставний з тим самим `request`); `now` — годинник."""
        self._session, self._call_timeout_s = session, call_timeout_s
        self._deadline, self._now = deadline, now

    def timezone(self) -> str:
        return str(self._call("GET", TIMEZONE_URL).json()["value"])

    def list_events(self, time_min: datetime, time_max: datetime) -> list[Event]:
        """Flow: усі сторінки → лише зайнятість (без подій на весь день, прозорих і скасованих)."""
        params: dict[str, str] = {
            "timeMin": _rfc3339(time_min),
            "timeMax": _rfc3339(time_max),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        items: list[dict[str, Any]] = []
        while True:
            page = self._call("GET", EVENTS_URL, params=params).json()
            items += page.get("items", [])
            if not page.get("nextPageToken"):
                break
            params = params | {"pageToken": page["nextPageToken"]}
        return [_event(item) for item in items if _is_busy(item)]

    def list_agenda(self, time_min: datetime, time_max: datetime) -> list[AgendaItem]:
        """Усі події періоду для показу: без скасованих, на весь день теж, у порядку Calendar."""
        params: dict[str, str] = {
            "timeMin": _rfc3339(time_min),
            "timeMax": _rfc3339(time_max),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        found: list[AgendaItem] = []
        while True:
            page = self._call("GET", EVENTS_URL, params=params).json()
            zone = page.get("timeZone")
            found += [
                _agenda_item(item, zone)
                for item in page.get("items", [])
                if item.get("status") != "cancelled"
            ]
            if not page.get("nextPageToken"):
                return found
            params = params | {"pageToken": page["nextPageToken"]}

    def get_event(self, event_id: str) -> Event | None:
        response = self._call("GET", f"{EVENTS_URL}/{event_id}", allow=(404,))
        if response.status_code == 404:
            return None
        return _event(response.json())

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        """Створення без повтору; 409 на повторний `id` — подія вже є."""
        body = {
            "id": event_id,
            "summary": title,
            "start": {"dateTime": _rfc3339(start)},
            "end": {"dateTime": _rfc3339(end)},
        }
        response = self._call("POST", EVENTS_URL, json=body, allow=(409,))
        if response.status_code == 409:
            return event_id
        return str(response.json().get("id", event_id))

    def list_open_tasks(self) -> list[TaskItem]:
        """Відкриті задачі списку `@default` (усі сторінки), без порожніх назв і підзадач."""
        params: dict[str, str] = {"showCompleted": "false", "showHidden": "false"}
        items: list[dict[str, Any]] = []
        while True:
            page = self._call("GET", TASKS_URL, params=params).json()
            items += page.get("items", [])
            if not page.get("nextPageToken"):
                break
            params = params | {"pageToken": page["nextPageToken"]}
        return [
            TaskItem(str(item["id"]), str(item["title"]).strip(), _due(item.get("due")))
            for item in items
            if str(item.get("title") or "").strip() and not item.get("parent")
        ]

    def insert_task(self, title: str) -> str:
        """Нова задача в `@default` лише з назвою (ADR-0002); без повторів."""
        return str(self._call("POST", TASKS_URL, json={"title": title}).json()["id"])

    def complete_task(self, task_id: str) -> None:
        """Закрити задачу; 404 — її вже нема, не помилка."""
        self._call("PATCH", f"{TASKS_URL}/{task_id}", json={"status": "completed"}, allow=(404,))

    def _call(self, method: str, url: str, *, allow: tuple[int, ...] = (), **kwargs: Any) -> Any:
        if self._now() >= self._deadline:
            raise DeadlinePassed(f"{method} {url}")
        response = self._session.request(method, url, timeout=self._call_timeout_s, **kwargs)
        if response.status_code not in allow:
            response.raise_for_status()
        return response


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _is_busy(item: dict[str, Any]) -> bool:
    timed = "dateTime" in item.get("start", {})
    return timed and item.get("transparency") != "transparent" and item.get("status") != "cancelled"


def _event(item: dict[str, Any]) -> Event:
    return Event(str(item["id"]), _moment(item.get("start", {})), _moment(item.get("end", {})))


def _agenda_item(item: dict[str, Any], zone: str | None) -> AgendaItem:
    """Подія з часом — початок у UTC і день у зоні календаря; на весь день — її дата, без часу."""
    title = str(item.get("summary") or UNTITLED)
    when = item.get("start", {})
    if "dateTime" not in when:
        return AgendaItem(title, None, date.fromisoformat(when["date"]), True)
    local = datetime.fromisoformat(when["dateTime"])
    if zone:
        local = local.astimezone(ZoneInfo(zone))
    return AgendaItem(title, local.astimezone(UTC), local.date(), False)


def _moment(when: dict[str, Any]) -> datetime:
    """Час події; скасована подія може прийти без часу — тоді найдавніший момент."""
    if "dateTime" not in when:
        return datetime.min.replace(tzinfo=UTC)
    return datetime.fromisoformat(when["dateTime"]).astimezone(UTC)


def _due(value: object) -> date | None:
    """Дата задачі з `due` Tasks API (RFC 3339, значуща лише дата — перші 10 символів); інакше `None`."""
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
