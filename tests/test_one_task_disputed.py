"""Disputed contract tests of the slice one-task-to-calendar: each depends on a question to the contract.

Written by the slice tester from `.engine/slices/one-task-to-calendar.md`, without the code. This file is
not sealed until the slice planner answers the questions named on each test (Q1-Q5 of the hand-in).
"""

from datetime import UTC, datetime, timedelta

from mamamemory.planning.placement import Interval, Placed, TaskSpec
from tests.test_one_task_placement import NOW as PLACE_NOW
from tests.test_one_task_placement import free_task, named_task, run, utc
from tests.test_one_task_planning import NOW, instant, world

# ------------------------------------------------------------------ Q1: the form of `start_local`


def test_named_date_and_time_from_model_is_shown_exactly() -> None:
    """Q1: the model gives `start_local` as ISO 8601 local date and time, `2026-11-12T10:00:00`."""
    w = world(duration_min=30, start_local="2026-11-12T10:00:00")
    reply = w.start("у четвер о десятій на пів години подзвонити нотаріусу")
    assert reply.plan is not None
    # Thursday 12 November 2026, 10:00 Berlin (CET) = 09:00 UTC.
    assert instant(reply.plan.start) == datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
    assert instant(reply.plan.end) == datetime(2026, 11, 12, 9, 30, tzinfo=UTC)
    assert w.calendar.insert_calls == []


def test_date_without_time_is_treated_as_no_time_named() -> None:
    """Q1: a date alone comes as `2026-11-12`; it is placed in free time from now, not on that day."""
    w = world(duration_min=30, start_local="2026-11-12")
    reply = w.start("у четвер на пів години подзвонити нотаріусу")
    assert reply.plan is not None
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)


def test_named_time_already_past_shows_no_plan_and_writes_nothing() -> None:
    """Q1: as above; 08:00 today in Berlin is before now (10:07 Berlin)."""
    w = world(duration_min=30, start_local="2026-11-09T08:00:00")
    reply = w.start("сьогодні о восьмій подзвонити нотаріусу")
    assert reply.plan is None
    assert w.calendar.insert_calls == []
    far = world(duration_min=30, start_local="2026-11-20T10:00:00")
    assert far.start("двадцятого о десятій подзвонити нотаріусу").plan is None
    assert far.calendar.insert_calls == []
    assert NOW < datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


# ------------------------------------------------------------------ Q2: are free starts on the step grid


def test_free_start_after_busy_end_off_step_rounds_up_to_step() -> None:
    """Q2: every free start is on the 15-minute grid, not only the lower bound."""
    busy = [Interval(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 10, 50))]
    assert run(free_task(30), busy) == Placed(utc(2026, 11, 9, 11, 0), utc(2026, 11, 9, 11, 30))


# ------------------------------------------------------------------ Q3: named time exactly at now


def test_named_time_equal_to_now_is_placed() -> None:
    """Q3: the closed interval [now, horizon_end] admits a named start equal to `now`."""
    now = utc(2026, 11, 9, 9, 0)  # 10:00 Berlin
    result = run(named_task(datetime(2026, 11, 9, 10, 0)), [], now=now)
    assert result == Placed(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 9, 30))


# ------------------------------------------------------------------ Q4: a free slot ending at the horizon


def test_free_slot_may_end_exactly_at_horizon_end() -> None:
    """Q4: "закінчується до `horizon_end`" admits an end equal to `horizon_end`."""
    horizon = PLACE_NOW + timedelta(days=7) + timedelta(minutes=8)  # 16 November 09:15 UTC, on the step
    assert horizon == utc(2026, 11, 16, 9, 15)
    busy = [Interval(PLACE_NOW - timedelta(hours=1), utc(2026, 11, 16, 8, 45))]
    assert run(free_task(30), busy, horizon_end=horizon) == Placed(utc(2026, 11, 16, 8, 45), horizon)


# ------------------------------------------------------------------ Q5: duration across the clock change


def test_duration_across_clock_change_is_real_minutes() -> None:
    """Q5: the end is start + duration in elapsed time, not on the wall clock."""
    task = TaskSpec(
        task_id="t1", title="подзвонити нотаріусу", duration_min=60, start_local=datetime(2026, 10, 25, 2, 30)
    )
    result = run(task, [], now=utc(2026, 10, 24, 12, 0))
    # 02:30 fold=0 is 00:30 UTC; sixty minutes later is 01:30 UTC (02:30 CET on the wall).
    assert result == Placed(utc(2026, 10, 25, 0, 30), utc(2026, 10, 25, 1, 30))
