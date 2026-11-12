"""Contract tests of the slice several-tasks: `planning` with several tasks on the S3 Calendar fake.

Seam 2 (writing several), Seam 3 (adding to a draft), I1, I2, I3, and the shown plan of three groups.
Written by the slice tester from the sealed contract `.engine/slices/several-tasks.md`, without the code.
Times are written by hand in UTC; `NOW` is Monday 9 November 2026, 10:07 in Berlin (CET, UTC+1), so the
first free step is 10:15 Berlin = 09:15 UTC.
"""

import contextlib
import copy
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mamamemory import planning
from mamamemory.planning.placement import Interval, Placement, TaskSpec, place_many
from mamamemory.replies import Question, Reply
from tests.several_tasks_world import (
    DOCTOR,
    GARDEN,
    MEDICINE,
    NOT_UNDERSTOOD,
    NOTARY,
    PARTLY_WRITTEN,
    SEEDS,
    SISTER,
    TASKS_LATER,
    WRITING_NOW,
    WRITTEN,
    Several,
    ask_named,
    items,
    several,
    task,
)
from tests.test_one_task_planning import NOW, instant, shown

BERLIN = ZoneInfo("Europe/Berlin")
LATER = NOW + timedelta(seconds=45)
"""Past REQUEST_TIMEOUT_S (30 s): a write left in «записується» is stale."""


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def at(reply: Reply, title: str) -> tuple[datetime, datetime]:
    shown_items = items(reply)
    assert title in shown_items, f"{title!r} is not among the plan's items: {shown_items!r}"
    start, end = shown_items[title]
    return instant(start), instant(end)


def three_timed() -> Several:
    """Three free 30-minute tasks: on an empty calendar 09:15, 09:45 and 10:15 UTC."""
    return several(task(NOTARY), task(MEDICINE), task(SISTER), honour_409=False)


def crash_on(w: Several, n: int) -> tuple[str, str]:
    """Show the plan, then "yes" whose n-th created event loses its answer."""
    plan_id, fingerprint = shown(w.start())
    w.calendar.crash_on = n
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    return plan_id, fingerprint


SLOTS = {
    NOTARY: (utc(9, 9, 15), utc(9, 9, 45)),
    MEDICINE: (utc(9, 9, 45), utc(9, 10, 15)),
    SISTER: (utc(9, 10, 15), utc(9, 10, 45)),
}
"""The shown slots of `three_timed()`; the contract does not fix the order in which they are written."""


def written_and_left(w: Several) -> tuple[set[str], str]:
    written = set(w.calendar.titles())
    left = set(SLOTS) - written
    assert len(written) == 2 and len(left) == 1, w.calendar.titles()
    return written, left.pop()


# ------------------------------------------------------------------ the shown plan


def test_several_tasks_in_one_message_become_one_plan_of_three_groups() -> None:
    w = several(
        task(NOTARY, day="2026-11-09"),
        task(SEEDS, needs_time=False, duration_min=None),
        task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60),
    )
    reply = w.start(
        "у понеділок подзвонити нотаріусу на пів години, купити насіння, а в середу о десятій до лікаря"
    )
    assert reply.plan is not None, f"expected one plan, got {reply!r}"
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, DOCTOR) == (utc(11, 9, 0), utc(11, 10, 0))
    assert reply.plan.untimed == [{"task_id": w.task_id(SEEDS), "title": SEEDS}]
    assert reply.plan.unplaced == []
    for item in reply.plan.items:
        assert item["task_id"] == w.task_id(item["title"])
    # title/start/end: the first placed task, as in S3.
    assert reply.plan.title == NOTARY
    assert (instant(reply.plan.start), instant(reply.plan.end)) == (utc(9, 9, 15), utc(9, 9, 45))
    assert reply.question == Question("plan", reply.plan.plan_id, reply.plan.fingerprint)
    text = reply.text
    assert "Пропоную:" in text
    assert "понеділок, 9 листопада, 10:15–10:45 — подзвонити нотаріусу" in text
    assert "середа, 11 листопада, 10:00–11:00 — до лікаря" in text
    assert SEEDS in text.split("Без часу:", 1)[1], "the untimed task is listed under «Без часу:»"
    assert text.rstrip().endswith("Записати?")
    assert w.calendar.insert_calls == []


def test_task_that_does_not_fit_is_shown_under_not_fitted() -> None:
    # Today (Monday, Berlin) is busy from 09:00 UTC to midnight Berlin (23:00 UTC).
    w = several(task(NOTARY, day="2026-11-09", duration_min=60), task(MEDICINE))
    w.calendar.busy(utc(9, 9, 0), utc(9, 23, 0))
    reply = w.start()
    assert reply.plan is not None
    assert reply.plan.unplaced == [{"task_id": w.task_id(NOTARY), "title": NOTARY}]
    assert at(reply, MEDICINE) == (utc(9, 23, 0), utc(9, 23, 30))
    assert reply.plan.title == MEDICINE
    assert NOTARY in reply.text.split("Не вмістилось:", 1)[1]
    assert w.calendar.insert_calls == []


def test_draft_keeps_every_task_in_the_task_format() -> None:
    w = several(
        task(NOTARY, day="2026-11-09"),
        task(SEEDS, needs_time=False, duration_min=None),
        task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=None),
    )
    w.start()
    tasks = {t["title"]: t for t in w.tasks()}
    assert {t["task_id"] for t in tasks.values()} == {"t1", "t2", "t3"}
    assert tasks[NOTARY]["needs_time"] is True
    assert tasks[NOTARY]["duration_min"] == 30
    assert tasks[NOTARY]["constraints"] == {"day": "2026-11-09"}
    assert tasks[SEEDS]["needs_time"] is False
    assert tasks[SEEDS]["constraints"] == {"day": None}
    assert tasks[DOCTOR]["duration_min"] is None
    for t in tasks.values():
        assert t["source"] == "speech"
        assert t["written"] == {"event_id": None, "tasks_id": None, "closed": False}
    orders = [tasks[NOTARY]["order"], tasks[SEEDS]["order"], tasks[DOCTOR]["order"]]
    assert orders == sorted(orders) and len(set(orders)) == 3


def test_message_without_any_task_changes_nothing() -> None:
    w = several()
    reply = w.start("ну як там погода")
    assert reply.text == NOT_UNDERSTOOD
    assert reply.plan is None
    assert w.draft() is None
    # With a shown draft: the draft stays as it was.
    w = several(task(NOTARY))
    shown(w.start())
    before = copy.deepcopy(w.draft())
    w.ai.says()
    reply = w.start("ну як там погода")
    assert reply.text == NOT_UNDERSTOOD
    assert w.draft() == before


def test_open_question_shows_the_same_plan_of_several_tasks() -> None:
    w = several(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    opened = w.open(NOW + timedelta(minutes=1))
    assert opened is not None and opened.reply.plan is not None
    assert opened.reply.plan.plan_id == plan_id
    assert opened.reply.plan.fingerprint == fingerprint
    assert set(items(opened.reply)) == {NOTARY, MEDICINE}
    assert opened.reply.plan.untimed == [{"task_id": w.task_id(SEEDS), "title": SEEDS}]
    assert w.calendar.insert_calls == []


# ------------------------------------------------------------------ duration questions


def test_next_question_asks_duration_of_first_timed_task_without_it() -> None:
    def draft(*tasks: tuple[str, bool, int | None]) -> dict[str, object]:
        return {
            "plan_id": "p-1",
            "state": "asking_duration",
            "tasks": [
                {
                    "task_id": f"t{n}",
                    "title": title,
                    "needs_time": needs_time,
                    "duration_min": duration,
                    "start_local": None,
                    "constraints": {"day": None},
                    "order": n,
                    "source": "speech",
                    "written": {"event_id": None, "tasks_id": None, "closed": False},
                }
                for n, (title, needs_time, duration) in enumerate(tasks, start=1)
            ],
        }

    assert planning.next_question(draft((NOTARY, True, None), (MEDICINE, True, None))) == Question(
        "duration", "p-1", None
    )
    assert planning.next_question(draft((NOTARY, True, 30), (MEDICINE, True, None))) == Question(
        "duration", "p-1", None
    )
    assert planning.next_question(draft((NOTARY, True, 30), (MEDICINE, True, 60))) is None


def test_several_tasks_without_duration_ask_by_name_one_at_a_time() -> None:
    w = several(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    first = w.start()
    assert first.plan is None
    assert first.question is not None and first.question.kind == "duration"
    assert first.text == ask_named(NOTARY)
    plan_id = first.question.id
    w.ai.durations = [30, 60]
    second = w.answer(plan_id, "пів години")
    assert second.plan is None
    assert second.question == Question("duration", plan_id, None), "the next task without duration is asked"
    reply = w.answer(plan_id, "годину")
    assert reply.plan is not None
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, MEDICINE) == (utc(9, 9, 45), utc(9, 10, 45))
    assert w.calendar.insert_calls == []


# ------------------------------------------------------------------ Seam 3: adding to a draft


def test_seam3_second_message_while_asking_adds_task_and_asks_first_without_duration() -> None:
    w = several(task(NOTARY, duration_min=None))
    asked = w.start("подзвонити нотаріусу")
    assert asked.question is not None
    plan_id = asked.question.id
    w.ai.says(task(MEDICINE, duration_min=60))
    again = w.start("і купити ліки на годину")
    assert again.plan is None
    assert again.question == Question("duration", plan_id, None)
    assert {t["title"] for t in w.tasks()} == {NOTARY, MEDICINE}
    orders = {t["title"]: t["order"] for t in w.tasks()}
    assert orders[MEDICINE] > orders[NOTARY], "`order` goes on"
    reply = w.answer(plan_id, "пів години")
    assert reply.plan is not None
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, MEDICINE) == (utc(9, 9, 45), utc(9, 10, 45))


def test_seam3_task_added_to_shown_plan_is_shown_anew_with_same_horizon() -> None:
    w = several(task(NOTARY), honour_409=False)
    old_id, old_fp = shown(w.start())
    current = w.draft()
    assert current is not None
    horizon = current["horizon_end"]
    w.ai.says(task(MEDICINE, duration_min=60))
    reply = w.start("і ще купити ліки", now=NOW + timedelta(minutes=1))
    new_id, new_fp = shown(reply)
    assert new_fp != old_fp
    assert set(items(reply)) == {NOTARY, MEDICINE}
    updated = w.draft()
    assert updated is not None and updated["horizon_end"] == horizon
    # "yes" with the old fingerprint writes nothing; with the new one, both.
    with contextlib.suppress(Exception):
        w.confirm(old_id, old_fp, now=NOW + timedelta(minutes=2))
    assert w.calendar.insert_calls == []
    replied = w.confirm(new_id, new_fp, now=NOW + timedelta(minutes=2))
    assert replied.text == WRITTEN
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1}


def test_seam3_after_written_a_new_message_starts_a_new_draft() -> None:
    w = several(task(NOTARY))
    plan_id, fingerprint = shown(w.start())
    assert w.confirm(plan_id, fingerprint).text == WRITTEN
    w.ai.says(task(MEDICINE))
    reply = w.start("купити ліки", now=NOW + timedelta(minutes=5))
    new_id, _ = shown(reply)
    assert new_id != plan_id
    assert set(items(reply)) == {MEDICINE}
    assert [t["title"] for t in w.tasks()] == [MEDICINE]


def test_start_during_fresh_writing_answers_writing_now_and_keeps_draft() -> None:
    w = several(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    replies: list[Reply] = []

    def message_while_writing(_: str) -> None:
        w.ai.says(task(SISTER))
        replies.append(w.start("ще зателефонувати сестрі", now=NOW + timedelta(seconds=2)))

    w.calendar.on_insert = message_while_writing
    assert w.confirm(plan_id, fingerprint).text == WRITTEN
    assert [r.text for r in replies] == [WRITING_NOW]
    assert replies[0].plan is None
    assert {t["title"] for t in w.tasks()} == {NOTARY, MEDICINE}
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1}


# ------------------------------------------------------------------ Seam 2: writing several


def test_seam2_yes_writes_each_timed_task_once_with_its_own_event_id() -> None:
    w = several(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    reply = w.confirm(plan_id, fingerprint)
    assert reply.text.startswith(WRITTEN)
    assert TASKS_LATER in reply.text
    assert reply.plan is None
    assert sorted((e.title, e.start, e.end) for e in w.calendar.created) == sorted(
        [(NOTARY, utc(9, 9, 15), utc(9, 9, 45)), (MEDICINE, utc(9, 9, 45), utc(9, 10, 15))]
    )
    assert len({e.id for e in w.calendar.created}) == 2
    again = w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=5))
    assert again.plan is None
    assert len(w.calendar.created) == 2


def test_seam2_yes_without_untimed_tasks_answers_only_written() -> None:
    w = several(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    assert w.confirm(plan_id, fingerprint).text == WRITTEN
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1}


def test_seam2_plan_of_only_untimed_tasks_answers_only_tasks_later_line() -> None:
    w = several(
        task(SEEDS, needs_time=False, duration_min=None), task(GARDEN, needs_time=False, duration_min=None)
    )
    reply = w.start()
    plan_id, fingerprint = shown(reply)
    assert reply.plan is not None and reply.plan.items == []
    assert w.confirm(plan_id, fingerprint).text == TASKS_LATER
    assert w.calendar.insert_calls == []


def test_seam2_crash_after_second_create_old_yes_shows_the_rest_and_writes_nothing() -> None:
    w = three_timed()
    plan_id, fingerprint = crash_on(w, 2)
    written, left = written_and_left(w)
    calls = len(w.calendar.insert_calls)
    rest = w.confirm(plan_id, fingerprint, now=LATER)
    assert len(w.calendar.insert_calls) == calls, "the old fingerprint writes nothing"
    assert PARTLY_WRITTEN in rest.text
    rest_id, rest_fp = shown(rest)
    assert rest_fp != fingerprint
    assert items(rest).keys() == {left}
    # The calendar did not change: the task left keeps its free slot.
    assert at(rest, left) == SLOTS[left]
    # "yes" with the new fingerprint writes only what is left; the second is found by step 0.
    done = w.confirm(rest_id, rest_fp, now=LATER + timedelta(seconds=5))
    assert done.text == WRITTEN
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1, SISTER: 1}
    assert len({e.id for e in w.calendar.created}) == 3
    assert written <= set(w.calendar.titles())
    # A repeated "yes" after «записано»: nothing new.
    w.confirm(rest_id, rest_fp, now=LATER + timedelta(seconds=10))
    w.confirm(plan_id, fingerprint, now=LATER + timedelta(seconds=15))
    assert len(w.calendar.created) == 3


def test_seam2_foreign_event_after_crash_rest_avoids_real_events_of_written_tasks() -> None:
    w = three_timed()
    plan_id, fingerprint = crash_on(w, 2)
    _, left = written_and_left(w)
    # The two written tasks hold two of 09:15-09:45, 09:45-10:15, 10:15-10:45 UTC; a foreign event
    # takes the third one's slot up to 11:00. The first time free of all of them is 11:00.
    w.calendar.busy(SLOTS[left][0], utc(9, 11, 0))
    rest = w.confirm(plan_id, fingerprint, now=LATER)
    rest_id, rest_fp = shown(rest)
    assert items(rest).keys() == {left}
    assert at(rest, left) == (utc(9, 11, 0), utc(9, 11, 30))
    w.confirm(rest_id, rest_fp, now=LATER + timedelta(seconds=5))
    again = [e for e in w.calendar.created if e.title == left]
    assert [(e.start, e.end) for e in again] == [(utc(9, 11, 0), utc(9, 11, 30))]
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1, SISTER: 1}


def test_seam2_crash_after_last_create_next_yes_is_written_at_once() -> None:
    w = several(task(NOTARY), task(MEDICINE), honour_409=False)
    plan_id, fingerprint = crash_on(w, 2)
    calls = len(w.calendar.insert_calls)
    reply = w.confirm(plan_id, fingerprint, now=LATER)
    assert reply.text == WRITTEN
    assert reply.plan is None
    assert len(w.calendar.insert_calls) == calls
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1}


def test_seam2_task_added_to_partly_written_rest_keeps_written_tasks_written() -> None:
    w = three_timed()
    plan_id, fingerprint = crash_on(w, 2)
    _, left = written_and_left(w)
    shown(w.confirm(plan_id, fingerprint, now=LATER))
    w.ai.says(task(GARDEN))
    reply = w.start("і полити город", now=LATER + timedelta(seconds=5))
    new_id, new_fp = shown(reply)
    assert items(reply).keys() == {left, GARDEN}
    w.confirm(new_id, new_fp, now=LATER + timedelta(seconds=10))
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1, SISTER: 1, GARDEN: 1}


# ------------------------------------------------------------------ invariants


def test_I1_any_sequence_of_yes_gives_each_task_at_most_one_event() -> None:
    def at_most_one(w: Several) -> None:
        assert all(n <= 1 for n in w.calendar.titles().values()), w.calendar.titles()

    def yes_to_whatever_is_shown(w: Several, reply: Reply, now: datetime) -> Reply:
        if reply.plan is None:
            return reply
        with contextlib.suppress(Exception):
            return w.confirm(reply.plan.plan_id, reply.plan.fingerprint, now=now)
        return reply

    # (1) yes, yes, a bogus fingerprint, yes — three tasks, one of them with a named time.
    w = several(
        task(NOTARY), task(MEDICINE, start_local="2026-11-10T10:00:00"), task(SISTER), honour_409=False
    )
    plan_id, fingerprint = shown(w.start())
    w.confirm(plan_id, fingerprint)
    w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=1))
    with contextlib.suppress(Exception):
        w.confirm(plan_id, "not-the-fingerprint", now=NOW + timedelta(seconds=2))
    w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=3))
    at_most_one(w)
    assert len(w.calendar.created) == 3

    # (2)-(4) the answer of the first, the second, the last create is lost; then yes many times.
    for n in (1, 2, 3):
        w = three_timed()
        plan_id, fingerprint = crash_on(w, n)
        reply = Reply("")
        for later in (timedelta(seconds=1), timedelta(seconds=45), timedelta(seconds=50), timedelta(hours=1)):
            with contextlib.suppress(Exception):
                reply = w.confirm(plan_id, fingerprint, now=NOW + later)
            at_most_one(w)
            reply = yes_to_whatever_is_shown(w, reply, NOW + later + timedelta(seconds=1))
            at_most_one(w)

    # (5) a second loss of an answer while writing the rest.
    w = three_timed()
    plan_id, fingerprint = crash_on(w, 1)
    rest = w.confirm(plan_id, fingerprint, now=LATER)
    if rest.plan is not None:
        w.calendar.crash_on = len(w.calendar.created) + 1
        with contextlib.suppress(Exception):
            w.confirm(rest.plan.plan_id, rest.plan.fingerprint, now=LATER + timedelta(seconds=1))
        then = LATER + timedelta(minutes=1)
        with contextlib.suppress(Exception):
            again = w.confirm(rest.plan.plan_id, rest.plan.fingerprint, now=then)
            yes_to_whatever_is_shown(w, again, then + timedelta(seconds=1))
    at_most_one(w)

    # (6) a task added to the shown plan: yes with the old fingerprint, then the new one, then both again.
    w = several(task(NOTARY), honour_409=False)
    old_id, old_fp = shown(w.start())
    w.ai.says(task(MEDICINE))
    new_id, new_fp = shown(w.start("і ще купити ліки", now=NOW + timedelta(seconds=1)))
    for n, (pid, fp) in enumerate([(old_id, old_fp), (new_id, new_fp), (old_id, old_fp), (new_id, new_fp)]):
        with contextlib.suppress(Exception):
            w.confirm(pid, fp, now=NOW + timedelta(seconds=2 + n))
        at_most_one(w)
    assert w.calendar.titles() == {NOTARY: 1, MEDICINE: 1}


def test_I2_task_without_named_time_never_overlaps_and_stays_on_its_named_day() -> None:
    def check(tasks: list[TaskSpec], busy: list[Interval], result: Placement) -> None:
        spans = {task_id: (start, end) for task_id, start, end in result.placed}
        for t in tasks:
            if t.start_local is not None or t.task_id not in spans:
                continue
            start, end = spans[t.task_id]
            for b in busy:
                assert not (start < b.end and b.start < end), f"{t.task_id} overlaps busy {b!r}"
            for other, (o_start, o_end) in spans.items():
                if other != t.task_id:
                    assert not (start < o_end and o_start < end), f"{t.task_id} overlaps {other}"
            if t.day is not None:
                assert start.astimezone(BERLIN).date() == t.day, f"{t.task_id} is not on {t.day}"

    def run(tasks: list[TaskSpec], busy: list[Interval], now: datetime = NOW) -> Placement:
        result = place_many(
            tasks, busy, now=now, tz=BERLIN, step_min=15, horizon_end=now + timedelta(days=7), t0=None
        )
        check(tasks, busy, result)
        return result

    def spans(result: Placement) -> dict[str, tuple[datetime, datetime]]:
        return {task_id: (start, end) for task_id, start, end in result.placed}

    # (a) A named time later in order than the free tasks, next to a busy event.
    busy = [Interval(utc(9, 8, 0), utc(9, 9, 15))]
    tasks = [
        TaskSpec("t1", "a", 30),
        TaskSpec("t2", "b", 60, start_local=datetime(2026, 11, 9, 10, 15)),
        TaskSpec("t3", "c", 45),
    ]
    assert spans(run(tasks, busy)) == {
        "t1": (utc(9, 10, 15), utc(9, 10, 45)),
        "t2": (utc(9, 9, 15), utc(9, 10, 15)),
        "t3": (utc(9, 10, 45), utc(9, 11, 30)),
    }
    # (b) A named time over a busy event; a long free task must clear both.
    busy = [Interval(utc(9, 10, 30), utc(9, 11, 15))]
    tasks = [TaskSpec("t1", "a", 30, start_local=datetime(2026, 11, 9, 12, 0)), TaskSpec("t2", "b", 90)]
    assert spans(run(tasks, busy)) == {
        "t1": (utc(9, 11, 0), utc(9, 11, 30)),
        "t2": (utc(9, 11, 30), utc(9, 13, 0)),
    }
    # (c) Two tasks on the same named day, the day's morning busy, a named time on that day too.
    wednesday = date(2026, 11, 11)
    busy = [Interval(utc(10, 23, 0), utc(11, 0, 0))]
    tasks = [
        TaskSpec("t1", "a", 60, day=wednesday),
        TaskSpec("t2", "b", 30, day=wednesday),
        TaskSpec("t3", "c", 60, start_local=datetime(2026, 11, 11, 1, 30)),
        TaskSpec("t4", "d", 30),
    ]
    assert spans(run(tasks, busy)) == {
        "t1": (utc(11, 1, 30), utc(11, 2, 30)),
        "t2": (utc(11, 0, 0), utc(11, 0, 30)),
        "t3": (utc(11, 0, 30), utc(11, 1, 30)),
        "t4": (utc(9, 9, 15), utc(9, 9, 45)),
    }
    # (d) The spring switch: 29 March 2026 in Berlin runs 23:00 UTC (28th) to 22:00 UTC (29th).
    spring_now = datetime(2026, 3, 28, 12, 0, tzinfo=UTC)
    march29 = date(2026, 3, 29)
    assert spans(run([TaskSpec("t1", "a", 60, day=march29)], [], spring_now)) == {
        "t1": (datetime(2026, 3, 28, 23, 0, tzinfo=UTC), datetime(2026, 3, 29, 0, 0, tzinfo=UTC))
    }
    busy = [Interval(datetime(2026, 3, 28, 23, 0, tzinfo=UTC), datetime(2026, 3, 29, 22, 0, tzinfo=UTC))]
    result = run([TaskSpec("t1", "a", 60, day=march29), TaskSpec("t2", "b", 60)], busy, spring_now)
    assert result.unplaced == ["t1"]
    assert spans(result) == {
        "t2": (datetime(2026, 3, 28, 12, 15, tzinfo=UTC), datetime(2026, 3, 28, 13, 15, tzinfo=UTC))
    }
    # (e) The autumn switch: 25 October 2026 in Berlin runs 22:00 UTC (24th) to 23:00 UTC (25th).
    autumn_now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    october25 = date(2026, 10, 25)
    assert spans(run([TaskSpec("t1", "a", 60, day=october25)], [], autumn_now)) == {
        "t1": (datetime(2026, 10, 24, 22, 0, tzinfo=UTC), datetime(2026, 10, 24, 23, 0, tzinfo=UTC))
    }
    busy = [Interval(datetime(2026, 10, 24, 22, 0, tzinfo=UTC), datetime(2026, 10, 25, 22, 0, tzinfo=UTC))]
    assert spans(run([TaskSpec("t1", "a", 60, day=october25)], busy, autumn_now)) == {
        "t1": (datetime(2026, 10, 25, 22, 0, tzinfo=UTC), datetime(2026, 10, 25, 23, 0, tzinfo=UTC))
    }

    # (f) Through `planning`: the rest after a partial write avoids the real events of the written tasks.
    w = three_timed()
    plan_id, fingerprint = crash_on(w, 1)
    w.calendar.busy(utc(9, 9, 45), utc(9, 10, 0))
    rest = w.confirm(plan_id, fingerprint, now=LATER)
    assert rest.plan is not None
    taken = [(e.start, e.end) for e in w.calendar.events if not e.cancelled]
    for title in items(rest):
        start, end = at(rest, title)
        for t_start, t_end in taken:
            assert not (start < t_end and t_start < end), f"{title} overlaps an event {t_start}-{t_end}"
    assert len(items(rest)) == 2


def test_I3_task_without_time_never_gets_an_event_or_a_duration_question() -> None:
    # (a) Only untimed tasks — one without a duration, one the model gave a time and a duration anyway.
    w = several(
        task(SEEDS, needs_time=False, duration_min=None),
        task(GARDEN, needs_time=False, duration_min=45, start_local="2026-11-10T10:00:00"),
        honour_409=False,
    )
    reply = w.start()
    assert reply.question is None or reply.question.kind != "duration"
    plan_id, fingerprint = shown(reply)
    for n in range(3):
        with contextlib.suppress(Exception):
            w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=n))
    assert w.calendar.insert_calls == []

    # (b) A timed task without duration beside an untimed one: one question, then the plan.
    w = several(task(NOTARY, duration_min=None), task(SEEDS, needs_time=False, duration_min=None))
    asked = w.start()
    assert asked.question is not None and asked.question.kind == "duration"
    reply = w.answer(asked.question.id, "пів години")
    plan_id, fingerprint = shown(reply)
    assert reply.plan is not None and [u["title"] for u in reply.plan.untimed] == [SEEDS]
    w.confirm(plan_id, fingerprint)
    assert w.calendar.titles() == {NOTARY: 1}

    # (c) An untimed task added while a duration is asked; any answer, then "yes" twice.
    w = several(task(NOTARY, duration_min=None))
    asked = w.start()
    assert asked.question is not None
    w.ai.says(task(SEEDS, needs_time=False, duration_min=None))
    again = w.start("і купити насіння")
    assert again.question == Question("duration", asked.question.id, None)
    w.ai.durations = [0, 30]
    first = w.answer(asked.question.id, "не знаю")
    if first.plan is None:
        first = w.answer(asked.question.id, "пів години")
    plan_id, fingerprint = shown(first)
    w.confirm(plan_id, fingerprint)
    w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=5))
    assert w.calendar.titles() == {NOTARY: 1}

    # (d) `next_question` over a draft whose only task without duration is untimed.
    draft = {
        "plan_id": "p-1",
        "state": "shown",
        "tasks": [
            {
                "task_id": "t1",
                "title": SEEDS,
                "needs_time": False,
                "duration_min": None,
                "start_local": None,
                "constraints": {"day": None},
                "order": 1,
                "source": "speech",
                "written": {"event_id": None, "tasks_id": None, "closed": False},
            }
        ],
    }
    assert planning.next_question(draft) is None
