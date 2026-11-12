"""The route sees the shown plan's titles (voice-edits, overseer test gap 719): `handle_message` with a plan
`reply_to` passes the unwritten titles of that very draft into the route prompt, and none for another plan."""

from mamamemory.replies import Question
from tests.several_tasks_world import MEDICINE, NOTARY, task
from tests.test_one_task_planning import shown
from tests.voice_edits_world import editing


def test_route_prompt_lists_the_titles_of_the_shown_plan() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    w.ai.intent = "other"
    w.message("лікар о десятій у середу", Question("plan", plan_id, fingerprint))
    prompt = w.ai.route_prompts[-1]
    assert NOTARY in prompt and MEDICINE in prompt, prompt


def test_route_prompt_lists_no_titles_for_another_plan() -> None:
    w = editing(task(NOTARY), task(MEDICINE))
    _, fingerprint = shown(w.start())
    w.ai.intent = "other"
    w.message("лікар о десятій у середу", Question("plan", "not-the-plan", fingerprint))
    prompt = w.ai.route_prompts[-1]
    assert NOTARY not in prompt and MEDICINE not in prompt, prompt
