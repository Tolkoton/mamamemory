"""Disputed contract tests of the slice work-recall: each fixes one reading of a question to the contract
`.engine/slices/work-recall.md` (Q1-Q3 of the hand-in). Not sealed until the slice planner answers.

Written by the slice tester from the sealed contract, without the code. Expected values are written by hand.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Berlin); Tuesday 10 November 00:30 in Berlin is
Monday 9 November 23:30Z.
"""

from tests.work_recall_world import NOTHING, Recall, iso

TUESDAY_10 = ("2026-11-10", "10.11.2026", "10 листопада", "10 november", "november 10")
THURSDAY_12 = ("2026-11-12", "12.11.2026", "12 листопада", "12 november", "november 12")


def has_any(prompt: str, forms: tuple[str, ...]) -> bool:
    low = prompt.lower()
    return any(form in low for form in forms)


def test_q1_prompt_names_weekday_and_date_in_the_calendar_zone() -> None:
    w = Recall()
    w.put("e1", "працюю над договором купівлі", iso(2026, 11, 9, 23, 30))
    w.answer("що я робила з договором?")
    prompt = w.ai.work_prompt()
    # the entry: Tuesday 10 November in Berlin, not Monday 9 as in UTC
    assert has_any(prompt, TUESDAY_10), prompt
    assert has_any(prompt, ("вівторок", "tuesday")), prompt
    assert not has_any(prompt, ("понеділок", "monday")), prompt
    # now: Thursday 12 November
    assert has_any(prompt, THURSDAY_12), prompt
    assert has_any(prompt, ("четвер", "thursday")), prompt


def test_q2_whitespace_only_answer_is_nothing() -> None:
    w = Recall()
    w.put("e1", "працюю над договором купівлі", iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"found": True, "answer": "  \n "}
    assert w.answer("що я робила з договором?").text == NOTHING


def test_q3_journal_of_entries_without_valid_at_only_is_nothing_without_model_or_calendar() -> None:
    w = Recall()
    w.put("a", "без часу", None)
    w.put("b", "час словами", "вчора")
    reply = w.answer("що я робила?")
    assert reply.text == NOTHING
    assert w.ai.calls == []
    assert w.calendar.log == []
