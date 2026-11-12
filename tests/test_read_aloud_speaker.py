"""Contract tests of `integrations.tts.Speaker.say` and of its wiring in `main.py` (slice read-aloud, Seam 2).

Written by the slice tester from the sealed contract `.engine/slices/read-aloud.md`, without the code.
The Cloud Text-to-Speech client is `FakeTTS`: it records the endpoint it was built with and every call.
"""

import importlib
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.cloud import firestore, texttospeech, texttospeech_v1

from mamamemory.http import app as app_module
from mamamemory.integrations.tts import Speaker
from tests.read_aloud_world import EU, FakeTTS
from tests.test_entrypoint import environ

T0 = datetime(2026, 11, 9, 9, 7, 0, tzinfo=UTC)
DEADLINE = T0 + timedelta(seconds=10)


def at(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


def speaker(tts: FakeTTS, call_timeout_s: float = 10.0) -> Speaker:
    return Speaker(tts.factory, endpoint=EU, call_timeout_s=call_timeout_s)


def refused(call: Callable[[], Any]) -> BaseException:
    """The error `call` raises; the skeleton's `NotImplementedError` does not count."""
    with pytest.raises(Exception) as caught:
        call()
    assert not isinstance(caught.value, NotImplementedError), caught.value
    return caught.value


# ------------------------------------------------------------------ Seam 2


def test_say_returns_the_audio_of_the_one_part_it_sent() -> None:
    tts = FakeTTS(b"OggS-audio-of-the-part")
    audio = speaker(tts).say("Завтра о десятій нотаріус.", "uk", deadline=DEADLINE, now=at(T0))
    assert audio == b"OggS-audio-of-the-part"
    assert len(tts.requests) == 1
    assert tts.requests[0].input.text == "Завтра о десятій нотаріус."


def test_say_asks_for_kore_gemini_tts_in_uk_ua_as_ogg_opus() -> None:
    tts = FakeTTS()
    speaker(tts).say("Так.", "uk", deadline=DEADLINE, now=at(T0))
    request = tts.requests[0]
    assert request.voice.language_code == "uk-UA"
    assert request.voice.name == "Kore"
    assert request.voice.model_name == "gemini-2.5-flash-tts"
    assert request.audio_config.audio_encoding == texttospeech.AudioEncoding.OGG_OPUS


def test_say_unknown_account_language_is_uk_ua() -> None:
    tts = FakeTTS()
    say = speaker(tts).say
    say("Так.", "xx", deadline=DEADLINE, now=at(T0))
    say("Так.", "", deadline=DEADLINE, now=at(T0))
    assert [r.voice.language_code for r in tts.requests] == ["uk-UA", "uk-UA"]


def test_say_calls_with_timeout_call_timeout_s() -> None:
    tts = FakeTTS()
    speaker(tts, call_timeout_s=7.5).say("Так.", "uk", deadline=DEADLINE, now=at(T0))
    assert tts.timeouts == [7.5]


def test_client_is_built_lazily_once_for_the_endpoint() -> None:
    tts = FakeTTS()
    built = speaker(tts)
    assert tts.endpoints == []
    built.say("Перша.", "uk", deadline=DEADLINE, now=at(T0))
    built.say("Друга.", "uk", deadline=DEADLINE, now=at(T0))
    assert tts.endpoints == [EU]
    assert len(tts.requests) == 2


def test_deadline_reached_or_past_is_an_error_without_a_call() -> None:
    tts = FakeTTS()
    built = speaker(tts)
    refused(lambda: built.say("Так.", "uk", deadline=DEADLINE, now=at(DEADLINE)))
    refused(lambda: built.say("Так.", "uk", deadline=DEADLINE, now=at(DEADLINE + timedelta(seconds=1))))
    assert tts.requests == []
    # A moment before the deadline the call is made.
    built.say("Так.", "uk", deadline=DEADLINE, now=at(DEADLINE - timedelta(milliseconds=1)))
    assert len(tts.requests) == 1


def test_main_builds_the_speaker_from_tts_endpoint_and_call_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in environ(CALL_TIMEOUT_S="9").items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(firestore, "Client", MagicMock(name="firestore.Client"))
    tts = FakeTTS()
    monkeypatch.setattr(texttospeech, "TextToSpeechClient", tts.factory)
    monkeypatch.setattr(texttospeech_v1, "TextToSpeechClient", tts.factory)
    built: list[dict[str, Any]] = []
    original = app_module.create_app

    def recording(*args: Any, **kwargs: Any) -> Any:
        built.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(app_module, "create_app", recording)
    sys.modules.pop("mamamemory.main", None)
    try:
        importlib.import_module("mamamemory.main")
    finally:
        sys.modules.pop("mamamemory.main", None)

    assert len(built) == 1
    made = built[0].get("speaker")
    assert isinstance(made, Speaker), made
    now = datetime.now(UTC)
    made.say("Так.", "uk", deadline=now + timedelta(minutes=1), now=lambda: datetime.now(UTC))
    assert tts.endpoints == ["eu-texttospeech.googleapis.com"]
    assert tts.timeouts == [9]
