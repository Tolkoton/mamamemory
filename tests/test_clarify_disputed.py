"""Disputed contract tests of the slice clarify: each takes one reading of a line that can be read two ways,
and carries the id of its question to the contract (Q1–Q5). Sealed after the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/clarify.md`, without the code.
"""

import re

from mamamemory import assistant
from mamamemory.replies import Question
from tests.case_questions_world import case_q
from tests.clarify_world import Clarify, clarified

KOCH = "пан Кох"
SCHMIDT = "пані Шмідт"
WOLF = "пан Вольф просив виписати рецепт на леводопу"
HINT = (
    "unsure — фраза справді двозначна між двома наміри (наприклад нотатка про людину з дією — note чи "
    "new_task); тоді options — два найімовірніші; коли впевнена — не unsure"
)


def seeded() -> Clarify:
    w = Clarify()
    w.seed(KOCH, "k0")
    w.ai.new_case(SCHMIDT)
    w.ai.default_name = SCHMIDT
    return w


def flat(text: str) -> str:
    """Whitespace made single spaces and apostrophes one character: the contract does not fix typography."""
    return re.sub(r"\s+", " ", re.sub("[’ʼ`]", "'", text)).strip()


def test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to() -> None:
    expected = {
        None: {
            "new_task",
            "plan_week",
            "schedule",
            "note",
            "move",
            "working_on",
            "work_question",
            "recall",
            "tasks",
        },
        "plan": {
            "yes",
            "edit",
            "new_task",
            "plan_week",
            "schedule",
            "note",
            "move",
            "working_on",
            "work_question",
            "recall",
            "tasks",
        },
        "case": {
            "no",
            "not_needed",
            "case_name",
            "new_task",
            "plan_week",
            "schedule",
            "note",
            "move",
            "working_on",
            "work_question",
            "recall",
            "tasks",
        },
    }
    reply_tos = {None: None, "plan": Question("plan", "p1", "fp"), "case": case_q("a1")}
    for key, reply_to in reply_tos.items():
        options = assistant.route_schema(reply_to)["properties"].get("options")
        assert isinstance(options, dict), (key, options)
        items = options.get("items")
        assert isinstance(items, dict), (key, options)
        assert set(items.get("enum") or []) == expected[key], (key, options)


def test_Q2_yes_under_a_case_question_is_no_valid_option() -> None:
    w = seeded()
    w.pending_note("a1", SCHMIDT)
    w.ai.unsure("yes", "note")
    reply = w.say("так, до Шмідт", "w1", case_q("a1"))
    assert reply.question is None or reply.question.kind != "clarify", reply
    assert w.current() is None
    # The same question with two options allowed under it is a clarification: the refusal was for `yes`.
    w.ai.unsure("case_name", "note")
    clarified(w.say("до Шмідт", "w2", case_q("a1")))


def test_Q3_route_prompt_carries_the_unsure_hint_word_for_word() -> None:
    w = seeded()
    w.ai.plain_intent("other")
    w.say("щось", "w1")
    assert flat(HINT) in flat(w.ai.prompts["route"][-1])


def test_Q4_a_chosen_clarification_document_is_deleted() -> None:
    w = seeded()
    w.ai.unsure("note", "new_task")
    question = clarified(w.say(WOLF, "m1"))
    assert w.current() is not None
    w.button(question.id, 1)
    assert w.current() is None
    w.ai.unsure("note", "new_task")
    second = clarified(w.say("друга двозначна фраза", "m2"))
    w.ai.option = 1
    w.say("нотаткою", "w3", Question("clarify", second.id, None))
    assert w.current() is None


def test_Q5_choices_are_the_phrases_of_the_two_options_in_their_order() -> None:
    w = seeded()
    w.ai.unsure("note", "new_task")
    reply = w.say(WOLF, "m1")
    clarified(reply)
    assert reply.choices == ["записати нотаткою до справи", "поставити задачею в календар"]
