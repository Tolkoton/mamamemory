"""Smoke of slice show-schedule with the real model: «які плани…» → `schedule`, «сплануй…» → `plan_week`.

«які плани на сьогодні?», «які в нас плани на поточний тиждень?», «що в мене завтра?»,
«що в мене на цей тиждень?» → `schedule`; «сплануй тиждень», «давай планувати тиждень: ще подзвонити сестрі» →
`plan_week`; «додай задачу подзвонити нотаріусу» → `new_task`. All 7 must pass (exit 1 otherwise).
No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_schedule.py
"""

import os
import sys

from google import genai

from mamamemory import assistant
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

ROUTES = [
    ("які плани на сьогодні?", "schedule"),
    ("які в нас плани на поточний тиждень?", "schedule"),
    ("що в мене завтра?", "schedule"),
    ("що в мене на цей тиждень?", "schedule"),
    ("сплануй тиждень", "plan_week"),
    ("давай планувати тиждень: ще подзвонити сестрі", "plan_week"),
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
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(ROUTES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
