"""Smoke of slice case-recall (F4 S3), real models: routing of case questions and answers from a case.

Routing: «що ми знаємо про пані Шмідт?», «що вже з'ясували по городу?», «нагадай про пана Коха» → `recall`;
«що я робила з договором?» → `work_question`; «запиши до пані Шмідт: аналізи в нормі» → `note`.
Answers: cases «пані Шмідт» (ТТГ 4,9), «купівля городу» (договір підписати до п'ятниці), «пан Кох»; journal
«працюю над договором купівлі городу» (yesterday 12:00 Europe/Berlin) and «сиджу над аналізами пана Коха»:
Шмідт → «4,9» or «4.9»; город → «п'ятниц» and «12:00», no «Кох»; пан Мюллер → not found. All 8 must pass.
No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_case_recall.py
"""

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google import genai
from google.oauth2.credentials import Credentials

from mamamemory import assistant, cases
from mamamemory.access import Session
from mamamemory.cases import recall, worklog
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.store import InMemoryStore

TZ = "Europe/Berlin"
ROUTES = [
    ("що ми знаємо про пані Шмідт?", "recall"),
    ("що вже з'ясували по городу?", "recall"),
    ("нагадай про пана Коха", "recall"),
    ("що я робила з договором?", "work_question"),
    ("запиши до пані Шмідт: аналізи в нормі", "note"),
]
CASES = [
    ("c1", "пані Шмідт", "Пацієнтка, щитоподібна залоза.", "m1", "ТТГ 4,9, повторити через шість тижнів."),
    ("c2", "купівля городу", "Купівля ділянки під город.", "m2", "Договір купівлі підписати до п'ятниці."),
    ("c3", "пан Кох", "Пацієнт, залізо.", "m3", "Феритин вісім, призначити залізо."),
]


class Calendar:
    """Only the zone: `recall` asks the calendar for nothing else."""

    def timezone(self) -> str:
        return TZ


def _no_google() -> Credentials:
    raise RuntimeError("the smoke signs in to no Google account")


def _at(day: datetime, hour: int) -> datetime:
    return datetime.combine(day.date(), time(hour), tzinfo=ZoneInfo(TZ))


def _seed(session: Session, store: InMemoryStore, now: datetime) -> None:
    """Three cases with one placed note each, and two journal entries."""
    for case_id, name, description, material_id, text in CASES:
        store.set(
            session.account_id,
            f"{cases.CASES}/{case_id}",
            {"name": name, "description": description, "created": now.isoformat(), "stale": False},
        )
        store.set(session.account_id, f"{cases.MATERIALS}/{material_id}",
                  {"kind": "note", "text": text, "state": "placed", "case_id": case_id, "pending_case": None,
                   "gs_uri": None, "mime": None, "created": now.isoformat(),
                   "in_description": True})  # fmt: skip
    local = now.astimezone(ZoneInfo(TZ))
    worklog.add(
        session,
        "працюю над договором купівлі городу",
        "e1",
        store=store,
        now=_at(local - timedelta(days=1), 12),
    )
    worklog.add(session, "сиджу над аналізами пана Коха", "e2", store=store, now=_at(local, 9))


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
    session = Session(account_id="smoke", google_credentials=_no_google)
    store = InMemoryStore()
    _seed(session, store, now)
    calendar: Any = Calendar()
    checks: list[tuple[str, Callable[[str], bool]]] = [
        ("що ми знаємо про пані Шмідт?", lambda t: "4,9" in t or "4.9" in t),
        ("що вже з'ясували по городу?", lambda t: "п'ятниц" in t.lower().replace("’", "'") and "12:00" in t
         and "кох" not in t.lower()),
        ("що ми знаємо про пана Мюллера?", lambda t: t == recall.NOT_FOUND),
    ]  # fmt: skip
    for question, good in checks:
        reply = recall.recall(session, question, store=store, ai=ai, calendar=calendar, now=now).text
        ok = good(reply)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  recall «{question}» -> {reply!r}")
    total = len(ROUTES) + len(checks)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
