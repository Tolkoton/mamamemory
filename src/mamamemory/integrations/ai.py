"""Gemini на Vertex AI (`integrations.ai`): структуровані відповіді для S3, `speech` — S2.

Клієнт `google-genai` будується один раз (ліниво, на перший виклик) і живе в цьому об'єкті.
Не робить: озвучення (F5), повторів понад один.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from google.genai import types

from mamamemory.config import DEFAULT_MODELS, Config, ModelChoice
from mamamemory.errors import AudioRejected


class AI:
    def __init__(self, client_factory: Callable[[], Any], config: Config) -> None:
        self._client_factory, self._client, self._config = client_factory, None, config

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Модель і рівень роздумів — з `config.models[task_type]`."""
        return self._generate(task_type, prompt, schema)

    def generate_json_with_file(
        self, task_type: str, prompt: str, schema: dict[str, Any], gs_uri: str, mime: str
    ) -> dict[str, Any]:
        """Як `generate_json`, з файлом `gs://` (фото, PDF) перед текстом (F3 S2)."""
        return self._generate(
            task_type, [types.Part.from_uri(file_uri=gs_uri, mime_type=mime), prompt], schema
        )

    def _generate(self, task_type: str, contents: Any, schema: dict[str, Any]) -> dict[str, Any]:
        choice = self._config.models[task_type]
        thinking = (
            types.ThinkingConfig(thinking_level=types.ThinkingLevel(choice.thinking_level))
            if (choice.thinking_level)
            else None
        )
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=thinking,
        )
        response = self._client_instance().models.generate_content(
            model=choice.model, contents=contents, config=config
        )
        answer = json.loads(response.text or "{}")
        return answer if isinstance(answer, dict) else {}

    def client(self) -> Any:
        """Клієнт `google-genai`, збудований один раз; `speech` (S2) бере його звідси."""
        return self._client_instance()

    def _client_instance(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client


ALLOWED_AUDIO = ("audio/webm", "audio/ogg")


def speech(
    audio: bytes, mime: str, *, language: str, deadline: datetime, client: Any, config: Config | None = None
) -> str:
    """Розпізнаний текст звуку (S2): Gemini з `models["transcribe"]`, звук вбудованим вмістом.

    `mime` з параметрами (`;codecs=opus`) зрізається; тип поза `ALLOWED_AUDIO` чи порожній результат —
    `AudioRejected`. Без `config` — моделі за замовчуванням (`DEFAULT_MODELS`)."""
    """Flow: тип → виклик моделі (один повтор, якщо дедлайн дозволяє) → непорожній текст."""
    kind = _audio_type(mime)
    choice = (config.models if config is not None else DEFAULT_MODELS)["transcribe"]
    request = types.GenerateContentConfig(temperature=0, thinking_config=_thinking(choice))
    contents = [types.Part.from_bytes(data=audio, mime_type=kind), _speech_prompt(language)]
    for attempt in (1, 2):
        _check_deadline(deadline)
        try:
            response = client.models.generate_content(model=choice.model, contents=contents, config=request)
            break
        except Exception:
            if attempt == 2:
                raise
    text = (response.text or "").strip()
    if not text:
        raise AudioRejected("the model heard nothing")
    return text


class DeadlinePassed(Exception):
    """Дедлайн запиту минув до виклику моделі."""


def _audio_type(mime: str) -> str:
    kind = mime.split(";", 1)[0].strip().lower()
    if kind not in ALLOWED_AUDIO:
        raise AudioRejected(f"audio type {kind!r} is not allowed")
    return kind


def _check_deadline(deadline: datetime) -> None:
    if datetime.now(UTC) >= deadline:
        raise DeadlinePassed("no time left for the model call")


def _speech_prompt(language: str) -> str:
    return (
        f"Перепиши дослівно, що сказано в записі. Мова — {language}; імена людей, назви ліків "
        "і медичні терміни можуть бути німецькими — пиши їх так, як їх пишуть. Лише текст, без коментарів."
    )


def _thinking(choice: ModelChoice) -> types.ThinkingConfig | None:
    if not choice.thinking_level:
        return None
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel(choice.thinking_level))
