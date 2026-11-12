"""Contract tests of `integrations.ai.speech` (slice voice-to-text, Seam 1).

Written by the slice tester from the sealed contract `.engine/slices/voice-to-text.md`, without the code.
The real `speech` runs on a real `google-genai` Vertex client whose HTTP transport is substituted
(`httpx.MockTransport`): what goes over the wire is checked, not what a mock was told to return.
"""

import base64
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

from mamamemory.config import ModelChoice
from mamamemory.errors import AudioRejected
from mamamemory.integrations.ai import speech
from tests.test_one_task_planning import make_config

AUDIO = b"OggS\x00\x02fake-opus-bytes-\xff\xfe\x00\x01"
SAID = "Подзвонити д-ру Müller у п'ятницю о 10:15"


class Gemini:
    """The Vertex endpoint behind a real `google-genai` client. Each answer is a text (200), an int
    (that HTTP status) or an exception (raised by the transport). The last answer repeats."""

    def __init__(self, *answers: str | int | Exception) -> None:
        self.answers = list(answers) or [SAID]
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((str(request.url), json.loads(request.content or b"{}")))
        answer = self.answers[min(len(self.requests) - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx.Response(
                answer, json={"error": {"code": answer, "message": "boom", "status": "INTERNAL"}}
            )
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": answer}]}}]}
        )

    def client(self) -> Any:
        return genai.Client(
            vertexai=True,
            project="pocket-lawyer-431614",
            location="eu",
            credentials=Credentials("at-test"),
            http_options=types.HttpOptions(httpx_client=httpx.Client(transport=httpx.MockTransport(self))),
        )


def find(obj: Any, *keys: str) -> list[Any]:
    """Every value under any of `keys` anywhere in a JSON tree (the wire mixes camelCase and snake_case)."""
    found: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys:
                found.append(value)
            found += find(value, *keys)
    elif isinstance(obj, list):
        for item in obj:
            found += find(item, *keys)
    return found


def inline_parts(body: dict[str, Any]) -> list[tuple[str, bytes]]:
    """(mime type, raw bytes) of every inline-data part of a generateContent request body."""
    parts = []
    for blob in find(body.get("contents"), "inlineData", "inline_data"):
        mime = (find(blob, "mimeType", "mime_type") or [None])[0]
        data = (find(blob, "data") or [""])[0]
        parts.append((mime, b64(data) if isinstance(data, str) else bytes(data)))
    return parts


def b64(data: str) -> bytes:
    """Standard or URL-safe base64, padded or not (the wire form is the client's choice)."""
    data = data.replace("+", "-").replace("/", "_")
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def later(seconds: int = 60) -> datetime:
    # `speech` takes no clock: its deadline is read against the wall clock.
    return datetime.now(UTC) + timedelta(seconds=seconds)


def call(gemini: Gemini, mime: str = "audio/ogg", **over: Any) -> Callable[[], str]:
    config = over.pop("config", make_config())
    audio = over.pop("audio", AUDIO)
    return lambda: speech(
        audio, mime, language=config.language, deadline=later(), client=gemini.client(), config=config
    )


# ------------------------------------------------------------------ Seam 1


def test_speech_returns_recognised_text() -> None:
    gemini = Gemini(SAID)
    assert call(gemini)() == SAID
    assert len(gemini.requests) == 1


def test_speech_sends_audio_as_inline_data_with_its_mime_type() -> None:
    gemini = Gemini(SAID)
    call(gemini, "audio/ogg")()
    _, body = gemini.requests[0]
    assert inline_parts(body) == [("audio/ogg", AUDIO)]


def test_speech_strips_mime_parameters_before_sending() -> None:
    for sent, expected in (("audio/webm;codecs=opus", "audio/webm"), ("audio/ogg;codecs=opus", "audio/ogg")):
        gemini = Gemini(SAID)
        assert call(gemini, sent)() == SAID, sent
        _, body = gemini.requests[0]
        assert inline_parts(body) == [(expected, AUDIO)], sent


def test_speech_uses_model_and_thinking_level_of_transcribe_from_config() -> None:
    # The default: gemini-3.8-flash.
    gemini = Gemini(SAID)
    call(gemini)()
    url, _ = gemini.requests[0]
    assert url.endswith("/models/gemini-3.8-flash:generateContent"), url
    # Whatever config names for "transcribe" is what is called, with its thinking level.
    config = make_config()
    config = replace(
        config, models={**config.models, "transcribe": ModelChoice("gemini-transcribe-test", "LOW")}
    )
    gemini = Gemini(SAID)
    call(gemini, config=config)()
    url, body = gemini.requests[0]
    assert url.endswith("/models/gemini-transcribe-test:generateContent"), url
    assert find(body, "thinkingLevel", "thinking_level") == ["LOW"]


def test_speech_empty_or_blank_model_answer_is_audio_rejected() -> None:
    for answer in ("", "   "):
        gemini = Gemini(answer)
        with pytest.raises(AudioRejected):
            call(gemini)()
