"""Integration tests of the feature f3-cases-intake (block f3-cases-intake, closed with S5 f3-measure).

Written by the slice tester (mode block) from the feature artifact
`.engine/architecture/feature/f3-cases-intake.md` and the public signatures, without the code. One test per
acceptance criterion AC1-AC6 and one for the line «Повтор без дубля» of «Inter-slice contracts». Each test
drives the built slices S1-S4 end to end through the app's routes (`/api/message`, `/api/case/confirm`,
`/api/upload`, `/api/open`) over one in-memory store, one fake Cloud Storage and one model fake; the state
is read back through the `cases` reading functions. The model fake is the S4 one
(`tests/move_material_world.py`): it answers the route with `ai.intent`, the Розкладач and «перекласти» by
the numbers in the prompt's catalogues.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access
from mamamemory import cases as case_module
from mamamemory.access import Session
from mamamemory.config import SCOPES
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.files import Files
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from tests.move_material_world import SNIPPET, WHAT, MoveAI, moved
from tests.note_to_case_world import NOT_ACTUAL, ask, placed
from tests.photo_and_file_world import NOT_READ, PDF, PNG, FakeFiles
from tests.test_one_task_http import MAMA, SUB, FakeGoogle
from tests.test_one_task_http import Clock as AppClock
from tests.test_one_task_planning import NOW, FakeCalendar, make_config

SUB_B = "2000000000000000002"
SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"
FISCHER = "пан Фішер"
NOTE = "запиши до пані Шмідт: HbA1c 7,2"
SECOND = "у Шмідт тиск 140 на 90"
WHICH = "У яку справу покласти?"
LEFT = "Гаразд, лишила без справи."
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def case_q(material_id: str) -> dict[str, Any]:
    return {"kind": "case", "id": material_id, "fingerprint": None}


class F3App:
    """The whole app as deployed, with fakes at its edges; two accounts signed in by cookie."""

    def __init__(self) -> None:
        self.config = make_config()
        self.store = InMemoryStore()
        for sub in (SUB, SUB_B):
            self.store.set(
                sub,
                access.TOKENS_PATH,
                access.tokens_document(
                    Tokens(
                        access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)
                    ),
                    NOW,
                ),
            )
        self.clock = AppClock(NOW)
        self.ai = MoveAI()
        self.files = FakeFiles()
        self.calendar = FakeCalendar()
        make: Callable[..., FastAPI] = create_app
        app = make(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
            files=cast(Files, self.files),
        )
        self.clients = {
            sub: TestClient(
                app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
            )
            for sub in (SUB, SUB_B)
        }
        for sub, client in self.clients.items():
            email = MAMA if sub == SUB else "second@example.com"
            client.cookies.set(
                "mm_session", access.session_cookie_value(sub, email, NOW, key=self.config.session_key)
            )
        self.step = 0

    # -------------------------------------------------------------- one request each, a minute apart

    def _tick(self) -> None:
        self.step += 1
        self.clock.at = NOW + timedelta(minutes=self.step)

    def _ok(self, resp: Any) -> dict[str, Any]:
        assert resp.status_code == 200, (resp.status_code, resp.text)
        answer: dict[str, Any] = resp.json()
        return answer

    def message(
        self, text: str, message_id: str, reply_to: dict[str, Any] | None = None, sub: str = SUB
    ) -> dict[str, Any]:
        self._tick()
        body = {"text": text, "reply_to": reply_to, "message_id": message_id}
        return self._ok(self.clients[sub].post("/api/message", json=body))

    def confirm(self, material_id: str, sub: str = SUB) -> dict[str, Any]:
        self._tick()
        return self._ok(self.clients[sub].post("/api/case/confirm", json={"material_id": material_id}))

    def upload(self, data: bytes, mime: str, material_id: str, sub: str = SUB) -> dict[str, Any]:
        self._tick()
        headers = {"Content-Type": mime, "X-Material-Id": material_id}
        return self._ok(self.clients[sub].post("/api/upload", content=data, headers=headers))

    def open(self, sub: str = SUB) -> dict[str, Any]:
        self._tick()
        return self._ok(self.clients[sub].get("/api/open"))

    # -------------------------------------------------------------- the model's choices

    def note(
        self, text: str, message_id: str, to: str | None, *, known: bool, sub: str = SUB
    ) -> dict[str, Any]:
        """A note the Розкладач files to the known case `to`, or proposes the new case `to`."""
        self.ai.intent = "note"
        if known:
            assert to is not None
            self.ai.file_to(to)
        elif to is None:
            self.ai.nowhere()
        else:
            self.ai.new_case(to)
            self.ai.default_name = to
        return self.message(text, message_id, sub=sub)

    def photo(
        self, read: str, material_id: str, to: str, *, known: bool, mime: str = "image/png", data: bytes = PNG
    ) -> dict[str, Any]:
        self.ai.read_text = read
        if known:
            self.ai.file_to(to)
        else:
            self.ai.new_case(to)
            self.ai.default_name = to
        return self.upload(data, mime, material_id)

    def make_case(self, name: str, message_id: str, sub: str = SUB) -> case_module.Case:
        """A case made the way mama makes it: a note, «Створити справу…?», the button «так»."""
        asked = self.note(f"перша нотатка про {name}", message_id, name, known=False, sub=sub)
        assert asked["text"] == ask(name), asked
        assert self.confirm(message_id, sub=sub)["text"] == placed(name)
        return self.case_named(name, sub)

    # -------------------------------------------------------------- reading back

    @staticmethod
    def session(sub: str = SUB) -> Session:
        return Session(account_id=sub, google_credentials=lambda: Credentials("at-test"))

    def materials(self, sub: str = SUB) -> list[case_module.Material]:
        return case_module.materials_catalogue(self.session(sub), self.store)

    def material(self, material_id: str, sub: str = SUB) -> case_module.Material:
        found = [m for m in self.materials(sub) if m.material_id == material_id]
        assert len(found) == 1, (material_id, found)
        return found[0]

    def cases(self, sub: str = SUB) -> list[case_module.Case]:
        return case_module.catalogue(self.session(sub), self.store)

    def case_named(self, name: str, sub: str = SUB) -> case_module.Case:
        found = [c for c in self.cases(sub) if c.name == name]
        assert len(found) == 1, (name, self.cases(sub))
        return found[0]

    def built_from(self, case: case_module.Case) -> str:
        assert case.description in self.ai.described, (case.name, case.description)
        return self.ai.described[case.description]


def question_replies(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in answer["replies"] if r["question"] is not None]


# ------------------------------------------------------------------ the acceptance criteria


def test_AC1_a_spoken_note_lands_in_the_case_the_system_chose_and_says_where() -> None:
    app = F3App()
    first = app.note(NOTE, "n1", SCHMIDT, known=False)
    assert first["text"] == ask(SCHMIDT)
    assert first["question"] == case_q("n1")
    done = app.confirm("n1")
    assert done["text"] == placed(SCHMIDT)
    schmidt = app.case_named(SCHMIDT)
    assert app.material("n1").case_id == schmidt.case_id
    assert app.material("n1").kind == "note"

    second = app.note(SECOND, "n2", SCHMIDT, known=True)
    assert second["text"] == placed(SCHMIDT)
    assert second["question"] is None
    assert app.material("n2").case_id == schmidt.case_id
    assert [c.name for c in app.cases()] == [SCHMIDT]
    assert question_replies(app.open()) == []


def test_AC2_a_photo_or_file_through_plus_lands_like_a_note_with_its_text_and_original() -> None:
    app = F3App()
    schmidt = app.make_case(SCHMIDT, "k0")
    form = "Аналіз крові: HbA1c 7,2"
    reply = app.photo(form, "p1", SCHMIDT, known=True)
    assert reply["text"] == placed(SCHMIDT)
    photo = app.material("p1")
    assert (photo.kind, photo.case_id, photo.text) == ("photo", schmidt.case_id, form)
    assert photo.gs_uri == app.files.uri(SUB, "p1")
    assert app.files.objects[(SUB, "p1")] == (PNG, "image/png")

    letter = app.photo(
        "Лист від лікаря: пані Шмідт", "f1", SCHMIDT, known=True, mime="application/pdf", data=PDF
    )
    assert letter["text"] == placed(SCHMIDT)
    assert (app.material("f1").kind, app.material("f1").case_id) == ("file", schmidt.case_id)
    assert app.files.objects[(SUB, "f1")] == (PDF, "application/pdf")

    for number, mime in enumerate(("image/jpeg", "image/webp", "image/heic", "text/plain")):
        material_id = f"t{number}"
        answer = app.photo("HbA1c 7,2", material_id, SCHMIDT, known=True, mime=mime, data=b"HbA1c 7,2")
        assert answer["text"] == placed(SCHMIDT), (mime, answer)
        assert app.material(material_id).case_id == schmidt.case_id, mime
        assert app.files.objects[(SUB, material_id)] == (b"HbA1c 7,2", mime)

    fresh = app.photo("Рахунок за ремонт кухні", "p2", "ремонт кухні", known=False)
    assert fresh["text"] == ask("ремонт кухні")
    assert fresh["question"] == case_q("p2")
    assert app.confirm("p2")["text"] == placed("ремонт кухні")
    assert app.material("p2").case_id == app.case_named("ремонт кухні").case_id

    before = {m.material_id for m in app.materials()}
    refused = app.upload(b"PK\x03\x04-a-word-document-", DOCX, "d1")
    assert refused["text"] == NOT_READ
    assert {m.material_id for m in app.materials()} == before
    assert (SUB, "d1") not in app.files.objects


def test_AC3_yes_creates_the_case_no_asks_which_not_needed_leaves_it_without_case() -> None:
    app = F3App()
    koch = app.make_case(KOCH, "k0")

    assert app.note("нотатка про пані Шмідт", "a1", SCHMIDT, known=False)["text"] == ask(SCHMIDT)
    app.ai.intent = "yes"
    yes = app.message("так", "w1", reply_to=case_q("a1"))
    assert yes["text"] == placed(SCHMIDT)
    assert app.material("a1").case_id == app.case_named(SCHMIDT).case_id

    assert app.note("нотатка про пана Фішера", "b1", FISCHER, known=False)["text"] == ask(FISCHER)
    app.ai.intent = "no"
    no = app.message("ні", "w2", reply_to=case_q("b1"))
    assert no["text"] == WHICH
    assert no["question"] == case_q("b1")
    app.ai.intent = "case_name"
    app.ai.file_to(KOCH)
    chosen = app.message("до Коха", "w3", reply_to=case_q("b1"))
    assert chosen["text"] == placed(KOCH)
    assert app.material("b1").case_id == koch.case_id
    assert FISCHER not in [c.name for c in app.cases()]

    assert app.photo("Квитанція з городу", "c1", "город", known=False)["text"] == ask("город")
    app.ai.intent = "not_needed"
    left = app.message("не треба", "w4", reply_to=case_q("c1"))
    assert left["text"] == LEFT
    assert left["question"] is None
    kept = app.material("c1")
    assert (kept.case_id, kept.text) == (None, "Квитанція з городу")
    assert app.files.objects[(SUB, "c1")] == (PNG, "image/png")
    assert "город" not in [c.name for c in app.cases()]
    assert sorted(c.name for c in app.cases()) == sorted([KOCH, SCHMIDT])
    assert question_replies(app.open()) == []


def test_AC4_each_open_create_question_is_kept_for_its_material_and_shown_newest_after_reopen() -> None:
    app = F3App()
    app.make_case(KOCH, "k0")
    assert app.note("нотатка про пані Шмідт", "a1", SCHMIDT, known=False)["question"] == case_q("a1")
    assert app.photo("Бланк пана Фішера", "b1", FISCHER, known=False)["question"] == case_q("b1")

    for _ in range(2):
        opened = question_replies(app.open())
        assert len(opened) == 1, opened
        assert opened[-1]["question"] == case_q("b1")
        assert opened[-1]["text"].startswith(ask(FISCHER)), opened
        assert opened[-1]["text"].endswith("Ще 1 питання чекає."), opened

    app.ai.intent = "not_needed"
    assert app.message("не треба", "w1", reply_to=case_q("b1"))["text"] == LEFT

    reopened = question_replies(app.open())
    assert len(reopened) == 1, reopened
    assert reopened[-1]["question"] == case_q("a1")
    assert reopened[-1]["text"] == ask(SCHMIDT)
    assert app.confirm("a1")["text"] == placed(SCHMIDT)
    assert question_replies(app.open()) == []


def test_AC5_move_any_named_material_not_only_the_last_and_both_descriptions_follow() -> None:
    app = F3App()
    koch = app.make_case(KOCH, "k0")
    schmidt = app.make_case(SCHMIDT, "s0")
    wrong = "Аналіз Коха: креатинін 1,1"
    assert len(wrong) < 40 and len(wrong) <= SNIPPET
    assert app.photo(wrong, "p1", SCHMIDT, known=True)["text"] == placed(SCHMIDT)
    stays = "у Шмідт тиск 140 на 90 зранку"
    assert app.note(stays, "n2", SCHMIDT, known=True)["text"] == placed(SCHMIDT)
    koch_before = app.case_named(KOCH).description

    app.ai.intent = "move"
    app.ai.choose(wrong, KOCH)
    app.ai.avoid = [m.text[:SNIPPET] for m in app.materials() if m.text]
    reply = app.message("переклади аналіз Коха до пана Коха", "m1")
    assert reply["text"] == moved(app.material("p1").text, KOCH)
    assert app.material("p1").case_id == koch.case_id
    assert app.material("n2").case_id == schmidt.case_id

    koch_after = app.case_named(KOCH)
    assert koch_after.description != koch_before
    assert wrong in app.built_from(koch_after)
    schmidt_after = app.case_named(SCHMIDT)
    source_prompt = app.built_from(schmidt_after)
    assert wrong not in source_prompt
    assert stays in source_prompt


def test_AC6_cases_materials_and_files_of_one_account_are_not_seen_or_reached_by_another() -> None:
    app = F3App()
    app.make_case(SCHMIDT, "k0")
    secret = "Бланк пані Шмідт: HbA1c 7,2"
    assert app.photo(secret, "p1", SCHMIDT, known=True)["text"] == placed(SCHMIDT)
    assert app.note("нотатка про пана Фішера", "a1", FISCHER, known=False)["question"] == case_q("a1")
    mine = {m.material_id: (m.state, m.case_id, m.text) for m in app.materials()}

    assert app.cases(SUB_B) == []
    assert app.materials(SUB_B) == []
    assert question_replies(app.open(SUB_B)) == []

    assert app.confirm("a1", sub=SUB_B)["text"] == NOT_ACTUAL
    app.ai.intent = "move"
    app.ai.choose(secret, SCHMIDT)
    app.ai.avoid = [secret[:SNIPPET]]
    assert app.message("переклади бланк Шмідт до Шмідт", "m1", sub=SUB_B)["text"] == WHAT
    assert all(secret not in prompt for prompt in app.ai.prompts.get("choose_material", []))

    app.ai.read_text = "Бланк другого акаунта"
    app.ai.new_case(KOCH)
    app.ai.default_name = KOCH
    seen = {task: len(prompts) for task, prompts in app.ai.prompts.items()}
    app.upload(b"\x89PNG-other-account-", "image/png", "p1", sub=SUB_B)
    for task, prompts in app.ai.prompts.items():
        for prompt in prompts[seen.get(task, 0) :]:
            assert SCHMIDT not in prompt and secret not in prompt and FISCHER not in prompt, (task, prompt)
    assert app.files.objects[(SUB, "p1")] == (PNG, "image/png")
    assert app.files.objects[(SUB_B, "p1")] == (b"\x89PNG-other-account-", "image/png")

    assert {m.material_id: (m.state, m.case_id, m.text) for m in app.materials()} == mine
    assert [c.name for c in app.cases()] == [SCHMIDT]
    assert [m.material_id for m in app.materials(SUB_B)] == ["p1"]
    assert app.material("p1", SUB_B).text == "Бланк другого акаунта"


# ------------------------------------------------------------------ «Inter-slice contracts»


def test_a_repeat_of_the_same_note_or_upload_makes_no_second_material_or_file() -> None:
    app = F3App()
    schmidt = app.make_case(SCHMIDT, "k0")
    for _ in range(2):
        assert app.note(SECOND, "n1", SCHMIDT, known=True)["text"] == placed(SCHMIDT)
        assert app.photo("Аналіз крові", "p1", SCHMIDT, known=True)["text"] == placed(SCHMIDT)
    assert [m.material_id for m in app.materials() if m.material_id in ("n1", "p1")].count("n1") == 1
    assert [m.material_id for m in app.materials()].count("p1") == 1
    assert [key for key in app.files.objects if key[0] == SUB] == [(SUB, "p1")]
    assert app.material("n1").case_id == schmidt.case_id
    assert app.material("p1").case_id == schmidt.case_id
