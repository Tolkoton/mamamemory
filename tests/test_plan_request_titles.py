"""The request itself, returned by the parse as a task, is recognised (add-or-plan; smoke 2026-11-11: the
model returned «Що в мене на цей тиждень» as a task); tasks with planning words are kept (overseer gap)."""

from mamamemory import planning
from tests.add_or_plan_world import add_or_plan
from tests.several_tasks_world import task

REQUESTS = (
    "спланувати тиждень",
    "Сплануй тиждень",
    "Що в мене на цей тиждень",
    "які в мене плани на тиждень",
    "давай планувати наступний тиждень",
)
TASKS = (
    "подзвонити нотаріусу",
    "купити ліки",
    "розібрати документи за тиждень",
    "що купити на ринку",
    "запланувати відпустку на тиждень",
    "Що на обід купити на тиждень",
    "запланувати прибирання на два дні",
)


def test_forms_of_the_request_are_recognised() -> None:
    for title in REQUESTS:
        assert planning._is_plan_request(title), title


def test_real_tasks_are_not_taken_for_the_request() -> None:
    for title in TASKS:
        assert not planning._is_plan_request(title), title


def test_plan_week_drops_only_the_request_and_keeps_a_task_with_a_planning_word() -> None:
    w = add_or_plan(use_tasks=False)
    w.plan_week(
        task("Сплануй тиждень"),
        task("запланувати відпустку на тиждень"),
        text="сплануй тиждень і ще запланувати відпустку на тиждень",
    )
    assert w.titles() == ["запланувати відпустку на тиждень"], w.titles()
