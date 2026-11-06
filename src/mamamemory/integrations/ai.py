"""Gemini на Vertex AI (`integrations.ai`): структуровані відповіді для S3, `speech` — S2.

Клієнт `google-genai` будується один раз (ліниво, на перший виклик) і живе в цьому об'єкті.
Не робить: озвучення (F5), повторів понад один.
"""

import json
from collections.abc import Callable
from typing import Any

from google.genai import types

from mamamemory.config import Config


class AI:
    def __init__(self, client_factory: Callable[[], Any], config: Config) -> None:
        self._client_factory, self._client, self._config = client_factory, None, config

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Модель і рівень роздумів — з `config.models[task_type]`."""
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
            model=choice.model, contents=prompt, config=config
        )
        answer = json.loads(response.text or "{}")
        return answer if isinstance(answer, dict) else {}

    def _client_instance(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client
