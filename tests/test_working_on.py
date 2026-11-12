"""Contract tests of the slice working-on: `cases.worklog.add` and the intent `working_on` of `assistant`;
Seam 1 (the record), Seam 2 (the route), I1.

Written by the slice tester from the sealed contract `.engine/slices/working-on.md`, without the code.
`NOW` is Monday 9 November 2026, 09:07Z. Every expected text and time is written by hand.
"""

import re
from datetime import UTC, datetime

from mamamemory import assistant
from mamamemory.replies import Question
from tests.case_questions_world import case_q
from tests.clarify_world import clarified
from tests.working_on_world import NOW_ISO, Work, plain, recorded

CONTRACT = "зараз працюю над договором купівлі городу"
SCHMIDT = "пані Шмідт"
NOTARY = "працюю над тим, щоб подзвонити нотаріусу в четвер"
HINT = (
    "working_on — мама каже, над чим зараз працює чи що робить («зараз працюю над …», «я зараз роблю …», "
    "«сиджу над …»); це не нотатка про людину і не задача на потім"
)


def reply_tos() -> list[Question | None]:
    return [None, Question("plan", "p1", "fp"), case_q("a1")]


# ------------------------------------------------------------------ Seam 1: the record


def test_seam1_add_writes_the_document_with_trimmed_text_and_time() -> None:
    w = Work()
    w.log(f"  {CONTRACT} \n", "e1")
    document = w.entry("e1")
    assert document is not None
    assert document["text"] == CONTRACT
    assert document["at"] == NOW_ISO
    assert [entry_id for entry_id, _ in w.entries()] == ["e1"]


def test_seam1_add_answers_recorded_with_trimmed_text_and_no_question() -> None:
    w = Work()
    reply = w.log(f"   {CONTRACT}  ", "e1")
    assert reply.text == "Записала: зараз працюю над договором купівлі городу."
    assert reply.text == recorded(CONTRACT)
    assert reply.question is None


def test_seam1_same_entry_id_twice_is_one_document() -> None:
    w = Work()
    first = w.log(CONTRACT, "e1")
    second = w.log(CONTRACT, "e1")
    assert [entry_id for entry_id, _ in w.entries()] == ["e1"]
    assert first.text == second.text == recorded(CONTRACT)


def test_add_writes_under_the_account_only() -> None:
    w = Work()
    other = w.other_work("acc-2")
    w.log(CONTRACT, "e1")
    assert other.entries() == []
    assert other.entry("e1") is None
    assert len(w.entries()) == 1


def test_seam1_message_calls_only_the_route_and_no_calendar_tasks_or_cases() -> None:
    w = Work()
    before = w.cases_state()
    reply = w.working(f" {CONTRACT} ", "m1")
    assert reply.text == recorded(CONTRACT)
    assert reply.question is None
    assert w.ai.calls == ["route"]
    assert w.calendar.log == []
    assert w.cases_state() == before


# ------------------------------------------------------------------ assistant: dispatch


def test_working_on_message_is_recorded_under_its_message_id_with_the_given_now() -> None:
    w = Work()
    later = datetime(2026, 11, 10, 14, 30, 5, tzinfo=UTC)
    reply = w.working("сиджу над аналізами пані Шмідт", "msg-7", now=later)
    assert reply.text == "Записала: сиджу над аналізами пані Шмідт."
    document = w.entry("msg-7")
    assert document is not None
    assert document["text"] == "сиджу над аналізами пані Шмідт"
    assert document["at"] == "2026-11-10T14:30:05+00:00"
    assert [entry_id for entry_id, _ in w.entries()] == ["msg-7"]


def test_working_on_message_without_message_id_gets_a_uuid4_hex_entry() -> None:
    w = Work()
    w.working("я зараз роблю звіт для податкової", None)
    entries = w.entries()
    assert len(entries) == 1
    entry_id, document = entries[0]
    assert re.fullmatch(r"[0-9a-f]{32}", entry_id), entry_id
    assert document["text"] == "я зараз роблю звіт для податкової"


# ------------------------------------------------------------------ Seam 2: the route


def test_route_schema_constant_offers_working_on() -> None:
    assert "working_on" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]


def test_working_on_is_always_allowed() -> None:
    assert "working_on" in assistant.ALWAYS


def test_working_on_phrase() -> None:
    assert assistant.PHRASES["working_on"] == "записати, над чим працюєте"


def test_seam2_route_schema_offers_working_on_under_every_reply_to() -> None:
    for reply_to in reply_tos():
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "working_on" in enum, reply_to


def test_seam2_allowed_has_working_on_under_every_reply_to() -> None:
    for reply_to in reply_tos():
        assert "working_on" in assistant.allowed(reply_to), reply_to


def test_route_prompt_carries_the_working_on_hint() -> None:
    w = Work()
    w.ai.plain_intent("other")
    w.message_any("щось", "m1")
    assert plain(HINT) in plain(w.ai.prompts["route"][-1])


def test_seam2_unsure_between_note_and_working_on_asks_with_the_phrase() -> None:
    w = Work()
    w.ai.unsure("note", "working_on")
    reply = w.message_any(CONTRACT, "m1")
    clarified(reply)
    assert reply.text == "Не зовсім зрозуміла: записати нотаткою до справи чи записати, над чим працюєте?"


# ------------------------------------------------------------------ invariants


def test_I1_working_on_writes_one_journal_document_per_entry_id_and_nothing_else() -> None:
    w = Work()
    # A case question and a shown plan made the lawful way, before the intent is measured.
    w.pending_note("a1", SCHMIDT)
    case_question = case_q("a1")
    plan_question = w.plan_question()
    cases_before = w.cases_state()
    inserts_before = list(w.calendar.insert_calls)
    w.calendar.log.clear()
    calls_before = len(w.ai.calls)

    phrases = [
        (None, f"  {CONTRACT}  ", "m1", CONTRACT),
        (plan_question, "я зараз роблю звіт для податкової", "m2", "я зараз роблю звіт для податкової"),
        (case_question, "сиджу над аналізами пані Шмідт", "m3", "сиджу над аналізами пані Шмідт"),
        (None, NOTARY, "m4", NOTARY),
        (None, "так", "m5", "так"),
    ]
    routes = 0
    for reply_to, text, message_id, expected in phrases:
        for _ in range(3):  # the app repeats the same message
            reply = w.working(text, message_id, reply_to)
            routes += 1
            assert reply.text == recorded(expected), (text, reply)
            assert reply.question is None, (text, reply)
    expected_ids = ["m1", "m2", "m3", "m4", "m5"]
    assert sorted(entry_id for entry_id, _ in w.entries()) == expected_ids
    assert w.ai.calls[calls_before:] == ["route"] * routes
    assert w.calendar.writes() == []
    assert w.calendar.insert_calls == inserts_before
    assert w.cases_state() == cases_before
    assert w.other_work("acc-2").entries() == []
