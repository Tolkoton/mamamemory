"""Contract test of `POST /api/speak` over 10 000 characters (slice speak-control): `SpeakTooLong`.

Written by the slice tester from the sealed contract `.engine/slices/speak-control.md`, without the code.
The log is read wherever it goes: stdout, stderr and the `logging` records.
"""

import pytest

from tests.read_aloud_world import FakeSpeaker, SpeakApp

SECRET_WORD = "Шмідтоватаємниця"


def too_long_text() -> str:
    """10 001 characters that carry a word no log line may show."""
    head = f"Мама записалася до {SECRET_WORD} на п'ятницю. "
    return head + "ж" * (10001 - len(head))


def log_lines(capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> list[str]:
    out, err = capfd.readouterr()
    return [line for line in (out + "\n" + err + "\n" + caplog.text).splitlines() if line.strip()]


def test_speak_over_10000_characters_writes_a_speak_too_long_line_without_the_text(
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    text = too_long_text()
    assert len(text) == 10001
    speaker = FakeSpeaker()
    app = SpeakApp(speaker)
    capfd.readouterr()
    caplog.clear()

    resp = app.speak({"text": text, "part": 0})
    assert resp.status_code == 400
    assert speaker.calls == []

    lines = log_lines(capfd, caplog)
    assert any("SpeakTooLong" in line for line in lines), lines
    for line in lines:
        assert SECRET_WORD not in line, line
        assert "ж" * 20 not in line, line[:200]
