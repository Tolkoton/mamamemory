"""Disputed contract tests of the slice case-questions: each one takes a reading of a question to the sealed
contract `.engine/slices/case-questions.md` (Q1, Q2 of the tester's hand-in) and is sealed only after the
slice planner's answer. Written by the slice tester from the contract, without the code.
"""

from tests.case_questions_world import WHICH, Asks, case_q
from tests.note_to_case_world import ask
from tests.test_one_task_planning import NOW

KOCH = "пан Кох"
SCHMIDT = "пані Шмідт"


def test_Q1_choose_on_which_naming_the_declined_name_asks_to_create_it() -> None:
    # Q1: on `asked: which`, a new name equal to `pending_case` (the name declined by «ні») is neither "the
    # same name on `asked: create`" nor "another new name"; the reading taken: it asks «Створити справу «X»?».
    a = Asks()
    first = a.seed(KOCH, "k0")
    a.pending_note("a1", SCHMIDT)
    a.decline("a1")
    a.ai.new_case("Пані Шмідт")
    reply = a.choose("a1", "до пані Шмідт")
    assert reply.question == case_q("a1")
    assert reply.text.lower() == ask(SCHMIDT).lower()
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "create", doc
    assert a.material("a1").state == "pending"
    assert [c.name for c in a.cases()] == [first.name]


def test_Q2_choose_on_create_naming_nothing_asks_which_and_changes_nothing() -> None:
    # Q2: on `asked: create`, a reply that names no listed case and no new name gets «У яку справу покласти?»
    # «без змін»; the reading taken: the material keeps `asked: create` and its `pending_case`, so the next
    # open shows «Створити справу «X»?» again.
    a = Asks()
    first = a.seed(KOCH, "k0")
    a.pending_note("a1", SCHMIDT, NOW)
    a.ai.nowhere()
    reply = a.choose("a1", "ні, кудись інше")
    assert reply.text == WHICH
    assert reply.question == case_q("a1")
    material = a.material("a1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    doc = a.doc("a1")
    assert doc is not None and doc.get("asked") == "create", doc
    assert [q.reply.text for q in a.case_questions()] == [ask(SCHMIDT)]
    assert [c.name for c in a.cases()] == [first.name]
