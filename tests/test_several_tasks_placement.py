"""Contract tests of `planning.placement.place_many` (slice several-tasks): Seam 1.

Written by the slice tester from the sealed contract `.engine/slices/several-tasks.md`, without the code.
Every expected moment is written by hand, in UTC. The order of `Placement.placed` is not part of the
contract: results are compared as a mapping task_id -> (start, end).
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mamamemory.planning.placement import Interval, Placement, TaskSpec, place_many

BERLIN = ZoneInfo("Europe/Berlin")
STEP = 15
# Monday 9 November 2026, 10:07 in Berlin (CET, UTC+1).
NOW = datetime(2026, 11, 9, 9, 7, 0, tzinfo=UTC)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def spec(
    task_id: str,
    duration_min: int = 30,
    *,
    start_local: datetime | None = None,
    day: date | None = None,
    title: str | None = None,
) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        title=title or f"задача {task_id}",
        duration_min=duration_min,
        start_local=start_local,
        day=day,
    )


def many(
    tasks: list[TaskSpec],
    busy: list[Interval] | None = None,
    *,
    now: datetime = NOW,
    t0: datetime | None = None,
    horizon_end: datetime | None = None,
) -> Placement:
    return place_many(
        tasks,
        busy or [],
        now=now,
        tz=BERLIN,
        step_min=STEP,
        horizon_end=horizon_end or now + timedelta(days=7),
        t0=t0,
    )


def placed(result: Placement) -> dict[str, tuple[datetime, datetime]]:
    found = {task_id: (start, end) for task_id, start, end in result.placed}
    assert len(found) == len(result.placed), f"a task placed twice: {result.placed!r}"
    return found


# ------------------------------------------------------------------ Seam 1


def test_seam1_each_placed_task_becomes_busy_for_the_next() -> None:
    result = many([spec("t1", 30), spec("t2", 60), spec("t3", 30)])
    # Empty calendar; the first step after 10:07 Berlin is 10:15 Berlin = 09:15 UTC.
    assert placed(result) == {
        "t1": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45)),
        "t2": (utc(2026, 11, 9, 9, 45), utc(2026, 11, 9, 10, 45)),
        "t3": (utc(2026, 11, 9, 10, 45), utc(2026, 11, 9, 11, 15)),
    }
    assert result.unplaced == []


def test_seam1_named_time_is_placed_first_and_free_task_goes_elsewhere() -> None:
    # t1 (free, first in order) would take 09:15 UTC; t2 names 10:15 Berlin = 09:15 UTC.
    result = many([spec("t1", 30), spec("t2", 30, start_local=datetime(2026, 11, 9, 10, 15))])
    assert placed(result) == {
        "t1": (utc(2026, 11, 9, 9, 45), utc(2026, 11, 9, 10, 15)),
        "t2": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45)),
    }
    assert result.unplaced == []


def test_seam1_named_time_is_exactly_it_without_busy_check() -> None:
    # Wednesday 11 November 10:00 Berlin = 09:00 UTC; a busy event lies over it.
    busy = [Interval(utc(2026, 11, 11, 8, 0), utc(2026, 11, 11, 11, 0))]
    result = many([spec("t1", 60, start_local=datetime(2026, 11, 11, 10, 0))], busy)
    assert placed(result) == {"t1": (utc(2026, 11, 11, 9, 0), utc(2026, 11, 11, 10, 0))}
    assert result.unplaced == []


def test_seam1_named_day_only_that_day_even_when_earlier_day_is_free() -> None:
    # Monday and Tuesday are free; t1 names Wednesday 11 November: its first free moment is
    # 00:00 Berlin (CET) = Tuesday 10 November 23:00 UTC. t2 has no day: today, 09:15 UTC.
    result = many([spec("t1", 30, day=date(2026, 11, 11)), spec("t2", 30)])
    assert placed(result) == {
        "t1": (utc(2026, 11, 10, 23, 0), utc(2026, 11, 10, 23, 30)),
        "t2": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45)),
    }
    # Wednesday busy until 08:00 Berlin (07:00 UTC): the day task takes the earliest free moment that day.
    busy = [Interval(utc(2026, 11, 10, 23, 0), utc(2026, 11, 11, 7, 0))]
    result = many([spec("t1", 30, day=date(2026, 11, 11))], busy)
    assert placed(result) == {"t1": (utc(2026, 11, 11, 7, 0), utc(2026, 11, 11, 7, 30))}


def test_seam1_task_that_does_not_fit_is_unplaced_and_the_others_are_placed() -> None:
    # Wednesday (Berlin) is busy except 10:00-12:00 Berlin (09:00-11:00 UTC): a 3-hour task named on
    # Wednesday does not fit there; the free tasks are placed as usual.
    busy = [
        Interval(utc(2026, 11, 10, 23, 0), utc(2026, 11, 11, 9, 0)),
        Interval(utc(2026, 11, 11, 11, 0), utc(2026, 11, 11, 23, 0)),
    ]
    result = many([spec("t1", 30), spec("t2", 180, day=date(2026, 11, 11)), spec("t3", 30)], busy)
    assert placed(result) == {
        "t1": (utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45)),
        "t3": (utc(2026, 11, 9, 9, 45), utc(2026, 11, 9, 10, 15)),
    }
    assert result.unplaced == ["t2"]
    # A free task with no free slot before the horizon is unplaced too.
    horizon = NOW + timedelta(days=7)
    result = many([spec("t1", 30)], [Interval(NOW - timedelta(hours=1), horizon)], horizon_end=horizon)
    assert result.placed == []
    assert result.unplaced == ["t1"]


def test_seam1_one_task_gives_the_same_result_as_place() -> None:
    # The values below are those of the sealed S3 tests of `place` (test_one_task_placement.py).
    busy = [
        Interval(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 10, 45)),
        Interval(utc(2026, 11, 9, 11, 0), utc(2026, 11, 9, 11, 45)),
    ]
    assert placed(many([spec("t1", 30)], busy)) == {
        "t1": (utc(2026, 11, 9, 11, 45), utc(2026, 11, 9, 12, 15))
    }
    # now exactly on a step: from the next step.
    on_step = utc(2026, 11, 9, 9, 15)
    assert placed(many([spec("t1", 30)], now=on_step)) == {
        "t1": (utc(2026, 11, 9, 9, 30), utc(2026, 11, 9, 10, 0))
    }
    # t0 later than now: from ceil_step(t0).
    assert placed(many([spec("t1", 30)], t0=utc(2026, 11, 9, 13, 5))) == {
        "t1": (utc(2026, 11, 9, 13, 15), utc(2026, 11, 9, 13, 45))
    }
    # A named time in Berlin across the spring switch (CEST, +02:00).
    result = many([spec("t1", 30, start_local=datetime(2026, 3, 29, 10, 0))], now=utc(2026, 3, 28, 12, 0))
    assert placed(result) == {"t1": (utc(2026, 3, 29, 8, 0), utc(2026, 3, 29, 8, 30))}
