"""Contract tests of `planning.placement.place` (slice one-task-to-calendar): Seam 1, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/one-task-to-calendar.md`,
without the code.
Every expected moment is written by hand, in UTC.
"""

import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from mamamemory.planning.placement import Interval, NotFit, Placed, TaskSpec, place

BERLIN = ZoneInfo("Europe/Berlin")
STEP = 15
# Monday 9 November 2026, 10:07 in Berlin (CET, UTC+1).
NOW = datetime(2026, 11, 9, 9, 7, 0, tzinfo=UTC)
HORIZON = NOW + timedelta(days=7)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def free_task(duration_min: int = 30, task_id: str = "t1") -> TaskSpec:
    return TaskSpec(task_id=task_id, title="подзвонити нотаріусу", duration_min=duration_min)


def named_task(start_local: datetime, duration_min: int = 30) -> TaskSpec:
    return TaskSpec(
        task_id="t1", title="подзвонити нотаріусу", duration_min=duration_min, start_local=start_local
    )


def run(
    task: TaskSpec,
    busy: list[Interval],
    *,
    now: datetime = NOW,
    horizon_end: datetime | None = None,
    t0: datetime | None = None,
    tz: ZoneInfo = BERLIN,
) -> Placed | NotFit:
    return place(
        task, busy, now=now, tz=tz, step_min=STEP, horizon_end=horizon_end or now + timedelta(days=7), t0=t0
    )


# ------------------------------------------------------------------ free placement


def test_free_task_takes_earliest_free_slot_long_enough() -> None:
    busy = [
        Interval(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 10, 45)),
        Interval(utc(2026, 11, 9, 11, 0), utc(2026, 11, 9, 11, 45)),
    ]
    # 10:45-11:00 is too short for 30 minutes; the next free start is 11:45.
    assert run(free_task(30), busy) == Placed(utc(2026, 11, 9, 11, 45), utc(2026, 11, 9, 12, 15))


def test_free_task_starts_on_step_after_max_of_t0_and_now_plus_second() -> None:
    # now exactly on a step: now + 1 s rounds up to the next step.
    on_step = utc(2026, 11, 9, 9, 15)
    assert run(free_task(30), [], now=on_step) == Placed(utc(2026, 11, 9, 9, 30), utc(2026, 11, 9, 10, 0))
    # t0 later than now: from ceil_step(t0).
    assert run(free_task(30), [], t0=utc(2026, 11, 9, 13, 5)) == Placed(
        utc(2026, 11, 9, 13, 15), utc(2026, 11, 9, 13, 45)
    )
    # t0 earlier than now: from ceil_step(now + 1 s).
    assert run(free_task(30), [], t0=utc(2026, 11, 9, 8, 0)) == Placed(
        utc(2026, 11, 9, 9, 15), utc(2026, 11, 9, 9, 45)
    )


def test_free_task_not_fit_when_no_slot_before_horizon() -> None:
    busy = [Interval(NOW - timedelta(hours=1), HORIZON - timedelta(minutes=10))]
    assert isinstance(run(free_task(30), busy, horizon_end=HORIZON), NotFit)


# ------------------------------------------------------------------ named time


def test_named_time_is_exactly_it_without_busy_check() -> None:
    # Thursday 12 November 2026, 10:00 in Berlin (CET) = 09:00 UTC; a busy event over it is ignored.
    busy = [Interval(utc(2026, 11, 12, 8, 0), utc(2026, 11, 12, 11, 0))]
    result = run(named_task(datetime(2026, 11, 12, 10, 0)), busy)
    assert result == Placed(utc(2026, 11, 12, 9, 0), utc(2026, 11, 12, 9, 30))


def test_named_time_in_zone_across_summer_winter_switch() -> None:
    # 29 March 2026: 02:30 does not exist in Berlin; fold=0 -> the offset before the switch (+01:00).
    r = run(named_task(datetime(2026, 3, 29, 2, 30)), [], now=utc(2026, 3, 28, 12, 0))
    assert isinstance(r, Placed) and r.start == utc(2026, 3, 29, 1, 30)
    # 25 October 2026: 02:30 happens twice; fold=0 -> the first one (+02:00).
    r = run(named_task(datetime(2026, 10, 25, 2, 30)), [], now=utc(2026, 10, 24, 12, 0))
    assert isinstance(r, Placed) and r.start == utc(2026, 10, 25, 0, 30)
    # 10:00 after the spring switch, asked the day before (still CET): CEST +02:00 -> 08:00 UTC.
    r = run(named_task(datetime(2026, 3, 29, 10, 0)), [], now=utc(2026, 3, 28, 12, 0))
    assert isinstance(r, Placed) and r.start == utc(2026, 3, 29, 8, 0)
    # 10:00 after the autumn switch, asked the day before (still CEST): CET +01:00 -> 09:00 UTC.
    r = run(named_task(datetime(2026, 10, 25, 10, 0)), [], now=utc(2026, 10, 24, 12, 0))
    assert isinstance(r, Placed) and r.start == utc(2026, 10, 25, 9, 0)


def test_named_time_outside_now_and_horizon_is_not_fit() -> None:
    # Already past: Monday 9 November 08:00 Berlin, now is 10:07 Berlin.
    assert isinstance(run(named_task(datetime(2026, 11, 9, 8, 0)), []), NotFit)
    # Further than the horizon: 20 November.
    assert isinstance(run(named_task(datetime(2026, 11, 20, 10, 0)), [], horizon_end=HORIZON), NotFit)


# ------------------------------------------------------------------ invariants


def test_I1_same_inputs_give_same_placement() -> None:
    busy = [
        Interval(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 10, 0)),
        Interval(utc(2026, 11, 9, 9, 30), utc(2026, 11, 9, 10, 45)),  # overlaps the first
        Interval(utc(2026, 11, 9, 11, 30), utc(2026, 11, 9, 12, 0)),
        Interval(utc(2026, 11, 9, 12, 0), utc(2026, 11, 9, 12, 45)),  # touches the third
        Interval(utc(2026, 11, 9, 11, 0), utc(2026, 11, 9, 11, 15)),
    ]
    cases: list[tuple[TaskSpec, list[Interval], datetime | None]] = [
        (free_task(30), busy, None),
        (free_task(45), busy, utc(2026, 11, 9, 11, 5)),
        (free_task(5), [], None),
        (named_task(datetime(2026, 11, 10, 7, 45)), busy, None),
        (free_task(60 * 24 * 8), busy, None),  # never fits: NotFit both times
    ]
    shuffler = random.Random(7)
    for task, intervals, t0 in cases:
        first = run(task, list(intervals), t0=t0)
        assert run(task, list(intervals), t0=t0) == first
        assert run(task, list(reversed(intervals)), t0=t0) == first
        mixed = list(intervals)
        shuffler.shuffle(mixed)
        assert run(task, mixed, t0=t0) == first
    # Hand-checked anchor: the gaps 10:45-11:00 and 11:15-11:30 are 15 minutes; free from 12:45.
    assert run(free_task(30), busy) == Placed(utc(2026, 11, 9, 12, 45), utc(2026, 11, 9, 13, 15))


def overlaps(a: Placed, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def test_I2_free_placement_never_overlaps_busy_never_before_bound_never_past_horizon() -> None:
    cases: list[tuple[str, TaskSpec, list[Interval], datetime, datetime | None, datetime, datetime]] = [
        # name, task, busy, now, t0, horizon_end, lower bound written by hand
        (
            "overlapping and touching busy",
            free_task(30),
            [
                Interval(utc(2026, 11, 9, 9, 0), utc(2026, 11, 9, 9, 40)),
                Interval(utc(2026, 11, 9, 9, 40), utc(2026, 11, 9, 10, 5)),
                Interval(utc(2026, 11, 9, 9, 50), utc(2026, 11, 9, 10, 20)),
                Interval(utc(2026, 11, 9, 10, 40), utc(2026, 11, 9, 11, 0)),
            ],
            NOW,
            None,
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "busy that only covers the start of the first slot",
            free_task(30),
            [Interval(utc(2026, 11, 9, 9, 40), utc(2026, 11, 9, 9, 50))],
            NOW,
            None,
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "busy inside the candidate slot, not at its start",
            free_task(60),
            [Interval(utc(2026, 11, 9, 9, 50), utc(2026, 11, 9, 9, 55))],
            NOW,
            None,
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "now exactly on a step",
            free_task(15),
            [],
            utc(2026, 11, 9, 9, 15),
            None,
            utc(2026, 11, 16, 9, 15),
            utc(2026, 11, 9, 9, 30),
        ),
        (
            "t0 later than now",
            free_task(30),
            [Interval(utc(2026, 11, 9, 14, 0), utc(2026, 11, 9, 15, 0))],
            NOW,
            utc(2026, 11, 9, 13, 50),
            HORIZON,
            utc(2026, 11, 9, 14, 0),
        ),
        (
            "t0 earlier than now",
            free_task(30),
            [],
            NOW,
            utc(2026, 11, 8, 9, 0),
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "busy that started before now and runs on",
            free_task(30),
            [Interval(utc(2026, 11, 9, 6, 0), utc(2026, 11, 9, 13, 10))],
            NOW,
            None,
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "the only gap is near the horizon",
            free_task(30),
            [
                Interval(utc(2026, 11, 9, 8, 0), utc(2026, 11, 16, 7, 0)),
                Interval(utc(2026, 11, 16, 8, 0), utc(2026, 11, 20, 0, 0)),
            ],
            NOW,
            None,
            HORIZON,
            utc(2026, 11, 9, 9, 15),
        ),
        (
            "over the spring switch, at night",
            free_task(60),
            [Interval(utc(2026, 3, 28, 22, 0), utc(2026, 3, 29, 0, 50))],
            utc(2026, 3, 28, 21, 58),
            None,
            utc(2026, 4, 4, 21, 58),
            utc(2026, 3, 28, 22, 0),
        ),
    ]
    for name, task, busy, now, t0, horizon_end, bound in cases:
        result = run(task, busy, now=now, t0=t0, horizon_end=horizon_end)
        assert isinstance(result, Placed), f"{name}: a free slot exists, got {result!r}"
        assert result.start >= bound, f"{name}: starts before {bound}"
        assert result.end <= horizon_end, f"{name}: runs past the horizon"
        for b in busy:
            assert not overlaps(result, b), f"{name}: overlaps busy {b}"
    # A gap shorter than the task is not used: NotFit rather than an overlap.
    short_gap = [
        Interval(utc(2026, 11, 9, 8, 0), utc(2026, 11, 9, 12, 0)),
        Interval(utc(2026, 11, 9, 12, 20), HORIZON + timedelta(days=1)),
    ]
    assert isinstance(run(free_task(30), short_gap, horizon_end=HORIZON), NotFit)
