"""Integration tests of the slice open-sign-in: two accounts on one store, real sign-in to every `/api/*`.

Written by the slice tester (mode block) from the sealed contract `.engine/slices/open-sign-in.md`
and the public signatures, without the code. The slice stands alone as one block; its acceptance
criterion crosses into the sealed slices it changes: the session made by `/auth/callback` (S1) is
the only source of `account_id` for `/api/transcribe` (S2), `/api/message` and `/api/plan/confirm`
(S3), and for the Google credentials the calendar is built from. Unlike the contract tests, the
sessions here are not hand-made cookies: each browser signs in through `/auth/login` and
`/auth/callback`.
"""

from datetime import UTC, datetime
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import planning
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Decide, InMemoryStore, document_path
from tests.test_one_task_planning import NOW, TITLE, WRITTEN, FakeAI, FakeCalendar, make_config
from tests.test_voice_speech import SAID, Gemini

SUB_A = "1000000000000000001"
SUB_B = "2000000000000000002"
MAMA = "mama@example.com"
STRANGER = "stranger.person@gmail.com"
B_TITLE = "купити хліб"
NOT_ACTUAL = "Це питання вже не актуальне."


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class FakeGoogle:
    """Google for two people: the code decides whose tokens and whose ID token come back."""

    def __init__(self) -> None:
        self.people = {
            "code-A": Claims(sub=SUB_A, email=MAMA, email_verified=True),
            "code-B": Claims(sub=SUB_B, email=STRANGER, email_verified=False),
        }
        self.issued: dict[str, str] = {}
        self.refreshed: list[str] = []

    def authorization_url(self) -> tuple[str, str, str]:
        n = len(self.issued) + 1
        state, verifier = f"state-{n}", f"verifier-{n}-" + "v" * 43
        self.issued[state] = verifier
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state, verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        if code_verifier not in self.issued.values():
            raise RuntimeError("fake: exchange without the issued code_verifier")
        who = code.removeprefix("code-")
        return Tokens(
            access_token=f"at-{who}",
            refresh_token=f"rt-{who}",
            id_token=f"idt-{who}",
            scopes=frozenset(SCOPES),
        )

    def verify_id_token(self, token: str) -> Claims:
        return self.people["code-" + token.removeprefix("idt-")]

    def refresh(self, tokens: Tokens) -> Credentials:
        self.refreshed.append(tokens.refresh_token)
        return Credentials(f"fresh-{tokens.refresh_token}")


class RecordingStore(InMemoryStore):
    """The in-memory store that remembers the full path of every get, set and transact."""

    def __init__(self) -> None:
        super().__init__()
        self.touched: list[tuple[str, str]] = []

    def get(self, account_id: str, path: str) -> dict[str, Any] | None:
        self.touched.append(("get", document_path(account_id, path)))
        return super().get(account_id, path)

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self.touched.append(("set", document_path(account_id, path)))
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        self.touched.append(("transact", document_path(account_id, path)))
        return super().transact(account_id, path, decide)


def outside(sub: str, touched: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The touched paths that are NOT under `accounts/{sub}/` (nor the account document itself)."""
    return [(op, p) for op, p in touched if not (p == f"accounts/{sub}" or p.startswith(f"accounts/{sub}/"))]


class Pair:
    """One app, one store, one Google, a calendar per account; each browser signs in for real."""

    def __init__(self, *, ai: Any = None, clock: Any = None, config: Config | None = None) -> None:
        self.config = config or make_config()
        self.store = RecordingStore()
        self.google = FakeGoogle()
        self.calendars = {SUB_A: FakeCalendar(), SUB_B: FakeCalendar()}
        self.built: list[tuple[str, str]] = []
        self.ai = ai if ai is not None else FakeAI(duration_min=30)

        def calendar(session: Session, started: datetime) -> GoogleWork:
            # The calendar of the request is built from the session's own Google credentials.
            self.built.append((session.account_id, str(session.google_credentials().token)))
            return cast(GoogleWork, self.calendars[session.account_id])

        self.app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, self.google),
            clock or Clock(NOW),
            ai=cast(AI, self.ai),
            calendar=calendar,
        )

    def sign_in(self, who: str) -> TestClient:
        client = TestClient(
            self.app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        login = client.get("/auth/login")
        assert login.status_code == 302, login.text
        state = sorted(self.google.issued)[-1]
        done = client.get("/auth/callback", params={"code": f"code-{who}", "state": state})
        assert done.status_code == 302, (who, done.status_code, done.text)
        assert httpx.URL(done.headers["location"]).path == "/", who
        assert client.cookies.get("mm_session"), f"{who}: the callback set no session"
        return client

    def start(self, sub: str, title: str, *, duration_min: int | None) -> dict[str, Any]:
        """A new task of `sub` through `planning.start`, as the S3 tests do: its reply as JSON."""
        self.ai.task["title"] = title
        self.ai.task["duration_min"] = duration_min
        reply = planning.start(
            Session(account_id=sub, google_credentials=lambda: Credentials("at-test")),
            "задача",
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendars[sub]),
            store=self.store,
            now=NOW,
            config=self.config,
        )
        plan, question = reply.plan, reply.question
        return {
            "plan": None if plan is None else {"plan_id": plan.plan_id, "fingerprint": plan.fingerprint},
            "question": None
            if question is None
            else {"kind": question.kind, "id": question.id, "fingerprint": question.fingerprint},
        }


def confirm(client: TestClient, plan: dict[str, Any]) -> Any:
    return client.post(
        "/api/plan/confirm", json={"plan_id": plan["plan_id"], "fingerprint": plan["fingerprint"]}
    )


# ------------------------------------------------------------------ the acceptance criterion, end to end


def test_two_accounts_signed_in_through_google_each_sees_and_writes_only_its_own_plan() -> None:
    pair = Pair()
    a = pair.sign_in("A")
    b = pair.sign_in("B")  # email_verified=false, an email no list ever named

    # Each sign-in left its tokens under its own sub, and both get the shell.
    assert pair.store.get(SUB_A, "private/google") is not None
    assert pair.store.get(SUB_B, "private/google") is not None
    assert a.get("/").status_code == 200
    assert b.get("/").status_code == 200

    shown = pair.start(SUB_A, TITLE, duration_min=30)
    plan, question = shown["plan"], shown["question"]
    assert plan is not None and question is not None

    # B, signed in through Google, says "yes" to A's plan by the button and by a reply.
    mark = len(pair.store.touched)
    for resp in [
        confirm(b, plan),
        b.post("/api/message", json={"text": "так", "reply_to": question}),
    ]:
        assert TITLE not in resp.text
    assert outside(SUB_B, pair.store.touched[mark:]) == [], (
        "B's requests touched a document outside accounts/B/"
    )
    assert pair.calendars[SUB_A].created == []
    assert pair.calendars[SUB_B].created == []
    assert all(account == SUB_B for account, _ in pair.built), pair.built

    # A, signed in through Google, writes A's plan into A's calendar, built from A's own tokens.
    pair.built.clear()
    mark = len(pair.store.touched)
    done = confirm(a, plan)
    assert done.status_code == 200, done.text
    assert done.json()["text"] == WRITTEN
    assert [e.title for e in pair.calendars[SUB_A].created] == [TITLE]
    assert pair.calendars[SUB_B].created == []
    assert outside(SUB_A, pair.store.touched[mark:]) == []
    assert pair.built and all(built == (SUB_A, "fresh-rt-A") for built in pair.built), pair.built
    assert "rt-B" not in pair.google.refreshed[-len(pair.built) :]


# ------------------------------------------------------------------ the drafts of two accounts do not meet


def test_a_new_task_of_one_account_leaves_the_open_question_of_the_other_actual() -> None:
    pair = Pair()
    a = pair.sign_in("A")
    b = pair.sign_in("B")

    asked_b = pair.start(SUB_B, B_TITLE, duration_min=None)["question"]
    assert asked_b is not None and asked_b["kind"] == "duration"
    # A starts a task later: in a shared draft this would make B's question not the current one.
    asked_a = pair.start(SUB_A, TITLE, duration_min=None)["question"]
    assert asked_a is not None and asked_a["kind"] == "duration"

    pair.ai.task["title"] = B_TITLE
    mark = len(pair.store.touched)
    reply_b = b.post("/api/message", json={"text": "пів години", "reply_to": asked_b})
    assert reply_b.status_code == 200, reply_b.text
    assert reply_b.json()["text"] != NOT_ACTUAL
    assert reply_b.json()["plan"] is not None
    assert reply_b.json()["plan"]["title"] == B_TITLE
    assert outside(SUB_B, pair.store.touched[mark:]) == []

    pair.ai.task["title"] = TITLE
    mark = len(pair.store.touched)
    reply_a = a.post("/api/message", json={"text": "пів години", "reply_to": asked_a})
    assert reply_a.status_code == 200, reply_a.text
    assert reply_a.json()["text"] != NOT_ACTUAL
    assert reply_a.json()["plan"] is not None
    assert reply_a.json()["plan"]["title"] == TITLE
    assert outside(SUB_A, pair.store.touched[mark:]) == []

    # Each "yes" goes into its own calendar only.
    assert confirm(b, reply_b.json()["plan"]).json()["text"] == WRITTEN
    assert confirm(a, reply_a.json()["plan"]).json()["text"] == WRITTEN
    assert [e.title for e in pair.calendars[SUB_B].created] == [B_TITLE]
    assert [e.title for e in pair.calendars[SUB_A].created] == [TITLE]


# ------------------------------------------------------------------ S2: the voice route under a new account


def test_transcribe_of_a_new_account_answers_and_touches_no_document_of_another() -> None:
    config = make_config()
    gemini = Gemini(SAID)
    client = gemini.client()
    # `speech` compares its deadline with the wall clock, so this app reads the real time.
    pair = Pair(ai=AI(lambda: client, config), clock=lambda: datetime.now(UTC), config=config)
    a_draft = FakeAI(duration_min=None)
    planning.start(
        Session(account_id=SUB_A, google_credentials=lambda: Credentials("at-test")),
        "задача",
        ai=cast(AI, a_draft),
        calendar=cast(GoogleWork, pair.calendars[SUB_A]),
        store=pair.store,
        now=NOW,
        config=config,
    )
    b = pair.sign_in("B")

    mark = len(pair.store.touched)
    resp = b.post("/api/transcribe", content=b"OggS fake opus", headers={"content-type": "audio/ogg"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"text": SAID}
    assert outside(SUB_B, pair.store.touched[mark:]) == [], (
        "B's voice request touched a document outside accounts/B/"
    )
    assert TITLE not in resp.text
