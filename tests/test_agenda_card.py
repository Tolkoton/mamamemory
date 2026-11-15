"""Contract tests of the slice agenda-card: Seam 1 (the schedule card), Seam 2 (the tasks card),
Seam 3 (JSON), Seam 5 (the wiring of `app.js`, the route `/card.js`), the styles of `index.html`, and I1.

Written by the slice tester from the sealed contract `.engine/slices/agenda-card.md`, without the code.
Every expected card is written by hand from the contract. `NOW` is Monday 9 November 2026, 10:07 Berlin
(09:07Z); Europe/Berlin is UTC+1 in November. Whether the JSON keeps the `None` fields inside the card as
`null` is question Q1, tested in `test_agenda_card_disputed.py` only: here such a field is read with `.get`.
"""

import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mamamemory.http.app import _reply_json
from mamamemory.integrations.google_work import DeadlinePassed, TaskItem
from mamamemory.replies import Reply
from tests import show_schedule_world, tasks_list_world
from tests.agenda_card_world import (
    BERLIN,
    NOTHING_ROW,
    NOW,
    TASKS_HEADING,
    Card,
    CardCalendar,
    CardItem,
    CardSection,
    all_day,
    bullets,
    card_bullets,
    config,
    dated,
    lines,
    show,
    timed,
    utc,
)
from tests.read_aloud_world import SpeakApp
from tests.tasks_list_world import ListCalendar, listed
from tests.test_one_message_web import _code_only, _enclosing_openers, _matching, _show_body

TODAY = "які плани на сьогодні?"
TOMORROW = "що в мене завтра?"
WEEK = "що в мене на тиждень?"
NEXT_WEEK = "які плани на наступний тиждень?"
WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"


def vacation_today() -> show_schedule_world.CalEvent:
    """All day on Monday 9 November (Berlin midnights in UTC)."""
    return all_day("Відпустка", utc(2026, 11, 8, 23), utc(2026, 11, 9, 23), date(2026, 11, 9))


def week_events() -> tuple[show_schedule_world.CalEvent, ...]:
    """Tuesday 10: 11:00 Ярмарок, 15:00 Аптека; Thursday 12: all day Бабусин день, 12:30 Банк (Berlin)."""
    return (
        timed("Ярмарок", utc(2026, 11, 10, 10), utc(2026, 11, 10, 11), date(2026, 11, 10)),
        timed("Аптека", utc(2026, 11, 10, 14), utc(2026, 11, 10, 15), date(2026, 11, 10)),
        all_day("Бабусин день", utc(2026, 11, 11, 23), utc(2026, 11, 12, 23), date(2026, 11, 12)),
        timed("Банк", utc(2026, 11, 12, 11, 30), utc(2026, 11, 12, 12), date(2026, 11, 12)),
    )


# ------------------------------------------------------------------ Seam 1: the schedule card


def test_seam1_today_card_has_title_one_untitled_section_in_text_order_and_the_tasks_section() -> None:
    calendar = CardCalendar(
        vacation_today(),
        timed("Лікар", utc(2026, 11, 9, 13), utc(2026, 11, 9, 14), date(2026, 11, 9)),
        tasks=(
            dated("t1", "оплатити світло", date(2026, 11, 9)),
            TaskItem("t2", "без дати"),
            dated("t3", "забрати посилку", date(2026, 11, 10)),
        ),
    )
    reply = show(TODAY, calendar)
    assert lines(reply) == [
        "На сьогодні:",
        "• весь день — Відпустка",
        "• 14:00 Лікар",
        "Задачі без часу:",
        "• оплатити світло",
    ]
    assert reply.card == Card(
        "На сьогодні",
        [
            CardSection(None, [CardItem("весь день", "Відпустка"), CardItem("14:00", "Лікар")]),
            CardSection(TASKS_HEADING, [CardItem(None, "оплатити світло")]),
        ],
    )


def test_seam1_tomorrow_card_has_one_section_without_heading() -> None:
    calendar = CardCalendar(
        timed("Ярмарок", utc(2026, 11, 10, 10), utc(2026, 11, 10, 11), date(2026, 11, 10)),
        all_day("Бабусин день", utc(2026, 11, 9, 23), utc(2026, 11, 10, 23), date(2026, 11, 10)),
    )
    reply = show(TOMORROW, calendar)
    assert reply.card == Card(
        "На завтра",
        [CardSection(None, [CardItem("11:00", "Ярмарок"), CardItem("весь день", "Бабусин день")])],
    )


def test_seam1_week_and_next_week_have_one_section_per_day_with_events_headed_by_the_day() -> None:
    calendar = CardCalendar(*week_events(), tasks=(dated("t1", "забрати посилку", date(2026, 11, 12)),))
    reply = show(WEEK, calendar)
    assert reply.card == Card(
        "На цей тиждень",
        [
            CardSection(
                "Вівторок, 10 листопада", [CardItem("11:00", "Ярмарок"), CardItem("15:00", "Аптека")]
            ),
            CardSection(
                "Четвер, 12 листопада", [CardItem("весь день", "Бабусин день"), CardItem("12:30", "Банк")]
            ),
            CardSection(TASKS_HEADING, [CardItem(None, "забрати посилку")]),
        ],
    )
    # Wednesday 25 November, 10:00 Berlin; next week is Monday 30 November – Sunday 6 December.
    calendar = CardCalendar(
        timed("Пошта", utc(2026, 11, 30, 10), utc(2026, 11, 30, 11), date(2026, 11, 30)),
        timed("Ринок", utc(2026, 12, 1, 10), utc(2026, 12, 1, 11), date(2026, 12, 1)),
    )
    reply = show(NEXT_WEEK, calendar, utc(2026, 11, 25, 9))
    assert reply.card == Card(
        "На наступний тиждень",
        [
            CardSection("Понеділок, 30 листопада", [CardItem("11:00", "Пошта")]),
            CardSection("Вівторок, 1 грудня", [CardItem("11:00", "Ринок")]),
        ],
    )


def test_seam1_no_events_with_tasks_gives_the_nothing_row_then_tasks_and_with_nothing_no_card() -> None:
    tasks = (
        dated("t1", "оплатити світло", date(2026, 11, 9)),
        dated("t2", "забрати посилку", date(2026, 11, 9)),
    )
    reply = show(TODAY, CardCalendar(tasks=tasks))
    assert reply.card == Card(
        "На сьогодні",
        [
            CardSection(None, [NOTHING_ROW]),
            CardSection(
                TASKS_HEADING, [CardItem(None, "оплатити світло"), CardItem(None, "забрати посилку")]
            ),
        ],
    )
    reply = show(WEEK, CardCalendar(tasks=(dated("t3", "пошта", date(2026, 11, 15)),)))
    assert reply.card == Card(
        "На цей тиждень",
        [CardSection(None, [NOTHING_ROW]), CardSection(TASKS_HEADING, [CardItem(None, "пошта")])],
    )
    outside = (TaskItem("t4", "без дати"), dated("t5", "стара", date(2026, 11, 1)))
    expected = {
        TODAY: "На сьогодні в календарі нічого немає.",
        TOMORROW: "На завтра в календарі нічого немає.",
        "що в мене на цей тиждень?": "На цей тиждень в календарі нічого немає.",
        NEXT_WEEK: "На наступний тиждень в календарі нічого немає.",
    }
    for text, answer in expected.items():
        for use_tasks in (True, False):
            reply = show(text, CardCalendar(tasks=outside), use_tasks=use_tasks)
            assert reply.card is None, (text, use_tasks, reply.card)
            assert lines(reply) == [answer], (text, use_tasks, reply.text)


def test_seam1_and_seam2_the_card_reaches_the_reply_of_the_message() -> None:
    calendar = show_schedule_world.AgendaCalendar(BERLIN, *week_events())
    reply = show_schedule_world.message(WEEK, calendar, NOW, config=config(False))
    assert reply.card is not None, reply
    assert reply.card.title == "На цей тиждень"
    assert [s.heading for s in reply.card.sections] == ["Вівторок, 10 листопада", "Четвер, 12 листопада"]
    tasks = ListCalendar(
        TaskItem("t1", "оплатити світло"), dated("t2", "подзвонити нотаріусу", date(2026, 11, 13))
    )
    reply = tasks_list_world.message("Які в мене задачі?", tasks, tasks_list_world.RouteAI("tasks"))
    assert reply.card == Card(
        "Задачі в списку",
        [
            CardSection(
                None,
                [
                    CardItem(None, "оплатити світло"),
                    CardItem(None, "подзвонити нотаріусу", "до 13 листопада"),
                ],
            )
        ],
    )


# ------------------------------------------------------------------ Seam 2: the tasks card


def test_seam2_tasks_card_in_list_order_with_note_only_on_the_dated_task_and_none_otherwise() -> None:
    calendar = ListCalendar(
        TaskItem("t1", "оплатити світло"),
        TaskItem("t2", "подзвонити нотаріусу", date(2026, 11, 13)),
        TaskItem("t3", "забрати посилку"),
    )
    reply = listed(calendar)
    assert lines(reply) == [
        "Задачі в списку:",
        "• оплатити світло",
        "• подзвонити нотаріусу — до 13 листопада",
        "• забрати посилку",
    ]
    assert reply.card == Card(
        "Задачі в списку",
        [
            CardSection(
                None,
                [
                    CardItem(None, "оплатити світло", None),
                    CardItem(None, "подзвонити нотаріусу", "до 13 листопада"),
                    CardItem(None, "забрати посилку", None),
                ],
            )
        ],
    )
    assert listed(ListCalendar()).card is None
    assert listed(ListCalendar(TaskItem("t1", "оплатити світло")), use_tasks=False).card is None
    for error in (
        RuntimeError("tasks down"),
        ValueError("bad json"),
        KeyError("items"),
        DeadlinePassed("GET"),
    ):
        reply = listed(ListCalendar(TaskItem("t1", "оплатити світло"), error=error))
        assert reply.card is None, (error, reply.card)
        assert lines(reply) == ["Не вдалося прочитати задачі, спробуйте ще раз."]


# ------------------------------------------------------------------ Seam 3: JSON


def test_seam3_json_has_no_card_key_without_a_card_and_the_nested_structure_with_one() -> None:
    assert "card" not in _reply_json(Reply("Записала."))
    assert "card" not in _reply_json(show(TODAY, CardCalendar()))

    body = _reply_json(
        listed(
            ListCalendar(TaskItem("t1", "оплатити світло"), TaskItem("t2", "нотаріус", date(2026, 11, 13)))
        )
    )
    card: dict[str, Any] = body["card"]
    assert card["title"] == "Задачі в списку"
    assert len(card["sections"]) == 1
    section = card["sections"][0]
    assert section.get("heading") is None
    items = section["items"]
    assert [(i.get("time"), i["text"], i.get("note")) for i in items] == [
        (None, "оплатити світло", None),
        (None, "нотаріус", "до 13 листопада"),
    ]

    body = _reply_json(show(WEEK, CardCalendar(*week_events())))
    assert body["text"].startswith("На цей тиждень:")
    card = body["card"]
    assert card["title"] == "На цей тиждень"
    assert [s["heading"] for s in card["sections"]] == ["Вівторок, 10 листопада", "Четвер, 12 листопада"]
    assert [(i["time"], i["text"]) for i in card["sections"][1]["items"]] == [
        ("весь день", "Бабусин день"),
        ("12:30", "Банк"),
    ]


# ------------------------------------------------------------------ Seam 5: the wiring


def _app_source() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


def test_seam5_card_js_is_served_like_the_other_scripts() -> None:
    app = SpeakApp(None)
    card = app.client.get("/card.js")
    help_js = app.client.get("/help.js")
    assert help_js.status_code == 200, "the reference script /help.js is not served"
    assert card.status_code == 200
    assert card.headers.get("content-type") == help_js.headers.get("content-type")
    assert card.content == (WEB / "card.js").read_bytes()

    signed_out = TestClient(app.client.app, base_url="https://testserver", follow_redirects=False)
    assert signed_out.get("/card.js").status_code == signed_out.get("/help.js").status_code


def test_seam5_app_js_imports_build_card_from_card_js() -> None:
    imports = re.findall(r"import\s*\{([^}]*)\}\s*from\s*[\"']/card\.js[\"']", _app_source())
    assert any("buildCard" in [name.strip() for name in names.split(",")] for names in imports), (
        "app.js does not import buildCard from /card.js"
    )


def _else_of_a_card_test(code: str, start: int, opener: int) -> bool:
    """`opener` is the `{` of an `else` whose `if` condition names `reply.card` (`if (!reply.card)`)."""
    ifs = list(re.finditer(r"\bif\s*\(", code[start:opener]))
    if not ifs:
        return False
    paren = start + ifs[-1].end() - 1
    return bool(re.search(r"\breply\s*\.\s*card\b", code[paren : _matching(code, paren)]))


def test_seam5_show_appends_build_card_of_reply_card_and_does_not_render_the_text_in_that_branch() -> None:
    source = _app_source()
    code = _code_only(source)
    body_start, body_end = _show_body(code)
    calls = [m.start() for m in re.finditer(r"\bbuildCard\s*\(", code) if body_start < m.start() < body_end]
    assert calls, "show does not call buildCard"
    call = calls[0]
    close = _matching(code, code.index("(", call))
    arguments = code[code.index("(", call) + 1 : close]
    assert re.match(r"\s*reply\s*\.\s*card\s*,", arguments), (
        f"buildCard is not given reply.card: {arguments!r}"
    )

    # The branch: an `if (… reply.card …) {` around the call, or a `reply.card ? buildCard(…) : …`.
    branch: tuple[int, int] | None = None
    for opener in _enclosing_openers(code, body_start + 1, call):
        if code[opener] != "{":
            continue
        head = re.split(r"[;{}]", code[body_start + 1 : opener])[-1]
        if re.search(r"\bif\s*\(.*\breply\s*\.\s*card\b", head, re.S) or (
            re.fullmatch(r"\s*else\s*", head) and _else_of_a_card_test(code, body_start, opener)
        ):
            branch = (opener, _matching(code, opener))
    if branch is None:
        before = re.split(r"[;{}]", code[body_start + 1 : call])[-1]
        assert re.search(r"\breply\s*\.\s*card\s*\?\s*$", before), (
            "buildCard is not called in a branch on reply.card"
        )
    else:
        inside = code[branch[0] : branch[1]]
        assert not re.search(r"\brenderText\s*\(", inside), "renderText is called in the reply.card branch"

    # The result goes to conversation.append: directly, or through the name it is given.
    show_code = code[body_start:body_end]
    direct = re.search(r"\bconversation\s*\.\s*append\s*\(\s*buildCard\s*\(", show_code)
    named = re.search(r"\b(\w+)\s*=\s*(?:[^;=]*\?\s*)?buildCard\s*\(", show_code)
    if not direct:
        assert named, "the result of buildCard is not given to conversation.append"
        name = re.escape(named.group(1))
        assert re.search(rf"\bconversation\s*\.\s*append\s*\(\s*{name}\b", show_code), (
            "the result of buildCard is not given to conversation.append"
        )


def _rule(html: str, selector: str) -> str:
    """The declarations of every rule whose selector list names `selector` itself, joined."""
    bodies = [
        body
        for selectors, body in re.findall(r"([^{}<>]+)\{([^}]*)\}", html)
        if selector in [part.strip() for part in selectors.split(",")]
    ]
    assert bodies, f"index.html has no rule for {selector}"
    return ";".join(bodies)


def test_index_html_styles_the_card_its_time_and_its_note() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    card = _rule(html, ".card")
    assert re.search(r"\bborder(-\w+)?\s*:", card), card
    assert re.search(
        r"\bbackground(-color)?\s*:\s*(#fff\b|#ffffff\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255)", card, re.I
    ), card
    time = _rule(html, ".card-time")
    assert re.search(r"\bfont-weight\s*:\s*(bold|[6-9]00)\b", time), time
    note = _rule(html, ".card-note")
    assert re.search(r"(^|[;\s])color\s*:", note), note


# ------------------------------------------------------------------ I1


def test_I1_the_card_holds_every_event_and_task_of_the_text_once_in_its_order_and_nothing_else() -> None:
    # (text, now, events, tasks, the bullets of the text and of the card — written by hand)
    cases: list[
        tuple[str, Any, tuple[show_schedule_world.CalEvent, ...], tuple[TaskItem, ...], list[str]]
    ] = [
        # Today, Monday 9, 10:07: a vacation all week (shown once), the same title twice, tasks repeated and
        # one with an event's title; tasks of Sunday 8 and Tuesday 10 are outside.
        (
            TODAY,
            NOW,
            (
                all_day("Відпустка", utc(2026, 11, 8, 23), utc(2026, 11, 13, 23), date(2026, 11, 9)),
                timed("Лікар", utc(2026, 11, 9, 13), utc(2026, 11, 9, 14), date(2026, 11, 9)),
                timed("Лікар", utc(2026, 11, 9, 15), utc(2026, 11, 9, 16), date(2026, 11, 9)),
            ),
            (
                dated("t1", "аптека", date(2026, 11, 9)),
                dated("t2", "стара", date(2026, 11, 8)),
                dated("t3", "аптека", date(2026, 11, 9)),
                dated("t4", "Лікар", date(2026, 11, 9)),
                dated("t5", "завтрашня", date(2026, 11, 10)),
            ),
            ["• весь день — Відпустка", "• 14:00 Лікар", "• 16:00 Лікар", "• аптека", "• аптека", "• Лікар"],
        ),
        # The week from Wednesday 11, 10:00: the vacation begun on Monday stands under Wednesday; the same
        # event twice at the same hour; the last minutes of Sunday; tasks of Tuesday 10 and Monday 16 are
        # outside.
        (
            WEEK,
            utc(2026, 11, 11, 9),
            (
                all_day("Відпустка", utc(2026, 11, 8, 23), utc(2026, 11, 13, 23), date(2026, 11, 9)),
                timed("Лікар", utc(2026, 11, 12, 10), utc(2026, 11, 12, 11), date(2026, 11, 12)),
                timed("Лікар", utc(2026, 11, 12, 10), utc(2026, 11, 12, 11), date(2026, 11, 12)),
                timed("Банк", utc(2026, 11, 15, 22, 45), utc(2026, 11, 15, 22, 55), date(2026, 11, 15)),
            ),
            (
                dated("t1", "вчорашня", date(2026, 11, 10)),
                dated("t2", "аптека", date(2026, 11, 11)),
                dated("t3", "пошта", date(2026, 11, 15)),
                dated("t4", "наступна", date(2026, 11, 16)),
            ),
            [
                "• весь день — Відпустка",
                "• 11:00 Лікар",
                "• 11:00 Лікар",
                "• 23:45 Банк",
                "• аптека",
                "• пошта",
            ],
        ),
        # Tomorrow, Tuesday 10: from its first minute to its last hour, an hour under ten.
        (
            TOMORROW,
            NOW,
            (
                timed("Опівніч", utc(2026, 11, 9, 23), utc(2026, 11, 10, 0), date(2026, 11, 10)),
                timed("Ліки", utc(2026, 11, 10, 8, 5), utc(2026, 11, 10, 8, 15), date(2026, 11, 10)),
                timed("Вечір", utc(2026, 11, 10, 22, 30), utc(2026, 11, 10, 22, 45), date(2026, 11, 10)),
            ),
            (dated("t1", "хліб", date(2026, 11, 10)),),
            ["• 00:00 Опівніч", "• 09:05 Ліки", "• 23:30 Вечір", "• хліб"],
        ),
        # Next week, Monday 16 – Sunday 22: an all-day event on its last day, one on Monday 23 outside;
        # tasks dated outside only.
        (
            NEXT_WEEK,
            NOW,
            (
                timed("Пошта", utc(2026, 11, 16, 10), utc(2026, 11, 16, 11), date(2026, 11, 16)),
                all_day("Свято", utc(2026, 11, 21, 23), utc(2026, 11, 22, 23), date(2026, 11, 22)),
                timed("Поза", utc(2026, 11, 23, 10), utc(2026, 11, 23, 11), date(2026, 11, 23)),
            ),
            (dated("t1", "ця", date(2026, 11, 15)), dated("t2", "потім", date(2026, 11, 23))),
            ["• 11:00 Пошта", "• весь день — Свято"],
        ),
        # No event, the same task twice.
        (
            TODAY,
            NOW,
            (),
            (dated("t1", "аптека", date(2026, 11, 9)), dated("t2", "аптека", date(2026, 11, 9))),
            ["• аптека", "• аптека"],
        ),
    ]
    for text, now, events, tasks, expected in cases:
        reply = show(text, CardCalendar(*events, tasks=tasks), now)
        assert bullets(reply) == expected, (text, reply.text)
        assert reply.card is not None, (text, reply.text)
        assert card_bullets(reply.card) == expected, (text, reply.card)
    # Nothing in the period: no bullet in the text, no card.
    reply = show(TODAY, CardCalendar(tasks=(dated("t1", "стара", date(2026, 11, 8)),)))
    assert bullets(reply) == []
    assert reply.card is None
