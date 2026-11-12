"""Smoke of slice clarify with the real model: an ambiguous phrase gets a clarification, not a guess.

(a) «пан Вольф просив виписати рецепт на леводопу» → `unsure` with {note, new_task}. (b) «ні, це не нова, це
до Бергер» under «Створити справу «пані Бергерова»?» → `unsure` or `case_name` (anything but `edit`).
(c) «нотатка» on the clarification «записати нотаткою до справи чи поставити задачею в календар?» → option 1.
All 3 must pass. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_clarify.py
"""

import os
import sys

from google import genai

from mamamemory import assistant, cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.replies import Question


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

    wolf = "пан Вольф просив виписати рецепт на леводопу"
    answer = ai.generate_json("route", assistant._route_prompt(wolf, None), assistant.route_schema(None))
    ok = answer.get("intent") == "unsure" and set(answer.get("options") or []) == {"note", "new_task"}
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  route «{wolf}» -> {answer}")

    berger = "ні, це не нова, це до Бергер"
    case_q = Question("case", "smoke", None)
    prompt = assistant._route_prompt(berger, case_q, None, cases.ask_text("пані Бергерова"))
    answer = ai.generate_json("route", prompt, assistant.route_schema(case_q))
    ok = answer.get("intent") in ("unsure", "case_name")
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  route «{berger}» under a case question -> {answer}")

    prompt = assistant._option_prompt(["note", "new_task"], "нотатка")
    option = ai.generate_json("choose_option", prompt, assistant.OPTION_SCHEMA).get("option")
    ok = option == 1
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  choose «нотатка» -> {option}")

    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of 3")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
