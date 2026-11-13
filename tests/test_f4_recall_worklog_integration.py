"""Integration tests of the feature f4-recall-worklog (block f4-recall-worklog, closed with S4 f4-measure).

Written by the slice tester (mode block) from the feature artifact
`.engine/architecture/feature/f4-recall-worklog.md` and the public signatures, without the code.
One test for every line of «Inter-slice contracts» and one for every acceptance criterion AC1-AC4.
Each test drives the built slices S1-S3 together over one store, one model fake and one calendar fake:
the journal is written by S1 (the intent `working_on` through `assistant.handle_message`, or
`cases.worklog.add`), read by S2 (`work_question`, `cases.worklog.recent`) and by S3 (`recall`).
Cases and materials are F3 documents put into the store by the case-recall world. The weekday and
date form in the prompts is a sealed question of work-recall (Q1): here a time is checked by its
local "HH:MM" in Europe/Berlin (UTC+1 in November). Every expected value is written by hand.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from mamamemory.cases import worklog
from tests.case_recall_world import MODEL_TEXT, NOT_FOUND, CaseRecall
from tests.work_recall_world import NOTHING, token
from tests.working_on_world import recorded

ROOT = Path(__file__).resolve().parent.parent
CASE = "купівля городу"
DESCRIPTION = "Купівля городу біля Бучі у пана Фішера."
MATERIAL = "Нотаріус просить витяг з реєстру на город."
CONTRACT = "працюю над договором купівлі городу"
KOCH = "працюю над паном Кохом"
WORK_ANSWER = "Учора о 12:00 ви працювали над договором купівлі городу."
TUESDAY_11Z = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)  # 12:00 in Berlin
TUESDAY_14Z = datetime(2026, 11, 10, 14, 30, tzinfo=UTC)  # 15:30 in Berlin


def with_case() -> CaseRecall:
    """A world with the case «купівля городу» (its description) and one material in it."""
    w = CaseRecall()
    w.put_case("c-garden", CASE, DESCRIPTION)
    w.put_material("mat-1", MATERIAL, "c-garden")
    return w


# ------------------------------------------------------------------ Inter-slice contracts


def test_S1_to_S2_a_working_on_document_is_text_and_utc_iso_at_and_reads_back_as_a_work_entry() -> None:
    w = CaseRecall()
    w.working(CONTRACT, "m1", now=TUESDAY_11Z)
    assert w.entries() == [("m1", {"text": CONTRACT, "at": "2026-11-10T11:00:00+00:00"})]
    found = worklog.recent(w.session, store=w.store, now=TUESDAY_11Z + timedelta(days=2))
    assert found == [worklog.WorkEntry(id="m1", text=CONTRACT, at=TUESDAY_11Z)]


def test_S2_to_S3_recall_sees_every_entry_newest_first_up_to_100_without_time_limit_or_case_filter() -> None:
    w = with_case()
    old = datetime(2025, 9, 1, 8, 0, tzinfo=UTC)  # more than a year before NOW
    w.working(token(0), "m-old", now=old)
    for k in range(1, 98):
        worklog.add(w.session, token(k), f"m-{k:03d}", store=w.store, now=old + timedelta(days=k))
    w.working(KOCH, "m-koch", now=TUESDAY_11Z)
    w.working(CONTRACT, "m-garden", now=TUESDAY_14Z)
    # 100 entries: the oldest is more than a year old, one is about another case
    entries = worklog.recent(w.session, store=w.store, now=TUESDAY_14Z)
    assert len(entries) == 100
    assert [e.id for e in entries[:3]] == ["m-garden", "m-koch", "m-097"]
    assert entries[-1].id == "m-old"
    w.ai.pick(CASE)
    assert w.ask_case("що вже з'ясували по городу?", "q1").text == MODEL_TEXT
    prompt = w.ai.case_prompt()
    assert CONTRACT in prompt
    assert KOCH in prompt  # no case filter in S2: the model, told to, picks
    assert token(0) in prompt  # no time limit
    # a 101st entry, newer than all: the oldest falls out
    w.working("працюю над листом до пані Шмідт", "m-new", now=TUESDAY_14Z + timedelta(hours=1))
    assert [e.id for e in worklog.recent(w.session, store=w.store, now=TUESDAY_14Z)][:1] == ["m-new"]
    assert len(worklog.recent(w.session, store=w.store, now=TUESDAY_14Z)) == 100
    w.ask_case("що вже з'ясували по городу?", "q2")
    second = w.ai.case_prompts()[-1]
    assert token(0) not in second
    assert token(1) in second
    assert "працюю над листом до пані Шмідт" in second


def test_S1_S3_to_S4_every_slice_has_its_smoke_script_and_the_report_names_it() -> None:
    report = (ROOT / "docs" / "f4-measure.md").read_text(encoding="utf-8")
    for name in ("smoke_working_on.py", "smoke_work_recall.py", "smoke_case_recall.py"):
        script = ROOT / "scripts" / name
        assert script.is_file(), name
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
        assert f"scripts/{name}" in report, name


# ------------------------------------------------------------------ acceptance criteria


def test_AC1_working_on_records_text_and_time_says_recorded_and_touches_no_calendar_tasks_or_cases() -> None:
    w = with_case()
    before = w.cases_state()
    other = w.other_work("acc-2")
    text = "зараз працюю над договором купівлі городу"
    reply = w.working(text, "m1", now=TUESDAY_11Z)
    assert reply.text == recorded(text)
    assert reply.question is None
    assert w.entry("m1") == {"text": text, "at": "2026-11-10T11:00:00+00:00"}
    assert other.entries() == []
    assert w.calendar.writes() == []
    assert w.cases_state() == before


def test_AC2_work_questions_answer_from_the_journal_with_time_and_nothing_yet_without_entries() -> None:
    w = CaseRecall()
    w.working(CONTRACT, "m1", now=TUESDAY_11Z)
    w.ai.work_answer = {"found": True, "answer": WORK_ANSWER}
    for n, question in enumerate(("над чим я працювала?", "що я робила з договором?", "що я робила вчора?")):
        reply = w.ask(question, f"q{n}")
        assert reply.text == WORK_ANSWER, question
        prompt = w.ai.work_prompts()[-1]
        assert question in prompt
        assert CONTRACT in prompt
        assert "12:00" in prompt  # 11:00Z is 12:00 in Berlin
    empty = CaseRecall()
    assert empty.ask("що я робила вчора?", "q9").text == NOTHING
    assert empty.ai.work_prompts() == []


def test_AC3_case_question_answers_from_description_materials_and_the_entry_and_not_found_otherwise() -> None:
    w = with_case()
    w.working(CONTRACT, "m1", now=TUESDAY_11Z)
    w.ai.pick(CASE)
    question = "що вже з'ясували по городу?"
    reply = w.ask_case(question, "q1")
    assert reply.text == MODEL_TEXT
    assert reply.question is None
    prompt = w.ai.case_prompt()
    for text in (CASE, DESCRIPTION, MATERIAL, CONTRACT, question):
        assert text in prompt, text
    assert "12:00" in prompt  # the entry's time in Berlin
    w.ai.pick_value(None)
    assert w.ask_case("що ми знаємо про пані Шмідт?", "q2").text == NOT_FOUND


def test_AC4_two_working_on_neither_erases_the_other_and_the_question_about_x_sees_x() -> None:
    w = CaseRecall()
    w.working(CONTRACT, "m1", now=TUESDAY_11Z)
    w.working("працюю над листом до пані Шмідт", "m2", now=TUESDAY_14Z)
    assert sorted(w.entries()) == [
        ("m1", {"text": CONTRACT, "at": "2026-11-10T11:00:00+00:00"}),
        ("m2", {"text": "працюю над листом до пані Шмідт", "at": "2026-11-10T14:30:00+00:00"}),
    ]
    w.ai.work_answer = {"found": True, "answer": WORK_ANSWER}
    assert w.ask("що я робила з договором?", "q1").text == WORK_ANSWER
    prompt = w.ai.work_prompt()
    assert CONTRACT in prompt
    assert "12:00" in prompt
