"""Smoke of slice move-material (F3 S4) with the real models: the route, `choose_material` and P-DESC.

(a) The route: three «перекласти» phrases → `move`; under a shown plan «перенеси нотаріуса на четвер» →
`edit`. (b) `choose_material` (3.8 Flash) on six materials in the six cases of S1: the three phrases of (a) →
the right material and case. (c) P-DESC: a case of two notes (HbA1c 7,2; тиск 140/90) whose first note is
moved away → the fresh description from the other note alone holds no «7,2».
All 8 must pass (exit 1 otherwise). No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_move_material.py
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
SIX = [
    ("пан Кох", "Пацієнт 71 рік, цукровий діабет 2 типу, метформін; алергія на пеніцилін."),
    ("пані Шмідт", "Пацієнтка 64 роки, гіпертонія, раміприл; HbA1c 7,2 у жовтні."),
    ("пан Шмітт", "Пацієнт 58 років, після інфаркту 2024, аспірин і статин."),
    ("пані Майєр", "Пацієнтка 80 років, остеопороз, щорічна денситометрія."),
    ("город", "Купівля ділянки біля Кельна: договір, нотаріус, межі ділянки."),
    ("пані Фішер", "Пацієнтка 45 років, гіпотиреоз, L-тироксин 75 мкг."),
]  # fmt: skip
MATERIALS: list[tuple[str, int, cases.MaterialKind, str]] = [
    ("m1", 0, "photo", "Laborbefund: Glukose nüchtern 142 mg/dl, HbA1c 7,8 %"),
    ("m2", 1, "photo", "Laborbefund Schmidt: HbA1c 7,2 %, Kreatinin 0,9"),
    ("m3", 2, "note", "після стенту: аспірин 100 щодня, контроль у кардіолога в грудні"),
    ("m4", 3, "file", "Densitometrie: T-Score −2,7 Lendenwirbelsäule"),
    ("m5", 0, "note", "нотатка: посадити часник у жовтні, грядка біля паркану"),
    ("m6", 5, "note", "TSH 2,1 — дозу L-тироксину не змінюємо"),
]  # fmt: skip
MOVES = [
    ("переклади аналіз пані Шмідт до пана Шмітта", 2, 3),
    ("нотатку про часник перенеси в город", 5, 5),
    ("це не до Коха, а до Фішер — аналіз з глюкозою", 1, 6),
]
ROUTES = [(text, None, "move") for text, *_ in MOVES] + [
    ("перенеси нотаріуса на четвер", Question("plan", "smoke", "fp"), "edit")
]


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
    for text, reply_to, expected in ROUTES:
        titles = ["подзвонити нотаріусу", "до лікаря"] if reply_to else None
        intent = ai.generate_json(
            "route", assistant._route_prompt(text, reply_to, titles), assistant.route_schema(reply_to)
        ).get("intent")
        ok = intent == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» -> {intent} (expected {expected})")
    known = [cases.Case(f"c{n}", name, description, NOW) for n, (name, description) in enumerate(SIX)]
    materials = [
        cases.Material(
            mid, kind, body, "placed", f"c{case}", None, None, None, NOW + timedelta(minutes=n), True
        )
        for n, (mid, case, kind, body) in enumerate(MATERIALS)
    ]
    for text, material, case in MOVES:
        answer = ai.generate_json(
            "choose_material", cases._move_prompt(materials, known, text), cases.MOVE_SCHEMA
        )
        ok = answer.get("material") == material and answer.get("case") == case
        failed += not ok
        expected = f"material {material}, case {case}"
        print(f"{'PASS' if ok else 'FAIL'}  choose «{text}» -> {answer} (expected {expected})")
    left = [
        cases.Material(
            "k2", "note", "тиск 140/90, раміприл 5 мг лишаємо", "placed", "c1", None, None, None, NOW, True
        )
    ]
    fresh = cases.Case("c1", "пані Шмідт", "", NOW)
    description = ai.generate_json(
        "describe_case", cases._describe_prompt(fresh, left), cases.DESCRIBE_SCHEMA
    ).get("description")
    ok = isinstance(description, str) and bool(description) and "7,2" not in description
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  P-DESC fresh description -> {description!r}")
    total = len(ROUTES) + len(MOVES) + 1
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
