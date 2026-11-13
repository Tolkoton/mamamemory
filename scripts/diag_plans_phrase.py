"""Diagnostic (not a smoke): what the real models do with «які в нас плани?» under open planning questions.

Prints the route intent with no reply_to, and the raw answers of the limits and priorities parsers to the same
phrases. No Google sign-in, no Firestore.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/diag_plans_phrase.py
"""

import os
import sys

from google import genai

from mamamemory import assistant, planning
from mamamemory.config import Config
from mamamemory.integrations.ai import AI

PHRASES = ["які в нас плани?", "які в нас плани на сьогодні?", "які плани?", "що в мене сьогодні?"]
DRAFT = {"tasks": [{"id": "t1", "title": "Finanzamt Umsatzsteuer, Miete", "order": 0},
                   {"id": "t2", "title": "aSXSA", "order": 1}]}  # fmt: skip


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
    planning._listed = lambda draft: draft["tasks"]  # the prompt only needs the titles here
    for text in PHRASES:
        route = ai.generate_json("route", assistant._route_prompt(text, None), assistant.route_schema(None))
        limits = ai.generate_json("parse_limits", planning._limits_prompt(text), planning.LIMITS_SCHEMA)
        chosen, _ = planning._limits_from(limits, None)
        prio = ai.generate_json(
            "parse_priorities", planning._priorities_prompt(DRAFT, text), planning.PRIORITIES_SCHEMA
        )
        print(f"«{text}»\n  route: {route}\n  limits: {limits} -> taken: {chosen is not None}")
        print(f"  priorities: {prio}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
