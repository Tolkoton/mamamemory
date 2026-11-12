"""Contract tests of the slice move-material: `cases.move_material` and the `move` route of `handle_message`.

Seam 1 (choice), Seam 2 (descriptions), Seam 3 (break), Seam 4 (open question, separate accounts), I1-I4.
Written by the slice tester from the sealed contract `.engine/slices/move-material.md`, without the code.
What `choose_material` answers is decided by the fake (`tests/move_material_world.py`); a failure at the level
of `cases` may be raised or answered with «Не вдалося…» (S1). The first case of a world is made on an empty
catalogue, where S1 does not fix its name: names are read from the cases returned.
"""

from mamamemory import assistant, cases
from mamamemory.replies import Question
from tests.move_material_world import WHAT, WHERE, Moves, already, ask, moved, placed
from tests.note_to_case_world import failed, plain

HBA = "аналіз HbA1c 7,2 у листопаді"
PRESSURE = "тиск 140/90 зранку"
GARLIC = "посадити часник біля паркану"
LETTER = "лист з податкової про декларацію"
SCHMIDT = "пані Шмідт"
SCHMITT = "пан Шмітт"
KOCH = "пан Кох"
NEW = "пан Фішер"
MOVE_HINT = (
    "мама просить перекласти вже внесений матеріал (нотатку, фото, документ) в іншу справу "
    "(«переклади …», «це не до X, а до Y»)"
)


def base() -> tuple[Moves, cases.Case, cases.Case, cases.Case]:
    """Three cases; HBA and then PRESSURE lie in the first (S1 names it), beside its seed note."""
    world = Moves()
    schmidt = world.seed(SCHMIDT, "s0")
    schmitt = world.seed(SCHMITT, "t0")
    koch = world.seed(KOCH, "k0")
    world.note(HBA, "m1", schmidt)
    world.note(PRESSURE, "m2", schmidt)
    assert world.material("m1").case_id == schmidt.case_id
    assert world.material("m2").case_id == schmidt.case_id
    return world, world.case(schmidt.case_id), world.case(schmitt.case_id), world.case(koch.case_id)


def described(world: Moves) -> int:
    return world.ai.count("describe_case")


def same_texts(world: Moves, text: str) -> list[cases.Material]:
    return [m for m in world.materials() if m.text == text]


# ------------------------------------------------------------------ the route


def test_route_knows_the_move_intent_and_its_hint() -> None:
    assert "move" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    world = Moves()
    world.ai.intent = "other"
    world.message("щось", "r1")
    assert plain(MOVE_HINT) in plain(world.ai.prompts["route"][-1])


def test_move_intent_goes_to_move_material() -> None:
    world, _, schmitt, _ = base()
    world.ai.intent = "move"
    world.ai.choose(HBA, schmitt.name)
    world.ai.avoid = [m.text[:30] for m in world.materials()]
    reply = world.message("переклади аналіз до пана Шмітта", "r1")
    assert reply.text == moved(HBA, schmitt.name)
    assert world.material("m1").case_id == schmitt.case_id
    assert world.ai.count("choose_material") == 1


def test_move_intent_with_reply_to_case_goes_to_move_material() -> None:
    world, _, schmitt, koch = base()
    world.note(GARLIC, "p1", NEW)
    assert world.material("p1").state == "pending"
    world.ai.intent = "move"
    world.ai.choose(HBA, schmitt.name)
    world.ai.avoid = [m.text[:30] for m in world.materials()]
    reply = world.message("переклади аналіз до пана Шмітта", "r1", reply_to=Question("case", "p1", None))
    assert reply.text == moved(HBA, schmitt.name)
    assert world.material("m1").case_id == schmitt.case_id
    assert world.material("p1").state == "pending"


# ------------------------------------------------------------------ the choice (Seam 1)


def test_material_named_by_its_text_not_the_last_moves_into_the_numbered_case() -> None:
    world, schmidt, schmitt, _ = base()
    reply = world.move(HBA, schmitt)
    assert reply.text == moved(HBA, schmitt.name)
    material = world.material("m1")
    assert material.state == "placed"
    assert material.case_id == schmitt.case_id
    assert material.pending_case is None
    assert material.asked is None
    assert material.in_description is True
    assert world.material("m2").case_id == schmidt.case_id


def test_material_not_in_the_catalogue_is_not_understood_and_changes_nothing() -> None:
    for number in (None, -1, 99):
        world, _, schmitt, _ = base()
        before, calls = world.documents(), described(world)
        reply = world.move(number, schmitt)
        assert reply.text == WHAT, number
        assert world.documents() == before, number
        assert described(world) == calls, number


def test_no_case_and_no_new_name_is_where_and_changes_nothing() -> None:
    for number in (None, -1, 99):
        world, _, _, _ = base()
        before, calls = world.documents(), described(world)
        reply = world.move(HBA, number)
        assert reply.text == WHERE, number
        assert world.documents() == before, number
        assert described(world) == calls, number


def test_the_case_it_already_lies_in_is_already_there_without_changes() -> None:
    world, schmidt, _, _ = base()
    before, calls = world.documents(), described(world)
    reply = world.move(HBA, schmidt)
    assert reply.text == already(schmidt.name)
    assert world.documents() == before
    assert described(world) == calls


def test_new_name_equal_to_its_own_case_in_another_register_is_already_there() -> None:
    world, schmidt, _, _ = base()
    before, calls = world.documents(), described(world)
    reply = world.move(HBA, None, new_case=schmidt.name.upper())
    assert reply.text == already(schmidt.name)
    assert world.documents() == before
    assert described(world) == calls


def test_new_name_asks_to_create_and_creates_no_case() -> None:
    world, _, _, _ = base()
    before = {c.case_id for c in world.cases()}
    reply = world.move(HBA, None, new_case=NEW)
    assert reply.text == ask(NEW)
    assert {c.case_id for c in world.cases()} == before
    material = world.material("m1")
    assert material.state == "pending"
    assert material.pending_case == NEW
    assert material.asked == "create"
    assert material.case_id is None
    assert material.in_description is False


def test_new_name_of_an_existing_case_in_another_register_is_that_case() -> None:
    world, _, schmitt, _ = base()
    before = {c.case_id for c in world.cases()}
    reply = world.move(HBA, None, new_case=schmitt.name.upper())
    assert reply.text.lower() == moved(HBA, schmitt.name).lower()
    assert {c.case_id for c in world.cases()} == before
    material = world.material("m1")
    assert material.state == "placed"
    assert material.case_id == schmitt.case_id


def test_case_number_outweighs_the_new_name() -> None:
    world, _, schmitt, _ = base()
    before = {c.case_id for c in world.cases()}
    reply = world.move(HBA, schmitt, new_case=NEW)
    assert reply.text == moved(HBA, schmitt.name)
    assert {c.case_id for c in world.cases()} == before
    material = world.material("m1")
    assert material.state == "placed"
    assert material.case_id == schmitt.case_id
    assert material.pending_case is None


def test_material_in_state_new_is_not_in_the_catalogue() -> None:
    world, _, schmitt, _ = base()
    world.ai.file_to(schmitt.name)
    world.ai.fail["classify_case"] = 1
    world.notes.try_add(LETTER, "n1")
    assert world.store.get("acc-1", "materials/n1") is not None
    reply = world.move(LETTER, schmitt)
    assert LETTER[:20] not in world.ai.prompts["choose_material"][-1]
    assert reply.text == WHAT
    assert world.store.get("acc-1", "materials/n1") is not None
    stored = world.store.get("acc-1", "materials/n1") or {}
    assert stored.get("state") == "new"


def test_reply_names_the_first_words_up_to_40_characters() -> None:
    world, schmidt, schmitt, _ = base()
    long_text = "розшифровка великого аналізу крові з усіма показниками за жовтень"
    world.note(long_text, "m9", schmidt)
    reply = world.move(long_text, schmitt)
    head, tail = "Переклала «", f"» у «{schmitt.name}»."
    assert reply.text.startswith(head) and reply.text.endswith(tail), reply.text
    words = reply.text[len(head) : -len(tail)].rstrip("…").rstrip(".").rstrip()
    assert words, reply.text
    assert len(words) <= 40, words
    assert long_text.startswith(words), words
    assert world.material("m9").case_id == schmitt.case_id


# ------------------------------------------------------------------ the descriptions (Seam 2)


def test_destination_is_described_with_the_one_moved_material() -> None:
    world, _, schmitt, _ = base()
    old = schmitt.description
    world.move(HBA, schmitt)
    prompt = world.built_from(schmitt.case_id)
    assert HBA in prompt
    assert old in prompt
    assert "відкриваю справу t0" not in prompt
    assert PRESSURE not in prompt


def test_source_is_rebuilt_fresh_from_its_remaining_materials() -> None:
    world, schmidt, schmitt, _ = base()
    old = schmidt.description
    world.move(HBA, schmitt)
    source = world.case(schmidt.case_id)
    assert source.description != old
    prompt = world.built_from(schmidt.case_id)
    assert PRESSURE in prompt
    assert "відкриваю справу s0" in prompt
    assert HBA not in prompt
    assert old not in prompt
    assert source.stale is False


def test_source_left_without_materials_gets_an_empty_description_without_the_model() -> None:
    world, _, schmitt, koch = base()
    calls = described(world)
    reply = world.move("відкриваю справу k0", schmitt)
    assert reply.text == moved("відкриваю справу k0", schmitt.name)
    source = world.case(koch.case_id)
    assert source.description == ""
    assert source.stale is False
    assert described(world) == calls + 1


def test_material_without_a_case_describes_only_the_destination() -> None:
    world, schmidt, schmitt, koch = base()
    world.note(GARLIC, "u1", None)
    assert world.material("u1").state == "unplaced"
    calls = described(world)
    others = {c.case_id: c.description for c in world.cases() if c.case_id != schmitt.case_id}
    reply = world.move(GARLIC, schmitt)
    assert reply.text == moved(GARLIC, schmitt.name)
    assert described(world) == calls + 1
    assert {c.case_id: c.description for c in world.cases() if c.case_id != schmitt.case_id} == others
    assert GARLIC in world.built_from(schmitt.case_id)
    assert all(c.stale is False for c in world.cases())
    assert world.material("u1").state == "placed"
    assert world.material("u1").in_description is True


def test_new_name_takes_the_material_out_of_its_source_and_rebuilds_the_source() -> None:
    world, schmidt, _, _ = base()
    old = schmidt.description
    world.move(HBA, None, new_case=NEW)
    source = world.case(schmidt.case_id)
    assert source.stale is False
    prompt = world.built_from(schmidt.case_id)
    assert PRESSURE in prompt
    assert HBA not in prompt
    assert old not in prompt


# ------------------------------------------------------------------ the break (Seam 3)


def test_failure_on_the_destination_description_is_finished_by_the_next_move() -> None:
    world, schmidt, schmitt, _ = base()
    world.ai.fail["describe_case"] = 1
    assert failed(world.try_move(HBA, schmitt))
    material = world.material("m1")
    assert material.case_id == schmitt.case_id
    assert material.in_description is False
    assert world.case(schmidt.case_id).stale is True
    reply = world.move(None)
    assert reply.text == WHAT
    material = world.material("m1")
    assert material.case_id == schmitt.case_id
    assert material.in_description is True
    assert HBA in world.built_from(schmitt.case_id)
    source = world.case(schmidt.case_id)
    assert source.stale is False
    prompt = world.built_from(schmidt.case_id)
    assert PRESSURE in prompt and HBA not in prompt
    assert len(same_texts(world, HBA)) == 1
    assert len(world.cases()) == 3


def test_failure_on_the_source_description_is_finished_by_an_already_there() -> None:
    world, schmidt, schmitt, _ = base()
    world.ai.after["describe_case"] = lambda: world.ai.fail.__setitem__("describe_case", 1)
    assert failed(world.try_move(HBA, schmitt))
    assert world.material("m1").case_id == schmitt.case_id
    assert world.material("m1").in_description is True
    assert world.case(schmidt.case_id).stale is True
    reply = world.move(HBA, schmitt)
    assert reply.text == already(schmitt.name)
    source = world.case(schmidt.case_id)
    assert source.stale is False
    prompt = world.built_from(schmidt.case_id)
    assert PRESSURE in prompt and HBA not in prompt
    assert len(same_texts(world, HBA)) == 1
    assert len(world.cases()) == 3


def test_deadline_after_the_destination_description_calls_no_model_and_is_finished_later() -> None:
    world, schmidt, schmitt, _ = base()
    world.ai.after["describe_case"] = world.clock.expire
    calls = described(world)
    assert failed(world.try_move(HBA, schmitt))
    assert described(world) == calls + 1
    assert world.case(schmidt.case_id).stale is True
    assert world.material("m1").case_id == schmitt.case_id
    world.reset_clock()
    reply = world.move(HBA, schmitt)
    assert reply.text == already(schmitt.name)
    assert world.case(schmidt.case_id).stale is False
    prompt = world.built_from(schmidt.case_id)
    assert PRESSURE in prompt and HBA not in prompt
    assert len(same_texts(world, HBA)) == 1


# ------------------------------------------------------------ the open question and the account (Seam 4)


def test_new_name_then_yes_builds_the_new_case_from_the_material() -> None:
    world, _, _, _ = base()
    world.move(HBA, None, new_case=NEW)
    reply = world.notes.yes("m1")
    assert reply.text == placed(NEW)
    made = [c for c in world.cases() if c.name == NEW]
    assert len(made) == 1
    assert world.material("m1").case_id == made[0].case_id
    assert world.material("m1").in_description is True
    assert HBA in world.built_from(made[0].case_id)


def test_new_name_then_no_then_an_existing_name_describes_that_case() -> None:
    world, _, _, koch = base()
    world.move(HBA, None, new_case=NEW)
    cases.decline_case(world.session, "m1", store=world.store)
    world.ai.file_to(koch.name)
    reply = world.choose("m1", "до Коха")
    assert reply.text == placed(koch.name)
    assert world.material("m1").case_id == koch.case_id
    assert world.material("m1").in_description is True
    assert HBA in world.built_from(koch.case_id)
    assert not [c for c in world.cases() if c.name == NEW]


def test_moving_a_pending_material_closes_its_question() -> None:
    world, _, schmitt, _ = base()
    world.note(GARLIC, "p1", NEW)
    assert "p1" in world.question_ids()
    reply = world.move(GARLIC, schmitt)
    assert reply.text == moved(GARLIC, schmitt.name)
    material = world.material("p1")
    assert material.state == "placed"
    assert material.case_id == schmitt.case_id
    assert material.pending_case is None
    assert material.asked is None
    assert "p1" not in world.question_ids()
    assert not [c for c in world.cases() if c.name == NEW]


def test_materials_of_another_account_are_not_in_the_catalogue_and_do_not_move() -> None:
    world, _, schmitt, _ = base()
    other = world.other()
    theirs = other.seed(KOCH, "x0")
    other.note(LETTER, "x1", theirs)
    reply = world.move(LETTER, schmitt)
    assert LETTER[:20] not in world.ai.prompts["choose_material"][-1]
    assert reply.text == WHAT
    assert other.material("x1").case_id == theirs.case_id
    assert [m.material_id for m in world.materials() if m.text == LETTER] == []


# ------------------------------------------------------------------ invariants


def lies_once(world: Moves, material_id: str, text: str, gs_uri: str | None) -> None:
    """One material with this id and none other with its text; the same text and original; in exactly one
    existing case, or pending on a new name."""
    found = [m for m in world.materials() if m.material_id == material_id]
    assert len(found) == 1, (material_id, found)
    assert len(same_texts(world, text)) == 1, text
    material = found[0]
    assert material.text == text
    assert material.gs_uri == gs_uri
    case_ids = [c.case_id for c in world.cases()]
    if material.state == "placed":
        assert case_ids.count(material.case_id or "") == 1, material
    else:
        assert material.state == "pending", material
        assert material.case_id is None and material.pending_case, material


def test_I1_a_move_never_doubles_or_loses_the_material() -> None:
    def break_destination(world: Moves) -> None:
        world.ai.fail["describe_case"] = 1

    def break_source(world: Moves) -> None:
        world.ai.after["describe_case"] = lambda: world.ai.fail.__setitem__("describe_case", 1)

    def break_deadline(world: Moves) -> None:
        world.ai.after["describe_case"] = world.clock.expire

    # (what, where it lies before, where it goes, the break, repeats)
    scenes = [
        ("note", "case", "case", None, 0),
        ("photo", "none", "case", None, 0),
        ("file", "pending", "new", None, 0),
        ("note", "case", "case", break_destination, 2),
        ("photo", "case", "case", break_source, 1),
        ("file", "case", "new", break_destination, 1),
        ("note", "pending", "case", break_deadline, 1),
        ("photo", "none", "new", None, 2),
    ]
    for kind, before, to, breaks, repeats in scenes:
        world, schmidt, schmitt, _ = base()
        where: cases.Case | str | None = {"case": schmidt, "none": None, "pending": "пан Вебер"}[before]
        if kind == "note":
            world.note(GARLIC, "x1", where)
        else:
            world.photo(GARLIC, "x1", where, "image/png" if kind == "photo" else "application/pdf")
        gs_uri = world.material("x1").gs_uri
        target: tuple[cases.Case | None, str | None] = (schmitt, None) if to == "case" else (None, NEW)
        if breaks is not None:
            breaks(world)
            world.try_move(GARLIC, target[0], new_case=target[1])
            world.reset_clock()
            lies_once(world, "x1", GARLIC, gs_uri)
        else:
            world.move(GARLIC, target[0], new_case=target[1])
        for _ in range(repeats):
            world.move(GARLIC, target[0], new_case=target[1])
        lies_once(world, "x1", GARLIC, gs_uri)
        material = world.material("x1")
        if to == "case":
            assert material.case_id == schmitt.case_id, (kind, before, to)
        else:
            assert material.state == "pending" and material.pending_case == NEW, (kind, before, to)


def test_I2_after_a_finished_move_nothing_is_stale_and_a_source_is_built_from_its_own_materials() -> None:
    world, schmidt, schmitt, koch = base()
    world.note(LETTER, "m3", schmidt)
    texts = {
        "s0": "відкриваю справу s0",
        "t0": "відкриваю справу t0",
        "k0": "відкриваю справу k0",
        "m1": HBA,
        "m2": PRESSURE,
        "m3": LETTER,
    }

    def holds(sources: list[cases.Case]) -> None:
        assert all(c.stale is False for c in world.cases()), world.cases()
        for m in world.materials():
            if m.state == "placed":
                assert m.in_description is True, m
        for source in sources:
            inside = {m.material_id for m in world.materials() if m.case_id == source.case_id}
            if not inside:
                assert world.case(source.case_id).description == ""
                continue
            prompt = world.built_from(source.case_id)
            for material_id, text in texts.items():
                if material_id in inside:
                    assert text in prompt, (source.name, text)
                else:
                    assert text not in prompt, (source.name, text)

    world.move(HBA, schmitt)
    holds([schmidt])
    world.ai.after["describe_case"] = lambda: world.ai.fail.__setitem__("describe_case", 1)
    world.try_move(PRESSURE, schmitt)
    assert world.move(None).text == WHAT
    holds([schmidt])
    world.ai.fail["describe_case"] = 1
    world.try_move(texts["t0"], schmidt)
    world.move(LETTER, koch)
    holds([schmidt, schmitt])
    assert world.move(LETTER, koch).text == already(koch.name)
    holds([schmidt, schmitt])


def test_I3_a_move_creates_no_case_without_yes() -> None:
    world, schmidt, schmitt, koch = base()
    world.note(GARLIC, "p1", "пан Вебер")
    before = {c.case_id for c in world.cases()}
    answers: list[tuple[str | None, cases.Case | int | None, str | None]] = [
        (HBA, schmitt, None),
        (PRESSURE, None, NEW),
        (PRESSURE, None, "пан Вагнер"),
        (GARLIC, None, koch.name.upper()),
        (GARLIC, schmidt, NEW),
        ("відкриваю справу t0", None, schmidt.name.lower()),
        (HBA, None, None),
        (None, None, NEW),
        (HBA, 99, None),
    ]
    for material, case, new_case in answers:
        world.move(material, case, new_case=new_case)
        assert {c.case_id for c in world.cases()} == before, (material, case, new_case)
    assert not [c for c in world.cases() if c.name in (NEW, "пан Вагнер", "пан Вебер")]


def test_I4_a_material_moved_out_of_its_case_waits_undescribed_and_is_described_where_it_lands() -> None:
    # placed note → new name → «так»
    world, _, _, _ = base()
    world.move(HBA, None, new_case=NEW)
    assert world.material("m1").in_description is False
    world.notes.yes("m1")
    made = [c for c in world.cases() if c.name == NEW]
    assert len(made) == 1
    assert world.material("m1").in_description is True
    assert HBA in world.built_from(made[0].case_id)

    # unplaced photo → new name → «ні» → an existing case by name
    world, _, _, koch = base()
    world.photo(GARLIC, "u1", None)
    world.move(GARLIC, None, new_case=NEW)
    assert world.material("u1").in_description is False
    cases.decline_case(world.session, "u1", store=world.store)
    assert world.material("u1").in_description is False
    world.ai.file_to(koch.name)
    world.choose("u1", "до Коха")
    assert world.material("u1").case_id == koch.case_id
    assert world.material("u1").in_description is True
    assert GARLIC in world.built_from(koch.case_id)

    # pending note → another new name → «так»
    world, _, _, _ = base()
    world.note(LETTER, "p1", "пан Вебер")
    world.move(LETTER, None, new_case=NEW)
    material = world.material("p1")
    assert material.pending_case == NEW and material.in_description is False
    world.notes.yes("p1")
    made = [c for c in world.cases() if c.name == NEW]
    assert len(made) == 1
    assert world.material("p1").in_description is True
    assert LETTER in world.built_from(made[0].case_id)
