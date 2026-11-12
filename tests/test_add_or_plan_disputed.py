"""Disputed contract tests of the slice add-or-plan: each takes one reading of a line of
`.engine/slices/add-or-plan.md` that can be read two ways, and names its question (Q1..Q5 of the hand-in).

Written by the slice tester from the sealed contract, without the code.
Sealed after the slice planner's answer.
"""

from mamamemory import planning
from tests.add_or_plan_world import NO_TASKS_THIS_WEEK, TK_BILLS, add_or_plan
from tests.google_tasks_world import BILLS
from tests.several_tasks_world import MEDICINE, NOTARY, SISTER, task
from tests.test_one_task_planning import shown


def test_Q1_next_question_itself_never_asks_the_priorities_in_add_mode() -> None:
    """Q1: «`next_question` (через `_asked`): у режимі `add` питання про важливість не ставиться ніколи» —
    `next_question` itself, called with `ask_priorities=True`, honours the draft's `mode`."""
    w = add_or_plan(TK_BILLS)
    shown(w.add(task(NOTARY), task(MEDICINE)))
    draft = w.draft()
    assert draft is not None and draft.get("mode") == "add", draft
    asked = planning.next_question(draft, ask_priorities=True)
    assert asked is None or asked.kind != "priorities", asked
    week = dict(draft, mode="week", priorities_answered=False)
    week_asked = planning.next_question(week, ask_priorities=True)
    assert week_asked is not None and week_asked.kind == "priorities", week_asked


def test_Q2_route_prompt_carries_the_contract_hints_in_their_words() -> None:
    """Q2: the plan_week hint and the rewritten new_task rule are given to the route model in the contract's
    words: «мама просить спланувати тиждень чи дні» and «— new_task, якщо мама не просить спланувати
    тиждень»."""
    w = add_or_plan()
    w.ai.says(task(NOTARY))
    w.ai.intent = "new_task"
    w.message("додай задачу подзвонити нотаріусу", None)
    assert w.ai.route_prompts, "the route model was not asked"
    prompt = " ".join(w.ai.route_prompts[-1].split())
    assert "plan_week — мама просить спланувати тиждень чи дні" in prompt, prompt
    assert "навіть з задачами в тій самій фразі" in prompt, prompt
    assert "new_task, якщо мама не просить спланувати тиждень" in prompt, prompt


def test_Q3_other_forms_of_the_request_returned_as_a_task_are_dropped_too() -> None:
    """Q3: «із назвою на кшталт «спланувати тиждень»» covers the forms of the request the contract itself
    names — «сплануй тиждень» — and a capital letter."""
    for title in ("сплануй тиждень", "Спланувати тиждень"):
        w = add_or_plan(TK_BILLS)
        w.plan_week(task(title))
        assert w.titles() == [BILLS], (title, w.titles())


def test_Q4_the_request_is_dropped_also_beside_a_spoken_task() -> None:
    """Q4: the request returned as a task is dropped in `week=True` also when a real task stands beside it
    («давай планувати тиждень: ще подзвонити сестрі»)."""
    w = add_or_plan(TK_BILLS)
    w.plan_week(
        task("спланувати тиждень"), task(SISTER), text="давай планувати тиждень: ще подзвонити сестрі"
    )
    assert sorted(w.titles()) == sorted([SISTER, BILLS]), w.titles()


def test_Q5_plan_the_week_with_tasks_off_says_there_are_no_tasks() -> None:
    """Q5: with `use_tasks` off and nothing spoken, «сплануй тиждень» gets «Задач на тиждень немає…», not
    «Не зрозуміла задачу…», and no draft."""
    w = add_or_plan(TK_BILLS, use_tasks=False)
    reply = w.plan_week()
    assert reply.text == NO_TASKS_THIS_WEEK, reply
    assert w.draft() is None
    assert w.tc.list_calls == 0
