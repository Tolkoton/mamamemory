"""Машина станів чернетки плану (S3, `planning.plan`).

Стани: «питаю тривалість» → «показано» → «записується» → «записано».
Чиста функція переходів для `store.transact`. Не робить: викликів Calendar чи моделі.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

ASKING = "asking_duration"
SHOWN = "shown"
WRITING = "writing"
WRITTEN = "written"

Action = Literal["show", "begin_write", "written", "interrupted", "release_stale"]


@dataclass(frozen=True)
class Decision:
    write: dict[str, Any] | None
    """Новий вміст чернетки або None — нічого не писати."""
    outcome: str


def decide(
    draft: dict[str, Any] | None, action: Action, *, now: datetime, request_timeout_s: int, **details: Any
) -> Decision:
    """`details`: `plan_id` завжди; `fingerprint` для begin_write; `started` для written/interrupted;
    `shown` (поля показаного плану) для show."""
    if draft is None or draft.get("plan_id") != details.get("plan_id"):
        return Decision(None, "not_actual")
    state = draft.get("state")
    if action == "show":
        return _show(draft, state, now, request_timeout_s, details["shown"])
    if action == "begin_write":
        if state == SHOWN and draft.get("fingerprint") == details.get("fingerprint"):
            return Decision(draft | {"state": WRITING, "writing_started": now.isoformat()}, "begin")
        return Decision(None, str(state))
    if action == "release_stale":
        if state == WRITING and _stale(draft, now, request_timeout_s):
            return Decision(_back_to_shown(draft), "released")
        return Decision(None, str(state))
    same_write = state == WRITING and draft.get("writing_started") == details.get("started")
    if action == "written":
        return Decision(
            draft | {"state": WRITTEN} if same_write else None, "written" if same_write else "lost"
        )
    if action == "interrupted":
        return Decision(
            _back_to_shown(draft) if same_write else None, "interrupted" if same_write else "lost"
        )
    raise ValueError(f"unknown action {action!r}")


def is_fresh_write(draft: dict[str, Any], now: datetime, request_timeout_s: int) -> bool:
    return draft.get("state") == WRITING and not _stale(draft, now, request_timeout_s)


def _show(
    draft: dict[str, Any], state: Any, now: datetime, request_timeout_s: int, shown: dict[str, Any]
) -> Decision:
    if state == WRITTEN or is_fresh_write(draft, now, request_timeout_s):
        return Decision(None, str(state))
    return Decision(_back_to_shown(draft) | shown | {"state": SHOWN}, "shown")


def _stale(draft: dict[str, Any], now: datetime, request_timeout_s: int) -> bool:
    started = datetime.fromisoformat(str(draft["writing_started"]))
    return now - started > timedelta(seconds=request_timeout_s)


def _back_to_shown(draft: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in draft.items() if k != "writing_started"} | {"state": SHOWN}
