"""Builder's own tests of time-limits answers: on «Як минулого разу — …?» an answer that names nothing is
acceptance only when the model read it as «так»; anything else asks again (contract: «Нерозібрана відповідь —
те саме питання ще раз»). A partial answer keeps the saved fields it does not name."""

from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.test_time_limits_planning import first_planning
from tests.time_limits_world import WEEKDAYS, limited, limits_question, parsed


def test_no_to_as_last_time_names_nothing_and_asks_again() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    w.ai.says(task(MEDICINE))
    question = limits_question(w.start("купити ліки"))
    writes = len(w.store.limits_writes)
    w.ai.limits = parsed(same_as_last=False)
    again = w.answer_limits(question.id, "ні")
    assert limits_question(again) == question
    assert w.saved() == (WEEKDAYS, "14:00", "18:00")
    assert len(w.store.limits_writes) == writes


def test_hours_only_over_saved_limits_keep_the_saved_days() -> None:
    w = limited(task(NOTARY))
    first_planning(w)
    w.ai.says(task(MEDICINE))
    question = limits_question(w.start("купити ліки"))
    w.ai.limits = parsed(start_local="10:00", end_local="16:00")
    reply = w.answer_limits(question.id, "тепер з десятої до четвертої")
    assert reply.plan is not None
    assert w.saved() == (WEEKDAYS, "10:00", "16:00")
