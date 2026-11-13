"""Contract tests of the slice case-recall: `cases.recall.recall` — the choice of the case (Seam 1), the
prompt and the reply of `answer_case` (Seam 2), the invariants I1 and I2.

Written by the slice tester from the sealed contract `.engine/slices/case-recall.md`, without the code.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Berlin). Europe/Berlin is UTC+1 in November, Asia/Tokyo
is UTC+9. The form of a material's kind and date, and of an entry's weekday and date, are questions Q1 and Q2
and are tested in `test_case_recall_disputed.py` only: here an entry is checked by its local time "HH:MM".
"""

from datetime import UTC, datetime, timedelta

import pytest

from tests.case_questions_world import case_q
from tests.case_recall_world import (
    ANSWER_CASE,
    CLASSIFY,
    MODEL_TEXT,
    NOT_FOUND,
    CaseRecall,
    nothing_yet,
)
from tests.note_to_case_world import ModelFailed
from tests.work_recall_world import CalendarDown, ZoneCalendar, iso, token

SCHMIDT = "пані Шмідт"
GARDEN = "купівля городу"
KOCH = "пан Кох"
SCHMIDT_ABOUT = "пацієнтка, щитоподібна залоза"
GARDEN_ABOUT = "ділянка біля річки, договір з власником"
KOCH_ABOUT = "пацієнт, аналізи крові"
TTG = "ТТГ 4,9, повторити через шість тижнів"
CONTRACT = "договір купівлі підписати до п'ятниці"
KOCH_BLOOD = "гемоглобін 128"
Q_SCHMIDT = "що ми знаємо про пані Шмідт?"
Q_GARDEN = "що вже з'ясували по городу?"


def three_cases(w: CaseRecall) -> None:
    """Schmidt, the garden and Koch, created in this order, each with one material."""
    w.put_case("c-s", SCHMIDT, SCHMIDT_ABOUT, datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
    w.put_case("c-g", GARDEN, GARDEN_ABOUT, datetime(2026, 11, 2, 8, 0, tzinfo=UTC))
    w.put_case("c-k", KOCH, KOCH_ABOUT, datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
    w.put_material("m-s", TTG, "c-s", created=datetime(2026, 11, 4, 8, 0, tzinfo=UTC))
    w.put_material("m-g", CONTRACT, "c-g", created=datetime(2026, 11, 5, 8, 0, tzinfo=UTC))
    w.put_material("m-k", KOCH_BLOOD, "c-k", created=datetime(2026, 11, 6, 8, 0, tzinfo=UTC))


# ------------------------------------------------------------------ Seam 1: the choice of the case


def test_seam1_empty_catalogue_is_not_found_without_a_model() -> None:
    w = CaseRecall()
    w.put_material("m1", "нотатка без справи", None)
    w.put("e1", "працюю над договором", iso(2026, 11, 11, 11, 0))
    w.ai.pick(SCHMIDT)
    reply = w.recall(Q_SCHMIDT)
    assert reply.text == NOT_FOUND
    assert reply.question is None and reply.plan is None and reply.choices is None
    assert w.ai.calls == []
    assert w.ai.prompts == {}


def test_seam1_classify_prompt_carries_the_catalogue_with_descriptions_and_the_question() -> None:
    w = CaseRecall()
    three_cases(w)
    w.ai.pick(GARDEN)
    w.recall(Q_GARDEN)
    assert w.ai.calls.count(CLASSIFY) == 1
    prompt = w.ai.classify_prompt()
    for text in (SCHMIDT, SCHMIDT_ABOUT, GARDEN, GARDEN_ABOUT, KOCH, KOCH_ABOUT, Q_GARDEN):
        assert text in prompt, (text, prompt)


def test_seam1_classify_schema_has_a_required_integer_number() -> None:
    w = CaseRecall()
    three_cases(w)
    w.ai.pick(GARDEN)
    w.recall(Q_GARDEN)
    schemas = w.ai.schemas.get(CLASSIFY)
    assert schemas and len(schemas) == 1, w.ai.schemas
    schema = schemas[0]
    spec = schema["properties"]["number"]
    kind = spec["type"]
    assert kind == "integer" or (isinstance(kind, list) and "integer" in kind), spec
    assert "number" in schema["required"]


def test_seam1_number_null_not_an_integer_or_outside_the_catalogue_is_not_found() -> None:
    w = CaseRecall()
    w.put_case("c-s", SCHMIDT, SCHMIDT_ABOUT, datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
    w.put_material("m-s", TTG, "c-s")
    w.put("e1", "працюю над аналізами", iso(2026, 11, 11, 11, 0))
    # one case: a null still is NOT_FOUND (the model is asked even for one case)
    w.ai.pick_value(None)
    reply = w.recall(Q_SCHMIDT)
    assert reply.text == NOT_FOUND and reply.question is None, reply
    w.put_case("c-g", GARDEN, GARDEN_ABOUT, datetime(2026, 11, 2, 8, 0, tzinfo=UTC))
    w.put_material("m-g", CONTRACT, "c-g")
    # two cases, numbered 1 and 2
    for value in (None, 0, 3, -1, 100, "пані Шмідт", True, False, [1], {"n": 1}):
        w.ai.pick_value(value)
        reply = w.recall(Q_SCHMIDT)
        assert reply.text == NOT_FOUND, (value, reply)
        assert reply.question is None, (value, reply)
    assert ANSWER_CASE not in w.ai.calls
    assert w.ai.case_prompts() == []


# ------------------------------------------------------------------ Seam 2: the prompt of answer_case


def test_seam2_prompt_carries_name_description_every_material_of_the_case_and_the_question() -> None:
    w = CaseRecall()
    three_cases(w)
    w.put_material(
        "m-s2", "УЗД без змін", "c-s", kind="photo", created=datetime(2026, 11, 7, 8, 0, tzinfo=UTC)
    )
    w.put_material("m-s3", "направлення до ендокринолога", "c-s", kind="file")
    w.ai.pick(SCHMIDT)
    w.recall(Q_SCHMIDT)
    prompt = w.ai.case_prompt()
    for text in (SCHMIDT, SCHMIDT_ABOUT, TTG, "УЗД без змін", "направлення до ендокринолога", Q_SCHMIDT):
        assert text in prompt, (text, prompt)
    for text in (CONTRACT, KOCH_BLOOD):
        assert text not in prompt, (text, prompt)


def test_seam2_prompt_carries_every_journal_entry_with_its_time_in_the_calendar_zone() -> None:
    w = CaseRecall()
    three_cases(w)
    w.put("e1", "працюю над договором купівлі городу", iso(2026, 11, 11, 11, 0))
    w.put("e2", "сиджу над аналізами пана Коха", iso(2026, 11, 9, 23, 30))
    w.ai.pick(GARDEN)
    w.recall(Q_GARDEN)
    prompt = w.ai.case_prompt()
    assert "працюю над договором купівлі городу" in prompt
    assert "сиджу над аналізами пана Коха" in prompt  # the model, not the code, picks the entries
    assert "12:00" in prompt  # 11:00Z is 12:00 in Berlin
    assert "00:30" in prompt  # 23:30Z on Monday 9 is 00:30 on Tuesday 10 in Berlin
    assert "23:30" not in prompt
    assert "timezone" in w.calendar.log


def test_seam2_entry_zone_is_the_calendar_s_not_a_fixed_one() -> None:
    w = CaseRecall(calendar=ZoneCalendar("Asia/Tokyo"))
    three_cases(w)
    w.put("e1", "працюю над договором купівлі городу", iso(2026, 11, 9, 23, 30))
    w.ai.pick(GARDEN)
    w.recall(Q_GARDEN)
    prompt = w.ai.case_prompt()
    assert "08:30" in prompt  # 23:30Z is 08:30 on Tuesday 10 in Tokyo
    assert "00:30" not in prompt
    assert "23:30" not in prompt


def test_seam2_no_entries_the_calendar_is_not_called() -> None:
    w = CaseRecall()
    three_cases(w)
    w.put("x", "чужий запис", iso(2026, 11, 11, 11, 0), account_id="acc-2")
    w.ai.pick(SCHMIDT)
    reply = w.recall(Q_SCHMIDT)
    assert reply.text == MODEL_TEXT
    assert TTG in w.ai.case_prompt()
    assert "чужий запис" not in w.ai.case_prompt()
    assert w.calendar.log == []


def test_seam2_empty_case_without_entries_is_nothing_yet_without_answer_case() -> None:
    w = CaseRecall()
    three_cases(w)
    w.put_case("c-m", "пан Мюллер", "", datetime(2026, 11, 8, 8, 0, tzinfo=UTC))
    w.put_material("m-x", "нотатка без справи", None)
    w.ai.pick("пан Мюллер")
    reply = w.recall("що ми знаємо про пана Мюллера?")
    assert reply.text == nothing_yet("пан Мюллер")
    assert reply.question is None and reply.plan is None and reply.choices is None
    assert w.ai.calls == [CLASSIFY]
    assert w.ai.case_prompts() == []


def test_seam2_a_description_materials_or_entries_alone_go_to_answer_case() -> None:
    # only a description
    w = CaseRecall()
    w.put_case("c-m", "пан Мюллер", "сусід, позичав драбину")
    w.ai.pick("пан Мюллер")
    assert w.recall("нагадай про пана Мюллера").text == MODEL_TEXT
    assert "сусід, позичав драбину" in w.ai.case_prompt()
    # only a material
    w = CaseRecall()
    w.put_case("c-m", "пан Мюллер", "")
    w.put_material("m1", "повернути драбину", "c-m")
    w.ai.pick("пан Мюллер")
    assert w.recall("нагадай про пана Мюллера").text == MODEL_TEXT
    assert "повернути драбину" in w.ai.case_prompt()
    # only a journal entry (entries carry no case: the model picks them)
    w = CaseRecall()
    w.put_case("c-m", "пан Мюллер", "")
    w.put("e1", "дзвонила пану Мюллеру", iso(2026, 11, 11, 11, 0))
    w.ai.pick("пан Мюллер")
    assert w.recall("нагадай про пана Мюллера").text == MODEL_TEXT
    assert "дзвонила пану Мюллеру" in w.ai.case_prompt()


def test_seam2_answer_case_schema_has_found_and_answer_both_required() -> None:
    w = CaseRecall()
    three_cases(w)
    w.ai.pick(SCHMIDT)
    w.recall(Q_SCHMIDT)
    schemas = w.ai.schemas.get(ANSWER_CASE)
    assert schemas and len(schemas) == 1, w.ai.schemas
    schema = schemas[0]
    assert schema["properties"]["found"]["type"] == "boolean"
    assert schema["properties"]["answer"]["type"] == "string"
    assert set(schema["required"]) == {"found", "answer"}


def test_seam2_found_true_is_the_model_s_answer_without_a_question() -> None:
    w = CaseRecall()
    three_cases(w)
    w.ai.pick(SCHMIDT)
    w.ai.case_answer = {"found": True, "answer": MODEL_TEXT}
    reply = w.recall(Q_SCHMIDT)
    assert reply.text == MODEL_TEXT
    assert reply.question is None and reply.plan is None and reply.choices is None


def test_seam2_found_not_true_or_empty_answer_is_nothing_yet() -> None:
    for answer in (
        {"found": False, "answer": MODEL_TEXT},
        {"answer": MODEL_TEXT},
        {"found": True, "answer": ""},
        {"found": True, "answer": "  \n "},
        {"found": None, "answer": MODEL_TEXT},
    ):
        w = CaseRecall()
        three_cases(w)
        w.ai.pick(SCHMIDT)
        w.ai.case_answer = answer
        reply = w.recall(Q_SCHMIDT)
        assert reply.text == nothing_yet(SCHMIDT), (answer, reply)
        assert reply.question is None, (answer, reply)


def test_seam2_a_model_error_is_raised_and_nothing_is_written() -> None:
    for task_type in (CLASSIFY, ANSWER_CASE):
        w = CaseRecall()
        three_cases(w)
        w.put("e1", "працюю над договором", iso(2026, 11, 11, 11, 0))
        w.ai.pick(SCHMIDT)
        w.ai.fail[task_type] = 1
        before = w.written_state()
        with pytest.raises(ModelFailed):
            w.recall(Q_SCHMIDT)
        assert w.written_state() == before, task_type
        assert w.calendar.writes() == [], task_type


def test_seam2_a_calendar_error_is_raised_and_nothing_is_written() -> None:
    w = CaseRecall(calendar=ZoneCalendar(down=True))
    three_cases(w)
    w.put("e1", "працюю над договором", iso(2026, 11, 11, 11, 0))
    w.ai.pick(SCHMIDT)
    before = w.written_state()
    with pytest.raises(CalendarDown):
        w.recall(Q_SCHMIDT)
    assert w.written_state() == before
    assert w.calendar.writes() == []


# ------------------------------------------------------------------ invariants


def test_I1_recall_writes_nothing() -> None:
    w = CaseRecall()
    # A case question and a shown plan made the lawful way, before the intent is measured.
    w.pending_note("a1", SCHMIDT)
    reply_tos = [None, w.plan_question(), case_q("a1")]
    inserts_before = list(w.calendar.insert_calls)
    w.calendar.log.clear()
    questions = [Q_SCHMIDT, Q_GARDEN, "нагадай про пана Коха", "запиши до пані Шмідт: аналізи в нормі"]

    def ask_all(size: str, expected: str) -> None:
        before = w.written_state()
        for r, reply_to in enumerate(reply_tos):
            for q, question in enumerate(questions):
                for _ in range(2):  # the app repeats the same message
                    reply = w.ask_case(question, f"{size}-{r}-{q}", reply_to)
                    assert reply.text == expected, (size, reply_to, question, reply)
                    assert reply.question is None, (size, reply_to, question, reply)
        assert w.written_state() == before, size
        assert w.calendar.writes() == [], size
        assert w.calendar.insert_calls == inserts_before, size

    # an empty catalogue (the pending note proposes a case that does not exist yet)
    w.ai.pick(SCHMIDT)
    ask_all("empty", NOT_FOUND)
    # one case, empty
    w.put_case("c-s", SCHMIDT, "")
    ask_all("one-empty", nothing_yet(SCHMIDT))
    # one case with a material
    w.put_material("m-s", TTG, "c-s")
    ask_all("one", MODEL_TEXT)
    # many cases, materials, a journal of over 100 entries
    w.put_case("c-g", GARDEN, GARDEN_ABOUT, datetime(2026, 11, 2, 8, 0, tzinfo=UTC))
    w.put_case("c-k", KOCH, KOCH_ABOUT, datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
    w.put_material("m-g", CONTRACT, "c-g")
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    for k in range(101):
        w.put(f"e{k:03d}", token(k), (base - timedelta(days=k)).isoformat())
    ask_all("many", MODEL_TEXT)
    # the model names no case, a case outside the catalogue, then finds nothing
    w.ai.pick_value(None)
    ask_all("none", NOT_FOUND)
    w.ai.pick_value(4)
    ask_all("outside", NOT_FOUND)
    w.ai.pick(KOCH)
    w.ai.case_answer = {"found": False, "answer": ""}
    ask_all("not-found", nothing_yet(KOCH))


def test_I2_the_answer_prompt_never_carries_a_material_of_another_case() -> None:
    w = CaseRecall()
    names = {"c1": SCHMIDT, "c2": GARDEN, "c3": KOCH, "c4": "пан Мюллер"}
    for n, (case_id, name) in enumerate(names.items()):
        w.put_case(case_id, name, f"опис {name}", datetime(2026, 11, 1 + n, 8, 0, tzinfo=UTC))
    # c1: two materials, c2: one, c3: three, c4: none (a description only)
    own = {
        "c1": [token(1), token(2)],
        "c2": [token(3)],
        "c3": [token(4), token(5), token(6)],
        "c4": [],
    }
    number = 0
    for case_id, texts in own.items():
        for text in texts:
            number += 1
            w.put_material(f"m{number}", text, case_id, kind=("note", "photo", "file")[number % 3])
    # materials with no case: unplaced, and pending with every case's name proposed
    w.put_material("u1", token(20), None)
    for n, name in enumerate(names.values()):
        w.put_material(f"p{n}", token(21 + n), None, pending_case=name)
    # another account: a case with the same id and name, with a material
    w.put_case("c1", SCHMIDT, "чужий опис", account_id="acc-2")
    w.put_material("x1", token(30), "c1", account_id="acc-2")
    w.put("e1", "працюю над договором", iso(2026, 11, 11, 11, 0))
    every = {text for texts in own.values() for text in texts} | {token(n) for n in (20, 21, 22, 23, 24, 30)}

    for case_id, name in names.items():
        w.ai.prompts.pop("answer_case", None)
        w.ai.pick(name)
        w.recall(f"що ми знаємо про {name}?")
        prompt = w.ai.case_prompt()
        for text in own[case_id]:
            assert text in prompt, (case_id, text)
        for text in every - set(own[case_id]):
            assert text not in prompt, (case_id, text)
