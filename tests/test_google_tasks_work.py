"""Contract tests of the Tasks calls of `integrations.google_work` on a stand-in transport
(slice google-tasks, Seam 1).

Written by the slice tester from the sealed contract `.engine/slices/google-tasks.md`, without the code.
A real `AuthorizedSession` carries the calls; the S3 adapter answers them. The contract names the paths
(`tasks/v1/lists/@default/tasks`), not the host, so the adapter answers on both Google hosts that serve them.
"""

import contextlib
from collections.abc import Callable
from datetime import timedelta

import pytest
import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from mamamemory.integrations.google_work import DeadlinePassed, GoogleWork, TaskItem
from tests.test_one_task_google_work import (
    CALL_TIMEOUT_S,
    T0,
    Answer,
    Clock,
    Transport,
    body_of,
    path,
    query,
)

LIST_PATH = "/tasks/v1/lists/@default/tasks"


def tasks_work(
    route: Callable[[requests.PreparedRequest], Answer], clock: Clock | None = None
) -> tuple[GoogleWork, Transport]:
    transport = Transport(route)
    session = AuthorizedSession(Credentials("at-test"))
    session.mount("https://tasks.googleapis.com/", transport)
    session.mount("https://www.googleapis.com/", transport)
    work = GoogleWork(
        session, call_timeout_s=CALL_TIMEOUT_S, deadline=T0 + timedelta(seconds=60), now=clock or Clock(T0)
    )
    return work, transport


def item(task_id: str, title: str, **extra: str) -> dict[str, str]:
    return {"kind": "tasks#task", "id": task_id, "title": title, "status": "needsAction", **extra}


def test_seam1_list_open_tasks_reads_default_list_without_completed_and_hidden() -> None:
    work, transport = tasks_work(lambda r: (200, {"items": [item("tk-1", "оплатити світло")]}))
    found = work.list_open_tasks()
    assert found == [TaskItem("tk-1", "оплатити світло")]
    request = transport.sent[0]
    assert request.method == "GET"
    assert path(request) == LIST_PATH
    q = query(request)
    assert q["showCompleted"] == ["false"]
    assert q["showHidden"] == ["false"]


def test_seam1_list_open_tasks_follows_next_page_token_over_two_pages() -> None:
    def route(request: requests.PreparedRequest) -> Answer:
        if "pageToken" not in query(request):
            return 200, {"items": [item("tk-1", "оплатити світло")], "nextPageToken": "pg2"}
        assert query(request)["pageToken"] == ["pg2"]
        return 200, {"items": [item("tk-2", "забрати посилку")]}

    work, transport = tasks_work(route)
    found = work.list_open_tasks()
    assert sorted((t.id, t.title) for t in found) == [
        ("tk-1", "оплатити світло"),
        ("tk-2", "забрати посилку"),
    ]
    assert len(transport.sent) == 2
    for request in transport.sent:
        assert path(request) == LIST_PATH
        assert query(request)["showCompleted"] == ["false"]
        assert query(request)["showHidden"] == ["false"]


def test_seam1_list_open_tasks_leaves_out_empty_titles_and_subtasks() -> None:
    items = [
        item("tk-1", "оплатити світло"),
        item("tk-2", ""),
        item("tk-3", "купити лампочку", parent="tk-1"),
        item("tk-4", "забрати посилку"),
    ]
    work, _ = tasks_work(lambda r: (200, {"items": items}))
    found = work.list_open_tasks()
    assert sorted((t.id, t.title) for t in found) == [
        ("tk-1", "оплатити світло"),
        ("tk-4", "забрати посилку"),
    ]
    # A list with no items at all.
    work, _ = tasks_work(lambda r: (200, {"kind": "tasks#tasks"}))
    assert work.list_open_tasks() == []


def test_seam1_insert_task_posts_only_the_title_and_returns_the_id() -> None:
    work, transport = tasks_work(lambda r: (200, item("tk-new", "купити насіння")))
    assert work.insert_task("купити насіння") == "tk-new"
    assert [r.method for r in transport.sent] == ["POST"]
    request = transport.sent[0]
    assert path(request) == LIST_PATH
    assert body_of(request) == {"title": "купити насіння"}


def test_seam1_insert_task_is_not_retried() -> None:
    work, transport = tasks_work(lambda r: (503, {"error": {"code": 503, "message": "Backend Error"}}))
    with pytest.raises(Exception) as raised:
        work.insert_task("купити насіння")
    assert not isinstance(raised.value, NotImplementedError)
    assert [r.method for r in transport.sent] == ["POST"]


def test_seam1_complete_task_patches_status_completed() -> None:
    work, transport = tasks_work(lambda r: (200, item("tk-1", "оплатити світло", status="completed")))
    work.complete_task("tk-1")
    assert [r.method for r in transport.sent] == ["PATCH"]
    request = transport.sent[0]
    assert path(request) == f"{LIST_PATH}/tk-1"
    assert body_of(request).get("status") == "completed"


def test_seam1_complete_task_404_is_not_an_error_and_other_failures_are() -> None:
    work, transport = tasks_work(lambda r: (404, {"error": {"code": 404, "message": "Not Found"}}))
    work.complete_task("tk-gone")  # 404: no error
    assert [r.method for r in transport.sent] == ["PATCH"]
    work, transport = tasks_work(lambda r: (503, {"error": {"code": 503, "message": "Backend Error"}}))
    with pytest.raises(requests.exceptions.HTTPError):
        work.complete_task("tk-1")


def test_seam1_every_tasks_call_has_call_timeout() -> None:
    def route(request: requests.PreparedRequest) -> Answer:
        if request.method == "GET":
            return 200, {"items": [item("tk-1", "оплатити світло")]}
        if request.method == "POST":
            return 200, item("tk-new", "купити насіння")
        return 200, item("tk-1", "оплатити світло", status="completed")

    work, transport = tasks_work(route)
    work.list_open_tasks()
    work.insert_task("купити насіння")
    work.complete_task("tk-1")
    assert len(transport.timeouts) == 3
    for timeout in transport.timeouts:
        parts = timeout if isinstance(timeout, tuple) else (timeout,)
        assert all(p == CALL_TIMEOUT_S for p in parts), transport.timeouts


def test_seam1_deadline_is_checked_before_every_tasks_call() -> None:
    late = Clock(T0 + timedelta(seconds=120))  # past the deadline T0 + 60 s
    calls: list[Callable[[GoogleWork], object]] = [
        lambda w: w.list_open_tasks(),
        lambda w: w.insert_task("купити насіння"),
        lambda w: w.complete_task("tk-1"),
    ]
    for call in calls:
        work, transport = tasks_work(lambda r: (200, {"items": [], "id": "tk-x"}), late)
        with pytest.raises(DeadlinePassed):
            call(work)
        assert transport.sent == [], "no call is sent once the deadline has passed"

    # Between pages: the first page goes out in time, the clock passes the deadline, the next page does not.
    clock = Clock(T0)
    work, transport = tasks_work(
        lambda r: (200, {"items": [item("tk-1", "оплатити світло")], "nextPageToken": "pg2"}), clock
    )

    def pass_deadline() -> None:
        clock.at = T0 + timedelta(seconds=120)

    transport.after_send = pass_deadline
    with pytest.raises(DeadlinePassed):
        work.list_open_tasks()
    assert len(transport.sent) == 1
    with contextlib.suppress(Exception):
        work.list_open_tasks()
    assert len(transport.sent) == 1
