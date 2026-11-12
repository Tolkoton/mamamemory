"""Disputed contract test of slice speak-control: what the `SpeakTooLong` log line carries.

Written by the slice tester from the sealed contract `.engine/slices/speak-control.md`, without the code.
The name leads with the id of the question to the contract; the file is sealed after the planner answers.
"""

import pytest

from tests.read_aloud_world import FakeSpeaker, SpeakApp


def test_Q1_speak_too_long_line_carries_the_status_400(
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    app = SpeakApp(FakeSpeaker())
    capfd.readouterr()
    caplog.clear()

    resp = app.speak({"text": "ж" * 10001, "part": 0})
    assert resp.status_code == 400

    out, err = capfd.readouterr()
    lines = [line for line in (out + "\n" + err + "\n" + caplog.text).splitlines() if line.strip()]
    marked = [line for line in lines if "SpeakTooLong" in line]
    assert marked, lines
    assert any("400" in line for line in marked), marked
