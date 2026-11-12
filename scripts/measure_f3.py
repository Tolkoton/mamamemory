"""Measurement of F3 (S5 f3-measure): the case path of the language model on ten new phrases the prompts were
never tuned on. Four notes and one task through the route; two answers to a case question; two «перекласти»
through `choose_material`; one note through the Розкладач. A measurement, not a gate: it prints each phrase,
the model's answer and «N of 10», and exits 0 unless the model is unreachable.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/measure_f3.py
"""

import os
import sys
from datetime import UTC, datetime, timedelta

from google import genai

from mamamemory import assistant, cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
CASES = [
    ("пані Бергер", "Пацієнтка 68 років, хронічна серцева недостатність, торасемід."),
    ("пан Вольф", "Пацієнт 77 років, хвороба Паркінсона, леводопа."),
    ("ремонт кухні", "Заміна плити й шаф: майстер Олег, кошторис, кахель."),
]  # fmt: skip
MATERIALS: list[tuple[str, int, cases.MaterialKind, str]] = [
    ("x1", 0, "photo", "Echokardiographie: EF 35 %, linker Vorhof vergrößert"),
    ("x2", 1, "note", "тремор посилився вечорами, дозу поки не міняємо"),
    ("x3", 2, "note", "майстер Олег прийде в четвер о 9, взяти аванс 500 євро"),
]  # fmt: skip
ROUTES = [
    ("занотуй: у Бергер набряки на ногах, вага плюс два кіло", None, None, "note"),
    ("запам'ятай, що кахель для кухні — сірий, 30 на 60", None, None, "note"),
    ("пан Вольф просив виписати рецепт на леводопу", None, None, "note"),
    ("треба в п'ятницю зранку зателефонувати майстру", None, None, "new_task"),
    ("запиши: Вольф упав удома, синець на стегні", None, None, "note"),
    ("ні, це не нова, це до Бергер", "case", cases.ask_text("пані Бергерова"), "case_name"),
    ("та ну, не треба нікуди", "case", cases.ask_text("кухня"), "not_needed"),
]
MOVES = [("ехокардіографію переклади до Вольфа", 1, 2), ("записку про аванс — у ремонт кухні", 3, 3)]
CLASSIFY = [("Вольфу додали прамipексол 0,25 вранці", 2)]


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
    known = [cases.Case(f"c{n}", name, description, NOW) for n, (name, description) in enumerate(CASES)]
    materials = [
        cases.Material(
            mid, kind, body, "placed", f"c{case}", None, None, None, NOW + timedelta(minutes=n), True
        )
        for n, (mid, case, kind, body) in enumerate(MATERIALS)
    ]
    results: list[bool] = []
    for text, kind, asked, expected in ROUTES:
        reply_to = Question("case", "measure", None) if kind else None
        prompt = assistant._route_prompt(text, reply_to, None, asked)
        intent = ai.generate_json("route", prompt, assistant.route_schema(reply_to)).get("intent")
        results.append(intent == expected)
        verdict = f"{'PASS' if results[-1] else 'FAIL'} (expected {expected})"
        print(f"«{text}»\n        intent={intent}\n    {verdict}")
    for text, material, case in MOVES:
        answer = ai.generate_json(
            "choose_material", cases._move_prompt(materials, known, text), cases.MOVE_SCHEMA
        )
        results.append(answer.get("material") == material and answer.get("case") == case)
        print(f"«{text}»\n        {answer}\n    {'PASS' if results[-1] else 'FAIL'}")
    for text, case in CLASSIFY:
        answer = ai.generate_json("classify_case", cases._classify_prompt(known, text), cases.CLASSIFY_SCHEMA)
        results.append(answer.get("number") == case)
        print(f"«{text}»\n        {answer}\n    {'PASS' if results[-1] else 'FAIL'}")
    print(f"MEASURED: {sum(results)} of {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
