"""Disputed contract tests of the slice working-on: each fixes one reading of a question to the contract
`.engine/slices/working-on.md` (Q1-Q4 of the hand-in). Not sealed until the slice planner answers.

Written by the slice tester from the sealed contract, without the code. Expected values are written by hand.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tests.working_on_world import NOW_ISO, Work


def test_q1_text_ending_in_a_full_stop_is_echoed_literally_with_the_added_full_stop() -> None:
    w = Work()
    reply = w.log("сиджу над аналізами.", "e1")
    assert reply.text == "Записала: сиджу над аналізами.."


def test_q2_repeat_with_same_entry_id_overwrites_with_the_second_call() -> None:
    w = Work()
    w.log("працюю над договором", "e1")
    later = datetime(2026, 11, 9, 9, 8, 0, tzinfo=UTC)
    w.log("працюю над договором купівлі", "e1", now=later)
    entries = w.entries()
    assert [entry_id for entry_id, _ in entries] == ["e1"]
    document = w.entry("e1")
    assert document is not None
    assert document["text"] == "працюю над договором купівлі"
    assert document["at"] == "2026-11-09T09:08:00+00:00"


def test_q3_whitespace_only_phrase_writes_one_document_with_empty_text() -> None:
    w = Work()
    reply = w.log("   ", "e1")
    w.log("   ", "e1")
    assert reply.question is None
    assert [entry_id for entry_id, _ in w.entries()] == ["e1"]
    document = w.entry("e1")
    assert document is not None
    assert document["text"] == ""


def test_q4_time_given_in_another_zone_is_stored_as_utc() -> None:
    w = Work()
    berlin = datetime(2026, 11, 9, 10, 7, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    w.log("працюю над договором", "e1", now=berlin)
    document = w.entry("e1")
    assert document is not None
    assert document["at"] == NOW_ISO
