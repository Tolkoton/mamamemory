"""Contract tests of the slice add-or-plan: «додати» against «спланувати» in `planning.start` and the route in
`assistant` — Seam 1, Seam 2, Seam 3, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/add-or-plan.md`, without the code.
Rewritten by the tester of `.engine/slices/add-simply.md` (supersession): a «додай» draft asks no duration and
no limits — a task with a named time is planned at once (60 minutes when none is named), one without a time
is asked «коли?».
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1). Tuesday 10 November 10:00 Berlin = 09:00Z,
12:00 Berlin = 11:00Z, 15:00 Berlin = 14:00Z. Every time below is written by hand in UTC.
"""

from datetime import UTC, datetime, timedelta

from mamamemory import assistant
from mamamemory.integrations.google_work import TaskItem
from mamamemory.replies import Reply
from tests.add_or_plan_world import (
    NO_TASKS_THIS_WEEK,
    TK_BILLS,
    TK_PARCEL,
    AddOrPlan,
    add_or_plan,
    no_priorities,
)
from tests.add_simply_world import AddSimply, WhenAI, ask_when, when
from tests.google_tasks_world import BILLS, PARCEL, TasksCalendar
from tests.priorities_world import listed, priorities_question
from tests.several_tasks_world import DOCTOR, MEDICINE, NOTARY, SISTER, items, task
from tests.test_one_task_planning import instant, shown
from tests.time_limits_world import AGAIN_PREFIX, WEEKDAYS, RecordingStore, limits_question

TUE_10 = "2026-11-10T10:00"
TUE_12 = "2026-11-10T12:00"
TUE_15 = "2026-11-10T15:00"
WED_10 = "2026-11-11T10:00"
WED_15 = "2026-11-11T15:00"
THU_10 = "2026-11-12T10:00"
THU_15 = "2026-11-12T15:00"


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def at(title: str, start_local: str, duration_min: int | None = 30) -> dict[str, object]:
    """A spoken task with a named time."""
    return task(title, start_local=start_local, duration_min=duration_min)


def with_when(*open_tasks: TaskItem, ask_limits: bool = False) -> AddSimply:
    """The add-or-plan world (Tasks on, priorities on) that also answers «коли?» through `try_answer_when`."""
    return AddSimply(
        WhenAI(), TasksCalendar(*open_tasks, honour_409=True), RecordingStore(), ask_limits, True, True
    )


def no_duration_nor_limits(reply: Reply | None) -> None:
    assert reply is not None
    assert reply.question is None or reply.question.kind not in ("duration", "limits"), reply
    assert "Скільки часу" not in reply.text, reply.text
    assert "Коли ви взагалі можете" not in reply.text, reply.text


def placed(reply: Reply, title: str) -> tuple[datetime, datetime]:
    start, end = items(reply)[title]
    return instant(start), instant(end)


# ------------------------------------------------------------------ Seam 1: «додати»


def test_seam1_add_reads_no_tasks_asks_no_priorities_and_shows_the_plan_at_once() -> None:
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    reply = w.add(at(NOTARY, TUE_10), at(MEDICINE, TUE_12))
    no_priorities(reply)
    no_duration_nor_limits(reply)
    assert w.tc.list_calls == 0
    assert set(items(reply)) == {NOTARY, MEDICINE}, reply
    assert BILLS not in reply.text and PARCEL not in reply.text, reply.text
    assert w.titles() == [NOTARY, MEDICINE]
    assert w.mode() == "add"


def test_seam1_add_without_a_duration_asks_no_duration_nor_priorities() -> None:
    # A task with a time and no duration is placed for 60 minutes; one with no time is asked «коли?».
    w = with_when(TK_BILLS)
    reply = w.add(at(NOTARY, TUE_10, duration_min=None), task(MEDICINE))
    no_priorities(reply)
    no_duration_nor_limits(reply)
    assert reply.question is not None and reply.question.kind == "when", reply
    assert ask_when(MEDICINE) in reply.text, reply.text
    assert reply.plan is None
    plan = w.answer_when(
        reply.question.id, when(day="2026-11-10", start_local=TUE_12), "у вівторок о дванадцятій"
    )
    assert plan is not None
    shown(plan)
    assert placed(plan, NOTARY) == (utc(10, 9), utc(10, 10))
    assert placed(plan, MEDICINE) == (utc(10, 11), utc(10, 11, 30))
    assert w.tc.list_calls == 0


def test_seam1_add_appended_to_an_unwritten_add_draft_reads_no_tasks() -> None:
    w = add_or_plan(TK_BILLS)
    shown(w.add(at(NOTARY, TUE_10)))
    again = w.add(at(MEDICINE, TUE_12), text="і ще купити ліки", now=utc(9, 9, 8))
    no_priorities(again)
    assert w.tc.list_calls == 0
    assert w.titles() == [NOTARY, MEDICINE]
    assert w.mode() == "add"
    assert set(items(again)) == {NOTARY, MEDICINE}, again


def test_seam1_add_with_saved_limits_applies_them_without_a_question() -> None:
    w = add_or_plan(TK_BILLS, ask_limits=True)
    w.seed_limits(WEEKDAYS, "14:00", "18:00")
    reply = w.add(at(NOTARY, TUE_15))
    assert AGAIN_PREFIX not in reply.text, reply.text
    no_duration_nor_limits(reply)
    assert reply.question is not None and reply.question.kind == "plan", reply
    assert placed(reply, NOTARY) == (utc(10, 14), utc(10, 14, 30))


def test_seam1_add_without_saved_limits_asks_no_limits_question() -> None:
    w = add_or_plan(TK_BILLS, ask_limits=True)
    reply = w.add(at(NOTARY, TUE_10), at(MEDICINE, TUE_12))
    no_priorities(reply)
    no_duration_nor_limits(reply)
    shown(reply)
    assert placed(reply, NOTARY) == (utc(10, 9), utc(10, 9, 30))
    assert placed(reply, MEDICINE) == (utc(10, 11), utc(10, 11, 30))
    assert w.tc.list_calls == 0


# ------------------------------------------------------------------ the mode of a week draft


def test_add_on_a_week_draft_keeps_the_week_and_asks_the_priorities_again() -> None:
    w = add_or_plan(TK_BILLS)
    first = w.plan_week(task(NOTARY), text="сплануй тиждень: подзвонити нотаріусу")
    question = priorities_question(first)
    w.pick(question.id, order=(1, 2))
    again = w.add(task(SISTER), text="і ще подзвонити сестрі", now=utc(9, 9, 8))
    priorities_question(again)
    assert w.mode() == "week"
    assert w.titles().count(BILLS) == 1
    assert SISTER in w.titles()


# ------------------------------------------------------------------ Seam 2: «спланувати»


def test_seam2_week_true_reads_tasks_and_asks_the_priorities_as_f2() -> None:
    w = add_or_plan(TK_BILLS)
    first = w.plan_week(task(NOTARY), task(MEDICINE), text="сплануй тиждень: нотаріус і ліки")
    priorities_question(first)
    listed(first.text, NOTARY, MEDICINE, BILLS)
    assert w.tc.list_calls == 1
    assert w.mode() == "week"


def test_seam2_week_appended_to_an_add_draft_turns_it_into_week_with_tasks_once() -> None:
    w = add_or_plan(TK_BILLS, TK_BILLS)
    shown(w.add(at(NOTARY, TUE_10)))
    assert w.tc.list_calls == 0
    again = w.plan_week(task(MEDICINE), text="давай планувати тиждень: ще купити ліки", now=utc(9, 9, 8))
    priorities_question(again)
    assert w.mode() == "week"
    assert w.titles().count(BILLS) == 1, w.titles()
    assert NOTARY in w.titles() and MEDICINE in w.titles()
    from_tasks = [t for t in w.tasks() if t.get("source") == "tasks"]
    assert [t["origin_tasks_id"] for t in from_tasks] == ["tk-1"], from_tasks


def test_seam2_plan_the_week_without_spoken_tasks_plans_the_tasks_of_tasks() -> None:
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    reply = w.plan_week()
    assert reply.text != "Не зрозуміла задачу, скажіть ще раз.", reply
    assert sorted(w.titles()) == sorted([BILLS, PARCEL]), w.titles()
    assert all(t.get("source") == "tasks" for t in w.tasks()), w.tasks()
    assert BILLS in reply.text and PARCEL in reply.text, reply.text
    assert w.mode() == "week"


def test_seam2_the_request_itself_returned_as_a_task_is_dropped() -> None:
    w = add_or_plan(TK_BILLS)
    w.plan_week(task("спланувати тиждень"))
    assert w.titles() == [BILLS], w.titles()


def test_seam2_plan_the_week_with_nothing_anywhere_says_there_are_no_tasks_and_keeps_no_draft() -> None:
    w = add_or_plan()
    reply = w.plan_week()
    assert reply.text == NO_TASKS_THIS_WEEK, reply
    assert reply.question is None and reply.plan is None, reply
    assert w.draft() is None
    only_the_request = add_or_plan()
    reply = only_the_request.plan_week(task("спланувати тиждень"))
    assert reply.text == NO_TASKS_THIS_WEEK, reply
    assert only_the_request.draft() is None


def test_week_mode_with_saved_limits_asks_as_last_time_as_f2() -> None:
    w = add_or_plan(ask_limits=True, ask_priorities=False, use_tasks=False)
    w.seed_limits(WEEKDAYS, "14:00", "18:00")
    reply = w.plan_week(task(NOTARY), text="сплануй тиждень: нотаріус")
    limits_question(reply)
    assert reply.text.startswith(AGAIN_PREFIX), reply.text


# ------------------------------------------------------------------ Seam 3: the route


def test_seam3_route_prompt_has_plan_week_and_no_unconditional_always_new_task() -> None:
    w = add_or_plan()
    w.ai.says(task(NOTARY))
    w.ai.intent = "new_task"
    w.message("додай задачу подзвонити нотаріусу", None)
    assert w.ai.route_prompts, "the route model was not asked"
    prompt = w.ai.route_prompts[-1]
    assert "plan_week" in prompt, prompt
    assert "завжди new_task" not in " ".join(prompt.split()), prompt


def test_seam3_new_task_routes_to_add_and_reads_no_tasks() -> None:
    w = add_or_plan(TK_BILLS)
    w.ai.says(task(NOTARY), task(MEDICINE))
    w.ai.intent = "new_task"
    reply = w.message("додай подзвонити нотаріусу і купити ліки", None)
    no_priorities(reply)
    assert w.tc.list_calls == 0
    assert BILLS not in w.titles()
    assert w.mode() == "add"


def test_seam3_plan_week_routes_to_week_and_reads_tasks() -> None:
    assert "plan_week" in assistant.route_schema(None)["properties"]["intent"]["enum"]
    w = add_or_plan(TK_BILLS)
    w.ai.says(task(NOTARY))
    w.ai.intent = "plan_week"
    reply = w.message("давай планувати тиждень: ще подзвонити нотаріусу", None)
    assert w.tc.list_calls == 1
    assert BILLS in w.titles()
    priorities_question(reply)
    assert w.mode() == "week"


# ------------------------------------------------------------------ invariants


def _never_tasks_nor_priorities(w: AddOrPlan, replies: list[Reply]) -> None:
    for reply in replies:
        no_priorities(reply)
    assert w.tc.list_calls == 0, w.tc.list_calls
    assert BILLS not in w.titles() and PARCEL not in w.titles(), w.titles()


def test_I1_add_never_reads_tasks_nor_asks_what_is_most_important() -> None:
    # Zero spoken tasks (refused), then one, then two appended, then a repeat of one already there.
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    replies = [w.add(text="додай")]
    assert w.tc.list_calls == 0
    replies.append(w.add(at(NOTARY, TUE_10)))
    replies.append(
        w.add(at(MEDICINE, TUE_12), at(SISTER, WED_10), text="і ще ліки і сестра", now=utc(9, 9, 8))
    )
    replies.append(w.add(at(NOTARY, TUE_10), text="і ще нотаріус", now=utc(9, 9, 9)))
    _never_tasks_nor_priorities(w, replies)
    assert w.mode() == "add"
    # Three at once; then «так»; then a new «додай» on a fresh draft.
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    first = w.add(at(NOTARY, TUE_10), at(MEDICINE, TUE_12), at(DOCTOR, WED_10))
    plan_id, fingerprint = shown(first)
    done = w.confirm(plan_id, fingerprint)
    later = w.add(at(SISTER, THU_10), at(MEDICINE, THU_15), text="додай сестру і ліки", now=utc(9, 9, 20))
    _never_tasks_nor_priorities(w, [first, done, later])
    # A «коли?» question on the way (two tasks, neither time nor duration) does not bring them in either.
    w2 = with_when(TK_BILLS)
    asked = w2.add(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    assert asked.question is not None and asked.question.kind == "when", asked
    after = w2.answer_when(
        asked.question.id, when(day="2026-11-10", start_local=TUE_10), "у вівторок о десятій"
    )
    assert after is not None
    replies = [asked, after]
    if after.question is not None and after.question.kind == "when":
        last = w2.answer_when(
            after.question.id, when(day="2026-11-11", start_local=WED_15), "у середу о третій"
        )
        assert last is not None
        replies.append(last)
    _never_tasks_nor_priorities(w2, replies)
    shown(replies[-1])


def test_I2_add_never_asks_the_limits_whether_saved_or_not() -> None:
    # No limits saved, `ask_limits` on: a refused «додай», then «додай», an append, «так», a later «додай».
    w = with_when(TK_BILLS, ask_limits=True)
    replies: list[Reply | None] = [w.add(text="додай")]
    first = w.add(at(NOTARY, TUE_10))
    replies.append(first)
    pending = w.add(at(MEDICINE, TUE_12), text="і ще ліки", now=utc(9, 9, 8))
    replies.append(pending)
    plan_id, fingerprint = shown(pending)
    replies.append(w.confirm(plan_id, fingerprint, now=utc(9, 9, 10)))
    later = w.add(at(SISTER, WED_10), text="додай подзвонити сестрі", now=utc(9, 9, 20))
    assert later.question is not None and later.question.kind == "plan", later
    assert AGAIN_PREFIX not in later.text, later.text
    replies.append(later)
    # A task with no time under `ask_limits`: «коли?», never the limits.
    timeless = w.add(task(DOCTOR, duration_min=None), text="і ще до лікаря", now=utc(9, 9, 21))
    assert timeless.question is not None and timeless.question.kind == "when", timeless
    replies.append(timeless)
    for reply in replies:
        no_duration_nor_limits(reply)
    # Limits saved by an earlier planning, before any «додай»: never asked again.
    # The three «додай» append to one unwritten draft (several-tasks S1), so their titles differ.
    w3 = add_or_plan(TaskItem("tk-9", "щось"), ask_limits=True)
    w3.seed_limits(WEEKDAYS, "14:00", "18:00")
    spoken_by_turn = (
        (at(NOTARY, TUE_15),),
        (at(MEDICINE, WED_15), at(SISTER, THU_15)),
        (at(DOCTOR, THU_10),),
    )
    for n, spoken in enumerate(spoken_by_turn):
        reply = w3.add(*spoken, now=utc(9, 9, 7) + timedelta(minutes=n))
        no_duration_nor_limits(reply)
        assert reply.question is not None and reply.question.kind == "plan", reply
        assert AGAIN_PREFIX not in reply.text
