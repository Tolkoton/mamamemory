"""Contract tests of the slice add-simply: «додай задачу» without the duration and limits questions, the
«коли?» question and its answer, edits without it, the request with no task — Seam 1, 2, 2b, 3, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/add-simply.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1): Tuesday 10:00 Berlin = 09:00Z, Wednesday
15:00 Berlin = 14:00Z. Every time below is written by hand in UTC.
"""

from datetime import timedelta
from typing import Any

from mamamemory import assistant, planning
from mamamemory.replies import Reply
from tests.add_simply_world import (
    ASK_WHAT_TO_ADD,
    BANNED_KINDS,
    NOT_ACTUAL,
    TUESDAY,
    WEDNESDAY,
    AddSimply,
    add_simply,
    ask_hour,
    ask_when,
    local,
    utc,
    when,
    when_question,
)
from tests.several_tasks_world import MEDICINE, NOTARY, SISTER, items, task
from tests.stuck_question_world import cannot
from tests.test_one_task_planning import NOW, instant, shown

AT_TUESDAY_TEN = "2026-11-10T10:00"


def placed(reply: Reply | None, title: str) -> tuple[Any, Any]:
    assert reply is not None, "expected a plan, got None"
    found = items(reply)
    assert title in found, (title, found)
    start, end = found[title]
    return instant(start), instant(end)


def plan_shown(reply: Reply | None) -> Reply:
    assert reply is not None, "expected a plan, got None"
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    assert reply.question is not None and reply.question.kind == "plan", reply
    return reply


def not_banned(reply: Reply | None) -> None:
    assert reply is not None
    assert reply.question is None or reply.question.kind not in BANNED_KINDS, reply
    assert "Скільки часу" not in reply.text, reply.text
    assert "Коли ви взагалі можете" not in reply.text, reply.text


# ------------------------------------------------------------------ Seam 1: «додай задачу» без питань


def test_seam1_add_with_a_named_time_shows_the_plan_at_once_for_sixty_minutes() -> None:
    w = add_simply(ask_limits=True, ask_priorities=True)
    reply = w.add(
        task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None),
        text="додай задачу подзвонити сестрі у вівторок о десятій",
    )
    not_banned(reply)
    plan_shown(reply)
    assert planning.ADD_DEFAULT_MIN == 60
    assert placed(reply, SISTER) == (utc(10, 9), utc(10, 10))


def test_seam1_plan_the_week_with_the_same_fakes_asks_the_duration_as_before() -> None:
    w = add_simply(ask_limits=True, ask_priorities=True)
    reply = w.plan_week(task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None), text="сплануй тиждень")
    assert reply.question is not None and reply.question.kind == "duration", reply
    assert reply.plan is None, reply
    assert w.mode() == "week"


# ------------------------------------------------------------------ Seam 2: «коли?»


def test_seam2_a_task_without_a_time_is_asked_when_with_day_and_hour() -> None:
    w = add_simply()
    reply = w.add(task(SISTER, duration_min=None))
    when_question(reply, w)
    assert ask_when(SISTER) in reply.text, reply.text
    not_banned(reply)


def test_seam2_a_task_with_a_known_day_is_asked_the_hour() -> None:
    w = add_simply()
    reply = w.add(task(SISTER, day=WEDNESDAY, duration_min=None))
    when_question(reply, w)
    assert ask_hour(SISTER) in reply.text, reply.text


def test_seam2_an_answer_with_start_local_shows_the_plan_at_that_time() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    reply = w.answer_when(question.id, when(day=TUESDAY, start_local=AT_TUESDAY_TEN), "у вівторок о десятій")
    plan_shown(reply)
    assert placed(reply, SISTER) == (utc(10, 9), utc(10, 10))
    assert w.find(SISTER)["constraints"]["day"] == TUESDAY


def test_seam2_an_answer_with_only_a_day_asks_the_hour_and_keeps_the_day() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    reply = w.answer_when(question.id, when(day=WEDNESDAY), "у середу")
    again = when_question(reply, w)
    assert reply is not None and ask_hour(SISTER) in reply.text, reply
    assert w.find(SISTER)["constraints"]["day"] == WEDNESDAY
    then = w.answer_when(again.id, when(day=WEDNESDAY, start_local="2026-11-11T15:00"), "о третій")
    assert placed(then, SISTER) == (utc(11, 14), utc(11, 15))


def test_seam2_an_answer_without_day_or_time_asks_the_same_question_and_keeps_the_tasks() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    before = w.tasks()
    reply = w.answer_when(question.id, when(), "будь-коли")
    assert when_question(reply, w) == question
    assert reply is not None and ask_when(SISTER) in reply.text, reply
    assert w.tasks() == before


def test_seam2_not_an_answer_gives_none_and_keeps_the_draft() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    before = w.draft()
    assert w.answer_when(question.id, when(is_answer=False), "які плани на сьогодні?") is None
    assert w.draft() == before


def test_seam2_two_tasks_without_a_time_are_asked_in_turn() -> None:
    w = add_simply()
    first = w.add(task(SISTER, duration_min=None), task(NOTARY, duration_min=None))
    question = when_question(first, w)
    first_title = SISTER if ask_when(SISTER) in first.text else NOTARY
    other = NOTARY if first_title == SISTER else SISTER
    assert ask_when(first_title) in first.text and ask_when(other) not in first.text, first.text
    second = w.answer_when(question.id, when(day=TUESDAY, start_local=AT_TUESDAY_TEN))
    next_question = when_question(second, w)
    assert second is not None and ask_when(other) in second.text, second
    done = w.answer_when(next_question.id, when(day=WEDNESDAY, start_local="2026-11-11T15:00"))
    plan_shown(done)
    assert placed(done, first_title) == (utc(10, 9), utc(10, 10))
    assert placed(done, other) == (utc(11, 14), utc(11, 15))


def test_seam2_parse_when_is_asked_with_all_three_fields_required() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    w.answer_when(question.id, when(day=TUESDAY, start_local=AT_TUESDAY_TEN))
    assert w.ai.when_types == ["parse_when"], w.ai.when_types
    schema = w.ai.when_schemas[-1]
    assert {"is_answer", "day", "start_local"} <= set(schema.get("properties", {})), schema
    assert {"is_answer", "day", "start_local"} <= set(schema.get("required", [])), schema


def test_seam2_a_stale_or_foreign_draft_is_answered_as_try_answer_duration() -> None:
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    before = w.draft()
    w.ai.when = when(day=TUESDAY, start_local=AT_TUESDAY_TEN)
    assert w.try_when(question.id, "у вівторок о десятій", now=NOW + timedelta(hours=25)) is None
    assert w.draft() == before
    foreign = w.try_when("another-plan", "у вівторок о десятій")
    assert foreign is not None and foreign.text == NOT_ACTUAL, foreign
    plan_id, _ = shown(plan_shown(w.try_when(question.id, "у вівторок о десятій")))
    not_asking = w.try_when(plan_id, "у вівторок о десятій")
    assert not_asking is not None and not_asking.text == NOT_ACTUAL, not_asking


def test_seam2_the_assistant_routes_a_when_reply_to_try_answer_when() -> None:
    assert assistant.SHORT_ANSWERS["when"] is planning.try_answer_when
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None)), w)
    w.ai.when = when(is_answer=False)
    cannot(w.say("які плани?", question, intent="other"))
    assert w.ai.when_types, "the when parse was not asked"
    assert w.draft() is not None and [t["title"] for t in w.tasks()] == [SISTER]
    w.ai.when = when(day=TUESDAY, start_local=AT_TUESDAY_TEN)
    reply = w.say("у вівторок о десятій", question, intent="new_task")
    assert placed(plan_shown(reply), SISTER) == (utc(10, 9), utc(10, 10))


# ------------------------------------------------------------------ Seam 2b: правка без питання


def _added_at_ten(w: AddSimply) -> str:
    plan_id, _ = shown(w.add(task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None)))
    return plan_id


def test_seam2b_not_before_edit_shows_the_plan_again_without_asking_when() -> None:
    w = add_simply()
    plan_id = _added_at_ten(w)
    reply = w.edit(plan_id, "not_before", SISTER, not_before_local="15:00")
    plan_shown(reply)
    not_banned(reply)
    start, _ = placed(reply, SISTER)
    assert local(start.isoformat()).hour >= 15, start


def test_seam2b_move_to_a_day_only_shows_the_plan_on_that_day() -> None:
    w = add_simply()
    plan_id = _added_at_ten(w)
    reply = w.edit(plan_id, "move", SISTER, day=WEDNESDAY)
    plan_shown(reply)
    start, _ = placed(reply, SISTER)
    assert local(start.isoformat()).date().isoformat() == WEDNESDAY, start


def test_seam2b_not_before_seven_pm_without_saved_limits_places_after_seven() -> None:
    w = add_simply(ask_limits=True)
    plan_id = _added_at_ten(w)
    reply = w.edit(plan_id, "not_before", SISTER, not_before_local="19:00")
    plan_shown(reply)
    start, _ = placed(reply, SISTER)
    assert local(start.isoformat()).hour >= 19, start


# ------------------------------------------------------------------ Seam 3: просьба без задачі


def test_seam3_the_request_alone_asks_which_task_and_keeps_no_draft() -> None:
    for title in (
        "Додати таску",
        "додай задачу",
        "додайте нову справу",
        "додавай ще одну таску будь ласка",
        "додати таск",
        "додай завдання",
    ):
        w = add_simply()
        reply = w.add(task(title, duration_min=None), text=title)
        assert reply.text == ASK_WHAT_TO_ADD, (title, reply)
        assert reply.question is None and reply.plan is None, (title, reply)
        assert w.draft() is None, title


def test_seam3_the_request_with_a_task_is_a_task() -> None:
    w = add_simply()
    reply = w.add(task("додати таску купити хліб", duration_min=None), text="додати таску купити хліб")
    assert reply.text != ASK_WHAT_TO_ADD, reply
    assert w.draft() is not None


# ------------------------------------------------------------------ Invariants


def _add_drafts() -> list[dict[str, Any]]:
    """Add drafts of every kind the Domain names, each taken as the flow leaves it."""
    drafts: list[dict[str, Any]] = []

    def keep(w: AddSimply) -> None:
        current = w.draft()
        assert current is not None and current.get("mode") == "add", current
        drafts.append(current)

    # With a time and without a duration, limits never saved, ask_limits on.
    a = add_simply(ask_limits=True, ask_priorities=True)
    not_banned(
        a.add(task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None), task(NOTARY, duration_min=None))
    )
    keep(a)
    # Saved limits, two tasks with durations and one without a time: the «when» question.
    b = add_simply(ask_limits=True, ask_priorities=True)
    b.seed_limits([0, 1, 2, 3, 4], "14:00", "18:00")
    first = b.add(task(SISTER), task(MEDICINE, start_local=AT_TUESDAY_TEN), task(NOTARY, duration_min=None))
    not_banned(first)
    keep(b)
    # Its answers: a day only, then a time.
    q = when_question(first, b)
    not_banned(b.answer_when(q.id, when(day=WEDNESDAY)))
    keep(b)
    not_banned(b.answer_when(q.id, when(day=WEDNESDAY, start_local="2026-11-11T15:00")))
    keep(b)
    # Removed, made untimed, not-before: edits by voice.
    c = add_simply(ask_limits=True, ask_priorities=True)
    plan_id, _ = shown(
        c.add(
            task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None),
            task(NOTARY, start_local="2026-11-10T12:00", duration_min=None),
        )
    )
    not_banned(c.edit(plan_id, "not_before", SISTER, not_before_local="15:00"))
    keep(c)
    not_banned(c.edit(plan_id, "untimed", NOTARY))
    keep(c)
    not_banned(c.edit(plan_id, "remove", SISTER))
    keep(c)
    # Written, then another task added: the written one stays in the draft or leaves it.
    d = add_simply(ask_limits=False, ask_priorities=False)
    plan_id, fingerprint = shown(d.add(task(SISTER, start_local=AT_TUESDAY_TEN, duration_min=None)))
    d.confirm(plan_id, fingerprint)
    not_banned(
        d.add(task(NOTARY, start_local="2026-11-10T12:00", duration_min=None), now=NOW + timedelta(minutes=2))
    )
    keep(d)
    # Untimed tasks without a duration.
    e = add_simply()
    not_banned(
        e.add(
            task("купити хліб", needs_time=False, duration_min=None),
            task(MEDICINE, needs_time=False, duration_min=None),
        )
    )
    keep(e)
    return drafts


def test_I1_an_add_draft_never_asks_the_duration_limits_or_priorities() -> None:
    drafts = _add_drafts()
    widened: list[dict[str, Any]] = []
    for draft in drafts:
        widened.append(draft)
        # The same draft with nothing answered and every task without a duration.
        bare_tasks = [dict(t, duration_min=None) for t in draft["tasks"]]
        widened.append(dict(draft, tasks=bare_tasks, limits_answered=False, priorities_answered=False))
    for draft in widened:
        for ask_limits in (False, True):
            for ask_priorities in (False, True):
                asked = planning.next_question(draft, ask_limits=ask_limits, ask_priorities=ask_priorities)
                assert asked is None or asked.kind not in BANNED_KINDS, (asked, draft)


def test_I2_a_when_parse_that_is_no_answer_never_changes_the_draft() -> None:
    answers = [
        when(is_answer=False),
        when(is_answer=False, day=TUESDAY),
        when(is_answer=False, start_local=AT_TUESDAY_TEN),
        when(is_answer=False, day=TUESDAY, start_local=AT_TUESDAY_TEN),
        when(is_answer=False, day="2026-11-09", start_local="2026-11-09T08:00"),
        when(is_answer=False, day="2026-11-30", start_local="2026-11-30T10:00"),
    ]
    phrases = ["які плани на сьогодні?", "о десятій", "", "додай задачу купити хліб"]
    w = add_simply()
    question = when_question(w.add(task(SISTER, duration_min=None), task(NOTARY, duration_min=None)), w)
    for answer in answers:
        for phrase in phrases:
            before = w.draft()
            assert w.answer_when(question.id, answer, phrase) is None, (answer, phrase)
            assert w.draft() == before, (answer, phrase)
    # After a lawful answer (a day only) the rule still holds.
    w.answer_when(question.id, when(day=WEDNESDAY))
    for answer in answers:
        before = w.draft()
        assert w.answer_when(question.id, answer, "які плани?") is None, answer
        assert w.draft() == before, answer
