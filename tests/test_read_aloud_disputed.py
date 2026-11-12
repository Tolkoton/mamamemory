"""Disputed contract tests of the slice read-aloud: each takes one reading of a question to the contract
(`.engine/slices/read-aloud.md`), named in its docstring. Sealed only after the slice planner answers.

Written by the slice tester from the sealed contract, without the code.
"""

import pytest
from google.api_core.exceptions import ServiceUnavailable

from mamamemory.integrations.tts import parts
from tests.read_aloud_world import (
    FAILED_SPEAK,
    FakeSpeaker,
    SpeakApp,
    norm,
    sentence,
    word,
)


def test_two_sentences_of_exactly_100_with_the_space_are_one_part() -> None:
    """Q1: a part's length counts the space between its sentences, and 100 itself is allowed."""
    a, b = sentence(1, 50), sentence(2, 49)
    assert [norm(p) for p in parts(f"{a} {b}")] == [f"{a} {b}"]


def test_two_sentences_of_101_with_the_space_are_two_parts() -> None:
    """Q1: 50 + 1 + 50 = 101 is over 100, so the second sentence starts a new part."""
    a, b = sentence(1, 50), sentence(2, 50)
    assert [norm(p) for p in parts(f"{a} {b}")] == [a, b]


def test_whitespace_only_text_gives_no_parts() -> None:
    """Q3: «порожній» is read after the stripping of whitespace."""
    assert parts("  \n\t \n") == []


def test_long_sentence_is_split_on_words_greedily() -> None:
    """Q4: the word split of a sentence over 100 is greedy, like the packing of sentences."""
    words = [word(i) for i in range(44)]
    text = " ".join(words) + " кінець."
    expected = [" ".join(words[k : k + 11]) for k in range(0, 44, 11)] + ["кінець."]  # 11 × 9 − 1 = 98
    assert [norm(p) for p in parts(text)] == expected


def test_text_of_exactly_10000_is_accepted() -> None:
    """Q5: «до 10 000 знаків» includes 10 000."""
    speaker = FakeSpeaker()
    resp = SpeakApp(speaker).speak({"text": "ж" * 10000, "part": 0})
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-parts"] == "100"


def test_part_as_json_float_is_400() -> None:
    """Q6: `1.0` in JSON is not a «JSON-ціле»."""
    speaker = FakeSpeaker()
    resp = SpeakApp(speaker).speak({"text": "Перше речення. Друге речення.", "part": 0.0})
    assert resp.status_code == 400
    assert resp.json() == {"error": FAILED_SPEAK}
    assert speaker.calls == []


def test_tts_error_log_line_names_the_error_type(
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Q7: «рядок журналу лише з типом помилки» names the class of the error TTS raised."""
    speaker = FakeSpeaker(fail=ServiceUnavailable("tts is down"))
    app = SpeakApp(speaker)
    capfd.readouterr()
    resp = app.speak({"text": "Так.", "part": 0})
    assert resp.status_code == 502
    out, err = capfd.readouterr()
    assert "ServiceUnavailable" in out + err + caplog.text
