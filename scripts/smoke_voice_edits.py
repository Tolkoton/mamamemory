"""Smoke of slice voice-edits (F2 S5) with the real model: the route on a shown plan and the edit parse.

(a) `assistant`'s own route prompt with `reply_to` of a plan: five edits → `edit`,
«ще купити хліб» → `new_task`, «так» → `yes`, «ну не знаю» → `other`. (b) `planning`'s own `parse_edit`
on the five edits of a plan of three tasks → the right task, kind and field. Gemini Flash-Lite on Vertex AI;
no Google sign-in and no Calendar. Exit 0 when all 13 pass.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_voice_edits.py
"""

import os
import sys
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from google import genai

from mamamemory import assistant, planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
"""Monday 9 November 2026, 10:07 Berlin: «четвер» is 12 November, «середа» 11 November."""
BERLIN = ZoneInfo("Europe/Berlin")
TITLES = ["подзвонити нотаріусу", "до лікаря", "купити насіння"]
PLAN = Question("plan", "smoke", "fp")
EDITS = [
    ("перенеси нотаріуса на четвер", "подзвонити нотаріусу", "move", {"day": "2026-11-12"}),
    ("лікар о десятій у середу", "до лікаря", "move", {"start_local": "2026-11-11T10:00:00"}),
    ("лікар не раніше десятої", "до лікаря", "not_before", {"not_before_local": "10:00"}),
    ("прибери насіння", "купити насіння", "remove", {}),
    ("нотаріус без часу", "подзвонити нотаріусу", "untimed", {}),
]
ROUTES = [(text, "edit") for text, *_ in EDITS] + [
    ("ще купити хліб", "new_task"),
    ("так", "yes"),
    ("ну не знаю", "other"),
]


def draft() -> dict[str, Any]:
    tasks = [
        {"task_id": f"t{n + 1}", "title": title, "order": n, "needs_time": True, "duration_min": 30}
        for n, title in enumerate(TITLES)
    ]
    return {"plan_id": "smoke", "tasks": tasks}


def edit_ok(answer: dict[str, Any], title: str, kind: str, fields: dict[str, str]) -> bool:
    """The parse names the task and the kind, and `_edited` takes it with the expected field."""
    tasks = planning._edited(draft(), answer)
    if tasks is None or answer.get("kind") != kind or TITLES[answer["number"] - 1] != title:
        return False
    task = next(t for t in tasks if t["title"] == title)
    if "day" in fields:
        return task["constraints"]["day"] == fields["day"] and task["start_local"] is None
    if "start_local" in fields:
        return bool(task["start_local"] == fields["start_local"])
    if "not_before_local" in fields:
        return bool(task["constraints"].get("not_before_local") == fields["not_before_local"])
    if kind == "remove":
        return bool(task["constraints"].get("removed"))
    return task["needs_time"] is False


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
            "route", assistant._route_prompt(text, PLAN, TITLES), assistant.route_schema(PLAN)
        ).get("intent")
        ok = intent == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» -> {intent} (expected {expected})")
    for text, title, kind, fields in EDITS:
        answer = ai.generate_json(
            "parse_edit", planning._edit_prompt(draft(), text, NOW, BERLIN), planning.EDIT_SCHEMA
        )
        ok = edit_ok(answer, title, kind, fields)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  edit «{text}»\n        {answer}")
    total = len(ROUTES) + len(EDITS)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
