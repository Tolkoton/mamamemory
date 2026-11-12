"""Disputed integration test of the feature f1-skeleton: AC5 (question Q1 of the hand-in).

AC5 asks that the owner be shown «як Gemini почув 5–10 справжніх маминих фраз», while the closing slice S5
measured synthesized recordings and left mama's own phrases to a card on the board. Reading taken: until the
owner answers that card, AC5's part about mama's phrases holds when the report says the measured voice is not
mama's, names the 5–10 phrases as what is left to the owner, and a task file asks for them. Not sealed until
the slice planner answers.
"""

import re

from tests.f1_measure_sources import report_text, task_files


def test_AC5_mama_phrases_are_named_as_left_to_the_owner_on_a_card() -> None:
    text = report_text()
    assert "синтез" in text.lower() and "не мамин" in text.lower(), (
        "the report does not say whose voice it was"
    )
    assert re.search(r"5\s*[–-]\s*10", text), "the report does not name the 5–10 phrases"
    cards = [
        path
        for path in task_files()
        if re.search(r"5\s*[–-]\s*10", body := path.read_text("utf-8")) and "фраз" in body
    ]
    assert cards, "no task file asks the owner for 5–10 of mama's phrases"
