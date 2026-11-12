# /// script
# requires-python = ">=3.12"
# dependencies = ["google-cloud-texttospeech>=2.29"]
# ///
"""Spike (read-aloud premise): how long Gemini-TTS on `eu` takes for the guide (~350 characters),
~700 and ~1 500 characters of Ukrainian, and whether ~1 500 characters with emoji pass the input limit.
Writes JSON to .engine/artifacts/spikes/read-aloud-tts-length-2026-11-11.json.

    GOOGLE_CLOUD_PROJECT=pocket-lawyer-431614 uv run poc/spike_tts_length.py
"""

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

import google.cloud.texttospeech as texttospeech
from google.api_core.client_options import ClientOptions

ROOT = Path(__file__).resolve().parents[1]


def _load_guide_text() -> str:
    assistant_file = ROOT / "src/mamamemory/assistant.py"
    match = re.search(r"GUIDE_UK = \((.*?)\)\n\n", assistant_file.read_text(), re.DOTALL)
    if match:
        return str(ast.literal_eval(f"({match.group(1)})"))
    raise RuntimeError("Could not load GUIDE_UK from assistant.py")


SENTENCE = "У понеділок о десятій подзвонити нотаріусу щодо договору на ділянку, а в середу піти до лікаря. "
TEXTS = {
    "guide": _load_guide_text(),
    "700": (SENTENCE * 8)[:700],
    "1500": (SENTENCE * 16)[:1500],
    "1500_emoji": ("📷 ＋ 🔊 … " + SENTENCE) * 13,
}


def main() -> None:
    client = texttospeech.TextToSpeechClient(
        client_options=ClientOptions(api_endpoint="eu-texttospeech.googleapis.com")
    )
    voice = texttospeech.VoiceSelectionParams(
        language_code="uk-UA", name="Kore", model_name="gemini-2.5-flash-tts"
    )
    results: dict[str, dict[str, Any]] = {}
    for name, text in TEXTS.items():
        text = text[:1500]
        started = time.monotonic()
        try:
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=voice,
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS),
                timeout=120,
            )
            results[name] = {
                "chars": len(text),
                "bytes": len(text.encode()),
                "seconds": round(time.monotonic() - started, 2),
                "audio_bytes": len(response.audio_content),
                "ogg": response.audio_content[:4] == b"OggS",
            }
        except Exception as exc:
            results[name] = {
                "chars": len(text),
                "bytes": len(text.encode()),
                "seconds": round(time.monotonic() - started, 2),
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
        print(name, results[name])
    out = ROOT / ".engine/artifacts/spikes/read-aloud-tts-length-2026-11-11.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("written", out)


if __name__ == "__main__":
    main()
