"""Contract tests of the slice clarify: the route's `unsure` with two `options`, the clarification and its
answer by button (`assistant.answer_clarify`) or by word (`reply_to.kind == "clarify"`), Seam 1, Seam 2,
I1, I2, I3.

Written by the slice tester from the sealed contract `.engine/slices/clarify.md`, without the code.
Option 1 is the first of the route's `options`, named first in the question. Every text is written by hand.
"""

from typing import Any

from mamamemory import assistant
from mamamemory.replies import Question, Reply
from tests.case_questions_world import case_q
from tests.clarify_world import (
    NOT_ACTUAL,
    Clarify,
    asked_text,
    clarified,
    stuck_clarify,
)
from tests.note_to_case_world import ask, placed
from tests.several_tasks_world import NOTARY, task
from tests.stuck_question_world import TEA, asked

KOCH = "пан Кох"
SCHMIDT = "пані Шмідт"
WOLF = "пан Вольф просив виписати рецепт на леводопу"
# The sealed contract guide, Seam «Незрозуміле», replaced the old «Поки що я вмію…» with this text.
CANNOT = "Не зрозуміла. Скажіть «що ти вмієш?» — розкажу."


def seeded() -> tuple[Clarify, str]:
    """A world with one case (its name read from what was made); the next note proposes «пані Шмідт»."""
    w = Clarify()
    first = w.seed(KOCH, "k0")
    w.ai.new_case(SCHMIDT)
    w.ai.default_name = SCHMIDT
    return w, first.name


def unsure_wolf(w: Clarify, *options: str, message_id: str = "m1") -> Question:
    w.ai.unsure(*options)
    return clarified(w.say(WOLF, message_id))


# ------------------------------------------------------------------ the route schema


def test_route_schema_has_unsure_and_options_under_every_reply_to() -> None:
    plan_q = Question("plan", "p1", "fp")
    for reply_to in (None, plan_q, case_q("a1")):
        schema = assistant.route_schema(reply_to)
        assert "unsure" in schema["properties"]["intent"]["enum"], reply_to
        options = schema["properties"].get("options")
        assert isinstance(options, dict), (reply_to, schema)
        assert options.get("type") == "array" or "array" in options.get("type", []), options
    assert "unsure" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    assert "options" in assistant.ROUTE_SCHEMA["properties"]


# ------------------------------------------------------------------ Seam 1: ask


def test_seam1_unsure_with_two_valid_options_asks_with_both_and_does_nothing_else() -> None:
    w, _ = seeded()
    before = w.everything_else()
    calls = len(w.ai.calls)
    w.ai.unsure("note", "new_task")
    reply = w.say(WOLF, "m1")
    question = clarified(reply)
    assert reply.text == "Не зовсім зрозуміла: записати нотаткою до справи чи поставити задачею в календар?"
    assert reply.plan is None, reply
    assert reply.choices is not None and len(reply.choices) == 2, reply
    assert all(isinstance(c, str) and c for c in reply.choices), reply
    assert w.ai.calls[calls:] == ["route"]
    assert w.everything_else() == before
    current = w.current()
    assert current is not None and current["clarify_id"] == question.id, current
    assert w.calendar.insert_calls == []


def test_seam1_clarify_document_holds_the_text_message_id_reply_to_and_options() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task", message_id="m1")
    current = w.current()
    assert current is not None
    assert {"clarify_id", "text", "message_id", "reply_to", "options", "created"} <= set(current), current
    assert current["clarify_id"] == question.id
    assert current["text"] == WOLF
    assert current["message_id"] == "m1"
    assert current["reply_to"] is None
    assert current["options"] == ["note", "new_task"]


def test_seam1_every_intent_is_named_by_its_phrase_where_it_is_allowed() -> None:
    w, _ = seeded()
    w.pending_note("a1", SCHMIDT)
    plan_reply = w.plan.start()
    assert plan_reply.question is not None and plan_reply.question.kind == "plan", plan_reply
    plan_q = plan_reply.question
    cases = [
        (plan_q, "yes", "edit", "Не зовсім зрозуміла: погодитись чи змінити показаний план?"),
        (
            plan_q,
            "plan_week",
            "move",
            "Не зовсім зрозуміла: спланувати тиждень чи перекласти матеріал в іншу справу?",
        ),
        (case_q("a1"), "no", "not_needed", "Не зовсім зрозуміла: відмовитись чи лишити без справи?"),
        (
            case_q("a1"),
            "case_name",
            "note",
            "Не зовсім зрозуміла: покласти в названу справу чи записати нотаткою до справи?",
        ),
        (
            None,
            "new_task",
            "plan_week",
            "Не зовсім зрозуміла: поставити задачею в календар чи спланувати тиждень?",
        ),
    ]
    for n, (reply_to, first, second, text) in enumerate(cases):
        w.ai.unsure(first, second)
        reply = w.say("двозначна фраза", f"p{n}", reply_to)
        clarified(reply)
        assert reply.text == text, (first, second, reply)
        assert reply.text == asked_text(first, second)


def cannot(reply: Reply) -> None:
    assert reply.text == CANNOT, reply
    assert reply.question is None, reply


def test_seam1_invalid_options_answer_as_other_and_write_no_clarification() -> None:
    w, _ = seeded()
    invalid: list[list[object]] = [
        [],
        ["note"],
        ["note", "new_task", "move"],
        ["note", "note"],
        ["yes", "note"],
        ["edit", "note"],
        ["case_name", "note"],
        ["no", "note"],
        ["not_needed", "note"],
        ["unsure", "note"],
        ["other", "note"],
        ["shop", "note"],
    ]
    before = w.everything_else()
    for n, options in enumerate(invalid):
        w.ai.unsure(*options)
        reply = w.say(WOLF, f"i{n}")
        cannot(reply)
        assert w.current() is None, options
    bare: list[dict[str, Any]] = [{"intent": "unsure"}, {"intent": "unsure", "options": None}]
    for n, answer in enumerate(bare):
        w.ai.route_answer = answer
        cannot(w.say(WOLF, f"j{n}"))
        assert w.current() is None, answer
    assert w.everything_else() == before
    assert w.calendar.insert_calls == []
    # The same phrase with two valid options is a clarification: the refusals above were for the options.
    w.ai.unsure("note", "new_task")
    clarified(w.say(WOLF, "k1"))


def test_seam1_a_new_clarification_replaces_the_old_one() -> None:
    w, _ = seeded()
    old = unsure_wolf(w, "note", "new_task", message_id="m1")
    w.ai.unsure("plan_week", "move")
    new = clarified(w.say("друга двозначна фраза", "m2"))
    assert new.id != old.id
    current = w.current()
    assert current is not None and current["clarify_id"] == new.id, current
    assert w.button(old.id, 1).text == NOT_ACTUAL
    assert [m.material_id for m in w.materials()] == ["k0"]


# ------------------------------------------------------------------ Seam 2: the choice


def test_seam2_button_runs_the_saved_text_as_the_chosen_note_with_the_saved_message_id() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task", message_id="m1")
    routes = w.routes()
    reply = w.button(question.id, 1)
    assert reply == Reply(ask(SCHMIDT), case_q("m1"))
    assert w.material("m1").text == WOLF
    assert w.routes() == routes
    assert WOLF in w.ai.prompts["classify_case"][-1]


def test_seam2_button_runs_case_name_with_the_saved_case_reply_to() -> None:
    w, koch = seeded()
    w.pending_note("a1", SCHMIDT)
    w.ai.unsure("case_name", "note")
    question = clarified(w.say("до Коха", "w1", case_q("a1")))
    w.ai.file_to(koch)
    routes = w.routes()
    reply = w.button(question.id, 1)
    assert reply.text == placed(koch)
    assert "до Коха" in w.ai.prompts["classify_case"][-1]
    assert w.material("a1").state == "placed"
    assert w.material("a1").case_id == [c for c in w.cases() if c.name == koch][0].case_id
    assert "w1" not in [m.material_id for m in w.materials()]
    assert w.routes() == routes


def test_seam2_repeated_button_is_not_actual_and_runs_nothing() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task")
    w.button(question.id, 1)
    after = w.everything_else()
    classified = w.ai.count("classify_case")
    for option in (1, 2, 1):
        assert w.button(question.id, option).text == NOT_ACTUAL
    assert w.everything_else() == after
    assert w.ai.count("classify_case") == classified


def test_seam2_button_with_an_unknown_clarify_id_is_not_actual() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task")
    before = w.everything_else()
    assert w.button("no-such-clarify", 1).text == NOT_ACTUAL
    assert w.everything_else() == before
    current = w.current()
    assert current is not None and current["clarify_id"] == question.id, current


def test_seam2_word_choosing_runs_the_saved_text_with_the_saved_message_id_without_a_route() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "new_task", "note", message_id="m1")
    routes = w.routes()
    w.ai.option = 2
    reply = w.say("нотаткою", "w2", Question("clarify", question.id, None))
    assert reply == Reply(ask(SCHMIDT), case_q("m1"))
    assert w.material("m1").text == WOLF
    assert "w2" not in [m.material_id for m in w.materials()]
    assert w.routes() == routes
    assert w.button(question.id, 2).text == NOT_ACTUAL


def test_seam2_choose_option_prompt_names_both_variants() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task")
    w.ai.option = 1
    w.say("нотаткою", "w2", Question("clarify", question.id, None))
    prompts = w.ai.prompts.get("option", [])
    assert len(prompts) == 1, prompts
    assert "записати нотаткою до справи" in prompts[0]
    assert "поставити задачею в календар" in prompts[0]
    assert "нотаткою" in prompts[0]


def test_seam2_word_that_is_no_choice_is_routed_as_new_and_the_clarification_stays() -> None:
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task", message_id="m1")
    routes = w.routes()
    w.ai.option = None
    w.ai.plain_intent("note")
    w.ai.new_case(SCHMIDT)
    word = "запиши до пані Шмідт: тиск 130"
    reply = w.say(word, "w2", Question("clarify", question.id, None))
    assert w.routes() == routes + 1
    assert reply.text != NOT_ACTUAL
    assert reply.question != question, reply
    assert w.material("w2").text == word
    assert "m1" not in [m.material_id for m in w.materials()]
    current = w.current()
    assert current is not None and current["clarify_id"] == question.id, current
    assert current["text"] == WOLF
    assert w.button(question.id, 1) == Reply(ask(SCHMIDT), case_q("m1"))
    assert w.material("m1").text == WOLF


def test_seam2_word_under_a_stale_clarification_is_routed_as_new_and_leaves_the_current_one() -> None:
    w, _ = seeded()
    old = unsure_wolf(w, "note", "new_task", message_id="m1")
    w.ai.unsure("new_task", "note")
    new = clarified(w.say("друга двозначна фраза", "m2"))
    kept = w.current()
    w.ai.option = 2
    w.ai.plain_intent("note")
    word = "запиши до пані Шмідт: тиск 130"
    routes = w.routes()
    reply = w.say(word, "w3", Question("clarify", old.id, None))
    assert w.routes() == routes + 1
    assert reply.text != NOT_ACTUAL
    assert reply.question != old and reply.question != new, reply
    assert w.material("w3").text == word
    ids = [m.material_id for m in w.materials()]
    assert "m1" not in ids and "m2" not in ids, ids
    assert w.current() == kept


def test_seam2_choice_replays_the_effective_reply_to_and_replace_asking() -> None:
    w = stuck_clarify()
    duration_q = asked(w.add(task(NOTARY, duration_min=None)), "duration")
    w.ai.raw_durations = [None]
    w.ai.unsure("new_task", "note")
    question = clarified(w.message("а мені треба чай", duration_q))
    current = w.current()
    assert current is not None and current["reply_to"] is None, current
    w.ai.says(task(TEA))
    reply = w.button(question.id, 1)
    assert w.titles() == [TEA]
    assert NOTARY not in reply.text, reply
    assert reply.question is None or reply.question.kind != "duration", reply
    assert w.tc.insert_calls == []
    parses = [p for k, ps in w.ai.prompts.items() if k.startswith("parse_task") for p in ps]
    assert parses and "а мені треба чай" in parses[-1], parses


# ------------------------------------------------------------------ invariants


def test_I1_a_clarification_does_nothing_until_a_variant_is_chosen() -> None:
    # Scene A: a shown plan and a pending note; scene B: a plan asking its duration (that no word answers).
    a, _ = seeded()
    a.pending_note("a1", SCHMIDT)
    plan_reply = a.plan.start()
    assert plan_reply.question is not None
    plan_q = plan_reply.question
    b, _ = seeded()
    b.ai.task = dict(b.ai.task, duration_min=None)
    duration_reply = b.plan.start()
    assert duration_reply.question is not None and duration_reply.question.kind == "duration", duration_reply
    duration_q = duration_reply.question
    b.ai.duration = {"duration_min": None}
    option_sets: list[list[object]] = [
        ["note", "new_task"],
        ["new_task", "plan_week"],
        ["move", "note"],
        ["note", "note"],
        ["note"],
        [],
        ["unsure", "note"],
        ["edit", "note"],
    ]
    scenes = [
        (a, [None, plan_q, case_q("a1"), Question("clarify", "gone", None)]),
        (b, [None, duration_q]),
    ]
    n = 0
    for w, reply_tos in scenes:
        before = w.everything_else()
        acting = sum(w.ai.count(t) for t in ("parse_task", "classify_case", "describe_case", "name_case"))
        for reply_to in reply_tos:
            for options in option_sets:
                n += 1
                w.ai.unsure(*options)
                reply = w.say(f"двозначна фраза {n}", f"x{n}", reply_to)
                if options in option_sets[:3] or (options == ["edit", "note"] and reply_to == plan_q):
                    clarified(reply)
                assert w.everything_else() == before, (reply_to, options)
        assert (
            sum(w.ai.count(t) for t in ("parse_task", "classify_case", "describe_case", "name_case"))
            == acting
        )
        assert w.calendar.insert_calls == []


def test_I2_the_chosen_variant_runs_once_with_the_text_mama_said() -> None:
    # The button, repeated; then a word under the spent clarification.
    w, _ = seeded()
    question = unsure_wolf(w, "note", "new_task", message_id="m1")
    classified = w.ai.count("classify_case")
    routes = w.routes()
    for option in (1, 1, 2, 1):
        w.button(question.id, option)
    w.ai.option = 1
    w.ai.plain_intent("other")
    w.say("нотаткою", "w9", Question("clarify", question.id, None))
    assert [m.material_id for m in w.materials() if m.text == WOLF] == ["m1"]
    assert w.ai.count("classify_case") == classified + 1
    assert WOLF in w.ai.prompts["classify_case"][classified]
    assert w.routes() == routes + 1
    # The word, then the button and the word again: the new task is started once, with the text said.
    s = stuck_clarify()
    s.ai.unsure("new_task", "note")
    said = "у четвер подзвонити нотаріусу, чи то записати"
    clarified_q = clarified(s.message(said, None))
    s.ai.says(task(NOTARY))
    s.ai.option = 1
    first = s.message("задачею", Question("clarify", clarified_q.id, None))
    assert first.plan is not None, first
    parses = [p for k, ps in s.ai.prompts.items() if k.startswith("parse_task") for p in ps]
    assert len(parses) == 1 and said in parses[0], parses
    assert s.button(clarified_q.id, 1).text == NOT_ACTUAL
    s.ai.route_answer = None
    s.ai.intent = "other"
    s.message("задачею", Question("clarify", clarified_q.id, None))
    parses = [p for k, ps in s.ai.prompts.items() if k.startswith("parse_task") for p in ps]
    assert len(parses) == 1, parses
    assert s.titles() == [NOTARY]


def test_I3_a_word_that_is_no_choice_is_a_new_message_never_the_same_question_or_not_actual() -> None:
    w, _ = seeded()
    live = unsure_wolf(w, "note", "new_task", message_id="m1")
    spent = unsure_wolf(w, "plan_week", "note", message_id="m2")
    w.button(spent.id, 2)
    current = unsure_wolf(w, "note", "new_task", message_id="m3")
    cases: list[tuple[str, int | None]] = [
        (current.id, None),
        (live.id, None),
        (spent.id, None),
        ("never-made", None),
    ]
    for n, (clarify_id, option) in enumerate(cases):
        w.ai.option = option
        w.ai.plain_intent("note")
        w.ai.new_case(SCHMIDT)
        word = f"запиши до пані Шмідт: тиск {120 + n}"
        routes = w.routes()
        reply = w.say(word, f"w{n}", Question("clarify", clarify_id, None))
        assert w.routes() == routes + 1, (clarify_id, option)
        assert reply.text != NOT_ACTUAL, (clarify_id, option, reply)
        assert reply.question is None or reply.question.kind != "clarify", (clarify_id, option, reply)
        assert reply == Reply(ask(SCHMIDT), case_q(f"w{n}")), (clarify_id, option, reply)
        assert w.material(f"w{n}").text == word
    ids = [m.material_id for m in w.materials()]
    assert "m1" not in ids and "m3" not in ids, ids
    kept = w.current()
    assert kept is not None and kept["clarify_id"] == current.id, kept
