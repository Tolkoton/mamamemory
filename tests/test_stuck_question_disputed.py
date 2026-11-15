"""Disputed tests of the slice stuck-question: each depends on a question to the contract (Q1-Q5).

Written by the slice tester from the sealed contract `.engine/slices/stuck-question.md`, without the code.
This file is sealed only after the slice planner answers. `NOW` is Monday 9 November 2026, 10:07 Berlin.
Superseded by `.engine/slices/add-simply.md` (2026-11-14): a draft of mode `add` never asks the duration, the
limits or the priorities, so the asking drafts here are drafts of the week (`plan_week`); a task said into a
new `add` draft names its time (`TEA_AT`) to be shown at once, or is asked «коли?».
"""

import copy
from datetime import timedelta

from tests.add_simply_world import ask_when
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.stuck_question_world import TEA, ask_named, asked, stuck
from tests.test_one_task_planning import NOW, shown
from tests.time_limits_world import parsed

# Wednesday 11 November 2026, 15:00 Berlin: inside the horizon from NOW and from NOW + 25 h.
TEA_AT = "2026-11-11T15:00"


def test_q1_asking_draft_exactly_24h_old_is_still_shown() -> None:
    # «старший за 24 год»: at exactly asked_at + 24 h it is not yet older.
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    opened = w.open(NOW + timedelta(hours=24))
    assert opened is not None
    assert opened.reply.question == question
    assert opened.reply.text == ask_named(NOTARY)


def test_q2_shown_plan_older_than_24h_is_shown_until_the_horizon_as_f2() -> None:
    w = stuck()
    plan_id, _ = shown(w.plan_week(task(NOTARY)))
    opened = w.open(NOW + timedelta(hours=30))
    assert opened is not None
    assert opened.reply.plan is not None, opened
    assert opened.reply.plan.plan_id == plan_id


def test_q3_priorities_naming_only_numbers_outside_the_list_is_no_answer() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    before = copy.deepcopy(w.draft())
    for numbers in ((4,), (0, 7)):
        w.ai.choose(order=numbers)
        assert w.try_priorities(question.id, "п'яте") is None, numbers
        assert w.draft() == before, numbers


def test_q4_the_new_draft_that_replaces_an_asking_one_has_a_new_plan_id() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    reply = w.say(
        "а мені треба чай у середу о третій",
        question,
        intent="new_task",
        spoken=(task(TEA, start_local=TEA_AT),),
    )
    assert reply.plan is not None, reply
    assert reply.plan.plan_id != question.id
    current = w.draft()
    assert current is not None and current["plan_id"] != question.id

    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.says(task(TEA, start_local=TEA_AT))
    late = w.start_in("мені треба чай у середу о третій", week=False, now=NOW + timedelta(hours=25))
    assert late.plan is not None, late
    assert late.plan.plan_id != question.id


def test_q5_new_task_under_the_limits_question_asks_the_new_draft_its_own_question_not_the_limits() -> None:
    # add-simply: the new draft is of mode `add` — it asks «коли?» of its task, never the limits.
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    w.ai.limits = parsed()
    reply = w.say("а мені треба чай", question, intent="new_task", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    again = asked(reply, "when")
    assert again.id != question.id
    assert ask_when(TEA) in reply.text, reply
    assert w.saved() is None
