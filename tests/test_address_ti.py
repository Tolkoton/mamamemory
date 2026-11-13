"""Contract tests of the slice address-ti: the shared sentence `cases.worklog.ADDRESS` stands, word for word,
in the prompts of `answer_work` (`cases.worklog.answer`) and `answer_case` (`cases.recall.recall`), before
«Мама питає» (Seam 1).

Written by the slice tester from the sealed contract `.engine/slices/address-ti.md`, without the code.
The sentence is written out by hand from the contract; the tests do not take it from the code alone.
"""

from datetime import UTC, datetime

from mamamemory.cases import worklog
from tests.case_recall_world import CaseRecall
from tests.work_recall_world import Recall, iso

ADDRESS = (
    "Звертайся до мами на «ти», у другій особі однини («ти працювала», «твої записи»); не «ви» і не «мама» в "
    "третій особі."
)
ASKS = "Мама питає"
SCHMIDT = "пані Шмідт"


def assert_address_before_question(prompt: str) -> None:
    assert ADDRESS in prompt, prompt
    assert ASKS in prompt, prompt
    assert prompt.index(ADDRESS) < prompt.index(ASKS), prompt


def test_seam1_answer_work_prompt_carries_address_before_the_question() -> None:
    assert worklog.ADDRESS == ADDRESS
    w = Recall()
    w.put("e1", "працюю над договором купівлі", iso(2026, 11, 11, 11, 0))
    w.answer("що я робила з договором?")
    assert_address_before_question(w.ai.work_prompt())


def test_seam1_answer_case_prompt_carries_address_before_the_question() -> None:
    assert worklog.ADDRESS == ADDRESS
    w = CaseRecall()
    w.put_case("c-s", SCHMIDT, "пацієнтка, щитоподібна залоза", datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
    w.put_material("m-s", "ТТГ 4,9, повторити через шість тижнів", "c-s")
    w.put("e1", "дзвонила пані Шмідт", iso(2026, 11, 11, 11, 0))
    w.ai.pick(SCHMIDT)
    w.recall("що ми знаємо про пані Шмідт?")
    assert_address_before_question(w.ai.case_prompt())
