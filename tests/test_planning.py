"""Builder's pins for `planning` (several-tasks): what the replaced F1 helpers `_show_new` (the first show)
and `_parse_task` (one task from the model) did, through the public functions. They pass on the F1 code and
on the several-tasks code alike."""

from datetime import UTC, datetime

from tests.test_one_task_planning import NOW, instant, world


def test_first_show_sets_a_seven_day_horizon_and_t0_now() -> None:
    w = world(duration_min=30)
    reply = w.start()
    assert reply.plan is not None
    draft = w.store.get(w.session.account_id, "plans/current")
    assert draft is not None
    assert datetime.fromisoformat(draft["horizon_end"]) == datetime(2026, 11, 16, 9, 7, tzinfo=UTC)
    assert datetime.fromisoformat(draft["t0"]) == NOW
    assert draft["state"] == "shown"


def test_one_task_from_the_model_keeps_its_title_time_and_duration() -> None:
    w = world(duration_min=45, start_local="2026-11-12T10:00:00")
    reply = w.start("у четвер о десятій подзвонити нотаріусу")
    assert reply.plan is not None
    assert reply.plan.title == "подзвонити нотаріусу"
    assert instant(reply.plan.start) == datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
    assert instant(reply.plan.end) == datetime(2026, 11, 12, 9, 45, tzinfo=UTC)


def test_model_title_missing_falls_back_to_nothing_understood_or_the_text() -> None:
    w = world(duration_min=30)
    w.ai.task["title"] = "  подзвонити нотаріусу  "
    reply = w.start()
    assert reply.plan is not None
    assert reply.plan.title == "подзвонити нотаріусу", "the model's title is stripped"


def test_task_prompt_counts_days_in_the_calendar_zone_near_local_midnight() -> None:
    from zoneinfo import ZoneInfo

    from mamamemory.planning import _task_prompt

    # 22:30 UTC on Monday 9 November is 00:30 on Tuesday 10 November in Kyiv.
    prompt = _task_prompt(
        "завтра подзвонити", datetime(2026, 11, 9, 22, 30, tzinfo=UTC), ZoneInfo("Europe/Kyiv")
    )
    assert "Зараз 2026-11-10T00:30" in prompt
    assert "Дні: вівторок — 2026-11-10; середа — 2026-11-11" in prompt
