"""Disputed contract test of the slice skeleton-measure: `HEARD` when calls fail (question Q1 of the hand-in).

Reading taken: N stays 29 («N = 29, як у PoC 2») whatever the calls give, and the keywords of a recording
whose call failed count as not heard. Not sealed until the slice planner answers.
"""

import pytest
from google.genai import errors

from mamamemory.errors import AudioRejected
from mamamemory.integrations.ai import DeadlinePassed
from tests.f1_measure_world import FULL, Answer, run_measure


def test_heard_keeps_n_29_when_calls_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers: dict[int, Answer] = {
        **FULL,
        3: AudioRejected("the model heard nothing"),
        5: DeadlinePassed("no time left for the model call"),
        7: errors.ServerError(503, {"error": {"message": "down", "status": "UNAVAILABLE"}}),
    }
    run = run_measure(monkeypatch, capsys, answers)
    assert run.line("HEARD:") == "HEARD: 20 of 29 keywords"
