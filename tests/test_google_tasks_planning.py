"""Contract tests of the slice google-tasks in `planning`, `config` and `http`: candidates from Tasks, the
choice «на час», writing in two steps, Seam 2, Seam 3, I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/google-tasks.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1): the first free step is 10:15 Berlin = 09:15Z.
Every time below is written by hand in UTC.
"""

import contextlib
import copy
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from mamamemory import access
from mamamemory.access import Session
from mamamemory.config import SCOPES, load_config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from mamamemory.replies import Question, Reply
from tests.google_tasks_world import (
    BILLS,
    CHOOSE_TIMED,
    PARCEL,
    TO_TASKS,
    TasksCalendar,
    WithTasks,
    number_of,
    with_tasks,
)
from tests.priorities_world import listed, priorities_question
from tests.several_tasks_world import (
    DOCTOR,
    GARDEN,
    MEDICINE,
    NOTARY,
    PARTLY_WRITTEN,
    SEEDS,
    SISTER,
    TASKS_LATER,
    WRITTEN,
    ask_named,
    items,
    task,
)
from tests.test_config import _environ
from tests.test_one_task_google_work import Transport
from tests.test_one_task_http import FAILED, SUB, Clock, FakeGoogle
from tests.test_one_task_planning import NOW, instant, shown

LATER = NOW + timedelta(seconds=45)
"""Past REQUEST_TIMEOUT_S (30 s): a write left in «записується» is stale."""
TK_BILLS = TaskItem("tk-1", BILLS)
TK_PARCEL = TaskItem("tk-2", PARCEL)


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def at(reply: Reply, title: str) -> tuple[datetime, datetime]:
    shown_items = items(reply)
    assert title in shown_items, f"{title!r} is not among the plan's items: {shown_items!r}"
    start, end = shown_items[title]
    return instant(start), instant(end)


def two_and_bills(*more: TaskItem) -> WithTasks:
    """Two spoken 30-minute tasks (notary, medicine) and the open Tasks task «оплатити світло»."""
    return with_tasks(task(NOTARY), task(MEDICINE), open_tasks=(TK_BILLS, *more))


def bills_timed(w: WithTasks, duration: str = "годину", now: datetime = NOW) -> tuple[str, str]:
    """Start, choose «оплатити світло» on time (order untouched), answer its duration (60 min).

    Returns the shown plan."""
    first = w.start(now=now)
    question = priorities_question(first)
    w.ai.durations = [60]
    asked = w.pick(question.id, timed=(number_of(first.text, BILLS),), now=now)
    assert asked.question == Question("duration", question.id, None), asked
    return shown(w.answer(question.id, duration, now=now))


def crash_before_closing(w: WithTasks) -> tuple[str, str]:
    """Show the plan with «оплатити світло» on time; «так» writes the events, then the closing fails."""
    plan_id, fingerprint = bills_timed(w)
    w.tc.fail_complete = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert w.tc.event_titles() == sorted([BILLS, MEDICINE, NOTARY]), w.tc.event_titles()
    assert w.tc.completed == []
    return plan_id, fingerprint


def yes_to_the_rest(w: WithTasks, reply: Reply, now: datetime) -> Reply:
    if reply.plan is None:
        return reply
    return w.confirm(reply.plan.plan_id, reply.plan.fingerprint, now=now)


# ------------------------------------------------------------------ the switch


def test_load_config_turns_use_tasks_on() -> None:
    assert load_config(_environ()).use_tasks is True


def test_without_use_tasks_tasks_are_neither_read_nor_written() -> None:
    w = with_tasks(
        task(NOTARY),
        task(SEEDS, needs_time=False, duration_min=None),
        open_tasks=(TK_BILLS,),
        use_tasks=False,
        ask_priorities=False,
    )
    reply = w.start()
    plan_id, fingerprint = shown(reply)
    assert BILLS not in reply.text
    done = w.confirm(plan_id, fingerprint)
    assert done.text.startswith(WRITTEN)
    assert TASKS_LATER in done.text
    assert w.tc.list_calls == 0
    assert w.tc.inserted == [] and w.tc.insert_task_calls == 0
    assert w.tc.complete_calls == []


# ------------------------------------------------------------------ candidates


def test_new_draft_adds_open_tasks_after_spoken_ones_as_untimed_tasks_from_tasks() -> None:
    w = two_and_bills()
    first = w.start()
    priorities_question(first)
    listed(first.text, NOTARY, MEDICINE, BILLS)
    titles = [t["title"] for t in w.tasks()]
    assert titles == [NOTARY, MEDICINE, BILLS], titles
    bills = w.find(BILLS)
    assert bills["source"] == "tasks"
    assert bills["origin_tasks_id"] == "tk-1"
    assert bills["needs_time"] is False
    assert bills["written"]["tasks_id"] is None
    assert bills["written"]["event_id"] is None
    assert [w.find(t)["source"] for t in (NOTARY, MEDICINE)] == ["speech", "speech"]
    assert w.tc.list_calls == 1
    assert w.tc.inserted == [] and w.tc.complete_calls == [] and w.tc.created == []


def test_the_same_origin_tasks_id_is_added_only_once() -> None:
    w = two_and_bills(TK_BILLS)
    w.start()
    from_tasks = [t for t in w.tasks() if t.get("source") == "tasks"]
    assert [t["origin_tasks_id"] for t in from_tasks] == ["tk-1"], from_tasks


def test_start_that_appends_does_not_read_tasks_again() -> None:
    w = two_and_bills()
    priorities_question(w.start())
    w.ai.says(task(SISTER))
    again = w.start("і зателефонувати сестрі", now=NOW + timedelta(minutes=1))
    priorities_question(again)
    assert w.tc.list_calls == 1
    assert [t["title"] for t in w.tasks()].count(BILLS) == 1
    assert again.text.count(BILLS) == 1, again.text


def test_seam3_question_lists_open_tasks_with_the_timed_line_and_no_subtasks() -> None:
    def route(request: Any) -> tuple[int, dict[str, Any]]:
        return 200, {
            "items": [
                {"id": "tk-1", "title": BILLS, "status": "needsAction"},
                {"id": "tk-3", "title": "купити лампочку", "status": "needsAction", "parent": "tk-1"},
            ]
        }

    transport = Transport(route)
    session = AuthorizedSession(Credentials("at-test"))
    session.mount("https://tasks.googleapis.com/", transport)
    session.mount("https://www.googleapis.com/", transport)
    real = GoogleWork(session, call_timeout_s=10, deadline=NOW + timedelta(seconds=60), now=lambda: NOW)
    w = with_tasks(task(NOTARY), task(MEDICINE))
    w.tc.list_delegate = real.list_open_tasks
    first = w.start()
    priorities_question(first)
    listed(first.text, NOTARY, MEDICINE, BILLS)
    assert CHOOSE_TIMED in first.text
    assert "купити лампочку" not in first.text
    # No open task in Tasks: the question has no such line.
    w = with_tasks(task(NOTARY), task(MEDICINE))
    plain = w.start()
    listed(plain.text, NOTARY, MEDICINE)
    assert CHOOSE_TIMED not in plain.text


# ------------------------------------------------------------------ Seam 3: the choice «на час»


def test_seam3_only_timed_choice_asks_its_duration_then_makes_an_event_and_closes_it() -> None:
    w = two_and_bills()
    first = w.start()
    question = priorities_question(first)
    before = w.orders()
    asked = w.pick(question.id, timed=(number_of(first.text, BILLS),))
    assert asked.question == Question("duration", question.id, None), asked
    assert asked.text == ask_named(BILLS), "the duration question names the task"
    draft = w.draft()
    assert draft is not None and draft.get("priorities_answered") is True
    assert w.find(BILLS)["needs_time"] is True
    assert w.orders() == before, "`timed` does not change the order"
    w.ai.durations = [60]
    reply = w.answer(question.id, "годину")
    assert at(reply, NOTARY) == (utc(9, 9, 15), utc(9, 9, 45))
    assert at(reply, MEDICINE) == (utc(9, 9, 45), utc(9, 10, 15))
    assert at(reply, BILLS) == (utc(9, 10, 15), utc(9, 11, 15))
    plan_id, fingerprint = shown(reply)
    done = w.confirm(plan_id, fingerprint)
    assert done.text.startswith(WRITTEN)
    assert TASKS_LATER not in done.text
    assert sorted((e.title, e.start, e.end) for e in w.tc.created) == sorted(
        [
            (NOTARY, utc(9, 9, 15), utc(9, 9, 45)),
            (MEDICINE, utc(9, 9, 45), utc(9, 10, 15)),
            (BILLS, utc(9, 10, 15), utc(9, 11, 15)),
        ]
    )
    assert w.tc.completed == ["tk-1"]
    assert w.tc.inserted == []
    bills = w.find(BILLS)["written"]
    assert bills["event_id"] and bills["closed"] is True and bills["tasks_id"] is None


def test_seam3_unchosen_task_from_tasks_stays_untimed_and_nothing_is_written_for_it() -> None:
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = bills_timed(w)
    assert w.find(PARCEL)["needs_time"] is False
    w.confirm(plan_id, fingerprint)
    assert PARCEL not in w.tc.event_titles()
    assert "tk-2" not in w.tc.complete_calls
    assert w.tc.completed == ["tk-1"]
    assert w.tc.inserted == []
    parcel = w.find(PARCEL)
    assert parcel["needs_time"] is False
    assert parcel["written"]["tasks_id"] is None and parcel["written"]["event_id"] is None


def test_seam3_numbers_outside_the_list_and_of_spoken_tasks_in_timed_are_ignored() -> None:
    w = two_and_bills()
    first = w.start()
    question = priorities_question(first)
    n_notary, n_medicine, n_bills = (number_of(first.text, t) for t in (NOTARY, MEDICINE, BILLS))
    before = copy.deepcopy(w.draft())
    for timed in ((n_notary,), (n_medicine, 9), (0,), (n_notary, n_medicine, 4, -1)):
        again = w.pick(question.id, timed=timed)
        assert again.question == question, (timed, again)
        assert again.text == first.text
        assert w.draft() == before, timed
    asked = w.pick(question.id, timed=(n_notary, n_bills, 7))
    assert asked.question == Question("duration", question.id, None), asked
    assert w.find(BILLS)["needs_time"] is True
    for title in (NOTARY, MEDICINE):
        assert w.find(title)["needs_time"] is True and w.find(title)["duration_min"] == 30


# ------------------------------------------------------------------ writing on «так»


def test_yes_writes_all_events_then_closings_then_new_tasks() -> None:
    w = with_tasks(
        task(NOTARY),
        task(MEDICINE),
        task(SEEDS, needs_time=False, duration_min=None),
        open_tasks=(TK_BILLS, TK_PARCEL),
    )
    plan_id, fingerprint = bills_timed(w)
    done = w.confirm(plan_id, fingerprint)
    kinds = [kind for kind, _ in w.tc.log]
    assert kinds == ["event", "event", "event", "close", "task"], w.tc.log
    assert ("close", "tk-1") in w.tc.log
    assert w.tc.inserted == [SEEDS]
    assert w.find(SEEDS)["written"]["tasks_id"] == "new-1"
    assert done.text.startswith(WRITTEN)
    assert TO_TASKS in done.text
    assert TASKS_LATER not in done.text
    assert done.plan is None


def test_untimed_spoken_tasks_go_to_tasks_and_the_answer_is_only_the_tasks_line() -> None:
    w = with_tasks(
        task(SEEDS, needs_time=False, duration_min=None),
        task(GARDEN, needs_time=False, duration_min=None),
        ask_priorities=False,
    )
    plan_id, fingerprint = shown(w.start())
    done = w.confirm(plan_id, fingerprint)
    assert done.text == TO_TASKS
    assert sorted(w.tc.inserted) == sorted([SEEDS, GARDEN])
    assert w.tc.created == []
    for title in (SEEDS, GARDEN):
        assert w.find(title)["written"]["tasks_id"] in {"new-1", "new-2"}


def test_spoken_task_that_did_not_fit_goes_to_tasks_on_yes() -> None:
    w = with_tasks(task(NOTARY), task(MEDICINE), ask_priorities=False)
    w.tc.busy(utc(9, 9, 0), utc(20, 0, 0))
    reply = w.start()
    assert reply.plan is not None and sorted(u["title"] for u in reply.plan.unplaced) == sorted(
        [NOTARY, MEDICINE]
    )
    done = w.confirm(*shown(reply))
    assert done.text == TO_TASKS
    assert sorted(w.tc.inserted) == sorted([NOTARY, MEDICINE])
    assert w.tc.created == []


def test_seam2_repeated_yes_adds_no_event_and_no_task() -> None:
    w = with_tasks(
        task(NOTARY),
        task(MEDICINE),
        task(SEEDS, needs_time=False, duration_min=None),
        open_tasks=(TK_BILLS,),
    )
    plan_id, fingerprint = bills_timed(w)
    w.confirm(plan_id, fingerprint)
    events, inserted, closings = len(w.tc.created), list(w.tc.inserted), list(w.tc.complete_calls)
    for seconds in (5, 50, 3600):
        again = w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=seconds))
        assert again.plan is None
    assert len(w.tc.created) == events == 3
    assert w.tc.inserted == inserted == [SEEDS]
    assert w.tc.complete_calls == closings == ["tk-1"]


def test_seam2_crash_after_events_before_closing_next_yes_closes_without_a_new_event() -> None:
    w = two_and_bills()
    plan_id, fingerprint = crash_before_closing(w)
    reply = w.confirm(plan_id, fingerprint, now=LATER)
    assert w.tc.completed == ["tk-1"]
    assert len(w.tc.created) == 3
    assert reply.plan is None, "a break on the Tasks step only is finished without a new plan"
    assert PARTLY_WRITTEN not in reply.text
    assert w.find(BILLS)["written"]["closed"] is True


def test_seam2_crash_before_closing_open_question_closes_without_a_new_yes() -> None:
    w = two_and_bills()
    crash_before_closing(w)
    w.opened(now=LATER)
    assert w.tc.completed == ["tk-1"]
    assert len(w.tc.created) == 3
    assert w.find(BILLS)["written"]["closed"] is True


def test_seam2_start_after_a_broken_write_appends_without_reading_tasks_or_showing_it_again() -> None:
    w = two_and_bills()
    crash_before_closing(w)
    w.ai.says(task(SISTER))
    reply = w.start("і зателефонувати сестрі", now=LATER)
    assert w.tc.list_calls == 1
    assert [t["title"] for t in w.tasks()].count(BILLS) == 1
    assert w.find(BILLS)["written"]["event_id"], "the same draft: the task keeps its event"
    assert BILLS not in items(reply)
    assert BILLS not in reply.text
    w.confirm(*shown(reply), now=LATER + timedelta(seconds=5))
    assert w.tc.event_titles() == sorted([BILLS, MEDICINE, NOTARY, SISTER])
    assert w.tc.completed == ["tk-1"]
    assert w.tc.inserted == []


def test_seam2_step0_records_the_found_event_before_it_closes() -> None:
    w = two_and_bills()
    plan_id, fingerprint = bills_timed(w)
    w.tc.crash_title = BILLS
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert w.tc.completed == []
    seen: list[Any] = []
    w.tc.on_complete = lambda task_id: seen.append(w.find(BILLS)["written"]["event_id"])
    reply = w.confirm(plan_id, fingerprint, now=LATER)
    yes_to_the_rest(w, reply, LATER + timedelta(seconds=5))
    assert seen and all(seen), f"closed before the found event was recorded: {seen!r}"
    assert w.tc.completed == ["tk-1"]
    assert w.tc.event_titles() == sorted([BILLS, MEDICINE, NOTARY])
    assert w.find(BILLS)["written"]["closed"] is True


def test_seam2_failure_on_the_second_new_task_next_yes_adds_only_the_rest() -> None:
    w = with_tasks(
        task(NOTARY),
        task(SEEDS, needs_time=False, duration_min=None),
        task(GARDEN, needs_time=False, duration_min=None),
        ask_priorities=False,
    )
    plan_id, fingerprint = shown(w.start())
    w.tc.fail_insert_task_on = 2
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert len(w.tc.inserted) == 1
    reply = w.confirm(plan_id, fingerprint, now=LATER)
    assert reply.plan is None
    assert sorted(w.tc.inserted) == sorted([SEEDS, GARDEN])
    assert w.tc.event_titles() == [NOTARY]
    assert TO_TASKS in reply.text


def test_spoken_task_already_in_tasks_is_not_placed_again() -> None:
    w = with_tasks(task(SISTER), task(GARDEN), ask_priorities=False)
    w.tc.busy(utc(9, 9, 0), utc(20, 0, 0))
    plan_id, fingerprint = shown(w.start())
    w.tc.fail_insert_task_on = 2
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert len(w.tc.inserted) == 1
    in_tasks = w.tc.inserted[0]
    left = GARDEN if in_tasks == SISTER else SISTER
    assert w.find(in_tasks)["written"]["tasks_id"] == "new-1"
    w.tc.free_all()
    w.ai.says(task(DOCTOR))
    reply = w.start("і до лікаря", now=LATER)
    assert reply.plan is not None, reply
    assert in_tasks not in items(reply)
    assert in_tasks not in [u["title"] for u in reply.plan.unplaced]
    assert left in items(reply)
    w.confirm(*shown(reply), now=LATER + timedelta(seconds=5))
    assert w.tc.inserted.count(in_tasks) == 1
    assert in_tasks not in w.tc.event_titles()


class _FailingOnce(TasksCalendar):
    """The first `insert_task` goes to the real `GoogleWork`, whose Tasks answers 503."""

    def __init__(self, real: GoogleWork) -> None:
        super().__init__()
        self.real: GoogleWork | None = real

    def insert_task(self, title: str) -> str:
        if self.real is not None:
            real, self.real = self.real, None
            return real.insert_task(title)
        return super().insert_task(title)


def test_tasks_error_gives_the_failed_reply_and_the_next_yes_finishes() -> None:
    transport = Transport(lambda r: (503, {"error": {"code": 503, "message": "Backend Error"}}))
    authorized = AuthorizedSession(Credentials("at-test"))
    authorized.mount("https://tasks.googleapis.com/", transport)
    authorized.mount("https://www.googleapis.com/", transport)
    real = GoogleWork(authorized, call_timeout_s=10, deadline=NOW + timedelta(seconds=60), now=lambda: NOW)
    w = with_tasks(task(NOTARY), task(SEEDS, needs_time=False, duration_min=None), ask_priorities=False)
    w.calendar = _FailingOnce(real)
    w.session = Session(account_id=SUB, google_credentials=lambda: Credentials("at-test"))
    w.store.set(
        SUB,
        access.TOKENS_PATH,
        access.tokens_document(
            Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)), NOW
        ),
    )
    app = create_app(
        w.config,
        w.store,
        cast(GoogleAuth, FakeGoogle()),
        Clock(NOW),
        ai=cast(AI, w.ai),
        calendar=lambda session, started: cast(GoogleWork, w.calendar),
    )
    client = TestClient(
        app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
    )
    client.cookies.set(
        "mm_session", access.session_cookie_value(SUB, "mama@example.com", NOW, key=w.config.session_key)
    )
    plan_id, fingerprint = shown(w.start())
    resp = client.post("/api/plan/confirm", json={"plan_id": plan_id, "fingerprint": fingerprint})
    body = resp.json()
    assert body["text"] == FAILED
    assert body["question"] is None
    assert [r.method for r in transport.sent] == ["POST"], "the failure came from Tasks"
    later = w.confirm(plan_id, fingerprint, now=LATER)
    assert later.plan is None
    assert w.tc.inserted == [SEEDS]
    assert w.tc.event_titles() == [NOTARY]
    assert TO_TASKS in later.text


# ------------------------------------------------------------------ invariants


def test_I1_task_from_tasks_is_never_created_in_tasks_and_its_event_gets_closed() -> None:
    def holds(w: WithTasks) -> None:
        for t in w.tasks():
            if t.get("source") == "tasks":
                assert t["written"]["tasks_id"] is None, t
        assert not {BILLS, PARCEL} & set(w.tc.inserted), w.tc.inserted
        assert w.tc.event_titles().count(BILLS) <= 1, w.tc.event_titles()
        assert w.tc.completed.count("tk-1") <= 1, w.tc.completed

    def closed(w: WithTasks) -> None:
        holds(w)
        assert w.tc.completed == ["tk-1"], w.tc.completed
        assert w.find(BILLS)["written"]["closed"] is True

    # (a) «так», then «так» again and again.
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = bills_timed(w)
    w.confirm(plan_id, fingerprint)
    closed(w)
    for seconds in (1, 45, 3600):
        w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=seconds))
        closed(w)

    # (b) the closing fails; the next «так» closes.
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = crash_before_closing(w)
    holds(w)
    yes_to_the_rest(w, w.confirm(plan_id, fingerprint, now=LATER), LATER + timedelta(seconds=1))
    closed(w)

    # (c) the closing fails; opening the app closes.
    w = two_and_bills(TK_PARCEL)
    crash_before_closing(w)
    w.opened(now=LATER)
    closed(w)

    # (d) the closing fails; a message appends (no new draft, Tasks not read), then «так» on the new plan.
    # The append leaves two unwritten tasks (the untimed PARCEL from Tasks counts, Q4), so the sealed
    # priorities rule asks the question again; «same» answers it and the plan follows.
    w = two_and_bills(TK_PARCEL)
    crash_before_closing(w)
    w.ai.says(task(SISTER))
    appended = w.start("і зателефонувати сестрі", now=LATER)
    holds(w)
    assert w.tc.list_calls == 1
    assert w.find(BILLS)["written"]["event_id"], "a new draft was made while an event was not closed"
    again = priorities_question(appended)
    reply = w.pick(again.id, same=True, now=LATER + timedelta(seconds=1))
    holds(w)
    assert w.tc.list_calls == 1
    assert w.find(BILLS)["written"]["event_id"], "a new draft was made while an event was not closed"
    w.confirm(*shown(reply), now=LATER + timedelta(seconds=5))
    closed(w)

    # (e) the answer of the event itself is lost; the next «так» finds it and closes.
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = bills_timed(w)
    w.tc.crash_title = BILLS
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    holds(w)
    yes_to_the_rest(w, w.confirm(plan_id, fingerprint, now=LATER), LATER + timedelta(seconds=1))
    closed(w)

    # (f) the closing fails twice: «так» fails again, then opening the app closes.
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = crash_before_closing(w)
    w.tc.fail_complete = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint, now=LATER)
    holds(w)
    assert w.tc.completed == []
    w.opened(now=LATER + timedelta(minutes=1))
    closed(w)

    # (g) after the write is done, a new planning: a new draft reads Tasks, the closed task is not offered.
    w = two_and_bills(TK_PARCEL)
    plan_id, fingerprint = bills_timed(w)
    w.confirm(plan_id, fingerprint)
    w.ai.says(task(SISTER), task(GARDEN))
    closed(w)
    fresh = w.start("зателефонувати сестрі і полити город", now=NOW + timedelta(hours=1))
    assert w.tc.list_calls == 2
    assert BILLS not in [t["title"] for t in w.tasks()]
    assert PARCEL in [t["title"] for t in w.tasks()]
    assert BILLS not in fresh.text
    holds(w)
    assert w.tc.completed == ["tk-1"]


def test_I2_nothing_is_written_to_calendar_or_tasks_without_yes_on_the_shown_plan() -> None:
    def nothing(w: WithTasks) -> None:
        assert w.tc.created == [] and w.tc.insert_calls == [], w.tc.created
        assert w.tc.insert_task_calls == 0 and w.tc.inserted == []
        assert w.tc.complete_calls == []

    w = with_tasks(
        task(NOTARY),
        task(MEDICINE),
        task(SEEDS, needs_time=False, duration_min=None),
        open_tasks=(TK_BILLS, TK_PARCEL),
    )
    w.tc.busy(utc(9, 9, 45), utc(9, 10, 15))
    first = w.start()
    question = priorities_question(first)
    nothing(w)
    w.opened()
    nothing(w)
    # A refused answer, then a lawful one.
    w.pick(question.id, timed=(0,))
    nothing(w)
    w.pick(question.id, order=(2,), timed=(number_of(first.text, BILLS), number_of(first.text, PARCEL)))
    nothing(w)
    w.opened()
    nothing(w)
    w.ai.durations = [60, 15]
    w.answer(question.id, "годину")
    nothing(w)
    reply = w.answer(question.id, "чверть години")
    old_id, old_fp = shown(reply)
    nothing(w)
    w.opened()
    nothing(w)
    with contextlib.suppress(Exception):
        w.confirm(old_id, "not-the-fingerprint")
    nothing(w)
    # A task added to the shown plan: «так» with the old fingerprint is a foreign one now.
    w.ai.says(task(SISTER))
    w.start("і зателефонувати сестрі", now=NOW + timedelta(seconds=10))
    nothing(w)
    w.opened(now=NOW + timedelta(seconds=11))
    nothing(w)
    with contextlib.suppress(Exception):
        w.confirm(old_id, old_fp, now=NOW + timedelta(seconds=12))
    nothing(w)
    w.opened(now=LATER + timedelta(minutes=5))
    nothing(w)
