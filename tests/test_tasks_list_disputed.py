"""Disputed contract tests of the slice tasks-list: each depends on a question to the contract (Q1, Q2) and is
sealed only after the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/tasks-list.md`, without the code.
"""

from mamamemory import assistant
from mamamemory.errors import LoginExpired
from mamamemory.integrations.google_work import TaskItem
from tests.tasks_list_world import ListCalendar, lines, listed, plain

FAILED = "Не вдалося прочитати задачі, спробуйте ще раз."
GUIDE_LINE = "• «Які в мене задачі?» — покажу список задач."


def test_q1_login_expired_of_list_open_tasks_also_gives_the_failure_text() -> None:
    calendar = ListCalendar(TaskItem("t1", "оплатити світло"), error=LoginExpired("refresh refused"))
    assert lines(listed(calendar)) == [FAILED]
    assert calendar.writes() == []


def test_q2_guide_tasks_line_stands_right_before_the_speaker_line() -> None:
    guide = [plain(line) for line in assistant.GUIDE_UK.splitlines()]
    assert plain(GUIDE_LINE) in guide, guide
    at = guide.index(plain(GUIDE_LINE))
    assert "🔊" in guide[at + 1], guide
