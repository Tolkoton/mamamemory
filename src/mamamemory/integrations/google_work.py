"""Google Calendar через REST (S3, `integrations.google_work`): часовий пояс, події, створення з власним `id`.

`AuthorizedSession` з облікових даних сесії; кожен виклик — з таймаутом `CALL_TIMEOUT_S`, ланцюжок запиту — з
дедлайном. Не робить: Google Tasks (F2), повторів створення.
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TIMEZONE_URL = "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"


@dataclass(frozen=True)
class Event:
    id: str
    start: datetime
    end: datetime


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


def _moment(when: dict[str, Any]) -> datetime:
    """Час події; скасована подія може прийти без часу — тоді найдавніший момент."""
    if "dateTime" not in when:
        return datetime.min.replace(tzinfo=UTC)
    return datetime.fromisoformat(when["dateTime"]).astimezone(UTC)
