"""Measurement of F2 (S6 f2-measure): P-PARSE on ten new phrases the prompts were never tuned on.

Six dictations through `planning`'s own task parse, two answers under a shown plan through the route, two
edits through `parse_edit`. Gemini Flash-Lite on Vertex AI; no Google sign-in and no Calendar. A measurement,
not a gate: it prints each phrase, the model's answer and «N of 10»; exit 0 always unless the model is
unreachable.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/measure_f2_parse.py
"""

import os
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from google import genai

from mamamemory import assistant, planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
"""Monday 9 November 2026, 10:07 Berlin: «завтра» is 10 November, «у п'ятницю» 13 November."""
BERLIN = ZoneInfo("Europe/Berlin")
TITLES = ["записатися до окуліста", "забрати посилку", "написати звіт для клініки"]
PLAN = Question("plan", "measure", "fp")

# phrase, tasks, timed, a day that must be named (or None), a duration that must be named (or None)
DICTATIONS = [
    ("Завтра о пів на дев'яту здати кров, а потім купити молоко", 2, 1, "2026-11-10", None),
    ("Треба подзвонити в страхову і ще оплатити рахунок за газ", 2, 1, None, None),
    ("У п'ятницю дві години попрацювати над статтею", 1, 1, "2026-11-13", 120),
    ("Не забути привітати Олю з днем народження в середу", 1, 1, "2026-11-11", None),
    ("Купити батарейки, мило і корм для кота", 3, 0, None, None),
    ("Сьогодні ввечері на сорок хвилин погуляти, а в четвер зранку до стоматолога", 2, 2, "2026-11-12", 40),
]
ROUTES = [("а окуліста давай на понеділок", "edit"), ("ще треба занести ключі сусідці", "new_task")]
EDITS = [
    ("звіт не раніше третьої", 3, "not_before", "15:00"),
    ("посилку прибери, я сама", 2, "remove", None),
]


def dictation(ai: AI, phrase: str, tasks: int, timed: int, day: str | None, minutes: int | None) -> bool:
    drafts = planning._parse_tasks(ai, phrase, NOW, BERLIN)
    print(f"        {drafts}")
    return (
        len(drafts) == tasks
        and len([d for d in drafts if d["needs_time"]]) == timed
        and (day is None or day in {d["constraints"]["day"] for d in drafts})
        and (minutes is None or minutes in {d["duration_min"] for d in drafts})
    )


def route(ai: AI, phrase: str, expected: str) -> bool:
    prompt = assistant._route_prompt(phrase, PLAN, TITLES)
    intent = ai.generate_json("route", prompt, assistant.route_schema(PLAN)).get("intent")
    print(f"        intent={intent}")
    return bool(intent == expected)


def edit(ai: AI, phrase: str, number: int, kind: str, not_before: str | None) -> bool:
    draft = {
        "plan_id": "measure",
        "tasks": [
            {"task_id": f"t{n + 1}", "title": t, "order": n, "needs_time": True, "duration_min": 30}
            for n, t in enumerate(TITLES)
        ],
    }
    answer = ai.generate_json(
        "parse_edit", planning._edit_prompt(draft, phrase, NOW, BERLIN), planning.EDIT_SCHEMA
    )
    print(f"        {answer}")
    ok = answer.get("number") == number and answer.get("kind") == kind
    return ok and (not_before is None or answer.get("not_before_local") == not_before)


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
    results: list[bool] = []
    for phrase, tasks, timed, day, minutes in DICTATIONS:
        print(f"«{phrase}»")
        results.append(dictation(ai, phrase, tasks, timed, day, minutes))
        print(f"    {'PASS' if results[-1] else 'FAIL'}")
    for phrase, expected in ROUTES:
        print(f"«{phrase}»")
        results.append(route(ai, phrase, expected))
        print(f"    {'PASS' if results[-1] else 'FAIL'}")
    for phrase, number, kind, not_before in EDITS:
        print(f"«{phrase}»")
        results.append(edit(ai, phrase, number, kind, not_before))
        print(f"    {'PASS' if results[-1] else 'FAIL'}")
    passed, checks = sum(results), results
    print(f"MEASURED: {passed} of {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
