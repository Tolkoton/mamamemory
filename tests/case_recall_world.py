"""Test helpers of the slice case-recall: a model fake whose `classify_case` names a case of the catalogue (by
the number standing in front of its name in the prompt) or answers a raw `number`, and whose `answer_case`
answers as told and records its prompt and schema; a world around `cases.recall.recall` and
`assistant.handle_message` over the work-recall world.

Written by the slice tester from the sealed contract `.engine/slices/case-recall.md`, without the code.
Cases and materials are put into the store as documents of F3 (`cases/{id}`, `materials/{id}`), the journal as
documents of F4 S1 (`work/{id}`). `NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Europe/Berlin).
Every expected text and time is written by hand.
"""

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from mamamemory import cases as case_module
from mamamemory.cases import recall as case_recall
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.replies import Question, Reply
from tests.note_to_case_world import listed_number
from tests.work_recall_world import NOW, Recall, RecallAI

CLASSIFY = "classify_case"
ANSWER_CASE = "answer_case"
NOT_FOUND = "Не знайшла такої справи. Скажіть ім'я чи назву інакше."
MODEL_TEXT = "Пані Шмідт: ТТГ 4,9, повторити через шість тижнів."
_UNSET = object()


def nothing_yet(name: str) -> str:
    """«Про «<name>» поки нічого не записано.»"""
    return f"Про «{name}» поки нічого не записано."


class CaseRecallAI(RecallAI):
    """The work-recall fake. While `picking` is set, `classify_case` answers `{"number": …}`: the number in
    front of `pick_name` in the prompt, or `pick_raw` as it is.
    `answer_case` answers `case_answer` (a copy)."""

    def __init__(self) -> None:
        super().__init__()
        self.picking = False
        self.pick_name: str | None = None
        self.pick_raw: object = _UNSET
        self.case_answer: dict[str, Any] = {"found": True, "answer": MODEL_TEXT}

    def pick(self, name: str) -> None:
        self.picking, self.pick_name, self.pick_raw = True, name, _UNSET

    def pick_value(self, value: object) -> None:
        self.picking, self.pick_name, self.pick_raw = True, None, value

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == CLASSIFY and self.picking:
            self.calls.append(task_type)
            self.schemas.setdefault(task_type, []).append(copy.deepcopy(schema))
            if self.pick_raw is not _UNSET:
                return {"number": self.pick_raw}
            number = listed_number(prompt, self.pick_name) if self.pick_name is not None else None
            return {"number": number}
        if task_type == ANSWER_CASE:
            self.calls.append(task_type)
            self.schemas.setdefault(task_type, []).append(copy.deepcopy(schema))
            return copy.deepcopy(self.case_answer)
        return super()._answer(task_type, prompt, schema)

    def case_prompts(self) -> list[str]:
        return self.prompts.get(ANSWER_CASE, [])

    def case_prompt(self) -> str:
        prompts = self.case_prompts()
        assert len(prompts) == 1, f"expected one answer_case call, got {len(prompts)}"
        return prompts[0]

    def classify_prompt(self) -> str:
        prompts = self.prompts.get(CLASSIFY, [])
        assert prompts, "expected a classify_case call"
        return prompts[-1]


@dataclass
class CaseRecall(Recall):
    ai: CaseRecallAI = field(default_factory=CaseRecallAI)

    def put_case(
        self,
        case_id: str,
        name: str,
        description: str = "",
        created: datetime = datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
        account_id: str | None = None,
    ) -> None:
        """A case document as F3 keeps it."""
        data = {"name": name, "description": description, "created": created.isoformat(), "stale": False}
        self.store.set(account_id or self.session.account_id, f"{case_module.CASES}/{case_id}", data)

    def put_material(
        self,
        material_id: str,
        text: str,
        case_id: str | None,
        *,
        kind: str = "note",
        created: datetime = datetime(2026, 11, 2, 8, 0, tzinfo=UTC),
        pending_case: str | None = None,
        account_id: str | None = None,
    ) -> None:
        """A material document as F3 keeps it: `placed` with a case, else `pending` (with a proposed name) or
        `unplaced`."""
        state = "placed" if case_id is not None else ("pending" if pending_case is not None else "unplaced")
        data: dict[str, Any] = {
            "kind": kind,
            "text": text,
            "state": state,
            "case_id": case_id,
            "pending_case": pending_case,
            "gs_uri": None,
            "mime": None,
            "created": created.isoformat(),
            "in_description": False,
            "asked": "create" if state == "pending" else None,
        }
        self.store.set(account_id or self.session.account_id, f"{case_module.MATERIALS}/{material_id}", data)

    def recall(self, question: str, now: datetime = NOW) -> Reply:
        return case_recall.recall(
            self.session,
            question,
            store=self.store,
            ai=cast(AI, self.ai),
            calendar=cast(GoogleWork, self.calendar),
            now=now,
        )

    def ask_case(
        self, text: str, message_id: str, reply_to: Question | None = None, now: datetime = NOW
    ) -> Reply:
        """A message the route names `recall`."""
        self.ai.plain_intent("recall")
        return self.message_any(text, message_id, reply_to, now)
