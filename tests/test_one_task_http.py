"""Contract tests of the S3 routes `/api/*` and the S1 error boundary (slice one-task-to-calendar, Seam 5).

Written by the slice tester from the sealed contract `.engine/slices/one-task-to-calendar.md`,
without the code.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from mamamemory import access, planning
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from tests.test_one_task_google_work import Transport
from tests.test_one_task_planning import NOW, TITLE, FakeAI, FakeCalendar, instant, make_config

MAMA = "mama@example.com"
SUB = "1000000000000000001"
WEEK_S = 7 * 24 * 3600
FAILED = "Не вдалося, спробуйте ще раз."


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class FakeGoogle:
    def authorization_url(self) -> tuple[str, str, str]:
        return "https://accounts.google.com/o/oauth2/auth?state=s1", "s1", "v" * 43

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        return Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES))

    def verify_id_token(self, token: str) -> Claims:
        return Claims(sub=SUB, email=MAMA, email_verified=True)

    def refresh(self, tokens: Tokens) -> Credentials:
        return Credentials("fresh-at")


class App:
    def __init__(self, calendar: Any | None = None) -> None:
        self.config: Config = make_config()
        self.store = InMemoryStore()
        self.store.set(
            SUB,
            access.TOKENS_PATH,
            access.tokens_document(
                Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
                NOW,
            ),
        )
        self.clock = Clock(NOW)
        self.ai = FakeAI(duration_min=None)
        self.calendar = calendar if calendar is not None else FakeCalendar()
        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )

    def sign_in(self, at: datetime = NOW) -> None:
        self.client.cookies.set(
            "mm_session", access.session_cookie_value(SUB, MAMA, at, key=self.config.session_key)
        )

    def session(self) -> Session:
        return Session(account_id=SUB, google_credentials=lambda: Credentials("at-test"))

    def start(self, calendar: FakeCalendar, *, duration_min: int | None) -> Any:
        self.ai.task["duration_min"] = duration_min
        return planning.start(
            self.session(),
            "у четвер подзвонити нотаріусу",
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, calendar),
            store=self.store,
            now=NOW,
            config=self.config,
        )


# ------------------------------------------------------------------ the error boundary (Seam 5)


def test_api_without_valid_session_is_401_without_location() -> None:
    app = App()
    calls = [
        ("/api/message", {"text": "у четвер подзвонити нотаріусу", "reply_to": None}),
        ("/api/plan/confirm", {"plan_id": "p1", "fingerprint": "f1"}),
    ]
    for url, body in calls:
        # NotSignedIn: no cookie at all.
        app.client.cookies.clear()
        resp = app.client.post(url, json=body)
        assert resp.status_code == 401, (url, resp.status_code)
        assert "location" not in resp.headers, url
        # LoginExpired: a session cookie older than its max age.
        app.sign_in(at=NOW - timedelta(seconds=WEEK_S + 60))
        resp = app.client.post(url, json=body)
        assert resp.status_code == 401, (url, resp.status_code)
        assert "location" not in resp.headers, url


def test_root_and_auth_keep_s1_redirects() -> None:
    app = App()
    root = app.client.get("/")
    assert root.status_code == 302
    login = app.client.get("/auth/login")
    assert login.status_code == 302
    assert login.headers["location"].startswith("https://accounts.google.com/")


# ------------------------------------------------------------------ the routes


def test_message_with_reply_to_duration_returns_reply_with_plan() -> None:
    app = App()
    app.sign_in()
    question = app.start(app.calendar, duration_min=None).question
    assert question is not None
    resp = app.client.post(
        "/api/message",
        json={"text": "пів години", "reply_to": {"kind": "duration", "id": question.id, "fingerprint": None}},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()
    assert set(reply) >= {"text", "question", "plan"}
    plan = reply["plan"]
    assert set(plan) >= {"plan_id", "title", "start", "end", "fingerprint"}
    assert plan["title"] == TITLE
    assert instant(plan["start"]) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert instant(plan["end"]) == datetime(2026, 11, 9, 9, 45, tzinfo=UTC)
    assert reply["question"] == {"kind": "plan", "id": plan["plan_id"], "fingerprint": plan["fingerprint"]}


def test_confirm_route_writes_event_and_says_so() -> None:
    app = App()
    app.sign_in()
    shown = app.start(app.calendar, duration_min=30).plan
    assert shown is not None
    resp = app.client.post(
        "/api/plan/confirm", json={"plan_id": shown.plan_id, "fingerprint": shown.fingerprint}
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()
    assert reply["text"] == "Записала в календар."
    assert reply["plan"] is None
    assert len(app.calendar.created) == 1


def test_calendar_error_gives_failed_reply_and_plan_unchanged() -> None:
    # The real GoogleWork; every call to Google answers 500.
    transport = Transport(lambda r: (500, {"error": {"code": 500, "message": "Backend Error"}}))
    authorized = AuthorizedSession(Credentials("at-test"))
    authorized.mount("https://www.googleapis.com/", transport)
    failing = GoogleWork(authorized, call_timeout_s=10, deadline=NOW + timedelta(seconds=60), now=lambda: NOW)
    app = App(calendar=failing)
    app.sign_in()
    working = FakeCalendar()
    shown = app.start(working, duration_min=30).plan
    assert shown is not None
    resp = app.client.post(
        "/api/plan/confirm", json={"plan_id": shown.plan_id, "fingerprint": shown.fingerprint}
    )
    reply = resp.json()
    assert reply["text"] == FAILED
    assert reply["question"] is None
    assert working.created == []
    assert len(transport.sent) >= 1, "the failure came from Google, not from before it"
    # The plan is unchanged: the same "yes" against a working calendar writes it.
    later = planning.confirm(
        app.session(),
        shown.plan_id,
        shown.fingerprint,
        calendar=cast(GoogleWork, working),
        store=app.store,
        now=NOW + timedelta(seconds=45),
        config=app.config,
    )
    assert later.text == "Записала в календар."
    assert len(working.created) == 1
