"""Smoke of slice priorities (F2 S3) with the real model: P-PARSE on answers to «Що з цього найважливіше?».

Runs `planning`'s own priorities parse (Gemini Flash-Lite on Vertex AI) on the contract's five answers to a
list of three tasks and checks the resulting order. No Google sign-in and no Calendar. Exit 0 when all pass.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_priorities.py
"""

import os
import sys
from typing import Any

from google import genai

from mamamemory import planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

TITLES = ["подзвонити нотаріусу", "до лікаря", "купити насіння"]
# answer, the titles in the expected order (None — same as before)
CASES = [
    ("спершу лікар, потім нотаріус", ["до лікаря", "подзвонити нотаріусу", "купити насіння"]),
    ("друге найважливіше", ["до лікаря", "подзвонити нотаріусу", "купити насіння"]),
    ("все однаково", TITLES),
    ("третє, потім перше", ["купити насіння", "подзвонити нотаріусу", "до лікаря"]),
    ("не знаю", TITLES),
]


# A list with one task from Google Tasks (number 3): answer, expected order, the titles chosen for a time.
WITH_TASKS = ["подзвонити нотаріусу", "до лікаря", "оплатити світло"]
TIMED_CASES = [
    ("третє поставте на час", WITH_TASKS, ["оплатити світло"]),
    (
        "спершу лікар, а світло теж на час",
        ["до лікаря", "подзвонити нотаріусу", "оплатити світло"],
        ["оплатити світло"],
    ),
    ("все однаково", WITH_TASKS, []),
]


def draft(titles: list[str] = TITLES, from_tasks: int | None = None) -> dict[str, Any]:
    tasks = [
        {"task_id": f"t{n + 1}", "title": title, "order": n, "needs_time": True, "duration_min": 30}
        | ({"needs_time": False, "source": "tasks", "origin_tasks_id": "g1"} if n + 1 == from_tasks else {})
        for n, title in enumerate(titles)
    ]
    return {"plan_id": "smoke", "tasks": tasks}


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
    for text, expected in CASES:
        answer = ai.generate_json(
            "parse_priorities", planning._priorities_prompt(draft(), text), planning.PRIORITIES_SCHEMA
        )
        reordered = planning._reordered(draft(), answer)
        got = [t["title"] for t in reordered] if reordered is not None else None
        ok = got == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {text}\n        {answer} -> {got}")
    for text, expected, timed in TIMED_CASES:
        listed = draft(WITH_TASKS, from_tasks=3)
        answer = ai.generate_json(
            "parse_priorities", planning._priorities_prompt(listed, text), planning.PRIORITIES_SCHEMA
        )
        reordered = planning._reordered(listed, answer)
        got = [t["title"] for t in reordered] if reordered is not None else None
        chosen = [t["title"] for t in reordered or [] if t.get("source") == "tasks" and t["needs_time"]]
        ok = got == expected and chosen == timed
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {text}\n        {answer} -> {got}, на час: {chosen}")
    total = len(CASES) + len(TIMED_CASES)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
