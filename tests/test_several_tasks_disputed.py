"""Disputed contract tests of the slice several-tasks: each depends on a question to the contract.

Written by the slice tester from `.engine/slices/several-tasks.md`, without the code. This file is not sealed
until the slice planner answers the questions named on each test (Q1-Q4 of the hand-in).
"""

from datetime import UTC, date, datetime

from mamamemory import planning
from mamamemory.planning.placement import Interval
from tests.several_tasks_world import MEDICINE, NOTARY, SEEDS, ask_named, items, several, task
from tests.test_one_task_planning import NOW, instant
from tests.test_several_tasks_placement import many, placed, spec, utc

# ------------------------------------------------------------------ Q1: which text the duration question has


def test_duration_question_text_counts_timed_tasks_still_without_duration() -> None:
    """Q1: «коли така задача в чернетці одна» counts the tasks with `needs_time` and no `duration_min`
    at the moment of the question; tasks without time and tasks with a duration do not count.

    Superseded by stuck-question: «Текст питання тривалості завжди називає задачу: «Скільки часу займе
    «<назва>»?» — і для однієї задачі». Each duration question, the last one included, names its task."""
    # Two such tasks: the first is asked by name; once it is answered one is left, also asked by name.
    w = several(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    first = w.start()
    assert first.text == ask_named(NOTARY)
    assert first.question is not None
    second = w.answer(first.question.id, "пів години")
    assert second.text == ask_named(MEDICINE)
    # One such task beside an untimed task: asked by name.
    w = several(task(NOTARY, duration_min=None), task(SEEDS, needs_time=False, duration_min=None))
    assert w.start().text == ask_named(NOTARY)
    # One such task beside a timed task with its duration: asked by name.
    w = several(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=60))
    assert w.start().text == ask_named(NOTARY)


# ------------------------------------------------------------------ Q2: "лише в цей день" and the day's end


def test_named_day_task_must_end_within_that_day() -> None:
    """Q2: a task on a named day starts and ends inside that day (in `tz`); one that would run past
    midnight does not fit."""
    # Wednesday 11 November (Berlin) is busy 00:00-23:30 Berlin = Tue 23:00 - Wed 22:30 UTC.
    busy_wed = [Interval(utc(2026, 11, 10, 23, 0), utc(2026, 11, 11, 22, 30))]
    result = many([spec("t1", 60, day=date(2026, 11, 11))], busy_wed)
    assert result.placed == []
    assert result.unplaced == ["t1"]
    # 30 minutes still fit, ending at midnight Berlin.
    result = many([spec("t1", 30, day=date(2026, 11, 11))], busy_wed)
    assert placed(result) == {"t1": (utc(2026, 11, 11, 22, 30), utc(2026, 11, 11, 23, 0))}


# ------------------------------------------------------------------ Q3: a named time outside [now, horizon]


def test_named_time_outside_now_and_horizon_is_unplaced_and_others_are_placed() -> None:
    """Q3: in `place_many`, a named time `place` S3 refuses (`NotFit`) goes to `unplaced`; it is not an
    error, and the other tasks are placed."""
    past = spec("t1", 30, start_local=datetime(2026, 11, 9, 8, 0))  # 08:00 Berlin, now is 10:07
    beyond = spec("t2", 30, start_local=datetime(2026, 11, 20, 10, 0))  # past the 7-day horizon
    result = many([past, beyond, spec("t3", 30)])
    assert placed(result) == {"t3": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45))}
    assert sorted(result.unplaced) == ["t1", "t2"]


# ------------------------------------------------------------------ Q4: the S3 document with one `task`


def test_s3_draft_with_one_task_field_is_read_as_a_list_of_one() -> None:
    """Q4: an S3 draft is `{plan_id, state: "asking_duration",
    task: {task_id, title, start_local, duration_min}}` (the S3 `TaskDraft` with its id);
    answering its duration shows a plan of that one task."""
    w = several()
    w.store.set(
        w.session.account_id,
        planning.DRAFT_PATH,
        {
            "plan_id": "legacy-plan",
            "state": "asking_duration",
            "task": {"task_id": "t1", "title": NOTARY, "start_local": None, "duration_min": None},
        },
    )
    w.ai.durations = [30]
    reply = w.answer("legacy-plan", "пів години", now=NOW)
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    shown_items = items(reply)
    assert NOTARY in shown_items, f"the S3 task is not in the plan: {reply.plan!r}"
    start, end = shown_items[NOTARY]
    assert (instant(start), instant(end)) == (
        datetime(2026, 11, 9, 9, 15, tzinfo=UTC),
        datetime(2026, 11, 9, 9, 45, tzinfo=UTC),
    )
