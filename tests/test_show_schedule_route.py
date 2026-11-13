"""Contract tests of the `schedule` intent in `assistant` (slice show-schedule, Seam 3).

Written by the slice tester from the sealed contract `.engine/slices/show-schedule.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z).
"""

from mamamemory import assistant
from mamamemory.replies import Question
from tests.show_schedule_world import (
    AgendaCalendar,
    ScheduleAI,
    WriteLogStore,
    lines,
    message,
    plain,
    timed,
    utc,
)

NOW = utc(2026, 11, 9, 9, 7)
REPLY_TOS: list[Question | None] = [
    None,
    Question("plan", "plan-x", "fp-x"),
    Question("case", "mat-x", None),
    Question("duration", "plan-x", None),
    Question("limits", "plan-x", None),
    Question("priorities", "plan-x", None),
    Question("clarify", "cl-x", None),
]


def test_seam3_schedule_is_in_the_route_schema_for_every_reply_to() -> None:
    assert "schedule" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    for reply_to in REPLY_TOS:
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "schedule" in enum, (reply_to, enum)


def test_seam3_schedule_is_always_allowed() -> None:
    assert "schedule" in assistant.ALWAYS
    for reply_to in REPLY_TOS:
        assert "schedule" in assistant.allowed(reply_to), reply_to


def test_schedule_phrase_names_what_is_planned() -> None:
    assert assistant.PHRASES["schedule"] == "показати, що вже заплановано"


def test_seam3_dispatch_schedule_shows_the_calendar_not_the_planning() -> None:
    calendar = AgendaCalendar(
        "Europe/Berlin",
        timed("Лікар", utc(2026, 11, 10, 9), utc(2026, 11, 10, 10), utc(2026, 11, 10).date()),
    )
    store = WriteLogStore()
    reply = message("що в мене завтра?", calendar, NOW, store=store)
    assert lines(reply) == ["На завтра:", "• 10:00 Лікар"]
    assert reply.question is None and reply.plan is None
    assert "list_open_tasks" not in calendar.log, calendar.log
    assert calendar.writes() == [] and store.writes == []


def test_route_prompt_tells_schedule_from_plan_week() -> None:
    ai = ScheduleAI()
    message("які плани на сьогодні?", AgendaCalendar("Europe/Berlin"), NOW, ai=ai)
    assert ai.prompts.get("route"), ai.prompts
    prompt = plain(ai.prompts["route"][0])
    assert (
        plain(
            "schedule — мама питає, що в неї вже заплановано («які плани на сьогодні?», «що в мене на "
            "тиждень?», «що в мене завтра?»)"
        )
        in prompt
    ), prompt
    assert plain("plan_week — лише коли просить спланувати («сплануй тиждень», «давай планувати»)") in prompt
    assert prompt.count("що в мене на тиждень") == 1, prompt
