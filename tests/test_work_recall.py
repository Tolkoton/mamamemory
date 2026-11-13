"""Contract tests of the slice work-recall: `cases.worklog.recent` (Seam 1), `cases.worklog.answer` (Seam 2),
AC4, the invariants I1 and I2.

Written by the slice tester from the sealed contract `.engine/slices/work-recall.md`, without the code.
`NOW` is Thursday 12 November 2026, 09:07Z (10:07 in Berlin). Europe/Berlin is UTC+1 in November,
Asia/Tokyo is UTC+9. The form of the weekday and the date in the prompt is question Q1 and is tested in
`test_work_recall_disputed.py` only: here the prompt is checked by the local time "HH:MM".
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from mamamemory.cases import worklog
from tests.case_questions_world import case_q
from tests.note_to_case_world import ModelFailed
from tests.work_recall_world import (
    ANSWER_WORK,
    NOTHING,
    CalendarDown,
    Recall,
    ZoneCalendar,
    iso,
    token,
)

CONTRACT = "працюю над договором купівлі"
QUESTION = "що я робила з договором?"
MODEL_TEXT = "Учора о 12:00 ви працювали над договором."
SCHMIDT = "пані Шмідт"
TOKEN = re.compile(r"задача-K(\d{3})Z")


def seen(prompt: str) -> set[int]:
    """The numbers of the `token` entries the prompt carries."""
    return {int(number) for number in TOKEN.findall(prompt)}


def notices(out: str) -> list[dict[str, object]]:
    """The stdout lines that name `WorkLogOver100`, parsed as JSON."""
    return [json.loads(line) for line in out.splitlines() if "WorkLogOver100" in line]


# ------------------------------------------------------------------ Seam 1: recent


def test_seam1_recent_keeps_the_100_newest_of_105_newest_first() -> None:
    w = Recall()
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    # entry k is k hours older than the newest; its id is a permutation:
    # the store's order is not the time order
    for k in range(105):
        w.put(f"e{(k * 37) % 105:03d}", f"текст {k}", (base - timedelta(hours=k)).isoformat())
    found = w.recent()
    assert len(found) == 100
    assert [entry.id for entry in found] == [f"e{(k * 37) % 105:03d}" for k in range(100)]
    assert found[0].id == "e000"
    assert found[0].at == datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    assert found[1].id == "e037"
    assert found[1].at == datetime(2026, 11, 12, 7, 0, tzinfo=UTC)
    assert found[99].id == "e093"
    assert found[99].at == datetime(2026, 11, 8, 5, 0, tzinfo=UTC)
    assert found[99].text == "текст 99"
    kept = {entry.id for entry in found}
    for k in range(100, 105):
        assert f"e{(k * 37) % 105:03d}" not in kept, k


def test_recent_returns_work_entries_with_id_text_and_time() -> None:
    w = Recall()
    w.put("m7", CONTRACT, iso(2026, 11, 11, 11, 0))
    assert w.recent() == [worklog.WorkEntry("m7", CONTRACT, datetime(2026, 11, 11, 11, 0, tzinfo=UTC))]


def test_seam1_entry_a_year_old_is_kept_when_it_is_among_the_100() -> None:
    w = Recall()
    w.put("b", "звіт для податкової", iso(2026, 11, 5, 8, 0))
    w.put("a", "старий договір", iso(2025, 11, 12, 9, 0))
    w.put("c", CONTRACT, iso(2026, 11, 11, 11, 0))
    found = w.recent()
    assert [entry.id for entry in found] == ["c", "b", "a"]
    assert found[2].text == "старий договір"
    assert found[2].at == datetime(2025, 11, 12, 9, 0, tzinfo=UTC)


def test_seam1_entry_without_a_valid_at_is_skipped() -> None:
    w = Recall()
    w.put("a", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.put("b", "без часу", None)
    w.put("c", "час словами", "вчора")
    w.put("d", "звіт", iso(2026, 11, 10, 8, 0))
    assert [entry.id for entry in w.recent()] == ["a", "d"]


def test_recent_reads_the_account_s_journal_only() -> None:
    w = Recall()
    w.put("a", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.put("x", "чужий запис", iso(2026, 11, 12, 8, 0), account_id="acc-2")
    assert [entry.id for entry in w.recent()] == ["a"]


def test_seam1_101_entries_print_one_notice_line_with_the_count_and_no_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    w = Recall()
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    for k in range(101):
        w.put(f"e{k:03d}", token(k), (base - timedelta(hours=k)).isoformat())
    assert len(w.recent()) == 100
    out = capsys.readouterr().out
    found = notices(out)
    assert len(found) == 1, out
    assert found[0]["event"] == "notice"
    assert found[0]["kind"] == "WorkLogOver100"
    assert found[0]["count"] == 101
    assert "задача-K" not in out
    # every call while the journal is over 100 prints the line again (critic note)
    w.recent()
    assert len(notices(capsys.readouterr().out)) == 1


def test_seam1_100_entries_print_no_notice(capsys: pytest.CaptureFixture[str]) -> None:
    w = Recall()
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    for k in range(100):
        w.put(f"e{k:03d}", token(k), (base - timedelta(hours=k)).isoformat())
    assert len(w.recent()) == 100
    assert notices(capsys.readouterr().out) == []


# ------------------------------------------------------------------ Seam 2: answer


def test_seam2_prompt_carries_the_question_now_and_each_entry_time_in_the_calendar_zone() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 9, 23, 30))
    w.put("e2", "аналізи пані Шмідт", iso(2026, 11, 11, 13, 15))
    w.answer(QUESTION)
    prompt = w.ai.work_prompt()
    assert QUESTION in prompt
    assert CONTRACT in prompt
    assert "аналізи пані Шмідт" in prompt
    assert "10:07" in prompt  # now: 09:07Z is 10:07 in Berlin
    assert "00:30" in prompt  # 23:30Z on Monday 9 is 00:30 on Tuesday 10 in Berlin
    assert "14:15" in prompt  # 13:15Z is 14:15 in Berlin
    assert "23:30" not in prompt
    assert "13:15" not in prompt
    assert "2026-11-09" not in prompt and "09.11.2026" not in prompt and "9 листопада" not in prompt
    assert w.calendar.log.count("timezone") >= 1


def test_seam2_zone_is_the_calendar_s_not_a_fixed_one() -> None:
    w = Recall(calendar=ZoneCalendar("Asia/Tokyo"))
    w.put("e1", CONTRACT, iso(2026, 11, 9, 23, 30))
    w.answer(QUESTION)
    prompt = w.ai.work_prompt()
    assert "18:07" in prompt  # now: 09:07Z is 18:07 in Tokyo
    assert "08:30" in prompt  # 23:30Z is 08:30 on Tuesday 10 in Tokyo
    assert "00:30" not in prompt
    assert "23:30" not in prompt


def test_seam2_empty_journal_is_nothing_without_the_model_and_the_calendar() -> None:
    w = Recall()
    w.put("x", "чужий запис", iso(2026, 11, 12, 8, 0), account_id="acc-2")
    reply = w.answer(QUESTION)
    assert reply.text == NOTHING
    assert reply.question is None and reply.plan is None and reply.choices is None
    assert w.ai.calls == []
    assert w.ai.prompts == {}
    assert w.calendar.log == []


def test_seam2_found_false_is_nothing() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"found": False, "answer": "Про машину нічого."}
    reply = w.answer("що я робила з машиною?")
    assert reply.text == NOTHING
    assert reply.question is None
    assert w.ai.calls == [ANSWER_WORK]


def test_answer_with_found_missing_is_nothing() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"answer": MODEL_TEXT}
    assert w.answer(QUESTION).text == NOTHING


def test_answer_with_found_true_and_empty_answer_is_nothing() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"found": True, "answer": ""}
    assert w.answer(QUESTION).text == NOTHING


def test_seam2_found_true_is_the_model_s_text_without_a_question() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.ai.work_answer = {"found": True, "answer": MODEL_TEXT}
    reply = w.answer(QUESTION)
    assert reply.text == MODEL_TEXT
    assert reply.question is None and reply.plan is None and reply.choices is None


def test_seam2_calendar_error_is_raised_and_nothing_is_written() -> None:
    w = Recall(calendar=ZoneCalendar(down=True))
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    before = w.written_state()
    with pytest.raises(CalendarDown):
        w.answer(QUESTION)
    assert w.written_state() == before
    assert w.calendar.writes() == []


def test_answer_model_error_is_raised_and_nothing_is_written() -> None:
    w = Recall()
    w.put("e1", CONTRACT, iso(2026, 11, 11, 11, 0))
    w.ai.fail[ANSWER_WORK] = 1
    before = w.written_state()
    with pytest.raises(ModelFailed):
        w.answer(QUESTION)
    assert w.written_state() == before
    assert w.calendar.writes() == []


# ------------------------------------------------------------------ AC4


def test_AC4_after_two_working_on_the_prompt_about_x_carries_the_x_entry() -> None:
    w = Recall()
    w.working("працюю над договором купівлі", "m1", now=datetime(2026, 11, 11, 11, 0, tzinfo=UTC))
    w.working("працюю над звітом для податкової", "m2", now=datetime(2026, 11, 11, 14, 0, tzinfo=UTC))
    w.ai.work_answer = {"found": True, "answer": MODEL_TEXT}
    reply = w.ask(QUESTION, "m3")
    assert reply.text == MODEL_TEXT
    prompt = w.ai.work_prompt()
    assert "працюю над договором купівлі" in prompt
    assert "12:00" in prompt  # 11:00Z is 12:00 in Berlin
    assert QUESTION in prompt
    assert sorted(entry_id for entry_id, _ in w.entries()) == ["m1", "m2"]


# ------------------------------------------------------------------ invariants


def test_I1_work_question_writes_nothing() -> None:
    w = Recall()
    # A case question and a shown plan made the lawful way, before the intent is measured.
    w.pending_note("a1", SCHMIDT)
    reply_tos = [None, w.plan_question(), case_q("a1")]
    inserts_before = list(w.calendar.insert_calls)
    w.calendar.log.clear()
    w.ai.work_answer = {"found": True, "answer": MODEL_TEXT}
    questions = [QUESTION, "над чим я працювала вчора?", "працюю над договором", "що я робила?"]
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)

    def ask_all(size: str, expected: str) -> None:
        before = w.written_state()
        for r, reply_to in enumerate(reply_tos):
            for q, question in enumerate(questions):
                for _ in range(2):  # the app repeats the same message
                    reply = w.ask(question, f"{size}-{r}-{q}", reply_to)
                    assert reply.text == expected, (size, reply_to, question, reply)
                    assert reply.question is None, (size, reply_to, question, reply)
        assert w.written_state() == before, size
        assert w.calendar.writes() == [], size
        assert w.calendar.insert_calls == inserts_before, size

    ask_all("empty", NOTHING)
    w.put("e000", token(0), base.isoformat())
    ask_all("one", MODEL_TEXT)
    for k in range(1, 101):
        w.put(f"e{k:03d}", token(k), (base - timedelta(days=k)).isoformat())
    ask_all("over100", MODEL_TEXT)


def test_I2_the_model_gets_the_100_newest_entries_and_never_more() -> None:
    base = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)

    def journal(count: int, year_old_at: int | None = None) -> set[int]:
        """`count` entries, entry k k days older than the newest, ids a permutation; what the model saw."""
        w = Recall()
        for k in range(count):
            at = base - timedelta(days=k)
            if k == year_old_at:
                at = datetime(2025, 11, 1, 9, 0, tzinfo=UTC)
            w.put(f"e{(k * 53) % count:03d}", token(k), at.isoformat())
        w.answer(QUESTION)
        return seen(w.ai.work_prompt())

    # one entry, a year old
    assert journal(1, year_old_at=0) == {0}
    # exactly 100, the oldest a year old
    assert journal(100, year_old_at=99) == set(range(100))
    # 101: the oldest one is left out
    assert journal(101) == set(range(100))
    # 150 in an order unlike the time order: the 100 newest, none of the 50 oldest
    assert journal(150) == set(range(100))
