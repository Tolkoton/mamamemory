"""Contract tests of the slice case-questions: `cases.decline_case`, `cases.leave_without_case`,
`cases.choose_case`, `cases.open_questions`, the route of the answers to a case question,
`planning.OpenQuestion.at` and `assistant.open_questions` over cases and plan.

Seam 1 (answers), Seam 2 (the newest of all modules), Seam 3 (one question per material), Seam 4
(separate accounts), I1, I2, I3. Written by the slice tester from the sealed contract
`.engine/slices/case-questions.md`, without the code. The separator between a question's text and the
line «Ще N …» is not fixed by the contract: the tests read only that the text starts with the question and
ends with the line. Two open items never share an `at` unless a test says so (I3 has one tie).

Superseded by guide («Перше відкриття»): an account without `settings/guide_shown` gets the guide first on
the open; the tests of `assistant.open_questions` hold the other sources, so their account has already seen
the guide (`guide_seen`).

Superseded by calm-open: `assistant.open_questions` reads no plan — no plan reply, no «увійди знову»,
`login_needed` always `False`, the calendar is not called and the plan draft is not changed; the case
questions, their order and the line «Ще N …» are as before, now counting the case questions only.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import requests

from mamamemory import assistant, cases, planning
from mamamemory.errors import LoginExpired
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Reply
from tests.case_questions_world import LEFT, WHICH, Asks, Lazy, case_q, question_replies
from tests.note_to_case_world import NOT_ACTUAL, ask, placed
from tests.photo_and_file_world import PDF, PNG, READ_TEXT, Uploads
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.test_one_task_planning import NO_FREE_TIME, NOW, World, shown, world
from tests.voice_edits_world import editing

KOCH = "пан Кох"
SCHMIDT = "пані Шмідт"
FISCHER = "пан Фішер"
WEEK = timedelta(days=7)
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)


def guide_seen(a: Asks) -> Asks:
    """The account has already seen the guide (F5 guide, «Перше відкриття»): the mark is in the store."""
    a.store.set(a.session.account_id, assistant.GUIDE_PATH, {"shown": "2026-11-01T09:00:00+00:00"})
    return a


def seeded() -> tuple[Asks, cases.Case]:
    """A world with one case made the S1 way; its name is read from the case returned."""
    world_ = Asks()
    first = world_.seed(KOCH, "k0")
    return world_, first


def open_plan(w: World, now: datetime) -> planning.OpenQuestion | None:
    return planning.open_question(
        w.session, calendar=Lazy(w.calendar), store=w.store, now=now, config=w.config
    )


def plan_at(w: World, now: datetime) -> datetime | None:
    found = open_plan(w, now)
    assert found is not None, "expected an open plan question"
    return found.at


def plan_draft(a: Asks) -> dict[str, Any] | None:
    """The plan draft as it lies in the store (calm-open: the open never changes it)."""
    return a.store.get(a.session.account_id, planning.DRAFT_PATH)


class Counted:
    """The `calendar` argument of the open that counts its calls (calm-open: the open never calls it)."""

    def __init__(self, a: Asks) -> None:
        self.inner = Lazy(a.calendar)
        self.calls = 0

    def __call__(self) -> GoogleWork:
        self.calls += 1
        return self.inner()


# ------------------------------------------------------------------ decline_case (Seam 1)


def test_decline_of_a_pending_material_asks_which_and_keeps_the_proposed_name() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    reply = a.decline("a1")
    assert reply == Reply(WHICH, case_q("a1"))
    material = a.material("a1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "which", doc
    assert [c.name for c in a.cases()] == [first.name]


def test_decline_of_a_material_that_is_not_pending_is_not_actual() -> None:
    a, first = seeded()
    a.ai.file_to(first.name)
    a.add("нотатка про Коха", "p1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1")
    a.ai.fail["classify_case"] = 1
    a.try_add("нотатка, що впала", "n1")
    for material_id in ("p1", "u1", "n1", "nope"):
        assert a.decline(material_id).text == NOT_ACTUAL, material_id
    assert a.material("p1").state == "placed"
    assert a.material("u1").state == "unplaced"
    assert a.material("n1").state == "new"


# ------------------------------------------------------------------ leave_without_case (Seam 1)


def test_leave_of_a_pending_material_leaves_it_without_case_and_keeps_its_text() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.pending_note("b1", FISCHER)
    a.decline("b1")
    for material_id in ("a1", "b1"):
        text = a.material(material_id).text
        reply = a.leave(material_id)
        assert reply == Reply(LEFT), material_id
        material = a.material(material_id)
        assert material.state == "unplaced", material_id
        assert material.pending_case is None, material_id
        assert material.case_id is None, material_id
        assert material.text == text, material_id
        doc = a.doc(material_id)
        assert doc is not None and doc.get("asked") is None, doc
    assert [c.name for c in a.cases()] == [first.name]


def test_leave_of_a_material_that_is_not_pending_is_not_actual() -> None:
    a, first = seeded()
    a.ai.file_to(first.name)
    a.add("нотатка про Коха", "p1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1")
    for material_id in ("p1", "u1", "nope"):
        assert a.leave(material_id).text == NOT_ACTUAL, material_id
    assert a.material("p1").state == "placed"
    assert a.material("p1").case_id == first.case_id


# ------------------------------------------------------------------ choose_case (Seam 1)


def test_choose_a_listed_case_places_the_material_there_and_describes_it() -> None:
    a, first = seeded()
    schmidt = a.seed(SCHMIDT, "m0")
    a.pending_note("a1", FISCHER)
    a.decline("a1")
    described = a.ai.count("describe_case")
    a.ai.file_to(first.name)
    reply = a.choose("a1", "до Коха")
    assert reply == Reply(placed(first.name))
    prompt = a.ai.prompts["classify_case"][-1]
    assert "до Коха" in prompt
    assert first.name in prompt and schmidt.name in prompt
    material = a.material("a1")
    assert material.state == "placed"
    assert material.case_id == first.case_id
    assert material.pending_case is None
    assert material.in_description is True
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") is None, doc
    assert a.ai.count("describe_case") == described + 1
    assert sorted(c.name for c in a.cases()) == sorted([first.name, SCHMIDT])


def test_choose_the_proposed_name_in_another_case_on_create_is_like_yes() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.ai.new_case("ПАНІ ШМІДТ")
    reply = a.choose("a1", "так, до пані Шмідт")
    assert reply == Reply(placed(SCHMIDT))
    made = [c for c in a.cases() if c.name == SCHMIDT]
    assert len(made) == 1
    assert len(a.cases()) == 2
    assert a.material("a1").state == "placed"
    assert a.material("a1").case_id == made[0].case_id


def test_choose_another_new_name_asks_to_create_it_and_yes_creates_it() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.pending_note("b1", "пані Маєр")
    a.decline("b1")
    for material_id in ("a1", "b1"):
        a.ai.new_case(FISCHER)
        reply = a.choose(material_id, "до пана Фішера")
        assert reply == Reply(ask(FISCHER), case_q(material_id)), material_id
        material = a.material(material_id)
        assert material.state == "pending", material_id
        assert material.pending_case == FISCHER, material_id
        doc = a.doc(material_id)
        assert doc is not None and doc.get("asked") == "create", doc
    assert [c.name for c in a.cases()] == [first.name]
    assert a.yes("a1").text == placed(FISCHER)
    assert sorted(c.name for c in a.cases()) == sorted([first.name, FISCHER])
    assert a.material("a1").state == "placed"


def test_choose_with_nothing_named_on_which_asks_which_again_without_change() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.nowhere()
    reply = a.choose("a1", "не знаю")
    assert reply == Reply(WHICH, case_q("a1"))
    material = a.material("a1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "which", doc
    assert [c.name for c in a.cases()] == [first.name]


def test_choose_on_an_empty_catalogue_names_the_case_from_the_reply() -> None:
    a = Asks()
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.default_name = KOCH
    reply = a.choose("a1", "до пана Коха")
    assert reply == Reply(ask(KOCH), case_q("a1"))
    assert "до пана Коха" in a.ai.prompts["name_case"][-1]
    assert a.ai.count("classify_case") == 0
    material = a.material("a1")
    assert material.state == "pending"
    assert material.pending_case == KOCH
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "create", doc
    assert a.cases() == []
    assert a.yes("a1").text == placed(KOCH)
    assert [c.name for c in a.cases()] == [KOCH]


def test_choose_on_an_empty_catalogue_without_a_name_asks_which_again() -> None:
    a = Asks()
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.nameless = True
    reply = a.choose("a1", "не знаю куди")
    assert reply == Reply(WHICH, case_q("a1"))
    assert a.material("a1").state == "pending"
    assert a.cases() == []


def test_choose_on_a_material_that_is_not_pending_is_not_actual() -> None:
    a, first = seeded()
    a.ai.file_to(first.name)
    a.add("нотатка про Коха", "p1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1")
    for material_id in ("p1", "u1", "nope"):
        a.ai.new_case(FISCHER)
        assert a.choose(material_id, "до пана Фішера").text == NOT_ACTUAL, material_id
    assert a.material("p1").case_id == first.case_id
    assert a.material("u1").state == "unplaced"
    assert [c.name for c in a.cases()] == [first.name]


# ------------------------------------------------------------------ the route (Seam 1)


def test_no_with_reply_to_case_asks_which() -> None:
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT)
    a.ai.intent = "no"
    reply = a.message("ні", "w1", reply_to=case_q("a1"))
    assert reply == Reply(WHICH, case_q("a1"))
    assert a.material("a1").state == "pending"
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "which", doc


def test_not_needed_with_reply_to_case_leaves_the_material_without_case() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.ai.intent = "not_needed"
    reply = a.message("не треба", "w1", reply_to=case_q("a1"))
    assert reply == Reply(LEFT)
    assert a.material("a1").state == "unplaced"
    assert [c.name for c in a.cases()] == [first.name]


def test_case_name_with_reply_to_case_places_by_the_message_text() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.ai.intent = "no"
    assert a.message("ні", "w1", reply_to=case_q("a1")) == Reply(WHICH, case_q("a1"))
    a.ai.intent = "case_name"
    a.ai.file_to(first.name)
    reply = a.message("до Коха", "w2", reply_to=case_q("a1"))
    assert reply.text == placed(first.name)
    assert "до Коха" in a.ai.prompts["classify_case"][-1]
    assert a.material("a1").state == "placed"
    assert a.material("a1").case_id == first.case_id


def test_yes_on_which_repeats_the_question_without_change() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.intent = "yes"
    reply = a.message("так", "w1", reply_to=case_q("a1"))
    assert reply == Reply(WHICH, case_q("a1"))
    material = a.material("a1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "which", doc
    assert [c.name for c in a.cases()] == [first.name]


def test_route_prompt_for_a_which_question_names_which() -> None:
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.intent = "other"
    a.message("щось", "w1", reply_to=case_q("a1"))
    prompt = a.ai.prompts["route"][-1]
    assert f"Асистент спитав «{WHICH}»" in prompt
    assert f"Асистент спитав «{ask(SCHMIDT)}»" not in prompt


def test_answers_to_a_question_of_a_material_no_longer_pending_go_by_its_state() -> None:
    a, first = seeded()
    a.ai.file_to(first.name)
    a.add("нотатка про Коха", "p1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1")
    for intent, text in (("no", "ні"), ("not_needed", "не треба"), ("case_name", "до пана Фішера")):
        for material_id in ("p1", "u1", "nope"):
            a.ai.intent = intent
            a.ai.new_case(FISCHER)
            reply = a.message(text, f"w-{intent}-{material_id}", reply_to=case_q(material_id))
            assert reply.text == NOT_ACTUAL, (intent, material_id)
    a.ai.intent = "yes"
    assert a.message("так", "w-yes", reply_to=case_q("p1")).text == placed(first.name)
    assert a.material("p1").case_id == first.case_id
    assert a.material("u1").state == "unplaced"
    assert [c.name for c in a.cases()] == [first.name]


def test_repeat_of_a_note_asked_which_answers_which() -> None:
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT)
    text = a.material("a1").text
    a.decline("a1")
    again = a.add(text, "a1")
    assert again == Reply(WHICH, case_q("a1"))
    assert len([m for m in a.materials() if m.material_id == "a1"]) == 1


# ------------------------------------------------------------------ cases.open_questions


def test_case_open_questions_are_one_per_pending_material_with_its_time_and_text() -> None:
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT, NOW + MINUTE)
    a.pending_note("b1", FISCHER, NOW + 2 * MINUTE)
    a.decline("b1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1", NOW + 3 * MINUTE)
    found = sorted(
        ((q.reply.question.id if q.reply.question else "", q.reply, q.at) for q in a.case_questions()),
        key=lambda item: item[0],
    )
    assert found == [
        ("a1", Reply(ask(SCHMIDT), case_q("a1")), NOW + MINUTE),
        ("b1", Reply(WHICH, case_q("b1")), NOW + 2 * MINUTE),
    ]


def test_a_pending_material_without_asked_reads_as_create() -> None:
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT)
    doc = a.doc("a1")
    assert doc is not None
    old = dict(doc)
    old.pop("asked", None)
    a.store.set(a.session.account_id, "materials/a1", old)
    assert [q.reply for q in a.case_questions()] == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert a.decline("a1") == Reply(WHICH, case_q("a1"))


# ------------------------------------------------------------------ planning.OpenQuestion.at


def test_plan_at_is_the_time_of_the_new_task_and_a_reopen_keeps_it() -> None:
    w = world()
    shown(w.start())
    assert plan_at(w, NOW + HOUR) == NOW
    assert plan_at(w, NOW + 2 * HOUR) == NOW


def test_plan_at_moves_to_the_answer_of_the_short_question() -> None:
    w = world(duration_min=None)
    asked = w.start().question
    assert asked is not None
    assert plan_at(w, NOW + MINUTE) == NOW
    shown(w.answer(asked.id, now=NOW + 10 * MINUTE))
    assert plan_at(w, NOW + HOUR) == NOW + 10 * MINUTE


def test_plan_at_moves_to_the_edit() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    shown(w.edit(plan_id, "move", NOTARY, day="2026-11-12", now=NOW + 20 * MINUTE))
    found = w.opened(NOW + HOUR)
    assert found is not None
    assert found.at == NOW + 20 * MINUTE


def test_plan_at_is_not_changed_by_the_recount_on_yes() -> None:
    w = world()
    plan_id, fingerprint = shown(w.start())
    w.calendar.busy(datetime(2026, 11, 9, 9, 0, tzinfo=UTC), datetime(2026, 11, 9, 11, 0, tzinfo=UTC))
    recount = w.confirm(plan_id, fingerprint, now=NOW + 5 * MINUTE)
    assert recount.plan is not None, recount
    assert plan_at(w, NOW + HOUR) == NOW


def test_plan_at_of_a_draft_without_asked_at_is_its_first_show() -> None:
    w = world()
    shown(w.start())
    draft = w.store.get(w.session.account_id, planning.DRAFT_PATH)
    assert draft is not None
    old = dict(draft)
    old.pop("asked_at", None)
    w.store.set(w.session.account_id, planning.DRAFT_PATH, old)
    assert plan_at(w, NOW + HOUR) == NOW
    assert plan_at(w, NOW + 2 * HOUR) == NOW


# ------------------------------------------------------------------ assistant.open_questions (Seam 2)


def test_open_with_two_materials_and_a_newer_plan_shows_the_newest_case_question_and_one_waiting() -> None:
    a = guide_seen(Asks())
    a.pending_note("a1", SCHMIDT, NOW - 2 * HOUR)
    a.pending_note("b1", FISCHER, NOW - HOUR)
    shown(a.plan.start())
    draft = plan_draft(a)
    calendar = Counted(a)
    result = a.open_all(NOW + HOUR, calendar=calendar)
    assert len(result.replies) == 1, result.replies
    newest = result.replies[0]
    assert newest.question == case_q("b1")
    assert newest.plan is None
    assert newest.text.startswith(ask(FISCHER))
    assert newest.text.endswith("Ще 1 питання чекає."), newest.text
    assert result.login_needed is False
    assert calendar.calls == 0
    assert plan_draft(a) == draft


def test_open_with_a_material_newer_than_the_plan_shows_only_the_case_question_after_reopens() -> None:
    a = guide_seen(Asks())
    shown(a.plan.start())
    a.pending_note("a1", SCHMIDT, NOW + 30 * MINUTE)
    draft = plan_draft(a)
    for opened in (NOW + HOUR, NOW + 2 * HOUR):
        result = a.open_all(opened)
        assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))], (opened, result.replies)
        assert plan_draft(a) == draft, opened


def test_open_with_no_free_time_for_the_plan_shows_only_the_case_question() -> None:
    a = guide_seen(Asks())
    a.pending_note("a1", SCHMIDT, NOW - HOUR)
    shown(a.plan.start())
    a.calendar.busy(NOW - HOUR, NOW + WEEK + HOUR)
    calendar = Counted(a)
    result = a.open_all(NOW + MINUTE, calendar=calendar)
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert all(r.text != NO_FREE_TIME for r in result.replies)
    assert calendar.calls == 0


def test_open_does_not_ask_to_sign_in_again_and_login_needed_is_false() -> None:
    a = guide_seen(Asks())
    a.pending_note("a1", SCHMIDT, NOW - HOUR)
    shown(a.plan.start())
    result = a.open_all(NOW + MINUTE, LoginExpired())
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert result.login_needed is False
    assert result.failed == []


def test_open_with_a_broken_calendar_keeps_the_case_questions_and_fails_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = guide_seen(Asks())
    a.pending_note("a1", SCHMIDT, NOW - HOUR)
    a.pending_note("b1", FISCHER, NOW - 30 * MINUTE)
    shown(a.plan.start())

    def broken(time_min: datetime, time_max: datetime) -> list[object]:
        raise requests.HTTPError("fake: 500 Backend Error")

    monkeypatch.setattr(a.calendar, "list_events", broken)
    result = a.open_all(NOW + MINUTE)
    assert len(result.replies) == 1, result.replies
    newest = result.replies[0]
    assert newest.question == case_q("b1")
    assert newest.text.startswith(ask(FISCHER))
    assert newest.text.endswith("Ще 1 питання чекає."), newest.text
    assert result.failed == []


def test_open_case_failure_shows_no_plan() -> None:
    a = guide_seen(Asks())
    shown(a.plan.start())
    a.pending_note("a1", SCHMIDT, NOW + HOUR)
    draft = plan_draft(a)
    a.store.broken = True
    result = a.open_all(NOW + 2 * HOUR)
    assert result.replies == []
    assert len(result.failed) == 1
    assert result.login_needed is False
    assert plan_draft(a) == draft


def test_open_waiting_line_takes_the_form_of_its_number() -> None:
    lines = {
        1: "Ще 1 питання чекає.",
        2: "Ще 2 питання чекають.",
        4: "Ще 4 питання чекають.",
        5: "Ще 5 питань чекають.",
        11: "Ще 11 питань чекають.",
        12: "Ще 12 питань чекають.",
        14: "Ще 14 питань чекають.",
        21: "Ще 21 питання чекає.",
        22: "Ще 22 питання чекають.",
        25: "Ще 25 питань чекають.",
    }
    for rest, line in lines.items():
        a = guide_seen(Asks())
        for i in range(rest + 1):
            a.pending_note(f"n{i}", f"справа {i}", NOW + i * MINUTE)
        result = a.open_all(NOW + timedelta(days=1))
        assert len(result.replies) == 1, (rest, result.replies)
        newest = result.replies[0]
        assert newest.question == case_q(f"n{rest}"), rest
        assert newest.text.startswith(ask(f"справа {rest}")), (rest, newest.text)
        assert newest.text.endswith(line), (rest, newest.text)


def test_open_without_pending_materials_shows_nothing_of_the_plan() -> None:
    a, first = seeded()
    guide_seen(a)
    a.ai.file_to(first.name)
    a.add("нотатка про Коха", "p1")
    a.ai.nowhere()
    a.add("щось незрозуміле", "u1")
    a.ai.task["duration_min"] = None
    asked = a.plan.start().question
    assert asked is not None
    draft = plan_draft(a)
    result = a.open_all(NOW + MINUTE)
    assert result.replies == []
    assert result.login_needed is False
    assert result.failed == []
    assert plan_draft(a) == draft


# ------------------------------------------------------------------ one question per material (Seam 3)


def test_each_material_keeps_its_own_question_and_its_reply_to_acts_on_it() -> None:
    a, first = seeded()
    a.pending_note("a1", SCHMIDT, NOW + MINUTE)
    a.pending_note("b1", FISCHER, NOW + 2 * MINUTE)
    assert sorted((q.reply.text, q.reply.question) for q in a.case_questions()) == sorted(
        [(ask(SCHMIDT), case_q("a1")), (ask(FISCHER), case_q("b1"))]
    )
    a.ai.intent = "yes"
    assert a.message("так", "w1", reply_to=case_q("a1")).text == placed(SCHMIDT)
    assert a.material("b1").state == "pending"
    assert a.material("b1").pending_case == FISCHER
    assert [q.reply for q in a.case_questions()] == [Reply(ask(FISCHER), case_q("b1"))]
    a.ai.intent = "no"
    assert a.message("ні", "w2", reply_to=case_q("b1")) == Reply(WHICH, case_q("b1"))
    assert [q.reply for q in a.case_questions()] == [Reply(WHICH, case_q("b1"))]
    assert sorted(c.name for c in a.cases()) == sorted([first.name, SCHMIDT])


# ------------------------------------------------------------------ separate accounts (Seam 4)


def test_questions_of_another_account_are_neither_shown_nor_answered() -> None:
    mama, first = seeded()
    mama.pending_note("a1", SCHMIDT)
    other = guide_seen(mama.other_account("acc-2"))
    assert other.case_questions() == []
    assert other.open_all(NOW + MINUTE).replies == []
    assert other.decline("a1").text == NOT_ACTUAL
    assert other.leave("a1").text == NOT_ACTUAL
    mama.ai.file_to(first.name)
    assert other.choose("a1", "до Коха").text == NOT_ACTUAL
    for intent in ("no", "not_needed", "case_name"):
        other.ai.intent = intent
        assert other.message("ні", f"o-{intent}", reply_to=case_q("a1")).text == NOT_ACTUAL, intent
    assert mama.material("a1").state == "pending"
    assert mama.material("a1").pending_case == SCHMIDT
    assert [q.reply for q in mama.case_questions()] == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert other.materials() == []
    assert other.cases() == []


# ------------------------------------------------------------------ invariants


def test_I1_every_pending_material_has_exactly_one_open_question() -> None:
    a, first = seeded()
    assert a.question_ids() == []
    a.pending_note("a1", SCHMIDT, NOW + MINUTE)
    a.pending_note("b1", FISCHER, NOW + 2 * MINUTE)
    a.pending_note("c1", "пані Маєр", NOW + 3 * MINUTE)
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.decline("a1")
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.decline("a1")
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.open_all(NOW + HOUR)
    a.open_all(NOW + 2 * HOUR)
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.ai.nowhere()
    a.choose("a1", "не знаю")
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.ai.new_case("пан Бауер")
    a.choose("a1", "до пана Бауера")
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.decline("b1")
    a.ai.intent = "yes"
    a.message("так", "w1", reply_to=case_q("b1"))
    assert a.question_ids() == ["a1", "b1", "c1"]
    a.ai.file_to(first.name)
    a.choose("b1", "до Коха")
    assert a.question_ids() == ["a1", "c1"]
    a.yes("a1")
    a.yes("a1")
    assert a.question_ids() == ["c1"]
    a.leave("c1")
    a.decline("c1")
    a.leave("c1")
    assert a.question_ids() == []
    a.pending_note("d1", "пані Ланг", NOW + 4 * MINUTE)
    a.add(a.material("d1").text, "d1", NOW + 4 * MINUTE)
    a.decline("d1")
    a.add(a.material("d1").text, "d1", NOW + 4 * MINUTE)
    assert a.question_ids() == ["d1"]
    result = a.open_all(NOW + 3 * HOUR)
    assert question_replies(result.replies) == [Reply(WHICH, case_q("d1"))]


def test_I2_no_and_not_needed_never_delete_the_material_its_text_or_its_original() -> None:
    up = Uploads()
    up.add("f1", PNG, "image/png")
    up.add("f2", PDF, "application/pdf")
    notes = up.notes
    notes.ai.new_case(SCHMIDT)
    notes.add("нотатка про пані Шмідт", "t1")
    kept = {m.material_id: (m.kind, m.text, m.gs_uri) for m in up.materials()}
    assert set(kept) == {"f1", "f2", "t1"}
    assert kept["f1"][1] == READ_TEXT
    for material_id in ("f1", "f2", "t1"):
        assert up.material(material_id).state == "pending", material_id
    objects = dict(up.files.objects)
    s = up.session

    def unchanged() -> None:
        now_kept = {m.material_id: (m.kind, m.text, m.gs_uri) for m in up.materials()}
        assert now_kept == kept
        assert up.files.objects == objects
        for material_id in kept:
            assert up.store.get(s.account_id, f"materials/{material_id}") is not None, material_id

    cases.decline_case(s, "f1", store=up.store)
    unchanged()
    cases.decline_case(s, "f1", store=up.store)
    cases.leave_without_case(s, "f1", store=up.store)
    unchanged()
    cases.leave_without_case(s, "f1", store=up.store)
    cases.decline_case(s, "f1", store=up.store)
    unchanged()
    cases.leave_without_case(s, "f2", store=up.store)
    unchanged()
    cases.decline_case(s, "t1", store=up.store)
    cases.decline_case(s, "t1", store=up.store)
    unchanged()
    cases.leave_without_case(s, "t1", store=up.store)
    cases.leave_without_case(s, "t1", store=up.store)
    unchanged()
    for material_id in ("f1", "f2", "t1"):
        assert up.material(material_id).state == "unplaced", material_id


def test_I3_one_question_with_reply_to_is_shown_last_and_the_rest_is_counted() -> None:
    lines = {0: None, 1: "Ще 1 питання чекає.", 2: "Ще 2 питання чекають."}
    # Material times: one before the plan's NOW, one after it, one at the plan's own time.
    times = [NOW - HOUR, NOW + 30 * MINUTE, NOW]
    # Superseded by calm-open: the open reads no plan, so no plan kind is shown or counted.
    plan_kinds = ("none", "asking", "shown", "no_free_time", "sign_in", "plan_error", "case_error")
    for kind in plan_kinds:
        for count in (0, 1, 2, 3):
            a = guide_seen(Asks())
            for i in range(count):
                a.pending_note(f"n{i}", f"справа {i}", times[i])
            if kind == "asking":
                a.ai.task["duration_min"] = None
            if kind != "none":
                a.plan.start()
            if kind == "no_free_time":
                a.calendar.busy(NOW - HOUR, NOW + WEEK + HOUR)
            raises: BaseException | None = LoginExpired() if kind == "sign_in" else None
            if kind == "plan_error":
                raises = requests.HTTPError("fake: 500 Backend Error")
            total = 0 if kind == "case_error" else count
            if kind == "case_error":
                a.store.broken = True
            result = a.open_all(NOW + 2 * HOUR, raises)
            asked = question_replies(result.replies)
            label = (kind, count)
            assert len(asked) == (1 if total else 0), (label, result.replies)
            assert len(result.replies) == len(asked), (label, result.replies)
            if not total:
                continue
            assert result.replies[-1] is asked[0], label
            assert asked[0].question is not None and asked[0].question.kind == "case", label
            line = lines[total - 1]
            if line is None:
                assert "Ще " not in asked[0].text, (label, asked[0].text)
            else:
                assert asked[0].text.endswith(line), (label, asked[0].text)
