"""Disputed contract tests of `POST /api/transcribe` (slice voice-to-text): each depends on a question to
the contract (Q1-Q3 of the tester's hand-in) and is not sealed until the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/voice-to-text.md`, without the code.
"""

from dataclasses import replace

from tests.test_one_task_planning import make_config
from tests.test_voice_http import FAILED, Voice, small_limit
from tests.test_voice_speech import SAID, Gemini, inline_parts


def test_body_exactly_at_limit_is_accepted() -> None:
    # Q1: «обриває, щойно перевищено» / «понад межу» — exactly max_audio_bytes is not over it.
    voice = Voice(Gemini(SAID), config=small_limit())
    resp = voice.post(b"a" * 1000, "audio/webm")
    assert resp.status_code == 200
    assert resp.json() == {"text": SAID}


def test_deadline_already_past_is_502_even_if_model_would_answer() -> None:
    # Q2: deadline = start + REQUEST_TIMEOUT_S − 2 × CALL_TIMEOUT_S; here 10 − 2×10 = −10 s.
    config = replace(make_config(), request_timeout_s=10, call_timeout_s=10)
    voice = Voice(Gemini(SAID), config=config)
    resp = voice.post(b"some audio bytes", "audio/webm")
    assert resp.status_code == 502
    assert resp.json() == {"error": FAILED}


def test_mime_parameters_after_space_are_stripped_too() -> None:
    # Q3: «з параметрами на кшталт `;codecs=opus` — зрізаються»: also `; codecs=opus` (OWS, RFC 9110).
    voice = Voice(Gemini(SAID))
    resp = voice.post(b"some audio bytes", "audio/ogg; codecs=opus")
    assert resp.status_code == 200
    assert resp.json() == {"text": SAID}
    _, body = voice.gemini.requests[0]
    assert inline_parts(body) == [("audio/ogg", b"some audio bytes")]
