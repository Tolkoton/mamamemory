"""Integration tests of the feature f1-skeleton (block f1-skeleton, closed with S5 skeleton-measure).

Written by the slice tester (mode block) from the feature artifact
`.engine/architecture/feature/f1-skeleton.md`
and the public signatures, without the code. One test per line of «Inter-slice contracts» (S1 -> S3, S1 -> S2,
S2 -> S3, S3 -> S4, S2/S3/S4 -> S5) and one per acceptance criterion AC1-AC5. The app is the one `create_app`
builds, with fakes at its edges only: Google sign-in (two people), a calendar per account, the parse model
(`FakeAI`) and the Vertex endpoint behind a real `google-genai` client for the voice. Every browser signs in
through `/auth/login` and `/auth/callback` (S1), never with a hand-made cookie.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import assistant
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.errors import LoginExpired
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from tests.f1_measure_sources import REVISION, report_text
from tests.test_one_task_planning import NOW, TITLE, WRITTEN, FakeAI, FakeCalendar, instant, make_config
from tests.test_open_sign_in_integration import RecordingStore, outside
from tests.test_voice_speech import Gemini

SUB_A = "1000000000000000001"
SUB_B = "2000000000000000002"
MAMA = "mama@example.com"
STRANGER = "stranger.person@gmail.com"
ASK_DURATION = f"Скільки часу займе «{TITLE}»?"
SIGN_IN_AGAIN = "Щоб показати план, увійди знову."
TRACER = "у четвер о десятій на пів години подзвонити нотаріусу"
NO_LENGTH = "у четвер о десятій подзвонити нотаріусу"
HALF_HOUR = "пів години"
SONKO_DEPLOY = Path.home() / "sonko" / "done" / "2026-11-11-mamamemory-f5-deploy.md"
BASE32HEX = re.compile(r"[0-9a-v]+")


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class TwoPeople:
    """Google sign-in for two people; `expired` holds the subs whose refresh token Google no longer takes."""

    def __init__(self) -> None:
        self.people = {
            "A": Claims(sub=SUB_A, email=MAMA, email_verified=True),
            "B": Claims(sub=SUB_B, email=STRANGER, email_verified=False),
        }
        self.issued: dict[str, str] = {}
        self.expired: set[str] = set()
        self.refreshed: list[str] = []

    def authorization_url(self) -> tuple[str, str, str]:
        n = len(self.issued) + 1
        state, verifier = f"state-{n}", f"verifier-{n}-" + "v" * 43
        self.issued[state] = verifier
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state, verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        assert code_verifier in self.issued.values(), "exchange without the issued code_verifier"
        who = code.removeprefix("code-")
        return Tokens(
            access_token=f"at-{who}",
            refresh_token=f"rt-{who}",
            id_token=f"idt-{who}",
            scopes=frozenset(SCOPES),
        )

    def verify_id_token(self, token: str) -> Claims:
        return self.people[token.removeprefix("idt-")]

    def refresh(self, tokens: Tokens) -> Credentials:
        who = tokens.refresh_token.removeprefix("rt-")
        if self.people[who].sub in self.expired:
            raise LoginExpired("fake: the weekly sign-in has run out")
        self.refreshed.append(tokens.refresh_token)
        return Credentials(f"fresh-{tokens.refresh_token}")


class VoiceAI(FakeAI):
    """`FakeAI` for the text models (route answers `self.intent`); a real `google-genai` client for voice."""

    def __init__(self, gemini: Gemini, *, duration_min: int | None) -> None:
        super().__init__(duration_min=duration_min)
        self.gemini = gemini
        self.intent = "new_task"
        self.prompts: list[tuple[str, str]] = []
        self._client: Any = None

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append((task_type, prompt))
        if task_type == "route":
            self.calls.append(task_type)
            return {"intent": self.intent}
        return super().generate_json(task_type, prompt, schema)

    def client(self) -> Any:
        if self._client is None:
            self._client = self.gemini.client()
        return self._client


class F1App:
    """The whole skeleton as deployed, fakes at its edges; each browser signs in through Google (S1)."""

    def __init__(self, *heard: str, duration_min: int | None = 30, clock: Clock | None = None) -> None:
        self.config: Config = make_config()
        self.store = RecordingStore()
        self.google = TwoPeople()
        self.gemini = Gemini(*heard)
        self.ai = VoiceAI(self.gemini, duration_min=duration_min)
        self.calendars = {SUB_A: FakeCalendar(), SUB_B: FakeCalendar()}
        self.built: list[tuple[str, str]] = []
        self.clock = clock or Clock(NOW)

        def calendar(session: Session, started: datetime) -> GoogleWork:
            self.built.append((session.account_id, str(session.google_credentials().token)))
            return cast(GoogleWork, self.calendars[session.account_id])

        self.app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, self.google),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=calendar,
        )

    def browser(self) -> TestClient:
        return TestClient(
            self.app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )

    def sign_in(self, who: str) -> TestClient:
        client = self.browser()
        login = client.get("/auth/login")
        assert login.status_code == 302, login.text
        state = sorted(self.google.issued)[-1]
        done = client.get("/auth/callback", params={"code": f"code-{who}", "state": state})
        assert done.status_code == 302, (who, done.status_code, done.text)
        assert client.cookies.get("mm_session"), f"{who}: the callback set no session"
        return client

    def guide_seen(self, sub: str) -> None:
        """The F5 guide was already shown, so `/api/open` holds only the open questions of F1."""
        self.store.set(sub, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})

    def tick(self, minutes: int = 1) -> None:
        self.clock.at = self.clock.at + timedelta(minutes=minutes)

    def message(self, client: TestClient, text: str, reply_to: Any = None, message_id: str = "m") -> Any:
        self.tick()
        resp = client.post(
            "/api/message", json={"text": text, "reply_to": reply_to, "message_id": message_id}
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)
        return resp.json()

    def transcribe(self, client: TestClient) -> httpx.Response:
        """`speech` holds its deadline against the wall clock: the voice request runs at the real time."""
        planning_time = self.clock.at
        self.clock.at = datetime.now(UTC)
        try:
            resp: httpx.Response = client.post(
                "/api/transcribe", content=b"OggS fake opus", headers={"content-type": "audio/ogg"}
            )
        finally:
            self.clock.at = planning_time
        return resp

    def open(self, client: TestClient) -> Any:
        self.tick()
        resp = client.get("/api/open")
        assert resp.status_code == 200, (resp.status_code, resp.text)
        return resp.json()


def confirm(client: TestClient, plan: dict[str, Any]) -> httpx.Response:
    resp: httpx.Response = client.post(
        "/api/plan/confirm", json={"plan_id": plan["plan_id"], "fingerprint": plan["fingerprint"]}
    )
    return resp


def plan_question(plan: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "plan", "id": plan["plan_id"], "fingerprint": plan["fingerprint"]}


# ------------------------------------------------------------------ the inter-slice contracts


def test_S1_to_S3_session_gives_the_plan_its_account_its_own_google_credentials_and_its_store() -> None:
    f1 = F1App()
    a = f1.sign_in("A")

    mark = len(f1.store.touched)
    shown = f1.message(a, TRACER)
    plan = shown["plan"]
    assert plan is not None and plan["title"] == TITLE, shown
    done = confirm(a, plan)
    assert done.status_code == 200, done.text
    assert done.json()["text"] == WRITTEN
    assert [e.title for e in f1.calendars[SUB_A].created] == [TITLE]

    # The calendar of every request is built from the session's account and that account's own tokens.
    assert f1.built and all(built == (SUB_A, "fresh-rt-A") for built in f1.built), f1.built
    # The plan's documents live under the account; S3 writes through `store.transact`.
    touched = f1.store.touched[mark:]
    assert outside(SUB_A, touched) == [], touched
    assert any(op == "transact" for op, _ in touched), touched

    # The weekly Google sign-in runs out: `google_credentials` raises LoginExpired, nothing is written.
    again = f1.message(a, TRACER, message_id="m2")["plan"]
    assert again is not None
    f1.google.expired.add(SUB_A)
    refused = confirm(a, again)
    assert refused.status_code == 401, (refused.status_code, refused.text)
    assert "location" not in refused.headers
    assert len(f1.calendars[SUB_A].created) == 1


def test_S1_to_S2_voice_request_one_is_under_the_same_sign_in_check() -> None:
    f1 = F1App("Подзвонити нотаріусу", clock=Clock(datetime.now(UTC)))
    stranger = f1.browser()
    resp = stranger.post("/api/transcribe", content=b"OggS fake opus", headers={"content-type": "audio/ogg"})
    assert resp.status_code == 401, resp.status_code
    assert "location" not in resp.headers
    stranger.cookies.set("mm_session", "forged.value.signature")
    resp = stranger.post("/api/transcribe", content=b"OggS fake opus", headers={"content-type": "audio/ogg"})
    assert resp.status_code == 401, resp.status_code
    assert f1.gemini.requests == [], "the model was called without a valid session"

    a = f1.sign_in("A")
    f1.clock.at = datetime.now(UTC) + timedelta(seconds=f1.config.session_max_age_s + 60)
    old = a.post("/api/transcribe", content=b"OggS fake opus", headers={"content-type": "audio/ogg"})
    assert old.status_code == 401, "a session older than its max age is refused on request 1 too"
    assert "location" not in old.headers
    assert f1.gemini.requests == []

    f1.clock.at = datetime.now(UTC)
    heard = f1.transcribe(a)
    assert heard.status_code == 200, heard.text
    assert heard.json() == {"text": "Подзвонити нотаріусу"}
    assert len(f1.gemini.requests) == 1


def test_S2_to_S3_recognised_text_goes_as_request_two_with_its_reply_to() -> None:
    f1 = F1App(NO_LENGTH, HALF_HOUR, duration_min=None)
    a = f1.sign_in("A")

    first = f1.transcribe(a)
    assert first.status_code == 200, first.text
    text = first.json()["text"]
    assert isinstance(text, str) and text == NO_LENGTH

    asked = f1.message(a, text, None, "m1")
    parsed = [prompt for kind, prompt in f1.ai.prompts if kind == "parse_task"]
    assert parsed and NO_LENGTH in parsed[-1], "the recognised text did not reach the task parse"
    question = asked["question"]
    assert question is not None and question["kind"] == "duration", asked
    assert asked["plan"] is None

    second = f1.transcribe(a)
    assert second.status_code == 200, second.text
    answer = second.json()["text"]
    assert answer == HALF_HOUR
    planned = f1.message(a, answer, question, "m2")
    assert any(kind == "parse_duration" and HALF_HOUR in prompt for kind, prompt in f1.ai.prompts), (
        "the recognised answer was not read as the answer to its question"
    )
    plan = planned["plan"]
    assert plan is not None and plan["title"] == TITLE, planned
    assert planned["question"] == plan_question(plan)


def test_S3_to_S4_open_question_is_built_from_the_plan_draft() -> None:
    # Superseded by calm-open (Seam): the open does not read the plan draft — no plan reply,
    # no «увійди знову», `login_needed` always False, the draft unchanged;
    # the plan is shown only in reply to mama's message.
    f1 = F1App()
    a = f1.sign_in("A")
    f1.guide_seen(SUB_A)
    first = f1.open(a)
    assert first["replies"] == [] and first["login_needed"] is False, first

    plan = f1.message(a, TRACER)["plan"]
    assert plan is not None and plan["title"] == TITLE
    mark, built = len(f1.store.touched), len(f1.built)
    opened = f1.open(a)
    assert opened["replies"] == [], "the open shows no plan reply"
    assert opened["login_needed"] is False
    assert [op for op, _ in f1.store.touched[mark:] if op != "get"] == [], "the open changes no plan draft"
    assert len(f1.built) == built, "the open does not reach the calendar"
    assert f1.calendars[SUB_A].insert_calls == []

    # The draft the open left alone still answers «так» for the plan the message showed.
    done = confirm(a, plan)
    assert done.json()["text"] == WRITTEN, done.text
    [event] = f1.calendars[SUB_A].created
    assert (event.start, event.end) == (instant(plan["start"]), instant(plan["end"]))
    assert f1.open(a)["replies"] == []

    # A shown plan whose Google sign-in ran out: the open does not ask to sign in again.
    assert f1.message(a, TRACER, message_id="m3")["plan"] is not None
    f1.google.expired.add(SUB_A)
    resp = a.get("/api/open")
    assert resp.status_code == 200, resp.text
    expired = resp.json()
    assert expired["login_needed"] is False
    assert expired["replies"] == []
    assert SIGN_IN_AGAIN not in resp.text
    assert len(f1.calendars[SUB_A].created) == 1


def test_S2_S3_S4_to_S5_the_deployed_service_answers_what_the_measure_reads() -> None:
    f1 = F1App()
    cold = f1.browser().get("/")
    assert cold.status_code == 302, "the cold-start number is `GET /` without a cookie: a redirect"
    assert httpx.URL(cold.headers["location"]).path == "/auth/login"
    a = f1.sign_in("A")
    shell = a.get("/")
    assert shell.status_code == 200
    assert shell.headers["cache-control"] == "no-cache"
    assert 'rel="manifest"' in shell.text

    assert SONKO_DEPLOY.is_file(), f"{SONKO_DEPLOY} does not exist"
    deployed = SONKO_DEPLOY.read_text(encoding="utf-8")
    assert REVISION in deployed, "the measured revision is not the one Sonko deployed"
    assert REVISION in report_text()


# ------------------------------------------------------------------ the acceptance criteria


def test_AC1_install_from_chrome_and_any_google_account_signs_in_and_sees_only_its_own() -> None:
    f1 = F1App()
    browser = f1.browser()
    manifest = browser.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["name"] and body["start_url"] == "/" and body["display"] in {"standalone", "fullscreen"}
    sizes = {icon["sizes"] for icon in body["icons"]}
    assert {"192x192", "512x512"} <= sizes, sizes
    for icon in body["icons"]:
        got = browser.get(icon["src"])
        assert got.status_code == 200, icon
        assert got.headers["content-type"] == icon["type"] == "image/png", icon

    a = f1.sign_in("A")
    b = f1.sign_in("B")  # an unverified email no list ever named: any Google account signs in
    assert a.get("/").status_code == 200
    assert b.get("/").status_code == 200
    f1.guide_seen(SUB_A)
    f1.guide_seen(SUB_B)

    plan = f1.message(a, TRACER)["plan"]
    assert plan is not None
    mark = len(f1.store.touched)
    seen_by_b = b.get("/api/open")
    assert seen_by_b.status_code == 200
    assert TITLE not in seen_by_b.text and plan["plan_id"] not in seen_by_b.text
    refused = confirm(b, plan)
    assert TITLE not in refused.text
    assert outside(SUB_B, f1.store.touched[mark:]) == []
    assert f1.calendars[SUB_A].created == [] and f1.calendars[SUB_B].created == []
    # Superseded by calm-open (Seam): the open shows no plan to anyone; A's own plan stays A's to confirm.
    assert f1.open(a)["replies"] == []
    assert confirm(a, plan).json()["text"] == WRITTEN
    assert [e.title for e in f1.calendars[SUB_A].created] == [TITLE]
    assert f1.calendars[SUB_B].created == []


def test_AC2_voice_shows_the_recognised_text_and_sending_it_again_plans() -> None:
    f1 = F1App(TRACER)
    a = f1.sign_in("A")
    mark = len(f1.store.touched)

    heard = f1.transcribe(a)
    assert heard.status_code == 200, heard.text
    assert heard.json() == {"text": TRACER}, "request 1 answers the recognised text only"
    assert f1.ai.calls == [], "request 1 plans nothing"
    assert f1.built == [], "request 1 touches no calendar"
    assert [op for op, _ in f1.store.touched[mark:] if op != "get"] == [], "request 1 writes nothing"

    planned = f1.message(a, heard.json()["text"])
    assert planned["plan"] is not None and planned["plan"]["title"] == TITLE, planned


def test_AC3_proposed_time_one_duration_question_yes_writes_once() -> None:
    f1 = F1App()
    a = f1.sign_in("A")
    calendar = f1.calendars[SUB_A]

    shown = f1.message(a, TRACER)
    plan = shown["plan"]
    assert plan is not None and shown["question"] == plan_question(plan), shown
    assert TITLE in shown["text"]
    assert calendar.insert_calls == [], "nothing is written before «так»"
    done = confirm(a, plan)
    assert done.json()["text"] == WRITTEN, done.text
    [event] = calendar.created
    assert event.title == TITLE
    assert (event.start, event.end) == (instant(plan["start"]), instant(plan["end"]))
    assert BASE32HEX.fullmatch(event.id), event.id

    again = confirm(a, plan)
    assert again.status_code == 200, again.text
    f1.ai.intent = "yes"
    f1.message(a, "так", plan_question(plan), "m-yes")
    assert len(calendar.created) == 1, "a repeated «так» creates no second event"

    # The second run: no duration in the phrase -> one question about it -> its answer -> the plan.
    f1.ai.intent = "new_task"
    f1.ai.task["duration_min"] = None
    asked = f1.message(a, NO_LENGTH, None, "m2")
    assert asked["text"] == ASK_DURATION, asked
    assert asked["plan"] is None
    question = asked["question"]
    assert question is not None and question["kind"] == "duration"
    planned = f1.message(a, HALF_HOUR, question, "m3")
    plan2 = planned["plan"]
    assert plan2 is not None and planned["question"] == plan_question(plan2), "one question, then the plan"
    assert confirm(a, plan2).json()["text"] == WRITTEN
    assert len(calendar.created) == 2


def test_AC4_closed_midway_the_next_open_shows_the_unclosed_plan() -> None:
    # Superseded by calm-open (Seam, I1): AC4 of f1-skeleton is withdrawn — the next open shows no plan and
    # does not change the draft; the unclosed plan returns in reply to mama's message.
    f1 = F1App(duration_min=None)
    a = f1.sign_in("A")
    f1.guide_seen(SUB_A)
    cookie = a.cookies.get("mm_session")
    assert cookie

    asked = f1.message(a, NO_LENGTH)["question"]
    assert asked is not None and asked["kind"] == "duration"
    reopened = f1.browser()  # the app was closed: a new page with the same session
    reopened.cookies.set("mm_session", cookie)
    mark = len(f1.store.touched)
    opened = f1.open(reopened)
    assert opened["replies"] == [] and opened["login_needed"] is False, opened
    assert [op for op, _ in f1.store.touched[mark:] if op != "get"] == [], "the open changes no plan draft"

    plan = f1.message(reopened, HALF_HOUR, asked, "m2")["plan"]
    assert plan is not None and plan["title"] == TITLE
    again = f1.browser()
    again.cookies.set("mm_session", cookie)
    mark = len(f1.store.touched)
    assert f1.open(again)["replies"] == []
    assert [op for op, _ in f1.store.touched[mark:] if op != "get"] == []
    assert confirm(again, plan).json()["text"] == WRITTEN
    assert [e.title for e in f1.calendars[SUB_A].created] == [TITLE]


def test_AC5_deployed_in_europe_west3_and_the_measured_numbers_are_in_the_report() -> None:
    assert SONKO_DEPLOY.is_file(), f"{SONKO_DEPLOY} does not exist"
    deployed = SONKO_DEPLOY.read_text(encoding="utf-8")
    assert "europe-west3" in deployed and REVISION in deployed

    text = report_text()
    lowered = text.lower()
    number = r"\d+(?:[.,]\d+)?\s*с\b"
    assert any(re.search(number, line) for line in text.splitlines() if "холодн" in line.lower()), (
        "no cold first-response seconds"
    )
    assert any(
        len(re.findall(r"\d+(?:[.,]\d+)?", line)) >= 3
        for line in text.splitlines()
        if "медіан" in line.lower()
    ), "no recognition seconds"
    assert re.search(r"\d+\s*з\s*\d+", text), "the report does not say how much Gemini heard"
    assert "почут" in lowered or "непочут" in lowered
