"""Contract tests of `GET /api/open` (slice open-questions).

Written by the slice tester from the sealed contract `.engine/slices/open-questions.md`, without the code.
The Calendar factory of `create_app` is replaced: it returns the S3 fake, or raises (an expired sign-in
raises only when the calendar is built, as in the real system).
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import requests
from fastapi.testclient import TestClient

from mamamemory import assistant
from mamamemory.access import Session
from mamamemory.errors import LoginExpired
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.google_work import GoogleWork
from tests.test_one_task_http import MAMA, SUB, WEEK_S, App, FakeGoogle
from tests.test_one_task_planning import NOW, TITLE, instant

SIGN_IN_AGAIN = "Щоб показати план, увійди знову."
FAILED = "Не вдалося, спробуйте ще раз."
# stuck-question: the duration question names the task, for one task too.
ASK_DURATION = f"Скільки часу займе «{TITLE}»?"


class OpenApp(App):
    """The S3 test app with a Calendar factory that counts its calls and may raise."""

    def __init__(self) -> None:
        super().__init__()
        self.raises: BaseException | None = None
        self.factory_calls = 0

        def factory(session: Session, started: datetime) -> GoogleWork:
            self.factory_calls += 1
            if self.raises is not None:
                raise self.raises
            return cast(GoogleWork, self.calendar)

        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=factory,
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )

    def guide_seen(self) -> None:
        """The account has already seen the guide (F5 guide, «Перше відкриття»): the mark is in the store."""
        self.store.set(SUB, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})


def test_open_without_valid_session_is_401_without_location() -> None:
    app = OpenApp()
    resp = app.client.get("/api/open")
    assert resp.status_code == 401, resp.status_code
    assert "location" not in resp.headers
    app.sign_in(at=NOW - timedelta(seconds=WEEK_S + 60))
    resp = app.client.get("/api/open")
    assert resp.status_code == 401, resp.status_code
    assert "location" not in resp.headers


def test_open_without_draft_is_empty() -> None:
    app = OpenApp()
    app.sign_in()
    app.guide_seen()
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replies"] == []
    assert body["login_needed"] is False


def test_open_returns_shown_plan_with_its_question() -> None:
    app = OpenApp()
    app.sign_in()
    app.guide_seen()
    first = app.start(app.calendar, duration_min=30).plan
    assert first is not None
    app.clock.at = NOW + timedelta(minutes=1)
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["login_needed"] is False
    assert len(body["replies"]) == 1
    reply = body["replies"][0]
    plan = reply["plan"]
    assert plan["plan_id"] == first.plan_id
    assert plan["title"] == TITLE
    assert instant(plan["start"]) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert instant(plan["end"]) == datetime(2026, 11, 9, 9, 45, tzinfo=UTC)
    assert reply["question"] == {"kind": "plan", "id": plan["plan_id"], "fingerprint": plan["fingerprint"]}
    assert app.calendar.insert_calls == []


def test_open_with_expired_google_sign_in_gives_login_needed() -> None:
    app = OpenApp()
    app.sign_in()
    app.guide_seen()
    app.start(app.calendar, duration_min=30)
    app.raises = LoginExpired()
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replies"] == [{"text": SIGN_IN_AGAIN, "question": None, "plan": None}]
    assert body["login_needed"] is True


def test_open_asking_duration_needs_no_calendar_even_when_sign_in_expired() -> None:
    app = OpenApp()
    app.sign_in()
    app.guide_seen()
    asked = app.start(app.calendar, duration_min=None).question
    assert asked is not None
    app.raises = LoginExpired()
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replies"] == [
        {
            "text": ASK_DURATION,
            "question": {"kind": "duration", "id": asked.id, "fingerprint": None},
            "plan": None,
        }
    ]
    assert body["login_needed"] is False
    assert app.factory_calls == 0


def test_open_with_calendar_error_is_empty_not_failed_and_logs_one_line(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = OpenApp()
    app.sign_in()
    app.guide_seen()
    app.start(app.calendar, duration_min=30)

    def broken(time_min: datetime, time_max: datetime) -> list[Any]:
        raise requests.HTTPError("fake: 500 Backend Error")

    monkeypatch.setattr(app.calendar, "list_events", broken)
    capfd.readouterr()
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replies"] == []
    assert body["login_needed"] is False
    assert FAILED not in resp.text
    lines = [line for line in capfd.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    assert MAMA not in lines[0]
