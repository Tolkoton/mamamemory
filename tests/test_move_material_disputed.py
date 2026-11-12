"""Disputed contract tests of the slice move-material: each takes one reading of a question to the contract
(`.engine/slices/move-material.md`) and is sealed only after the slice planner answers it.

Written by the slice tester from the sealed contract, without the code.
"""

from mamamemory.replies import Question
from tests.move_material_world import Moves, ask

HBA = "аналіз HbA1c 7,2 у листопаді"
NEW = "пан Фішер"


def world_with_a_note() -> Moves:
    world = Moves()
    first = world.seed("пані Шмідт", "s0")
    world.seed("пан Шмітт", "t0")
    world.note(HBA, "m1", first)
    assert world.material("m1").case_id == first.case_id
    return world


def test_Q1_a_case_number_outside_the_catalogue_with_a_new_name_takes_the_new_name() -> None:
    for number in (-1, 99):
        world = world_with_a_note()
        before = {c.case_id for c in world.cases()}
        reply = world.move(HBA, number, new_case=NEW)
        assert reply.text == ask(NEW), number
        material = world.material("m1")
        assert material.state == "pending" and material.pending_case == NEW, number
        assert {c.case_id for c in world.cases()} == before, number


def test_Q2_the_create_question_of_a_move_carries_the_case_question_of_the_material() -> None:
    world = world_with_a_note()
    reply = world.move(HBA, None, new_case=NEW)
    assert reply.text == ask(NEW)
    assert reply.question == Question("case", "m1", None)
