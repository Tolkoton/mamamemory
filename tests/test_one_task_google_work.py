"""Contract tests of `integrations.google_work` on a stand-in transport (slice one-task-to-calendar, Seam 3).

Written by the slice tester from the sealed contract `.engine/slices/one-task-to-calendar.md`,
without the code. A real `AuthorizedSession` carries the calls; a `requests` adapter mounted on
googleapis.com answers them and records what it was sent.
"""

import contextlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests.adapters import BaseAdapter

from mamamemory.integrations.google_work import (
    EVENTS_URL,
    TIMEZONE_URL,
    DeadlinePassed,
    Event,
    GoogleWork,
    event_id,
)

T0 = datetime(2026, 11, 9, 9, 7, 0, tzinfo=UTC)
CALL_TIMEOUT_S = 10
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
CALENDAR_ID = re.compile(r"^[a-v0-9]{5,1024}$")

Answer = tuple[int, dict[str, Any]]


class Transport(BaseAdapter):
    """Answers each request with the next answer `route(request)` gives; records request and timeout."""

    def __init__(self, route: Callable[[requests.PreparedRequest], Answer]) -> None:
        super().__init__()
        self.route = route
        self.sent: list[requests.PreparedRequest] = []
        self.timeouts: list[Any] = []
        self.after_send: Callable[[], None] | None = None

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        self.sent.append(request)
        self.timeouts.append(timeout)
        status, body = self.route(request)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        response.url = str(request.url)
        response.request = request
        response.encoding = "utf-8"
        if self.after_send is not None:
            self.after_send()
        return response

    def close(self) -> None:
        pass


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def work(
    route: Callable[[requests.PreparedRequest], Answer], clock: Clock | None = None
) -> tuple[GoogleWork, Transport]:
    transport = Transport(route)
    session = AuthorizedSession(Credentials("at-test"))
    session.mount("https://www.googleapis.com/", transport)
    calendar = GoogleWork(
        session, call_timeout_s=CALL_TIMEOUT_S, deadline=T0 + timedelta(seconds=60), now=clock or Clock(T0)
    )
    return calendar, transport


def body_of(request: requests.PreparedRequest) -> Any:
    raw = request.body or b"{}"
    return json.loads(raw if isinstance(raw, (bytes, str)) else b"{}")


def query(request: requests.PreparedRequest) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(request.url)).query)


def path(request: requests.PreparedRequest) -> str:
    return urlparse(str(request.url)).path


def timed(event_id_: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": event_id_,
        "status": "confirmed",
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        **extra,
    }


# ------------------------------------------------------------------ event_id


def test_event_id_is_lowercase_base32hex_of_plan_and_task_without_padding() -> None:
    # Written by hand: base32hex("p1t1") = "E0ON8C8=", base32hex("plan-7task-1") = "E1M62RHD6TQ62SRB5KOG====".
    assert event_id("p1", "t1") == "e0on8c8"
    assert event_id("plan-7", "task-1") == "e1m62rhd6tq62srb5kog"
    for plan_id, task_id in [("p1", "t1"), ("plan-7", "task-1"), ("0f3a9c1e-uuid-like", "t-01")]:
        assert CALENDAR_ID.match(event_id(plan_id, task_id))
    assert event_id("p1", "t1") == event_id("p1", "t1")
    assert event_id("p1", "t1") != event_id("p1", "t2")


# ------------------------------------------------------------------ the four calls


def test_timezone_reads_calendar_setting() -> None:
    calendar, transport = work(
        lambda r: (200, {"kind": "calendar#setting", "id": "timezone", "value": "Europe/Berlin"})
    )
    assert calendar.timezone() == "Europe/Berlin"
    assert [r.method for r in transport.sent] == ["GET"]
    assert str(transport.sent[0].url).split("?")[0] == TIMEZONE_URL
    assert path(transport.sent[0]) == "/calendar/v3/users/me/settings/timezone"


def test_list_events_sends_window_in_rfc3339_with_single_events_ordered() -> None:
    calendar, transport = work(lambda r: (200, {"items": []}))
    time_min, time_max = T0, T0 + timedelta(days=7)
    calendar.list_events(time_min, time_max)
    request = transport.sent[0]
    assert request.method == "GET"
    assert path(request) == "/calendar/v3/calendars/primary/events"
    assert str(request.url).split("?")[0] == EVENTS_URL
    q = query(request)
    assert q["singleEvents"] == ["true"]
    assert q["orderBy"] == ["startTime"]
    for key, value in (("timeMin", time_min), ("timeMax", time_max)):
        assert RFC3339.match(q[key][0]), q[key]
        assert datetime.fromisoformat(q[key][0].replace("Z", "+00:00")) == value


def test_list_events_follows_next_page_token_to_the_end() -> None:
    def route(request: requests.PreparedRequest) -> Answer:
        if "pageToken" not in query(request):
            return 200, {
                "items": [timed("ev1", "2026-11-09T11:00:00+01:00", "2026-11-09T12:00:00+01:00")],
                "nextPageToken": "pg2",
            }
        if query(request)["pageToken"] == ["pg2"]:
            return 200, {
                "items": [timed("ev2", "2026-11-10T09:00:00Z", "2026-11-10T09:30:00Z")],
                "nextPageToken": "pg3",
            }
        return 200, {"items": [timed("ev3", "2026-11-11T08:00:00Z", "2026-11-11T08:15:00Z")]}

    calendar, transport = work(route)
    events = calendar.list_events(T0, T0 + timedelta(days=7))
    assert sorted(e.id for e in events) == ["ev1", "ev2", "ev3"]
    by_id = {e.id: e for e in events}
    assert by_id["ev1"].start == datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    assert by_id["ev1"].end == datetime(2026, 11, 9, 11, 0, tzinfo=UTC)
    assert by_id["ev2"].start == datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    assert len(transport.sent) == 3
    for request in transport.sent:
        assert query(request)["singleEvents"] == ["true"]


def test_list_events_leaves_out_all_day_and_transparent_events() -> None:
    items = [
        timed("busy1", "2026-11-09T11:00:00+01:00", "2026-11-09T12:00:00+01:00"),
        {
            "id": "allday",
            "status": "confirmed",
            "start": {"date": "2026-11-10"},
            "end": {"date": "2026-11-11"},
        },
        timed("free1", "2026-11-09T13:00:00+01:00", "2026-11-09T14:00:00+01:00", transparency="transparent"),
        timed("busy2", "2026-11-09T15:00:00+01:00", "2026-11-09T16:00:00+01:00", transparency="opaque"),
    ]
    calendar, _ = work(lambda r: (200, {"items": items}))
    events = calendar.list_events(T0, T0 + timedelta(days=7))
    assert sorted(e.id for e in events) == ["busy1", "busy2"]


def test_get_event_404_is_none_and_cancelled_is_an_event() -> None:
    calendar, transport = work(lambda r: (404, {"error": {"code": 404, "message": "Not Found"}}))
    assert calendar.get_event("e0on8c8") is None
    assert transport.sent[0].method == "GET"
    assert str(transport.sent[0].url).split("?")[0] == f"{EVENTS_URL}/e0on8c8"

    cancelled = timed("e0on8c8", "2026-11-09T10:15:00+01:00", "2026-11-09T10:45:00+01:00")
    cancelled["status"] = "cancelled"
    calendar, _ = work(lambda r: (200, cancelled))
    found = calendar.get_event("e0on8c8")
    assert found is not None
    assert found.id == "e0on8c8"
    assert found.start == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert isinstance(found, Event)


def test_insert_event_posts_own_id_title_and_times() -> None:
    def route(request: requests.PreparedRequest) -> Answer:
        body = body_of(request)
        return 200, {**body, "status": "confirmed"}

    calendar, transport = work(route)
    eid = event_id("p1", "t1")
    start, end = datetime(2026, 11, 9, 9, 15, tzinfo=UTC), datetime(2026, 11, 9, 9, 45, tzinfo=UTC)
    result = calendar.insert_event(eid, "подзвонити нотаріусу", start, end)
    assert isinstance(result, str)
    request = transport.sent[0]
    assert request.method == "POST"
    assert str(request.url).split("?")[0] == EVENTS_URL
    body = body_of(request)
    assert body["id"] == "e0on8c8"
    assert CALENDAR_ID.match(body["id"])
    assert body["summary"] == "подзвонити нотаріусу"
    assert datetime.fromisoformat(body["start"]["dateTime"].replace("Z", "+00:00")) == start
    assert datetime.fromisoformat(body["end"]["dateTime"].replace("Z", "+00:00")) == end


def test_insert_event_409_on_repeated_id_counts_as_already_there() -> None:
    calendar, transport = work(
        lambda r: (409, {"error": {"code": 409, "message": "The requested identifier already exists."}})
    )
    result = calendar.insert_event("e0on8c8", "подзвонити нотаріусу", T0, T0 + timedelta(minutes=30))
    assert isinstance(result, str)
    assert len(transport.sent) == 1


def test_insert_event_is_not_retried() -> None:
    calendar, transport = work(lambda r: (503, {"error": {"code": 503, "message": "Backend Error"}}))
    with contextlib.suppress(Exception):
        calendar.insert_event("e0on8c8", "подзвонити нотаріусу", T0, T0 + timedelta(minutes=30))
    assert [r.method for r in transport.sent] == ["POST"]


def test_every_call_has_call_timeout() -> None:
    def route(request: requests.PreparedRequest) -> Answer:
        if path(request).endswith("/timezone"):
            return 200, {"value": "Europe/Berlin"}
        if request.method == "POST":
            return 200, body_of(request)
        if path(request).endswith("/events"):
            return 200, {"items": []}
        return 404, {"error": {"code": 404}}

    calendar, transport = work(route)
    calendar.timezone()
    calendar.list_events(T0, T0 + timedelta(days=7))
    calendar.get_event("e0on8c8")
    calendar.insert_event("e0on8c8", "подзвонити нотаріусу", T0, T0 + timedelta(minutes=30))
    assert len(transport.timeouts) == 4
    for timeout in transport.timeouts:
        parts = timeout if isinstance(timeout, tuple) else (timeout,)
        assert all(p == CALL_TIMEOUT_S for p in parts), transport.timeouts


def test_deadline_is_checked_before_every_call() -> None:
    late = Clock(T0 + timedelta(seconds=120))  # past the deadline T0 + 60 s
    calls: list[Callable[[GoogleWork], object]] = [
        lambda c: c.timezone(),
        lambda c: c.list_events(T0, T0 + timedelta(days=7)),
        lambda c: c.get_event("e0on8c8"),
        lambda c: c.insert_event("e0on8c8", "подзвонити нотаріусу", T0, T0 + timedelta(minutes=30)),
    ]
    for call in calls:
        calendar, transport = work(lambda r: (200, {"value": "Europe/Berlin", "items": []}), late)
        with pytest.raises(DeadlinePassed):
            call(calendar)
        assert transport.sent == [], "no call is sent once the deadline has passed"

    # Between pages: the first page goes out in time, the clock passes the deadline, the next page does not.
    clock = Clock(T0)
    calendar, transport = work(
        lambda r: (
            200,
            {"items": [timed("ev1", "2026-11-09T11:00:00Z", "2026-11-09T12:00:00Z")], "nextPageToken": "pg2"},
        ),
        clock,
    )

    def pass_deadline() -> None:
        clock.at = T0 + timedelta(seconds=120)

    transport.after_send = pass_deadline
    with pytest.raises(DeadlinePassed):
        calendar.list_events(T0, T0 + timedelta(days=7))
    assert len(transport.sent) == 1
