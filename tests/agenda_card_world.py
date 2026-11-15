"""Test helpers of the slice agenda-card: a calendar fake with events (overlap with the window, as
`show_schedule_world.AgendaCalendar`) and open tasks, the calls of `schedule.show` / `schedule.tasks` with
`use_tasks` on, and the rows of a card made back into the bullet lines of the text.

Written by the slice tester from the sealed contract `.engine/slices/agenda-card.md`, without the code.
November 2026: Monday 9, Sunday 15, Monday 16, Sunday 22, Monday 30; Europe/Berlin is UTC+1 in November.
"""

from dataclasses import replace
from datetime import date, datetime
from typing import cast

from mamamemory.config import Config
from mamamemory.integrations.google_work import GoogleWork, TaskItem
from mamamemory.planning import schedule
from mamamemory.replies import Card, CardItem, CardSection, Reply
from tests.show_schedule_world import AgendaCalendar, CalEvent, all_day, bullets, lines, timed, utc
from tests.test_one_task_planning import make_config, make_session

__all__ = [
    "BERLIN",
    "NOW",
    "TASKS_HEADING",
    "NOTHING_ROW",
    "CardCalendar",
    "Card",
    "CardItem",
    "CardSection",
    "all_day",
    "bullets",
    "card_bullets",
    "config",
    "dated",
    "lines",
    "show",
    "timed",
    "utc",
]

BERLIN = "Europe/Berlin"
NOW = utc(2026, 11, 9, 9, 7)
"""Monday 9 November 2026, 10:07 Berlin."""
TASKS_HEADING = "Задачі без часу"
NOTHING_ROW = CardItem(None, "В календарі нічого немає.")


class CardCalendar(AgendaCalendar):
    """`AgendaCalendar` whose `list_open_tasks` returns the tasks it was given, in that order."""

    def __init__(self, *events: CalEvent, tasks: tuple[TaskItem, ...] = (), tz: str = BERLIN) -> None:
        super().__init__(tz, *events)
        self.tasks = list(tasks)

    def list_open_tasks(self) -> list[TaskItem]:
        self.log.append("list_open_tasks")
        return list(self.tasks)


def dated(task_id: str, title: str, due: date) -> TaskItem:
    return TaskItem(task_id, title, due)


def config(use_tasks: bool = True) -> Config:
    return replace(make_config(), use_tasks=use_tasks)


def show(text: str, calendar: CardCalendar, now: datetime = NOW, *, use_tasks: bool = True) -> Reply:
    return schedule.show(
        make_session(), text, calendar=cast(GoogleWork, calendar), now=now, config=config(use_tasks)
    )


def card_bullets(card: Card) -> list[str]:
    """Every event and task row of the card as the bullet line the text writes for it, in card order:
    `• весь день — <назва>`, `• <час> <назва>`, a task `• <назва>`. The row «В календарі нічого немає.» of a
    reply with tasks and no events is not an event and is left out."""
    found: list[str] = []
    for section in card.sections:
        for item in section.items:
            if section.heading == TASKS_HEADING:
                found.append(f"• {item.text}")
            elif item == NOTHING_ROW:
                continue
            elif item.time == "весь день":
                found.append(f"• весь день — {item.text}")
            else:
                found.append(f"• {item.time} {item.text}")
    return [" ".join(line.split()) for line in found]
