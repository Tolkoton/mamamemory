# /// script
# requires-python = ">=3.12"
# dependencies = ["google-cloud-texttospeech>=2.29"]
# ///
"""Spike (read-aloud premise P-TTS-PART): seconds Gemini-TTS on `eu` takes for one part
of up to 150 characters — 5 runs of a plain Ukrainian part, 5 of a part from the guide (emoji, «»),
3 of a 100-character part. Writes JSON to
.engine/artifacts/spikes/read-aloud-tts-parts-2026-11-11.json.

    GOOGLE_CLOUD_PROJECT=pocket-lawyer-431614 uv run poc/spike_tts_parts.py
"""

import ast
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

import google.cloud.texttospeech as texttospeech
from google.api_core.client_options import ClientOptions

ROOT = Path(__file__).resolve().parents[1]


def _guide_part() -> str:
    text = (ROOT / "src/mamamemory/assistant.py").read_text()
    match = re.search(r"GUIDE_UK = \((.*?)\)\n\n", text, re.DOTALL)
    if match is None:
        raise RuntimeError("Could not load GUIDE_UK from assistant.py")
    guide = str(ast.literal_eval(f"({match.group(1)})"))
    part = ""
    for line in guide.splitlines():
        if len(part) + len(line) + 1 > 150:
            break
        part = f"{part}\n{line}".strip()
    return part


SENTENCE = "У понеділок о десятій подзвонити нотаріусу щодо договору на ділянку, а в середу піти до лікаря. "
TEXTS = {
    "plain_150": ((SENTENCE * 2)[:150], 5),
    "guide_150": (_guide_part(), 5),
    "plain_100": (SENTENCE[:100], 3),
}


def main() -> None:
    client = texttospeech.TextToSpeechClient(
        client_options=ClientOptions(api_endpoint="eu-texttospeech.googleapis.com")
    )
    voice = texttospeech.VoiceSelectionParams(
        language_code="uk-UA", name="Kore", model_name="gemini-2.5-flash-tts"
    )
    results: dict[str, Any] = {}
    for name, (text, runs) in TEXTS.items():
        rows: list[dict[str, Any]] = []
        for _ in range(runs):
            started = time.monotonic()
            try:
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=text),
                    voice=voice,
                    audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS),
                    timeout=30,
                )
                rows.append(
                    {
                        "seconds": round(time.monotonic() - started, 2),
                        "audio_bytes": len(response.audio_content),
                        "ogg": response.audio_content[:4] == b"OggS",
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "seconds": round(time.monotonic() - started, 2),
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    }
                )
            print(name, rows[-1])
        ok = [r["seconds"] for r in rows if "error" not in r]
        results[name] = {
            "chars": len(text),
            "text": text,
            "runs": rows,
            "errors": len(rows) - len(ok),
            "min": min(ok, default=None),
            "median": statistics.median(ok) if ok else None,
            "max": max(ok, default=None),
        }
        print(name, {k: results[name][k] for k in ("chars", "errors", "min", "median", "max")})
    out = ROOT / ".engine/artifacts/spikes/read-aloud-tts-parts-2026-11-11.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("written", out)


if __name__ == "__main__":
    main()
