"""Contract tests of `GoogleWork.list_agenda` on a stand-in transport (slice show-schedule, Seam 2).

Written by the slice tester from the sealed contract `.engine/slices/show-schedule.md`, without the code.
A real `AuthorizedSession` carries the calls; the S3 adapter answers them. The stand-in Calendar is told the
zone three ways that agree (the timezone setting, the list's `timeZone`, the offset of each `dateTime`): the
contract does not say where `list_agenda` takes the zone from.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests

from mamamemory.integrations.google_work import AgendaItem, GoogleWork
from tests.test_one_task_google_work import Answer, Transport, path, query, work

EVENTS_PATH = "/calendar/v3/calendars/primary/events"
BERLIN = "Europe/Berlin"
TIME_MIN = datetime(2026, 11, 15, 22, 30, tzinfo=UTC)
TIME_MAX = datetime(2026, 11, 22, 23, 0, tzinfo=UTC)


def event(event_id: str, summary: str | None, start: dict[str, str], **extra: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {"id": event_id, "status": "confirmed", "start": start, "end": start, **extra}
    if summary is not None:
        raw["summary"] = summary
    return raw


def at(local: str) -> dict[str, str]:
    return {"dateTime": local}


def day(value: str) -> dict[str, str]:
    return {"date": value}


def calendar(pages: list[list[dict[str, Any]]]) -> tuple[GoogleWork, Transport]:
    """Berlin; the events list answers `pages` one after another, chained by `nextPageToken`."""

    def route(request: requests.PreparedRequest) -> Answer:
        if path(request).endswith("/settings/timezone"):
            return 200, {"kind": "calendar#setting", "id": "timezone", "value": BERLIN}
        number = int(query(request).get("pageToken", ["0"])[0])
        page: dict[str, Any] = {"timeZone": BERLIN, "items": pages[number]}
        if number + 1 < len(pages):
            page["nextPageToken"] = str(number + 1)
        return 200, page

    return work(route)


def agenda(pages: list[list[dict[str, Any]]]) -> list[AgendaItem]:
    google, _ = calendar(pages)
    return google.list_agenda(TIME_MIN, TIME_MAX)


def event_requests(transport: Transport) -> list[requests.PreparedRequest]:
    return [r for r in transport.sent if path(r) == EVENTS_PATH]


def test_list_agenda_reads_the_window_as_single_events_ordered_by_start() -> None:
    google, transport = calendar([[]])
    assert google.list_agenda(TIME_MIN, TIME_MAX) == []
    sent = event_requests(transport)
    assert len(sent) == 1
    q = query(sent[0])
    assert sent[0].method == "GET"
    assert datetime.fromisoformat(q["timeMin"][0]) == TIME_MIN
    assert datetime.fromisoformat(q["timeMax"][0]) == TIME_MAX
    assert q["singleEvents"] == ["true"]
    assert q["orderBy"] == ["startTime"]


def test_seam2_list_agenda_reads_every_page() -> None:
    google, transport = calendar(
        [
            [event("e1", "Лікар", at("2026-11-16T10:00:00+01:00"))],
            [event("e2", "Нотаріус", at("2026-11-17T10:00:00+01:00"))],
            [event("e3", "Перукар", at("2026-11-18T10:00:00+01:00"))],
        ]
    )
    found = google.list_agenda(TIME_MIN, TIME_MAX)
    assert [item.title for item in found] == ["Лікар", "Нотаріус", "Перукар"]
    sent = event_requests(transport)
    assert len(sent) == 3
    assert [query(r).get("pageToken") for r in sent] == [None, ["1"], ["2"]]


def test_seam2_list_agenda_leaves_out_cancelled_events() -> None:
    found = agenda(
        [
            [
                event("e1", "Лікар", at("2026-11-16T10:00:00+01:00")),
                event("e2", "Скасоване", at("2026-11-16T12:00:00+01:00"), status="cancelled"),
            ],
            [{"id": "e3", "status": "cancelled"}, event("e4", "Банк", at("2026-11-17T11:00:00+01:00"))],
        ]
    )
    assert [item.title for item in found] == ["Лікар", "Банк"]


def test_list_agenda_keeps_free_events_too() -> None:
    found = agenda([[event("e1", "Прогулянка", at("2026-11-16T10:00:00+01:00"), transparency="transparent")]])
    assert [item.title for item in found] == ["Прогулянка"]


def test_list_agenda_timed_event_starts_in_utc_on_its_day_in_calendar_zone() -> None:
    found = agenda([[event("e1", "Нічний рейс", at("2026-11-16T00:30:00+01:00"))]])
    assert found == [
        AgendaItem("Нічний рейс", datetime(2026, 11, 15, 23, 30, tzinfo=UTC), date(2026, 11, 16), False)
    ]
    start = found[0].start
    assert start is not None and start.utcoffset() == timedelta(0)


def test_seam2_list_agenda_all_day_event_has_no_start_and_its_date() -> None:
    found = agenda([[event("e1", "Відпустка", day("2026-11-18"), end=day("2026-11-21"))]])
    assert found == [AgendaItem("Відпустка", None, date(2026, 11, 18), True)]


def test_seam2_list_agenda_event_without_summary_is_untitled() -> None:
    found = agenda([[event("e1", None, at("2026-11-16T11:00:00+01:00"))]])
    assert [item.title for item in found] == ["(без назви)"]


def test_seam2_list_agenda_keeps_the_order_calendar_gave() -> None:
    found = agenda(
        [
            [
                event("e1", "Ярмарок", day("2026-11-16"), end=day("2026-11-17")),
                event("e2", "Банк", at("2026-11-16T10:00:00+01:00")),
            ],
            [event("e3", "Аптека", at("2026-11-16T12:00:00+01:00"))],
        ]
    )
    assert [item.title for item in found] == ["Ярмарок", "Банк", "Аптека"]
