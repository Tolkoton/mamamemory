"""Contract tests of the slice tasks-list: Seam 1 (the list), Seam 2 (the route), the guide line, I1.

Written by the slice tester from the sealed contract `.engine/slices/tasks-list.md`, without the code.
Every expected text is written by hand from the contract.
"""

from datetime import date

import pytest

from mamamemory import assistant
from mamamemory.integrations.google_work import DeadlinePassed, TaskItem
from mamamemory.replies import Question
from tests.tasks_list_world import ListCalendar, RouteAI, WriteLogStore, lines, listed, message, plain

HEADER = "Задачі в списку:"
EMPTY = "Відкритих задач немає."
FAILED = "Не вдалося прочитати задачі, спробуйте ще раз."
OFF = "Список задач вимкнено."
GUIDE_LINE = "• «Які в мене задачі?» — покажу список задач."
HINT = (
    "tasks — мама питає про свої задачі чи список справ без періоду («які в мене задачі?», «що в списку "
    "справ?», «покажи задачі»); з періодом («на сьогодні», «на тиждень») — schedule; нова задача — new_task; "
    "«список справ» тут — задачі, не recall (не про справу-людину)"
)
REPLY_TOS: list[Question | None] = [
    None,
    Question("plan", "plan-x", "fp-x"),
    Question("case", "mat-x", None),
    Question("duration", "plan-x", None),
    Question("limits", "plan-x", None),
    Question("priorities", "plan-x", None),
    Question("clarify", "cl-x", None),
]


# ------------------------------------------------------------------ Seam 1: the list


def test_seam1_tasks_with_and_without_due_are_listed_in_list_order() -> None:
    calendar = ListCalendar(
        TaskItem("t1", "оплатити світло"),
        TaskItem("t2", "подзвонити нотаріусу", date(2026, 11, 13)),
        TaskItem("t3", "забрати посилку"),
    )
    reply = listed(calendar)
    assert lines(reply) == [
        HEADER,
        "• оплатити світло",
        "• подзвонити нотаріусу — до 13 листопада",
        "• забрати посилку",
    ]
    assert calendar.writes() == []


def test_seam1_due_is_day_and_month_in_the_genitive() -> None:
    months = (
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
    )  # fmt: skip
    calendar = ListCalendar(
        *(TaskItem(f"t{m}", f"задача {m}", date(2026, m, 1 if m % 2 else 28)) for m in range(1, 13))
    )
    expected = [HEADER] + [f"• задача {m} — до {1 if m % 2 else 28} {months[m - 1]}" for m in range(1, 13)]
    assert lines(listed(calendar)) == expected


def test_seam1_no_open_tasks_says_so() -> None:
    calendar = ListCalendar()
    assert lines(listed(calendar)) == [EMPTY]
    assert calendar.writes() == []


@pytest.mark.parametrize(
    "error",
    [RuntimeError("tasks down"), ValueError("bad json"), KeyError("items"), DeadlinePassed("GET tasks")],
)
def test_seam1_any_error_of_list_open_tasks_gives_the_failure_text(error: Exception) -> None:
    calendar = ListCalendar(TaskItem("t1", "оплатити світло"), error=error)
    assert lines(listed(calendar)) == [FAILED]
    assert calendar.writes() == []


def test_seam1_use_tasks_off_says_the_list_is_off_and_does_not_read_tasks() -> None:
    calendar = ListCalendar(TaskItem("t1", "оплатити світло"))
    assert lines(listed(calendar, use_tasks=False)) == [OFF]
    assert "list_open_tasks" not in calendar.log, calendar.log
    assert calendar.writes() == []


# ------------------------------------------------------------------ Seam 2: the route


def test_seam2_tasks_is_in_the_route_schema_for_every_reply_to() -> None:
    assert "tasks" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    for reply_to in REPLY_TOS:
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "tasks" in enum, (reply_to, enum)


def test_seam2_tasks_is_always_allowed() -> None:
    assert "tasks" in assistant.ALWAYS
    for reply_to in REPLY_TOS:
        assert "tasks" in assistant.allowed(reply_to), reply_to


def test_tasks_phrase_is_show_the_list_of_tasks() -> None:
    assert assistant.PHRASES["tasks"] == "показати список задач"


def test_seam2_route_tasks_returns_the_list() -> None:
    calendar = ListCalendar(
        TaskItem("t1", "оплатити світло"),
        TaskItem("t2", "подзвонити нотаріусу", date(2026, 11, 13)),
    )
    store = WriteLogStore()
    reply = message("Які в мене задачі?", calendar, RouteAI("tasks"), store=store)
    assert lines(reply) == [HEADER, "• оплатити світло", "• подзвонити нотаріусу — до 13 листопада"]
    assert calendar.writes() == []


def test_route_prompt_carries_the_tasks_hint() -> None:
    ai = RouteAI("other")
    message("щось", ListCalendar(), ai)
    assert ai.prompts.get("route"), ai.prompts
    assert plain(HINT) in plain(ai.prompts["route"][-1])


# ------------------------------------------------------------------ the guide


def test_guide_names_the_tasks_phrase_before_the_speaker_line() -> None:
    guide = [plain(line) for line in assistant.GUIDE_UK.splitlines()]
    assert plain(GUIDE_LINE) in guide, guide
    speaker = next(i for i, line in enumerate(guide) if "🔊" in line)
    assert guide.index(plain(GUIDE_LINE)) < speaker, guide


# ------------------------------------------------------------------ invariants


def test_I1_every_open_task_is_listed_exactly_once_in_list_order_and_nothing_is_written() -> None:
    cases: list[tuple[list[TaskItem], list[str]]] = [
        ([], [EMPTY]),
        ([TaskItem("a", "купити хліб")], [HEADER, "• купити хліб"]),
        ([TaskItem("a", "купити хліб", date(2026, 12, 3))], [HEADER, "• купити хліб — до 3 грудня"]),
        (
            [
                TaskItem("a", "купити хліб"),
                TaskItem("b", "купити хліб"),
                TaskItem("c", "оплатити світло", date(2026, 11, 14)),
                TaskItem("d", "купити хліб", date(2026, 11, 14)),
                TaskItem("e", "забрати посилку"),
            ],
            [
                HEADER,
                "• купити хліб",
                "• купити хліб",
                "• оплатити світло — до 14 листопада",
                "• купити хліб — до 14 листопада",
                "• забрати посилку",
            ],
        ),
        (
            [TaskItem(f"k{i}", f"справа {i}") for i in range(1, 13)],
            [HEADER, *(f"• справа {i}" for i in range(1, 13))],
        ),
    ]
    for tasks, expected in cases:
        calendar = ListCalendar(*tasks)
        assert lines(listed(calendar)) == expected, tasks
        assert calendar.writes() == [], calendar.log
        assert calendar.log.count("list_open_tasks") == 1, calendar.log
