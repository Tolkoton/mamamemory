"""Contract tests of the slice one-task-to-calendar: `planning` and `assistant` on a fake Calendar.

Seam 2, I3, I4. Written by the slice tester from the sealed contract
`.engine/slices/one-task-to-calendar.md`, without the code.
The fake Calendar counts every `insert_event`, filters `list_events` by its time window as Google does, and
can create an event and then fail ("crash between create and record").
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import requests
from google.oauth2.credentials import Credentials

from mamamemory import assistant, planning
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import Event, GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Question, Reply

BERLIN = ZoneInfo("Europe/Berlin")
# Monday 9 November 2026, 10:07 in Berlin (CET, UTC+1).
NOW = datetime(2026, 11, 9, 9, 7, 0, tzinfo=UTC)
TITLE = "подзвонити нотаріусу"
ASK_DURATION = "Скільки часу це займе?"
WRITTEN = "Записала в календар."
NOT_ACTUAL = "Це питання вже не актуальне."
NO_FREE_TIME = "Не знайшла вільного часу цього тижня."


def make_config() -> Config:
    return Config(
        allowed_emails=frozenset({"mama@example.com"}),
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id="client-id.apps.googleusercontent.com",
        oauth_client_secret="client-secret",
        session_key="session-key-for-tests",
        session_max_age_s=7 * 24 * 3600,
        login_max_age_s=600,
        base_url="https://testserver",
        request_timeout_s=30,
        call_timeout_s=10,
    )


def make_session(account_id: str = "acc-1") -> Session:
    return Session(account_id=account_id, google_credentials=lambda: Credentials("at-test"))


@dataclass
class StoredEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    cancelled: bool = False


class FakeCalendar:
    """Stands in for `GoogleWork`. `honour_409=False` accepts a repeated id as a new event (no P-CALID)."""

    def __init__(self, tz: str = "Europe/Berlin", *, honour_409: bool = True) -> None:
        self.tz = tz
        self.honour_409 = honour_409
        self.events: list[StoredEvent] = []
        self.insert_calls: list[str] = []
        self.created: list[StoredEvent] = []
        self.on_insert: Callable[[str], None] | None = None
        """Called inside `insert_event` before anything is created (to run a later request)."""
        self.fail_after_create = False

    def busy(self, start: datetime, end: datetime, event_id: str = "otherbusy") -> None:
        self.events.append(StoredEvent(event_id, "чуже", start, end))

    def timezone(self) -> str:
        return self.tz

    def list_events(self, time_min: datetime, time_max: datetime) -> list[Event]:
        found = [e for e in self.events if not e.cancelled and e.end > time_min and e.start < time_max]
        return [Event(e.id, e.start, e.end) for e in sorted(found, key=lambda e: e.start)]

    def get_event(self, event_id: str) -> Event | None:
        for e in self.events:
            if e.id == event_id:
                return Event(e.id, e.start, e.end)
        return None

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        self.insert_calls.append(event_id)
        if self.on_insert is not None:
            hook, self.on_insert = self.on_insert, None
            hook(event_id)
        if self.honour_409 and any(e.id == event_id for e in self.events):
            return event_id
        event = StoredEvent(event_id, title, start, end)
        self.events.append(event)
        self.created.append(event)
        if self.fail_after_create:
            self.fail_after_create = False
            raise requests.exceptions.ReadTimeout("fake: created, the answer was lost")
        return event_id

    def own_events(self) -> list[StoredEvent]:
        return [e for e in self.events if e.id != "otherbusy" and not e.id.startswith("otherbusy")]


class FakeAI:
    """Stands in for `AI`: answers by `task_type` (`parse_task`, `parse_duration`, `route`)."""

    def __init__(
        self, *, start_local: str | None = None, duration_min: int | None = 30, title: str = TITLE
    ) -> None:
        self.task: dict[str, Any] = {"title": title, "start_local": start_local, "duration_min": duration_min}
        self.duration: dict[str, Any] = {"duration_min": 30}
        self.route: dict[str, Any] = {}
        self.calls: list[str] = []

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(task_type)
        if task_type == "parse_task":
            return dict(self.task)
        if task_type == "parse_duration":
            return dict(self.duration)
        return dict(self.route)


@dataclass
class World:
    calendar: FakeCalendar
    ai: FakeAI
    store: InMemoryStore
    config: Config
    session: Session

    def start(self, text: str = "у четвер подзвонити нотаріусу", now: datetime = NOW) -> Reply:
        return planning.start(
            self.session,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def answer(self, plan_id: str, text: str = "пів години", now: datetime = NOW) -> Reply:
        return planning.answer_duration(
            self.session,
            plan_id,
            text,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def confirm(self, plan_id: str, fingerprint: str, now: datetime = NOW) -> Reply:
        return planning.confirm(
            self.session,
            plan_id,
            fingerprint,
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            now=now,
            config=self.config,
        )

    def message(self, text: str, reply_to: Question | None, now: datetime = NOW) -> Reply:
        return assistant.handle_message(
            self.session,
            text,
            reply_to,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            store=self.store,
            config=self.config,
            now=now,
        )


def world(*, duration_min: int | None = 30, start_local: str | None = None, honour_409: bool = True) -> World:
    return World(
        FakeCalendar(honour_409=honour_409),
        FakeAI(start_local=start_local, duration_min=duration_min),
        InMemoryStore(),
        make_config(),
        make_session(),
    )


def instant(iso: str) -> datetime:
    """A `PlanView` time as an instant; a time without an offset is read in the calendar's zone."""
    value = datetime.fromisoformat(iso)
    return value if value.tzinfo is not None else value.replace(tzinfo=BERLIN)


def shown(reply: Reply) -> tuple[str, str]:
    assert reply.plan is not None, f"expected a plan, got {reply!r}"
    return reply.plan.plan_id, reply.plan.fingerprint


# ------------------------------------------------------------------ start / answer_duration


def test_start_without_duration_asks_for_it() -> None:
    w = world(duration_min=None)
    reply = w.start()
    assert reply.question is not None
    assert reply.question.kind == "duration"
    assert reply.text == ASK_DURATION
    assert reply.plan is None
    assert w.calendar.insert_calls == []


def test_start_with_duration_shows_plan_with_its_question() -> None:
    w = world(duration_min=30)
    reply = w.start()
    assert reply.plan is not None
    # 10:07 Berlin -> the next 15-minute step is 10:15 Berlin = 09:15 UTC; empty calendar.
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert instant(reply.plan.end) == datetime(2026, 11, 9, 9, 45, tzinfo=UTC)
    assert reply.plan.title == TITLE
    assert reply.question == Question(kind="plan", id=reply.plan.plan_id, fingerprint=reply.plan.fingerprint)
    assert "Пропоную" in reply.text and "Записати?" in reply.text
    assert "10:15" in reply.text, "the proposal names the time in the calendar's zone"
    assert w.calendar.insert_calls == []


def test_answer_duration_shows_plan() -> None:
    w = world(duration_min=None)
    question = w.start().question
    assert question is not None
    reply = w.answer(question.id, "пів години")
    assert reply.plan is not None
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert instant(reply.plan.end) == datetime(2026, 11, 9, 9, 45, tzinfo=UTC)
    assert reply.question is not None and reply.question.kind == "plan"
    assert reply.question.fingerprint == reply.plan.fingerprint
    assert w.calendar.insert_calls == []


def test_answer_to_old_duration_question_is_not_actual_and_keeps_current_draft() -> None:
    w = world(duration_min=None)
    old = w.start("перша задача").question
    new = w.start("друга задача").question
    assert old is not None and new is not None
    stale = w.answer(old.id)
    assert stale.text == NOT_ACTUAL
    assert stale.plan is None
    current = w.answer(new.id)
    assert current.plan is not None, "the current draft must be unchanged by the stale answer"


def test_answer_duration_without_free_time_this_week_shows_no_plan_and_keeps_draft() -> None:
    w = world(duration_min=None)
    question = w.start().question
    assert question is not None
    # Busy from before now to 10 minutes before the 7-day horizon: no 30-minute slot.
    w.calendar.busy(NOW - timedelta(hours=1), NOW + timedelta(days=7) - timedelta(minutes=10))
    reply = w.answer(question.id)
    assert reply.text == NO_FREE_TIME
    assert reply.plan is None
    w.calendar.events.clear()
    again = w.answer(question.id)
    assert again.plan is not None, "the draft still waits for its duration"


def test_message_reply_to_duration_goes_to_answer_duration() -> None:
    w = world(duration_min=None)
    question = w.start().question
    assert question is not None
    reply = w.message("пів години", Question(kind="duration", id=question.id, fingerprint=None))
    assert reply.plan is not None
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 9, 15, tzinfo=UTC)


# ------------------------------------------------------------------ confirm (Seam 2)


def test_confirm_with_shown_fingerprint_writes_one_event_at_shown_time() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    reply = w.confirm(plan_id, fingerprint)
    assert reply.text == WRITTEN
    assert reply.plan is None
    assert len(w.calendar.created) == 1
    event = w.calendar.created[0]
    assert (event.start, event.end) == (
        datetime(2026, 11, 9, 9, 15, tzinfo=UTC),
        datetime(2026, 11, 9, 9, 45, tzinfo=UTC),
    )
    assert event.title == TITLE


def test_confirm_twice_creates_no_second_event() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    w.confirm(plan_id, fingerprint)
    second = w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=5))
    assert second.plan is None
    assert len(w.calendar.insert_calls) == 1
    assert len(w.calendar.own_events()) == 1


def test_confirm_after_calendar_changed_shows_new_plan_and_writes_nothing() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    # Mama's calendar gets an event over the shown 09:15-09:45 UTC.
    w.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    reply = w.confirm(plan_id, fingerprint)
    assert w.calendar.insert_calls == []
    assert reply.plan is not None
    assert reply.plan.fingerprint != fingerprint
    assert reply.question is not None and reply.question.kind == "plan"
    assert reply.question.fingerprint == reply.plan.fingerprint
    # The busy event ends at 11:00 UTC: the earliest free start.
    assert instant(reply.plan.start) == datetime(2026, 11, 9, 11, 0, tzinfo=UTC)
    written = w.confirm(reply.plan.plan_id, reply.plan.fingerprint)
    assert written.text == WRITTEN
    assert [(e.start, e.end) for e in w.calendar.created] == [
        (datetime(2026, 11, 9, 11, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 30, tzinfo=UTC))
    ]


def test_crash_between_create_and_record_then_yes_writes_without_second_event() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    w.calendar.fail_after_create = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert len(w.calendar.created) == 1
    # Later than REQUEST_TIMEOUT_S (30 s), still before the 09:15 step.
    later = NOW + timedelta(seconds=45)
    reply = w.confirm(plan_id, fingerprint, now=later)
    assert reply.text == WRITTEN
    assert reply.plan is None
    assert len(w.calendar.insert_calls) == 1, "the found own event must not be created again"
    own = w.calendar.own_events()
    assert [(e.start, e.end) for e in own] == [
        (datetime(2026, 11, 9, 9, 15, tzinfo=UTC), datetime(2026, 11, 9, 9, 45, tzinfo=UTC))
    ]


def test_crashed_write_found_by_id_when_event_is_past_or_cancelled() -> None:
    # (a) the event already ended: outside any events.list window from "now".
    w = world()
    plan_id, fingerprint = shown(w.start())
    w.calendar.fail_after_create = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    after_end = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    reply = w.confirm(plan_id, fingerprint, now=after_end)
    assert reply.text == WRITTEN
    assert reply.plan is None
    assert len(w.calendar.insert_calls) == 1
    assert len(w.calendar.own_events()) == 1

    # (b) mama deleted the event (status cancelled): it counts as "already there".
    w = world()
    plan_id, fingerprint = shown(w.start())
    w.calendar.fail_after_create = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    w.calendar.created[0].cancelled = True
    reply = w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=45))
    assert reply.text == WRITTEN
    assert reply.plan is None
    assert len(w.calendar.insert_calls) == 1


def test_late_request_does_not_overwrite_newer_write() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    replies: list[Reply] = []

    def newer_request(_: str) -> None:
        # Request A is stuck inside its create call past REQUEST_TIMEOUT_S; request B comes.
        replies.append(w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=40)))

    w.calendar.on_insert = newer_request
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    assert replies, "the newer request returned its reply"
    assert len(w.calendar.own_events()) == 1
    calls = len(w.calendar.insert_calls)
    after = w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=60))
    assert after.plan is None
    assert len(w.calendar.insert_calls) == calls
    assert [(e.start, e.end) for e in w.calendar.own_events()] == [
        (datetime(2026, 11, 9, 9, 15, tzinfo=UTC), datetime(2026, 11, 9, 9, 45, tzinfo=UTC))
    ]


# ------------------------------------------------------------------ invariants


def test_I3_any_sequence_of_yes_creates_at_most_one_event_per_task() -> None:
    # A Calendar that does NOT refuse a repeated id: no reliance on P-CALID.
    # (1) yes, yes, yes with a bogus fingerprint, yes again.
    w = world(honour_409=False)
    plan_id, fingerprint = shown(w.start())
    w.confirm(plan_id, fingerprint)
    w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=1))
    with contextlib.suppress(Exception):
        w.confirm(plan_id, "not-the-fingerprint", now=NOW + timedelta(seconds=2))
    w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=3))
    assert len(w.calendar.created) == 1

    # (2) crash between create and record, then yes three times (fresh, stale, after the event ended).
    w = world(honour_409=False)
    plan_id, fingerprint = shown(w.start())
    w.calendar.fail_after_create = True
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint)
    for later in (timedelta(seconds=1), timedelta(seconds=45), timedelta(hours=1)):
        with contextlib.suppress(Exception):
            w.confirm(plan_id, fingerprint, now=NOW + later)
    assert len(w.calendar.created) == 1

    # (3) a wrong fingerprint first (new plan shown), then yes to the new one, then the old one again.
    w = world(honour_409=False)
    plan_id, fingerprint = shown(w.start())
    renewed = w.confirm(plan_id, "stale-fingerprint")
    assert w.calendar.created == []
    new_id, new_fp = shown(renewed)
    w.confirm(new_id, new_fp, now=NOW + timedelta(seconds=1))
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=2))
    with contextlib.suppress(Exception):
        w.confirm(new_id, new_fp, now=NOW + timedelta(seconds=50))
    assert len(w.calendar.created) == 1

    # (4) the calendar changes after "yes" was written: a repeated yes still creates nothing.
    w = world(honour_409=False)
    plan_id, fingerprint = shown(w.start())
    w.confirm(plan_id, fingerprint)
    w.calendar.busy(datetime(2026, 11, 9, 8, 0, tzinfo=UTC), datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint, now=NOW + timedelta(seconds=2))
    assert len(w.calendar.created) == 1


def test_I4_nothing_is_written_without_yes_carrying_the_shown_fingerprint() -> None:
    # (a) "yes" while the duration is still being asked: directly, and through a message.
    w = world(duration_min=None)
    question = w.start().question
    assert question is not None
    with contextlib.suppress(Exception):
        w.confirm(question.id, "any-fingerprint")
    assert w.calendar.insert_calls == []
    wm = world(duration_min=None)
    asked = wm.start().question
    assert asked is not None
    with contextlib.suppress(Exception):
        wm.message("так", Question(kind="plan", id=asked.id, fingerprint="any-fingerprint"))
    assert wm.calendar.insert_calls == []

    # (b) the plan is shown after the duration answer: showing writes nothing.
    reply = w.answer(question.id)
    plan_id, fingerprint = shown(reply)
    assert w.calendar.insert_calls == []

    # (c) "yes" with a fingerprint of no shown plan, directly and through a message.
    with contextlib.suppress(Exception):
        w.confirm(plan_id, fingerprint + "x")
    with contextlib.suppress(Exception):
        w.message("так", Question(kind="plan", id=plan_id, fingerprint="other-plan"))
    assert w.calendar.insert_calls == []

    # (d) "yes" with the fingerprint of a plan that was shown before the calendar changed.
    w2 = world()
    old_id, old_fp = shown(w2.start())
    w2.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    new_reply = w2.confirm(old_id, old_fp)
    assert w2.calendar.insert_calls == []

    # The fake does record writes: the fingerprint of the shown plan writes.
    new_id, new_fp = shown(new_reply)
    w2.confirm(new_id, new_fp, now=NOW + timedelta(seconds=2))
    assert len(w2.calendar.created) == 1
