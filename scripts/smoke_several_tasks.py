"""Smoke of slice several-tasks (F2 S1) with the real model: P-PARSE on phrases with several tasks.

Runs `planning`'s own parse (Gemini Flash-Lite on Vertex AI, location from VERTEX_LOCATION) on five phrases
and checks what the plan needs: how many tasks, which need a time, the named day and the named duration.
No Google sign-in and no Calendar. Exit 0 when every phrase passes.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_several_tasks.py
"""

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from google import genai

from mamamemory import planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

# Monday 9 November 2026, 10:07 Berlin: "у понеділок" is today, "у середу" is 11 November.
NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)


@dataclass(frozen=True)
class Case:
    phrase: str
    tasks: int
    timed: int
    days: set[str]
    durations: set[int]


CASES = [
    Case(
        "У понеділок подзвонити нотаріусу на пів години, купити насіння, "
        "а в середу о десятій до лікаря на годину",
        3, 2, {"2026-11-09"}, {30, 60},
    ),
    Case("Купити ліки і хліб", 2, 0, set(), set()),
    Case("Завтра на годину розібрати документи і зателефонувати сестрі на пятнадцять хвилин", 2, 2,
         {"2026-11-10"}, {60, 15}),
    Case("У четвер передзвонити пані Шмідт щодо аналізу HbA1c", 1, 1, {"2026-11-12"}, set()),
    Case("Полити город колись цього тижня і в пятницю о девятій на дві години в лабораторію",
         2, 1, set(), {120}),
]  # fmt: skip


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
    for case in CASES:
        drafts = planning._parse_tasks(ai, case.phrase, NOW, ZoneInfo("Europe/Berlin"))
        timed = [d for d in drafts if d["needs_time"]]
        days = {d["constraints"]["day"] for d in drafts if d["constraints"]["day"]}
        durations = {d["duration_min"] for d in drafts if d["duration_min"]}
        ok = (
            len(drafts) == case.tasks
            and len(timed) == case.timed
            and case.days <= days
            and case.durations <= durations
        )
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {case.phrase}")
        for d in drafts:
            print(f"        {d}")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(CASES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
