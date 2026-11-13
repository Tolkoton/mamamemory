"""Disputed tests of `planning.schedule` (slice show-schedule): each fixes one reading of a question to the
contract and waits for the slice planner's answer before it is sealed.

Written by the slice tester from the sealed contract `.engine/slices/show-schedule.md`, without the code.
Q1 — «до кінця дня»: the period ends exactly at the next local midnight (Calendar's `timeMax` is exclusive).
Q2 — «• 10:00 Лікар»: an hour under 10 is written with two digits («09:05»).
Q3 — «далі по днях»: a day of week / next_week with no event gets no day line.
Q4 — the reply's lines are joined by one line break, no blank lines.
Q5 — «завтра» together with «тиждень»: the contract's first rule wins, `tomorrow`.
"""

from datetime import date

from mamamemory.planning import schedule
from tests.show_schedule_world import AgendaCalendar, all_day, plain, show, timed, utc

BERLIN = "Europe/Berlin"
SUNDAY_2330_BERLIN = utc(2026, 11, 15, 22, 30)


def test_q1_period_ends_exactly_at_the_next_local_midnight() -> None:
    for text, end in [
        ("які плани на сьогодні?", utc(2026, 11, 15, 23)),
        ("що в мене завтра?", utc(2026, 11, 16, 23)),
        ("що в мене на цей тиждень?", utc(2026, 11, 15, 23)),
        ("які плани на наступний тиждень?", utc(2026, 11, 22, 23)),
    ]:
        calendar = AgendaCalendar(BERLIN)
        show(text, calendar, SUNDAY_2330_BERLIN)
        assert calendar.window()[1] == end, (text, calendar.windows)


def test_q2_hour_under_ten_has_two_digits() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Ліки", utc(2026, 11, 10, 8, 5), utc(2026, 11, 10, 8, 15), date(2026, 11, 10)),
    )
    reply = show("що в мене завтра?", calendar, utc(2026, 11, 9, 9, 7))
    assert "• 09:05 Ліки" in reply.text, reply.text


def test_q3_days_without_events_get_no_day_line() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        timed("Лікар", utc(2026, 11, 10, 9), utc(2026, 11, 10, 10), date(2026, 11, 10)),
        timed("Банк", utc(2026, 11, 13, 10), utc(2026, 11, 13, 11), date(2026, 11, 13)),
    )
    reply = show("що в мене на тиждень?", calendar, utc(2026, 11, 9, 9, 7))
    assert [plain(line) for line in reply.text.splitlines() if line.strip()] == [
        "На цей тиждень:",
        "Вівторок, 10 листопада:",
        "• 10:00 Лікар",
        "П'ятниця, 13 листопада:",
        "• 11:00 Банк",
    ]


def test_q4_lines_are_joined_by_single_line_breaks() -> None:
    calendar = AgendaCalendar(
        BERLIN,
        all_day("Відпустка", utc(2026, 11, 9, 23), utc(2026, 11, 10, 23), date(2026, 11, 10)),
        timed("Лікар", utc(2026, 11, 10, 9), utc(2026, 11, 10, 10), date(2026, 11, 10)),
        timed("Банк", utc(2026, 11, 11, 10), utc(2026, 11, 11, 11), date(2026, 11, 11)),
    )
    today = show("що в мене завтра?", calendar, utc(2026, 11, 9, 9, 7))
    assert today.text.strip() == "На завтра:\n• весь день — Відпустка\n• 10:00 Лікар"
    week = show("що в мене на тиждень?", calendar, utc(2026, 11, 9, 9, 7))
    assert week.text.strip() == (
        "На цей тиждень:\nВівторок, 10 листопада:\n• весь день — Відпустка\n• 10:00 Лікар\n"
        "Середа, 11 листопада:\n• 11:00 Банк"
    )


def test_q5_zavtra_wins_over_tyzhden() -> None:
    assert schedule.period("що в мене завтра і на тиждень?") == "tomorrow"
    assert schedule.period("завтра чи наступного тижня?") == "tomorrow"
