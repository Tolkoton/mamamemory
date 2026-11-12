"""Disputed contract tests of the slice voice-edits: each takes one reading of a line of
`.engine/slices/voice-edits.md` that can be read two ways, and names its question (Q1..Q3 of the hand-in).

Written by the slice tester from the sealed contract, without the code.
Sealed after the slice planner's answer.
"""

from datetime import UTC, datetime

from mamamemory.replies import Question
from tests.several_tasks_world import MEDICINE, NOTARY, items, task
from tests.test_one_task_planning import instant, make_config, shown
from tests.voice_edits_world import editing


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_Q1_route_prompt_names_the_edit_hint() -> None:
    """Q1: the hint «мама просить змінити показаний план» is given to the route model in these words."""
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, fingerprint = shown(w.start())
    w.ai.intent = "other"
    w.message("перенеси нотаріуса на четвер", Question("plan", plan_id, fingerprint))
    assert w.ai.route_prompts, "the route model was not asked"
    prompt = w.ai.route_prompts[-1]
    assert "edit" in prompt, prompt
    assert "змінити показаний план" in prompt, prompt


def test_Q2_the_edit_parse_is_the_task_type_parse_edit_on_flash_lite() -> None:
    """Q2: «Розбір Flash-Lite `parse_edit`» — the task type is exactly `parse_edit`, and the config maps it to
    the Flash-Lite model the other parses use."""
    choice = make_config().models.get("parse_edit")
    assert choice is not None, "no model for `parse_edit` in the config"
    assert "flash-lite" in choice.model
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    w.edit(plan_id, "move", NOTARY, day="2026-11-12")
    assert "parse_edit" in w.ai.calls, w.ai.calls


def test_Q3_move_with_a_named_time_takes_its_date_over_a_different_day() -> None:
    """Q3: `move` with `start_local` and a `day` of another date: the date of `start_local` wins."""
    w = editing(task(NOTARY), task(MEDICINE))
    plan_id, _ = shown(w.start())
    reply = w.edit(plan_id, "move", NOTARY, day="2026-11-13", start_local="2026-11-12T10:00:00")
    start, end = items(reply)[NOTARY]
    assert (instant(start), instant(end)) == (utc(12, 9, 0), utc(12, 9, 30))
    assert w.find(NOTARY)["constraints"]["day"] == "2026-11-12"
