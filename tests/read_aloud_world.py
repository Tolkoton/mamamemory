"""Test helpers of the slice read-aloud: hand-written texts, a fake Cloud Text-to-Speech client, a fake
`Speaker` for the HTTP route, and the app signed in as `SUB`.

Written by the slice tester from the sealed contract `.engine/slices/read-aloud.md`, without the code.
Every expected part is written by hand from the contract. Parts are compared with their whitespace made
single spaces: the contract keeps text «без втрат (крім пробілів і переносів на стиках)» and does not say
whether a line break inside a part stays a line break.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient
from google.cloud import texttospeech

from mamamemory import access
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.integrations.tts import Speaker
from tests.test_one_task_http import MAMA, SUB, Clock, FakeGoogle
from tests.test_one_task_planning import NOW, FakeAI, FakeCalendar, make_config

EU = "eu-texttospeech.googleapis.com"
FAILED_SPEAK = "Не вдалося озвучити."

# Three sentences: 71, 42 and 47 characters, ended by «!», «?» and «…».
S71 = "Завтра о десятій нотаріус, документи вже лежать у синій папці на столі!"
S42 = "Чи взяти з собою копію паспорта і довідку?"
S47 = "Візьміть обидві, вони знадобляться пізніше теж…"
THREE = f"{S71} {S42} {S47}"
"""Parts: [S71] (71 + 1 + 42 = 114 is over 100), then [S42 S47] (42 + 1 + 47 = 90)."""
THREE_PARTS = [S71, f"{S42} {S47}"]

# The week plan: 15 lines of 19 characters, no punctuation at all, 299 characters in all.
WEEK_LINES = [
    "Пн 09:00 аптека лік",
    "Пн 10:00 нотаріус Ф",
    "Пн 15:00 дзвінок Ол",
    "Вт 09:30 лікар Шмід",
    "Вт 12:00 пошта лист",
    "Вт 16:00 ринок овоч",
    "Ср 10:00 банк карта",
    "Ср 14:00 звіт у ДПС",
    "Ср 18:00 Йоганн веч",
    "Чт 08:30 аналіз кро",
    "Чт 11:00 поліс авто",
    "Пт 09:00 перукар Ія",
    "Пт 13:00 магазин хл",
    "Сб 10:00 прибирання",
    "Нд 12:00 обід дітям",
]
WEEK = "\n".join(WEEK_LINES)
"""Five lines fill a part (5 × 19 + 4 = 99); a sixth would make 119. So three parts of five lines."""
WEEK_PARTS = [" ".join(WEEK_LINES[0:5]), " ".join(WEEK_LINES[5:10]), " ".join(WEEK_LINES[10:15])]


def sentence(i: int, length: int, end: str = ".") -> str:
    """A sentence of exactly `length` characters: «Речення 007 » + «а» × … + `end` (no inner boundary)."""
    head = f"Речення {i:03d} "
    return head + "а" * (length - len(head) - len(end)) + end


def word(i: int) -> str:
    """An 8-character word: «слово» and three digits."""
    return f"слово{i:03d}"


def norm(text: str) -> str:
    """Whitespace made single spaces, the ends stripped."""
    return " ".join(text.split())


def bare(text: str) -> str:
    """The text without any whitespace."""
    return "".join(text.split())


def glued(parts: list[str]) -> str:
    """The parts glued, without any whitespace: what «без втрат (крім пробілів і переносів)» keeps."""
    return "".join(bare(p) for p in parts)


# ------------------------------------------------------------------ Cloud Text-to-Speech fake


class FakeTTS:
    """`client_factory` for `Speaker`: records each build's endpoint and each `synthesize_speech` call.

    Takes the client options as `client_options=` or first positional, a `ClientOptions` or a dict; takes
    the call as `request=` (message or dict) or as `input=`, `voice=`, `audio_config=`."""

    def __init__(self, audio: bytes = b"OggS-fake-audio") -> None:
        self.audio = audio
        self.endpoints: list[str | None] = []
        self.requests: list[texttospeech.SynthesizeSpeechRequest] = []
        self.timeouts: list[Any] = []

    def factory(self, *args: Any, **kwargs: Any) -> "FakeTTS":
        options = kwargs.get("client_options", args[0] if args else None)
        if isinstance(options, dict):
            self.endpoints.append(options.get("api_endpoint"))
        else:
            self.endpoints.append(getattr(options, "api_endpoint", None))
        return self

    def synthesize_speech(
        self,
        request: Any = None,
        *,
        input: Any = None,
        voice: Any = None,
        audio_config: Any = None,
        timeout: Any = None,
        **_: Any,
    ) -> texttospeech.SynthesizeSpeechResponse:
        if request is None:
            request = texttospeech.SynthesizeSpeechRequest(
                input=input, voice=voice, audio_config=audio_config
            )
        elif isinstance(request, dict):
            request = texttospeech.SynthesizeSpeechRequest(request)
        self.requests.append(request)
        self.timeouts.append(timeout)
        return texttospeech.SynthesizeSpeechResponse(audio_content=self.audio)


# ------------------------------------------------------------------ the HTTP route


def _no_client() -> Any:
    raise AssertionError("the fake speaker builds no client")


class FakeSpeaker(Speaker):
    """A `Speaker` whose `say` records (part, language, deadline) and answers `OggS:<part>`, or raises."""

    def __init__(self, fail: BaseException | None = None) -> None:
        super().__init__(_no_client, endpoint=EU, call_timeout_s=10.0)
        self.fail = fail
        self.calls: list[tuple[str, str, datetime]] = []

    def say(self, part: str, language: str, *, deadline: datetime, now: Callable[[], datetime]) -> bytes:
        self.calls.append((part, language, deadline))
        if self.fail is not None:
            raise self.fail
        return b"OggS:" + part.encode()


class SpeakApp:
    """The app at `NOW` (a fixed clock), signed in as `SUB`, with a model and calendar fake for the
    other routes and the given speaker (`None` → none)."""

    def __init__(self, speaker: Speaker | None) -> None:
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
        self.calendar = FakeCalendar()
        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
            speaker=speaker,
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        self.client.cookies.set(
            "mm_session", access.session_cookie_value(SUB, MAMA, NOW, key=self.config.session_key)
        )

    def speak(self, body: Any) -> httpx.Response:
        resp: httpx.Response = self.client.post("/api/speak", json=body)
        return resp
