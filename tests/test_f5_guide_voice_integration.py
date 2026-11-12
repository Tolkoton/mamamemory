"""Integration tests of the feature f5-guide-voice (block f5-guide-voice, closed with S4 f5-measure).

Written by the slice tester (mode block) from the feature artifact
`.engine/architecture/feature/f5-guide-voice.md` and the public signatures, without the code. The artifact
has no connections between blocks (one block), so there is one test per acceptance criterion AC1-AC4. Each
test drives the built slices S1-S3 end to end through the app's routes (`/api/open`, `/api/message`,
`/api/speak`, `/api/transcribe`) over one in-memory store, a model fake and a fake `Speaker`. The guide's
text is the one sealed by the slice guide (`tests/guide_world.py`), compared with its apostrophes made one
character and its ends stripped, as there.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from mamamemory import access
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.files import Files
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from tests.guide_world import GUIDE, plain
from tests.language_setting_world import HEARD, ProfileStore
from tests.move_material_world import MoveAI
from tests.note_to_case_world import ask
from tests.photo_and_file_world import FakeFiles
from tests.read_aloud_world import FakeSpeaker, bare
from tests.test_one_task_http import MAMA, SUB, FakeGoogle
from tests.test_one_task_http import Clock as AppClock
from tests.test_one_task_planning import NOW, FakeCalendar, make_config
from tests.test_voice_speech import Gemini

SUB_B = "2000000000000000002"
SCHMIDT = "пані Шмідт"
NOTE = "запиши до пані Шмідт: HbA1c 7,2"


def case_q(material_id: str) -> dict[str, Any]:
    return {"kind": "case", "id": material_id, "fingerprint": None}


def is_guide(reply: dict[str, Any]) -> bool:
    return plain(reply["text"]) == GUIDE


def signed_in(store: ProfileStore, config: Config, app: Any, sub: str, started: datetime) -> TestClient:
    store.set(
        sub,
        access.TOKENS_PATH,
        access.tokens_document(
            Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
            started,
        ),
    )
    client = TestClient(
        app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
    )
    email = MAMA if sub == SUB else "second@example.com"
    client.cookies.set("mm_session", access.session_cookie_value(sub, email, started, key=config.session_key))
    return client


class F5App:
    """The whole app as deployed, with fakes at its edges (model, calendar, files, speaker); two accounts."""

    def __init__(self) -> None:
        self.config = make_config()
        self.store = ProfileStore()
        self.clock = AppClock(NOW)
        self.ai = MoveAI()
        self.calendar = FakeCalendar()
        self.speaker = FakeSpeaker()
        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
            files=cast(Files, FakeFiles()),
            speaker=self.speaker,
        )
        self.clients = {sub: signed_in(self.store, self.config, app, sub, NOW) for sub in (SUB, SUB_B)}
        self.step = 0

    def _tick(self) -> None:
        self.step += 1
        self.clock.at = NOW + timedelta(minutes=self.step)

    @staticmethod
    def _ok(resp: httpx.Response) -> dict[str, Any]:
        assert resp.status_code == 200, (resp.status_code, resp.text)
        answer: dict[str, Any] = resp.json()
        return answer

    def open(self, sub: str = SUB) -> list[dict[str, Any]]:
        self._tick()
        replies: list[dict[str, Any]] = self._ok(self.clients[sub].get("/api/open"))["replies"]
        return replies

    def message(
        self, text: str, message_id: str, reply_to: dict[str, Any] | None = None, sub: str = SUB
    ) -> dict[str, Any]:
        self._tick()
        body = {"text": text, "reply_to": reply_to, "message_id": message_id}
        return self._ok(self.clients[sub].post("/api/message", json=body))

    def help(self, text: str, message_id: str, reply_to: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ai.intent = "help"
        return self.message(text, message_id, reply_to)

    def ask_case(self, message_id: str) -> None:
        """A note to an unknown case: the assistant asks «Створити справу …?» — a case question stays open."""
        self.ai.intent = "note"
        self.ai.new_case(SCHMIDT)
        self.ai.default_name = SCHMIDT
        asked = self.message(NOTE, message_id)
        assert asked["text"] == ask(SCHMIDT), asked

    def speak(self, text: str, part: int, sub: str = SUB) -> httpx.Response:
        resp: httpx.Response = self.clients[sub].post("/api/speak", json={"text": text, "part": part})
        return resp


# ------------------------------------------------------------------ the acceptance criteria


def test_AC1_guide_on_the_first_open_only_before_the_open_question_per_account() -> None:
    app = F5App()
    app.ask_case("n1")

    first = app.open()
    assert len(first) >= 2, first
    assert is_guide(first[0]), first
    assert first[0]["question"] is None, first
    assert first[-1]["question"] is not None, first
    assert first[-1]["text"] == ask(SCHMIDT), first
    assert sum(1 for r in first if is_guide(r)) == 1, first

    again = app.open()
    assert not any(is_guide(r) for r in again), again
    assert again[-1]["text"] == ask(SCHMIDT), again
    assert not any(is_guide(r) for r in app.open()), "the guide never shows by itself again"

    other = app.open(SUB_B)
    assert len(other) == 1 and is_guide(other[0]), other
    assert not any(is_guide(r) for r in app.open(SUB_B)), "the second account's guide is shown once too"


def test_AC2_what_can_you_do_answers_the_same_guide_also_under_a_case_question() -> None:
    app = F5App()
    shown = app.open()
    assert any(is_guide(r) for r in shown), shown
    assert not any(is_guide(r) for r in app.open()), "no guide by itself after the first open"

    for i, text in enumerate(["що ти вмієш?", "як з тобою працювати?"]):
        reply = app.help(text, f"h{i}")
        assert is_guide(reply), (text, reply)
        assert reply["question"] is None, reply
        assert reply["plan"] is None, reply

    app.ask_case("n1")
    under_case = app.help("що ти вмієш?", "h-case", case_q("n1"))
    assert is_guide(under_case), under_case
    assert under_case["question"] is None, under_case


def test_AC3_speaker_icon_reads_this_reply_only_when_pressed() -> None:
    app = F5App()
    shown = app.open()
    reply = app.help("що ти вмієш?", "h1")
    assert is_guide(reply), reply
    assert shown and app.speaker.calls == [], "nothing sounds without a press"

    text = reply["text"]
    first = app.speak(text, 0)
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("audio/ogg"), first.headers
    count = int(first.headers["x-parts"])
    assert count >= 1, first.headers
    bodies = [first.content] + [app.speak(text, i).content for i in range(1, count)]

    spoken = [part for part, _, _ in app.speaker.calls]
    assert len(spoken) == count, spoken
    assert bodies == [b"OggS:" + part.encode() for part in spoken]
    assert "".join(bare(part) for part in spoken) == bare(text), "the parts are this reply, whole"
    assert all(language == "uk" for _, language, _ in app.speaker.calls), app.speaker.calls

    app.open()
    app.message("що ти вмієш?", "h2")
    assert len(app.speaker.calls) == count, "only a press makes a sound"


def test_AC4_recognition_speech_and_guide_take_the_language_from_the_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heard: list[str] = []

    def fake_speech(audio: bytes, mime: str, *, language: str, **_: Any) -> str:
        heard.append(language)
        return HEARD

    monkeypatch.setattr("mamamemory.http.app.speech", fake_speech, raising=False)
    monkeypatch.setattr("mamamemory.integrations.ai.speech", fake_speech)

    config = replace(make_config(), language="xx")
    store = ProfileStore()
    store.set(SUB, access.PROFILE_PATH, {"language": "uk"})
    speaker = FakeSpeaker()
    calendar = FakeCalendar()
    gemini = Gemini(HEARD).client()
    app = create_app(
        config,
        store,
        cast(GoogleAuth, FakeGoogle()),
        lambda: datetime.now(UTC),
        ai=AI(lambda: gemini, config),
        calendar=lambda session, started: cast(GoogleWork, calendar),
        speaker=speaker,
    )
    started = datetime.now(UTC)
    clients = {sub: signed_in(store, config, app, sub, started) for sub in (SUB, SUB_B)}

    for sub in (SUB, SUB_B):  # SUB_B has no profile document: the default `uk`
        store.profile_reads.clear()
        opened = clients[sub].get("/api/open")
        assert opened.status_code == 200, opened.text
        assert is_guide(opened.json()["replies"][0]), opened.json()
        assert any(acc == sub for acc, _, _ in store.profile_reads), ("guide", sub, store.profile_reads)

        store.profile_reads.clear()
        said = clients[sub].post(
            "/api/transcribe", content=b"\x1a\x45\xdf\xa3 webm", headers={"content-type": "audio/webm"}
        )
        assert said.status_code == 200, said.text
        assert heard[-1] == "uk", heard
        assert any(acc == sub for acc, _, _ in store.profile_reads), ("transcribe", sub, store.profile_reads)

        store.profile_reads.clear()
        spoken = clients[sub].post("/api/speak", json={"text": "Перевірка озвучення.", "part": 0})
        assert spoken.status_code == 200, spoken.text
        assert speaker.calls[-1][1] == "uk", speaker.calls
        assert any(acc == sub for acc, _, _ in store.profile_reads), ("speak", sub, store.profile_reads)
