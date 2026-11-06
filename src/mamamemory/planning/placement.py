"""Розстановка однієї задачі в часі (S3, `planning.placement`). Чиста, лише стандартна бібліотека.

Названий час — рівно він у поясі `tz`, без перевірки зайнятості, у межах [`now`, `horizon_end`]; інакше —
найраніший вільний відрізок від `ceil_step(max(t0 or now, now + 1s))` до `horizon_end`.
Не робить: кількох задач, меж часу мами, пріоритетів (F2).
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    duration_min: int
    start_local: datetime | None = None
    """Названий мамою час (наївний, у поясі календаря) або None."""


@dataclass(frozen=True)
class Placed:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class NotFit:
    reason: str


def place(
    task: TaskSpec,
    busy: list[Interval],
    *,
    now: datetime,
    tz: ZoneInfo,
    step_min: int,
    horizon_end: datetime,
    t0: datetime | None,
) -> Placed | NotFit:
    """Flow: названий час → рівно він; інакше — найраніший вільний відрізок на сітці кроку."""
    duration = timedelta(minutes=task.duration_min)
    if task.start_local is not None:
        return _named(task.start_local, duration, tz=tz, now=now, horizon_end=horizon_end)
    bound = _ceil_step(max(t0 or now, now + timedelta(seconds=1)), step_min)
    return _earliest_free(
        bound, duration, sorted(busy, key=lambda b: (b.start, b.end)), step_min, horizon_end
    )


def _named(
    start_local: datetime, duration: timedelta, *, tz: ZoneInfo, now: datetime, horizon_end: datetime
) -> Placed | NotFit:
    start = start_local.replace(tzinfo=tz, fold=0).astimezone(UTC)
    if not now <= start <= horizon_end:
        return NotFit("named time outside [now, horizon_end]")
    return Placed(start, start + duration)


def _earliest_free(
    start: datetime, duration: timedelta, busy: list[Interval], step_min: int, horizon_end: datetime
) -> Placed | NotFit:
    while start + duration <= horizon_end:
        clash = [b.end for b in busy if start < b.end and b.start < start + duration]
        if not clash:
            return Placed(start, start + duration)
        start = _ceil_step(max(clash), step_min)
    return NotFit("no free slot before horizon_end")


def _ceil_step(moment: datetime, step_min: int) -> datetime:
    step_s = step_min * 60
    return datetime.fromtimestamp(math.ceil(moment.timestamp() / step_s) * step_s, UTC)
