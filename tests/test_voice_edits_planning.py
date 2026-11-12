"""Contract tests of the slice voice-edits: `planning.edit_plan`, the route `edit`, `place_many` with
`not_before_local`; Seam 1, Seam 2, Seam 3, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/voice-edits.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1): the first free step is 10:15 Berlin = 09:15Z.
Thursday 12 November starts at 00:00 Berlin = Wednesday 11 November 23:00Z. Every time is written by hand
in UTC. Berlin goes from CET to CEST on Sunday 28 March 2027 at 02:00.
"""

import contextlib
import copy
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mamamemory.integrations.google_work import TaskItem
from mamamemory.planning import plan
from mamamemory.planning.placement import Interval, Limits, TaskSpec, place_many
from mamamemory.replies import Question, Reply
from tests.google_tasks_world import BILLS
from tests.several_tasks_world import DOCTOR, MEDICINE, NOTARY, SEEDS, SISTER, items, several, task
from tests.test_one_task_planning import NOT_ACTUAL, NOW, instant, shown
from tests.time_limits_world import WEEKDAYS, limits_question, parsed
from tests.voice_edits_world import (
    NOT_UNDERSTOOD_EDIT,
    PLAN_EMPTY,
    Editing,
    editing,
    listed_number,
)

BERLIN = ZoneInfo("Europe/Berlin")
LATER = NOW + timedelta(seconds=45)
"""Past REQUEST_TIMEOUT_S (30 s): a write left in «записується» is stale."""
TK_BILLS = TaskItem("tk-1", BILLS)
NO_WRITES = (0, 0, 0, 0)
THURSDAY = "2026-11-12"
CANNOT = "Не зрозуміла. Скажіть «що ти вмієш?» — розкажу."
"""guide, Seam «Незрозуміле»: `CANNOT_TEXT` (superseded the old «Поки що я вмію…»)."""


def utc(day: int, hour: int, minute: int = 0, *, month: int = 11, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def at(reply: Reply, title: str) -> tuple[datetime, datetime]:
    shown_items = items(reply)
    assert title in shown_items, f"{title!r} is not among the plan's items: {shown_items!r}"
    start, end = shown_items[title]
    return instant(start), instant(end)


def titles(entries: list[dict[str, str]]) -> set[str]:
    return {str(e["title"]) for e in entries}


def every_title(reply: Reply) -> set[str]:
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    return titles(reply.plan.items) | titles(reply.plan.untimed) | titles(reply.plan.unplaced)


def plan_question(reply: Reply, plan_id: str) -> str:
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    assert reply.question == Question("plan", plan_id, reply.plan.fingerprint), reply
    return reply.plan.fingerprint


def created(w: Editing) -> dict[str, tuple[datetime, datetime]]:
    return {e.title: (e.start, e.end) for e in w.tc.created}


def partly_written(w: Editing) -> tuple[str, Reply]:
    """Show the plan, «так» loses the answer of the first created event; «так» again (stale) shows the rest.

    Returns the title written and the rest shown."""
    plan_id, fingerprint = shown(w.start())
    w.tc.crash_on = 1
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert len(w.tc.created) == 1, w.tc.created
    rest = w.confirm(plan_id, fingerprint, now=LATER)
    assert rest.plan is not None, f"expected the rest as a plan, got {rest!r}"
    return w.tc.created[0].title, rest


def local(moment: datetime) -> datetime:
    return moment.astimezone(BERLIN)


# ------------------------------------------------------------------ Seam 1: edits in the placement


def test_seam1_move_to_a_day_places_the_task_only_that_day() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, before = shown(w.start())
    reply = w.edit(plan_id, "move", NOTARY, day=THURSDAY)
    # Monday is free, yet the notary stands on Thursday from 00:00 Berlin; the medicine moves up to 09:15Z.
    assert at(reply, NOTARY) == (utc(11, 23, 0), utc(11, 23, 30))
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert plan_question(reply, plan_id) != before
    assert w.find(NOTARY)["constraints"]["day"] == THURSDAY
    assert w.writes() == NO_WRITES


def test_seam1_move_to_a_day_drops_the_named_time() -> None:
    w = editing(task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60), task(NOTARY))
    plan_id, _ = shown(w.start())
    reply = w.edit(plan_id, "move", DOCTOR, day=THURSDAY)
    assert at(reply, DOCTOR) == (utc(11, 23, 0), utc(12, 0, 0))
    assert w.find(DOCTOR)["start_local"] is None
    # Moved to the day it had a named time on: free that day, from 00:00 Berlin (10 Nov 23:00Z), not 10:00.
    again = w.edit(plan_id, "move", DOCTOR, day="2026-11-11")
    assert at(again, DOCTOR) == (utc(10, 23, 0), utc(11, 0, 0))
    assert at(again, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert w.writes() == NO_WRITES


def test_seam1_move_to_a_named_time_places_exactly_then_and_drops_not_before() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "not_before", NOTARY, not_before_local="12:00")
    reply = w.edit(plan_id, "move", NOTARY, start_local="2026-11-12T10:00:00")
    # Exactly 10:00 Berlin on Thursday = 09:00Z, though «not before 12:00» was set: her named time wins.
    assert at(reply, NOTARY) == (utc(12, 9, 0), utc(12, 9, 30))
    assert w.find(NOTARY)["constraints"]["day"] == THURSDAY
    assert w.find(NOTARY)["start_local"] == "2026-11-12T10:00:00"
    # «not before» is gone: moved on to Friday by day alone, it starts at 00:00 Berlin, not at 12:00.
    friday = w.edit(plan_id, "move", NOTARY, day="2026-11-13")
    assert at(friday, NOTARY) == (utc(12, 23, 0), utc(12, 23, 30))
    assert w.writes() == NO_WRITES


def test_seam1_move_of_an_untimed_task_asks_its_duration_then_shows_the_plan() -> None:
    w = editing(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None))
    plan_id, _ = shown(w.start())
    asked = w.edit(plan_id, "move", SEEDS, day=THURSDAY)
    assert asked.question == Question("duration", plan_id, None), asked
    assert asked.plan is None, asked
    assert w.find(SEEDS)["needs_time"] is True
    w.ai.durations = [60]
    reply = w.answer(plan_id, "годину")
    assert at(reply, SEEDS) == (utc(11, 23, 0), utc(12, 0, 0))
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    plan_question(reply, plan_id)
    assert w.writes() == NO_WRITES


def test_seam1_move_of_a_task_from_tasks_asks_its_duration_then_shows_the_plan() -> None:
    w = editing(task(NOTARY), open_tasks=(TK_BILLS,), use_tasks=True)
    plan_id, _ = shown(w.start())
    asked = w.edit(plan_id, "move", BILLS, day=THURSDAY)
    assert asked.question == Question("duration", plan_id, None), asked
    assert asked.plan is None, asked
    assert w.find(BILLS)["needs_time"] is True
    w.ai.durations = [60]
    reply = w.answer(plan_id, "годину")
    assert at(reply, BILLS) == (utc(11, 23, 0), utc(12, 0, 0))
    plan_question(reply, plan_id)
    assert w.writes() == NO_WRITES


def test_seam1_not_before_drops_the_named_time() -> None:
    w = editing(task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60), task(NOTARY))
    plan_id, _ = shown(w.start())
    reply = w.edit(plan_id, "not_before", DOCTOR, not_before_local="12:00")
    # Free again, not before 12:00 Berlin: today (Monday) at 12:00 Berlin = 11:00Z, not Wednesday 10:00.
    assert at(reply, DOCTOR) == (utc(9, 11, 0), utc(9, 12, 0))
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert w.find(DOCTOR)["start_local"] is None
    plan_question(reply, plan_id)
    assert w.writes() == NO_WRITES


def test_seam1_removed_task_is_not_shown_not_placed_and_not_written_anywhere() -> None:
    w = editing(
        task(NOTARY),
        task(SEEDS, needs_time=False, duration_min=None),
        task(MEDICINE),
        open_tasks=(TK_BILLS,),
        use_tasks=True,
    )
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "remove", SEEDS)
    reply = w.edit(plan_id, "remove", BILLS)
    assert every_title(reply) == {NOTARY, MEDICINE}
    assert SEEDS not in reply.text and BILLS not in reply.text
    fingerprint = plan_question(reply, plan_id)
    w.confirm(plan_id, fingerprint)
    assert sorted(created(w)) == sorted([NOTARY, MEDICINE])
    assert w.tc.inserted == [], "a removed task does not go to Tasks"
    assert w.tc.complete_calls == [], "a removed task from Tasks is not closed in Tasks"
    current = w.draft()
    assert current is not None and current["state"] == plan.WRITTEN, current


def test_seam1_untimed_puts_the_task_under_without_time() -> None:
    w = editing(task(NOTARY), task(MEDICINE), use_tasks=True)
    plan_id, _ = shown(w.start())
    reply = w.edit(plan_id, "untimed", MEDICINE)
    assert reply.plan is not None
    assert reply.plan.untimed == [{"task_id": w.task_id(MEDICINE), "title": MEDICINE}]
    assert set(items(reply)) == {NOTARY}
    assert MEDICINE in reply.text.split("Без часу:", 1)[1]
    assert w.find(MEDICINE)["needs_time"] is False
    w.confirm(plan_id, plan_question(reply, plan_id))
    assert sorted(created(w)) == [NOTARY]
    assert w.tc.inserted == [MEDICINE], "an untimed task goes to Tasks on «так» with use_tasks"


def test_place_many_raises_the_lower_bound_to_not_before_on_every_day() -> None:
    def one(spec: TaskSpec, busy: list[Interval], limits: Limits | None = None) -> tuple[datetime, datetime]:
        result = place_many(
            [spec],
            busy,
            now=NOW,
            tz=BERLIN,
            step_min=15,
            horizon_end=NOW + timedelta(days=7),
            t0=None,
            limits=limits,
        )
        assert result.unplaced == [], result
        assert len(result.placed) == 1, result
        _, start, end = result.placed[0]
        return start, end

    noon = TaskSpec("t1", "a", 30, not_before_local=time(12, 0))
    # Monday is free: 12:00 Berlin = 11:00Z (not the first step, 09:15Z).
    assert one(noon, []) == (utc(9, 11, 0), utc(9, 11, 30))
    # Monday busy from 12:00 Berlin to midnight: Tuesday at 12:00 Berlin, not at 00:00.
    rest_of_monday = [Interval(utc(9, 11, 0), utc(9, 23, 0))]
    assert one(noon, rest_of_monday) == (utc(10, 11, 0), utc(10, 11, 30))
    # Together with the limits (weekdays 09:00–18:00): the later of the two bounds.
    workdays = Limits(days=frozenset(WEEKDAYS), start_local=time(9, 0), end_local=time(18, 0))
    early = TaskSpec("t1", "a", 30, not_before_local=time(8, 0))
    all_monday = [Interval(utc(9, 9, 0), utc(9, 23, 0))]
    assert one(early, all_monday, workdays) == (utc(10, 8, 0), utc(10, 8, 30))
    late = TaskSpec("t1", "a", 30, not_before_local=time(17, 30))
    assert one(late, all_monday, workdays) == (utc(10, 16, 30), utc(10, 17, 0))
    # Together with a named day: Thursday, not before 14:00 Berlin = 13:00Z.
    thursday = TaskSpec("t1", "a", 30, day=date(2026, 11, 12), not_before_local=time(14, 0))
    assert one(thursday, []) == (utc(12, 13, 0), utc(12, 13, 30))


def test_constraints_survive_later_changes_of_the_draft() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "not_before", NOTARY, not_before_local="12:00")
    w.edit(plan_id, "remove", MEDICINE)
    # A new task added to the shown draft: a new show, the earlier edits still hold.
    w.ai.says(task(SISTER))
    reply = w.start("ще зателефонувати сестрі")
    assert at(reply, NOTARY) == (utc(9, 11, 0), utc(9, 11, 30))
    assert at(reply, SISTER) == (utc(9, 9, 15), utc(9, 9, 45))
    assert MEDICINE not in every_title(reply)
    assert MEDICINE not in reply.text
    assert w.writes() == NO_WRITES


def test_removing_the_last_unwritten_task_says_the_plan_is_empty() -> None:
    w = editing(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None))
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "remove", SEEDS)
    reply = w.edit(plan_id, "remove", NOTARY)
    assert PLAN_EMPTY in reply.text, reply
    assert reply.plan is None, reply
    current = w.draft()
    assert current is not None and current["state"] == plan.WRITTEN, current
    assert w.writes() == NO_WRITES


def test_a_plan_left_with_one_task_is_shown_as_a_plan_of_one_task() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    reply = w.edit(plan_id, "remove", MEDICINE)
    alone = several(task(NOTARY)).start()
    assert at(reply, NOTARY) == at(alone, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert reply.text == alone.text


def test_removed_and_written_tasks_are_not_in_the_list_the_model_numbers() -> None:
    w = editing(task(NOTARY), task(MEDICINE), task(SISTER))
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "remove", MEDICINE)
    w.edit(plan_id, "none")
    prompt = w.ai.edit_prompts[-1]
    assert listed_number(prompt, NOTARY) is not None, prompt
    assert listed_number(prompt, SISTER) is not None, prompt
    assert MEDICINE not in prompt, prompt
    # A partly written plan: the written task is not listed, the rest is.
    p = editing(task(NOTARY), task(MEDICINE), task(SISTER))
    written, rest = partly_written(p)
    assert rest.plan is not None
    p.edit(rest.plan.plan_id, "none", now=LATER)
    prompt = p.ai.edit_prompts[-1]
    assert written not in prompt, prompt
    for title in {NOTARY, MEDICINE, SISTER} - {written}:
        assert listed_number(prompt, title) is not None, prompt


# ------------------------------------------------------------------ where edit_plan acts


def test_edit_of_a_plan_id_that_is_not_the_current_draft_is_not_actual() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    shown(w.start())
    before = copy.deepcopy(w.draft())
    reply = w.edit("not-the-plan", "move", NOTARY, day=THURSDAY)
    assert reply.text == NOT_ACTUAL
    assert w.draft() == before
    assert w.writes() == NO_WRITES


def test_edit_while_a_question_is_asked_returns_that_question_and_changes_nothing() -> None:
    w = editing(task(NOTARY, duration_min=None), task(MEDICINE))
    first = w.start()
    assert first.question is not None and first.question.kind == "duration", first
    before = copy.deepcopy(w.draft())
    reply = w.edit(first.question.id, "move", MEDICINE, day=THURSDAY)
    assert reply.question == Question("duration", first.question.id, None), reply
    assert reply.plan is None
    assert w.draft() == before


def test_edit_into_asking_is_refused_while_a_fresh_write_is_running() -> None:
    w = editing(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None))
    plan_id, fingerprint = shown(w.start())

    class Interrupted(BaseException):
        """Stops the concurrent «так» inside its first creation: the draft stays in a fresh «записується»."""

    def stop(_: str) -> None:
        raise Interrupted

    def concurrent_yes() -> None:
        w.tc.on_insert = stop
        with contextlib.suppress(Interrupted):
            w.confirm(plan_id, fingerprint)

    w.ai.during_edit = concurrent_yes
    with contextlib.suppress(Exception):
        w.edit(plan_id, "move", SEEDS, day=THURSDAY)
    current = w.draft()
    assert current is not None and current["state"] == plan.WRITING, current
    assert w.find(SEEDS)["needs_time"] is False, "the edit was not applied over a running write"


# ------------------------------------------------------------------ Seam 2: the old fingerprint


def test_seam2_yes_with_the_old_fingerprint_writes_nothing_and_shows_the_edited_plan() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, old = shown(w.start())
    w.edit(plan_id, "move", NOTARY, day=THURSDAY)
    again = w.confirm(plan_id, old)
    assert w.writes() == NO_WRITES
    assert at(again, NOTARY) == (utc(11, 23, 0), utc(11, 23, 30))
    assert at(again, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    plan_question(again, plan_id)


def test_seam2_yes_with_the_new_fingerprint_writes_the_edited_plan() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    edited = w.edit(plan_id, "move", NOTARY, day=THURSDAY)
    w.confirm(plan_id, plan_question(edited, plan_id))
    assert created(w) == {
        NOTARY: (utc(11, 23, 0), utc(11, 23, 30)),
        MEDICINE: (utc(9, 9, 15), utc(9, 9, 45)),
    }


# ------------------------------------------------------------------ Seam 3: the route


def test_seam3_message_replying_to_the_plan_with_intent_edit_goes_to_edit_plan() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    w.ai.intent = "edit"
    w.ai.wants("move", NOTARY, day=THURSDAY)
    reply = w.message("перенеси нотаріуса на четвер", Question("plan", plan_id, fingerprint))
    assert at(reply, NOTARY) == (utc(11, 23, 0), utc(11, 23, 30))
    plan_question(reply, plan_id)
    assert "route" in w.ai.calls
    assert w.writes() == NO_WRITES


def test_seam3_edit_not_understood_keeps_the_plan_and_its_fingerprint() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    before = copy.deepcopy(w.draft())
    w.ai.intent = "edit"
    unreadable: list[dict[str, Any]] = [
        {"kind": "none"},
        {"kind": "move", "title": NOTARY},
        {"kind": "not_before", "title": NOTARY},
        {"kind": "move", "number": 99, "day": THURSDAY},
        {"kind": "remove", "title": None},
    ]
    for edit in unreadable:
        w.ai.wants(
            edit["kind"],
            edit.get("title"),
            number=edit.get("number"),
            day=edit.get("day"),
        )
        reply = w.message("щось про план", Question("plan", plan_id, fingerprint))
        assert NOT_UNDERSTOOD_EDIT in reply.text, (edit, reply)
        assert w.draft() == before, edit
    # The fingerprint did not change: «так» with it writes the plan as shown.
    w.confirm(plan_id, fingerprint)
    assert created(w) == {
        NOTARY: (utc(9, 9, 15), utc(9, 9, 45)),
        MEDICINE: (utc(9, 9, 45), utc(9, 10, 15)),
    }


def test_seam3_what_is_not_an_edit_is_still_other() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    before = copy.deepcopy(w.draft())
    w.ai.intent = "other"
    reply = w.message("ну не знаю", Question("plan", plan_id, fingerprint))
    assert reply.text == CANNOT
    assert w.draft() == before
    assert w.writes() == NO_WRITES


# ------------------------------------------------------------------ invariants


def test_I1_an_edit_never_writes_to_calendar_or_tasks() -> None:
    # A plan with spoken tasks on time, one without time and one from Tasks; every kind of edit.
    w = editing(
        task(NOTARY),
        task(MEDICINE),
        task(SEEDS, needs_time=False, duration_min=None),
        open_tasks=(TK_BILLS,),
        use_tasks=True,
    )
    plan_id, _ = shown(w.start())
    edits: list[dict[str, Any]] = [
        {"kind": "move", "title": NOTARY, "day": THURSDAY},
        {"kind": "move", "title": MEDICINE, "start_local": "2026-11-11T15:00:00"},
        {"kind": "not_before", "title": NOTARY, "not_before_local": "12:00"},
        {"kind": "untimed", "title": MEDICINE},
        {"kind": "none"},
        {"kind": "move", "number": 99, "day": THURSDAY},
        {"kind": "remove", "title": SEEDS},
        {"kind": "remove", "title": BILLS},
        {"kind": "move", "title": MEDICINE, "day": "2026-11-13"},
    ]
    for edit in edits:
        w.edit(
            plan_id,
            edit["kind"],
            edit.get("title"),
            number=edit.get("number"),
            day=edit.get("day"),
            start_local=edit.get("start_local"),
            not_before_local=edit.get("not_before_local"),
        )
        assert w.writes() == NO_WRITES, edit
    assert w.tc.inserted == [] and w.tc.completed == []

    # An edit that leads to the duration question.
    d = editing(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None), use_tasks=True)
    d_plan, _ = shown(d.start())
    d.edit(d_plan, "move", SEEDS, day=THURSDAY)
    assert d.writes() == NO_WRITES

    # An edit that removes the last task.
    e = editing(task(NOTARY), use_tasks=True)
    e_plan, _ = shown(e.start())
    e.edit(e_plan, "remove", NOTARY)
    assert e.writes() == NO_WRITES

    # A partly written plan: no edit of the rest writes anything more.
    p = editing(task(NOTARY), task(MEDICINE), task(SISTER), use_tasks=True)
    written, rest = partly_written(p)
    assert rest.plan is not None
    p_plan = rest.plan.plan_id
    left = sorted({NOTARY, MEDICINE, SISTER} - {written})
    so_far = p.writes()
    p.edit(p_plan, "move", left[0], day=THURSDAY, now=LATER)
    assert p.writes() == so_far
    p.edit(p_plan, "not_before", left[1], not_before_local="12:00", now=LATER)
    assert p.writes() == so_far
    p.edit(p_plan, "untimed", left[0], now=LATER)
    assert p.writes() == so_far
    p.edit(p_plan, "remove", left[1], now=LATER)
    assert p.writes() == so_far
    assert p.tc.inserted == []


def test_I2_moved_task_stands_only_that_day_and_not_before_is_kept_on_every_day() -> None:
    # (a) A task with a named time moved to a day that is busy until 09:00 Berlin (08:00Z).
    a = editing(task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60))
    a.tc.busy(utc(12, 23, 0), utc(13, 8, 0))
    a_plan, _ = shown(a.start())
    reply = a.edit(a_plan, "move", DOCTOR, day="2026-11-13")
    assert at(reply, DOCTOR) == (utc(13, 8, 0), utc(13, 9, 0))
    assert all(local(t).date() == date(2026, 11, 13) for t in at(reply, DOCTOR))

    # (b) Monday busy from 12:00 Berlin to midnight; an edit refused first, then «not before 12:00»:
    # Tuesday 12:00 Berlin, not Tuesday 00:00. Then moved to Thursday by day: still not before 12:00.
    b = editing(task(NOTARY))
    b.tc.busy(utc(9, 11, 0), utc(9, 23, 0))
    b_plan, _ = shown(b.start())
    b.edit(b_plan, "none")
    reply = b.edit(b_plan, "not_before", NOTARY, not_before_local="12:00")
    assert at(reply, NOTARY) == (utc(10, 11, 0), utc(10, 11, 30))
    reply = b.edit(b_plan, "move", NOTARY, day=THURSDAY)
    assert at(reply, NOTARY) == (utc(12, 11, 0), utc(12, 11, 30))
    start, _ = at(reply, NOTARY)
    assert local(start).date() == date(2026, 11, 12) and local(start).time() >= time(12, 0)

    # (c) Over the change to summer time: Saturday 27 March 2027 busy from 12:00 Berlin (CET) to midnight;
    # Sunday 28 March at 12:00 Berlin is CEST, 10:00Z.
    spring_now = datetime(2027, 3, 27, 9, 7, tzinfo=UTC)
    c = editing(task(NOTARY))
    c.tc.busy(utc(27, 11, 0, month=3, year=2027), utc(27, 23, 0, month=3, year=2027))
    c_plan, _ = shown(c.start(now=spring_now))
    reply = c.edit(c_plan, "not_before", NOTARY, not_before_local="12:00", now=spring_now)
    assert at(reply, NOTARY) == (utc(28, 10, 0, month=3, year=2027), utc(28, 10, 30, month=3, year=2027))

    # (d) With the limits (weekdays 09:00–18:00) and Monday busy: the later of the two bounds on Tuesday.
    d = editing(task(NOTARY), ask_limits=True)
    d.seed_limits(WEEKDAYS, "09:00", "18:00")
    d.tc.busy(utc(9, 9, 0), utc(9, 23, 0))
    question = limits_question(d.start())
    d.ai.limits = parsed(same_as_last=True)
    d_plan, _ = shown(d.answer_limits(question.id, "так"))
    reply = d.edit(d_plan, "not_before", NOTARY, not_before_local="08:00")
    assert at(reply, NOTARY) == (utc(10, 8, 0), utc(10, 8, 30))
    reply = d.edit(d_plan, "not_before", NOTARY, not_before_local="17:30")
    assert at(reply, NOTARY) == (utc(10, 16, 30), utc(10, 17, 0))
