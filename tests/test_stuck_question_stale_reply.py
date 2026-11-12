"""A reply to a question older than 24 h (overseer test gap, stuck-question): even a phrase that parses as an
answer is not written into the old draft: `try_answer_duration` gives `None`, routed as a new message."""

from datetime import timedelta
from typing import cast

from mamamemory import planning
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from tests.test_one_task_planning import NOW, world


def test_a_duration_reply_to_a_stale_question_is_no_answer() -> None:
    w = world(duration_min=None)
    asked = w.start()
    assert asked.question is not None and asked.question.kind == "duration"
    before = w.store.get(w.session.account_id, planning.DRAFT_PATH)
    late = NOW + timedelta(hours=25)
    found = planning.try_answer_duration(
        w.session, asked.question.id, "пів години", ai=cast(AI, w.ai), calendar=cast(GoogleWork, w.calendar),
        store=w.store, now=late, config=w.config,
    )  # fmt: skip
    assert found is None
    assert w.store.get(w.session.account_id, planning.DRAFT_PATH) == before
    # Within 24 h the same reply is the answer.
    assert planning.try_answer_duration(
        w.session, asked.question.id, "пів години", ai=cast(AI, w.ai), calendar=cast(GoogleWork, w.calendar),
        store=w.store, now=NOW + timedelta(hours=1), config=w.config,
    ) is not None  # fmt: skip
