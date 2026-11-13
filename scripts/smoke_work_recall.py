"""Smoke of slice work-recall (F4 S2), real model: routing of work questions, answers from the journal.

Routing: «що я робила з договором?», «над чим я працювала вчора?», «що я робила вчора?»,
«над чим я працювала?» → `work_question`; «які плани на сьогодні?» → `schedule`; «зараз працюю над звітом» →
`working_on`. Answers from three entries (договір — yesterday 12:00 Europe/Berlin, аналізи пані Шмідт — today
09:00, звіт — a week ago): «що я робила з договором?» → «договор» and «12:00»;
«що я робила вчора?» → «договор»;
«що я робила з машиною?» → nothing found. All 9 must pass. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_work_recall.py
"""

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google import genai
from google.oauth2.credentials import Credentials

from mamamemory import assistant
from mamamemory.access import Session
from mamamemory.cases import worklog
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.store import InMemoryStore

TZ = "Europe/Berlin"
ROUTES = [
    ("що я робила з договором?", "work_question"),
    ("над чим я працювала вчора?", "work_question"),
    ("що я робила вчора?", "work_question"),
    ("над чим я працювала?", "work_question"),
    ("які плани на сьогодні?", "schedule"),
    ("зараз працюю над звітом", "working_on"),
]


class Calendar:
    """Only the zone: `answer` asks the calendar for nothing else."""

    def timezone(self) -> str:
        return TZ


def _no_google() -> Credentials:
    raise RuntimeError("the smoke signs in to no Google account")


def _at(day: datetime, hour: int) -> datetime:
    return datetime.combine(day.date(), time(hour), tzinfo=ZoneInfo(TZ))


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

    now = datetime.now(UTC)
    local = now.astimezone(ZoneInfo(TZ))
    session = Session(account_id="smoke", google_credentials=_no_google)
    store = InMemoryStore()
    worklog.add(
        session,
        "працюю над договором купівлі городу",
        "e1",
        store=store,
        now=_at(local - timedelta(days=1), 12),
    )
    worklog.add(session, "сиджу над аналізами пані Шмідт", "e2", store=store, now=_at(local, 9))
    worklog.add(
        session, "роблю звіт для податкової", "e3", store=store, now=_at(local - timedelta(days=7), 15)
    )
    calendar: Any = Calendar()
    checks: list[tuple[str, Callable[[str], bool]]] = [
        ("що я робила з договором?", lambda t: "договор" in t.lower() and "12:00" in t),
        ("що я робила вчора?", lambda t: "договор" in t.lower()),
        ("що я робила з машиною?", lambda t: t == worklog.NOTHING),
    ]
    for question, good in checks:
        reply = worklog.answer(session, question, store=store, ai=ai, calendar=calendar, now=now).text
        ok = good(reply)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  answer «{question}» -> {reply!r}")
    total = len(ROUTES) + len(checks)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
