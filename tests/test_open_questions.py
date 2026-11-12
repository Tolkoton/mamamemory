"""Contract tests of the slice open-questions: `planning.open_question` and `assistant.open_questions`.

Seam 1 (open -> yes), Seam 2 (expired sign-in), I1, I2. Written by the slice tester from the sealed contract
`.engine/slices/open-questions.md`, without the code. The Calendar is the S3 fake; the lazy `calendar`
argument is a counting factory. A request "killed" inside the Calendar create call (the process died, no
`except` ran) is simulated by a `BaseException` raised from `FakeCalendar.on_insert`: the draft is left in
«записується», as after a crash of the instance.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import requests

from mamamemory import assistant, planning
from mamamemory.errors import LoginExpired, MissingScopes
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.planning import OpenQuestion
from mamamemory.replies import Question, Reply
from tests.test_one_task_planning import (
    ASK_DURATION,
    NO_FREE_TIME,
    NOW,
    TITLE,
    WRITTEN,
    FakeCalendar,
    StoredEvent,
    World,
    instant,
    shown,
    world,
)

SIGN_IN_AGAIN = "Щоб показати план, увійди знову."
NAMED_OUTSIDE = "Цей час уже минув або він далі ніж за тиждень."
WEEK = timedelta(days=7)
# 09:15-09:45 UTC is the first free 30-minute slot from NOW (10:07 Berlin) on an empty calendar.
SLOT = (datetime(2026, 11, 9, 9, 15, tzinfo=UTC), datetime(2026, 11, 9, 9, 45, tzinfo=UTC))


class Killed(BaseException):
    """The instance died inside the create call: nothing after it ran."""


class Lazy:
    """The `calendar` argument: counts its calls; returns the fake or raises what it is told to."""

    def __init__(self, calendar: FakeCalendar, raises: BaseException | None = None) -> None:
        self.calendar = calendar
        self.raises = raises
        self.calls = 0

    def __call__(self) -> GoogleWork:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return cast(GoogleWork, self.calendar)


def open_q(w: World, now: datetime = NOW, *, calendar: Lazy | None = None) -> OpenQuestion | None:
    lazy = calendar if calendar is not None else Lazy(w.calendar)
    return planning.open_question(w.session, calendar=lazy, store=w.store, now=now, config=w.config)


def open_all(w: World, calendar: Callable[[], GoogleWork], now: datetime = NOW) -> assistant.OpenQuestions:
    return assistant.open_questions(w.session, calendar=calendar, store=w.store, now=now, config=w.config)


def guide_seen(w: World) -> World:
    """The account has already seen the guide (F5 guide, «Перше відкриття»): the mark is in the store."""
    w.store.set(w.session.account_id, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})
    return w


def draft(w: World) -> object:
    return w.store.get(w.session.account_id, planning.DRAFT_PATH)


def killed_writing(w: World, *, created: bool) -> tuple[str, str]:
    """A shown plan whose "yes" died inside the create call; the draft stays in «записується»."""
    plan_id, fingerprint = shown(w.start())

    def die(event_id: str) -> None:
        if created:
            w.calendar.events.append(StoredEvent(event_id, TITLE, *SLOT))
        raise Killed()

    w.calendar.on_insert = die
    with pytest.raises(Killed):
        w.confirm(plan_id, fingerprint)
    return plan_id, fingerprint


def plan_question(result: OpenQuestion | None) -> tuple[str, str]:
    assert result is not None, "expected an open question"
    assert result.login_needed is False
    plan = result.reply.plan
    assert plan is not None, f"expected a plan, got {result.reply!r}"
    assert result.reply.question == Question("plan", plan.plan_id, plan.fingerprint)
    return plan.plan_id, plan.fingerprint


# ------------------------------------------------------------------ planning.open_question


def test_no_draft_is_none() -> None:
    w = world()
    assert open_q(w) is None


def test_written_draft_is_none() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    assert w.confirm(plan_id, fingerprint).text == WRITTEN
    assert open_q(w, NOW + timedelta(minutes=1)) is None


def test_fresh_writing_is_none() -> None:
    w = world()
    killed_writing(w, created=False)
    # 5 s later: younger than REQUEST_TIMEOUT_S (30 s).
    assert open_q(w, NOW + timedelta(seconds=5)) is None


def test_asking_duration_returns_the_question_without_calendar() -> None:
    w = world(duration_min=None)
    asked = w.start().question
    assert asked is not None
    lazy = Lazy(w.calendar)
    result = open_q(w, NOW + timedelta(hours=2), calendar=lazy)
    assert result == OpenQuestion(Reply(ASK_DURATION, Question("duration", asked.id, None)), False)
    assert lazy.calls == 0


def test_asking_duration_is_not_subject_to_horizon() -> None:
    # Superseded by stuck-question («Старе питання», I2): the 7-day plan horizon does not apply to an asking
    # draft, but an asking draft older than 24 h is not shown on open, and opening writes nothing.
    w = world(duration_min=None)
    asked = w.start().question
    assert asked is not None
    result = open_q(w, NOW + timedelta(hours=23))
    assert result == OpenQuestion(Reply(ASK_DURATION, Question("duration", asked.id, None)), False)
    before = draft(w)
    assert open_q(w, NOW + timedelta(hours=25)) is None
    assert open_q(w, NOW + timedelta(days=30)) is None
    assert draft(w) == before


def test_shown_plan_is_shown_again_with_its_question() -> None:
    w = world()
    plan_id, _ = shown(w.start())
    result = open_q(w, NOW + timedelta(minutes=1))
    open_id, _ = plan_question(result)
    assert open_id == plan_id
    assert result is not None and result.reply.plan is not None
    assert result.reply.plan.title == TITLE
    # 10:08 Berlin -> next step 10:15 Berlin = 09:15 UTC; empty calendar.
    assert (instant(result.reply.plan.start), instant(result.reply.plan.end)) == SLOT
    assert w.calendar.insert_calls == []


def test_shown_plan_without_free_time_gives_s3_text_without_plan() -> None:
    w = world()
    shown(w.start())
    w.calendar.busy(NOW - timedelta(hours=1), NOW + WEEK + timedelta(hours=1))
    result = open_q(w, NOW + timedelta(minutes=1))
    assert result is not None
    assert result.login_needed is False
    assert result.reply.text == NO_FREE_TIME
    assert result.reply.plan is None


def test_shown_plan_with_named_time_passed_gives_s3_text_without_plan() -> None:
    # Named 11:00 Berlin on Monday 9 November; opened at 11:30 Berlin, inside the horizon.
    w = world(start_local="2026-11-09T11:00:00")
    first = w.start().plan
    assert first is not None
    result = open_q(w, datetime(2026, 11, 9, 10, 30, tzinfo=UTC))
    assert result is not None
    assert result.login_needed is False
    assert result.reply.text == NAMED_OUTSIDE
    assert result.reply.plan is None


def test_open_without_draft_creates_no_draft() -> None:
    w = world()
    open_q(w)
    assert draft(w) is None


def test_shown_plan_at_horizon_end_is_none() -> None:
    w = world()
    shown(w.start())
    # The horizon is 7 days from the first show (NOW); now == horizon_end counts as passed.
    assert open_q(w, NOW + WEEK) is None
    assert open_q(w, NOW + WEEK + timedelta(days=1)) is None


def test_shown_plan_just_before_horizon_end_is_not_none() -> None:
    w = world()
    shown(w.start())
    result = open_q(w, NOW + WEEK - timedelta(minutes=1))
    assert result is not None, "the horizon has not passed yet"
    assert result.login_needed is False


def test_shown_draft_past_horizon_is_not_deleted() -> None:
    w = world()
    shown(w.start())
    assert draft(w) is not None
    open_q(w, NOW + WEEK + timedelta(days=1))
    assert draft(w) is not None


def test_stale_writing_with_own_event_found_is_none() -> None:
    w = world()
    killed_writing(w, created=True)
    calls = len(w.calendar.insert_calls)
    assert open_q(w, NOW + timedelta(seconds=45)) is None
    assert len(w.calendar.insert_calls) == calls


def test_stale_writing_without_event_is_shown_again() -> None:
    w = world()
    plan_id, _ = killed_writing(w, created=False)
    open_id, _ = plan_question(open_q(w, NOW + timedelta(seconds=45)))
    assert open_id == plan_id


def test_stale_writing_past_horizon_is_none() -> None:
    w = world()
    killed_writing(w, created=False)
    assert open_q(w, NOW + WEEK + timedelta(hours=1)) is None


def test_seam2_login_expired_on_plan_asks_to_sign_in_and_keeps_draft() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    before = draft(w)
    result = open_q(w, NOW + timedelta(minutes=1), calendar=Lazy(w.calendar, LoginExpired()))
    assert result == OpenQuestion(Reply(SIGN_IN_AGAIN), True)
    assert draft(w) == before
    # The draft is the same: the shown plan is still written by its own "yes".
    assert w.confirm(plan_id, fingerprint, now=NOW + timedelta(minutes=1)).text == WRITTEN
    assert [(e.start, e.end) for e in w.calendar.created] == [SLOT]


def test_seam2_missing_scopes_on_plan_asks_to_sign_in_and_keeps_draft() -> None:
    w = world()
    shown(w.start())
    before = draft(w)
    failing = Lazy(w.calendar, MissingScopes(frozenset({"https://www.googleapis.com/auth/calendar.events"})))
    result = open_q(w, NOW + timedelta(minutes=1), calendar=failing)
    assert result == OpenQuestion(Reply(SIGN_IN_AGAIN), True)
    assert draft(w) == before


def test_seam2_asking_duration_is_returned_when_login_expired_and_calendar_not_called() -> None:
    w = world(duration_min=None)
    asked = w.start().question
    assert asked is not None
    lazy = Lazy(w.calendar, LoginExpired())
    result = open_q(w, NOW + timedelta(minutes=1), calendar=lazy)
    assert result == OpenQuestion(Reply(ASK_DURATION, Question("duration", asked.id, None)), False)
    assert lazy.calls == 0


def test_calendar_http_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    w = world()
    shown(w.start())

    def broken(time_min: datetime, time_max: datetime) -> list[object]:
        raise requests.HTTPError("fake: 500 Backend Error")

    monkeypatch.setattr(w.calendar, "list_events", broken)
    with pytest.raises(requests.HTTPError):
        open_q(w, NOW + timedelta(minutes=1))


def test_seam1_plan_shown_on_open_is_written_once_by_its_yes() -> None:
    w = world()
    shown(w.start())
    at = NOW + timedelta(minutes=1)
    plan_id, fingerprint = plan_question(open_q(w, at))
    assert w.confirm(plan_id, fingerprint, now=at).text == WRITTEN
    w.confirm(plan_id, fingerprint, now=at + timedelta(seconds=5))
    assert len(w.calendar.insert_calls) == 1
    assert [(e.start, e.end, e.title) for e in w.calendar.own_events()] == [(*SLOT, TITLE)]


def test_seam1_calendar_changed_before_open_new_fingerprint_writes_old_does_not() -> None:
    # (a) the new fingerprint writes exactly once; the old one adds nothing.
    w = world()
    old_id, old_fp = shown(w.start())
    w.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    at = NOW + timedelta(minutes=1)
    new_id, new_fp = plan_question(open_q(w, at))
    assert new_id == old_id
    assert new_fp != old_fp
    assert w.confirm(new_id, new_fp, now=at).text == WRITTEN
    w.confirm(old_id, old_fp, now=at + timedelta(seconds=5))
    assert len(w.calendar.insert_calls) == 1
    # The busy event ends at 11:00 UTC: the earliest free start.
    assert [(e.start, e.end) for e in w.calendar.own_events()] == [
        (datetime(2026, 11, 9, 11, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 30, tzinfo=UTC))
    ]

    # (b) after the open, "yes" with the old fingerprint writes nothing.
    w = world()
    old_id, old_fp = shown(w.start())
    w.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    plan_question(open_q(w, at))
    w.confirm(old_id, old_fp, now=at)
    assert w.calendar.insert_calls == []


# ------------------------------------------------------------------ assistant.open_questions
# Superseded by guide («Перше відкриття»): an account without `settings/guide_shown` gets the guide
# first; these tests hold the other sources, so the account has already seen the guide.


def test_open_questions_without_draft_is_empty() -> None:
    w = guide_seen(world())
    result = open_all(w, Lazy(w.calendar))
    assert result.replies == []
    assert result.login_needed is False
    assert result.failed == []


def test_open_questions_returns_the_source_reply() -> None:
    w = guide_seen(world(duration_min=None))
    asked = w.start().question
    assert asked is not None
    result = open_all(w, Lazy(w.calendar))
    assert result.replies == [Reply(ASK_DURATION, Question("duration", asked.id, None))]
    assert result.login_needed is False
    assert result.failed == []


def test_open_questions_login_needed_from_source() -> None:
    w = guide_seen(world())
    shown(w.start())
    result = open_all(w, Lazy(w.calendar, LoginExpired()), NOW + timedelta(minutes=1))
    assert result.replies == [Reply(SIGN_IN_AGAIN)]
    assert result.login_needed is True


def test_open_questions_failed_source_is_skipped_and_named(monkeypatch: pytest.MonkeyPatch) -> None:
    w = guide_seen(world())
    shown(w.start())

    def broken(time_min: datetime, time_max: datetime) -> list[object]:
        raise requests.HTTPError("fake: 500 Backend Error")

    monkeypatch.setattr(w.calendar, "list_events", broken)
    result = open_all(w, Lazy(w.calendar), NOW + timedelta(minutes=1))
    assert result.replies == []
    assert result.login_needed is False
    assert len(result.failed) == 1
    assert isinstance(result.failed[0], str) and result.failed[0]


# ------------------------------------------------------------------ invariants


def test_I1_opening_never_writes_to_calendar() -> None:
    later = NOW + timedelta(minutes=1)
    cases: list[tuple[str, World, datetime, BaseException | None]] = []

    cases.append(("no draft", world(), later, None))

    w = world(duration_min=None)
    w.start()
    cases.append(("asking duration", w, later, None))
    w = world(duration_min=None)
    w.start()
    cases.append(("asking duration, sign-in expired", w, later, LoginExpired()))

    w = world()
    shown(w.start())
    cases.append(("shown", w, later, None))
    w = world()
    shown(w.start())
    w.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    cases.append(("shown, calendar changed", w, later, None))
    w = world()
    shown(w.start())
    w.calendar.busy(NOW - timedelta(hours=1), NOW + WEEK + timedelta(hours=1))
    cases.append(("shown, no free time", w, later, None))
    w = world()
    shown(w.start())
    cases.append(("shown, horizon passed", w, NOW + WEEK, None))
    w = world()
    shown(w.start())
    cases.append(("shown, sign-in expired", w, later, LoginExpired()))

    w = world()
    plan_id, fingerprint = shown(w.start())
    w.confirm(plan_id, fingerprint)
    cases.append(("written", w, later, None))

    w = world()
    killed_writing(w, created=False)
    cases.append(("fresh writing", w, NOW + timedelta(seconds=5), None))
    w = world()
    killed_writing(w, created=False)
    cases.append(("stale writing, nothing created", w, NOW + timedelta(seconds=45), None))
    w = world()
    killed_writing(w, created=True)
    cases.append(("stale writing, event created", w, NOW + timedelta(seconds=45), None))
    w = world()
    killed_writing(w, created=False)
    cases.append(("stale writing, horizon passed", w, NOW + WEEK + timedelta(hours=1), None))

    for name, case, at, raises in cases:
        case.calendar.on_insert = None
        calls = list(case.calendar.insert_calls)
        events = [(e.id, e.start, e.end) for e in case.calendar.events]
        open_q(case, at, calendar=Lazy(case.calendar, raises))
        # Opened twice: a repeat writes nothing either.
        open_q(case, at + timedelta(seconds=1), calendar=Lazy(case.calendar, raises))
        assert case.calendar.insert_calls == calls, name
        assert [(e.id, e.start, e.end) for e in case.calendar.events] == events, name


def test_I2_question_returned_on_open_is_valid_and_writes_exactly_the_shown_plan() -> None:
    at = NOW + timedelta(minutes=1)
    busy = (datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    after_busy = (datetime(2026, 11, 9, 11, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 30, tzinfo=UTC))

    def yes_writes_shown(
        w: World, result: OpenQuestion | None, when: datetime, expected: tuple[datetime, datetime]
    ) -> None:
        plan_id, fingerprint = plan_question(result)
        assert result is not None and result.reply.plan is not None
        shown_slot = (instant(result.reply.plan.start), instant(result.reply.plan.end))
        assert shown_slot == expected
        before = len(w.calendar.insert_calls)
        reply = w.confirm(plan_id, fingerprint, now=when)
        assert reply.text == WRITTEN, reply
        assert reply.plan is None, "a valid question writes without a new show"
        assert len(w.calendar.insert_calls) == before + 1
        assert [(e.start, e.end) for e in w.calendar.own_events()] == [expected]

    # (a) shown, calendar unchanged.
    w = world()
    shown(w.start())
    yes_writes_shown(w, open_q(w, at), at, SLOT)

    # (b) shown, an event lands over the shown slot before the open.
    w = world()
    shown(w.start())
    w.calendar.busy(*busy)
    yes_writes_shown(w, open_q(w, at), at, after_busy)

    # (c) shown over a busy calendar, the busy event is removed before the open: the earlier slot.
    w = world()
    w.calendar.busy(*busy)
    first = w.start()
    assert first.plan is not None and (instant(first.plan.start), instant(first.plan.end)) == after_busy
    w.calendar.events.clear()
    yes_writes_shown(w, open_q(w, at), at, SLOT)

    # (d) opened twice, the calendar changed between the two opens: the second question is the valid one.
    w = world()
    shown(w.start())
    open_q(w, at)
    w.calendar.busy(*busy)
    yes_writes_shown(w, open_q(w, at), at, after_busy)

    # (e) stale «записується», nothing was created.
    w = world()
    killed_writing(w, created=False)
    w.calendar.on_insert = None
    stale = NOW + timedelta(seconds=45)
    result = open_q(w, stale)
    plan_id, fingerprint = plan_question(result)
    assert result is not None and result.reply.plan is not None
    assert (instant(result.reply.plan.start), instant(result.reply.plan.end)) == SLOT
    reply = w.confirm(plan_id, fingerprint, now=stale)
    assert reply.text == WRITTEN and reply.plan is None
    assert [(e.start, e.end) for e in w.calendar.own_events()] == [SLOT]

    # (f) stale «записується» and the calendar changed.
    w = world()
    killed_writing(w, created=False)
    w.calendar.on_insert = None
    w.calendar.busy(*busy)
    result = open_q(w, stale)
    plan_id, fingerprint = plan_question(result)
    assert result is not None and result.reply.plan is not None
    assert (instant(result.reply.plan.start), instant(result.reply.plan.end)) == after_busy
    reply = w.confirm(plan_id, fingerprint, now=stale)
    assert reply.text == WRITTEN and reply.plan is None
    assert [(e.start, e.end) for e in w.calendar.own_events()] == [after_busy]

    # (g) an open refused by an expired sign-in, then a lawful open: its question is valid.
    w = world()
    shown(w.start())
    w.calendar.busy(*busy)
    assert open_q(w, at, calendar=Lazy(w.calendar, LoginExpired())) == OpenQuestion(
        Reply(SIGN_IN_AGAIN), True
    )
    yes_writes_shown(w, open_q(w, at), at, after_busy)
