"""Contract tests of `place_many(..., limits)` (slice time-limits): Seam 1 and I1.

Written by the slice tester from the sealed contract `.engine/slices/time-limits.md`, without the code.
Every expected moment is written by hand, in UTC. Berlin is CEST (UTC+2) until Sunday 25 October 2026,
03:00, and CET (UTC+1) after it.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mamamemory.planning.placement import Interval, Limits, Placement, TaskSpec, place_many
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.test_one_task_planning import instant
from tests.time_limits_world import WEEKDAYS, limited, limits_question, parsed

BERLIN = ZoneInfo("Europe/Berlin")
STEP = 15
WORKDAYS = Limits(days=frozenset(WEEKDAYS), start_local=time(9, 0), end_local=time(18, 0))
"""Weekdays 09:00–18:00 local."""


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def spec(
    task_id: str, duration_min: int = 30, *, start_local: datetime | None = None, day: date | None = None
) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        title=f"задача {task_id}",
        duration_min=duration_min,
        start_local=start_local,
        day=day,
    )


def many(
    tasks: list[TaskSpec], *, now: datetime, limits: Limits = WORKDAYS, busy: list[Interval] | None = None
) -> Placement:
    return place_many(
        tasks,
        busy or [],
        now=now,
        tz=BERLIN,
        step_min=STEP,
        horizon_end=now + timedelta(days=7),
        t0=None,
        limits=limits,
    )


def placed(result: Placement) -> dict[str, tuple[datetime, datetime]]:
    found = {task_id: (start, end) for task_id, start, end in result.placed}
    assert len(found) == len(result.placed), f"a task placed twice: {result.placed!r}"
    return found


def within(result: Placement, limits: Limits) -> None:
    """Every placed task: its local day in `days`, start ≥ `start_local`, end ≤ `end_local` of that day."""
    for task_id, start, end in result.placed:
        local_start = start.astimezone(BERLIN)
        assert local_start.weekday() in limits.days, (task_id, local_start)
        assert local_start.time() >= limits.start_local, (task_id, local_start)
        day_end = datetime.combine(local_start.date(), limits.end_local, tzinfo=BERLIN)
        assert end <= day_end, (task_id, end.astimezone(BERLIN), day_end)


# ------------------------------------------------------------------ Seam 1


def test_seam1_free_task_whose_end_leaves_the_limits_goes_to_next_weekday_morning() -> None:
    # Monday 9 November, 17:40 Berlin (16:40Z): the first step 17:45 would end at 18:15, past 18:00.
    result = many([spec("t1", 30)], now=utc(2026, 11, 9, 16, 40))
    # Tuesday 10 November 09:00 Berlin (CET) = 08:00Z.
    assert placed(result) == {"t1": (utc(2026, 11, 10, 8, 0), utc(2026, 11, 10, 8, 30))}
    assert result.unplaced == []


def test_seam1_saturday_and_sunday_are_skipped() -> None:
    # Friday 13 November, 17:40 Berlin (16:40Z): the next weekday morning is Monday 16 November.
    result = many([spec("t1", 30)], now=utc(2026, 11, 13, 16, 40))
    assert placed(result) == {"t1": (utc(2026, 11, 16, 8, 0), utc(2026, 11, 16, 8, 30))}


def test_seam1_clock_change_first_weekday_after_is_monday_0900_cet() -> None:
    # Friday 23 October 2026, 18:30 Berlin (CEST) = 16:30Z; the clock goes back on Sunday 25 October.
    result = many([spec("t1", 30)], now=utc(2026, 10, 23, 16, 30))
    # Monday 26 October 09:00 CET = 08:00Z (not 09:00Z, not 07:00Z).
    assert placed(result) == {"t1": (utc(2026, 10, 26, 8, 0), utc(2026, 10, 26, 8, 30))}


def test_seam1_named_day_outside_days_is_placed_that_day_in_the_hours() -> None:
    # Monday 9 November 10:07 Berlin; the task names Sunday 15 November (not in `days`).
    result = many([spec("t1", 30, day=date(2026, 11, 15))], now=utc(2026, 11, 9, 9, 7))
    # Sunday 15 November 09:00 Berlin (CET) = 08:00Z.
    assert placed(result) == {"t1": (utc(2026, 11, 15, 8, 0), utc(2026, 11, 15, 8, 30))}
    assert result.unplaced == []


def test_named_time_outside_the_limits_is_placed_as_named() -> None:
    # Tuesday 10 November 20:00 Berlin (after 18:00) = 19:00Z.
    result = many([spec("t1", 30, start_local=datetime(2026, 11, 10, 20, 0))], now=utc(2026, 11, 9, 9, 7))
    assert placed(result) == {"t1": (utc(2026, 11, 10, 19, 0), utc(2026, 11, 10, 19, 30))}


def test_named_day_whose_hours_are_busy_is_unplaced_even_if_the_evening_is_free() -> None:
    # Tuesday 10 November is busy 09:00–18:00 Berlin (08:00Z–17:00Z); free after 18:00, outside the hours.
    busy = [Interval(utc(2026, 11, 10, 8, 0), utc(2026, 11, 10, 17, 0))]
    result = many([spec("t1", 30, day=date(2026, 11, 10))], now=utc(2026, 11, 9, 9, 7), busy=busy)
    assert placed(result) == {}
    assert result.unplaced == ["t1"]


def test_free_task_that_fits_nowhere_in_the_limits_is_unplaced() -> None:
    # Only Mondays 09:00–09:30: a 60-minute task never fits.
    narrow = Limits(days=frozenset({0}), start_local=time(9, 0), end_local=time(9, 30))
    result = many([spec("t1", 60)], now=utc(2026, 11, 8, 20, 0), limits=narrow)
    assert placed(result) == {}
    assert result.unplaced == ["t1"]


# ------------------------------------------------------------------ I1


def test_I1_free_task_never_stands_outside_the_limits() -> None:
    # (a) Saturday 24 October 20:00 CEST (18:00Z), every day 09:00–18:00: Sunday 25 October is the day the
    # clock goes back — 09:00 CET = 08:00Z.
    every_day = Limits(days=frozenset(range(7)), start_local=time(9, 0), end_local=time(18, 0))
    a = many([spec("t1", 30)], now=utc(2026, 10, 24, 18, 0), limits=every_day)
    within(a, every_day)
    assert placed(a) == {"t1": (utc(2026, 10, 25, 8, 0), utc(2026, 10, 25, 8, 30))}

    # (b) Odd minutes 09:10–11:50 on weekdays (160 minutes a day), now before the start (Monday 06:00
    # Berlin); three 60-minute tasks cannot all stand on Monday.
    odd = Limits(days=frozenset(WEEKDAYS), start_local=time(9, 10), end_local=time(11, 50))
    b = many([spec("t1", 60), spec("t2", 60), spec("t3", 60)], now=utc(2026, 11, 9, 5, 0), limits=odd)
    within(b, odd)
    assert set(placed(b)) == {"t1", "t2", "t3"}
    mondays = [s for s, _ in placed(b).values() if s.astimezone(BERLIN).date() == date(2026, 11, 9)]
    assert len(mondays) == 2

    # (c) Monday busy 09:00–17:30 Berlin: a 60-minute task does not take 17:30–18:30 → Tuesday 09:00.
    busy = [Interval(utc(2026, 11, 9, 8, 0), utc(2026, 11, 9, 16, 30))]
    c = many([spec("t1", 60)], now=utc(2026, 11, 9, 5, 0), busy=busy)
    within(c, WORKDAYS)
    assert placed(c) == {"t1": (utc(2026, 11, 10, 8, 0), utc(2026, 11, 10, 9, 0))}

    # (d) Weekends only, 10:00–12:00, from a Monday: Saturday 14 November 10:00 Berlin = 09:00Z.
    weekend = Limits(days=frozenset({5, 6}), start_local=time(10, 0), end_local=time(12, 0))
    d = many([spec("t1", 120), spec("t2", 30)], now=utc(2026, 11, 9, 9, 7), limits=weekend)
    within(d, weekend)
    assert placed(d)["t1"] == (utc(2026, 11, 14, 9, 0), utc(2026, 11, 14, 11, 0))
    assert placed(d)["t2"] == (utc(2026, 11, 15, 9, 0), utc(2026, 11, 15, 9, 30))

    # (e) A task longer than a day's limits is never placed; the free task beside it still is.
    e = many([spec("t1", 600), spec("t2", 30)], now=utc(2026, 11, 9, 9, 7))
    within(e, WORKDAYS)
    assert e.unplaced == ["t1"]
    assert placed(e) == {"t2": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45))}

    # (f) Limits from the previous planning, answered «так»: the plan keeps them (Tuesdays 14:00–15:00).
    w = limited(task(NOTARY), task(MEDICINE))
    w.seed_limits([1], "14:00", "15:00")
    question = limits_question(w.start())
    w.ai.limits = parsed(same_as_last=True)
    reply = w.answer_limits(question.id, "так")
    assert reply.plan is not None, f"expected the plan, got {reply!r}"
    starts = sorted(instant(i["start"]) for i in reply.plan.items)
    ends = sorted(instant(i["end"]) for i in reply.plan.items)
    # Tuesday 10 November 14:00–15:00 Berlin = 13:00Z–14:00Z.
    assert starts == [utc(2026, 11, 10, 13, 0), utc(2026, 11, 10, 13, 30)]
    assert ends == [utc(2026, 11, 10, 13, 30), utc(2026, 11, 10, 14, 0)]
