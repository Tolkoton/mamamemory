"""Contract tests of the slice add-or-plan: «додати» against «спланувати» in `planning.start` and the route in
`assistant` — Seam 1, Seam 2, Seam 3, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/add-or-plan.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1): the first free step is 10:15 Berlin = 09:15Z.
Limits «weekdays 14:00–18:00» put a task at 14:00 Berlin = 13:00Z at the earliest, 18:00 Berlin = 17:00Z at
the latest. Every time below is written by hand in UTC.
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
from tests.google_tasks_world import BILLS, PARCEL
from tests.priorities_world import listed, priorities_question
from tests.several_tasks_world import DOCTOR, MEDICINE, NOTARY, SISTER, items, task
from tests.test_one_task_planning import instant, shown
from tests.time_limits_world import (
    AGAIN_PREFIX,
    ASK_LIMITS_FIRST,
    WEEKDAYS,
    limits_question,
    parsed,
    plain,
)

AFTERNOONS = parsed(days=WEEKDAYS, start_local="14:00", end_local="18:00")


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def within_afternoons(reply: Reply) -> None:
    """Every timed item of the plan lies inside Monday 14:00–18:00 Berlin (13:00Z–17:00Z)."""
    found = items(reply)
    assert found, f"expected timed items, got {reply!r}"
    for title, (start, end) in found.items():
        assert utc(9, 13) <= instant(start) and instant(end) <= utc(9, 17), (title, start, end)


# ------------------------------------------------------------------ Seam 1: «додати»


def test_seam1_add_reads_no_tasks_asks_no_priorities_and_shows_the_plan_at_once() -> None:
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    reply = w.add(task(NOTARY), task(MEDICINE))
    no_priorities(reply)
    assert w.tc.list_calls == 0
    assert set(items(reply)) == {NOTARY, MEDICINE}, reply
    assert BILLS not in reply.text and PARCEL not in reply.text, reply.text
    assert w.titles() == [NOTARY, MEDICINE]
    assert w.mode() == "add"


def test_seam1_add_without_a_duration_asks_the_duration_not_the_priorities() -> None:
    w = add_or_plan(TK_BILLS)
    reply = w.add(task(NOTARY, duration_min=None), task(MEDICINE))
    no_priorities(reply)
    assert reply.question is not None and reply.question.kind == "duration", reply
    assert reply.plan is None
    assert w.tc.list_calls == 0


def test_seam1_add_appended_to_an_unwritten_add_draft_reads_no_tasks() -> None:
    w = add_or_plan(TK_BILLS)
    shown(w.add(task(NOTARY)))
    again = w.add(task(MEDICINE), text="і ще купити ліки", now=utc(9, 9, 8))
    no_priorities(again)
    assert w.tc.list_calls == 0
    assert w.titles() == [NOTARY, MEDICINE]
    assert w.mode() == "add"
    assert set(items(again)) == {NOTARY, MEDICINE}, again


def test_seam1_add_with_saved_limits_applies_them_without_a_question() -> None:
    w = add_or_plan(TK_BILLS, ask_limits=True)
    w.seed_limits(WEEKDAYS, "14:00", "18:00")
    reply = w.add(task(NOTARY))
    assert AGAIN_PREFIX not in reply.text, reply.text
    assert reply.question is not None and reply.question.kind == "plan", reply
    start, end = items(reply)[NOTARY]
    assert (instant(start), instant(end)) == (utc(9, 13), utc(9, 13, 30))
    draft = w.draft()
    assert draft is not None and draft.get("limits_answered") is True, draft


def test_seam1_add_without_saved_limits_asks_the_first_limits_question_once() -> None:
    w = add_or_plan(TK_BILLS, ask_limits=True)
    reply = w.add(task(NOTARY), task(MEDICINE))
    question = limits_question(reply)
    no_priorities(reply)
    assert plain(reply.text) == plain(ASK_LIMITS_FIRST), reply.text
    w.ai.limits = dict(AFTERNOONS)
    plan = w.answer_limits(question.id, "будні з другої до шостої")
    shown(plan)
    within_afternoons(plan)
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
    shown(w.add(task(NOTARY)))
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
    replies.append(w.add(task(NOTARY)))
    replies.append(w.add(task(MEDICINE), task(SISTER), text="і ще ліки і сестра", now=utc(9, 9, 8)))
    replies.append(w.add(task(NOTARY), text="і ще нотаріус", now=utc(9, 9, 9)))
    _never_tasks_nor_priorities(w, replies)
    assert w.mode() == "add"
    # Three at once; then «так»; then a new «додай» on a fresh draft.
    w = add_or_plan(TK_BILLS, TK_PARCEL)
    first = w.add(task(NOTARY), task(MEDICINE), task(DOCTOR))
    plan_id, fingerprint = shown(first)
    done = w.confirm(plan_id, fingerprint)
    later = w.add(task(SISTER), task(MEDICINE), text="додай сестру і ліки", now=utc(9, 9, 20))
    _never_tasks_nor_priorities(w, [first, done, later])
    # A duration question on the way does not bring the priorities in either.
    w = add_or_plan(TK_BILLS)
    asked = w.add(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    assert asked.question is not None and asked.question.kind == "duration", asked
    w.ai.durations = [30, 30]
    after = w.answer(asked.question.id, "пів години")
    replies = [asked, after]
    if after.question is not None and after.question.kind == "duration":
        replies.append(w.answer(after.question.id, "пів години"))
    _never_tasks_nor_priorities(w, replies)
    shown(replies[-1])


def test_I2_add_asks_limits_only_while_none_are_saved_and_never_places_outside_them() -> None:
    w = add_or_plan(TK_BILLS, ask_limits=True)
    # A refused «додай» first: nothing saved, nothing asked about limits beyond the first question later.
    w.add(text="додай")
    first = w.add(task(NOTARY))
    question = limits_question(first)
    assert plain(first.text) == plain(ASK_LIMITS_FIRST), first.text
    # Appended before the answer: still no plan outside unconfirmed limits.
    pending = w.add(task(MEDICINE), text="і ще ліки", now=utc(9, 9, 8))
    limits_question(pending)
    w.ai.limits = dict(AFTERNOONS)
    plan = w.answer_limits(question.id, "будні з другої до шостої", now=utc(9, 9, 9))
    within_afternoons(plan)
    plan_id, fingerprint = shown(plan)
    w.confirm(plan_id, fingerprint, now=utc(9, 9, 10))
    # Saved now: every later «додай» is planned inside them, with no question about limits.
    later = w.add(task(SISTER), text="додай подзвонити сестрі", now=utc(9, 9, 20))
    assert later.question is not None and later.question.kind == "plan", later
    assert AGAIN_PREFIX not in later.text, later.text
    within_afternoons(later)
    appended = w.add(task(DOCTOR), text="і ще до лікаря", now=utc(9, 9, 21))
    assert appended.question is not None and appended.question.kind == "plan", appended
    within_afternoons(appended)
    assert set(items(appended)) == {SISTER, DOCTOR}, appended
    # Limits saved by an earlier planning, before any «додай»: never asked, always applied.
    # The three «додай» append to one unwritten draft (several-tasks S1), so their titles differ.
    w = add_or_plan(TaskItem("tk-9", "щось"), ask_limits=True)
    w.seed_limits(WEEKDAYS, "14:00", "18:00")
    for n, spoken in enumerate(((task(NOTARY),), (task(MEDICINE), task(SISTER)), (task(DOCTOR),))):
        reply = w.add(*spoken, now=utc(9, 9, 7) + timedelta(minutes=n))
        assert reply.question is not None and reply.question.kind == "plan", reply
        assert AGAIN_PREFIX not in reply.text
        within_afternoons(reply)
