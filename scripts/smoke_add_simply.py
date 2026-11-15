"""Smoke of slice add-simply, real models: the answer to «коли?» and the bare «додай таску».

`parse_when`: «о десятій» (day known: tomorrow) → tomorrow 10:00; «у понеділок о третій» → the nearest Monday
15:00; «завтра о пів на десяту» → tomorrow 09:30; «у середу» → only the day of the nearest Wednesday;
«будь-коли» → an answer with neither day nor time; «які плани на сьогодні?» → no answer. Routing «додай таску»
and «подзвонити сестрі в понеділок о десятій» → `new_task`; the parse of «додай таску» → the request alone
(«Яку задачу додати?»). All 9 must pass. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_add_simply.py
"""

import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google import genai

from mamamemory import assistant, planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

TZ = ZoneInfo("Europe/Berlin")


def _nearest(today: date, weekday: int) -> date:
    """The nearest such weekday, today included."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _task(title: str, day: date | None) -> dict[str, Any]:
    return {"title": title, "constraints": {"day": day.isoformat() if day else None}}


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
    now = datetime.now(UTC)
    today = now.astimezone(TZ).date()
    tomorrow = today + timedelta(days=1)
    monday, wednesday = _nearest(today, 0), _nearest(today, 2)
    cases: list[tuple[str, date | None, dict[str, Any]]] = [
        ("о десятій", tomorrow, {"is_answer": True, "start": f"{tomorrow}T10:00"}),
        ("у понеділок о третій", None, {"is_answer": True, "start": f"{monday}T15:00"}),
        ("завтра о пів на десяту", None, {"is_answer": True, "start": f"{tomorrow}T09:30"}),
        ("у середу", None, {"is_answer": True, "start": None, "day": wednesday.isoformat()}),
        ("будь-коли", None, {"is_answer": True, "start": None, "day": None}),
        ("які плани на сьогодні?", None, {"is_answer": False}),
    ]
    failed = 0
    for text, day, want in cases:
        prompt = planning._when_prompt(text, _task("подзвонити сестрі", day), now, TZ)
        got = ai.generate_json("parse_when", prompt, planning.WHEN_SCHEMA)
        start = planning._start_local(got.get("start_local"))
        ok = got.get("is_answer") is want["is_answer"]
        if want["is_answer"]:
            ok = ok and (start or "")[:16] == (want["start"] or "") if want["start"] else ok and start is None
            if "day" in want:
                ok = ok and planning._day(got.get("day")) == want["day"]
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  when «{text}» -> {got} (expected {want})")
    for text in ("додай таску", "подзвонити сестрі в понеділок о десятій"):
        intent = ai.generate_json(
            "route", assistant._route_prompt(text, None), assistant.route_schema(None)
        ).get("intent")
        ok = intent == "new_task"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  route «{text}» -> {intent} (expected new_task)")
    drafts = planning._parse_tasks(ai, "додай таску", now, TZ)
    ok = bool(drafts) and all(planning._is_add_request(d["title"]) for d in drafts)
    failed += not ok
    titles = [d["title"] for d in drafts]
    print(f"{'PASS' if ok else 'FAIL'}  parse «додай таску» -> {titles} (expected the request alone)")
    total = len(cases) + 3
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
