"""Contract tests of the slice time-limits in `planning`, `assistant`, `config` and `/api/message`:
Seam 2 (the order of questions), Seam 3 (the limits answer), I2, and the `ask_limits` switch.

Written by the slice tester from the sealed contract `.engine/slices/time-limits.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (CET, UTC+1). Limits «weekdays 14:00–18:00» move a free task
from the S3 slot 10:15 Berlin to 14:00 Berlin = 13:00Z, so a plan shows whether the limits reached it.
"""

import copy
from datetime import UTC, datetime
from typing import cast

from fastapi.testclient import TestClient

from mamamemory import access, assistant, planning
from mamamemory.config import SCOPES, load_config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.several_tasks_world import DOCTOR, MEDICINE, NOTARY, task
from tests.test_config import _environ
from tests.test_one_task_http import SUB, Clock, FakeGoogle
from tests.test_one_task_planning import NOW, instant, shown
from tests.time_limits_world import (
    AGAIN_PREFIX,
    ASK_LIMITS_FIRST,
    NOT_ACTUAL,
    WEEKDAYS,
    Limited,
    limited,
    limits_question,
    parsed,
    plain,
)

ASK_NOTARY_DURATION = "Скільки часу займе «подзвонити нотаріусу»?"
"""stuck-question Seam: the duration question names the task, for one task too."""

AFTERNOONS = parsed(days=WEEKDAYS, start_local="14:00", end_local="18:00")
"""«будні з другої до шостої»: weekdays 14:00–18:00."""


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def plan_at(reply: Reply) -> tuple[datetime, datetime]:
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    return instant(reply.plan.start), instant(reply.plan.end)


def first_planning(w: Limited) -> str:
    """Start → the limits question → weekdays 14:00–18:00 → the plan → «так». Returns the plan's id."""
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    plan_id, fingerprint = shown(w.answer_limits(question.id, "будні з другої до шостої"))
    w.confirm(plan_id, fingerprint)
    return plan_id


# ------------------------------------------------------------------ the switch and next_question


def test_load_config_turns_ask_limits_on() -> None:
    assert load_config(_environ()).ask_limits is True


def test_ask_limits_off_keeps_the_path_duration_to_plan_and_ignores_saved_limits() -> None:
    w = limited(task(NOTARY), ask_limits=False)
    w.seed_limits([1], "14:00", "15:00")
    reply = w.start()
    # The S3 slot: Monday 10:15 Berlin = 09:15Z, not Tuesday 14:00.
    assert plan_at(reply) == (utc(9, 9, 15), utc(9, 9, 45))
    assert reply.question is not None and reply.question.kind == "plan"


def test_next_question_asks_limits_only_with_ask_limits_and_until_answered() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    draft = w.draft()
    assert draft is not None
    assert planning.next_question(draft, ask_limits=True) == Question("limits", draft["plan_id"], None)
    assert question == Question("limits", draft["plan_id"], None)
    assert planning.next_question(draft) is None
    assert planning.next_question(draft, ask_limits=False) is None
    answered = dict(draft, limits_answered=True)
    assert planning.next_question(answered, ask_limits=True) is None


# ------------------------------------------------------------------ Seam 2: the order of questions


def test_seam2_first_planning_asks_limits_with_the_first_text() -> None:
    w = limited(task(NOTARY))
    reply = w.start()
    question = limits_question(reply)
    assert plain(reply.text) == ASK_LIMITS_FIRST
    assert question.fingerprint is None
    assert w.calendar.insert_calls == []


def test_seam2_order_is_duration_then_limits_then_plan() -> None:
    w = limited(task(NOTARY, duration_min=None))
    first = w.start()
    assert first.question is not None and first.question.kind == "duration"
    assert first.text == ASK_NOTARY_DURATION
    second = w.answer(first.question.id, "пів години")
    limits_question(second)
    assert plain(second.text) == ASK_LIMITS_FIRST
    w.ai.limits = dict(AFTERNOONS)
    third = w.answer_limits(first.question.id, "будні з другої до шостої")
    # Weekdays 14:00–18:00: Monday 14:00 Berlin = 13:00Z.
    assert plan_at(third) == (utc(9, 13, 0), utc(9, 13, 30))
    assert third.plan is not None
    assert third.question == Question("plan", third.plan.plan_id, third.plan.fingerprint)


def test_limits_are_asked_even_when_every_task_names_its_time() -> None:
    w = limited(task(DOCTOR, start_local="2026-11-11T10:00:00", duration_min=60))
    limits_question(w.start())


def test_new_limits_are_saved_under_the_account_and_the_draft_is_answered() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    w.answer_limits(question.id, "будні з другої до шостої")
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")
    draft = w.draft()
    assert draft is not None and draft.get("limits_answered") is True


def test_seam2_second_planning_asks_as_last_time_and_yes_keeps_saved_limits_unwritten() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    assert len(w.store.limits_writes) == 1
    w.ai.says(task(MEDICINE))
    again = w.start("купити ліки")
    question = limits_question(again)
    assert again.text.startswith(AGAIN_PREFIX), again.text
    assert again.text.endswith("?"), again.text
    w.ai.limits = parsed(same_as_last=True)
    reply = w.answer_limits(question.id, "так")
    # NOTARY is written 14:00–14:30 Berlin; MEDICINE follows at 14:30 Berlin = 13:30Z.
    assert plan_at(reply) == (utc(9, 13, 30), utc(9, 14, 0))
    assert len(w.store.limits_writes) == 1, w.store.limits_writes
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")


def test_named_days_or_hours_win_over_same_as_last() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    w.ai.says(task(MEDICINE))
    question = limits_question(w.start("купити ліки"))
    w.ai.limits = parsed(same_as_last=True, days=WEEKDAYS, start_local="10:00", end_local="16:00")
    reply = w.answer_limits(question.id, "так, але тепер з десятої до четвертої")
    assert w.saved() == (WEEKDAYS, "10:00", "16:00")
    # Monday 10:15 Berlin (the first step) is inside 10:00–16:00: 09:15Z.
    assert plan_at(reply) == (utc(9, 9, 15), utc(9, 9, 45))


# ------------------------------------------------------------------ Seam 3: the limits answer


def assert_asked_again(w: Limited, plan_id: str, reply: Reply, text: str = ASK_LIMITS_FIRST) -> None:
    assert reply.question == Question("limits", plan_id, None), reply
    assert reply.plan is None, reply
    assert plain(reply.text) == text
    draft = w.draft()
    assert draft is not None
    assert planning.next_question(draft, ask_limits=True) == Question("limits", plan_id, None)


def test_seam3_answer_without_hours_asks_the_same_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = parsed(days=WEEKDAYS)
    reply = w.answer_limits(question.id, "у будні")
    assert_asked_again(w, question.id, reply)
    assert w.store.limits_writes == []


def test_seam3_answer_without_days_asks_the_same_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = parsed(start_local="09:00", end_local="18:00")
    reply = w.answer_limits(question.id, "з дев'ятої до шостої")
    assert_asked_again(w, question.id, reply)
    assert w.store.limits_writes == []


def test_seam3_start_not_before_end_asks_the_same_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    for start, end in (("18:00", "09:00"), ("10:00", "10:00")):
        w.ai.limits = parsed(days=WEEKDAYS, start_local=start, end_local=end)
        reply = w.answer_limits(question.id, f"з {start} до {end}")
        assert_asked_again(w, question.id, reply)
    assert w.store.limits_writes == []


def test_seam3_same_as_last_without_saved_limits_asks_the_same_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = parsed(same_as_last=True)
    reply = w.answer_limits(question.id, "як минулого разу")
    assert_asked_again(w, question.id, reply)
    assert w.store.limits_writes == []


def test_seam3_answer_to_an_old_plan_id_is_not_actual() -> None:
    w = limited(task(NOTARY))
    old_plan_id = first_planning(w)
    w.ai.says(task(MEDICINE))
    current = limits_question(w.start("купити ліки"))
    assert current.id != old_plan_id
    before = copy.deepcopy(w.draft())
    w.ai.limits = parsed(days=[0], start_local="08:00", end_local="09:00")
    reply = w.answer_limits(old_plan_id, "лише в понеділок з восьмої до дев'ятої")
    assert reply.text == NOT_ACTUAL
    assert w.draft() == before
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")


def test_seam3_duration_answer_while_limits_are_asked_returns_the_limits_question() -> None:
    w = limited(task(NOTARY, duration_min=None))
    first = w.start()
    assert first.question is not None
    limits_question(w.answer(first.question.id, "пів години"))
    before = copy.deepcopy(w.draft())
    reply = w.answer(first.question.id, "година")
    assert reply.question == Question("limits", first.question.id, None), reply
    assert plain(reply.text) == ASK_LIMITS_FIRST
    assert w.draft() == before
    assert w.store.limits_writes == []


def test_seam3_limits_answer_while_duration_is_asked_returns_the_duration_question() -> None:
    w = limited(task(NOTARY, duration_min=None))
    first = w.start()
    assert first.question is not None and first.question.kind == "duration"
    before = copy.deepcopy(w.draft())
    w.ai.limits = dict(AFTERNOONS)
    reply = w.answer_limits(first.question.id, "будні з другої до шостої")
    assert reply.question == Question("duration", first.question.id, None), reply
    assert reply.text == ASK_NOTARY_DURATION
    assert w.draft() == before
    assert w.store.limits_writes == []


def test_seam3_limits_answer_after_the_plan_is_shown_changes_nothing() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    shown(w.answer_limits(question.id, "будні з другої до шостої"))
    before = copy.deepcopy(w.draft())
    w.ai.limits = parsed(days=[0], start_local="08:00", end_local="09:00")
    reply = w.answer_limits(question.id, "лише в понеділок з восьмої до дев'ятої")
    assert reply.question is None or reply.question.kind != "limits", reply
    assert w.draft() == before
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")
    assert len(w.store.limits_writes) == 1
    assert w.calendar.insert_calls == []


# ------------------------------------------------------------------ routes to answer_limits


def test_message_reply_to_limits_goes_to_answer_limits() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
    reply = w.message("будні з другої до шостої", Question("limits", question.id, None))
    assert plan_at(reply) == (utc(9, 13, 0), utc(9, 13, 30))
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")


def test_open_question_shows_the_limits_question() -> None:
    w = limited(task(NOTARY))
    question = limits_question(w.start())
    opened = w.open()
    assert opened is not None
    assert opened.reply.question == Question("limits", question.id, None)
    assert plain(opened.reply.text) == ASK_LIMITS_FIRST


def test_open_questions_of_the_page_do_not_show_the_limits_question() -> None:
    w = limited(task(NOTARY))
    limits_question(w.start())
    draft = copy.deepcopy(w.store.get(w.session.account_id, planning.DRAFT_PATH))
    assert draft is not None, "the start of planning must leave a draft that asks the limits question"

    # Superseded by guide («Перше відкриття»): an account that has already seen the guide
    # (`settings/guide_shown` present) gets no guide.
    w.store.set(w.session.account_id, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})

    # Superseded by calm-open (Seam, I1): the open shows nothing of planning — the limits question
    # comes only in reply to a message — does not call the Calendar, and leaves the plan draft as it was.
    calls: list[str] = []

    def calendar() -> GoogleWork:
        calls.append("calendar")
        return cast(GoogleWork, w.calendar)

    found = assistant.open_questions(w.session, calendar=calendar, store=w.store, now=NOW, config=w.config)
    assert found.replies == []
    assert found.login_needed is False
    assert calls == []
    assert w.store.get(w.session.account_id, planning.DRAFT_PATH) == draft


def test_api_message_with_reply_to_limits_returns_the_plan() -> None:
    w = limited(task(NOTARY))
    w.session = access.Session(account_id=SUB, google_credentials=w.session.google_credentials)
    w.store.set(
        SUB,
        access.TOKENS_PATH,
        access.tokens_document(
            Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)), NOW
        ),
    )
    question = limits_question(w.start())
    w.ai.limits = dict(AFTERNOONS)
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
    resp = client.post(
        "/api/message",
        json={
            "text": "будні з другої до шостої",
            "reply_to": {"kind": "limits", "id": question.id, "fingerprint": None},
        },
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()["plan"]
    assert plan is not None, resp.json()
    assert (instant(plan["start"]), instant(plan["end"])) == (utc(9, 13, 0), utc(9, 13, 30))


# ------------------------------------------------------------------ I2


def test_I2_saved_limits_change_only_by_the_answer_to_the_limits_question() -> None:
    w = limited(task(NOTARY, duration_min=None))
    first = w.start()
    assert first.question is not None and first.question.kind == "duration"
    plan_id = first.question.id
    assert w.store.limits_writes == [] and w.saved() is None
    limits_question(w.answer(plan_id, "пів години"))
    w.answer(plan_id, "година")  # a duration answer while limits are asked
    w.open()
    w.ai.limits = parsed()  # an answer the model could not read
    w.answer_limits(plan_id, "не знаю")
    assert w.store.limits_writes == [] and w.saved() is None, "no default limits without an answer"

    w.ai.limits = dict(AFTERNOONS)
    plan_id_1, fingerprint = shown(w.answer_limits(plan_id, "будні з другої до шостої"))
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")
    w.ai.limits = parsed(days=[0], start_local="08:00", end_local="09:00")
    w.answer_limits(plan_id_1, "лише в понеділок з восьмої")  # the plan is shown: not the limits question
    w.confirm(plan_id_1, fingerprint)
    assert len(w.store.limits_writes) == 1 and w.saved() == (WEEKDAYS, "14:00", "18:00")

    # Second planning: «так» keeps the saved limits, written nowhere.
    w.ai.says(task(MEDICINE))
    second = limits_question(w.start("купити ліки"))
    w.open()
    w.answer(second.id, "година")
    w.ai.limits = parsed(same_as_last=True)
    plan_id_2, fingerprint_2 = shown(w.answer_limits(second.id, "так"))
    w.confirm(plan_id_2, fingerprint_2)
    assert len(w.store.limits_writes) == 1 and w.saved() == (WEEKDAYS, "14:00", "18:00")

    # Third planning: the answer to «як минулого разу?» names other hours — they become the limits.
    w.ai.says(task(DOCTOR))
    third = limits_question(w.start("до лікаря"))
    w.ai.limits = parsed(same_as_last=True, days=WEEKDAYS, start_local="10:00", end_local="16:00")
    w.answer_limits(third.id, "так, але з десятої до четвертої")
    assert w.saved() == (WEEKDAYS, "10:00", "16:00")
    assert len(w.store.limits_writes) == 2
