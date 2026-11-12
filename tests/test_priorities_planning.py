"""Contract tests of the slice priorities in `planning`, `assistant` and `config`:
Seam 1 (the order of questions), Seam 2 (the answer), Seam 3 (more important earlier), I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/priorities.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1): the first free step is 10:15 Berlin = 09:15Z.
Every time below is written by hand in UTC.
"""

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

from mamamemory import planning
from mamamemory.config import load_config
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.priorities_world import (
    Prioritized,
    listed,
    priorities_question,
    prioritized,
    ranked,
    yes_ignoring_crash,
)
from tests.several_tasks_world import (
    DOCTOR,
    GARDEN,
    MEDICINE,
    NOTARY,
    SEEDS,
    SISTER,
    ask_named,
    items,
    task,
)
from tests.test_config import _environ
from tests.test_one_task_planning import NOW, instant, shown
from tests.time_limits_world import NOT_ACTUAL, WEEKDAYS, limits_question, parsed

LATER = NOW + timedelta(seconds=45)
"""Past REQUEST_TIMEOUT_S (30 s): a write left in «записується» is stale."""
AFTERNOONS = parsed(days=WEEKDAYS, start_local="14:00", end_local="18:00")
"""«будні з другої до шостої»: weekdays 14:00–18:00 Berlin; Monday 14:00 Berlin = 13:00Z."""


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def at(reply: Reply, title: str) -> tuple[datetime, datetime]:
    shown_items = items(reply)
    assert title in shown_items, f"{title!r} is not among the plan's items: {shown_items!r}"
    start, end = shown_items[title]
    return instant(start), instant(end)


def unplaced(reply: Reply) -> list[str]:
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    return [str(u["title"]) for u in reply.plan.unplaced]


def three() -> Prioritized:
    """Three free 30-minute tasks, in this order: notary, medicine, sister."""
    return prioritized(task(NOTARY), task(MEDICINE), task(SISTER))


def draft_of(*titles: str, written: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "plan_id": "p-1",
        "state": "asking_duration",
        "tasks": [
            {
                "task_id": f"t{n}",
                "title": title,
                "needs_time": True,
                "duration_min": 30,
                "start_local": None,
                "constraints": {"day": None},
                "order": n,
                "source": "speech",
                "written": {
                    "event_id": f"ev{n}" if title in written else None,
                    "tasks_id": None,
                    "closed": False,
                },
            }
            for n, title in enumerate(titles, start=1)
        ],
    }


# ------------------------------------------------------------------ the switch and next_question


def test_load_config_turns_ask_priorities_on() -> None:
    assert load_config(_environ()).ask_priorities is True


def test_config_without_ask_priorities_keeps_the_path_duration_to_plan() -> None:
    w = prioritized(task(NOTARY), task(MEDICINE), ask_priorities=False)
    reply = w.start()
    assert reply.plan is not None, reply
    assert reply.question is not None and reply.question.kind == "plan"
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))


def test_next_question_asks_priorities_first_for_two_or_more_unwritten_tasks_until_answered() -> None:
    two = draft_of(NOTARY, MEDICINE)
    assert planning.next_question(two, ask_priorities=True) == Question("priorities", "p-1", None)
    assert planning.next_question(two, ask_limits=True, ask_priorities=True) == Question(
        "priorities", "p-1", None
    )
    assert planning.next_question(two) is None
    assert planning.next_question(dict(two, priorities_answered=True), ask_priorities=True) is None
    # Before a missing duration.
    without_duration = copy.deepcopy(two)
    without_duration["tasks"][0]["duration_min"] = None
    assert planning.next_question(without_duration, ask_priorities=True) == Question(
        "priorities", "p-1", None
    )
    # One task, or one unwritten task beside a written one: nothing to compare.
    assert planning.next_question(draft_of(NOTARY), ask_priorities=True) is None
    partly = draft_of(NOTARY, MEDICINE, written=(NOTARY,))
    assert planning.next_question(partly, ask_priorities=True) is None


# ------------------------------------------------------------------ Seam 1: the order of questions


def test_seam1_order_is_priorities_then_durations_in_new_order_then_limits_then_plan() -> None:
    w = prioritized(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None), ask_limits=True)
    first = w.start()
    question = priorities_question(first)
    listed(first.text, NOTARY, MEDICINE)
    assert w.calendar.insert_calls == []
    w.ai.durations = [60, 30]
    second = w.rank(question.id, 2)
    assert second.question == Question("duration", question.id, None), second
    assert second.text == ask_named(MEDICINE)
    third = w.answer(question.id, "годину")
    assert third.question == Question("duration", question.id, None), third
    # Only NOTARY still lacks a duration: the question names it, for one task too (stuck-question Seam).
    assert third.text == ask_named(NOTARY)
    limits_question(w.answer(question.id, "пів години"))
    w.ai.limits = dict(AFTERNOONS)
    reply = w.answer_limits(question.id, "будні з другої до шостої")
    assert at(reply, MEDICINE) == (utc(9, 13, 0), utc(9, 14, 0))
    assert at(reply, NOTARY) == (utc(9, 14, 0), utc(9, 14, 30))
    assert reply.plan is not None
    assert reply.question == Question("plan", reply.plan.plan_id, reply.plan.fingerprint)


def test_seam1_one_task_gets_no_priorities_question_until_a_second_is_added() -> None:
    w = prioritized(task(NOTARY, duration_min=None))
    asked = w.start()
    assert asked.question is not None and asked.question.kind == "duration", asked
    w = prioritized(task(NOTARY))
    reply = w.start()
    assert reply.plan is not None, reply
    assert reply.question is not None and reply.question.kind == "plan"
    w.ai.says(task(MEDICINE))
    again = w.start("і купити ліки", now=NOW + timedelta(minutes=1))
    priorities_question(again)
    listed(again.text, NOTARY, MEDICINE)


def test_seam1_task_added_after_the_answer_asks_again_with_the_new_task_last() -> None:
    # (a) Added to the shown plan.
    w = three()
    question = priorities_question(w.start())
    shown(w.rank(question.id, 3, 1))
    w.ai.says(task(GARDEN))
    again = w.start("і ще полити город", now=NOW + timedelta(minutes=1))
    priorities_question(again)
    listed(again.text, SISTER, NOTARY, MEDICINE, GARDEN)
    # (b) Added while a duration is asked after the answer.
    w = prioritized(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    question = priorities_question(w.start())
    asked = w.rank(question.id, 2)
    assert asked.question is not None and asked.question.kind == "duration", asked
    w.ai.says(task(SISTER))
    again = w.start("і зателефонувати сестрі")
    priorities_question(again)
    listed(again.text, MEDICINE, NOTARY, SISTER)


def test_seam1_open_question_builds_the_priorities_question_from_the_draft_without_the_calendar() -> None:
    w = three()
    first = w.start()
    question = priorities_question(first)

    def calendar() -> GoogleWork:
        raise AssertionError("the priorities question needs no calendar")

    opened = planning.open_question(w.session, calendar=calendar, store=w.store, now=NOW, config=w.config)
    assert opened is not None
    assert opened.reply.question == Question("priorities", question.id, None)
    assert opened.reply.text == first.text
    listed(opened.reply.text, NOTARY, MEDICINE, SISTER)


def test_question_lists_every_unwritten_task_including_untimed_and_named_time() -> None:
    w = prioritized(
        task(NOTARY),
        task(SEEDS, needs_time=False, duration_min=None),
        task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60),
    )
    first = w.start()
    question = priorities_question(first)
    listed(first.text, NOTARY, SEEDS, DOCTOR)
    reply = w.rank(question.id, 3, 2)
    assert w.by_order() == [DOCTOR, SEEDS, NOTARY]
    # The named time and the untimed task keep their places in the plan; their order is not used there.
    assert at(reply, DOCTOR) == (utc(11, 9, 0), utc(11, 10, 0))
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert reply.plan is not None
    assert [u["title"] for u in reply.plan.untimed] == [SEEDS]


# ------------------------------------------------------------------ Seam 2: the answer


def test_seam2_third_then_first_on_three_tasks_gives_order_3_1_2_and_the_plan_in_it() -> None:
    w = three()
    question = priorities_question(w.start())
    before = w.orders()
    reply = w.rank(question.id, 3, 1)
    assert w.by_order() == [SISTER, NOTARY, MEDICINE]
    assert w.open_titles() == [SISTER, NOTARY, MEDICINE], "`tasks` in the draft go in the new order"
    after = w.orders()
    assert after[SISTER] == before[NOTARY]
    assert after[NOTARY] == before[MEDICINE]
    assert after[MEDICINE] == before[SISTER]
    draft = w.draft()
    assert draft is not None and draft.get("priorities_answered") is True
    assert at(reply, SISTER) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, NOTARY) == (utc(9, 9, 45), utc(9, 10, 15))
    assert at(reply, MEDICINE) == (utc(9, 10, 15), utc(9, 10, 45))
    assert reply.plan is not None
    assert reply.question == Question("plan", reply.plan.plan_id, reply.plan.fingerprint)


def test_seam2_all_the_same_keeps_the_order() -> None:
    w = three()
    question = priorities_question(w.start())
    before = w.orders()
    reply = w.rank(question.id, same=True)
    assert w.orders() == before
    draft = w.draft()
    assert draft is not None and draft.get("priorities_answered") is True
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, MEDICINE) == (utc(9, 9, 45), utc(9, 10, 15))
    assert at(reply, SISTER) == (utc(9, 10, 15), utc(9, 10, 45))


def test_seam2_number_outside_the_list_and_a_repeat_are_ignored() -> None:
    w = three()
    question = priorities_question(w.start())
    reply = w.rank(question.id, 2, 5, 2, 0)
    assert w.by_order() == [MEDICINE, NOTARY, SISTER]
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, NOTARY) == (utc(9, 9, 45), utc(9, 10, 15))
    assert at(reply, SISTER) == (utc(9, 10, 15), utc(9, 10, 45))


def test_seam2_nothing_valid_asks_the_same_question_again() -> None:
    w = three()
    first = w.start()
    question = priorities_question(first)
    before = copy.deepcopy(w.draft())
    for numbers in ((), (4,), (0, 7)):
        reply = w.rank(question.id, *numbers)
        assert reply.question == question, reply
        assert reply.plan is None, reply
        assert reply.text == first.text
        assert w.draft() == before
    draft = w.draft()
    assert draft is not None
    assert planning.next_question(draft, ask_priorities=True) == Question("priorities", question.id, None)
    assert w.calendar.insert_calls == []


def test_priorities_answer_while_a_duration_is_asked_returns_the_duration_question() -> None:
    w = prioritized(task(NOTARY, duration_min=None), task(MEDICINE, duration_min=None))
    question = priorities_question(w.start())
    asked = w.rank(question.id, 2)
    assert asked.question == Question("duration", question.id, None)
    before = copy.deepcopy(w.draft())
    reply = w.rank(question.id, 1)
    assert reply.question == Question("duration", question.id, None), reply
    assert reply.text == ask_named(MEDICINE)
    assert w.draft() == before


def test_priorities_answer_after_the_plan_is_shown_changes_nothing() -> None:
    w = three()
    question = priorities_question(w.start())
    shown(w.rank(question.id, 3))
    before = copy.deepcopy(w.draft())
    reply = w.rank(question.id, 1, 2)
    assert reply.question is None or reply.question.kind != "priorities", reply
    assert w.draft() == before
    assert w.calendar.insert_calls == []


def test_priorities_answer_to_an_old_plan_id_is_not_actual() -> None:
    w = prioritized(task(NOTARY))
    old_id, fingerprint = shown(w.start())
    w.confirm(old_id, fingerprint)
    w.ai.says(task(MEDICINE), task(SISTER))
    current = priorities_question(
        w.start("купити ліки і зателефонувати сестрі", now=NOW + timedelta(minutes=5))
    )
    assert current.id != old_id
    before = copy.deepcopy(w.draft())
    reply = w.rank(old_id, 2)
    assert reply.text == NOT_ACTUAL
    assert w.draft() == before


def test_message_reply_to_priorities_goes_to_answer_priorities() -> None:
    w = three()
    question = priorities_question(w.start())
    w.ai.priorities = ranked(3, 1)
    reply = w.message("спершу третє, потім перше", Question("priorities", question.id, None))
    assert at(reply, SISTER) == (utc(9, 9, 15), utc(9, 9, 45))
    assert w.by_order() == [SISTER, NOTARY, MEDICINE]


# ------------------------------------------------------------------ Seam 3: more important earlier


def test_seam3_more_important_stands_earlier_and_the_less_important_does_not_fit() -> None:
    w = prioritized(task(NOTARY), task(MEDICINE))
    reply = w.rank(priorities_question(w.start()).id, 2)
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, NOTARY) == (utc(9, 9, 45), utc(9, 10, 15))
    # Only one 30-minute slot is free: 09:15–09:45Z.
    w = prioritized(task(NOTARY), task(MEDICINE))
    w.calendar.busy(utc(9, 9, 45), utc(20, 0, 0))
    reply = w.rank(priorities_question(w.start()).id, 2)
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert unplaced(reply) == [NOTARY]
    assert reply.plan is not None and NOTARY in reply.text.split("Не вмістилось:", 1)[1]


# ------------------------------------------------------------------ invariants


def test_I1_order_of_unwritten_tasks_is_a_permutation_and_written_keep_theirs() -> None:
    def unwritten_orders(w: Prioritized) -> list[Any]:
        return [t["order"] for t in w.tasks() if not t["written"]["event_id"]]

    def written_orders(w: Prioritized) -> dict[str, Any]:
        return {str(t["task_id"]): t["order"] for t in w.tasks() if t["written"]["event_id"]}

    def holds(w: Prioritized, before_open: list[Any], before_written: dict[str, Any]) -> None:
        after = unwritten_orders(w)
        assert sorted(after) == sorted(before_open), (before_open, after)
        assert len(set(after)) == len(after), f"an `order` repeated: {after!r}"
        assert written_orders(w) == before_written

    answers: list[tuple[int, dict[str, Any]]] = [
        (3, ranked(3, 1)),
        (3, ranked(2, 2, 1)),
        (3, ranked(0, 4, -1)),
        (2, ranked()),
        (3, ranked(same=True)),
        (2, ranked(2, 1, 2, 3)),
        (3, ranked(1, 2, 3)),
        (3, ranked(3, 2, 1)),
    ]
    titles = [NOTARY, MEDICINE, SISTER]
    for size, answer in answers:
        w = prioritized(*(task(t) for t in titles[:size]))
        question = priorities_question(w.start())
        before_open, before_written = unwritten_orders(w), written_orders(w)
        w.ai.priorities = answer
        w.answer_priorities(question.id, "відповідь")
        holds(w, before_open, before_written)

    # A partly written draft: two of three tasks written, then a task added — the question again.
    w = prioritized(task(NOTARY), task(MEDICINE), task(SISTER), honour_409=False)
    question = priorities_question(w.start())
    plan_id, fingerprint = shown(w.rank(question.id, same=True))
    w.calendar.crash_on = 2
    yes_ignoring_crash(w, plan_id, fingerprint)
    shown(w.confirm(plan_id, fingerprint, now=LATER))
    assert len(written_orders(w)) == 2, w.tasks()
    w.ai.says(task(GARDEN))
    again = priorities_question(w.start("і полити город", now=LATER + timedelta(seconds=5)))
    before_open, before_written = unwritten_orders(w), written_orders(w)
    assert len(before_open) == 2
    w.rank(again.id, 2, now=LATER + timedelta(seconds=10))
    holds(w, before_open, before_written)
    assert w.by_order()[0] == GARDEN


def test_I2_more_important_free_task_never_stands_later_nor_goes_unfitted_first() -> None:
    # (a) Empty calendar, the second is the more important.
    w = prioritized(task(NOTARY), task(MEDICINE))
    reply = w.rank(priorities_question(w.start()).id, 2)
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, NOTARY) == (utc(9, 9, 45), utc(9, 10, 15))
    # (b) A busy gap: 09:45–10:15Z; the order is medicine, sister, notary.
    w = three()
    w.calendar.busy(utc(9, 9, 45), utc(9, 10, 15))
    reply = w.rank(priorities_question(w.start()).id, 2, 3)
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, SISTER) == (utc(9, 10, 15), utc(9, 10, 45))
    assert at(reply, NOTARY) == (utc(9, 10, 45), utc(9, 11, 15))
    # (c) Room for one only: the less important does not fit.
    w = prioritized(task(NOTARY), task(MEDICINE))
    w.calendar.busy(utc(9, 9, 45), utc(20, 0, 0))
    reply = w.rank(priorities_question(w.start()).id, 2)
    assert at(reply, MEDICINE) == (utc(9, 9, 15), utc(9, 9, 45))
    assert unplaced(reply) == [NOTARY]
    # (d) Within the limits weekdays 14:00–18:00 Berlin, room for one only: Monday 13:00–13:30Z.
    w = prioritized(task(NOTARY), task(MEDICINE), ask_limits=True)
    w.calendar.busy(utc(9, 13, 30), utc(20, 0, 0))
    limits_question(w.rank(priorities_question(w.start()).id, 2))
    w.ai.limits = dict(AFTERNOONS)
    reply = w.answer_limits(_plan_id(w), "будні з другої до шостої")
    assert at(reply, MEDICINE) == (utc(9, 13, 0), utc(9, 13, 30))
    assert unplaced(reply) == [NOTARY]
    # (e) «все однаково»: the order of collection stands, notary first.
    w = prioritized(task(NOTARY), task(MEDICINE))
    w.calendar.busy(utc(9, 9, 45), utc(20, 0, 0))
    reply = w.rank(priorities_question(w.start()).id, same=True)
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert unplaced(reply) == [MEDICINE]
    # (f) Three tasks, the most important named alone: sister, then notary, medicine; room for two.
    w = three()
    w.calendar.busy(utc(9, 10, 15), utc(20, 0, 0))
    reply = w.rank(priorities_question(w.start()).id, 3)
    assert at(reply, SISTER) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, NOTARY) == (utc(9, 9, 45), utc(9, 10, 15))
    assert unplaced(reply) == [MEDICINE]


def _plan_id(w: Prioritized) -> str:
    draft = w.draft()
    assert draft is not None
    return str(draft["plan_id"])
