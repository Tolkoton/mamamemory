"""Smoke of slice note-to-case (F3 S1) with the real models: the route, the Розкладач, and P-CASES.

(a) `assistant`'s own route prompt: three notes → `note`, a task → `new_task`, «так» under
«Створити справу?» → `yes`. (b) `cases`' own Розкладач prompt (3.8 Flash) on a catalogue of six made-up
cases: two notes about known cases → their numbers, one about a new person → no number and a name.
(d) The first case's name on an empty catalogue (`name_case`): two notes. All 10 must pass (exit 1
otherwise).
(c) A measurement, not a gate: the Розкладач on 48 made-up cases with look-alike patients — how many of 48
notes it puts into the right case (Q2 of the goals: no threshold; the number goes to the owner).
Gemini on Vertex AI, eu; no Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_note_to_case.py
"""

import os
import sys
import time
from datetime import UTC, datetime

from google import genai

from mamamemory import assistant, cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
ROUTES = [
    ("запиши до пані Шмідт: HbA1c 7,2", None, "note"),
    ("запам'ятай, що в Коха алергія на пеніцилін", None, "note"),
    ("нотатка про город: посадити часник у жовтні", None, "note"),
    ("подзвонити нотаріусу в понеділок", None, "new_task"),
    ("так", "пані Шмідт", "yes"),
]
SIX = [
    ("пан Кох", "Пацієнт 71 рік, цукровий діабет 2 типу, метформін; алергія на пеніцилін."),
    ("пані Шмідт", "Пацієнтка 64 роки, гіпертонія, раміприл; HbA1c 7,2 у жовтні."),
    ("пан Шмітт", "Пацієнт 58 років, після інфаркту 2024, аспірин і статин."),
    ("пані Майєр", "Пацієнтка 80 років, остеопороз, щорічна денситометрія."),
    ("город", "Купівля ділянки біля Кельна: договір, нотаріус, межі ділянки."),
    ("пані Фішер", "Пацієнтка 45 років, гіпотиреоз, L-тироксин 75 мкг."),
]  # fmt: skip
CLASSIFY = [
    ("у Шмідт тиск 140 на 90, раміприл лишаємо", 2, None),
    ("нотаріус переніс підписання договору на ділянку", 5, None),
    ("нова пацієнтка пані Вагнер, 52 роки, мігрень", None, "Вагнер"),
]
FIRST_NOTES = [
    ("запиши до пані Шмідт: HbA1c 7,2", "Шмідт"),
    ("нотатка про город: посадити часник у жовтні", "город"),
]
"""An empty catalogue: the first case's name comes from `name_case` (Flash-Lite)."""
SURNAMES = [
    "Шмідт", "Шмітт", "Шмід", "Мюллер", "Меллер", "Міллер", "Майєр", "Маєр",
    "Мейєр", "Фішер", "Фішман", "Вебер", "Ваґнер", "Вагнер", "Беккер", "Бекер",
    "Шульц", "Шульце", "Гофман", "Гоффман", "Кох", "Кох-Рієль", "Ріхтер", "Клайн",
    "Кляйн", "Вольф", "Шредер", "Шрьодер", "Нойман", "Найман", "Шварц", "Циммерман",
    "Браун", "Крюгер", "Гартман", "Ланґе", "Ланге", "Шміт", "Вернер", "Краузе",
    "Мейер-Шмідт", "Леманн", "Леман", "Шмітц", "Кравс", "Майер", "Кьоніг", "Кеніг",
]  # fmt: skip
CONDITIONS = [
    "цукровий діабет 2 типу", "гіпертонія", "гіпотиреоз", "астма", "подагра", "остеопороз", "мігрень",
    "фібриляція передсердь", "ХОЗЛ", "анемія", "ревматоїдний артрит", "хронічна хвороба нирок",
]  # fmt: skip


def catalogue(pairs: list[tuple[str, str]]) -> list[cases.Case]:
    return [cases.Case(f"c{n}", name, description, NOW) for n, (name, description) in enumerate(pairs)]


def forty_eight() -> tuple[list[cases.Case], list[tuple[str, int]]]:
    """48 look-alike patients: each has a surname, age and condition; each note names one by surname and a
    detail from its description."""
    pairs, notes = [], []
    for n, surname in enumerate(SURNAMES):
        title = ("пані " if n % 2 else "пан ") + surname
        age, condition = 40 + (n * 7) % 45, CONDITIONS[n % len(CONDITIONS)]
        pairs.append((title, f"Пацієнт(ка) {age} років, {condition}; веду з {2015 + n % 10} року."))
        notes.append((f"{title}: контроль, {condition} стабільно, наступний візит за 3 місяці", n + 1))
    return catalogue(pairs), notes


def classify(ai: AI, known: list[cases.Case], text: str) -> dict[str, object]:
    return ai.generate_json("classify_case", cases._classify_prompt(known, text), cases.CLASSIFY_SCHEMA)


def main() -> int:
    client = genai.Client(
        vertexai=True, project=os.environ["GCP_PROJECT"], location=os.environ.get("VERTEX_LOCATION", "eu")
    )
    config = Config(
        gcp_project=os.environ["GCP_PROJECT"], firestore_database="mamamemory", vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com", region="europe-west3", oauth_client_id="-",
        oauth_client_secret="-", session_key="-", session_max_age_s=1, login_max_age_s=1, base_url="-",
        request_timeout_s=60, call_timeout_s=15,
    )  # fmt: skip
    ai = AI(lambda: client, config)
    failed = 0
    for text, asked, expected in ROUTES:
        reply_to = Question("case", "smoke", None) if asked else None
        prompt = assistant._route_prompt(text, reply_to, None, cases.ask_text(asked) if asked else None)
        intent = ai.generate_json("route", prompt, assistant.route_schema(reply_to)).get("intent")
        ok = intent == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» -> {intent} (expected {expected})")
    six = catalogue(SIX)
    for text, number, name in CLASSIFY:
        answer = classify(ai, six, text)
        new_name = answer.get("new_name")
        if number is not None:
            ok = answer.get("number") == number
        else:
            in_catalogue = isinstance(answer.get("number"), int) and 1 <= int(str(answer["number"])) <= len(
                six
            )
            ok = not in_catalogue and isinstance(new_name, str) and name is not None and name in new_name
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  classify «{text}» -> {answer}")
    for text, part in FIRST_NOTES:
        name = ai.generate_json("name_case", cases._name_prompt(text), cases.NAME_SCHEMA).get("name")
        ok = isinstance(name, str) and part in name
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  first case name «{text}» -> {name!r}")
    total = len(ROUTES) + len(CLASSIFY) + len(FIRST_NOTES)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    known, notes = forty_eight()
    right, started = 0, time.monotonic()
    for text, number in notes:
        answer = classify(ai, known, text)
        hit = answer.get("number") == number
        right += hit
        if not hit:
            print(f"        miss: «{text}» -> {answer}")
    seconds = (time.monotonic() - started) / len(notes)
    print(f"MEASURED P-CASES: {right} of {len(notes)} on {len(known)} cases, {seconds:.1f} s per call")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
