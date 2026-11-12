"""Contract tests of the slice note-to-case: `cases`, `Store.list` and the route of `handle_message`.

Seam 1 (repeat and break), Seam 2 (catalogue and number), Seam 3 (route), Seam 4 (separate accounts),
I1, I2, I3, I4. Written by the slice tester from the sealed contract `.engine/slices/note-to-case.md`, without
the code. What the Розкладач names is decided by the fake (`tests/note_to_case_world.py`); a failure at the
level of `cases` may be raised or answered with «Не вдалося…» — the contract fixes only what `http` answers.
The first case of a test is made on an empty catalogue, where the contract does not fix the new case's name
(question Q1): its name is read from the case returned, never assumed.
"""

from datetime import timedelta

from mamamemory import assistant, cases
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Question
from tests.note_to_case_world import (
    NOT_ACTUAL,
    NOT_UNDERSTOOD,
    Notes,
    ask,
    failed,
    listed_number,
    placed,
    plain,
)
from tests.test_one_task_planning import NOW

SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"
NOTE = "запиши до пані Шмідт: HbA1c 7,2"
ALLERGY = "запам'ятай, що в Коха алергія на пеніцилін"
NOTE_HINT = (
    "мама просить записати чи запам'ятати відомості про людину чи справу (нотатка), а не задачу в календар"
)


def note_materials(world: Notes, text: str) -> list[cases.Material]:
    return [m for m in world.materials() if m.text == text]


def two_cases() -> tuple[Notes, cases.Case, cases.Case]:
    """A world with a first case (any name) and «пані Шмідт», made by notes and «так»."""
    world = Notes()
    first = world.seed(KOCH, "k0")
    schmidt = world.seed(SCHMIDT, "m0")
    return world, first, schmidt


# ------------------------------------------------------------------ recording (Seam 1)


def test_note_is_recorded_as_new_before_the_classifier_answers() -> None:
    world, _, schmidt = two_cases()
    seen: list[cases.Material] = []
    world.ai.file_to(schmidt.name)
    world.ai.after["classify_case"] = lambda: seen.extend(
        m for m in world.materials() if m.material_id == "m1"
    )
    world.add(NOTE, "m1")
    assert len(seen) == 1, "the material was not written before the Розкладач was called"
    assert seen[0].kind == "note"
    assert seen[0].state == "new"
    assert seen[0].text == NOTE
    assert seen[0].case_id is None


def test_note_document_lies_under_its_message_id() -> None:
    world = Notes()
    world.add(NOTE, "msg-7")
    assert world.store.get("acc-1", "materials/msg-7") is not None
    assert world.material("msg-7").material_id == "msg-7"


# ------------------------------------------------------------------ catalogue and number (Seam 2)


def test_note_named_by_number_goes_into_that_case_with_description() -> None:
    world, _, schmidt = two_cases()
    described = world.ai.count("describe_case")
    world.ai.file_to(SCHMIDT)
    reply = world.add(NOTE, "m1")
    assert reply.text == placed(SCHMIDT)
    assert reply.question is None
    material = world.material("m1")
    assert material.state == "placed"
    assert material.case_id == schmidt.case_id
    assert material.pending_case is None
    assert material.in_description is True
    assert world.ai.count("describe_case") == described + 1
    assert len(world.cases()) == 2


def test_classifier_gets_numbered_catalogue_of_names_and_descriptions_and_the_text() -> None:
    world, _, _ = two_cases()
    before = world.cases()
    world.ai.file_to(SCHMIDT)
    world.add(NOTE, "m1")
    prompt = world.ai.prompts["classify_case"][-1]
    assert NOTE in prompt
    numbers = []
    for case in before:
        assert case.name in prompt
        assert case.description in prompt
        number = listed_number(prompt, case.name)
        assert number is not None, f"{case.name} carries no number in the catalogue"
        numbers.append(number)
    assert len(set(numbers)) == 2


def test_description_is_the_old_description_and_the_text() -> None:
    world, _, schmidt = two_cases()
    world.ai.file_to(SCHMIDT)
    world.add(NOTE, "m1")
    prompt = world.ai.prompts["describe_case"][-1]
    assert schmidt.description in prompt
    assert NOTE in prompt


def test_new_name_asks_to_create_the_case_and_creates_none() -> None:
    world = Notes()
    first = world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    reply = world.add(NOTE, "m1")
    assert reply.text == ask(SCHMIDT)
    assert reply.question == Question("case", "m1", None)
    material = world.material("m1")
    assert material.state == "pending"
    assert material.pending_case == SCHMIDT
    assert material.case_id is None
    assert [c.name for c in world.cases()] == [first.name]


def test_neither_number_nor_name_leaves_the_note_unplaced() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.nowhere()
    reply = world.add(NOTE, "m1")
    assert reply.text == NOT_UNDERSTOOD
    assert reply.question is None
    material = world.material("m1")
    assert material.state == "unplaced"
    assert material.case_id is None
    assert material.pending_case is None
    assert len(world.cases()) == 1


def test_number_outside_the_catalogue_without_a_name_is_unplaced() -> None:
    world, _, _ = two_cases()
    for number, mid in ((99, "m1"), (-1, "m2")):
        world.ai.number(number)
        reply = world.add(f"нотатка {number}", mid)
        assert reply.text == NOT_UNDERSTOOD, number
        material = world.material(mid)
        assert material.state == "unplaced", number
        assert material.case_id is None, number
    assert len(world.cases()) == 2


def test_empty_catalogue_asks_without_calling_the_classifier() -> None:
    world = Notes()
    reply = world.add(NOTE, "m1")
    assert world.ai.count("classify_case") == 0
    assert reply.question == Question("case", "m1", None)
    assert reply.text.startswith("Створити справу «") and reply.text.endswith("»?"), reply.text
    assert world.material("m1").state == "pending"
    assert world.cases() == []


def test_yes_creates_the_case_with_the_pending_name_and_places_the_note() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    described = world.ai.count("describe_case")
    reply = world.yes("m1")
    assert reply.text == placed(SCHMIDT)
    made = [c for c in world.cases() if c.name == SCHMIDT]
    assert len(made) == 1
    material = world.material("m1")
    assert material.state == "placed"
    assert material.case_id == made[0].case_id
    assert material.pending_case is None
    assert material.in_description is True
    assert world.ai.count("describe_case") == described + 1


def test_yes_on_a_name_of_an_existing_case_in_another_case_goes_there() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    existing = world.seed("Пані Шмідт", "m0")
    world.ai.new_case("пані шмідт")
    world.add(NOTE, "m1")
    reply = world.yes("m1")
    assert reply.text.startswith("Поклала в «"), reply.text
    assert len(world.cases()) == 2
    assert world.material("m1").case_id == existing.case_id
    assert world.material("m1").state == "placed"


def test_yes_on_unknown_new_or_unplaced_material_is_not_actual() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.nowhere()
    world.add("нотатка без справи", "u1")
    world.ai.new_case(SCHMIDT)
    world.ai.fail["classify_case"] = 1
    world.try_add(NOTE, "n1")
    assert world.material("n1").state == "new"
    for material_id in ("nope", "u1", "n1"):
        assert world.yes(material_id).text == NOT_ACTUAL, material_id
    assert world.material("u1").state == "unplaced"
    assert world.material("n1").state == "new"
    assert len(world.cases()) == 1


# ------------------------------------------------------------------ repeat and break (Seam 1)


def test_classifier_failure_keeps_the_note_new_and_the_repeat_places_it() -> None:
    world, _, _ = two_cases()
    world.ai.file_to(SCHMIDT)
    world.ai.fail["classify_case"] = 1
    assert failed(world.try_add(NOTE, "m1"))
    assert world.material("m1").state == "new"
    reply = world.add(NOTE, "m1")
    assert reply.text == placed(SCHMIDT)
    assert len(note_materials(world, NOTE)) == 1
    assert world.material("m1").state == "placed"


def test_description_failure_in_add_note_the_repeat_fills_it_without_classifying_again() -> None:
    world, _, _ = two_cases()
    world.ai.file_to(SCHMIDT)
    world.ai.fail["describe_case"] = 1
    assert failed(world.try_add(NOTE, "m1"))
    material = world.material("m1")
    assert material.state == "placed"
    assert material.in_description is False
    classified = world.ai.count("classify_case")
    reply = world.add(NOTE, "m1")
    assert reply.text == placed(SCHMIDT)
    assert world.material("m1").in_description is True
    assert world.ai.count("classify_case") == classified
    assert len(note_materials(world, NOTE)) == 1
    assert len(world.cases()) == 2


def test_deadline_before_the_classifier_makes_no_call_and_the_repeat_places() -> None:
    world, _, _ = two_cases()
    world.ai.file_to(SCHMIDT)
    classified = world.ai.count("classify_case")
    world.clock.expire()
    assert failed(world.try_add(NOTE, "m1"))
    assert world.ai.count("classify_case") == classified
    assert world.material("m1").state == "new"
    world.clock.at = NOW
    assert world.add(NOTE, "m1").text == placed(SCHMIDT)
    assert len(note_materials(world, NOTE)) == 1


def test_deadline_before_the_description_makes_no_call_and_the_repeat_describes() -> None:
    world, _, _ = two_cases()
    world.ai.file_to(SCHMIDT)
    described = world.ai.count("describe_case")
    world.ai.after["classify_case"] = world.clock.expire
    assert failed(world.try_add(NOTE, "m1"))
    assert world.ai.count("describe_case") == described
    assert world.material("m1").state == "placed"
    assert world.material("m1").in_description is False
    world.clock.at = NOW
    assert world.add(NOTE, "m1").text == placed(SCHMIDT)
    assert world.material("m1").in_description is True


def test_repeated_yes_makes_no_second_case_and_no_second_description() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    described = world.ai.count("describe_case")
    replies = [world.yes("m1") for _ in range(3)]
    assert [r.text for r in replies] == [placed(SCHMIDT)] * 3
    assert [c.name for c in world.cases()].count(SCHMIDT) == 1
    assert world.ai.count("describe_case") == described + 1


def test_description_failure_inside_yes_the_repeated_yes_fills_it() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    world.ai.fail["describe_case"] = 1
    assert failed(world.try_yes("m1"))
    assert [c.name for c in world.cases()].count(SCHMIDT) == 1
    assert world.material("m1").state == "placed"
    assert world.material("m1").in_description is False
    assert world.yes("m1").text == placed(SCHMIDT)
    assert world.material("m1").in_description is True
    assert [c.name for c in world.cases()].count(SCHMIDT) == 1


def test_repeat_of_a_finished_note_answers_by_its_state_without_a_model_call() -> None:
    world = Notes()
    first = world.seed(KOCH, "k0")
    world.ai.file_to(first.name)
    first_placed = world.add(ALLERGY, "p1")
    world.ai.new_case(SCHMIDT)
    first_pending = world.add(NOTE, "q1")
    world.ai.nowhere()
    first_unplaced = world.add("щось незрозуміле", "u1")
    calls = list(world.ai.calls)
    assert world.add(ALLERGY, "p1").text == placed(first.name) == first_placed.text
    again = world.add(NOTE, "q1")
    assert again.text == ask(SCHMIDT) == first_pending.text
    assert again.question == Question("case", "q1", None)
    assert world.add("щось незрозуміле", "u1").text == NOT_UNDERSTOOD == first_unplaced.text
    assert world.ai.calls == calls
    assert len(world.materials()) == 4


# ------------------------------------------------------------------ reading


def test_pending_lists_waiting_materials_newest_first() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case("пан Фішер")
    world.add("нотатка про Фішера", "a1", now=NOW)
    world.ai.new_case("пані Маєр")
    world.add("нотатка про Маєр", "b1", now=NOW + timedelta(minutes=1))
    world.ai.nowhere()
    world.add("щось незрозуміле", "u1", now=NOW + timedelta(minutes=3))
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "c1", now=NOW + timedelta(minutes=2))
    waiting = cases.pending(world.session, world.store)
    assert [(m.material_id, m.pending_case) for m in waiting] == [
        ("c1", SCHMIDT),
        ("b1", "пані Маєр"),
        ("a1", "пан Фішер"),
    ]
    world.yes("b1")
    assert [m.material_id for m in cases.pending(world.session, world.store)] == ["c1", "a1"]


def test_texts_lists_the_materials_of_one_case() -> None:
    world, first, schmidt = two_cases()
    world.ai.file_to(SCHMIDT)
    world.add(NOTE, "m1")
    world.ai.file_to(first.name)
    world.add(ALLERGY, "k1")
    world.ai.nowhere()
    world.add("щось незрозуміле", "u1")
    assert {m.material_id for m in cases.texts(world.session, schmidt.case_id, world.store)} == {"m0", "m1"}
    assert {m.material_id for m in cases.texts(world.session, first.case_id, world.store)} == {"k0", "k1"}
    assert {m.material_id for m in world.materials()} == {"k0", "m0", "m1", "k1", "u1"}


def test_store_list_gives_the_documents_of_one_collection_under_the_account() -> None:
    store = InMemoryStore()
    store.set("acc-1", "cases/a", {"name": "A"})
    store.set("acc-1", "cases/b", {"name": "B"})
    store.set("acc-1", "materials/x", {"text": "X"})
    store.set("acc-2", "cases/c", {"name": "C"})
    assert sorted(store.list("acc-1", "cases")) == [("a", {"name": "A"}), ("b", {"name": "B"})]
    assert store.list("acc-1", "materials") == [("x", {"text": "X"})]
    assert store.list("acc-2", "cases") == [("c", {"name": "C"})]
    assert store.list("acc-3", "cases") == []


# ------------------------------------------------------------------ the route (Seam 3)


def test_route_knows_the_note_intent_and_its_hint() -> None:
    assert "note" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    world = Notes()
    world.ai.intent = "other"
    world.message("щось", "m1")
    assert plain(NOTE_HINT) in plain(world.ai.prompts["route"][-1])


def test_note_intent_goes_to_add_note() -> None:
    world, _, _ = two_cases()
    world.ai.intent = "note"
    world.ai.file_to(SCHMIDT)
    reply = world.message(NOTE, "m5")
    assert reply.text == placed(SCHMIDT)
    assert world.material("m5").text == NOTE
    assert world.material("m5").state == "placed"


def test_yes_with_reply_to_case_goes_to_confirm_case() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    world.ai.intent = "yes"
    reply = world.message("так", "m2", reply_to=Question("case", "m1", None))
    assert reply.text == placed(SCHMIDT)
    assert [c.name for c in world.cases()].count(SCHMIDT) == 1
    assert world.material("m1").state == "placed"


def test_other_intent_with_reply_to_case_is_routed_as_without_it() -> None:
    world = Notes()
    first = world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    world.ai.intent = "new_task"
    world.message("у четвер подзвонити нотаріусу", "m2", reply_to=Question("case", "m1", None))
    assert world.ai.count("parse_task") >= 1, "a new task with reply_to case did not reach planning"
    assert world.material("m1").state == "pending"
    assert [c.name for c in world.cases()] == [first.name]


def test_route_prompt_for_a_case_reply_names_the_question() -> None:
    world = Notes()
    world.seed(KOCH, "k0")
    world.ai.new_case(SCHMIDT)
    world.add(NOTE, "m1")
    world.ai.intent = "other"
    world.message("щось", "m2", reply_to=Question("case", "m1", None))
    assert f"Асистент спитав «Створити справу «{SCHMIDT}»?»" in world.ai.prompts["route"][-1]


# ------------------------------------------------------------------ invariants

BREAKS_IN_NOTE = ["classify", "classify_twice", "describe", "deadline_first", "deadline_second"]


def broken_note_world(path: str, where: str) -> Notes:
    """A world with one case, the Розкладач set to `path`, the next `add_note` set to break at `where`."""
    world = Notes()
    first = world.seed(KOCH, "k0")
    if path == "listed":
        world.ai.file_to(first.name)
    elif path == "new":
        world.ai.new_case(SCHMIDT)
    else:
        world.ai.nowhere()
    if where == "classify":
        world.ai.fail["classify_case"] = 1
    elif where == "classify_twice":
        world.ai.fail["classify_case"] = 2
    elif where == "describe":
        world.ai.fail["describe_case"] = 1
    elif where == "deadline_first":
        world.clock.expire()
    elif where == "deadline_second":
        world.ai.after["classify_case"] = world.clock.expire
    return world


def test_I1_a_received_note_is_neither_lost_nor_doubled() -> None:
    # Every failure point of add_note -> place (and none), on each path of the Розкладач, then 1 to 3 repeats.
    for path in ("listed", "new", "nowhere"):
        for where in ["none", *BREAKS_IN_NOTE]:
            for repeats in (1, 2, 3):
                world = broken_note_world(path, where)
                text = f"нотатка {path} {where} {repeats}"
                world.try_add(text, "m1")
                world.clock.at = NOW
                for _ in range(repeats):
                    world.try_add(text, "m1")
                found = note_materials(world, text)
                assert len(found) == 1, (path, where, repeats, found)
                assert found[0].material_id == "m1", (path, where, repeats)
                assert [m.material_id for m in world.materials()].count("m1") == 1
    # Two notes combined, the second failing between the repeats of the first.
    world = Notes()
    first = world.seed(KOCH, "k0")
    world.ai.file_to(first.name)
    world.ai.fail["classify_case"] = 1
    world.try_add("перша", "a1")
    world.ai.fail["describe_case"] = 1
    world.try_add("друга", "b1")
    world.try_add("перша", "a1")
    world.try_add("друга", "b1")
    world.try_add("перша", "a1")
    assert len(note_materials(world, "перша")) == 1
    assert len(note_materials(world, "друга")) == 1
    assert len(world.materials()) == 3


def test_I4_after_the_first_successful_repeat_the_note_is_finished() -> None:
    for path in ("listed", "new", "nowhere"):
        for where in BREAKS_IN_NOTE:
            world = broken_note_world(path, where)
            text = f"нотатка {path} {where}"
            reply = world.try_add(text, "m1")
            world.clock.at = NOW
            tries = 0
            while failed(reply):
                tries += 1
                assert tries <= 3, (path, where, "never succeeded")
                reply = world.try_add(text, "m1")
            material = world.material("m1")
            assert material.state != "new", (path, where)
            if material.state == "placed":
                assert material.in_description is True, (path, where)
    # A break inside «так»: the description fails, or the time is up before it.
    for where in ("describe", "deadline"):
        world = Notes()
        world.seed(KOCH, "k0")
        world.ai.new_case(SCHMIDT)
        world.add(NOTE, "m1")
        if where == "describe":
            world.ai.fail["describe_case"] = 1
        else:
            world.clock.expire()
        assert failed(world.try_yes("m1")), where
        world.clock.at = NOW
        assert not failed(world.try_yes("m1")), where
        material = world.material("m1")
        assert material.state == "placed", where
        assert material.in_description is True, where


def test_I2_a_case_is_created_only_after_yes_and_once_per_material() -> None:
    world = Notes()

    def made() -> int:
        return len(world.cases())

    # Empty catalogue: the first note asks; neither it nor its repeat creates a case.
    world.add(NOTE, "m1")
    world.add(NOTE, "m1")
    assert made() == 0
    pending_name = world.material("m1").pending_case
    assert pending_name
    # «так» by word, then by button, then by word again: one case.
    world.ai.intent = "yes"
    world.message("так", "w1", reply_to=Question("case", "m1", None))
    assert made() == 1
    world.yes("m1")
    world.message("так", "w2", reply_to=Question("case", "m1", None))
    assert made() == 1
    # A note the Розкладач files into the case creates nothing; a note with a new name neither.
    world.ai.file_to(pending_name)
    world.add("друга нотатка про ту саму людину", "m2")
    assert made() == 1
    world.ai.new_case(KOCH)
    world.add(ALLERGY, "k1")
    world.add(ALLERGY, "k1")
    world.ai.nowhere()
    world.add("щось незрозуміле", "u1")
    assert made() == 1
    # «так» whose description fails, then repeated: one more case, not two.
    world.ai.fail["describe_case"] = 1
    world.try_yes("k1")
    assert made() == 2
    world.yes("k1")
    world.yes("k1")
    # «так» on a placed note, an unplaced one, an unknown id: nothing new.
    world.yes("m2")
    world.yes("u1")
    world.yes("nope")
    assert made() == 2
    assert sorted(c.name for c in world.cases()) == sorted([pending_name, KOCH])


def test_I3_cases_and_materials_of_one_account_are_not_seen_or_changed_from_another() -> None:
    mama = Notes()
    first = mama.seed(KOCH, "k0")
    mama.ai.new_case(SCHMIDT)
    mama.add(NOTE, "m1")
    other = mama.other("acc-2")
    assert other.cases() == []
    assert other.materials() == []
    assert cases.pending(other.session, other.store) == []
    assert cases.texts(other.session, first.case_id, other.store) == []
    # A foreign material id is not actual, and changes nothing on either side.
    assert other.yes("m1").text == NOT_ACTUAL
    assert other.yes("k0").text == NOT_ACTUAL
    assert other.cases() == []
    assert mama.material("m1").state == "pending"
    assert [c.name for c in mama.cases()] == [first.name]
    # The same message id in the other account is that account's own note.
    other.add("нотатка другого акаунта", "m1")
    assert [m.text for m in other.materials()] == ["нотатка другого акаунта"]
    assert mama.material("m1").text == NOTE
    assert mama.material("m1").state == "pending"
    # A lawful «так» after the refused ones still works, in its own account only.
    assert mama.yes("m1").text == placed(SCHMIDT)
    assert sorted(c.name for c in mama.cases()) == sorted([first.name, SCHMIDT])
    assert other.cases() == []
    assert other.material("m1").state == "pending"
