"""Contract tests of the slice calm-open: Seam 1 (an open without planning), Seam 2 (tasks by their date),
Seam 3 (the guide button, server side), I1, I2.

Written by the slice tester from the sealed contract `.engine/slices/calm-open.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). November 2026: Sunday 8, Monday 9, Sunday 15,
Monday 16, Sunday 22, Monday 23. Europe/Berlin is UTC+1 in November and UTC+2 until Sunday 25 October 2026,
03:00. America/Los_Angeles is UTC-8 in November; Pacific/Kiritimati is UTC+14. Every expected value is
written by hand.
"""

import copy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from mamamemory import access, assistant, planning
from mamamemory import cases as case_module
from mamamemory.errors import LoginExpired
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.google_work import AgendaItem, GoogleWork, TaskItem
from mamamemory.integrations.store import Decide, InMemoryStore
from mamamemory.planning import schedule
from mamamemory.replies import Reply
from tests.case_questions_world import Asks, case_q
from tests.google_tasks_world import TasksCalendar
from tests.guide_world import GUIDE, is_guide
from tests.guide_world import plain as guide_plain
from tests.note_to_case_world import ask
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.stuck_question_world import Stuck, StuckAI
from tests.test_google_tasks_work import item, tasks_work
from tests.test_one_task_http import SUB, WEEK_S, App, FakeGoogle
from tests.test_one_task_planning import NOW, make_config, make_session, shown
from tests.test_open_questions import killed_writing
from tests.time_limits_world import RecordingStore

SCHMIDT = "пані Шмідт"
BERLIN = "Europe/Berlin"
LOS_ANGELES = "America/Los_Angeles"
KIRITIMATI = "Pacific/Kiritimati"
TASKS_HEADER = "Задачі без часу:"
NOTHING_TODAY = "На сьогодні в календарі нічого немає."
DOCTOR_LINE = "• 12:00 Лікар"
TODAY = "які плани на сьогодні?"
TOMORROW = "що в мене завтра?"
WEEK_TEXT = "що в мене на цей тиждень?"
NEXT_WEEK = "які плани на наступний тиждень?"
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
WEEK = timedelta(days=7)
WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ------------------------------------------------------------------ helpers: the open


class Factory:
    """The lazy `calendar` argument of the open: counts its calls; returns the calendar or raises."""

    def __init__(self, calendar: object, raises: BaseException | None = None) -> None:
        self.calendar = calendar
        self.raises = raises
        self.calls = 0

    def __call__(self) -> GoogleWork:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return cast(GoogleWork, self.calendar)


def mark_guide_seen(store: InMemoryStore) -> None:
    """The account has already seen the guide (F5 guide, «Перше відкриття»)."""
    store.set(make_session().account_id, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})


def plan_draft(store: InMemoryStore) -> dict[str, Any] | None:
    return store.get(make_session().account_id, planning.DRAFT_PATH)


def open_on(
    store: InMemoryStore, calendar: Factory, now: datetime, config: Any = None
) -> assistant.OpenQuestions:
    return assistant.open_questions(
        make_session(), calendar=calendar, store=store, now=now, config=config or make_config()
    )


def no_planning(result: assistant.OpenQuestions, case_question: bool, guide: bool = False) -> None:
    """Only the guide (on the first open) and the case question «a1», nothing of planning."""
    expected_count = int(guide) + int(case_question)
    assert len(result.replies) == expected_count, result.replies
    for reply in result.replies:
        assert reply.plan is None, reply
        assert reply.question is None or reply.question.kind == "case", reply
    if guide:
        assert is_guide(result.replies[0]), result.replies
    if case_question:
        assert result.replies[-1] == Reply(ask(SCHMIDT), case_q("a1")), result.replies
    assert result.login_needed is False


def with_case_question(store: InMemoryStore) -> None:
    """Copies the pending material «a1» (its case question asks about «пані Шмідт») into `store`."""
    source = Asks()
    source.pending_note("a1", SCHMIDT, NOW - 2 * HOUR)
    account = make_session().account_id
    assert source.session.account_id == account
    for doc_id, doc in source.store.list(account, case_module.MATERIALS):
        store.set(account, f"{case_module.MATERIALS}/{doc_id}", doc)


def stuck_world(*, ask_limits: bool = False, ask_priorities: bool = True) -> Stuck:
    return Stuck(
        StuckAI(), TasksCalendar(honour_409=True), RecordingStore(), ask_limits, ask_priorities, False
    )


# ------------------------------------------------------------------ Seam 1: an open without planning


def test_seam1_fresh_asking_draft_with_a_case_question_gives_only_the_case_question() -> None:
    # add-simply: a timed task of an `add` draft with no time named is asked «коли?» (not its duration).
    w = stuck_world(ask_priorities=False)
    reply = w.add(task(NOTARY, duration_min=None))
    assert reply.question is not None and reply.question.kind == "when", reply
    mark_guide_seen(w.store)
    with_case_question(w.store)
    before = copy.deepcopy(plan_draft(w.store))
    assert before is not None
    calendar = Factory(w.calendar)
    result = open_on(w.store, calendar, NOW + MINUTE, w.config)
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert result.login_needed is False
    assert calendar.calls == 0
    assert plan_draft(w.store) == before


def test_seam1_fresh_week_asking_draft_shows_no_priorities_question_and_keeps_the_draft() -> None:
    w = stuck_world()
    reply = w.plan_week(task(NOTARY), task(MEDICINE))
    assert reply.question is not None and reply.question.kind == "priorities", reply
    mark_guide_seen(w.store)
    with_case_question(w.store)
    before = copy.deepcopy(plan_draft(w.store))
    calendar = Factory(w.calendar)
    result = open_on(w.store, calendar, NOW + MINUTE, w.config)
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert result.login_needed is False
    assert calendar.calls == 0
    assert plan_draft(w.store) == before


def test_seam1_shown_plan_in_horizon_gives_no_plan_and_calls_no_calendar() -> None:
    a = Asks()
    mark_guide_seen(a.store)
    a.pending_note("a1", SCHMIDT, NOW - 2 * HOUR)
    shown(a.plan.start())
    before = copy.deepcopy(plan_draft(a.store))
    calendar = Factory(a.calendar)
    result = open_on(a.store, calendar, NOW + HOUR, a.config)
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert result.login_needed is False
    assert calendar.calls == 0
    assert plan_draft(a.store) == before
    assert a.calendar.insert_calls == []


def test_seam1_login_needed_is_false_when_the_google_sign_in_expired() -> None:
    a = Asks()
    mark_guide_seen(a.store)
    shown(a.plan.start())
    result = open_on(a.store, Factory(a.calendar, LoginExpired()), NOW + MINUTE, a.config)
    assert result.replies == []
    assert result.login_needed is False


class OpenApp(App):
    """The S3 test app with a Calendar factory that counts its calls and may raise."""

    def __init__(self) -> None:
        super().__init__()
        self.raises: BaseException | None = None
        self.factory_calls = 0

        def factory(session: access.Session, started: datetime) -> GoogleWork:
            self.factory_calls += 1
            if self.raises is not None:
                raise self.raises
            return cast(GoogleWork, self.calendar)

        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=factory,
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )


def test_seam1_api_open_with_shown_plan_and_asking_draft_has_no_planning_replies() -> None:
    for duration in (30, None):
        app = OpenApp()
        app.sign_in()
        app.store.set(SUB, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})
        app.start(app.calendar, duration_min=duration)
        before = copy.deepcopy(app.store.get(SUB, planning.DRAFT_PATH))
        assert before is not None
        app.clock.at = NOW + MINUTE
        resp = app.client.get("/api/open")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["replies"] == [], (duration, body)
        assert body["login_needed"] is False
        assert app.factory_calls == 0, duration
        assert app.store.get(SUB, planning.DRAFT_PATH) == before


def test_seam1_api_open_with_expired_google_sign_in_is_not_login_needed() -> None:
    app = OpenApp()
    app.sign_in()
    app.store.set(SUB, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})
    app.start(app.calendar, duration_min=30)
    app.raises = LoginExpired()
    app.clock.at = NOW + MINUTE
    resp = app.client.get("/api/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replies"] == []
    assert body["login_needed"] is False


# ------------------------------------------------------------------ helpers: show


class DueAgenda:
    """Stands in for `GoogleWork` in `schedule.show`: `timezone` answers `tz`, `list_agenda` answers
    `agenda` whatever the window, `list_open_tasks` answers `tasks`. Every call is logged by name."""

    def __init__(self, tz: str, *agenda: AgendaItem, tasks: tuple[TaskItem, ...] = ()) -> None:
        self.tz = tz
        self.agenda = list(agenda)
        self.tasks = list(tasks)
        self.log: list[str] = []

    def timezone(self) -> str:
        self.log.append("timezone")
        return self.tz

    def list_agenda(self, time_min: datetime, time_max: datetime) -> list[AgendaItem]:
        self.log.append("list_agenda")
        return list(self.agenda)

    def list_open_tasks(self) -> list[TaskItem]:
        self.log.append("list_open_tasks")
        return list(self.tasks)

    def insert_event(self, event_id: str, title: str, start: datetime, end: datetime) -> str:
        self.log.append("insert_event")
        return event_id

    def insert_task(self, title: str) -> str:
        self.log.append("insert_task")
        return "new-1"

    def complete_task(self, task_id: str) -> None:
        self.log.append("complete_task")


def doctor_today() -> AgendaItem:
    """11:00Z = 12:00 Berlin on Monday 9 November."""
    return AgendaItem("Лікар", utc(2026, 11, 9, 11), date(2026, 11, 9), False)


def due(day: date | None) -> TaskItem:
    """A task titled by its due date (`без дати` when it has none)."""
    title = f"на {day.isoformat()}" if day is not None else "без дати"
    return TaskItem(f"tk-{title}", title, day)


def lines(reply: Reply) -> list[str]:
    return [" ".join(line.split()) for line in reply.text.splitlines() if line.strip()]


def show(text: str, calendar: DueAgenda, now: datetime) -> Reply:
    return schedule.show(
        make_session(),
        text,
        calendar=cast(GoogleWork, calendar),
        now=now,
        config=replace(make_config(), use_tasks=True),
    )


def task_lines(reply: Reply) -> list[str]:
    """The lines of the tasks section (after its header); [] when there is no section."""
    found = lines(reply)
    if TASKS_HEADER not in found:
        return []
    assert found.count(TASKS_HEADER) == 1, reply.text
    return found[found.index(TASKS_HEADER) + 1 :]


# ------------------------------------------------------------------ Seam 2: tasks by their date


def test_seam2_today_from_midday_shows_the_task_due_today_and_not_yesterday_tomorrow_or_undated() -> None:
    calendar = DueAgenda(
        BERLIN,
        doctor_today(),
        tasks=(due(date(2026, 11, 8)), due(None), due(date(2026, 11, 9)), due(date(2026, 11, 10))),
    )
    reply = show(TODAY, calendar, NOW)
    assert lines(reply) == ["На сьогодні:", DOCTOR_LINE, TASKS_HEADER, "• на 2026-11-09"]


def test_seam2_no_task_dated_in_the_period_means_no_tasks_section() -> None:
    tasks = (due(date(2026, 11, 8)), due(None), due(date(2026, 11, 10)))
    reply = show(TODAY, DueAgenda(BERLIN, doctor_today(), tasks=tasks), NOW)
    assert lines(reply) == ["На сьогодні:", DOCTOR_LINE]
    reply = show(TODAY, DueAgenda(BERLIN, tasks=tasks), NOW)
    assert lines(reply) == [NOTHING_TODAY]


def test_seam2_tasks_in_the_period_keep_the_order_of_the_list() -> None:
    tasks = (
        TaskItem("tk-3", "я купити хліб", date(2026, 11, 9)),
        TaskItem("tk-4", "стара", date(2026, 11, 1)),
        TaskItem("tk-2", "забрати посилку", date(2026, 11, 9)),
        TaskItem("tk-5", "аптека", date(2026, 11, 9)),
    )
    reply = show(TODAY, DueAgenda(BERLIN, doctor_today(), tasks=tasks), NOW)
    assert task_lines(reply) == ["• я купити хліб", "• забрати посилку", "• аптека"]


def test_seam2_tomorrow_shows_only_the_task_due_tomorrow() -> None:
    tasks = (due(date(2026, 11, 9)), due(date(2026, 11, 10)), due(date(2026, 11, 11)), due(None))
    reply = show(TOMORROW, DueAgenda(BERLIN, tasks=tasks), NOW)
    assert task_lines(reply) == ["• на 2026-11-10"]


def test_seam2_week_includes_this_sunday_and_not_next_monday() -> None:
    tasks = (
        due(date(2026, 11, 8)),
        due(date(2026, 11, 9)),
        due(date(2026, 11, 12)),
        due(date(2026, 11, 15)),
        due(date(2026, 11, 16)),
        due(None),
    )
    reply = show(WEEK_TEXT, DueAgenda(BERLIN, doctor_today(), tasks=tasks), NOW)
    assert task_lines(reply) == ["• на 2026-11-09", "• на 2026-11-12", "• на 2026-11-15"]


def test_seam2_day_boundary_is_in_the_calendar_zone_not_utc() -> None:
    tasks = (due(date(2026, 11, 8)), due(date(2026, 11, 9)), due(date(2026, 11, 10)))
    # 23:30Z on Sunday 8 November is 00:30 on Monday 9 November in Berlin.
    reply = show(TODAY, DueAgenda(BERLIN, tasks=tasks), utc(2026, 11, 8, 23, 30))
    assert task_lines(reply) == ["• на 2026-11-09"]
    # 03:00Z on Monday 9 November is 19:00 on Sunday 8 November in Los Angeles.
    reply = show(TODAY, DueAgenda(LOS_ANGELES, tasks=tasks), utc(2026, 11, 9, 3))
    assert task_lines(reply) == ["• на 2026-11-08"]


def test_seam2_list_open_tasks_reads_the_date_of_due() -> None:
    work, _ = tasks_work(
        lambda r: (
            200,
            {
                "items": [
                    item("tk-1", "оплатити світло", due="2026-11-13T00:00:00.000Z"),
                    item("tk-2", "забрати посилку"),
                    item("tk-3", "аптека", due="не дата"),
                ]
            },
        )
    )
    assert work.list_open_tasks() == [
        TaskItem("tk-1", "оплатити світло", date(2026, 11, 13)),
        TaskItem("tk-2", "забрати посилку", None),
        TaskItem("tk-3", "аптека", None),
    ]


# ------------------------------------------------------------------ Seam 3: GET /api/guide


class LoggingStore(InMemoryStore):
    """`InMemoryStore` that logs every write after `watch()`."""

    def __init__(self) -> None:
        super().__init__()
        self.watching = False
        self.writes: list[tuple[str, str]] = []

    def watch(self) -> None:
        self.watching = True

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        if self.watching:
            self.writes.append(("set", path))
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        written = super().transact(account_id, path, decide)
        if self.watching and written is not None:
            self.writes.append(("transact", path))
        return written

    def delete(self, account_id: str, path: str) -> None:
        if self.watching:
            self.writes.append(("delete", path))
        super().delete(account_id, path)


class GuideApp(App):
    """The S3 test app over a store that logs its writes."""

    def __init__(self) -> None:
        super().__init__()
        logging_store = LoggingStore()
        for path in (access.TOKENS_PATH,):
            doc = self.store.get(SUB, path)
            assert doc is not None
            logging_store.set(SUB, path, doc)
        self.store = logging_store
        self.logging = logging_store
        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )


def test_seam3_api_guide_with_session_answers_the_guide_without_question_and_writes_nothing() -> None:
    app = GuideApp()
    app.sign_in()
    app.store.set(SUB, access.PROFILE_PATH, {"language": "uk"})
    app.logging.watch()
    resp = app.client.get("/api/guide")
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert guide_plain(reply["text"]) == GUIDE
    assert reply["text"] == assistant.guide_text("uk")
    assert reply["question"] is None
    assert app.logging.writes == []
    assert app.store.get(SUB, assistant.GUIDE_PATH) is None


def test_seam3_api_guide_under_a_waiting_plan_question_changes_nothing() -> None:
    app = GuideApp()
    app.sign_in()
    app.start(app.calendar, duration_min=None)
    before = copy.deepcopy(app.store.get(SUB, planning.DRAFT_PATH))
    app.logging.watch()
    resp = app.client.get("/api/guide")
    assert resp.status_code == 200, resp.text
    assert guide_plain(resp.json()["reply"]["text"]) == GUIDE
    assert resp.json()["reply"]["question"] is None
    assert app.logging.writes == []
    assert app.store.get(SUB, planning.DRAFT_PATH) == before


def test_seam3_api_guide_without_valid_session_is_401() -> None:
    app = GuideApp()
    resp = app.client.get("/api/guide")
    assert resp.status_code == 401, resp.status_code
    app.sign_in(at=NOW - timedelta(seconds=WEEK_S + 60))
    resp = app.client.get("/api/guide")
    assert resp.status_code == 401, resp.status_code


def test_seam3_page_has_the_help_button_under_the_header() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    button = page.find('id="help"')
    assert button != -1, "no element with id help"
    start = page.rfind("<", 0, button)
    assert page[start : start + 7] == "<button", page[start : button + 20]
    closing = page.find("</button>", button)
    assert "Що я вмію" in page[button:closing]
    header = page.find("<h1")
    assert header != -1 and header < start, "the button does not come after the header"
    conversation = page.find('id="conversation"')
    assert not (conversation < start < page.find("</section>", conversation)), (
        "button inside the conversation"
    )


def test_seam3_conversation_paragraphs_keep_line_breaks() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    styles = page + "".join(p.read_text(encoding="utf-8") for p in WEB.rglob("*.css"))
    rules = [
        block
        for selector, block in _css_rules(styles)
        if "#conversation p" in [part.strip() for part in selector.split(",")]
    ]
    assert any("white-space:pre-line" in block.replace(" ", "") for block in rules), rules


def _css_rules(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    position = 0
    while True:
        opening = text.find("{", position)
        if opening == -1:
            return found
        closing = text.find("}", opening)
        if closing == -1:
            return found
        selector_start = max(text.rfind("}", 0, opening), text.rfind(">", 0, opening)) + 1
        found.append((text[selector_start:opening], text[opening + 1 : closing]))
        position = closing + 1


# ------------------------------------------------------------------ invariants


def test_I1_the_open_never_shows_planning_and_never_changes_the_plan_draft() -> None:
    def cases() -> list[tuple[str, InMemoryStore, object, Any, datetime, BaseException | None]]:
        found: list[tuple[str, InMemoryStore, object, Any, datetime, BaseException | None]] = []
        a = Asks()
        found.append(("no draft", a.store, a.calendar, a.config, NOW + MINUTE, None))
        for age in (MINUTE, 23 * HOUR, 25 * HOUR, 30 * DAY):
            w = stuck_world()
            w.plan_week(task(NOTARY), task(MEDICINE))
            found.append((f"week priorities after {age}", w.store, w.calendar, w.config, NOW + age, None))
            w = stuck_world(ask_limits=True)
            w.add(task(NOTARY))
            found.append((f"add limits after {age}", w.store, w.calendar, w.config, NOW + age, None))
            w = stuck_world(ask_limits=True, ask_priorities=False)
            w.plan_week(task(NOTARY), task(MEDICINE))
            found.append((f"week limits after {age}", w.store, w.calendar, w.config, NOW + age, None))
            w = stuck_world(ask_priorities=False)
            w.plan_week(task(NOTARY, duration_min=None))
            found.append((f"week duration after {age}", w.store, w.calendar, w.config, NOW + age, None))
            w = stuck_world(ask_priorities=False)
            w.add(task(NOTARY, duration_min=None))
            found.append((f"add duration after {age}", w.store, w.calendar, w.config, NOW + age, None))
        w = stuck_world(ask_priorities=False)
        w.plan_week(task(NOTARY, duration_min=None))
        w.forget_asked_at()
        found.append(("week duration without asked_at", w.store, w.calendar, w.config, NOW + MINUTE, None))
        for at, raises in ((NOW + MINUTE, None), (NOW + MINUTE, LoginExpired()), (NOW + WEEK, None)):
            a = Asks()
            shown(a.plan.start())
            found.append((f"shown at {at}, {raises!r}", a.store, a.calendar, a.config, at, raises))
        a = Asks()
        shown(a.plan.start())
        a.calendar.busy(NOW - HOUR, NOW + WEEK + HOUR)
        found.append(("shown, no free time", a.store, a.calendar, a.config, NOW + MINUTE, None))
        a = Asks()
        plan_id, fingerprint = shown(a.plan.start())
        a.plan.confirm(plan_id, fingerprint)
        found.append(("written", a.store, a.calendar, a.config, NOW + MINUTE, None))
        for seconds in (5, 45):
            a = Asks()
            killed_writing(a.plan, created=False)
            a.calendar.on_insert = None
            at = NOW + timedelta(seconds=seconds)
            found.append((f"writing after {seconds}s", a.store, a.calendar, a.config, at, None))
        return found

    for with_case in (False, True):
        for name, store, calendar, config, at, raises in cases():
            if with_case:
                with_case_question(store)
            mark_guide_seen(store)
            before = copy.deepcopy(plan_draft(store))
            for opened in (at, at + MINUTE):
                result = open_on(store, Factory(calendar, raises), opened, config)
                try:
                    no_planning(result, case_question=with_case)
                except AssertionError as error:
                    raise AssertionError(f"{name}, with a case question: {with_case}") from error
                assert plan_draft(store) == before, (name, with_case)

    # The first open: the guide, then the case question; still nothing of planning.
    a = Asks()
    a.pending_note("a1", SCHMIDT, NOW - 2 * HOUR)
    shown(a.plan.start())
    before = copy.deepcopy(plan_draft(a.store))
    result = open_on(a.store, Factory(a.calendar), NOW + MINUTE, a.config)
    no_planning(result, case_question=True, guide=True)
    assert plan_draft(a.store) == before


def test_I2_every_task_in_the_tasks_section_is_due_in_the_period() -> None:
    dates = [
        date(2026, 10, 20),
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 25),
        date(2026, 10, 26),
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 7),
        date(2026, 11, 8),
        date(2026, 11, 9),
        date(2026, 11, 10),
        date(2026, 11, 11),
        date(2026, 11, 15),
        date(2026, 11, 16),
        date(2026, 11, 22),
        date(2026, 11, 23),
    ]
    tasks = tuple(due(d) for d in dates[:8]) + (due(None),) + tuple(due(d) for d in dates[8:])
    # (zone, now, period text, the due dates shown — written by hand, in the order of the list)
    cases: list[tuple[str, datetime, str, list[str]]] = [
        # Monday 9 November, 10:07 Berlin.
        (BERLIN, NOW, TODAY, ["2026-11-09"]),
        (BERLIN, NOW, TOMORROW, ["2026-11-10"]),
        (BERLIN, NOW, WEEK_TEXT, ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-15"]),
        (BERLIN, NOW, NEXT_WEEK, ["2026-11-16", "2026-11-22"]),
        # Sunday 8 November, 19:00 Los Angeles (03:00Z on the 9th): the week is its last day.
        (LOS_ANGELES, utc(2026, 11, 9, 3), TODAY, ["2026-11-08"]),
        (LOS_ANGELES, utc(2026, 11, 9, 3), TOMORROW, ["2026-11-09"]),
        (LOS_ANGELES, utc(2026, 11, 9, 3), WEEK_TEXT, ["2026-11-08"]),
        (
            LOS_ANGELES,
            utc(2026, 11, 9, 3),
            NEXT_WEEK,
            ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-15"],
        ),
        # Tuesday 10 November, 02:00 Kiritimati (12:00Z on the 9th).
        (KIRITIMATI, utc(2026, 11, 9, 12), TODAY, ["2026-11-10"]),
        (KIRITIMATI, utc(2026, 11, 9, 12), TOMORROW, ["2026-11-11"]),
        (KIRITIMATI, utc(2026, 11, 9, 12), WEEK_TEXT, ["2026-11-10", "2026-11-11", "2026-11-15"]),
        (KIRITIMATI, utc(2026, 11, 9, 12), NEXT_WEEK, ["2026-11-16", "2026-11-22"]),
        # Wednesday 21 October, 12:00 Berlin (CEST); the week crosses the switch to CET on Sunday 25.
        (BERLIN, utc(2026, 10, 21, 10), TODAY, ["2026-10-21"]),
        (BERLIN, utc(2026, 10, 21, 10), TOMORROW, ["2026-10-22"]),
        (BERLIN, utc(2026, 10, 21, 10), WEEK_TEXT, ["2026-10-21", "2026-10-22", "2026-10-25"]),
        (BERLIN, utc(2026, 10, 21, 10), NEXT_WEEK, ["2026-10-26", "2026-11-01"]),
        # Sunday 15 November, 23:30 Berlin: today is the last minutes of the week.
        (BERLIN, utc(2026, 11, 15, 22, 30), TODAY, ["2026-11-15"]),
        (BERLIN, utc(2026, 11, 15, 22, 30), WEEK_TEXT, ["2026-11-15"]),
        (BERLIN, utc(2026, 11, 15, 22, 30), NEXT_WEEK, ["2026-11-16", "2026-11-22"]),
    ]
    for zone, now, text, shown_dates in cases:
        for agenda in ((), (doctor_today(),)):
            reply = show(text, DueAgenda(zone, *agenda, tasks=tasks), now)
            expected = [f"• на {d}" for d in shown_dates]
            assert task_lines(reply) == expected, (zone, now, text, agenda, reply.text)
            assert "• без дати" not in lines(reply), (zone, now, text, reply.text)
    # No task dated in the period: no section at all.
    reply = show(TODAY, DueAgenda(BERLIN, tasks=(due(None), due(date(2026, 11, 8)))), NOW)
    assert TASKS_HEADER not in lines(reply), reply.text
