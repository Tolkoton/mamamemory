"""Disputed contract tests of the slice note-to-case: each fixes one reading of a question to the contract.

Written by the slice tester from the sealed contract `.engine/slices/note-to-case.md`, without the code.
This file is sealed only after the slice planner answers the questions Q1–Q4 of the hand-in.
"""

from tests.note_to_case_world import Notes, ask, placed

SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"
NOTE = "запиши до пані Шмідт: HbA1c 7,2"


def test_q1_empty_catalogue_question_names_the_case_that_yes_creates() -> None:
    # Q1: on an empty catalogue the Розкладач is not called; the reading taken: the question still names a
    # new case, that name is the material's `pending_case`, and «так» creates the case under that name.
    world = Notes()
    reply = world.add(NOTE, "m1")
    material = world.material("m1")
    assert material.pending_case, "the question about a new case names no case"
    assert reply.text == ask(material.pending_case)
    assert world.yes("m1").text == placed(material.pending_case)
    assert [c.name for c in world.cases()] == [material.pending_case]


def test_q2_number_outside_the_catalogue_with_a_name_asks_about_that_name() -> None:
    # Q2: a number that is not in the catalogue counts as no number; with a name it is «Створити справу?».
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.number(99, new_name=SCHMIDT)
    reply = world.add(NOTE, "m1")
    assert reply.text == ask(SCHMIDT)
    material = world.material("m1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    assert material.case_id is None


def test_q3_the_case_description_is_what_the_description_model_answered() -> None:
    # Q3: `describe_case` answers the new description; the case keeps it as it is.
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    world.yes("m1")
    made = [c for c in world.cases() if c.name == SCHMIDT]
    assert made[0].description == world.ai.descriptions[-1]
    world.ai.file_to(SCHMIDT)
    world.add("друга нотатка про пані Шмідт", "m2")
    made = [c for c in world.cases() if c.name == SCHMIDT]
    assert made[0].description == world.ai.descriptions[-1]


def test_q4_yes_into_an_existing_case_names_the_existing_case() -> None:
    # Q4: «так» on «пані шмідт» while «Пані Шмідт» exists puts it there and says the existing case's name.
    world = Notes()
    world.seed(KOCH, "k0")
    world.seed("Пані Шмідт", "m0")
    world.ai.new_case("пані шмідт")
    world.add(NOTE, "m1")
    assert world.yes("m1").text == placed("Пані Шмідт")
