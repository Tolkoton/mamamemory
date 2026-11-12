"""Smoke of slice read-aloud on the real `eu` Gemini-TTS: every part of the guide and the first 3 parts of a
3 000-character text through `Speaker.say` — each non-empty audio starting with `OggS`. The call goes with
`timeout=call_timeout_s`, so a slow part fails. Prints seconds and audio size of each. No Google sign-in.

    GCP_PROJECT=pocket-lawyer-431614 uv run python scripts/smoke_read_aloud.py
"""

import sys
import time
from datetime import UTC, datetime, timedelta

from google.cloud import texttospeech

from mamamemory import assistant
from mamamemory.integrations.tts import Speaker, parts

CALL_TIMEOUT_S = 10.0
SENTENCE = "У понеділок о десятій подзвонити нотаріусу щодо договору на ділянку, а в середу піти до лікаря. "


def _now() -> datetime:
    return datetime.now(UTC)


def main() -> int:
    speaker = Speaker(
        lambda **options: texttospeech.TextToSpeechClient(**options),
        endpoint="eu-texttospeech.googleapis.com",
        call_timeout_s=CALL_TIMEOUT_S,
    )
    checks = [("guide", p) for p in parts(assistant.guide_text("uk"))]
    checks += [("long", p) for p in parts((SENTENCE * 31)[:3000])[:3]]
    failed = 0
    for name, part in checks:
        started = time.monotonic()
        try:
            audio = speaker.say(part, "uk", deadline=_now() + timedelta(seconds=CALL_TIMEOUT_S), now=_now)
            ok, info = audio.startswith(b"OggS"), f"{len(audio)} bytes"
        except Exception as exc:
            ok, info = False, type(exc).__name__
        failed += not ok
        seconds = time.monotonic() - started
        print(f"{'PASS' if ok else 'FAIL'}  {name} {len(part):>3} chars  {seconds:5.2f} s  {info}")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
