"""Smoke of slice plans-not-questions with the real model: the priorities and limits parses tell answers from
other phrases (`is_answer`).

`is_answer: false` — «які в нас плани?», «які плани?», «що в мене сьогодні?» for both parses (6);
`is_answer: true` — «перше важливіше», «все однаково», «не знаю», «не важливо» (priorities),
«будні з дев'ятої до шостої», «як минулого разу» (limits) (6).
«друге поставте на час», «спершу ліки, а нотаріуса на час» (priorities, a timed choice) → true.
All 14 must pass. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_plans_not_questions.py
"""

import os
import sys
from typing import Any

from google import genai

from mamamemory import planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

NOT_ANSWERS = ["які в нас плани?", "які плани?", "що в мене сьогодні?"]
PRIORITY_ANSWERS = [
    "перше важливіше", "все однаково", "не знаю", "не важливо",
    "друге поставте на час", "спершу ліки, а нотаріуса на час",
]  # fmt: skip
LIMIT_ANSWERS = ["будні з дев'ятої до шостої", "як минулого разу"]
TASKS = [{"title": "подзвонити нотаріусу"}, {"title": "купити ліки"}]


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
    planning._listed = lambda draft: draft["tasks"]  # the priorities prompt only needs the titles here
    draft: dict[str, Any] = {"tasks": TASKS}

    def priorities(text: str) -> Any:
        prompt = planning._priorities_prompt(draft, text)
        return ai.generate_json("parse_priorities", prompt, planning.PRIORITIES_SCHEMA).get("is_answer")

    def limits(text: str) -> Any:
        return ai.generate_json("parse_limits", planning._limits_prompt(text), planning.LIMITS_SCHEMA).get(
            "is_answer"
        )

    checks = [(f"priorities «{t}»", priorities, t, False) for t in NOT_ANSWERS]
    checks += [(f"limits «{t}»", limits, t, False) for t in NOT_ANSWERS]
    checks += [(f"priorities «{t}»", priorities, t, True) for t in PRIORITY_ANSWERS]
    checks += [(f"limits «{t}»", limits, t, True) for t in LIMIT_ANSWERS]
    failed = 0
    for name, parse, text, expected in checks:
        got = parse(text)
        ok = got is expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name} -> is_answer {got} (expected {expected})")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
