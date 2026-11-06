"""Планування однієї задачі (S3): розбір, питання про тривалість, показ плану, «так» → подія в Calendar.

Без FastAPI. Залежності — параметрами. Чернетка одна на акаунт (`DRAFT_PATH`), її переходи — `plan.decide`
у `store.transact`. Не робить: правок плану, кількох задач, Tasks, меж часу (F2).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork, event_id
from mamamemory.integrations.store import Store
from mamamemory.planning import plan
from mamamemory.planning.placement import Interval, NotFit, Placed, TaskSpec, place
from mamamemory.replies import PlanView, Question, Reply

DRAFT_PATH = "plans/current"
TASK_ID = "t1"
HORIZON = timedelta(days=7)

ASK_DURATION = "Скільки часу це займе?"
WRITTEN_TEXT = "Записала в календар."
NOT_ACTUAL = "Це питання вже не актуальне."
NO_FREE_TIME = "Не знайшла вільного часу цього тижня."
NAMED_OUTSIDE = "Цей час уже минув або він далі ніж за тиждень."
ALREADY_WRITTEN = "Цей план уже записано."
WRITING_NOW = "Записую, хвилинку."

TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "start_local": {"type": ["string", "null"], "description": "YYYY-MM-DDTHH:MM:SS, або YYYY-MM-DD"},
        "duration_min": {"type": ["integer", "null"]},
    },
    "required": ["title", "start_local", "duration_min"],
}
DURATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"duration_min": {"type": ["integer", "null"]}},
    "required": ["duration_min"],
}

WEEKDAYS = ("понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя")
MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)  # fmt: skip


@dataclass(frozen=True)
class Deps:
    calendar: GoogleWork
    store: Store
    now: datetime
    config: Config
    account_id: str


def start(
    session: Session, text: str, *, ai: AI, calendar: GoogleWork, store: Store, now: datetime, config: Config
) -> Reply:
    """Flow: розбір задачі → нова чернетка → питання про тривалість або показ плану."""
    deps = Deps(calendar, store, now, config, session.account_id)
    task = _parse_task(ai, text, now)
    draft: dict[str, Any] = {"plan_id": uuid.uuid4().hex, "task": task}
    if task["duration_min"] is None:
        store.set(session.account_id, DRAFT_PATH, draft | {"state": plan.ASKING})
        return Reply(ASK_DURATION, Question("duration", draft["plan_id"], None))
    return _show_new(deps, draft)


def answer_duration(
    session: Session,
    plan_id: str,
    text: str,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
) -> Reply:
    """Flow: та сама чернетка, що питає тривалість → тривалість з тексту → показ плану."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("plan_id") != plan_id or draft.get("state") != plan.ASKING:
        return Reply(NOT_ACTUAL)
    duration = ai.generate_json("parse_duration", _duration_prompt(text), DURATION_SCHEMA).get("duration_min")
    if not isinstance(duration, int) or duration <= 0:
        return Reply(ASK_DURATION, Question("duration", plan_id, None))
    return _show_new(deps, draft | {"task": draft["task"] | {"duration_min": duration}})


def confirm(
    session: Session,
    plan_id: str,
    fingerprint: str,
    *,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
) -> Reply:
    """Flow гілок M3: (4) записано / свіжий запис → повідомлення; (5) застарілий запис → «показано»;
    (0) своя подія вже є → «записано»; (1) перерахунок; (2) той самий відбиток → запис;
    (3) інший відбиток → новий план."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("plan_id") != plan_id:
        return Reply(NOT_ACTUAL)
    if draft.get("state") == plan.ASKING:
        return Reply(ASK_DURATION, Question("duration", plan_id, None))
    if draft.get("state") == plan.WRITTEN:
        return Reply(ALREADY_WRITTEN)
    if plan.is_fresh_write(draft, now, config.request_timeout_s):
        return Reply(WRITING_NOW)
    _transact(deps, "release_stale", plan_id=plan_id)
    found = _refresh(deps, draft)
    if isinstance(found, Reply):
        return found
    placed, shown = found
    if shown["fingerprint"] != fingerprint:
        return _store_shown(deps, draft, placed, shown, t0=now)
    return _write(deps, draft, placed)


# ------------------------------------------------------------------ show


def _show_new(deps: Deps, draft: dict[str, Any]) -> Reply:
    """Перший показ: горизонт і T0 від «зараз»; чернетку записано лише коли план показано."""
    draft = draft | {"horizon_end": (deps.now + HORIZON).isoformat(), "t0": deps.now.isoformat()}
    found = _refresh(deps, draft | {"state": plan.SHOWN})
    if isinstance(found, Reply):
        return found
    placed, shown = found
    return _store_shown(deps, draft, placed, shown, t0=deps.now, first=True)


def _refresh(deps: Deps, draft: dict[str, Any]) -> tuple[Placed, dict[str, Any]] | Reply:
    """Крок (0) і (1): своя подія → «записано»; інакше розстановка й відбиток поза транзакцією."""
    tz = _zone(deps)
    horizon_end = datetime.fromisoformat(draft["horizon_end"])
    own = event_id(draft["plan_id"], TASK_ID)
    events = deps.calendar.list_events(deps.now, horizon_end)
    if any(e.id == own for e in events) or deps.calendar.get_event(own) is not None:
        _transact(deps, "found", plan_id=draft["plan_id"])
        return Reply(WRITTEN_TEXT)
    busy = [Interval(e.start, e.end) for e in events]
    result = place(
        _task_spec(draft["task"]),
        busy,
        now=deps.now,
        tz=tz,
        step_min=deps.config.step_min,
        horizon_end=horizon_end,
        t0=datetime.fromisoformat(draft["t0"]),
    )
    if isinstance(result, NotFit):
        return Reply(NAMED_OUTSIDE if draft["task"].get("start_local") else NO_FREE_TIME)
    return result, _shown_fields(draft, result, tz)


def _zone(deps: Deps) -> ZoneInfo:
    return ZoneInfo(deps.calendar.timezone())


def _store_shown(
    deps: Deps,
    draft: dict[str, Any],
    placed: Placed,
    shown: dict[str, Any],
    *,
    t0: datetime,
    first: bool = False,
) -> Reply:
    fields = shown | {"t0": t0.isoformat()}
    if first:
        deps.store.set(deps.account_id, DRAFT_PATH, draft | fields | {"state": plan.SHOWN})
    else:
        _transact(deps, "show", plan_id=draft["plan_id"], shown=fields)
    return _plan_reply(draft, placed, shown)


def _shown_fields(draft: dict[str, Any], placed: Placed, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "start": placed.start.isoformat(),
        "end": placed.end.isoformat(),
        "tz": tz.key,
        "fingerprint": _fingerprint(draft["plan_id"], draft["task"], placed),
    }


def _plan_reply(draft: dict[str, Any], placed: Placed, shown: dict[str, Any]) -> Reply:
    tz = ZoneInfo(shown["tz"])
    start, end = placed.start.astimezone(tz), placed.end.astimezone(tz)
    title = draft["task"]["title"]
    view = PlanView(draft["plan_id"], title, start.isoformat(), end.isoformat(), shown["fingerprint"])
    text = (
        f"Пропоную: {WEEKDAYS[start.weekday()]}, {start.day} {MONTHS[start.month - 1]}, "
        f"{start:%H:%M}–{end:%H:%M} — {title}. Записати?"
    )
    return Reply(text, Question("plan", view.plan_id, view.fingerprint), view)


def _fingerprint(plan_id: str, task: dict[str, Any], placed: Placed) -> str:
    raw = json.dumps([plan_id, task, placed.start.isoformat(), placed.end.isoformat()], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ write


def _write(deps: Deps, draft: dict[str, Any], placed: Placed) -> Reply:
    """Flow (2): «показано → записується» → читання за id → створення → «записано»; помилка → «показано»."""
    plan_id = draft["plan_id"]
    begun = _transact(
        deps, "begin_write", plan_id=plan_id, fingerprint=_fingerprint(plan_id, draft["task"], placed)
    )
    if begun.outcome != "begin":
        if begun.outcome == plan.SHOWN:
            return _store_shown(deps, draft, placed, _shown_fields(draft, placed, _zone(deps)), t0=deps.now)
        return Reply(WRITING_NOW if begun.outcome == plan.WRITING else ALREADY_WRITTEN)
    started = deps.now.isoformat()
    own = event_id(plan_id, TASK_ID)
    try:
        if deps.calendar.get_event(own) is None:
            deps.calendar.insert_event(own, draft["task"]["title"], placed.start, placed.end)
    except Exception:
        _transact(deps, "interrupted", plan_id=plan_id, started=started)
        raise
    _transact(deps, "written", plan_id=plan_id, started=started)
    return Reply(WRITTEN_TEXT)


def _transact(deps: Deps, action: plan.Action | Literal["found"], **details: Any) -> plan.Decision:
    """Один перехід `plan.decide` у транзакції; `found` — своя подія вже є (крок 0)."""
    outcome: list[plan.Decision] = []

    def decide(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if action == "found":
            decision = _decide_found(snapshot, details)
        else:
            timeout = deps.config.request_timeout_s
            decision = plan.decide(snapshot, action, now=deps.now, request_timeout_s=timeout, **details)
        outcome.append(decision)
        return decision.write

    deps.store.transact(deps.account_id, DRAFT_PATH, decide)
    return outcome[-1]


def _decide_found(snapshot: dict[str, Any] | None, details: dict[str, Any]) -> plan.Decision:
    if (
        snapshot is None
        or snapshot.get("plan_id") != details["plan_id"]
        or snapshot.get("state") == plan.WRITTEN
    ):
        return plan.Decision(None, "unchanged")
    kept = {k: v for k, v in snapshot.items() if k != "writing_started"}
    return plan.Decision(kept | {"state": plan.WRITTEN}, "written")


# ------------------------------------------------------------------ parsing


def _parse_task(ai: AI, text: str, now: datetime) -> dict[str, Any]:
    answer = ai.generate_json("parse_task", _task_prompt(text, now), TASK_SCHEMA)
    duration = answer.get("duration_min")
    return {
        "task_id": TASK_ID,
        "title": str(answer.get("title") or text).strip(),
        "start_local": _start_local(answer.get("start_local")),
        "duration_min": duration if isinstance(duration, int) and duration > 0 else None,
    }


def _start_local(value: Any) -> str | None:
    """Лише дата й час; дата без часу в F1 — «час не названо»."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None).isoformat()
    except ValueError:
        return None


def _task_spec(task: dict[str, Any]) -> TaskSpec:
    start_local = datetime.fromisoformat(task["start_local"]) if task.get("start_local") else None
    return TaskSpec(task["task_id"], task["title"], int(task["duration_min"]), start_local)


def _task_prompt(text: str, now: datetime) -> str:
    return (
        "Мама надиктувала одну задачу. Витягни: title — коротка назва задачі; start_local — дата й час, "
        "якщо названо (YYYY-MM-DDTHH:MM:SS, або лише YYYY-MM-DD, якщо часу не названо; інакше null); "
        f"duration_min — тривалість у хвилинах, якщо названо, інакше null. Зараз {now.isoformat()}.\n"
        f"Задача: {text}"
    )


def _duration_prompt(text: str) -> str:
    return (
        "Скільки хвилин триває задача за цією відповіддю? duration_min — ціле число або null.\n"
        f"Відповідь: {text}"
    )
