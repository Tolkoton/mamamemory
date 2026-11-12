"""Smoke of slice time-limits (F2 S2) with the real model: P-PARSE on mama's answers about her hours.

Runs `planning`'s own limits parse (Gemini Flash-Lite on Vertex AI) on five answers from the contract and
checks the days, the hours or «як минулого разу». No Google sign-in and no Calendar. Exit 0 when all pass.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_time_limits.py
"""

import os
import sys
from datetime import time

from google import genai

from mamamemory import planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.planning.placement import Limits

LAST = Limits(frozenset(range(5)), time(9), time(18))
# answer, saved limits before it, expected limits after it
CASES = [
    ("будні з дев'ятої до шостої", None, Limits(frozenset(range(5)), time(9), time(18))),
    ("щодня з восьмої до восьмої вечора, крім неділі", None, Limits(frozenset(range(6)), time(8), time(20))),
    ("так", LAST, LAST),
    ("як минулого разу", LAST, LAST),
    ("тепер з десятої до четвертої", LAST, Limits(frozenset(range(5)), time(10), time(16))),
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
    for text, saved, expected in CASES:
        answer = ai.generate_json("parse_limits", planning._limits_prompt(text), planning.LIMITS_SCHEMA)
        chosen, _ = planning._limits_from(answer, saved)
        ok = chosen == expected
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {text}\n        {answer} -> {chosen}")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(CASES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
