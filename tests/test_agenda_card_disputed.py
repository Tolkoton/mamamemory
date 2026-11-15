"""Disputed tests of the slice agenda-card: they take one reading of a question to the contract and are sealed
after the slice planner answers it.

Written by the slice tester from the sealed contract `.engine/slices/agenda-card.md`, without the code.

Q1 — «`card` — `None` прибирається з JSON (як `choices`); інакше — `{"title", "sections": [{"heading",
"items": [{"time", "text", "note"}]}]}`»: only `card` itself is said to be dropped when `None`. Reading taken:
inside the card every key named there is present, a `None` value as `null` (`heading`, `time`, `note`).
"""

from datetime import date

from mamamemory.http.app import _reply_json
from mamamemory.integrations.google_work import TaskItem
from tests.agenda_card_world import CardCalendar, dated, show, timed, utc
from tests.tasks_list_world import ListCalendar, listed


def test_q1_none_fields_inside_the_card_are_kept_as_null() -> None:
    body = _reply_json(
        listed(
            ListCalendar(TaskItem("t1", "оплатити світло"), TaskItem("t2", "нотаріус", date(2026, 11, 13)))
        )
    )
    assert body["card"] == {
        "title": "Задачі в списку",
        "sections": [
            {
                "heading": None,
                "items": [
                    {"time": None, "text": "оплатити світло", "note": None},
                    {"time": None, "text": "нотаріус", "note": "до 13 листопада"},
                ],
            }
        ],
    }
    calendar = CardCalendar(
        timed("Лікар", utc(2026, 11, 9, 13), utc(2026, 11, 9, 14), date(2026, 11, 9)),
        tasks=(dated("t1", "аптека", date(2026, 11, 9)),),
    )
    body = _reply_json(show("які плани на сьогодні?", calendar))
    assert body["card"] == {
        "title": "На сьогодні",
        "sections": [
            {"heading": None, "items": [{"time": "14:00", "text": "Лікар", "note": None}]},
            {"heading": "Задачі без часу", "items": [{"time": None, "text": "аптека", "note": None}]},
        ],
    }
