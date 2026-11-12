"""Measure F1 S5 (skeleton-measure): the production `integrations.ai.speech` (model
`DEFAULT_MODELS["transcribe"]`) on the 10 synthetic recordings of PoC 2 (`poc/out/poc2-audio/NN.ogg`, keywords
from `poc2_voice.SENTENCES`). Prints seconds, the heard text and the missing keywords per recording, then
`HEARD: K of N keywords`, `SECONDS: min / median / max`, `MEASURED: M of 10 calls`. Exit 0 when all 10 calls
gave text. Not mama's voice.

    GCP_PROJECT=pocket-lawyer-431614 uv run python scripts/measure_f1.py
"""

import importlib
import os
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

from google import genai

from mamamemory.integrations import ai

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "poc"
AUDIO = POC / "out" / "poc2-audio"
DEADLINE_S = 30  # the measure's own deadline, looser than production's


def _poc2() -> ModuleType:
    """PoC 2 module with `poc/` on `sys.path` (it imports `common`): `SENTENCES`, `key_words_found`."""
    if str(POC) not in sys.path:
        sys.path.insert(0, str(POC))
    return importlib.import_module("poc2_voice")


def main() -> int:
    poc2 = _poc2()
    client = genai.Client(vertexai=True, project=os.environ["GCP_PROJECT"], location="eu")
    heard = total = measured = 0
    seconds: list[float] = []
    for number, (_, keys) in enumerate(poc2.SENTENCES, start=1):
        total += len(keys)
        audio = (AUDIO / f"{number:02d}.ogg").read_bytes()
        started = time.monotonic()
        try:
            text = ai.speech(
                audio,
                "audio/ogg",
                language="uk",
                deadline=datetime.now(UTC) + timedelta(seconds=DEADLINE_S),
                client=client,
                config=None,
            )
        except Exception as exc:
            print(f"{number:02d}  FAILED {type(exc).__name__}  ({time.monotonic() - started:.2f} s)")
            continue
        took = time.monotonic() - started
        seconds.append(took)
        measured += 1
        found = poc2.key_words_found(text, keys)
        heard += len(found)
        missing = [key for key in keys if key not in found]
        print(f"{number:02d}  {took:5.2f} s  heard: {text!r}  missing: {missing}")
    print(f"HEARD: {heard} of {total} keywords")
    if seconds:
        print(f"SECONDS: {min(seconds):.2f} / {statistics.median(seconds):.2f} / {max(seconds):.2f}")
    else:
        print("SECONDS: - / - / -")
    print(f"MEASURED: {measured} of {len(poc2.SENTENCES)} calls")
    return 0 if measured == len(poc2.SENTENCES) else 1


if __name__ == "__main__":
    sys.exit(main())
