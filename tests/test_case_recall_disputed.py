"""Disputed contract tests of the slice case-recall: each fixes one reading of a question to the contract
`.engine/slices/case-recall.md` (Q1-Q4 of the hand-in). Not sealed until the slice planner answers.

Written by the slice tester from the sealed contract, without the code. Expected values are written by hand.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Berlin); Monday 9 November 23:30Z is Tuesday 10 November
00:30 in Berlin.
"""

from datetime import UTC, datetime

from tests.case_recall_world import NOT_FOUND, CaseRecall, nothing_yet
from tests.work_recall_world import iso

SCHMIDT = "пані Шмідт"
QUESTION = "що ми знаємо про пані Шмідт?"
MONDAY_9 = (
    "2026-11-09",
    "09.11.2026",
    "9.11.2026",
    "9 листопада",
    "09 листопада",
    "9 november",
    "november 9",
)
TUESDAY_10 = ("2026-11-10", "10.11.2026", "10 листопада", "10 november", "november 10")
THURSDAY_5 = (
    "2026-11-05",
    "05.11.2026",
    "5.11.2026",
    "5 листопада",
    "05 листопада",
    "5 november",
    "november 5",
)


def has_any(prompt: str, forms: tuple[str, ...]) -> bool:
    low = prompt.lower()
    return any(form in low for form in forms)


def schmidt() -> CaseRecall:
    w = CaseRecall()
    w.put_case("c-s", SCHMIDT, "пацієнтка")
    w.ai.pick(SCHMIDT)
    return w


def test_Q1_each_material_carries_its_kind_and_its_utc_date_without_time() -> None:
    w = schmidt()
    w.put_material("m1", "ТТГ 4,9", "c-s", kind="note", created=datetime(2026, 11, 9, 23, 30, tzinfo=UTC))
    w.put_material("m2", "знімок УЗД", "c-s", kind="photo", created=datetime(2026, 11, 5, 8, 15, tzinfo=UTC))
    w.recall(QUESTION)
    prompt = w.ai.case_prompt()
    # the date in UTC: 9 November, not 10 November as in Berlin
    assert has_any(prompt, MONDAY_9), prompt
    assert not has_any(prompt, TUESDAY_10), prompt
    assert has_any(prompt, THURSDAY_5), prompt
    # without the time
    for clock in ("23:30", "00:30", "08:15", "09:15"):
        assert clock not in prompt, (clock, prompt)
    # the kind, in the code's word or in Ukrainian
    assert has_any(prompt, ("note", "нотатк")), prompt
    assert has_any(prompt, ("photo", "фото")), prompt


def test_Q2_each_entry_carries_its_weekday_and_date_in_the_calendar_zone() -> None:
    w = schmidt()
    w.put("e1", "працюю над аналізами пані Шмідт", iso(2026, 11, 9, 23, 30))
    w.recall(QUESTION)
    prompt = w.ai.case_prompt()
    # Tuesday 10 November in Berlin, not Monday 9 as in UTC
    assert has_any(prompt, TUESDAY_10), prompt
    assert has_any(prompt, ("вівторок", "tuesday")), prompt
    assert not has_any(prompt, ("понеділок", "monday")), prompt


def test_Q3_found_other_than_json_true_is_nothing_yet() -> None:
    for found in ("true", 1, "так"):
        w = schmidt()
        w.put_material("m1", "ТТГ 4,9", "c-s")
        w.ai.case_answer = {"found": found, "answer": "ТТГ 4,9."}
        reply = w.recall(QUESTION)
        assert reply.text == nothing_yet(SCHMIDT), (found, reply)


def test_Q4_a_number_as_a_string_or_a_float_is_not_found() -> None:
    for value in ("1", 1.0):
        w = schmidt()
        w.put_material("m1", "ТТГ 4,9", "c-s")
        w.ai.pick_value(value)
        reply = w.recall(QUESTION)
        assert reply.text == NOT_FOUND, (value, reply)
        assert w.ai.case_prompts() == [], value
