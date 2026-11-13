"""Contract tests of `planning.schedule` (slice show-schedule, Seams 1 and 2, invariants I1 and I2).

Written by the slice tester from the sealed contract `.engine/slices/show-schedule.md`, without the code.
Every instant is written by hand in UTC. Europe/Berlin is UTC+1 in November and UTC+2 until Sunday
25 October 2026, 03:00. The exact end of a day (Q1), the hour's padding (Q2), whether empty days are listed
(Q3) and the exact line breaks (Q4) are tested in `test_show_schedule_disputed.py` only: here a period's
end is checked to within one second, hours are 10 and later, and only days that carry an event are compared.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, cast

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from mamamemory.integrations.google_work import GoogleWork
from mamamemory.planning import schedule
from mamamemory.replies import Question
from tests.show_schedule_world import (
    AgendaCalendar,
    ScheduleAI,
    WriteLogStore,
    all_day,
    bullets,
    count_title,
    lines,
    message,
    sections,
    show,
    timed,
    utc,
)
from tests.test_one_task_google_work import CALL_TIMEOUT_S, Answer, Clock, Transport, path, query
from tests.test_one_task_planning import make_config, make_session

BERLIN = "Europe/Berlin"
SUNDAY_2330_BERLIN = utc(2026, 11, 15, 22, 30)
"""Sunday 15 November 2026, 23:30 in Berlin (22:30Z)."""
ONE_SECOND = timedelta(seconds=1)


def ends_at(found: datetime, end: datetime) -> None:
    """The period ends at `end` (the next local midnight), to within one second (Q1 fixes it exactly)."""
    assert end - ONE_SECOND <= found <= end, f"period ends at {found!r}, expected about {end!r}"


# ------------------------------------------------------------------ period


def test_period_is_tomorrow_when_the_text_says_zavtra() -> None:
    assert schedule.period("що в мене завтра?") == "tomorrow"
    assert schedule.period("Завтра які плани?") == "tomorrow"
    assert schedule.period("а ЗАВТРА що?") == "tomorrow"


def test_period_is_next_week_with_nastupn_and_tyzhd() -> None:
    assert schedule.period("які плани на наступний тиждень?") == "next_week"
    assert schedule.period("що в мене наступного тижня") == "next_week"
    assert schedule.period("Наступного Тижня що заплановано?") == "next_week"


def test_period_is_week_with_tyzhd_or_tyzhn() -> None:
    assert schedule.period("що в мене на тиждень?") == "week"
    assert schedule.period("які в нас плани на поточний тиждень?") == "week"
    assert schedule.period("що в мене цього тижня?") == "week"
    assert schedule.period("що в мене на цей тиждень?") == "week"


def test_period_is_today_otherwise() -> None:
    assert schedule.period("які плани на сьогодні?") == "today"
    assert schedule.period("що в мене заплановано?") == "today"
    assert schedule.period("") == "today"


def test_seam2_pisliazavtra_is_today_not_tomorrow() -> None:
    assert schedule.period("що в мене післязавтра?") == "today"
    assert schedule.period("Післязавтра які плани?") == "today"


# ------------------------------------------------------------------ Seam 1: the period's bounds in the zone


def test_seam1_today_runs_from_now_to_end_of_day_in_calendar_zone() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Вечеря", utc(2026, 11, 15, 19), utc(2026, 11, 15, 20), date(2026, 11, 15)),
        timed("Дзвінок сестрі", utc(2026, 11, 15, 22, 45), utc(2026, 11, 15, 22, 55), date(2026, 11, 15)),
        timed("Лікар", utc(2026, 11, 16, 9), utc(2026, 11, 16, 10), date(2026, 11, 16)),
    )
    reply = show("які плани на сьогодні?", calendar, SUNDAY_2330_BERLIN)
    time_min, time_max = calendar.window()
    assert time_min == SUNDAY_2330_BERLIN
    ends_at(time_max, utc(2026, 11, 15, 23))
    assert lines(reply) == ["На сьогодні:", "• 23:45 Дзвінок сестрі"]
    assert reply.question is None


def test_seam1_tomorrow_is_the_whole_next_day_in_calendar_zone() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Дзвінок сестрі", utc(2026, 11, 15, 22, 45), utc(2026, 11, 15, 22, 55), date(2026, 11, 15)),
        timed("Лікар", utc(2026, 11, 16, 9), utc(2026, 11, 16, 10), date(2026, 11, 16)),
        timed("Вечірній дзвінок", utc(2026, 11, 16, 21, 30), utc(2026, 11, 16, 21, 45), date(2026, 11, 16)),
        timed("Перукар", utc(2026, 11, 16, 23, 30), utc(2026, 11, 17, 0, 30), date(2026, 11, 17)),
    )
    reply = show("що в мене завтра?", calendar, SUNDAY_2330_BERLIN)
    time_min, time_max = calendar.window()
    assert time_min == utc(2026, 11, 15, 23)
    ends_at(time_max, utc(2026, 11, 16, 23))
    assert lines(reply) == ["На завтра:", "• 10:00 Лікар", "• 22:30 Вечірній дзвінок"]
    assert reply.question is None


def test_seam1_week_ends_this_sunday_in_calendar_zone() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Дзвінок сестрі", utc(2026, 11, 15, 22, 45), utc(2026, 11, 15, 22, 55), date(2026, 11, 15)),
        timed("Нічний рейс", utc(2026, 11, 15, 23, 30), utc(2026, 11, 16, 1), date(2026, 11, 16)),
        timed("Лікар", utc(2026, 11, 16, 9), utc(2026, 11, 16, 10), date(2026, 11, 16)),
    )
    reply = show("що в мене на цей тиждень?", calendar, SUNDAY_2330_BERLIN)
    time_min, time_max = calendar.window()
    assert time_min == SUNDAY_2330_BERLIN
    ends_at(time_max, utc(2026, 11, 15, 23))
    assert lines(reply)[0] == "На цей тиждень:"
    assert sections(reply) == [("Неділя, 15 листопада:", ["• 23:45 Дзвінок сестрі"])]
    assert reply.question is None


def test_seam1_next_week_runs_monday_to_sunday_of_next_week_in_calendar_zone() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Дзвінок сестрі", utc(2026, 11, 15, 22, 45), utc(2026, 11, 15, 22, 55), date(2026, 11, 15)),
        timed("Лікар", utc(2026, 11, 16, 9), utc(2026, 11, 16, 10), date(2026, 11, 16)),
        all_day("Відпустка", utc(2026, 11, 17, 23), utc(2026, 11, 18, 23), date(2026, 11, 18)),
        timed("Пізній дзвінок", utc(2026, 11, 22, 21, 30), utc(2026, 11, 22, 21, 45), date(2026, 11, 22)),
        timed("Нотаріус", utc(2026, 11, 23, 9), utc(2026, 11, 23, 10), date(2026, 11, 23)),
    )
    reply = show("які плани на наступний тиждень?", calendar, SUNDAY_2330_BERLIN)
    time_min, time_max = calendar.window()
    assert time_min == utc(2026, 11, 15, 23)
    ends_at(time_max, utc(2026, 11, 22, 23))
    assert lines(reply)[0] == "На наступний тиждень:"
    assert sections(reply) == [
        ("Понеділок, 16 листопада:", ["• 10:00 Лікар"]),
        ("Середа, 18 листопада:", ["• весь день — Відпустка"]),
        ("Неділя, 22 листопада:", ["• 22:30 Пізній дзвінок"]),
    ]
    assert reply.question is None


# ------------------------------------------------------------------ Seam 2: the events in the reply


def test_seam2_all_day_and_untitled_events_are_shown() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        all_day("Відпустка", utc(2026, 11, 9, 23), utc(2026, 11, 10, 23), date(2026, 11, 10)),
        timed("(без назви)", utc(2026, 11, 10, 10), utc(2026, 11, 10, 11), date(2026, 11, 10)),
    )
    reply = show("що в мене завтра?", calendar, utc(2026, 11, 9, 9, 7))
    assert lines(reply) == ["На завтра:", "• весь день — Відпустка", "• 11:00 (без назви)"]


def test_seam2_event_begun_before_the_period_stands_under_its_first_day() -> None:
    # Wednesday 11 November, 10:00 Berlin. The vacation runs Monday 9 – Friday 13; the conference began
    # Tuesday 10, 09:00 and ends Thursday 12, 17:00.
    calendar = AgendaCalendar(
        BERLIN,
        all_day("Відпустка", utc(2026, 11, 8, 23), utc(2026, 11, 13, 23), date(2026, 11, 9)),
        timed("Конференція", utc(2026, 11, 10, 8), utc(2026, 11, 12, 16), date(2026, 11, 10)),
        timed("Лікар", utc(2026, 11, 12, 10), utc(2026, 11, 12, 11), date(2026, 11, 12)),
    )
    reply = show("що в мене на тиждень?", calendar, utc(2026, 11, 11, 9))
    found = sections(reply)
    assert [day for day, _ in found] == ["Середа, 11 листопада:", "Четвер, 12 листопада:"]
    wednesday = found[0][1]
    assert wednesday[0] == "• весь день — Відпустка"
    assert len(wednesday) == 2 and wednesday[1].endswith(" Конференція"), wednesday
    assert found[1][1] == ["• 11:00 Лікар"]
    today = show("які плани на сьогодні?", calendar, utc(2026, 11, 11, 9))
    assert lines(today)[:2] == ["На сьогодні:", "• весь день — Відпустка"]
    assert count_title(today, "Конференція") == 1


def test_seam2_events_keep_calendar_order_by_day_and_within_a_day() -> None:
    # Monday 9 November, 10:07 Berlin; the order is the one Calendar gives (`orderBy=startTime`).
    calendar = AgendaCalendar(
        BERLIN,
        timed("Ярмарок", utc(2026, 11, 10, 10), utc(2026, 11, 10, 11), date(2026, 11, 10)),
        timed("Аптека", utc(2026, 11, 10, 14), utc(2026, 11, 10, 15), date(2026, 11, 10)),
        all_day("Бабусин день", utc(2026, 11, 11, 23), utc(2026, 11, 12, 23), date(2026, 11, 12)),
        timed("Банк", utc(2026, 11, 12, 11, 30), utc(2026, 11, 12, 12), date(2026, 11, 12)),
    )
    reply = show("що в мене на тиждень?", calendar, utc(2026, 11, 9, 9, 7))
    assert sections(reply) == [
        ("Вівторок, 10 листопада:", ["• 11:00 Ярмарок", "• 15:00 Аптека"]),
        ("Четвер, 12 листопада:", ["• весь день — Бабусин день", "• 12:30 Банк"]),
    ]


def test_day_line_names_weekday_and_date_in_genitive_across_month() -> None:
    # Wednesday 25 November, 10:00 Berlin; next week is Monday 30 November – Sunday 6 December.
    calendar = AgendaCalendar(
        BERLIN,
        timed("Пошта", utc(2026, 11, 30, 10), utc(2026, 11, 30, 11), date(2026, 11, 30)),
        timed("Ринок", utc(2026, 12, 1, 10), utc(2026, 12, 1, 11), date(2026, 12, 1)),
        timed("Банк", utc(2026, 12, 2, 10), utc(2026, 12, 2, 11), date(2026, 12, 2)),
        timed("Лікар", utc(2026, 12, 3, 10), utc(2026, 12, 3, 11), date(2026, 12, 3)),
        timed("Нотаріус", utc(2026, 12, 4, 10), utc(2026, 12, 4, 11), date(2026, 12, 4)),
        timed("Театр", utc(2026, 12, 5, 17), utc(2026, 12, 5, 20), date(2026, 12, 5)),
        timed("Обід у сестри", utc(2026, 12, 6, 12), utc(2026, 12, 6, 14), date(2026, 12, 6)),
    )
    reply = show("які плани на наступний тиждень?", calendar, utc(2026, 11, 25, 9))
    assert sections(reply) == [
        ("Понеділок, 30 листопада:", ["• 11:00 Пошта"]),
        ("Вівторок, 1 грудня:", ["• 11:00 Ринок"]),
        ("Середа, 2 грудня:", ["• 11:00 Банк"]),
        ("Четвер, 3 грудня:", ["• 11:00 Лікар"]),
        ("П'ятниця, 4 грудня:", ["• 11:00 Нотаріус"]),
        ("Субота, 5 грудня:", ["• 18:00 Театр"]),
        ("Неділя, 6 грудня:", ["• 13:00 Обід у сестри"]),
    ]


def test_no_events_says_nothing_in_calendar_for_each_period() -> None:
    now = utc(2026, 11, 9, 9, 7)
    expected = {
        "які плани на сьогодні?": "На сьогодні в календарі нічого немає.",
        "що в мене завтра?": "На завтра в календарі нічого немає.",
        "що в мене на цей тиждень?": "На цей тиждень в календарі нічого немає.",
        "які плани на наступний тиждень?": "На наступний тиждень в календарі нічого немає.",
    }
    for text, answer in expected.items():
        reply = show(text, AgendaCalendar(BERLIN), now)
        assert lines(reply) == [answer], (text, reply.text)
        assert reply.question is None
        assert reply.plan is None


# ------------------------------------------------------------------ I1


PERIOD_TEXTS = {
    "які плани на сьогодні?": "На сьогодні:",
    "що в мене завтра?": "На завтра:",
    "що в мене на тиждень?": "На цей тиждень:",
    "які плани на наступний тиждень?": "На наступний тиждень:",
}


def test_I1_schedule_writes_nothing_but_the_dismissal_of_an_asking_week_draft() -> None:
    # Superseded by plans-not-questions: reading Google Tasks is now part of the reply (when `use_tasks`);
    # writing to Calendar or Tasks is not, and Firestore gets nothing but the deletion of the week draft
    # «питаю» (`dismiss_asking`) under a `priorities` / `limits` reply_to — that exception is held by the
    # tests of plans-not-questions; the reply_tos here are none of those two, so nothing is written at all.
    # Monday 9 November, 10:07 Berlin; an event on every day of this week and the next.
    now = utc(2026, 11, 9, 9, 7)
    events = [
        timed(f"Справа {d}", utc(2026, 11, d, 10), utc(2026, 11, d, 11), date(2026, 11, d))
        for d in range(9, 23)
    ] + [all_day("Відпустка", utc(2026, 11, 9, 23), utc(2026, 11, 11, 23), date(2026, 11, 10))]
    reply_tos: list[Question | None] = [
        None,
        Question("plan", "plan-x", "fp-x"),
        Question("case", "mat-x", None),
    ]
    configs = [make_config(), replace(make_config(), use_tasks=True)]
    for config in configs:
        for reply_to in reply_tos:
            for text, header in PERIOD_TEXTS.items():
                calendar = AgendaCalendar(BERLIN, *events)
                store = WriteLogStore()
                reply = message(
                    text, calendar, now, reply_to=reply_to, ai=ScheduleAI(), store=store, config=config
                )
                where = (config.use_tasks, reply_to, text)
                assert lines(reply)[0] == header, (where, reply.text)
                assert calendar.writes() == [], (where, calendar.log)
                assert store.writes == [], (where, store.writes)
                assert reply.question is None and reply.plan is None
    for config in configs:
        for text in [*PERIOD_TEXTS, "що в мене заплановано?", "що в мене післязавтра?"]:
            calendar = AgendaCalendar(BERLIN)
            schedule.show(make_session(), text, calendar=cast(GoogleWork, calendar), now=now, config=config)
            assert calendar.writes() == [], (config.use_tasks, text, calendar.log)


# ------------------------------------------------------------------ I2


def expect_exactly(
    texts: dict[str, set[str]], calendar_of: Callable[[], object], now: datetime, all_titles: set[str]
) -> None:
    """For every text: each title of `inside` stands on exactly one bullet line, every other title on none."""
    for text, inside in texts.items():
        calendar = cast(GoogleWork, calendar_of())
        reply = schedule.show(make_session(), text, calendar=calendar, now=now, config=make_config())
        for title in sorted(all_titles):
            want = 1 if title in inside else 0
            assert count_title(reply, title) == want, (text, title, reply.text)
        assert len(bullets(reply)) == len(inside), (text, reply.text)


def berlin_dst_week() -> AgendaCalendar:
    # Wednesday 21 October 2026, 12:00 Berlin (CEST, 10:00Z). Berlin turns to CET on Sunday 25 at 03:00.
    return AgendaCalendar(
        BERLIN,
        all_day("Вчора", utc(2026, 10, 19, 22), utc(2026, 10, 20, 22), date(2026, 10, 20)),
        timed("Ранковий", utc(2026, 10, 21, 7), utc(2026, 10, 21, 8), date(2026, 10, 21)),
        timed("Триває", utc(2026, 10, 21, 9), utc(2026, 10, 21, 11), date(2026, 10, 21)),
        timed("Вечір", utc(2026, 10, 21, 21, 30), utc(2026, 10, 21, 21, 45), date(2026, 10, 21)),
        timed("Опівночі", utc(2026, 10, 21, 22, 30), utc(2026, 10, 21, 23), date(2026, 10, 22)),
        all_day("Відпустка", utc(2026, 10, 22, 22), utc(2026, 10, 24, 22), date(2026, 10, 23)),
        timed("Неділя пізно", utc(2026, 10, 25, 22, 30), utc(2026, 10, 25, 22, 50), date(2026, 10, 25)),
        timed("Понеділок рано", utc(2026, 10, 25, 23, 30), utc(2026, 10, 26, 0), date(2026, 10, 26)),
        timed("(без назви)", utc(2026, 11, 1, 9), utc(2026, 11, 1, 10), date(2026, 11, 1)),
        timed("Далеко", utc(2026, 11, 2, 9), utc(2026, 11, 2, 10), date(2026, 11, 2)),
    )


def kiritimati() -> AgendaCalendar:
    # Pacific/Kiritimati is UTC+14: Monday 9 November, 09:07Z is Monday 23:07 there.
    return AgendaCalendar(
        "Pacific/Kiritimati",
        all_day("Багатоденна", utc(2026, 11, 7, 10), utc(2026, 11, 10, 10), date(2026, 11, 8)),
        timed("Ніч", utc(2026, 11, 9, 9, 30), utc(2026, 11, 9, 9, 45), date(2026, 11, 9)),
        timed("Вівторок", utc(2026, 11, 9, 20), utc(2026, 11, 9, 21), date(2026, 11, 10)),
        timed("Наступний понеділок", utc(2026, 11, 15, 19), utc(2026, 11, 15, 20), date(2026, 11, 16)),
    )


def ny(
    event_id: str, summary: str | None, start: dict[str, str], end: dict[str, str], *, cancelled: bool = False
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": event_id,
        "status": "cancelled" if cancelled else "confirmed",
        "start": start,
        "end": end,
    }
    if summary is not None:
        raw["summary"] = summary
    return raw


def at(local: str) -> dict[str, str]:
    return {"dateTime": local}


NEW_YORK_EVENTS: list[tuple[dict[str, Any], datetime, datetime]] = [
    # Sunday 15 November, 23:30 in New York (EST, UTC-5) is Monday 16, 04:30Z. Each raw event with its
    # interval in UTC, written by hand.
    (
        ny("b1", "Пізно", at("2026-11-15T23:45:00-05:00"), at("2026-11-15T23:55:00-05:00")),
        utc(2026, 11, 16, 4, 45),
        utc(2026, 11, 16, 4, 55),
    ),
    (
        ny("b5", "Свято", {"date": "2026-11-16"}, {"date": "2026-11-17"}),
        utc(2026, 11, 16, 5),
        utc(2026, 11, 17, 5),
    ),
    (
        ny("b2", "Понеділок", at("2026-11-16T08:00:00-05:00"), at("2026-11-16T09:00:00-05:00")),
        utc(2026, 11, 16, 13),
        utc(2026, 11, 16, 14),
    ),
    (
        ny("b6", None, at("2026-11-16T12:00:00-05:00"), at("2026-11-16T13:00:00-05:00")),
        utc(2026, 11, 16, 17),
        utc(2026, 11, 16, 18),
    ),
    (
        ny(
            "b7",
            "Скасоване",
            at("2026-11-16T15:00:00-05:00"),
            at("2026-11-16T16:00:00-05:00"),
            cancelled=True,
        ),
        utc(2026, 11, 16, 20),
        utc(2026, 11, 16, 21),
    ),
    (
        ny("b3", "Неділя наступна", at("2026-11-22T22:00:00-05:00"), at("2026-11-22T23:00:00-05:00")),
        utc(2026, 11, 23, 3),
        utc(2026, 11, 23, 4),
    ),
    (
        ny("b4", "Понеділок через тиждень", at("2026-11-23T00:30:00-05:00"), at("2026-11-23T01:00:00-05:00")),
        utc(2026, 11, 23, 5, 30),
        utc(2026, 11, 23, 6),
    ),
]


def new_york_google() -> GoogleWork:
    """A real `GoogleWork` over a stand-in Calendar in America/New_York that filters by `timeMin`/`timeMax`
    and pages two items at a time."""

    def route(request: requests.PreparedRequest) -> Answer:
        if path(request).endswith("/settings/timezone"):
            return 200, {"kind": "calendar#setting", "id": "timezone", "value": "America/New_York"}
        q = query(request)
        low = datetime.fromisoformat(q["timeMin"][0])
        high = datetime.fromisoformat(q["timeMax"][0])
        inside = [raw for raw, begin, end in NEW_YORK_EVENTS if end > low and begin < high]
        offset = int(q.get("pageToken", ["0"])[0])
        page: dict[str, Any] = {"timeZone": "America/New_York", "items": inside[offset : offset + 2]}
        if offset + 2 < len(inside):
            page["nextPageToken"] = str(offset + 2)
        return 200, page

    now = utc(2026, 11, 16, 4, 30)
    session = AuthorizedSession(Credentials("at-test"))
    session.mount("https://www.googleapis.com/", Transport(route))
    return GoogleWork(
        session, call_timeout_s=CALL_TIMEOUT_S, deadline=now + timedelta(seconds=60), now=Clock(now)
    )


def test_I2_every_event_of_the_period_once_and_none_outside() -> None:
    berlin_texts = {
        "які плани на сьогодні?": {"Триває", "Вечір"},
        "що в мене завтра?": {"Опівночі"},
        "що в мене на цей тиждень?": {"Триває", "Вечір", "Опівночі", "Відпустка", "Неділя пізно"},
        "які плани на наступний тиждень?": {"Понеділок рано", "(без назви)"},
    }
    berlin_titles = {
        "Вчора", "Ранковий", "Триває", "Вечір", "Опівночі", "Відпустка", "Неділя пізно",
        "Понеділок рано", "(без назви)", "Далеко",
    }  # fmt: skip
    expect_exactly(berlin_texts, berlin_dst_week, utc(2026, 10, 21, 10), berlin_titles)

    kiritimati_texts = {
        "які плани на сьогодні?": {"Ніч", "Багатоденна"},
        "що в мене завтра?": {"Вівторок", "Багатоденна"},
        "що в мене на тиждень?": {"Ніч", "Вівторок", "Багатоденна"},
        "що в мене наступного тижня?": {"Наступний понеділок"},
    }
    kiritimati_titles = {"Багатоденна", "Ніч", "Вівторок", "Наступний понеділок"}
    expect_exactly(kiritimati_texts, kiritimati, utc(2026, 11, 9, 9, 7), kiritimati_titles)

    new_york_texts = {
        "які плани на сьогодні?": {"Пізно"},
        "що в мене завтра?": {"Свято", "Понеділок", "(без назви)"},
        "що в мене на тиждень?": {"Пізно"},
        "які плани на наступний тиждень?": {"Свято", "Понеділок", "(без назви)", "Неділя наступна"},
    }
    new_york_titles = {
        "Пізно", "Свято", "Понеділок", "(без назви)", "Скасоване", "Неділя наступна",
        "Понеділок через тиждень",
    }  # fmt: skip
    expect_exactly(new_york_texts, new_york_google, utc(2026, 11, 16, 4, 30), new_york_titles)
