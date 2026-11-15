"""Contract tests of the slice plans-not-questions: Seam 1 (a reply that is no answer), Seam 2 (the week draft
closed under «які плани»), Seam 3 (Google Tasks in the schedule), I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/plans-not-questions.md`, no code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). Every expected line is written by hand.

Superseded in part by `.engine/slices/calm-open.md`: a task reaches «Задачі без часу:» only with `due` in
the period, so the tasks shown below are due today (Monday 9 November, Berlin).

Superseded in part by `.engine/slices/add-simply.md`: a draft of `mode: "add"` asks neither the duration nor
the limits, so the limits question is reached through the week plan, and the «додай задачу» draft is kept
under its «коли?» question.
"""

import copy
from datetime import date, timedelta

import requests

from mamamemory import planning
from mamamemory.integrations.google_work import TaskItem
from tests.add_or_plan_world import TK_BILLS, TK_PARCEL
from tests.add_simply_world import AddSimply, WhenAI, when
from tests.google_tasks_world import BILLS, PARCEL
from tests.plans_not_questions_world import (
    DOCTOR_LINE,
    NOTHING_TODAY,
    TASKS_HEADER,
    AgendaTasksCalendar,
    TasksAgenda,
    WriteLogStore,
    doctor_today,
    lines,
    plans,
    seed_draft,
    show_with,
)
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.stuck_question_world import asked, cannot
from tests.test_one_task_planning import NOW, make_session
from tests.time_limits_world import RecordingStore, parsed

PLANS = "які в нас плани?"
MINUTE = timedelta(minutes=1)
WEEKDAYS = [0, 1, 2, 3, 4]
LIMITS_DOC = {"days": [0, 1, 2, 3, 4], "start_local": "09:00", "end_local": "18:00"}
TODAY = date(2026, 11, 9)
"""The local date of `NOW` in Berlin: the day the period «today» covers."""
TK_BILLS_TODAY = TaskItem(TK_BILLS.id, BILLS, TODAY)
TK_PARCEL_TODAY = TaskItem(TK_PARCEL.id, PARCEL, TODAY)


def doctor_event() -> TasksAgenda:
    return TasksAgenda(doctor_today())


# ------------------------------------------------------------------ the schemas


def test_schemas_require_a_boolean_is_answer() -> None:
    for schema in (planning.PRIORITIES_SCHEMA, planning.LIMITS_SCHEMA):
        assert schema["properties"]["is_answer"]["type"] == "boolean", schema
        assert "is_answer" in schema["required"], schema


# ------------------------------------------------------------------ Seam 1: no answer


def test_seam1_is_answer_false_with_same_true_is_none_and_keeps_the_draft() -> None:
    w = plans(use_tasks=False)
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    before = copy.deepcopy(w.draft())
    w.ai.priorities = {"is_answer": False, "same": True, "order": [], "timed": []}
    assert w.try_priorities(question.id, PLANS) is None
    assert w.draft() == before


def test_seam1_is_answer_true_with_numbers_answers_as_before() -> None:
    w = plans(use_tasks=False)
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.priorities = {"is_answer": True, "same": False, "order": [2], "timed": []}
    reply = w.try_priorities(question.id, "друге")
    assert reply is not None
    assert reply.plan is not None, reply
    assert w.by_order() == [MEDICINE, NOTARY]


def test_seam1_is_answer_missing_answers_as_before() -> None:
    w = plans(use_tasks=False)
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.priorities = {"same": False, "order": [2], "timed": []}
    reply = w.try_priorities(question.id, "друге")
    assert reply is not None
    assert reply.plan is not None, reply
    assert w.by_order() == [MEDICINE, NOTARY]


def test_seam1_limits_is_answer_true_saves_the_limits_as_before() -> None:
    # Superseded by add-simply: a draft of `mode: "add"` never asks the limits; the week plan asks them.
    w = plans(ask_limits=True, ask_priorities=False, use_tasks=False)
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "limits")
    w.ai.limits = dict(parsed(days=WEEKDAYS, start_local="14:00", end_local="18:00"), is_answer=True)
    reply = w.try_limits(question.id, "будні з другої до шостої")
    assert reply is not None
    assert reply.plan is not None, reply
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")


def test_seam1_other_under_priorities_with_is_answer_false_is_cannot_and_keeps_the_draft() -> None:
    w = plans(use_tasks=False)
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    before = copy.deepcopy(w.draft())
    w.ai.priorities = {"is_answer": False, "same": True, "order": [], "timed": []}
    cannot(w.say("що там по роботі", question, intent="other"))
    assert w.draft() == before


# ------------------------------------------------------------------ Seam 2: the week draft closed


def test_seam2_plans_under_priorities_of_the_week_shows_calendar_and_tasks_and_drops_the_draft() -> None:
    w = plans(TK_BILLS_TODAY, TK_PARCEL_TODAY, agenda=(doctor_today(),))
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.priorities = {"is_answer": False, "same": True, "order": [], "timed": []}
    reply = w.say(PLANS, question, intent="schedule")
    found = lines(reply)
    assert DOCTOR_LINE in found, reply.text
    assert TASKS_HEADER in found, reply.text
    assert f"• {BILLS}" in found and f"• {PARCEL}" in found, reply.text
    assert reply.question is None, reply
    assert w.draft() is None
    opened = w.open(NOW + MINUTE)
    assert opened is None or opened.reply.question is None or opened.reply.question.kind != "priorities"
    assert w.google_writes() == (0, 0, 0)


def test_seam2_plans_under_limits_of_the_week_drops_the_draft() -> None:
    w = plans(ask_limits=True, ask_priorities=False, use_tasks=False, agenda=(doctor_today(),))
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "limits")
    w.ai.limits = dict(parsed(), is_answer=False)
    reply = w.say(PLANS, question, intent="schedule")
    assert DOCTOR_LINE in lines(reply), reply.text
    assert w.draft() is None
    assert w.saved() is None
    opened = w.open(NOW + MINUTE)
    assert opened is None or opened.reply.question is None or opened.reply.question.kind != "limits"


def test_seam2_plans_under_the_duration_question_keeps_the_draft() -> None:
    w = plans(ask_priorities=False, use_tasks=False, agenda=(doctor_today(),))
    question = asked(w.plan_week(task(NOTARY, duration_min=None)), "duration")
    before = copy.deepcopy(w.draft())
    w.ai.raw_durations = [None]
    w.say(PLANS, question, intent="schedule")
    assert w.draft() == before


def test_seam2_plans_under_the_when_question_of_add_a_task_keeps_the_draft() -> None:
    # Superseded by add-simply: «додай задачу» asks no limits any more, only «коли?» for a task with no time;
    # «які плани» under it (not an answer, routed `schedule`) leaves the «додай задачу» draft as it is.
    w = AddSimply(
        WhenAI(),
        AgendaTasksCalendar(agenda=(doctor_today(),)),
        RecordingStore(),
        True,
        True,
        False,
    )
    question = asked(w.add(task(NOTARY, duration_min=None)), "when")
    before = copy.deepcopy(w.draft())
    w.ai.when = when(is_answer=False)
    w.say(PLANS, question, intent="schedule")
    assert w.draft() == before


def test_seam2_plans_under_an_old_priorities_question_keeps_a_shown_plan() -> None:
    w = plans(use_tasks=False, agenda=(doctor_today(),))
    question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.priorities = {"is_answer": True, "same": False, "order": [2], "timed": []}
    shown = w.try_priorities(question.id, "друге")
    assert shown is not None and shown.plan is not None, shown
    before = copy.deepcopy(w.draft())
    w.ai.priorities = {"is_answer": False, "same": True, "order": [], "timed": []}
    w.say(PLANS, question, intent="schedule")
    assert w.draft() == before


# ------------------------------------------------------------------ Seam 3: tasks in the schedule


def test_seam3_events_then_the_open_tasks_and_nothing_written() -> None:
    calendar = doctor_event()
    calendar.tasks = [TK_BILLS_TODAY, TK_PARCEL_TODAY]
    reply = show_with("які плани на сьогодні?", calendar)
    assert lines(reply) == ["На сьогодні:", DOCTOR_LINE, TASKS_HEADER, f"• {BILLS}", f"• {PARCEL}"]
    assert calendar.writes() == []


def test_seam3_tasks_come_in_the_order_of_the_list() -> None:
    calendar = doctor_event()
    calendar.tasks = [
        TaskItem("tk-3", "я купити хліб", TODAY),
        TK_BILLS,
        TK_PARCEL_TODAY,
        TaskItem("tk-4", "аптека", TODAY),
    ]
    reply = show_with("які плани на сьогодні?", calendar)
    assert lines(reply)[2:] == [TASKS_HEADER, "• я купити хліб", f"• {PARCEL}", "• аптека"]


def test_seam3_only_tasks_says_nothing_in_calendar_then_the_tasks() -> None:
    calendar = TasksAgenda(tasks=(TK_BILLS_TODAY,))
    reply = show_with("які плани на сьогодні?", calendar)
    assert lines(reply) == [NOTHING_TODAY, TASKS_HEADER, f"• {BILLS}"]


def test_seam3_neither_events_nor_tasks_is_as_before() -> None:
    reply = show_with("які плани на сьогодні?", TasksAgenda())
    assert lines(reply) == [NOTHING_TODAY]


def test_seam3_use_tasks_false_shows_no_tasks_and_does_not_read_them() -> None:
    calendar = doctor_event()
    calendar.tasks = [TK_BILLS]
    reply = show_with("які плани на сьогодні?", calendar, use_tasks=False)
    assert lines(reply) == ["На сьогодні:", DOCTOR_LINE]
    assert "list_open_tasks" not in calendar.log, calendar.log


def test_seam3_a_tasks_error_leaves_the_events_without_a_tasks_section() -> None:
    for error in (requests.exceptions.HTTPError("fake: 503"), RuntimeError("fake"), KeyError("items")):
        calendar = doctor_event()
        calendar.fail = error
        reply = show_with("які плани на сьогодні?", calendar)
        assert "list_open_tasks" in calendar.log, (error, calendar.log)
        assert lines(reply) == ["На сьогодні:", DOCTOR_LINE], (error, reply.text)


# ------------------------------------------------------------------ invariants


def test_I1_is_answer_false_never_changes_the_draft_nor_the_limits() -> None:
    priorities_answers = [
        {"is_answer": False, "same": True, "order": [], "timed": []},
        {"is_answer": False, "same": False, "order": [2, 1], "timed": [1]},
        {"is_answer": False, "same": True, "order": [1], "timed": []},
        {"is_answer": False, "same": False, "order": [], "timed": []},
    ]
    for phrase in (PLANS, "друге", "все однаково", ""):
        for answer in priorities_answers:
            w = plans(use_tasks=False)
            w.seed_limits(WEEKDAYS, "09:00", "18:00")
            question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
            before = copy.deepcopy(w.draft())
            w.ai.priorities = dict(answer)
            assert w.try_priorities(question.id, phrase) is None, (phrase, answer)
            assert w.draft() == before, (phrase, answer)
            assert w.saved() == (WEEKDAYS, "09:00", "18:00")
            assert w.store.limits_writes == []
    limits_answers = [
        dict(parsed(), is_answer=False),
        dict(parsed(same_as_last=True), is_answer=False),
        dict(parsed(days=[5, 6], start_local="10:00", end_local="12:00"), is_answer=False),
        dict(parsed(same_as_last=True, days=[0], start_local="08:00", end_local="09:00"), is_answer=False),
    ]
    for phrase in (PLANS, "як минулого разу", "будні з дев'ятої до шостої", ""):
        for answer in limits_answers:
            for saved in (False, True):
                w = plans(ask_limits=True, ask_priorities=False, use_tasks=False)
                if saved:
                    w.seed_limits(WEEKDAYS, "09:00", "18:00")
                question = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "limits")
                before = copy.deepcopy(w.draft())
                w.ai.limits = dict(answer)
                assert w.try_limits(question.id, phrase) is None, (phrase, answer, saved)
                assert w.draft() == before, (phrase, answer, saved)
                assert w.saved() == ((WEEKDAYS, "09:00", "18:00") if saved else None)
                assert w.store.limits_writes == []


def test_I2_dismiss_asking_deletes_only_an_asking_week_draft_and_writes_nothing_else() -> None:
    session = make_session()
    states = ("asking_duration", "shown", "writing", "written")
    for state in states:
        for mode in ("week", "add", None):
            store = WriteLogStore()
            draft = seed_draft(store, state=state, mode=mode)
            store.set(session.account_id, planning.LIMITS_PATH, LIMITS_DOC)
            store.writes.clear()
            planning.dismiss_asking(session, store=store)
            assert store.get(session.account_id, planning.LIMITS_PATH) == LIMITS_DOC
            if state == "asking_duration" and mode == "week":
                assert store.get(session.account_id, planning.DRAFT_PATH) is None
                assert store.writes == [("delete", planning.DRAFT_PATH)], store.writes
                planning.dismiss_asking(session, store=store)
                assert store.writes == [("delete", planning.DRAFT_PATH)], store.writes
            else:
                assert store.get(session.account_id, planning.DRAFT_PATH) == draft, (state, mode)
                assert store.writes == [], (state, mode, store.writes)
    empty = WriteLogStore()
    planning.dismiss_asking(session, store=empty)
    planning.dismiss_asking(session, store=empty)
    assert empty.writes == []
