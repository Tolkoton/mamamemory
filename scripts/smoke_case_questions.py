"""Smoke of slice case-questions (F3 S3) with the real models: answers to the questions about cases.

The route with `reply_to` of a case question: «ні» → `no`, «ні, не треба» and «не треба» → `not_needed`,
«так» → `yes`; on «У яку справу покласти?»: «до Коха», «в город», «ні, до Коха» → `case_name`. The Розкладач
(3.8 Flash) on the six cases of S1: «до Коха» → «пан Кох», «в город» → «город». On an empty catalogue
`name_case` with «до пані Шмідт» → a name with «Шмідт». All 10 must pass (exit 1 otherwise).
No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_case_questions.py
"""

import os
import sys
from datetime import UTC, datetime

from google import genai

from mamamemory import assistant, cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
CREATE = cases.ask_text("пані Вагнер")
WHICH = cases.ASK_WHICH
ROUTES = [
    ("ні", CREATE, "no"),
    ("ні, не треба", CREATE, "not_needed"),
    ("не треба", CREATE, "not_needed"),
    ("так", CREATE, "yes"),
    ("до Коха", WHICH, "case_name"),
    ("в город", WHICH, "case_name"),
    ("ні, до Коха", CREATE, "case_name"),
]
SIX = [
    ("пан Кох", "Пацієнт 71 рік, цукровий діабет 2 типу, метформін; алергія на пеніцилін."),
    ("пані Шмідт", "Пацієнтка 64 роки, гіпертонія, раміприл; HbA1c 7,2 у жовтні."),
    ("пан Шмітт", "Пацієнт 58 років, після інфаркту 2024, аспірин і статин."),
    ("пані Майєр", "Пацієнтка 80 років, остеопороз, щорічна денситометрія."),
    ("город", "Купівля ділянки біля Кельна: договір, нотаріус, межі ділянки."),
    ("пані Фішер", "Пацієнтка 45 років, гіпотиреоз, L-тироксин 75 мкг."),
]  # fmt: skip
CHOOSE = [("до Коха", 1), ("в город", 5)]


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
        prompt = assistant._route_prompt(text, Question("case", "smoke", None), None, asked)
        intent = ai.generate_json(
            "route", prompt, assistant.route_schema(Question("case", "smoke", None))
        ).get("intent")
        ok = intent == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» on «{asked}» -> {intent} (expected {expected})")
    known = [cases.Case(f"c{n}", name, description, NOW) for n, (name, description) in enumerate(SIX)]
    for text, number in CHOOSE:
        answer = ai.generate_json("classify_case", cases._classify_prompt(known, text), cases.CLASSIFY_SCHEMA)
        ok = answer.get("number") == number
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  choose «{text}» -> {answer}")
    name = ai.generate_json("name_case", cases._name_prompt("до пані Шмідт"), cases.NAME_SCHEMA).get("name")
    ok = isinstance(name, str) and "Шмідт" in name
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  name on an empty catalogue «до пані Шмідт» -> {name!r}")
    total = len(ROUTES) + len(CHOOSE) + 1
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
