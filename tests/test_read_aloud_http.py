"""Contract tests of `POST /api/speak` (slice read-aloud, Seam 3) and of I2.

Written by the slice tester from the sealed contract `.engine/slices/read-aloud.md`, without the code.
The app's speaker is `FakeSpeaker`: its `say` answers `OggS:<the part's text>`, so the body tells which
part was spoken. The app's clock stands at `NOW`; `_deadline` is `NOW + 30 − 2 × 10` seconds.
"""

from datetime import timedelta
from typing import Any

import pytest
from google.api_core.exceptions import ServiceUnavailable

from mamamemory import access
from mamamemory.integrations.store import Store
from tests.read_aloud_world import FAILED_SPEAK, THREE, THREE_PARTS, FakeSpeaker, SpeakApp, norm
from tests.test_one_task_http import SUB
from tests.test_one_task_planning import NOW

SECRET_WORD = "Шмідтоватаємниця"
SECRET_TEXT = f"Мама записалася до {SECRET_WORD} на п'ятницю."


def spoken(body: bytes) -> str:
    assert body.startswith(b"OggS:"), body[:20]
    return norm(body[len(b"OggS:") :].decode())


# ------------------------------------------------------------------ Seam 3


def test_speak_returns_200_with_audio_of_the_part_ogg_no_store_and_x_parts() -> None:
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    resp = app.speak({"text": THREE, "part": 1})
    assert resp.status_code == 200, resp.text
    assert spoken(resp.content) == THREE_PARTS[1]
    assert resp.headers["content-type"].split(";")[0].strip() == "audio/ogg"
    assert "no-store" in resp.headers["cache-control"]
    assert resp.headers["x-parts"] == "2"
    assert len(speaker.calls) == 1

    first = app.speak({"text": THREE, "part": 0})
    assert first.status_code == 200
    assert spoken(first.content) == THREE_PARTS[0]
    assert first.headers["x-parts"] == "2"


def test_speak_deadline_is_the_deadline_formula_from_the_request_start() -> None:
    speaker = FakeSpeaker()
    resp = SpeakApp(speaker).speak({"text": THREE, "part": 0})
    assert resp.status_code == 200, resp.text
    (_, _, deadline) = speaker.calls[0]
    assert deadline == NOW + timedelta(seconds=10)


def test_speak_language_is_the_accounts_language(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, Store]] = []

    def account_language(session: access.Session, store: Store) -> str:
        asked.append((session.account_id, store))
        return "xx-account"

    monkeypatch.setattr(access, "language", account_language)
    monkeypatch.setattr("mamamemory.http.app.language", account_language, raising=False)
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    resp = app.speak({"text": THREE, "part": 0})
    assert resp.status_code == 200, resp.text
    assert [language for _, language, _ in speaker.calls] == ["xx-account"]
    assert asked and asked[0][0] == SUB and asked[0][1] is app.store


def test_speak_part_outside_range_or_not_a_json_integer_is_400() -> None:
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    bodies: list[dict[str, Any]] = [
        {"text": THREE, "part": 2},  # THREE has 2 parts: 0 and 1
        {"text": THREE, "part": -1},
        {"text": THREE, "part": True},
        {"text": THREE, "part": False},
        {"text": THREE, "part": "1"},
        {"text": THREE, "part": None},
        {"text": THREE},
    ]
    for body in bodies:
        resp = app.speak(body)
        assert resp.status_code == 400, (body.get("part", "missing"), resp.status_code)
        assert resp.json() == {"error": FAILED_SPEAK}, body.get("part", "missing")
    assert speaker.calls == []


def test_speak_text_empty_blank_not_a_string_or_over_10000_is_400() -> None:
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    texts: list[Any] = ["", "   \n\t ", 42, None, ["Так."], {"text": "Так."}, "ж" * 10001]
    for text in texts:
        resp = app.speak({"text": text, "part": 0})
        assert resp.status_code == 400, (repr(text)[:30], resp.status_code)
    resp = app.speak({"part": 0})
    assert resp.status_code == 400, resp.status_code
    assert speaker.calls == []


def test_speak_without_speaker_is_502() -> None:
    resp = SpeakApp(None).speak({"text": THREE, "part": 0})
    assert resp.status_code == 502
    assert resp.json() == {"error": FAILED_SPEAK}


def test_speak_without_session_is_401() -> None:
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    app.client.cookies.clear()
    resp = app.speak({"text": THREE, "part": 0})
    assert resp.status_code == 401
    assert speaker.calls == []


def test_speak_tts_error_is_502_and_the_log_carries_no_text(
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    speaker = FakeSpeaker(fail=ServiceUnavailable(f"tts failed on: {SECRET_TEXT}"))
    app = SpeakApp(speaker)
    capfd.readouterr()
    resp = app.speak({"text": SECRET_TEXT, "part": 0})
    assert resp.status_code == 502
    assert resp.json() == {"error": FAILED_SPEAK}
    assert len(speaker.calls) == 1
    out, err = capfd.readouterr()
    for written in (out, err, caplog.text):
        assert SECRET_WORD not in written, written


# ------------------------------------------------------------------ I2


def test_I2_only_api_speak_calls_tts() -> None:
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    client = app.client
    client.post("/api/message", json={"text": "у четвер подзвонити нотаріусу", "reply_to": None})
    client.post("/api/message", json={"text": "що ти вмієш?", "reply_to": None})
    client.get("/api/open")
    client.post("/api/plan/confirm", json={"plan_id": "p1", "fingerprint": "f1"})
    client.post("/api/case/confirm", json={"case_id": "c1", "fingerprint": "f1"})
    client.post("/api/upload", content=b"%PDF-1.4 a file", headers={"content-type": "application/pdf"})
    client.post("/api/clarify", json={"text": "так", "reply_to": None})
    assert speaker.calls == []

    resp = app.speak({"text": THREE, "part": 0})
    assert resp.status_code == 200, resp.text
    assert [norm(part) for part, _, _ in speaker.calls] == [THREE_PARTS[0]]
