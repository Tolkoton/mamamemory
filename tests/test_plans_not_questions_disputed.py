"""Disputed contract tests of the slice plans-not-questions: each one takes the reading of a question to the
contract `.engine/slices/plans-not-questions.md` and is sealed only after the slice planner answers it.

Written by the slice tester from the sealed contract, no code. `NOW` is Monday 9 November 2026, 10:07 Berlin.
"""

import re

from tests.plans_not_questions_world import IS_ANSWER_SENTENCE, plans
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.stuck_question_world import asked
from tests.time_limits_world import parsed


def plain(text: str) -> str:
    """Apostrophes made one character, dashes made one, whitespace single spaces."""
    return " ".join(re.sub("[–-]", "—", re.sub("[’ʼ`]", "'", text)).split())


def test_q1_both_parse_prompts_carry_the_is_answer_sentence_word_for_word() -> None:
    sentence = plain(IS_ANSWER_SENTENCE)
    w = plans(use_tasks=False)
    priorities = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "priorities")
    w.ai.priorities = {"is_answer": False, "same": True, "order": [], "timed": []}
    w.try_priorities(priorities.id, "які в нас плани?")
    prompts = w.ai.parse_prompts.get("priorities", [])
    assert prompts, w.ai.parse_prompts
    assert sentence in plain(prompts[0]), prompts[0]
    w = plans(ask_limits=True, ask_priorities=False, use_tasks=False)
    limits = asked(w.plan_week(task(NOTARY), task(MEDICINE)), "limits")
    w.ai.limits = dict(parsed(), is_answer=False)
    w.try_limits(limits.id, "які в нас плани?")
    prompts = w.ai.parse_prompts.get("limits", [])
    assert prompts, w.ai.parse_prompts
    assert sentence in plain(prompts[0]), prompts[0]
