"""The world of the contract tests of the slice skeleton-measure: `scripts/measure_f1.py` run in-process.

Written by the slice tester from the sealed contract `.engine/slices/skeleton-measure.md` («Seam (contract)»,
«Hardest seams», «Exit criterion»), without the code. `integrations.ai.speech` is replaced by a spy that
answers per recording (the recording is told by its bytes, read from `poc/out/poc2-audio/NN.ogg`);
`google.genai.Client` is replaced by a fake that records how it was built and refuses a direct model call.
Nothing here computes the numbers the script must print: the tests write them by hand.
"""

import importlib
import importlib.util
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from google import genai

from mamamemory.integrations import ai

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_f1.py"
POC = ROOT / "poc"
AUDIO_DIR = POC / "out" / "poc2-audio"
AUDIO: dict[bytes, int] = {(AUDIO_DIR / f"{n:02d}.ogg").read_bytes(): n for n in range(1, 11)}
PROJECT = "measure-test-project"

# What a perfect ear hears: every sentence of PoC 2 as it was said.
FULL = {
    1: "Передзвонити пані Шмідт щодо аналізу HbA1c у четвер о десятій.",
    2: "У пані Мюллер TSH чотири і девʼять, повторити через шість тижнів.",
    3: "Записати пана Беккера на УЗД щитоподібної залози в лікарні Санкт-Катарінен.",
    4: "Пані Шнайдер принесла Arztbrief з кардіології, переглянути дозування Ramipril.",
    5: "Зараз я працюю над договором купівлі городу, пункт сім про межі ділянки.",
    6: "Треба цього тижня купити насіння, подзвонити нотаріусу і забрати Überweisung для пані Вагнер.",
    7: "Феритин у пані Кох вісім, призначити залізо і контроль через три місяці.",
    8: "Що я робила з договором учора ввечері?",
    9: "Вітамін D двадцять три у пана Ціммерманна, продовжити Vigantol.",
    10: "Пані Майєр і пані Маєр — різні пацієнтки, не переплутати аналізи.",
}

Answer = str | BaseException


@dataclass
class Call:
    number: int
    audio: bytes
    mime: str
    kwargs: dict[str, Any]
    at: datetime


class FakeModels:
    def __init__(self) -> None:
        self.direct: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.direct.append(kwargs)
        raise AssertionError("the script called the model itself, not through integrations.ai.speech")


class FakeClient:
    built: list["FakeClient"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args, self.kwargs = args, kwargs
        self.models = FakeModels()
        FakeClient.built.append(self)


@dataclass
class Run:
    code: int | str | None
    out: str
    calls: list[Call] = field(default_factory=list)
    clients: list[FakeClient] = field(default_factory=list)

    def line(self, prefix: str) -> str:
        found = [line.strip() for line in self.out.splitlines() if line.strip().startswith(prefix)]
        assert found, f"the output has no line starting with {prefix!r}:\n{self.out}"
        return found[-1]

    def numbers(self, prefix: str) -> list[float]:
        return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", self.line(prefix)[len(prefix) :])]


def run_measure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answers: dict[int, Answer],
    pause: Callable[[int], float] = lambda number: 0.0,
) -> Run:
    """Load the script fresh and run its `main()`; recording N answers `answers[N]` (text, or raised)."""
    calls: list[Call] = []

    def spy(*args: Any, **kwargs: Any) -> str:
        audio = args[0] if args else kwargs.pop("audio")
        mime = args[1] if len(args) > 1 else kwargs.pop("mime")
        number = AUDIO[audio]
        calls.append(Call(number, audio, mime, dict(kwargs), datetime.now(UTC)))
        time.sleep(pause(number))
        answer = answers[number]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    FakeClient.built = []
    monkeypatch.setattr(ai, "speech", spy)
    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setenv("GCP_PROJECT", PROJECT)
    monkeypatch.setenv("VERTEX_LOCATION", "eu")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setattr(sys, "path", list(sys.path))
    module = load_script()
    try:
        code: int | str | None = module.main()
    except SystemExit as stop:
        code = stop.code
    out = capsys.readouterr().out
    return Run(code, out, calls, list(FakeClient.built))


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_f1_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def poc2_voice(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The PoC 2 module, imported the way the contract says the script imports it (`poc/` on `sys.path`)."""
    monkeypatch.syspath_prepend(str(POC))
    return importlib.import_module("poc2_voice")
