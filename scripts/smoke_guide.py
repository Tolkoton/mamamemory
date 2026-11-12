"""Smoke of slice guide (F5 S2) with the real model: «що ти вмієш?» routes to `help`.

«що ти вмієш?», «як з тобою працювати?», «допоможи, я не розумію, що тут робити» → `help`;
«додай задачу подзвонити нотаріусу» → `new_task`; «що ти вмієш?» under the case
question «Створити справу «пані Бергерова»?» → `help` (F5 S4). All 5 must pass (exit 1 otherwise).
No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_guide.py
"""

import os
import sys

from google import genai

from mamamemory import assistant, cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

ROUTES = [
    ("що ти вмієш?", "help"),
    ("як з тобою працювати?", "help"),
    ("допоможи, я не розумію, що тут робити", "help"),
    ("додай задачу подзвонити нотаріусу", "new_task"),
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
    for text, expected in ROUTES:
        intent = ai.generate_json(
            "route", assistant._route_prompt(text, None), assistant.route_schema(None)
        ).get("intent")
        ok = intent == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» -> {intent} (expected {expected})")
    case_q = Question("case", "smoke", None)
    prompt = assistant._route_prompt("що ти вмієш?", case_q, None, cases.ask_text("пані Бергерова"))
    intent = ai.generate_json("route", prompt, assistant.route_schema(case_q)).get("intent")
    ok = intent == "help"
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  route «що ти вмієш?» under a case question -> {intent} (expect help)")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(ROUTES) + 1}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
