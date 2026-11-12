"""Disputed contract tests of the slice priorities: each takes one reading of a question to the contract
(Q1, Q2 in the tester's hand-in) and is sealed only after the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/priorities.md`, without the code.
"""

from datetime import UTC, datetime

from tests.priorities_world import priorities_question, prioritized
from tests.several_tasks_world import MEDICINE, NOTARY, SISTER, items, task
from tests.test_one_task_planning import instant, shown


def test_q1_same_with_named_numbers_keeps_the_order() -> None:
    w = prioritized(task(NOTARY), task(MEDICINE), task(SISTER))
    question = priorities_question(w.start())
    before = w.orders()
    reply = w.rank(question.id, 3, same=True)
    assert w.orders() == before
    shown_items = items(reply)
    assert instant(shown_items[NOTARY][0]) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert instant(shown_items[SISTER][0]) == datetime(2026, 11, 9, 10, 15, tzinfo=UTC)


def test_q2_priorities_answer_after_the_plan_is_shown_returns_the_plan_question() -> None:
    w = prioritized(task(NOTARY), task(MEDICINE))
    question = priorities_question(w.start())
    plan_id, fingerprint = shown(w.rank(question.id, 2))
    reply = w.rank(question.id, 1)
    assert reply.question is not None, reply
    assert (reply.question.kind, reply.question.id, reply.question.fingerprint) == (
        "plan",
        plan_id,
        fingerprint,
    )
