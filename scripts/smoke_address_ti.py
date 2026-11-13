"""Smoke of slice address-ti, real model: answers from the journal and from a case address mom on «ти».

The same entries and cases as smoke S2 (`smoke_work_recall.py`), S3 (`smoke_case_recall.py`). `answer_work` on
«що я робила з договором?», «що я робила вчора?» and `answer_case` on «що ми знаємо про пані Шмідт?», «що вже
з'ясували по городу?», each three times: no answer has a polite-plural or third-person word (whole words, any
case; `answer_work` also no «вона», «її»). All 12 must pass. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_address_ti.py
"""

import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google import genai
from smoke_case_recall import Calendar, _at, _no_google, _seed

from mamamemory.access import Session
from mamamemory.cases import recall, worklog
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.store import InMemoryStore

TZ = "Europe/Berlin"
REPEATS = 3
PLURAL = r"ви|вас|вам|вами|ваш\w*"
VERBS = r"працювали|сиділи|робили|дзвонили|писали|з'ясували|підписали"
THIRD = r"мам(?:а|и|і|у|ою|ин\w*)"
# `\b` does not hold at an apostrophe, so word edges are written out; «ми з'ясували» is allowed.
EDGE_L, EDGE_R = r"(?<![\w'])", r"(?![\w'])"
BANNED = re.compile(
    rf"{EDGE_L}(?:{PLURAL}|{THIRD}){EDGE_R}|(?<!\bми )(?<![\w'])(?:{VERBS}){EDGE_R}", re.IGNORECASE
)
BANNED_WORK = re.compile(rf"{EDGE_L}(?:вона|її){EDGE_R}", re.IGNORECASE)
WORK_QUESTIONS = ["що я робила з договором?", "що я робила вчора?"]
CASE_QUESTIONS = ["що ми знаємо про пані Шмідт?", "що вже з'ясували по городу?"]


def _banned(text: str, *, work: bool) -> list[str]:
    plain = text.replace("’", "'")
    found = [m.group(0) for m in BANNED.finditer(plain)]
    return found + ([m.group(0) for m in BANNED_WORK.finditer(plain)] if work else [])


def _seed_work(session: Session, store: InMemoryStore, now: datetime) -> None:
    """The three journal entries of smoke S2."""
    local = now.astimezone(ZoneInfo(TZ))
    entries = [
        ("працюю над договором купівлі городу", local - timedelta(days=1), 12),
        ("сиджу над аналізами пані Шмідт", local, 9),
        ("роблю звіт для податкової", local - timedelta(days=7), 15),
    ]
    for number, (text, day, hour) in enumerate(entries, 1):
        worklog.add(session, text, f"e{number}", store=store, now=_at(day, hour))


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
    session = Session(account_id="smoke", google_credentials=_no_google)
    work_store, case_store = InMemoryStore(), InMemoryStore()
    _seed_work(session, work_store, now)
    _seed(session, case_store, now)
    calendar: Any = Calendar()
    failed = total = 0
    for _ in range(REPEATS):
        for question in WORK_QUESTIONS:
            reply = worklog.answer(
                session, question, store=work_store, ai=ai, calendar=calendar, now=now
            ).text
            bad = _banned(reply, work=True)
            failed, total = failed + bool(bad), total + 1
            print(f"{'FAIL' if bad else 'PASS'}  answer_work «{question}» {bad or ''} -> {reply!r}")
        for question in CASE_QUESTIONS:
            reply = recall.recall(session, question, store=case_store, ai=ai, calendar=calendar, now=now).text
            bad = _banned(reply, work=False)
            failed, total = failed + bool(bad), total + 1
            print(f"{'FAIL' if bad else 'PASS'}  answer_case «{question}» {bad or ''} -> {reply!r}")
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
