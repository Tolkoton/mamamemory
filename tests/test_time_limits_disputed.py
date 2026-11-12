"""Disputed contract tests of the slice time-limits: each takes one reading of a question to the contract
(Q1–Q3 in the tester's hand-in) and is sealed only after the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/time-limits.md`, without the code.
"""

from datetime import UTC, datetime

from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.test_one_task_planning import instant, shown
from tests.time_limits_world import WEEKDAYS, Limited, limited, limits_question, parsed

AFTERNOONS = parsed(days=WEEKDAYS, start_local="14:00", end_local="18:00")


def first_planning(w: Limited) -> None:
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    plan_id, fingerprint = shown(w.answer_limits(question.id, "будні з другої до шостої"))
    w.confirm(plan_id, fingerprint)


def test_q1_as_last_time_question_names_the_hours_as_hh_mm() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    w.ai.says(task(MEDICINE))
    again = w.start("купити ліки")
    limits_question(again)
    assert "14:00–18:00" in again.text, again.text


def test_q2_partial_answer_over_saved_limits_changes_only_what_it_names() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    w.ai.says(task(MEDICINE))
    question = limits_question(w.start("купити ліки"))
    # «так, але тепер з десятої»: only the start is named.
    w.ai.limits = parsed(same_as_last=True, start_local="10:00")
    reply = w.answer_limits(question.id, "так, але тепер з десятої")
    assert w.saved() == (WEEKDAYS, "10:00", "18:00")
    assert reply.plan is not None, reply
    # Monday 10:15 Berlin (the first step) is inside 10:00–18:00: 09:15Z.
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)


def test_q3_limits_answer_after_the_plan_is_shown_returns_the_plan_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    plan_id, fingerprint = shown(w.answer_limits(question.id, "будні з другої до шостої"))
    w.ai.limits = parsed(days=[0], start_local="08:00", end_local="09:00")
    reply = w.answer_limits(question.id, "лише в понеділок з восьмої до дев'ятої")
    assert reply.question is not None, reply
    assert (reply.question.kind, reply.question.id, reply.question.fingerprint) == (
        "plan",
        plan_id,
        fingerprint,
    )
