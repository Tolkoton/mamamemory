# /// script
# requires-python = ">=3.11"
# dependencies = ["google-genai>=1.0", "google-cloud-texttospeech>=2.29"]
# ///
"""PoC 2 (M2): Ukrainian speech with German names and medical terms — read aloud by Gemini-TTS
through the EU address of Cloud Text-to-Speech, then turned back into text by Gemini on Vertex AI.

Premises: P-TTS, P-STT-UK (.engine/premises/premise-log.md). Invented sentences only.
Synthetic speech is cleaner than mama's real voice; for a closer check, put real recordings into
poc/data/voice/ (name.webm|ogg|m4a|mp3|wav|aac with name.txt holding what was said) — they are used too.

    GOOGLE_CLOUD_PROJECT=pocket-lawyer-431614 uv run poc/poc2_voice.py
    GOOGLE_CLOUD_PROJECT=pocket-lawyer-431614 THINKING_LEVEL=LOW uv run poc/poc2_voice.py

Writes poc/out/poc2-report.md and the synthesized audio to poc/out/poc2-audio/.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import google.cloud.texttospeech as texttospeech
from common import MODELS, OUT_DIR, Usage, client, generate, normalize, vertex_location
from google import genai
from google.api_core.client_options import ClientOptions
from google.genai import types

TTS_ENDPOINT = "eu-texttospeech.googleapis.com"  # «data at-rest and in-use stay within … Europe»
TTS_MODEL = os.environ.get("TTS_MODEL", "gemini-2.5-flash-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "Kore")

# (what is said, the words that must come back exactly)
SENTENCES = [
    ("Передзвонити пані Шмідт щодо аналізу HbA1c у четвер о десятій.", ["Шмідт", "HbA1c", "четвер"]),
    ("У пані Мюллер TSH чотири і дев'ять, повторити через шість тижнів.", ["Мюллер", "TSH", "шість тижнів"]),
    (
        "Записати пана Беккера на УЗД щитоподібної залози в лікарні Санкт-Катарінен.",
        ["Беккер", "УЗД", "Катарінен"],
    ),
    (
        "Пані Шнайдер принесла Arztbrief з кардіології, переглянути дозування Ramipril.",
        ["Шнайдер", "Arztbrief", "Ramipril"],
    ),
    (
        "Зараз я працюю над договором купівлі городу, пункт сім про межі ділянки.",
        ["договором", "городу", "пункт сім"],
    ),
    (
        "Треба цього тижня купити насіння, подзвонити нотаріусу і забрати Überweisung для пані Вагнер.",
        ["нотаріусу", "Überweisung", "Вагнер"],
    ),
    (
        "Феритин у пані Кох вісім, призначити залізо і контроль через три місяці.",
        ["Кох", "залізо", "три місяці"],
    ),
    ("Що я робила з договором учора ввечері?", ["договором", "учора"]),
    (
        "Вітамін D двадцять три у пана Ціммерманна, продовжити Vigantol.",
        ["Ціммерманна", "Vigantol", "двадцять три"],
    ),
    ("Пані Майєр і пані Маєр — різні пацієнтки, не переплутати аналізи.", ["Майєр", "Маєр", "аналізи"]),
]
MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".m4a": "audio/m4a",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".aac": "audio/x-aac",
}


def synthesize(text: str) -> tuple[bytes, str, float]:
    tts = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_endpoint=TTS_ENDPOINT))
    voice = texttospeech.VoiceSelectionParams(language_code="uk-UA", name=TTS_VOICE, model_name=TTS_MODEL)
    started = time.monotonic()
    for encoding, mime in [
        (texttospeech.AudioEncoding.OGG_OPUS, "audio/ogg"),
        (texttospeech.AudioEncoding.MP3, "audio/mp3"),
    ]:
        try:
            response = tts.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=voice,
                audio_config=texttospeech.AudioConfig(audio_encoding=encoding),
            )
            return response.audio_content, mime, time.monotonic() - started
        except Exception as exc:  # try the next encoding, then report
            error = exc
    raise RuntimeError(f"TTS failed: {error}")


def transcribe(gc: genai.Client, model: str, audio: bytes, mime: str, usage: Usage) -> str:
    prompt = (
        "Перепиши дослівно, що сказано в записі. Мова — українська; імена людей, назви ліків і "
        "медичні терміни можуть бути німецькими — пиши їх так, як вони звучать і як їх пишуть. Лише текст."
    )
    return generate(gc, model, [types.Part.from_bytes(data=audio, mime_type=mime), prompt], usage)


def key_words_found(transcript: str, keys: list[str]) -> list[str]:
    said = normalize(transcript)
    return [key for key in keys if normalize(key) in said]


def real_recordings() -> list[tuple[str, bytes, str, list[str]]]:
    folder = Path(__file__).parent / "data" / "voice"
    found = []
    for path in sorted(folder.glob("*")) if folder.exists() else []:
        if path.suffix in MIME and path.with_suffix(".txt").exists():
            expected = path.with_suffix(".txt").read_text(encoding="utf-8").strip()
            keys = [word for word in re.findall(r"[\w'’-]+", expected) if len(word) > 3]
            found.append((path.name, path.read_bytes(), MIME[path.suffix], keys))
    return found


def run() -> str:
    report = ["# PoC 2 — голос українською з німецькими словами (вигадані речення)", ""]
    report.append(
        f"Озвучення: `{TTS_MODEL}`, голос `{TTS_VOICE}`, адреса `{TTS_ENDPOINT}`. "
        f"Vertex AI location: `{vertex_location()}`. "
        f"THINKING_LEVEL: `{os.environ.get('THINKING_LEVEL', 'типовий')}`."
    )
    audio_dir = OUT_DIR / "poc2-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    samples: list[tuple[str, bytes, str, list[str]]] = []
    tts_seconds: list[float] = []
    for number, (text, keys) in enumerate(SENTENCES, start=1):
        try:
            audio, mime, seconds = synthesize(text)
        except RuntimeError as exc:
            report.append(f"- Озвучення речення {number}: ПОМИЛКА — {str(exc)[:300]}")
            continue
        tts_seconds.append(seconds)
        (audio_dir / f"{number:02d}{'.ogg' if mime == 'audio/ogg' else '.mp3'}").write_bytes(audio)
        samples.append((f"синтез {number:02d}: {text}", audio, mime, keys))
    if tts_seconds:
        report.append(
            f"- Озвучення: {len(tts_seconds)} з {len(SENTENCES)} речень; "
            f"середній час {sum(tts_seconds) / len(tts_seconds):.1f} с."
        )
    recordings = real_recordings()
    report.append(f"- Справжніх записів у poc/data/voice/: {len(recordings)}.")
    samples += recordings

    gc = client()
    for model in MODELS:
        usage = Usage()
        found_total = keys_total = 0
        report += ["", f"## {model}", ""]
        for label, audio, mime, keys in samples:
            transcript = transcribe(gc, model, audio, mime, usage)
            found = key_words_found(transcript, keys)
            found_total += len(found)
            keys_total += len(keys)
            missing = [key for key in keys if key not in found]
            report.append(
                f"- {label} ({usage.seconds / max(usage.calls, 1):.1f} с у середньому)"
                f"\n  - почуто: {transcript.strip()!r}" + (f"\n  - не почуто: {missing}" if missing else "")
            )
        report.append(
            f"- Ключових слів почуто: {found_total} з {keys_total}. Викликів: {usage.calls}; токенів: "
            f"{usage.tokens_in} вхід / {usage.tokens_out} вихід / {usage.tokens_thinking} роздуми; "
            f"час: {usage.seconds:.0f} с; помилок: {len(usage.errors)} "
            "(ціна аудіовходу може відрізнятися від текстової — див. сторінку цін Vertex AI)."
        )
        report += [f"  - помилка: {error}" for error in usage.errors[:5]]
    return "\n".join(report)


def main() -> None:
    report = run()
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "poc2-report.md").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
