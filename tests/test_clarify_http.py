"""Contract tests of the routes of the slice clarify: `/api/message` answering a clarification with `choices`,
and `POST /api/clarify {clarify_id, option: 1|2}`.

Written by the slice tester from the sealed contract `.engine/slices/clarify.md`, without the code.
"""

from typing import Any, cast

from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access, cases
from mamamemory.access import Session
from mamamemory.config import SCOPES
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from tests.case_questions_world import BrokenStore
from tests.clarify_world import NOT_ACTUAL, Clarify, ClarifyCaseAI
from tests.note_to_case_world import ask
from tests.test_one_task_http import MAMA, SUB, Clock, FakeGoogle
from tests.test_one_task_planning import NOW, FakeCalendar, make_config

SCHMIDT = "пані Шмідт"
WOLF = "пан Вольф просив виписати рецепт на леводопу"


class ClarifyApp:
    def __init__(self) -> None:
        self.config = make_config()
        self.store = BrokenStore()
        self.store.set(
            SUB,
            access.TOKENS_PATH,
            access.tokens_document(
                Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
                NOW,
            ),
        )
        self.clock = Clock(NOW)
        self.ai = ClarifyCaseAI()
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
        world = Clarify(ai=self.ai, store=self.store, config=self.config, session=self.session)
        world.seed("пан Кох", "k0")
        self.ai.new_case(SCHMIDT)
        self.ai.default_name = SCHMIDT

    def message(self, text: str, message_id: str) -> dict[str, Any]:
        resp = self.client.post(
            "/api/message", json={"text": text, "reply_to": None, "message_id": message_id}
        )
        assert resp.status_code == 200, resp.text
        answer: dict[str, Any] = resp.json()
        return answer

    def clarify(self, clarify_id: str, option: int) -> dict[str, Any]:
        resp = self.client.post("/api/clarify", json={"clarify_id": clarify_id, "option": option})
        assert resp.status_code == 200, resp.text
        answer: dict[str, Any] = resp.json()
        return answer

    def materials(self) -> list[cases.Material]:
        return cases.materials_catalogue(self.session, self.store)


def test_message_route_answers_the_clarification_with_its_question_and_two_choices() -> None:
    app = ClarifyApp()
    app.ai.unsure("note", "new_task")
    answer = app.message(WOLF, "m1")
    assert (
        answer["text"] == "Не зовсім зрозуміла: записати нотаткою до справи чи поставити задачею в календар?"
    )
    question = answer["question"]
    assert question["kind"] == "clarify", answer
    assert question["fingerprint"] is None, answer
    choices = answer.get("choices")
    assert isinstance(choices, list) and len(choices) == 2, answer
    assert all(isinstance(c, str) and c for c in choices), answer


def test_clarify_route_runs_the_chosen_option_once_then_is_not_actual() -> None:
    app = ClarifyApp()
    app.ai.unsure("note", "new_task")
    question = app.message(WOLF, "m1").get("question")
    assert isinstance(question, dict) and question.get("kind") == "clarify", question
    clarify_id = question["id"]
    answer = app.clarify(clarify_id, 1)
    assert answer["text"] == ask(SCHMIDT)
    assert answer["question"] == {"kind": "case", "id": "m1", "fingerprint": None}
    assert [m.material_id for m in app.materials() if m.text == WOLF] == ["m1"]
    assert app.clarify(clarify_id, 1)["text"] == NOT_ACTUAL
    assert app.clarify("no-such-clarify", 2)["text"] == NOT_ACTUAL
    assert [m.material_id for m in app.materials() if m.text == WOLF] == ["m1"]
