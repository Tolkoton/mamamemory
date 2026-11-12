"""Розстановка однієї задачі в часі (S3, `planning.placement`). Чиста, лише стандартна бібліотека.

Названий час — рівно він у поясі `tz`, без перевірки зайнятості, у межах [`now`, `horizon_end`]; інакше —
найраніший вільний відрізок від `ceil_step(max(t0 or now, now + 1s))` до `horizon_end`.
Не робить: кількох задач, меж часу мами, пріоритетів (F2).
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
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
    day: date | None = None
    """Названий день без часу (F2): лише в цей день, у поясі календаря."""
    not_before_local: time | None = None
    """Правка «не раніше …» (voice-edits F2): у кожному дні не раніше цього місцевого часу."""


@dataclass(frozen=True)
class Placed:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Placement:
    placed: list[tuple[str, datetime, datetime]]
    unplaced: list[str]


@dataclass(frozen=True)
class Limits:
    """Межі часу мами (S2 F2): дні тижня (0 — понеділок) і місцеві години в поясі календаря."""

    days: frozenset[int]
    start_local: time
    end_local: time


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


def place_many(
    tasks: list[TaskSpec],
    busy: list[Interval],
    *,
    now: datetime,
    tz: ZoneInfo,
    step_min: int,
    horizon_end: datetime,
    t0: datetime | None,
    limits: Limits | None = None,
) -> Placement:
    """Кілька задач (F2): спершу названий час (як `place`, стає зайнятістю), далі решта по черзі."""
    taken = list(busy)
    found: dict[str, tuple[datetime, datetime]] = {}
    unplaced: list[str] = []
    named = [t for t in tasks if t.start_local is not None]
    for task in named + [t for t in tasks if t.start_local is None]:
        result: Placed | NotFit = NotFit("no window")
        for window_end, bound in _windows(
            task, now=now, tz=tz, horizon_end=horizon_end, t0=t0, limits=limits
        ):
            result = place(task, taken, now=now, tz=tz, step_min=step_min, horizon_end=window_end, t0=bound)
            if isinstance(result, Placed):
                break
        if isinstance(result, NotFit):
            unplaced.append(task.task_id)
            continue
        found[task.task_id] = (result.start, result.end)
        taken.append(Interval(result.start, result.end))
    placed = [(t.task_id, *found[t.task_id]) for t in tasks if t.task_id in found]
    return Placement(placed, [t.task_id for t in tasks if t.task_id in unplaced])


def _windows(
    task: TaskSpec,
    *,
    now: datetime,
    tz: ZoneInfo,
    horizon_end: datetime,
    t0: datetime | None,
    limits: Limits | None,
) -> list[tuple[datetime, datetime | None]]:
    """Вікна пошуку задачі (кінець, нижня межа) по черзі: названий час — горизонт; названий день — той
    місцевий день (у годинах меж, якщо є); вільна з межами — кожен день з `days` у годинах меж; «не раніше»
    піднімає початок кожного дня до свого часу."""
    free_all_week = task.day is None and limits is None and task.not_before_local is None
    if task.start_local is not None or free_all_week:
        return [(horizon_end, t0)]
    if task.day is not None:
        dates = [task.day]
    else:
        first = (t0 or now).astimezone(tz).date()
        last = horizon_end.astimezone(tz).date()
        dates = [first + timedelta(days=n) for n in range((last - first).days + 1)]
        dates = [d for d in dates if limits is None or d.weekday() in limits.days]
    windows: list[tuple[datetime, datetime | None]] = []
    for day in dates:
        opens = time(0) if limits is None else limits.start_local
        if task.not_before_local is not None:
            opens = max(opens, task.not_before_local)
        closes_next = limits is None
        start = datetime.combine(day, opens, tzinfo=tz).astimezone(UTC)
        if closes_next:
            end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC)
        else:
            assert limits is not None
            end = datetime.combine(day, limits.end_local, tzinfo=tz).astimezone(UTC)
        windows.append((min(horizon_end, end), max(t0 or now, start)))
    return windows
