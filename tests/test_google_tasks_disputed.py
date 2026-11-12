"""Disputed contract tests of the slice google-tasks: each fixes the reading taken on one question to the
contract `.engine/slices/google-tasks.md` (Q1-Q4 of the slice tester's hand-in), sealed after the planner's
answer.

Written by the slice tester from the sealed contract, without the code.
"""

from mamamemory.integrations.google_work import TaskItem
from mamamemory.replies import Question
from tests.google_tasks_world import BILLS, CHOOSE_TIMED, PARCEL, TO_TASKS, number_of, with_tasks
from tests.priorities_world import listed, priorities_question
from tests.several_tasks_world import MEDICINE, NOTARY, SEEDS, WRITTEN, task
from tests.test_google_tasks_planning import TK_BILLS, TK_PARCEL, bills_timed, two_and_bills


def test_Q1_tasks_from_tasks_keep_the_order_list_open_tasks_gives() -> None:
    w = two_and_bills(TK_PARCEL)
    first = w.start()
    priorities_question(first)
    listed(first.text, NOTARY, MEDICINE, BILLS, PARCEL)
    w = with_tasks(task(NOTARY), task(MEDICINE), open_tasks=(TK_PARCEL, TK_BILLS))
    first = w.start()
    priorities_question(first)
    listed(first.text, NOTARY, MEDICINE, PARCEL, BILLS)


def test_Q2_closing_in_tasks_alone_does_not_add_the_tasks_line() -> None:
    w = two_and_bills()
    plan_id, fingerprint = bills_timed(w)
    done = w.confirm(plan_id, fingerprint)
    assert w.tc.completed == ["tk-1"]
    assert w.tc.inserted == []
    assert done.text == WRITTEN
    assert TO_TASKS not in done.text


def test_Q3_untimed_spoken_task_is_still_listed_in_the_priorities_question() -> None:
    w = with_tasks(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None), open_tasks=(TK_BILLS,))
    first = w.start()
    priorities_question(first)
    listed(first.text, NOTARY, SEEDS, BILLS)


def test_Q4_one_spoken_task_and_one_from_tasks_get_the_priorities_question() -> None:
    w = with_tasks(task(NOTARY), open_tasks=(TaskItem("tk-1", BILLS),))
    first = w.start()
    question = priorities_question(first)
    listed(first.text, NOTARY, BILLS)
    assert CHOOSE_TIMED in first.text
    asked = w.pick(question.id, timed=(number_of(first.text, BILLS),))
    assert asked.question == Question("duration", question.id, None), asked
