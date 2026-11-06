"""Shared helpers for the M2 proofs of concept: the Vertex AI client, the region guard, timing.

Throwaway code: it answers PoC questions in .engine/architecture/architecture-map.md and is not
part of the product. All data it sends is invented (no real patient).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

OUT_DIR = Path(__file__).parent / "out"

# Price per 1M tokens, standard tier, non-global endpoint (cloud.google.com/vertex-ai/generative-ai/pricing,
# read by the master-critic on 2026-10-24). Text input/output; audio input may cost more — see the report.
PRICES = {
    "gemini-3.5-flash-lite": (0.33, 2.75),
    "gemini-3.8-flash": (0.825, 4.125),
}
MODELS = list(PRICES)


def project() -> str:
    value = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not value:
        raise SystemExit("set GOOGLE_CLOUD_PROJECT (docs/infra.md: pocket-lawyer-431614)")
    return value


def vertex_location() -> str:
    """The EU multi-region by default; refuses `global`, which carries no data-residency guarantee (C1)."""
    location = os.environ.get("VERTEX_LOCATION", "eu")
    if location == "global" or not (location == "eu" or location.startswith("europe-")):
        raise SystemExit(f"refused: VERTEX_LOCATION={location!r} — only `eu` or a europe-* region (C1)")
    return location


def client() -> genai.Client:
    base_url = os.environ.get("VERTEX_BASE_URL")
    http_options = types.HttpOptions(base_url=base_url) if base_url else None
    return genai.Client(
        vertexai=True, project=project(), location=vertex_location(), http_options=http_options
    )


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thinking: int = 0  # billed as output (Vertex «Thinking»: thoughts_token_count)
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def cost(self, model: str) -> float:
        price_in, price_out = PRICES[model]
        return (self.tokens_in * price_in + (self.tokens_out + self.tokens_thinking) * price_out) / 1_000_000


def thinking(model: str) -> types.ThinkingConfig | None:
    """THINKING_LEVEL=LOW|MEDIUM|HIGH applies to gemini-3.8-flash only; unset keeps the model's default."""
    level = os.environ.get("THINKING_LEVEL")
    if not level or model != "gemini-3.8-flash":
        return None
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel(level))


def generate(gc: genai.Client, model: str, parts: list[Any], usage: Usage, as_json: bool = False) -> str:
    """One call; counts tokens and time into `usage`. Returns the text, or '' after an error."""
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json" if as_json else None,
        thinking_config=thinking(model),
    )
    started = time.monotonic()
    try:
        response = gc.models.generate_content(model=model, contents=parts, config=config)
    except Exception as exc:  # a PoC reports failures instead of stopping on the first one
        usage.errors.append(f"{type(exc).__name__}: {exc}"[:300])
        return ""
    finally:
        usage.seconds += time.monotonic() - started
        usage.calls += 1
    meta = response.usage_metadata
    if meta is not None:
        usage.tokens_in += meta.prompt_token_count or 0
        usage.tokens_out += meta.candidates_token_count or 0
        usage.tokens_thinking += getattr(meta, "thoughts_token_count", 0) or 0
    return response.text or ""


def parse_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace(",", ".")).strip()
