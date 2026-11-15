"""Disputed contract tests of the slice add-simply: each takes one reading of a line of
`.engine/slices/add-simply.md` that can be read two ways, and names its question (Q1, Q2 of the hand-in).

Written by the slice tester from the sealed contract, without the code.
Sealed after the slice planner's answer. `NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1).
"""

from tests.add_simply_world import NAMED_OUTSIDE, WEDNESDAY, add_simply, when, when_question
from tests.several_tasks_world import SISTER, task


def test_Q1_the_when_prompt_carries_now_the_zone_the_title_and_the_known_day() -> None:
    """Q1: «підказка з «зараз», зоною календаря, назвою задачі й відомим днем» — «зараз» is written as
    the local time of the calendar's zone (10:07), the zone by its IANA name (Europe/Berlin), the known
    day as its ISO date or as «11 листопада»."""
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    w.answer_when(question.id, when(day=WEDNESDAY), "у середу")
    first = w.ai.when_prompts[0]
    assert SISTER in first, first
    assert "Europe/Berlin" in first, first
    assert "10:07" in first, first
    w.answer_when(question.id, when(is_answer=False), "які плани?")
    with_day = w.ai.when_prompts[-1]
    assert WEDNESDAY in with_day or "11 листопада" in with_day, with_day


def test_Q2_a_past_start_local_says_the_time_is_outside_as_a_named_time() -> None:
    """Q2: «`start_local` у минулому — далі як для названого часу поза горизонтом (`NAMED_OUTSIDE`,
    як було)» — for a single task the reply's text carries `NAMED_OUTSIDE`."""
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    past = when(day="2026-11-09", start_local="2026-11-09T08:00")
    reply = w.answer_when(question.id, past, "сьогодні о восьмій")
    assert reply is not None and NAMED_OUTSIDE in reply.text, reply
