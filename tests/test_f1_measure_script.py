"""Contract tests of the slice skeleton-measure: the script `scripts/measure_f1.py`.

Written by the slice tester from the sealed contract `.engine/slices/skeleton-measure.md` («Seam (contract)»,
«Hardest seams» Seam 1), without the code. The script runs in-process over the 10 recordings of PoC 2 with
`integrations.ai.speech` replaced by a spy (`tests/f1_measure_world.py`); every expected count is written by
hand from `SENTENCES` of `poc/poc2_voice.py` (10 sentences, 29 keywords).
"""

import sys
from datetime import timedelta

import pytest
from google.genai import errors

from mamamemory.errors import AudioRejected
from mamamemory.integrations.ai import DeadlinePassed
from tests.f1_measure_world import AUDIO_DIR, FULL, PROJECT, Answer, poc2_voice, run_measure

# Three heard in other letter case or spacing, three missed: «Arztbrief», «Ramipril», «двадцять три».
MIXED: dict[int, Answer] = {
    **FULL,
    1: "передзвонити пані шмідт щодо аналізу hba1c у четвер о десятій.",
    2: "У пані Мюллер TSH чотири і девʼять, повторити через шість   тижнів.",
    4: "Пані Шнайдер принесла артцбріф з кардіології, переглянути дозування Раміприл.",
    9: "Вітамін D 23 у пана Ціммерманна, продовжити Vigantol.",
}


def failing() -> dict[int, Answer]:
    return {
        **FULL,
        3: AudioRejected("the model heard nothing"),
        5: DeadlinePassed("no time left for the model call"),
        7: errors.ServerError(503, {"error": {"message": "down", "status": "UNAVAILABLE"}}),
    }


def test_calls_production_speech_on_each_recording(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(FULL))
    assert [call.number for call in run.calls] == list(range(1, 11))
    for call in run.calls:
        assert call.audio == (AUDIO_DIR / f"{call.number:02d}.ogg").read_bytes()
        assert call.mime == "audio/ogg"
        assert call.kwargs["language"] == "uk"
        assert call.kwargs.get("config") is None, "speech must take the default models (config=None)"


def test_client_is_vertex_eu_and_goes_to_speech(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(FULL))
    assert run.clients, "no genai.Client was built"
    for client in run.clients:
        assert client.kwargs.get("vertexai") is True
        assert client.kwargs.get("project") == PROJECT
        assert client.kwargs.get("location") == "eu"
    for call in run.calls:
        assert call.kwargs["client"] in run.clients
    assert all(not client.models.direct for client in run.clients)


def test_does_not_import_main(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delitem(sys.modules, "mamamemory.main", raising=False)
    run = run_measure(monkeypatch, capsys, dict(FULL))
    assert len(run.calls) == 10
    assert "mamamemory.main" not in sys.modules


def test_deadline_is_thirty_seconds_ahead(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(FULL))
    assert len(run.calls) == 10
    for call in run.calls:
        ahead = call.kwargs["deadline"] - call.at
        assert timedelta(seconds=29) <= ahead <= timedelta(seconds=30), f"recording {call.number}: {ahead}"


def test_prints_heard_text_and_missing_keywords(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(MIXED))
    for number in range(1, 11):
        heard = MIXED[number]
        assert isinstance(heard, str)
        assert heard.strip() in run.out, f"the heard text of recording {number} is not printed"
    for missing in ["Arztbrief", "Ramipril", "двадцять три"]:
        assert missing in run.out, f"the missing keyword «{missing}» is not printed"


def test_heard_counts_keywords_case_insensitively(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(MIXED))
    assert run.line("HEARD:") == "HEARD: 26 of 29 keywords"


def test_keywords_come_from_poc2_sentences(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = poc2_voice(monkeypatch)
    monkeypatch.setattr(module, "SENTENCES", [(f"речення {n}", ["ключ"]) for n in range(1, 11)])
    answers: dict[int, Answer] = {n: "ключ" if n <= 4 else "нічого" for n in range(1, 11)}
    run = run_measure(monkeypatch, capsys, answers)
    assert run.line("HEARD:") == "HEARD: 4 of 10 keywords"


def test_seconds_line_gives_min_median_max(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, dict(FULL), pause=lambda number: 0.6 if number == 10 else 0.0)
    numbers = run.numbers("SECONDS:")
    assert len(numbers) == 3, run.line("SECONDS:")
    low, median, high = numbers
    assert low < 0.3
    assert median < 0.3
    assert 0.5 <= high < 1.5


def test_all_ten_give_exit_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    run = run_measure(monkeypatch, capsys, dict(FULL))
    assert run.line("MEASURED:") == "MEASURED: 10 of 10 calls"
    assert run.line("HEARD:") == "HEARD: 29 of 29 keywords"
    assert run.code in (0, None)


def test_failed_call_is_named_and_loop_goes_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, failing())
    assert [call.number for call in run.calls] == list(range(1, 11))
    for name in ["AudioRejected", "DeadlinePassed", "ServerError"]:
        assert name in run.out, f"the failure {name} is not printed by its type name"
    for number in (8, 9, 10):
        assert FULL[number] in run.out, f"recording {number} after the failures is not printed"


def test_failures_give_exit_one_with_summaries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = run_measure(monkeypatch, capsys, failing())
    assert run.line("MEASURED:") == "MEASURED: 7 of 10 calls"
    assert run.line("HEARD:").endswith("keywords")
    assert len(run.numbers("SECONDS:")) == 3
    assert run.code == 1
