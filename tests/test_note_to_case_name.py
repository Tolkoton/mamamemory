"""The first note of an account (empty catalogue) when `name_case` gives no name (overseer test gap, F3 S1):
the note is kept unplaced, «Не зрозуміла…», no case, the Розкладач is not called."""

from typing import Any

import pytest

from tests.note_to_case_world import NOT_UNDERSTOOD, CaseAI, Notes


class NoName(CaseAI):
    def __init__(self, name: Any) -> None:
        super().__init__()
        self.name = name

    def generate_json(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "name_case":
            self.calls.append(task_type)
            return {"name": self.name}
        return super().generate_json(task_type, prompt, schema)


@pytest.mark.parametrize("name", [None, "", "   "])
def test_first_note_without_a_name_is_unplaced(name: Any) -> None:
    world = Notes(ai=NoName(name))
    reply = world.add("щось незрозуміле", "m-1")
    assert reply.text == NOT_UNDERSTOOD
    assert reply.question is None
    assert world.material("m-1").state == "unplaced"
    assert world.cases() == []
    assert world.ai.count("classify_case") == 0
