"""Contract tests of the intent `recall` of `assistant`, the model type `answer_case` and the guide's two new
lines (slice case-recall, Seam 3); the guide test superseded by tasks-list (the tasks line before 🔊).

Written by the slice tester from the sealed contract `.engine/slices/case-recall.md`, without the code.
The contract does not fix the apostrophe's typography nor whitespace around the guide (as in the guide slice):
the guide is compared with its apostrophes made one character, «...» made «…» and its ends stripped.
"""

import re

from mamamemory import assistant
from mamamemory.config import DEFAULT_MODELS
from mamamemory.replies import Question
from tests.case_recall_world import ANSWER_CASE, MODEL_TEXT, NOT_FOUND, CaseRecall
from tests.working_on_world import plain

HINT = (
    "recall — мама питає, що відомо про людину чи справу («що ми знаємо про пані Шмідт?», «що вже "
    "з'ясували по городу?», «нагадай про пана Коха»); це не note (вона нічого не просить записати) і не "
    "work_question (питає про справу, не про свою роботу)"
)
GUIDE = (
    "Я допомагаю планувати й пам'ятати справи. Що можна сказати:\n"
    "• «Додай задачу подзвонити нотаріусу в понеділок» — поставлю в календар.\n"
    "• «Сплануй тиждень» — складу план з усіх задач.\n"
    "• «Запиши до пані Шмідт: …», або ＋ (фото чи файл) — покладу у справу.\n"
    "• «Переклади … до …» — перенесу в іншу справу.\n"
    "• «Працюю над …», потім «що я робила з …?» — запам'ятаю й нагадаю.\n"
    "• «Що ми знаємо про пані Шмідт?», «які плани на тиждень?» — розповім.\n"
    "• «Які в мене задачі?» — покажу список задач.\n"
    "• 🔊 біля відповіді — прочитаю вголос.\n"
    "Не зрозумію — перепитаю."
)
QUESTION = "що ми знаємо про пані Шмідт?"
REPLY_TOS: list[Question | None] = [
    None,
    Question("plan", "plan-x", "fp-x"),
    Question("case", "mat-x", None),
    Question("duration", "plan-x", None),
    Question("limits", "plan-x", None),
    Question("priorities", "plan-x", None),
    Question("clarify", "cl-x", None),
]


def guide_form(text: str) -> str:
    """Apostrophes one character, «...» one «…», the ends stripped; the lines as they are."""
    return re.sub("[’ʼ`]", "'", text).replace("...", "…").strip()


def test_seam3_recall_is_in_the_route_schema_for_every_reply_to() -> None:
    assert "recall" in assistant.ROUTE_SCHEMA["properties"]["intent"]["enum"]
    for reply_to in REPLY_TOS:
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "recall" in enum, (reply_to, enum)


def test_seam3_recall_is_always_allowed() -> None:
    assert "recall" in assistant.ALWAYS
    for reply_to in REPLY_TOS:
        assert "recall" in assistant.allowed(reply_to), reply_to


def test_recall_phrase() -> None:
    assert assistant.PHRASES.get("recall") == "розповісти, що відомо про справу"


def test_seam3_dispatch_answers_from_the_case() -> None:
    w = CaseRecall()
    w.put_case("c-s", "пані Шмідт", "пацієнтка")
    w.put_material("m-s", "ТТГ 4,9, повторити через шість тижнів", "c-s")
    w.put("e1", "працюю над аналізами", "2026-11-11T11:00:00+00:00")
    w.ai.pick("пані Шмідт")
    reply = w.ask_case(QUESTION, "m1")
    assert reply.text == MODEL_TEXT
    assert reply.question is None
    prompt = w.ai.case_prompt()
    assert QUESTION in prompt
    assert "ТТГ 4,9, повторити через шість тижнів" in prompt
    assert "працюю над аналізами" in prompt
    assert "12:00" in prompt  # 11:00Z is 12:00 in Berlin: the calendar was passed through


def test_dispatch_with_an_empty_catalogue_is_not_found() -> None:
    w = CaseRecall()
    w.ai.pick("пані Шмідт")
    reply = w.ask_case(QUESTION, "m1")
    assert reply.text == NOT_FOUND
    assert reply.question is None
    assert ANSWER_CASE not in w.ai.calls
    assert "classify_case" not in w.ai.calls


def test_seam3_route_prompt_carries_the_recall_hint() -> None:
    w = CaseRecall()
    w.ask_case(QUESTION, "m1")
    assert w.ai.prompts.get("route"), w.ai.prompts
    assert plain(HINT) in plain(w.ai.prompts["route"][-1])


def test_answer_case_is_a_flash_lite_model_type() -> None:
    assert ANSWER_CASE in DEFAULT_MODELS
    assert "flash-lite" in DEFAULT_MODELS[ANSWER_CASE].model


def test_seam3_guide_is_ten_lines_with_the_two_new_and_the_tasks_line_before_the_read_aloud_line() -> None:
    # tasks-list: the tasks line stands right before the 🔊 line; the guide is now 10 lines.
    assert guide_form(assistant.GUIDE_UK) == GUIDE
    assert guide_form(assistant.guide_text("uk")) == GUIDE
    lines = guide_form(assistant.GUIDE_UK).split("\n")
    assert len(lines) == 10
    assert lines[7] == "• «Які в мене задачі?» — покажу список задач."
    assert lines[8].startswith("• 🔊")
