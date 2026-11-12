"""Contract tests of `POST /api/transcribe` and of I1 (slice voice-to-text, Seams 2 and 4).

Written by the slice tester from the sealed contract `.engine/slices/voice-to-text.md`, without the code.
The app gets a real `AI` whose `google-genai` client has a substituted HTTP transport (`Gemini`).
"""

import asyncio
import sys
import tomllib
from collections.abc import MutableMapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient

from mamamemory import access
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore
from tests.test_one_task_http import MAMA, SUB, WEEK_S, FakeGoogle
from tests.test_one_task_planning import make_config
from tests.test_voice_speech import SAID, Gemini, inline_parts

NOT_HEARD = "Не почула, спробуйте ще раз."
FAILED = "Не вдалося, спробуйте ще раз."
ROOT = Path(__file__).resolve().parents[1]
BIG = 1_500_000  # over 1 MB (Starlette's spool threshold), under the 6 MB limit


class CountingStore(InMemoryStore):
    """`InMemoryStore` that counts every write after `counting` is switched on."""

    def __init__(self) -> None:
        super().__init__()
        self.counting = False
        self.writes = 0

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self.writes += self.counting
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Any) -> dict[str, Any] | None:
        self.writes += self.counting
        return super().transact(account_id, path, decide)


class Opens:
    """`sys.addaudithook` counting `open` events (builtins.open, io.open, os.open, tempfile) while on."""

    on = False
    events: list[tuple[Any, ...]] = []

    @classmethod
    def hook(cls, event: str, args: tuple[Any, ...]) -> None:
        if cls.on and event == "open":
            cls.events.append(args)


sys.addaudithook(Opens.hook)


class Voice:
    def __init__(self, gemini: Gemini | None = None, config: Config | None = None) -> None:
        # The app's clock reads the real time: `speech` compares its deadline with the wall clock.
        self.started = datetime.now(UTC)
        self.config = config or make_config()
        self.gemini = gemini or Gemini(SAID)
        self.store = CountingStore()
        self.store.set(
            SUB,
            access.TOKENS_PATH,
            access.tokens_document(
                Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
                self.started,
            ),
        )
        client = self.gemini.client()
        self.app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            lambda: datetime.now(UTC),
            ai=AI(lambda: client, self.config),
        )
        self.client = TestClient(
            self.app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        self.sign_in()

    def cookie(self, at: datetime | None = None) -> str:
        return access.session_cookie_value(SUB, MAMA, at or self.started, key=self.config.session_key)

    def sign_in(self, at: datetime | None = None) -> None:
        self.client.cookies.set("mm_session", self.cookie(at))

    def post(self, body: bytes, content_type: str | None = "audio/webm;codecs=opus") -> httpx.Response:
        headers = {"content-type": content_type} if content_type is not None else {}
        resp: httpx.Response = self.client.post("/api/transcribe", content=body, headers=headers)
        return resp


def small_limit() -> Config:
    return replace(make_config(), max_audio_bytes=1000)


# ------------------------------------------------------------------ Seam 2


def test_transcribe_returns_200_with_recognised_text_only() -> None:
    voice = Voice(Gemini(SAID))
    resp = voice.post(b"\x1a\x45\xdf\xa3 webm bytes", "audio/webm;codecs=opus")
    assert resp.status_code == 200
    assert resp.json() == {"text": SAID}
    _, body = voice.gemini.requests[0]
    assert inline_parts(body) == [("audio/webm", b"\x1a\x45\xdf\xa3 webm bytes")]


def test_transcribe_empty_body_is_400_not_heard() -> None:
    voice = Voice()
    resp = voice.post(b"")
    assert resp.status_code == 400
    assert resp.json() == {"error": NOT_HEARD}


def test_transcribe_body_over_limit_is_400_not_heard() -> None:
    voice = Voice(config=small_limit())
    resp = voice.post(b"a" * 1001)
    assert resp.status_code == 400
    assert resp.json() == {"error": NOT_HEARD}


def test_transcribe_stops_reading_body_once_over_limit() -> None:
    voice = Voice(config=small_limit())
    calls = 0
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls > 1000:  # 100 kB on offer, a hundred times the limit
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": b"a" * 100, "more_body": True}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/transcribe",
        "raw_path": b"/api/transcribe",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"audio/webm"),
            (b"cookie", f"mm_session={voice.cookie()}".encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 443),
    }
    asyncio.run(voice.app(scope, receive, send))
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 400
    # The limit (1000) is exceeded by the 11th chunk of 100 bytes; reading stops there.
    assert calls <= 12, calls
    assert voice.gemini.requests == []


def test_transcribe_type_outside_list_is_400_not_heard() -> None:
    voice = Voice()
    for content_type in (
        "audio/mpeg",
        "audio/mp4",
        "audio/wav",
        "text/plain",
        "application/octet-stream",
        "audio/webmx",
    ):
        resp = voice.post(b"some audio bytes", content_type)
        assert resp.status_code == 400, content_type
        assert resp.json() == {"error": NOT_HEARD}, content_type
    assert voice.gemini.requests == []


def test_transcribe_without_valid_session_is_401_without_location() -> None:
    voice = Voice()
    voice.client.cookies.clear()
    resp = voice.post(b"some audio bytes")
    assert resp.status_code == 401
    assert "location" not in resp.headers
    voice.sign_in(at=voice.started - timedelta(seconds=WEEK_S + 60))
    resp = voice.post(b"some audio bytes")
    assert resp.status_code == 401
    assert "location" not in resp.headers
    assert voice.gemini.requests == []


def test_transcribe_blank_model_answer_is_400_not_heard() -> None:
    for answer in ("", "   "):
        voice = Voice(Gemini(answer))
        resp = voice.post(b"some audio bytes")
        assert resp.status_code == 400, repr(answer)
        assert resp.json() == {"error": NOT_HEARD}, repr(answer)


def test_transcribe_model_or_transport_error_is_502_failed() -> None:
    for answer in (500, 503, httpx.ConnectError("down"), httpx.ReadTimeout("slow")):
        voice = Voice(Gemini(answer))
        resp = voice.post(b"some audio bytes")
        assert resp.status_code == 502, answer
        assert resp.json() == {"error": FAILED}, answer


def test_transcribe_model_call_is_repeated_at_most_once() -> None:
    voice = Voice(Gemini(500))
    resp = voice.post(b"some audio bytes")
    assert resp.status_code == 502
    assert 1 <= len(voice.gemini.requests) <= 2, len(voice.gemini.requests)


# ------------------------------------------------------------------ Seam 4


def test_transcribe_writes_nothing_to_store_on_success_or_error() -> None:
    for gemini, status in ((Gemini(SAID), 200), (Gemini(500), 502), (Gemini("  "), 400)):
        voice = Voice(gemini)
        voice.store.counting = True
        resp = voice.post(b"some audio bytes")
        assert resp.status_code == status
        assert voice.store.writes == 0, status


def test_transcribe_large_body_opens_no_file() -> None:
    voice = Voice(Gemini(SAID))
    body = b"\x00" * BIG
    voice.post(body)  # warm-up outside the window: lazy imports open .py files
    Opens.events.clear()
    Opens.on = True
    try:
        resp = voice.post(body)
    finally:
        Opens.on = False
    assert resp.status_code == 200
    assert Opens.events == []


def test_multipart_is_400_and_python_multipart_is_not_a_dependency() -> None:
    voice = Voice()
    resp = voice.client.post(
        "/api/transcribe", files={"audio": ("voice.webm", b"some audio bytes", "audio/webm")}
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": NOT_HEARD}
    assert voice.gemini.requests == []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = list(project["project"].get("dependencies", []))
    for group in project.get("dependency-groups", {}).values():
        declared += [d for d in group if isinstance(d, str)]
    assert not [d for d in declared if d.lower().replace("_", "-").startswith("python-multipart")]


# ------------------------------------------------------------------ I1


def test_I1_audio_never_reaches_a_file_object_or_the_store() -> None:
    over_limit = make_config().max_audio_bytes + 1
    cases: list[tuple[str, Gemini, bytes, str | None, int]] = [
        ("empty body", Gemini(SAID), b"", "audio/webm", 400),
        ("big, recognised", Gemini(SAID), b"\x01" * BIG, "audio/webm;codecs=opus", 200),
        ("big, model error", Gemini(500), b"\x02" * BIG, "audio/ogg", 502),
        ("big, model heard nothing", Gemini("   "), b"\x03" * BIG, "audio/ogg;codecs=opus", 400),
        ("over the limit", Gemini(SAID), b"\x04" * over_limit, "audio/webm", 400),
        ("big, type outside the list", Gemini(SAID), b"\x05" * BIG, "audio/mpeg", 400),
        ("big, multipart", Gemini(SAID), b"\x06" * BIG, "multipart/form-data; boundary=xyz", 400),
    ]
    for name, gemini, body, content_type, status in cases:
        voice = Voice(gemini)
        if content_type and content_type.startswith("multipart/"):
            body = (
                b'--xyz\r\nContent-Disposition: form-data; name="audio"; filename="v.webm"\r\n'
                b"Content-Type: audio/webm\r\n\r\n" + body + b"\r\n--xyz--\r\n"
            )
        voice.post(body, content_type)  # warm-up (a repeat of the same request) outside the window
        voice.store.counting = True
        Opens.events.clear()
        Opens.on = True
        try:
            resp = voice.post(body, content_type)
        finally:
            Opens.on = False
        assert resp.status_code == status, name
        assert Opens.events == [], (name, Opens.events[:3])
        assert voice.store.writes == 0, name
    # Without a session the audio is not taken in either.
    voice = Voice()
    voice.client.cookies.clear()
    voice.store.counting = True
    Opens.events.clear()
    Opens.on = True
    try:
        resp = voice.post(b"\x07" * BIG)
    finally:
        Opens.on = False
    assert resp.status_code == 401
    assert Opens.events == []
    assert voice.store.writes == 0
