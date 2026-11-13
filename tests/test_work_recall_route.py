"""Contract tests of the intent `work_question` of `assistant` and the model type `answer_work`
(slice work-recall, Seam 3).

Written by the slice tester from the sealed contract `.engine/slices/work-recall.md`, without the code.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Berlin).
"""

from mamamemory import assistant
from mamamemory.config import DEFAULT_MODELS
from mamamemory.replies import Question
from tests.work_recall_world import ANSWER_WORK, NOTHING, Recall, iso
from tests.working_on_world import plain

HINT = (
    "work_question — мама питає, що вона робила чи над чим працювала («що я робила з договором?», "
    "«над чим я працювала вчора?»); це не schedule (заплановане в календарі)"
)
QUESTION = "що я робила з договором?"
MODEL_TEXT = "Учора о 12:00 ви працювали над договором."
REPLY_TOS: list[Question | None] = [
    None,
    Question("plan", "plan-x", "fp-x"),
    Question("case", "mat-x", None),
    Question("duration", "plan-x", None),
    Question("limits", "plan-x", None),
    Question("priorities", "plan-x", None),
    Question("clarify", "cl-x", None),
]


def test_seam3_work_question_is_in_the_route_schema_for_every_reply_to() -> None:
    assert "work_question" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    for reply_to in REPLY_TOS:
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "work_question" in enum, (reply_to, enum)


def test_seam3_work_question_is_always_allowed() -> None:
    assert "work_question" in assistant.ALWAYS
    for reply_to in REPLY_TOS:
        assert "work_question" in assistant.allowed(reply_to), reply_to


def test_work_question_phrase() -> None:
    assert assistant.PHRASES["work_question"] == "згадати, що ви робили"


def test_seam3_dispatch_answers_from_the_journal() -> None:
    w = Recall()
    w.put("e1", "працюю над договором купівлі", iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"found": True, "answer": MODEL_TEXT}
    reply = w.ask(QUESTION, "m1")
    assert reply.text == MODEL_TEXT
    assert reply.question is None
    prompt = w.ai.work_prompt()
    assert QUESTION in prompt
    assert "працюю над договором купівлі" in prompt
    assert "timezone" in w.calendar.log


def test_dispatch_with_an_empty_journal_is_nothing() -> None:
    w = Recall()
    reply = w.ask(QUESTION, "m1")
    assert reply.text == NOTHING
    assert reply.question is None
    assert ANSWER_WORK not in w.ai.calls


def test_seam3_route_prompt_carries_the_work_question_hint() -> None:
    w = Recall()
    w.ask(QUESTION, "m1")
    assert w.ai.prompts.get("route"), w.ai.prompts
    assert plain(HINT) in plain(w.ai.prompts["route"][-1])


def test_answer_work_is_a_flash_lite_model_type() -> None:
    assert ANSWER_WORK in DEFAULT_MODELS
    assert "flash-lite" in DEFAULT_MODELS[ANSWER_WORK].model


def test_answer_work_schema_has_found_and_answer_both_required() -> None:
    w = Recall()
    w.put("e1", "працюю над договором купівлі", iso(2026, 11, 11, 11, 0))
    w.answer(QUESTION)
    schemas = w.ai.schemas.get(ANSWER_WORK)
    assert schemas and len(schemas) == 1, w.ai.schemas
    schema = schemas[0]
    properties = schema["properties"]
    assert properties["found"]["type"] == "boolean"
    assert properties["answer"]["type"] == "string"
    assert set(schema["required"]) == {"found", "answer"}
