"""Contract tests of the routes of the slice note-to-case: `/api/message` with `message_id`,
`/api/case/confirm`, the deadline of both and the log line (C1).

Written by the slice tester from the sealed contract `.engine/slices/note-to-case.md`, without the code.
The app's clock is the clock the routes pass on; the model fake moves it during a call, and a store that
calls back on every write moves it between the writes of «так», to stand on either side of the deadline.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access, cases
from mamamemory.access import Session
from mamamemory.config import SCOPES
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Decide, InMemoryStore
from tests.note_to_case_world import FAILED, NOT_ACTUAL, CaseAI, Notes, ask, placed
from tests.test_one_task_http import MAMA, SUB, Clock, FakeGoogle
from tests.test_one_task_planning import NOW, FakeCalendar, make_config

SCHMIDT = "пані Шмідт"
NOTE = "запиши до пані Шмідт: HbA1c 7,2"


class HookStore(InMemoryStore):
    """The fake store; `on_write(path)` runs after every write."""

    def __init__(self) -> None:
        super().__init__()
        self.on_write: Callable[[str], None] | None = None

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        super().set(account_id, path, data)
        if self.on_write is not None:
            self.on_write(path)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        written = super().transact(account_id, path, decide)
        if self.on_write is not None:
            self.on_write(path)
        return written


class NotesApp:
    def __init__(self) -> None:
        self.config = make_config()
        self.store = HookStore()
        self.store.set(
            SUB,
            access.TOKENS_PATH,
            access.tokens_document(
                Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
                NOW,
            ),
        )
        self.clock = Clock(NOW)
        self.ai = CaseAI()
        self.ai.intent = "note"
        self.calendar = FakeCalendar()
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
        self.client.cookies.set(
            "mm_session", access.session_cookie_value(SUB, MAMA, NOW, key=self.config.session_key)
        )
        self.session = Session(account_id=SUB, google_credentials=lambda: Credentials("at-test"))
        self.world = Notes(ai=self.ai, store=self.store, config=self.config, session=self.session)

    def message(self, text: str, message_id: str | None = None, **extra: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text, "reply_to": None, **extra}
        if message_id is not None:
            body["message_id"] = message_id
        resp = self.client.post("/api/message", json=body)
        assert resp.status_code == 200, resp.text
        answer: dict[str, Any] = resp.json()
        return answer

    def confirm(self, material_id: str) -> dict[str, Any]:
        resp = self.client.post("/api/case/confirm", json={"material_id": material_id})
        assert resp.status_code == 200, resp.text
        answer: dict[str, Any] = resp.json()
        return answer

    def materials(self) -> list[cases.Material]:
        return cases.materials_catalogue(self.session, self.store)


def with_case() -> NotesApp:
    """An app whose account already has a first case (made by a note and «так» through `cases`)."""
    app = NotesApp()
    app.world.seed("пан Кох", "k0")
    app.ai.intent = "note"
    app.ai.calls.clear()
    return app


def test_message_id_names_the_material_and_its_repeat_makes_no_second() -> None:
    app = with_case()
    app.ai.new_case(SCHMIDT)
    first = app.message(NOTE, "msg-1")
    again = app.message(NOTE, "msg-1")
    assert first["text"] == ask(SCHMIDT)
    assert first["question"] == {"kind": "case", "id": "msg-1", "fingerprint": None}
    assert again["text"] == first["text"]
    assert again["question"] == first["question"]
    assert [m.material_id for m in app.materials() if m.text == NOTE] == ["msg-1"]


def test_message_without_or_with_a_bad_message_id_gets_a_new_id_on_the_server() -> None:
    app = with_case()
    app.ai.nowhere()
    bad = ["", "a" * 65, "a/b", "ü", "a b", "../x"]
    for message_id in [None, None, *bad, *bad]:
        app.message(f"нотатка {message_id!r}", message_id)
    sent = len(bad) * 2 + 2
    notes = [m for m in app.materials() if m.text.startswith("нотатка ")]
    assert len(notes) == sent, [m.material_id for m in notes]
    assert len({m.material_id for m in notes}) == sent
    assert not {m.material_id for m in notes} & set(bad)
    # Both edges of the lawful form are kept as they are: a repeat is the same material.
    for message_id in ("a" * 64, "A-z_09"):
        app.message(f"лагідна {message_id}", message_id)
        app.message(f"лагідна {message_id}", message_id)
    kept = [m.material_id for m in app.materials() if m.text.startswith("лагідна ")]
    assert sorted(kept) == sorted(["a" * 64, "A-z_09"])


def test_case_confirm_route_places_the_note_without_the_route_model() -> None:
    app = with_case()
    app.ai.new_case(SCHMIDT)
    app.message(NOTE, "msg-1")
    routed = app.ai.count("route")
    reply = app.confirm("msg-1")
    assert reply["text"] == placed(SCHMIDT)
    assert reply["question"] is None
    assert app.ai.count("route") == routed
    assert [c.name for c in cases.catalogue(app.session, app.store)].count(SCHMIDT) == 1


def test_case_confirm_with_a_bad_or_unknown_material_id_is_not_actual() -> None:
    app = with_case()
    app.ai.new_case(SCHMIDT)
    app.message(NOTE, "msg-1")
    for material_id in ("", "a" * 65, "../x", "msg-1/x", "nope"):
        assert app.confirm(material_id)["text"] == NOT_ACTUAL, material_id
    assert len(cases.catalogue(app.session, app.store)) == 1


@pytest.mark.parametrize(("moved_s", "finished"), [(9, True), (11, False)])
def test_message_deadline_is_request_timeout_less_two_call_timeouts(moved_s: int, finished: bool) -> None:
    # request_timeout_s = 30, call_timeout_s = 10: the deadline is 10 s after the request began.
    app = with_case()
    app.ai.file_to(cases.catalogue(app.session, app.store)[0].name)

    def move() -> None:
        app.clock.at = NOW + timedelta(seconds=moved_s)

    app.ai.after["classify_case"] = move
    reply = app.message("алергія на пеніцилін", "msg-1")
    if finished:
        assert reply["text"].startswith("Поклала в «"), reply
        assert app.ai.count("describe_case") == 1
    else:
        assert reply["text"] == FAILED
        assert app.ai.count("describe_case") == 0


@pytest.mark.parametrize(("moved_s", "finished"), [(9, True), (11, False)])
def test_case_confirm_deadline_is_the_same(moved_s: int, finished: bool) -> None:
    app = with_case()
    app.ai.new_case(SCHMIDT)
    app.message(NOTE, "msg-1")
    described = app.ai.count("describe_case")

    def move(path: str) -> None:
        app.clock.at = NOW + timedelta(seconds=moved_s)

    app.store.on_write = move
    reply = app.confirm("msg-1")
    if finished:
        assert reply["text"] == placed(SCHMIDT)
        assert app.ai.count("describe_case") == described + 1
    else:
        assert reply["text"] == FAILED
        assert app.ai.count("describe_case") == described


def test_model_failure_answers_failed_and_the_repeat_finishes() -> None:
    app = with_case()
    app.ai.new_case(SCHMIDT)
    app.ai.fail["classify_case"] = 1
    assert app.message(NOTE, "msg-1")["text"] == FAILED
    assert [m.state for m in app.materials() if m.material_id == "msg-1"] == ["new"]
    assert app.message(NOTE, "msg-1")["text"] == ask(SCHMIDT)
    assert [m.material_id for m in app.materials() if m.text == NOTE] == ["msg-1"]


def test_log_lines_carry_neither_the_note_nor_the_case_name(capfd: pytest.CaptureFixture[str]) -> None:
    app = with_case()
    capfd.readouterr()
    app.ai.new_case(SCHMIDT)
    app.ai.fail["classify_case"] = 1
    app.message(NOTE, "msg-1")
    app.message(NOTE, "msg-1")
    app.ai.fail["describe_case"] = 1
    app.confirm("msg-1")
    app.confirm("msg-1")
    out = capfd.readouterr()
    for line in (out.out + out.err).splitlines():
        for secret in ("HbA1c", "Шмідт", NOTE):
            assert secret not in line, f"the log line carries {secret!r}: {line}"
