"""Smoke of slice add-or-plan with the real model: «додай задачу» against «сплануй тиждень».

The route: three phrases → `new_task`, three → `plan_week`; the task parse of «сплануй тиждень» and
«що в мене на цей тиждень?» gives no task once the request itself is dropped.
All 8 must pass (exit 1 otherwise). No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_add_or_plan.py
"""

import os
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from google import genai

from mamamemory import assistant, planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
ROUTES = [
    ("додай задачу подзвонити нотаріусу в понеділок", "new_task"),
    ("купити ліки і хліб", "new_task"),
    ("завтра о десятій до лікаря", "new_task"),
    ("сплануй тиждень", "plan_week"),
    ("давай планувати тиждень: ще подзвонити сестрі", "plan_week"),
    ("що в мене на цей тиждень?", "plan_week"),
]
EMPTY = ["сплануй тиждень", "що в мене на цей тиждень?"]


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
    for text in EMPTY:
        drafts = planning._parse_tasks(ai, text, NOW, ZoneInfo("Europe/Berlin"))
        left = [d for d in drafts if not planning._is_plan_request(d["title"])]
        ok = left == []
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  parse «{text}» -> {[d['title'] for d in drafts]} -> kept {left}")
    total = len(ROUTES) + len(EMPTY)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
