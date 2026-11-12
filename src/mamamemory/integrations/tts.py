"""Озвучення відповіді (F5 S3, `integrations.tts`): текст → частини до `PART_CHARS` знаків → аудіо OGG Opus.

Gemini-TTS через `eu-texttospeech.googleapis.com`, голос Kore. Один виклик на частину: довгий
текст за один виклик не встигає (P-TTS-LONG). Не робить: автоозвучення, кешування, вибору голосу.
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech

PART_CHARS = 100
VOICE, MODEL = "Kore", "gemini-2.5-flash-tts"
TTS_LANGUAGES = {"uk": "uk-UA"}
DEFAULT_TTS_LANGUAGE = "uk-UA"

SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\s*\n\s*")


class DeadlinePassed(Exception):
    """Дедлайн запиту минув — виклику TTS не було."""


def parts(text: str) -> list[str]:
    """Детерміновані частини всього тексту (без обрізання, speak-control): жадібне пакування речень у частини
    ≤ `PART_CHARS`."""
    units = [unit for sentence in _sentences(text.strip()) for unit in _units(sentence)]
    return _pack(units)


def _sentences(text: str) -> list[str]:
    return [sentence for sentence in (s.strip() for s in SENTENCE_SPLIT.split(text)) if sentence]


def _units(sentence: str) -> list[str]:
    """Речення ≤ `PART_CHARS` — саме; довше — його слова, а слово довше — шматки по `PART_CHARS`."""
    if len(sentence) <= PART_CHARS:
        return [sentence]
    return [word[i : i + PART_CHARS] for word in sentence.split() for i in range(0, len(word), PART_CHARS)]


def _pack(units: list[str]) -> list[str]:
    """Жадібно: сусідні шматки через пробіл в одну частину, поки вона не довша за `PART_CHARS`."""
    packed: list[str] = []
    for unit in units:
        if packed and len(packed[-1]) + 1 + len(unit) <= PART_CHARS:
            packed[-1] = f"{packed[-1]} {unit}"
        else:
            packed.append(unit)
    return packed


class Speaker:
    def __init__(self, client_factory: Callable[..., Any], *, endpoint: str, call_timeout_s: float) -> None:
        self._client_factory, self._endpoint, self._call_timeout_s = client_factory, endpoint, call_timeout_s
        self._built: Any = None

    def say(self, part: str, language: str, *, deadline: datetime, now: Callable[[], datetime]) -> bytes:
        """Одна частина → аудіо OGG Opus; дедлайн минув — помилка без виклику."""
        if now() >= deadline:
            raise DeadlinePassed()
        response = self._client().synthesize_speech(
            input=texttospeech.SynthesisInput(text=part),
            voice=texttospeech.VoiceSelectionParams(
                language_code=TTS_LANGUAGES.get(language, DEFAULT_TTS_LANGUAGE), name=VOICE, model_name=MODEL
            ),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS),
            timeout=self._call_timeout_s,
        )
        return bytes(response.audio_content)

    def _client(self) -> Any:
        if self._built is None:
            self._built = self._client_factory(client_options=ClientOptions(api_endpoint=self._endpoint))
        return self._built
