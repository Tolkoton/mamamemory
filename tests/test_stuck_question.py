"""Contract tests of the slice stuck-question: Seam 1 (a reply that is no answer is routed), Seam 2 (the old
question), Seam 3 (the duration question names its task), I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/stuck-question.md`, without the code.
Superseded by `.engine/slices/add-simply.md` (2026-11-14): a draft of mode `add` never asks the duration, the
limits or the priorities, so the asking drafts here are drafts of the week (`plan_week`), where they are
asked as before; a task said into a new `add` draft names its time (`TEA_AT`) to be shown at once,
or is asked «коли?».
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). Every time is written by hand.
"""

import copy
from datetime import timedelta

from tests.add_simply_world import ask_when
from tests.several_tasks_world import MEDICINE, NOTARY, SISTER, task
from tests.stuck_question_world import TEA, ask_named, asked, cannot, stuck
from tests.test_one_task_planning import NOW
from tests.time_limits_world import parsed

HOUR = timedelta(hours=1)
NOTHING = parsed()
# Wednesday 11 November 2026, 15:00 Berlin: inside the horizon from NOW and from NOW + 25 h.
TEA_AT = "2026-11-11T15:00"


# ------------------------------------------------------------------ Seam 3: the text


def test_seam3_duration_question_for_one_task_names_it_at_start_and_on_open() -> None:
    w = stuck()
    first = w.plan_week(task(NOTARY, duration_min=None))
    question = asked(first, "duration")
    assert first.text == ask_named(NOTARY)
    opened = w.open(NOW + HOUR)
    assert opened is not None
    assert opened.reply.text == ask_named(NOTARY)
    assert opened.reply.question == question


# ------------------------------------------------------------------ try_answer_*


def test_try_answer_duration_not_a_positive_integer_is_none_and_keeps_the_draft() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    before = copy.deepcopy(w.draft())
    for raw in (None, 0, -30):
        w.ai.raw_durations = [raw]
        assert w.try_duration(question.id, "не знаю") is None, raw
        assert w.draft() == before, raw
    assert w.tc.insert_calls == []


def test_try_answer_duration_with_a_duration_answers_as_f2() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [30]
    reply = w.try_duration(question.id, "пів години")
    assert reply is not None
    assert reply.plan is not None, reply
    assert reply.plan.title == NOTARY
    assert w.find(NOTARY)["duration_min"] == 30


def test_try_answer_priorities_neither_same_nor_a_number_is_none_and_keeps_the_draft() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    before = copy.deepcopy(w.draft())
    w.ai.choose()
    assert w.try_priorities(question.id, "не знаю") is None
    assert w.draft() == before


def test_try_answer_priorities_with_a_number_answers_as_f2() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.choose(order=(2,))
    reply = w.try_priorities(question.id, "друге")
    assert reply is not None
    assert reply.plan is not None, reply
    assert w.by_order() == [MEDICINE, NOTARY]


def test_try_answer_limits_naming_nothing_is_none_and_keeps_the_draft() -> None:
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    before = copy.deepcopy(w.draft())
    w.ai.limits = NOTHING
    assert w.try_limits(question.id, "не знаю") is None
    assert w.draft() == before
    assert w.saved() is None


def test_try_answer_limits_with_limits_answers_as_f2() -> None:
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    w.ai.limits = parsed(days=[0, 1, 2, 3, 4], start_local="14:00", end_local="18:00")
    reply = w.try_limits(question.id, "будні з другої до шостої")
    assert reply is not None
    assert reply.plan is not None, reply
    assert w.saved() == ([0, 1, 2, 3, 4], "14:00", "18:00")


def test_answer_duration_unparsed_still_repeats_the_question() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    reply = w.answer(question.id, "не знаю")
    assert reply.question == question, reply


# ------------------------------------------------------------------ Seam 1: capture


def test_seam1_new_task_under_the_duration_question_starts_a_new_draft_with_only_it() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    reply = w.say("а мені треба чай", question, intent="new_task", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    assert NOTARY not in reply.text, reply
    assert reply.question is None or reply.question.kind != "duration", reply
    assert w.tc.insert_calls == []
    opened = w.open(NOW + timedelta(minutes=1))
    assert opened is None or NOTARY not in opened.reply.text, opened


def test_seam1_plan_week_under_the_duration_question_starts_a_new_draft_with_what_was_said() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    reply = w.say("сплануй тиждень: чай", question, intent="plan_week", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    assert NOTARY not in reply.text, reply
    assert w.tc.insert_calls == []


def test_seam1_half_an_hour_under_the_duration_question_is_the_duration_as_f2() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [30]
    reply = w.say("пів години", question, intent="other")
    assert reply.plan is not None, reply
    assert reply.plan.title == NOTARY
    assert w.titles() == [NOTARY]


def test_seam1_other_under_the_duration_question_is_cannot_and_keeps_the_draft() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    before = copy.deepcopy(w.draft())
    w.ai.raw_durations = [None]
    cannot(w.say("не знаю", question, intent="other"))
    assert w.draft() == before
    opened = w.open(NOW + timedelta(minutes=1))
    assert opened is not None
    assert opened.reply.question == question


def test_seam1_new_task_under_the_priorities_question_starts_a_new_draft_with_only_it() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.choose()
    reply = w.say("а мені треба чай", question, intent="new_task", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    assert reply.question is None or reply.question.kind != "priorities", reply
    assert NOTARY not in reply.text and MEDICINE not in reply.text, reply


def test_seam1_other_under_the_priorities_question_is_cannot_and_keeps_the_draft() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    before = copy.deepcopy(w.draft())
    w.ai.choose()
    cannot(w.say("не знаю", question, intent="other"))
    assert w.draft() == before


def test_seam1_number_under_the_priorities_question_is_the_answer_as_f2() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.choose(order=(2,))
    reply = w.say("друге", question, intent="other")
    assert reply.plan is not None, reply
    assert w.by_order() == [MEDICINE, NOTARY]


def test_seam1_new_task_under_the_limits_question_starts_a_new_draft_with_only_it() -> None:
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    w.ai.limits = NOTHING
    w.say("а мені треба чай", question, intent="new_task", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    assert w.saved() is None


def test_seam1_other_under_the_limits_question_is_cannot_and_keeps_the_draft() -> None:
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    before = copy.deepcopy(w.draft())
    w.ai.limits = NOTHING
    cannot(w.say("не знаю", question, intent="other"))
    assert w.draft() == before
    assert w.saved() is None


def test_seam1_limits_named_under_the_limits_question_are_the_answer_as_f2() -> None:
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    w.ai.limits = parsed(days=[0, 1, 2, 3, 4], start_local="14:00", end_local="18:00")
    reply = w.say("будні з другої до шостої", question, intent="other")
    assert reply.plan is not None, reply
    assert w.saved() == ([0, 1, 2, 3, 4], "14:00", "18:00")


def test_start_with_replace_asking_starts_a_new_draft_over_an_asking_one() -> None:
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.says(task(TEA, start_local=TEA_AT))
    reply = w.start_replacing("мені треба чай у середу о третій", week=False, now=NOW + timedelta(minutes=2))
    assert w.titles() == [TEA]
    assert reply.plan is not None, reply
    assert reply.plan.title == TEA


# ------------------------------------------------------------------ Seam 2: the old question


def test_seam2_asking_draft_older_than_24h_is_not_shown_and_nothing_is_written() -> None:
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    before = copy.deepcopy(w.draft())
    assert w.open(NOW + timedelta(hours=24, minutes=1)) is None
    assert w.open(NOW + timedelta(days=3)) is None
    assert w.draft() == before


def test_seam2_asking_draft_without_asked_at_and_horizon_end_is_not_shown() -> None:
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.forget_asked_at()
    assert "horizon_end" not in (w.draft() or {})
    assert w.open(NOW + timedelta(minutes=1)) is None


def test_seam2_asking_draft_without_asked_at_is_aged_from_horizon_end_minus_the_horizon() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.forget_asked_at()
    # First shown at NOW: horizon_end = NOW + 7 days.
    w.set_field("horizon_end", "2026-11-16T09:07:00+00:00")
    young = w.open(NOW + timedelta(hours=2))
    assert young is not None
    assert young.reply.question == question
    assert w.open(NOW + timedelta(hours=25)) is None


def test_seam2_asking_draft_younger_than_24h_is_shown() -> None:
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    opened = w.open(NOW + timedelta(hours=23, minutes=59))
    assert opened is not None
    assert opened.reply.question == question
    assert opened.reply.text == ask_named(NOTARY)


def test_seam2_start_after_24h_begins_a_new_draft_without_the_old_task() -> None:
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.says(task(TEA, start_local=TEA_AT))
    reply = w.start_in("мені треба чай у середу о третій", week=False, now=NOW + timedelta(hours=25))
    assert w.titles() == [TEA]
    assert reply.plan is not None, reply
    assert reply.plan.title == TEA
    assert NOTARY not in reply.text


def test_seam2_start_before_24h_appends_as_f2() -> None:
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.says(task(TEA))
    w.start_in("і ще чай", week=False, now=NOW + timedelta(hours=1))
    assert w.titles() == [NOTARY, TEA]


# ------------------------------------------------------------------ invariants


def test_I1_a_phrase_that_is_no_answer_never_gives_the_same_question_again() -> None:
    # Duration: nothing, zero, a negative number — each with `other`.
    for raw in (None, 0, -15):
        w = stuck()
        question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
        w.ai.raw_durations = [raw]
        reply = w.say("не знаю", question, intent="other")
        cannot(reply)
        assert reply.question != question, raw

    # Priorities: neither `same` nor a number.
    w = stuck()
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.choose()
    cannot(w.say("не знаю", question, intent="other"))

    # Limits: nothing named and not «так».
    w = stuck(ask_limits=True)
    question = asked(w.plan_week(task(NOTARY)), "limits")
    w.ai.limits = NOTHING
    cannot(w.say("не знаю", question, intent="other"))

    # A lawful answer, then a new task under the next duration question: the draft is not appended to,
    # and the question about the first unanswered task does not come back.
    w = stuck(ask_priorities=False)
    first = asked(w.plan_week(task(NOTARY, duration_min=None), task(SISTER, duration_min=None)), "duration")
    w.ai.raw_durations = [30]
    second = w.say("пів години", first, intent="other")
    question = asked(second, "duration")
    assert second.text == ask_named(SISTER)
    w.ai.raw_durations = [None]
    reply = w.say("а мені треба чай", question, intent="new_task", spoken=(task(TEA),))
    assert w.titles() == [TEA]
    assert reply.question is None or reply.question.kind != "duration", reply
    assert SISTER not in reply.text and NOTARY not in reply.text, reply

    # A lawful answer after a refused one is still taken.
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    cannot(w.say("не знаю", question, intent="other"))
    w.ai.raw_durations = [30]
    after = w.say("пів години", question, intent="other")
    assert after.plan is not None, after
    assert after.plan.title == NOTARY


def test_I2_a_question_older_than_24h_is_never_shown_nor_captures_a_message() -> None:
    # Shown again at 23h does not make it younger: at 25h it is gone.
    w = stuck()
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    again = w.open(NOW + timedelta(hours=23))
    assert again is not None and again.reply.question == question
    assert w.open(NOW + timedelta(hours=25)) is None
    assert w.open(NOW + timedelta(days=30)) is None

    # A message without reply_to after 24h starts a new draft; the new draft's question is then shown
    # (a new `add` draft: «коли?», add-simply).
    w.ai.raw_durations = []
    reply = w.say(
        "мені треба чай", None, intent="new_task", spoken=(task(TEA, duration_min=None),), now=NOW + 25 * HOUR
    )
    assert w.titles() == [TEA]
    assert ask_when(TEA) in reply.text, reply
    assert NOTARY not in reply.text, reply
    fresh = w.open(NOW + 25 * HOUR + timedelta(minutes=1))
    assert fresh is not None
    assert ask_when(TEA) in fresh.reply.text, fresh
    assert fresh.reply.question != question

    # An old priorities question: not shown, and a new start does not append to it.
    w = stuck()
    asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    assert w.open(NOW + timedelta(hours=24, minutes=1)) is None
    w.ai.says(task(TEA))
    w.start_in("мені треба чай", week=False, now=NOW + 30 * HOUR)
    assert w.titles() == [TEA]

    # An old limits question: not shown.
    w = stuck(ask_limits=True)
    asked(w.plan_week(task(NOTARY)), "limits")
    assert w.open(NOW + timedelta(hours=48)) is None

    # A pre-F3 S3 asking draft (neither field) right after it was written: not shown.
    w = stuck()
    asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    w.forget_asked_at()
    assert w.open(NOW) is None
