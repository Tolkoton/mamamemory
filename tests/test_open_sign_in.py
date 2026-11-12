"""Contract tests of the slice open-sign-in: any Google account signs in, each works only with its own data.

Written by the slice tester from the sealed contract `.engine/slices/open-sign-in.md` and the public
signatures only, without the code. Seam 1 (a foreign account), I1 (no valid session, nothing), I2 (A's
session never reads or writes B's documents), the session check without a list, and the end of `NotAllowed`.
The store records every document path it is asked for (through the public `document_path`), so a read
and a write of another account are both visible.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access, errors, planning
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Decide, InMemoryStore, document_path
from tests.test_one_task_planning import NOW, TITLE, WRITTEN, FakeAI, FakeCalendar

KEY = "session-key-for-tests"
WEEK_S = 7 * 24 * 3600
SUB_A = "1000000000000000001"
SUB_B = "1000000000000000002"
MAMA = "mama@example.com"
STRANGER = "stranger.person@gmail.com"
B_TITLE = "купити хліб"
FORBIDDEN_TEXT = "Цей акаунт не має доступу."
TASK_TEXT = "у четвер подзвонити нотаріусу"


def make_config() -> Config:
    return Config(
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id="client-id.apps.googleusercontent.com",
        oauth_client_secret="client-secret",
        session_key=KEY,
        session_max_age_s=WEEK_S,
        login_max_age_s=600,
        base_url="https://testserver",
        request_timeout_s=30,
        call_timeout_s=10,
    )


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
        return Claims(sub=SUB_A, email=MAMA, email_verified=True)

    def refresh(self, tokens: Tokens) -> Credentials:
        return Credentials("fresh-at")


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


class Two:
    """One app, one store, a calendar per account (chosen by the session's account_id), many browsers."""

    def __init__(self, subs: tuple[str, ...] = (SUB_A, SUB_B)) -> None:
        self.config = make_config()
        self.store = RecordingStore()
        for sub in subs:
            InMemoryStore.set(
                self.store,
                sub,
                access.TOKENS_PATH,
                access.tokens_document(
                    Tokens(
                        access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)
                    ),
                    NOW,
                ),
            )
        self.calendars: dict[str, FakeCalendar] = {sub: FakeCalendar() for sub in subs}
        self.built_for: list[str] = []
        self.ai = FakeAI(duration_min=30)
        self.clock = Clock(NOW)

        def calendar(session: Any, started: datetime) -> GoogleWork:
            self.built_for.append(session.account_id)
            return cast(GoogleWork, self.calendars[session.account_id])

        self.app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=calendar,
        )

    def browser(self, sub: str | None = None, email: str = MAMA, at: datetime = NOW) -> TestClient:
        client = TestClient(
            self.app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        if sub is not None:
            client.cookies.set("mm_session", access.session_cookie_value(sub, email, at, key=KEY))
        return client

    def start(self, sub: str, text: str = TASK_TEXT) -> dict[str, Any]:
        """A new task of `sub` straight through `planning.start` (as the S3 tests do): its reply as JSON."""
        reply = planning.start(
            Session(account_id=sub, google_credentials=lambda: Credentials("at-test")),
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendars[sub]),
            store=self.store,
            now=NOW,
            config=self.config,
        )
        plan = reply.plan
        question = reply.question
        return {
            "plan": None
            if plan is None
            else {"plan_id": plan.plan_id, "title": plan.title, "fingerprint": plan.fingerprint},
            "question": None
            if question is None
            else {"kind": question.kind, "id": question.id, "fingerprint": question.fingerprint},
        }

    def paths_since(self, mark: int) -> list[tuple[str, str]]:
        return self.store.touched[mark:]


def under(sub: str, touched: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The touched paths that are NOT under `accounts/{sub}/` (nor the account document itself)."""
    return [(op, p) for op, p in touched if not (p == f"accounts/{sub}" or p.startswith(f"accounts/{sub}/"))]


def message(client: TestClient, text: str, reply_to: Any = None) -> Any:
    return client.post("/api/message", json={"text": text, "reply_to": reply_to})


def confirm(client: TestClient, plan_id: Any, fingerprint: Any) -> Any:
    return client.post("/api/plan/confirm", json={"plan_id": plan_id, "fingerprint": fingerprint})


# ------------------------------------------------------------------ the session check without a list


def test_session_cookie_of_any_account_gives_its_claims_without_an_allowed_list() -> None:
    for sub, email in [(SUB_A, MAMA), (SUB_B, STRANGER), ("3", "someone@other.example")]:
        value = access.session_cookie_value(sub, email, NOW, key=KEY)
        claims = access.verify_session_cookie(value, NOW + timedelta(hours=1), key=KEY, max_age_s=WEEK_S)
        assert claims.sub == sub
        assert claims.email == email


def test_not_allowed_text_and_403_are_gone_any_account_gets_the_shell() -> None:
    assert not hasattr(errors, "NotAllowed")
    two = Two()
    mama = two.browser(SUB_A, MAMA).get("/")
    assert mama.status_code == 200
    shell = mama.text
    assert shell.strip()
    stranger = two.browser(SUB_B, STRANGER).get("/")
    assert stranger.status_code == 200
    assert stranger.text == shell
    assert FORBIDDEN_TEXT not in stranger.text
    reply = message(two.browser(SUB_B, STRANGER), TASK_TEXT)
    assert reply.status_code == 200, reply.text
    assert FORBIDDEN_TEXT not in reply.text


# ------------------------------------------------------------------ Seam 1: a foreign account


def test_seam1_account_b_with_plan_id_of_a_writes_nothing_and_leaves_a_draft_intact() -> None:
    two = Two()
    a = two.browser(SUB_A, MAMA)
    b = two.browser(SUB_B, STRANGER)

    mark = len(two.store.touched)
    shown = two.start(SUB_A)
    plan = shown["plan"]
    assert plan is not None and plan["title"] == TITLE
    question = shown["question"]
    assert under(SUB_A, two.paths_since(mark)) == [], "A's documents lie only under accounts/A/"

    two.ai.task["title"] = B_TITLE
    mark = len(two.store.touched)
    for resp in [
        confirm(b, plan["plan_id"], plan["fingerprint"]),
        message(b, "так", question),
    ]:
        assert TITLE not in resp.text
    assert under(SUB_B, two.paths_since(mark)) == [], "B's requests touched a document outside accounts/B/"
    assert two.calendars[SUB_A].created == []
    assert two.calendars[SUB_B].created == []
    assert SUB_A not in two.built_for

    # A's draft is unchanged: A's own "yes" writes it, exactly once.
    mark = len(two.store.touched)
    done = confirm(a, plan["plan_id"], plan["fingerprint"])
    assert done.status_code == 200, done.text
    assert done.json()["text"] == WRITTEN
    assert [e.title for e in two.calendars[SUB_A].created] == [TITLE]
    assert two.calendars[SUB_B].created == []
    assert under(SUB_A, two.paths_since(mark)) == []


# ------------------------------------------------------------------ I1: no valid session, no content


def test_I1_request_without_a_valid_session_gets_no_shell_and_no_account_data() -> None:
    two = Two()
    a = two.browser(SUB_A, MAMA)
    shown = two.start(SUB_A)
    plan, question = shown["plan"], shown["question"]
    assert plan is not None and plan["title"] == TITLE

    # Anchors: a session of any account is valid at exactly SESSION_MAX_AGE_S and gets the shell.
    edge = two.browser(SUB_B, STRANGER, at=NOW - timedelta(seconds=WEEK_S)).get("/")
    assert edge.status_code == 200
    shell = edge.text
    assert shell.strip()

    good = access.session_cookie_value(SUB_A, MAMA, NOW, key=KEY)
    payload, _ = good.rsplit(".", 1)
    _, other_signature = access.session_cookie_value(SUB_B, STRANGER, NOW, key=KEY).rsplit(".", 1)
    refused: list[tuple[str, str | None]] = [
        ("no cookie", None),
        ("empty cookie", ""),
        ("not a signed value", "garbage"),
        ("forged: A's payload with B's signature", f"{payload}.{other_signature}"),
        ("signed with another key", access.session_cookie_value(SUB_A, MAMA, NOW, key="another-key")),
        (
            "expired by one second",
            access.session_cookie_value(SUB_A, MAMA, NOW - timedelta(seconds=WEEK_S + 1), key=KEY),
        ),
        ("mm_login value as mm_session", access.login_cookie_value("s1", "v" * 43, NOW, key=KEY)),
    ]
    for label, value in refused:
        client = two.browser()
        if value is not None:
            client.cookies.set("mm_session", value)
        for path in ["/", "/index.html", "/static/index.html", "/anything", "/api/plan"]:
            resp = client.get(path)
            assert shell not in resp.text, f"{label}: GET {path} carried the shell"
            assert TITLE not in resp.text, f"{label}: GET {path} carried A's data"
        assert client.get("/").status_code != 200, label
        for resp in [
            message(client, "що в мене заплановано?", question),
            message(client, "так", question),
            confirm(client, plan["plan_id"], plan["fingerprint"]),
        ]:
            assert resp.status_code != 200, (label, resp.status_code)
            assert shell not in resp.text, label
            assert TITLE not in resp.text, label
    assert two.calendars[SUB_A].created == []
    assert two.calendars[SUB_B].created == []

    # A lawful request after the refused ones: A's own "yes" still writes A's plan once.
    done = confirm(a, plan["plan_id"], plan["fingerprint"])
    assert done.json()["text"] == WRITTEN
    assert [e.title for e in two.calendars[SUB_A].created] == [TITLE]


# ------------------------------------------------------------------ I2: each account only its own documents


def test_I2_session_of_one_account_never_reads_or_writes_a_document_of_another() -> None:
    pairs = [
        ((SUB_A, MAMA), (SUB_B, STRANGER)),
        ((SUB_A, MAMA), (SUB_A + "0", STRANGER)),  # one sub is a prefix of the other
        ((SUB_A, MAMA), (SUB_B, MAMA)),  # the same email under two different subs
    ]
    for (sub_a, email_a), (sub_b, email_b) in pairs:
        two = Two((sub_a, sub_b))
        two.ai.task["title"] = TITLE
        a = two.browser(sub_a, email_a)
        b = two.browser(sub_b, email_b)
        case = (sub_a, email_a, sub_b, email_b)

        # A asks a task without a duration: A's open question.
        two.ai.task["duration_min"] = None
        mark = len(two.store.touched)
        asked = two.start(sub_a)
        duration_question = asked["question"]
        assert duration_question is not None and duration_question["kind"] == "duration", case
        assert under(sub_a, two.paths_since(mark)) == [], case

        # B answers A's question, and says "yes" to plan ids that are not B's.
        two.ai.task["title"] = B_TITLE
        mark = len(two.store.touched)
        foreign = [
            message(b, "пів години", duration_question),
            confirm(b, duration_question["id"], None),
            confirm(b, "p1", "f1"),
            confirm(b, "", ""),
        ]
        for resp in foreign:
            assert TITLE not in resp.text, case
        assert under(sub_b, two.paths_since(mark)) == [], case

        # A answers its own question: A's plan.
        two.ai.task["title"] = TITLE
        mark = len(two.store.touched)
        planned = message(a, "пів години", duration_question).json()
        plan = planned["plan"]
        assert plan is not None and plan["title"] == TITLE, case
        assert under(sub_a, two.paths_since(mark)) == [], case

        # B with A's plan id and fingerprint, by the confirm route and by "yes" as a reply.
        two.ai.task["title"] = B_TITLE
        mark = len(two.store.touched)
        foreign = [
            confirm(b, plan["plan_id"], plan["fingerprint"]),
            message(b, "так", planned["question"]),
            message(b, "пів години", duration_question),
        ]
        for resp in foreign:
            assert TITLE not in resp.text, case
        assert under(sub_b, two.paths_since(mark)) == [], case
        assert two.calendars[sub_a].created == [], case
        assert two.calendars[sub_b].created == [], case

        # A lawful operation of B after the refused ones: B's own task goes into B's calendar only.
        two.ai.task["duration_min"] = 30
        mark = len(two.store.touched)
        own = two.start(sub_b, "купити хліб")["plan"]
        assert own is not None and own["title"] == B_TITLE, case
        written = confirm(b, own["plan_id"], own["fingerprint"])
        assert written.json()["text"] == WRITTEN, case
        assert under(sub_b, two.paths_since(mark)) == [], case
        assert [e.title for e in two.calendars[sub_b].created] == [B_TITLE], case
        assert two.calendars[sub_a].created == [], case

        # And A's plan is still A's: A's "yes" writes it into A's calendar, once.
        mark = len(two.store.touched)
        done = confirm(a, plan["plan_id"], plan["fingerprint"])
        assert done.json()["text"] == WRITTEN, case
        assert under(sub_a, two.paths_since(mark)) == [], case
        assert [e.title for e in two.calendars[sub_a].created] == [TITLE], case
        assert [e.title for e in two.calendars[sub_b].created] == [B_TITLE], case
