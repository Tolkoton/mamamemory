"""`assistant.route_schema` (overseer test gap, F3 S4): answers to a case question exist only under one."""

from mamamemory import assistant
from mamamemory.replies import Question


def intents(reply_to: Question | None) -> list[str]:
    enum: list[str] = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
    return enum


def test_without_a_case_question_the_case_answers_are_not_offered() -> None:
    for reply_to in (None, Question("plan", "p", "fp"), Question("duration", "p", None)):
        offered = intents(reply_to)
        assert not {"no", "not_needed", "case_name"} & set(offered), offered
        assert {"yes", "new_task", "edit", "note", "move", "other"} <= set(offered), offered


def test_under_a_case_question_the_full_schema_is_offered() -> None:
    case_schema = assistant.route_schema(Question("case", "m", None))
    assert intents(Question("case", "m", None)) == assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    assert case_schema["required"] == assistant.ROUTE_SCHEMA["required"]
    assert {"yes", "no", "not_needed", "case_name"} <= set(intents(Question("case", "m", None)))
