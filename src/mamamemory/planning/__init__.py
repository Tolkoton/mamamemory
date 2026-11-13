"""Планування задач (S3 F1 → several-tasks F2): розбір, короткі питання, показ одного плану, «так» → події.

Без FastAPI. Залежності — параметрами. Чернетка одна на акаунт (`DRAFT_PATH`) зі списком задач; переходи —
`plan.decide` у `store.transact`. Одна задача F1 — список з однієї. F2: межі часу, пріоритети, Tasks, правки
показаного плану голосом (`edit_plan`). Не робить: переїзду записаних подій, кількох правок за раз.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.errors import LoginExpired, MissingScopes
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork, event_id
from mamamemory.integrations.store import Store
from mamamemory.planning import plan
from mamamemory.planning import schedule as schedule  # показ запланованого — `planning.schedule`
from mamamemory.planning.placement import Interval, Limits, Placement, TaskSpec, place_many
from mamamemory.replies import PlanView, Question, Reply

DRAFT_PATH = "plans/current"
TASK_ID = "t1"
HORIZON = timedelta(days=7)
STALE_AFTER = timedelta(hours=24)

ASK_DURATION = "Скільки часу це займе?"
WRITTEN_TEXT = "Записала в календар."
TASKS_LATER = "Ці задачі запишу в Tasks пізніше."
PARTLY_WRITTEN = "Записано не повністю — ось решта:"
NOT_UNDERSTOOD = "Не зрозуміла задачу, скажіть ще раз."
NOT_ACTUAL = "Це питання вже не актуальне."
NO_FREE_TIME = "Не знайшла вільного часу цього тижня."
NAMED_OUTSIDE = "Цей час уже минув або він далі ніж за тиждень."
ALREADY_WRITTEN = "Цей план уже записано."
WRITING_NOW = "Записую, хвилинку."
SIGN_IN_AGAIN = "Щоб показати план, увійди знову."
PLAN_SHOWN = "План уже показано — натисніть «так» під ним."
ASK_PRIORITIES = "Що з цього найважливіше?"
CHOOSE_TIMED = "Назвіть і ті, що поставити на час."
TO_TASKS = "Задачі без часу — у Tasks."
PLAN_WRITTEN = "План записано."
NO_WEEK_TASKS = "Задач на тиждень немає — скажіть, що треба зробити."
PLAN_REQUEST_WORDS = frozenset(
    "що в у мене мені мої мій які який на цей цьому цього наступний наступного весь цілий давай "
    "дні днів два три і а ще є маю буде".split()
)
ASK_LIMITS_FIRST = "Коли ви взагалі можете робити задачі? Наприклад: будні з дев'ятої до шостої."
LIMITS_PATH = "planning/limits"
NOT_UNDERSTOOD_EDIT = "Не зрозуміла правку, скажіть ще раз."
PLAN_EMPTY = "План порожній — нічого записувати."
EDIT_KINDS = ("move", "not_before", "remove", "untimed")

TASK_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "needs_time": {
            "type": "boolean",
            "description": "false — задача без часу (купити, колись цього тижня)",
        },
        "start_local": {"type": ["string", "null"], "description": "YYYY-MM-DDTHH:MM:SS, якщо названо час"},
        "day": {"type": ["string", "null"], "description": "YYYY-MM-DD, якщо названо лише день"},
        "duration_min": {"type": ["integer", "null"]},
    },
    "required": ["title", "needs_time", "start_local", "day", "duration_min"],
}
TASKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"tasks": {"type": "array", "items": TASK_DRAFT_SCHEMA}},
    "required": ["tasks"],
}
IS_ANSWER_HINT = (
    "чи мама взагалі відповідає на це питання; питання про плани, справи, роботу, нова задача — false"
)
IS_ANSWER_TRUE = (
    "true — будь-яка відповідь на це питання, зокрема задача зі списку номером чи назвою, прохання поставити "
    "на час, «так», «все однаково», «не знаю»"
)
PRIORITIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_answer": {"type": "boolean", "description": IS_ANSWER_HINT},
        "same": {"type": "boolean", "description": "true — «все однаково», «не важливо», «не знаю»"},
        "order": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "номери зі списку, від найважливішого",
        },
        "timed": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "номери задач, які мама просить поставити на час",
        },
    },
    "required": ["is_answer", "same", "order"],
}
LIMITS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_answer": {"type": "boolean", "description": IS_ANSWER_HINT},
        "same_as_last": {"type": "boolean", "description": "true — «так», «як минулого разу»"},
        "days": {"type": "array", "items": {"type": "integer"}, "description": "0 — понеділок … 6 — неділя"},
        "start_local": {"type": ["string", "null"], "description": "HH:MM"},
        "end_local": {"type": ["string", "null"], "description": "HH:MM"},
    },
    "required": ["is_answer", "same_as_last", "days", "start_local", "end_local"],
}
EDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "number": {"type": ["integer", "null"], "description": "номер задачі зі списку"},
        "kind": {"type": "string", "enum": ["move", "not_before", "remove", "untimed", "none"]},
        "day": {"type": ["string", "null"], "description": "YYYY-MM-DD, якщо названо день"},
        "start_local": {
            "type": ["string", "null"],
            "description": "YYYY-MM-DDTHH:MM:SS, якщо названо годину",
        },
        "not_before_local": {"type": ["string", "null"], "description": "HH:MM для «не раніше»"},
    },
    "required": ["number", "kind", "day", "start_local", "not_before_local"],
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


@dataclass(frozen=True)
class Shown:
    """Розстановка незаписаних задач і поля показу для чернетки."""

    placement: Placement
    fields: dict[str, Any]


def start(
    session: Session,
    text: str,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
    week: bool | None = None,
    replace_asking: bool = False,
) -> Reply:
    """Flow: розбір задач → дописати до незаписаної чернетки чи нова → наступне питання або показ плану.

    `week` (add-or-plan): `False` — «додай задачу» (без Tasks і без питання про важливість); `True` — «сплануй
    тиждень» (і без надиктованих задач); `None` — як F2 (маршрутизація завжди передає `True` чи `False`)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    current = store.get(session.account_id, DRAFT_PATH)
    if current is not None and plan.is_fresh_write(current, now, config.request_timeout_s):
        return Reply(WRITING_NOW)
    drafts = _parse_tasks(ai, text, now, _zone(deps))
    if week:
        drafts = [d for d in drafts if not _is_plan_request(d["title"])]
    if not drafts and week is not True:
        return Reply(NOT_UNDERSTOOD)
    abandoned = (
        current is not None
        and current.get("state") == plan.ASKING
        and (replace_asking or _stale(current, now))
    )
    if (
        current is not None
        and not abandoned
        and current.get("state") in (plan.ASKING, plan.SHOWN, plan.WRITING)
    ):
        _transact(deps, "release_stale", plan_id=current["plan_id"])
        draft = _with_tasks(current, tasks_of(current) + _new_tasks(drafts, _next_order(current)))
        if week and current.get("mode") == "add":
            draft = _with_week_tasks(deps, draft | {"mode": "week"})
        if len(_open_tasks(draft)) >= 2:
            draft = {k: v for k, v in draft.items() if k != "priorities_answered"}
    else:
        draft = {
            "plan_id": uuid.uuid4().hex,
            "tasks": _new_tasks(drafts, 0),
            "mode": "add" if week is False else "week",
        }
        if week is not False:
            draft = _with_week_tasks(deps, draft)
        if not tasks_of(draft):
            return Reply(NO_WEEK_TASKS)
    if draft.get("mode") == "add" and _saved_limits(deps) is not None:
        draft = draft | {"limits_answered": True}
    return _advance(deps, draft)


def _with_week_tasks(deps: Deps, draft: dict[str, Any]) -> dict[str, Any]:
    """Режим «сплануй тиждень»: відкриті задачі Google Tasks додаються до чернетки (без повторів за id)."""
    if not deps.config.use_tasks:
        return draft
    tasks = tasks_of(draft)
    known = {t.get("origin_tasks_id") for t in tasks}
    fresh = [t for t in _from_tasks(deps.calendar, len(tasks)) if t.get("origin_tasks_id") not in known]
    order = _next_order(draft)
    renumbered = [t | {"task_id": f"t{len(tasks) + n + 1}", "order": order + n} for n, t in enumerate(fresh)]
    return _with_tasks(draft, tasks + renumbered)


def _is_plan_request(title: str) -> bool:
    """Сама просьба «спланувати тиждень», яку розбір повернув як задачу (add-or-plan): у назві лише слова
    просьби й періоду, жодної справи («запланувати відпустку на тиждень» — задача, не просьба)."""
    words = re.findall(r"[\w'ʼ]+", title.casefold())
    asks = any(w.startswith(("сплан", "план")) for w in words) or "що" in words
    period = any(w.startswith(("тижд", "тижн", "дні", "днів")) for w in words)
    return asks and period and all(w in PLAN_REQUEST_WORDS or w.startswith(("сплан", "план", "тижд", "тижн"))
                                   for w in words)  # fmt: skip


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
    """Flow: та сама чернетка, що питає тривалість → тривалість задачі, про яку питали → далі; не розібрано —
    те саме питання."""
    found = try_answer_duration(
        session, plan_id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
    )
    return found if found is not None else _repeat(session, calendar, store, now, config)


def try_answer_duration(
    session: Session,
    plan_id: str,
    text: str,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
) -> Reply | None:
    """Як `answer_duration`, але фраза, що не є тривалістю, — `None` (чернетка без змін; stuck-question)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is not None and _too_old_to_answer(draft, now):
        return None
    if draft is None or draft.get("plan_id") != plan_id or draft.get("state") != plan.ASKING:
        return Reply(NOT_ACTUAL)
    current = _asked(config, draft)
    if current is None or current.kind != "duration":
        return _current_reply(deps, draft)
    duration = ai.generate_json("parse_duration", _duration_prompt(text), DURATION_SCHEMA).get("duration_min")
    if not isinstance(duration, int) or duration <= 0:
        return None
    tasks = tasks_of(draft)
    asked = _missing_duration(tasks)[0]["task_id"]
    updated = [t | {"duration_min": duration} if t["task_id"] == asked else t for t in tasks]
    return _advance(deps, _with_tasks(draft, updated))


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
    (0) свої події вже є → записані; (1) перерахунок решти; (2) той самий відбиток → запис;
    (3) інший відбиток → новий план (решта)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("plan_id") != plan_id:
        return Reply(NOT_ACTUAL)
    if draft.get("state") == plan.ASKING:
        return _question_reply(deps, draft)
    if draft.get("state") == plan.WRITTEN:
        return Reply(ALREADY_WRITTEN)
    if plan.is_fresh_write(draft, now, config.request_timeout_s):
        return Reply(WRITING_NOW)
    _transact(deps, "release_stale", plan_id=plan_id)
    draft = _found_own(deps, draft)
    if draft.get("state") == plan.WRITTEN:
        return Reply(_found_text(deps, draft))
    if _only_tasks_left(deps, draft) and fingerprint == draft.get("fingerprint"):
        rest = Shown(Placement([], []), {"fingerprint": fingerprint})
        return _write(deps, draft, rest, events=any(_written(t) for t in tasks_of(draft)))
    found = _refresh(deps, draft)
    if isinstance(found, Reply):
        return found
    if found.fields["fingerprint"] != fingerprint:
        return _store_shown(deps, draft, found, t0=now)
    return _write(deps, draft, found)


def next_question(
    draft: dict[str, Any], *, ask_limits: bool = False, ask_priorities: bool = False
) -> Question | None:
    """Наступне коротке питання над чернеткою (F2): важливість → тривалості → межі; `None` — показ плану."""
    week = draft.get("mode") != "add"
    if week and ask_priorities and len(_listed(draft)) >= 2 and not draft.get("priorities_answered"):
        return Question("priorities", draft["plan_id"], None)
    if _missing_duration(tasks_of(draft)):
        return Question("duration", draft["plan_id"], None)
    if ask_limits and not draft.get("limits_answered"):
        return Question("limits", draft["plan_id"], None)
    return None


def _asked(config: Config, draft: dict[str, Any]) -> Question | None:
    return next_question(draft, ask_limits=config.ask_limits, ask_priorities=config.ask_priorities)


def edit_plan(
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
    """Flow: та сама чернетка у «показано» → розбір правки → задача без тривалості — питання; усе прибрано —
    «план порожній»; інакше новий показ з новим T0. Нічого не пише в Calendar чи Tasks."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("plan_id") != plan_id:
        return Reply(NOT_ACTUAL)
    if plan.is_fresh_write(draft, now, config.request_timeout_s):
        return Reply(WRITING_NOW)
    _transact(deps, "release_stale", plan_id=plan_id)
    draft = store.get(session.account_id, DRAFT_PATH) or draft
    if draft.get("state") != plan.SHOWN:
        return _current_reply(deps, draft)
    answer = ai.generate_json("parse_edit", _edit_prompt(draft, text, now, _zone(deps)), EDIT_SCHEMA)
    tasks = _edited(draft, answer)
    if tasks is None:
        return Reply(NOT_UNDERSTOOD_EDIT, Question("plan", plan_id, draft["fingerprint"]))
    return _after_edit(deps, _with_tasks(draft, tasks))


def _after_edit(deps: Deps, draft: dict[str, Any]) -> Reply:
    """Після правки: порожній план — «записано»; бракує тривалості — питання; інакше показ (гілка 3 S3)."""
    draft = draft | {"asked_at": deps.now.isoformat()}
    if not _open_tasks(draft):
        outcome = _transact(deps, "edited", plan_id=draft["plan_id"], draft=draft | {"state": plan.WRITTEN})
        return Reply(PLAN_EMPTY) if outcome.outcome == "edited" else _busy_reply(outcome)
    if _asked(deps.config, draft) is not None:
        asking = _without_shown(draft) | {"state": plan.ASKING}
        outcome = _transact(deps, "edited", plan_id=draft["plan_id"], draft=asking)
        return _question_reply(deps, draft) if outcome.outcome == "edited" else _busy_reply(outcome)
    draft = draft | {"t0": deps.now.isoformat()}
    found = _refresh(deps, draft)
    if isinstance(found, Reply):
        return found
    fields = found.fields | {
        "t0": deps.now.isoformat(),
        "tasks": tasks_of(draft),
        "asked_at": draft["asked_at"],
    }
    outcome = _transact(deps, "show", plan_id=draft["plan_id"], shown=fields)
    return _plan_reply(draft, found) if outcome.outcome == "shown" else _busy_reply(outcome)


def _busy_reply(decision: plan.Decision) -> Reply:
    """Правку не застосовано: поки її розбирали, план почали записувати чи записали."""
    return Reply(ALREADY_WRITTEN if decision.outcome == plan.WRITTEN else WRITING_NOW)


def shown_titles(session: Session, plan_id: str, *, store: Store) -> list[str]:
    """Назви незаписаних задач показаного плану з цим `plan_id` (для маршрутизації); інакше порожньо."""
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("plan_id") != plan_id:
        return []
    return [t["title"] for t in _listed(draft)]


def answer_priorities(
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
    """Flow: та сама чернетка, що питає пріоритет → номери зі списку стають першими → `order` → далі; не
    розібрано — те саме питання."""
    found = try_answer_priorities(
        session, plan_id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
    )
    return found if found is not None else _repeat(session, calendar, store, now, config)


def try_answer_priorities(
    session: Session,
    plan_id: str,
    text: str,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
) -> Reply | None:
    """Як `answer_priorities`, але нечинна відповідь — `None` (чернетка без змін; stuck-question)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is not None and _too_old_to_answer(draft, now):
        return None
    if draft is None or draft.get("plan_id") != plan_id:
        return Reply(NOT_ACTUAL)
    current = _asked(config, draft) if draft.get("state") == plan.ASKING else None
    if current is None or current.kind != "priorities":
        return _current_reply(deps, draft)
    answer = ai.generate_json("parse_priorities", _priorities_prompt(draft, text), PRIORITIES_SCHEMA)
    if answer.get("is_answer") is False:
        return None
    reordered = _reordered(draft, answer)
    if reordered is None:
        return None
    return _advance(deps, _with_tasks(draft, reordered) | {"priorities_answered": True})


def answer_limits(
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
    """Flow: та сама чернетка, що питає межі → розбір (нові, «як минулого разу», частково) → далі;
    не розібрано — те саме питання."""
    found = try_answer_limits(
        session, plan_id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
    )
    return found if found is not None else _repeat(session, calendar, store, now, config)


def try_answer_limits(
    session: Session,
    plan_id: str,
    text: str,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    now: datetime,
    config: Config,
) -> Reply | None:
    """Як `answer_limits`, але нічого не назване й не «так» — `None` (чернетка без змін; stuck-question)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is not None and _too_old_to_answer(draft, now):
        return None
    if draft is None or draft.get("plan_id") != plan_id:
        return Reply(NOT_ACTUAL)
    current = _asked(config, draft) if draft.get("state") == plan.ASKING else None
    if current is None or current.kind != "limits":
        return _current_reply(deps, draft)
    answer = ai.generate_json("parse_limits", _limits_prompt(text), LIMITS_SCHEMA)
    if answer.get("is_answer") is False:
        return None
    saved = _saved_limits(deps)
    chosen, changed = _limits_from(answer, saved)
    if chosen is None:
        return None
    if changed:
        store.set(session.account_id, LIMITS_PATH, _limits_doc(chosen))
    return _advance(deps, draft | {"limits_answered": True})


def _repeat(session: Session, calendar: GoogleWork, store: Store, now: datetime, config: Config) -> Reply:
    """Те саме питання ще раз — для `answer_*`, коли відповідь не розібрано (поведінка F2)."""
    deps = Deps(calendar, store, now, config, session.account_id)
    draft = store.get(session.account_id, DRAFT_PATH)
    return _question_reply(deps, draft) if draft is not None else Reply(NOT_ACTUAL)


def tasks_of(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Задачі чернетки; документ S3 з одним полем `task` — список з однієї задачі на час."""
    if "tasks" in draft:
        return [_normalized(t) for t in draft["tasks"]]
    return [_normalized(draft["task"])] if draft.get("task") else []


# ------------------------------------------------------------------ open question (S4)


@dataclass(frozen=True)
class OpenQuestion:
    reply: Reply
    login_needed: bool
    at: datetime | None = field(default=None, compare=False)
    """Час останньої зміни, яку спричинила мама (`asked_at`), — для вибору найновішого питання (F3 S3)."""


def dismiss_asking(session: Session, *, store: Store) -> None:
    """Видалити чернетку плану тижня в стані «питаю» (plans-not-questions); інша — без змін."""
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is not None and draft.get("state") == plan.ASKING and draft.get("mode") == "week":
        store.delete(session.account_id, DRAFT_PATH)


def open_question(
    session: Session,
    *,
    calendar: Callable[[], GoogleWork],
    store: Store,
    now: datetime,
    config: Config,
) -> OpenQuestion | None:
    """Незакрите питання чернетки на відкритті (S4); календар — ліниво. Нічого не пише в Calendar.

    Flow: стан без Google → `None` чи питання тривалості; інакше календар → кроки 0–1 S3 → показ."""
    draft = store.get(session.account_id, DRAFT_PATH)
    if draft is None or draft.get("state") == plan.WRITTEN:
        return None
    if draft.get("state") == plan.ASKING and _stale(draft, now):
        return None
    if draft.get("state") == plan.ASKING:
        deps = Deps(cast(GoogleWork, None), store, now, config, session.account_id)
        return OpenQuestion(_question_reply(deps, draft), False, _asked_at(draft))
    if plan.is_fresh_write(draft, now, config.request_timeout_s):
        return None
    if now >= datetime.fromisoformat(draft["horizon_end"]):
        return None
    try:
        work = calendar()
    except (LoginExpired, MissingScopes):
        return OpenQuestion(Reply(SIGN_IN_AGAIN), True, _asked_at(draft))
    return _reopen(Deps(work, store, now, config, session.account_id), draft)


def _reopen(deps: Deps, draft: dict[str, Any]) -> OpenQuestion | None:
    """Застарілий «записується» — назад у «показано»; свої події вже є — «записано»; інакше новий показ."""
    _transact(deps, "release_stale", plan_id=draft["plan_id"])
    draft = _found_own(deps, draft)
    if draft.get("state") == plan.WRITTEN:
        return None
    found = _refresh(deps, draft)
    if isinstance(found, Reply):
        return OpenQuestion(found, False, _asked_at(draft))
    return OpenQuestion(_store_shown(deps, draft, found, t0=deps.now), False, _asked_at(draft))


def _too_old_to_answer(draft: dict[str, Any], now: datetime) -> bool:
    """Відповідь на питання чернетки «питаю», старшої за добу, — не відповідь (повідомлення йде як нове).
    Чернетка без відомого віку (до F3 S3) тут не стара: явна відповідь на її питання лишається відповіддю."""
    at = _asked_at(draft)
    return draft.get("state") == plan.ASKING and at is not None and now - at > STALE_AFTER


def _stale(draft: dict[str, Any], now: datetime) -> bool:
    """Чернетка «питаю», старша за добу (stuck-question): без `asked_at` і `horizon_end` — з часів до F3 S3,
    стара."""
    at = _asked_at(draft)
    return at is None or now - at > STALE_AFTER


def _asked_at(draft: dict[str, Any]) -> datetime | None:
    """Час останньої зміни, яку спричинила мама; чернетка до F3 S3 — час першого показу
    (`horizon_end` − горизонт)."""
    if draft.get("asked_at"):
        return datetime.fromisoformat(draft["asked_at"])
    if draft.get("horizon_end"):
        return datetime.fromisoformat(draft["horizon_end"]) - HORIZON
    return None


# ------------------------------------------------------------------ questions and show


def _advance(deps: Deps, draft: dict[str, Any]) -> Reply:
    """Наступне коротке питання чи показ плану; горизонт — від першого показу, T0 — від «зараз»; `asked_at` —
    час цієї зміни, яку спричинила мама (порядок незакритих питань, F3 S3)."""
    draft = draft | {"asked_at": deps.now.isoformat()}
    if _asked(deps.config, draft) is not None:
        deps.store.set(deps.account_id, DRAFT_PATH, _without_shown(draft) | {"state": plan.ASKING})
        return _question_reply(deps, draft)
    draft = draft | {"t0": deps.now.isoformat()}
    if "horizon_end" not in draft:
        draft = draft | {"horizon_end": (deps.now + HORIZON).isoformat()}
    found = _refresh(deps, draft)
    if isinstance(found, Reply):
        return found
    deps.store.set(deps.account_id, DRAFT_PATH, _without_shown(draft) | found.fields | {"state": plan.SHOWN})
    return _plan_reply(draft, found)


def _question_reply(deps: Deps, draft: dict[str, Any]) -> Reply:
    """Текст поточного питання за його видом: тривалість (одна задача — текст S3) чи межі."""
    question = _asked(deps.config, draft)
    if question is None:
        return _current_reply(deps, draft)
    if question.kind == "priorities":
        listed = "\n".join(f"{n}. {t['title']}" for n, t in enumerate(_listed(draft), start=1))
        timed_line = f"\n{CHOOSE_TIMED}" if any(t["source"] == "tasks" for t in _listed(draft)) else ""
        return Reply(f"{ASK_PRIORITIES}\n{listed}{timed_line}", question)
    if question.kind == "limits":
        saved = _saved_limits(deps)
        text = ASK_LIMITS_FIRST if saved is None else f"Як минулого разу — {_limits_text(saved)}?"
        return Reply(text, question)
    missing = _missing_duration(tasks_of(draft))
    text = f"Скільки часу займе «{missing[0]['title']}»?"
    return Reply(text, question)


def _current_reply(deps: Deps, draft: dict[str, Any]) -> Reply:
    """Відповідь на не поточне питання: поточне питання, чернетка без змін."""
    if draft.get("state") == plan.ASKING and _asked(deps.config, draft):
        return _question_reply(deps, draft)
    if draft.get("state") == plan.SHOWN and draft.get("fingerprint"):
        return Reply(PLAN_SHOWN, Question("plan", draft["plan_id"], draft["fingerprint"]))
    return Reply(NOT_ACTUAL)


def _missing_duration(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Задачі на час без тривалості — у порядку `order` (після відповіді про пріоритет — у новому)."""
    missing = [
        t
        for t in tasks
        if t["needs_time"] and t["duration_min"] is None and not _written(t) and not _removed(t)
    ]
    return sorted(missing, key=lambda t: t["order"])


def _refresh(deps: Deps, draft: dict[str, Any]) -> Shown | Reply:
    """Крок (1): розстановка незаписаних задач на час за теперішнім календарем і відбиток."""
    tz = _zone(deps)
    horizon_end = datetime.fromisoformat(draft["horizon_end"])
    events = deps.calendar.list_events(deps.now, horizon_end)
    timed = [t for t in _open_tasks(draft) if t["needs_time"] and not _in_tasks(t)]
    placement = place_many(
        [_task_spec(t) for t in timed],
        [Interval(e.start, e.end) for e in events],
        now=deps.now,
        tz=tz,
        step_min=deps.config.step_min,
        horizon_end=horizon_end,
        t0=datetime.fromisoformat(draft["t0"]),
        limits=_saved_limits(deps) if deps.config.ask_limits else None,
    )
    alone = len([t for t in tasks_of(draft) if not _removed(t)]) == 1 and len(timed) == 1
    if alone and placement.unplaced:
        return Reply(NAMED_OUTSIDE if timed[0].get("start_local") else NO_FREE_TIME)
    return Shown(placement, _shown_fields(draft, placement, tz))


def _found_own(deps: Deps, draft: dict[str, Any]) -> dict[str, Any]:
    """Крок (0): незаписана задача на час, чия подія вже є (за `event_id`), — записана; з Tasks — ще й закрита
    (друга половина вже підтвердженого запису); усе виконане — «записано»."""
    open_timed = [t for t in _open_tasks(draft) if t["needs_time"] and not _in_tasks(t)]
    found = {}
    if open_timed:
        horizon_end = datetime.fromisoformat(draft["horizon_end"])
        events = {e.id for e in deps.calendar.list_events(deps.now, horizon_end)}
        for task in open_timed:
            own = event_id(draft["plan_id"], task["task_id"])
            if own in events or deps.calendar.get_event(own) is not None:
                found[task["task_id"]] = own
    use_tasks = deps.config.use_tasks
    if found:
        decision = _transact(deps, "found", plan_id=draft["plan_id"], found=found, use_tasks=use_tasks)
        draft = decision.write if decision.write is not None else draft
    if use_tasks and draft.get("state") != plan.WRITTEN:
        for task in tasks_of(draft):
            if _written(task) and task["source"] == "tasks" and not task["written"]["closed"]:
                deps.calendar.complete_task(task["origin_tasks_id"])
                marked = _transact(
                    deps, "task_mark", plan_id=draft["plan_id"], task_id=task["task_id"],
                    fields={"closed": True},
                    use_tasks=True,
                )  # fmt: skip
                draft = marked.write if marked.write is not None else draft
    return draft


def _zone(deps: Deps) -> ZoneInfo:
    return ZoneInfo(deps.calendar.timezone())


def _store_shown(deps: Deps, draft: dict[str, Any], shown: Shown, *, t0: datetime) -> Reply:
    fields = shown.fields | {"t0": t0.isoformat()}
    _transact(deps, "show", plan_id=draft["plan_id"], shown=fields | {"tasks": tasks_of(draft)})
    return _plan_reply(draft, shown)


def _shown_fields(draft: dict[str, Any], placement: Placement, tz: ZoneInfo) -> dict[str, Any]:
    first = placement.placed[0] if placement.placed else None
    return {
        "start": first[1].isoformat() if first else "",
        "end": first[2].isoformat() if first else "",
        "tz": tz.key,
        "fingerprint": _fingerprint(draft, placement),
    }


def _plan_reply(draft: dict[str, Any], shown: Shown) -> Reply:
    tz = ZoneInfo(shown.fields["tz"])
    by_id = {t["task_id"]: t for t in tasks_of(draft)}
    items = [
        {"task_id": task_id, "title": by_id[task_id]["title"], "start": s.astimezone(tz).isoformat(),
         "end": e.astimezone(tz).isoformat()}
        for task_id, s, e in shown.placement.placed
    ]  # fmt: skip
    untimed = [
        {"task_id": t["task_id"], "title": t["title"]} for t in _open_tasks(draft) if not t["needs_time"]
    ]
    unplaced = [{"task_id": i, "title": by_id[i]["title"]} for i in shown.placement.unplaced]
    first = items[0] if items else {"title": untimed[0]["title"] if untimed else "", "start": "", "end": ""}
    fingerprint = shown.fields["fingerprint"]
    view = PlanView(
        draft["plan_id"], first["title"], first["start"], first["end"], fingerprint, items, untimed, unplaced
    )
    return Reply(
        _plan_text(draft, items, untimed, unplaced), Question("plan", view.plan_id, fingerprint), view
    )


def _plan_text(
    draft: dict[str, Any],
    items: list[dict[str, str]],
    untimed: list[dict[str, str]],
    unplaced: list[dict[str, str]],
) -> str:
    lines = [PARTLY_WRITTEN] if any(_written(t) for t in tasks_of(draft)) else []
    if len(items) == 1 and not untimed and not unplaced and not lines:
        return f"Пропоную: {_when(items[0])}. Записати?"
    lines.append("Пропоную:")
    lines += [_when(item) for item in items]
    if untimed:
        lines.append("Без часу: " + ", ".join(t["title"] for t in untimed))
    if unplaced:
        lines.append("Не вмістилось: " + ", ".join(t["title"] for t in unplaced))
    lines.append("Записати?")
    return "\n".join(lines)


def _when(item: dict[str, str]) -> str:
    start, end = datetime.fromisoformat(item["start"]), datetime.fromisoformat(item["end"])
    return (
        f"{WEEKDAYS[start.weekday()]}, {start.day} {MONTHS[start.month - 1]}, "
        f"{start:%H:%M}–{end:%H:%M} — {item['title']}"
    )


def _fingerprint(draft: dict[str, Any], placement: Placement) -> str:
    """Хеш незаписаних задач (без `written`) і їхньої розстановки: часткове записування змінює відбиток."""
    tasks = [{k: v for k, v in t.items() if k != "written"} for t in _open_tasks(draft)]
    placed = [[i, s.isoformat(), e.isoformat()] for i, s, e in placement.placed]
    raw = json.dumps([draft["plan_id"], tasks, placed, placement.unplaced], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ write


def _only_tasks_left(deps: Deps, draft: dict[str, Any]) -> bool:
    """Усі події показаного плану вже записані, лишились кроки Tasks: обрив на них не змінює відбитка."""
    if not deps.config.use_tasks or not any(_written(t) for t in tasks_of(draft)):
        return False
    return not [t for t in _open_tasks(draft) if t["needs_time"] and not _in_tasks(t)]


def _write(deps: Deps, draft: dict[str, Any], shown: Shown, *, events: bool = False) -> Reply:
    """Flow (2): «показано → записується» → по задачі: читання за id, створення, запис id → «записано»;
    помилка → «показано» (решту покаже наступне «так»)."""
    plan_id = draft["plan_id"]
    begun = _transact(deps, "begin_write", plan_id=plan_id, fingerprint=shown.fields["fingerprint"])
    if begun.outcome != "begin":
        if begun.outcome == plan.SHOWN:
            return _store_shown(deps, draft, shown, t0=deps.now)
        return Reply(WRITING_NOW if begun.outcome == plan.WRITING else ALREADY_WRITTEN)
    started = deps.now.isoformat()
    titles = {t["task_id"]: t["title"] for t in tasks_of(draft)}
    try:
        for task_id, start_at, end_at in shown.placement.placed:
            own = event_id(plan_id, task_id)
            if deps.calendar.get_event(own) is None:
                deps.calendar.insert_event(own, titles[task_id], start_at, end_at)
            _transact(deps, "task_written", plan_id=plan_id, started=started, task_id=task_id, event_id=own)
        inserted = _write_tasks(deps, draft, shown, started) if deps.config.use_tasks else False
    except Exception:
        _transact(deps, "interrupted", plan_id=plan_id, started=started)
        raise
    _transact(deps, "written", plan_id=plan_id, started=started)
    if deps.config.use_tasks:
        return Reply(_tasks_text(events or bool(shown.placement.placed), inserted))
    return Reply(_written_text(draft, shown.placement.unplaced))


def _write_tasks(deps: Deps, draft: dict[str, Any], shown: Shown, started: str) -> bool:
    """Після подій: закрити в Tasks поставлені задачі з Tasks, потім створити в Tasks мамині задачі без часу
    й ті, що не вмістились; кожен крок — запис у чернетку за того самого `writing_started`.
    Повертає, чи створено щось у Tasks."""
    by_id = {t["task_id"]: t for t in tasks_of(draft)}
    plan_id = draft["plan_id"]
    for task_id, _, _ in shown.placement.placed:
        task = by_id[task_id]
        if task["source"] == "tasks" and not task["written"]["closed"]:
            deps.calendar.complete_task(task["origin_tasks_id"])
            _transact(
                deps, "task_mark", plan_id=plan_id, task_id=task_id, fields={"closed": True}, started=started
            )
    to_tasks = [t for t in _open_tasks(draft) if not t["needs_time"]]
    to_tasks += [by_id[i] for i in shown.placement.unplaced]
    inserted = False
    for task in to_tasks:
        if task["source"] == "speech" and not task["written"]["tasks_id"]:
            new_id = deps.calendar.insert_task(task["title"])
            _transact(
                deps, "task_mark", plan_id=plan_id, task_id=task["task_id"], fields={"tasks_id": new_id},
                started=started,
            )  # fmt: skip
            inserted = True
    return inserted


def _tasks_text(events: bool, inserted: bool) -> str:
    parts = ([WRITTEN_TEXT] if events else []) + ([TO_TASKS] if inserted else [])
    return " ".join(parts) if parts else PLAN_WRITTEN


def _found_text(deps: Deps, draft: dict[str, Any]) -> str:
    """Відповідь, коли крок 0 довів запис до кінця."""
    if not deps.config.use_tasks:
        return _written_text(draft)
    return _tasks_text(any(_written(t) for t in tasks_of(draft)), False)


def _written_text(draft: dict[str, Any], unplaced: list[str] | None = None) -> str:
    """«Записала» і рядок про Tasks, коли є задачі без часу чи «не вмістилось»; лише без часу — лише рядок."""
    tasks = [t for t in tasks_of(draft) if not _removed(t)]
    if not any(t["needs_time"] for t in tasks):
        return TASKS_LATER
    later = any(not t["needs_time"] for t in tasks) or bool(unplaced)
    return f"{WRITTEN_TEXT} {TASKS_LATER}" if later else WRITTEN_TEXT


TransactAction = plan.Action | Literal["found", "task_written", "task_mark", "edited"]


def _transact(deps: Deps, action: TransactAction, **details: Any) -> plan.Decision:
    """Один перехід у транзакції: `plan.decide`, `found` (крок 0) чи `task_written` (id однієї події)."""
    outcome: list[plan.Decision] = []

    def decide(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if action == "found":
            decision = _decide_found(snapshot, details)
        elif action == "task_written":
            decision = _decide_task_written(snapshot, details)
        elif action == "task_mark":
            decision = _decide_task_mark(snapshot, details)
        elif action == "edited":
            decision = _decide_edited(snapshot, details, deps)
        else:
            timeout = deps.config.request_timeout_s
            decision = plan.decide(snapshot, action, now=deps.now, request_timeout_s=timeout, **details)
        outcome.append(decision)
        return decision.write

    deps.store.transact(deps.account_id, DRAFT_PATH, decide)
    return outcome[-1]


def _decide_found(snapshot: dict[str, Any] | None, details: dict[str, Any]) -> plan.Decision:
    """Знайдені події записуються в задачі; коли всі задачі на час записані — «записано»."""
    if (
        snapshot is None
        or snapshot.get("plan_id") != details["plan_id"]
        or snapshot.get("state") == plan.WRITTEN
    ):
        return plan.Decision(None, "unchanged")
    tasks = [_mark(t, details["found"].get(t["task_id"])) for t in tasks_of(snapshot)]
    return _maybe_written(_with_tasks(snapshot, tasks), bool(details.get("use_tasks")), "found")


def _decide_edited(snapshot: dict[str, Any] | None, details: dict[str, Any], deps: Deps) -> plan.Decision:
    """Чернетка після правки (питання чи «план порожній») — лише поверх «показано» того самого плану."""
    if (
        snapshot is None
        or snapshot.get("plan_id") != details["plan_id"]
        or snapshot.get("state") != plan.SHOWN
    ):
        return plan.Decision(None, str(snapshot.get("state")) if snapshot is not None else "lost")
    return plan.Decision(details["draft"], "edited")


def _decide_task_mark(snapshot: dict[str, Any] | None, details: dict[str, Any]) -> plan.Decision:
    """Поля `written` однієї задачі (закрито в Tasks, id задачі Tasks): під час запису — лише за того самого
    `writing_started`; у кроці 0 — будь-коли до «записано»; там усе виконане — «записано»."""
    if (
        snapshot is None
        or snapshot.get("plan_id") != details["plan_id"]
        or snapshot.get("state") == plan.WRITTEN
    ):
        return plan.Decision(None, "lost")
    started = details.get("started")
    writing = snapshot.get("state") == plan.WRITING and snapshot.get("writing_started") == started
    if started is not None and not writing:
        return plan.Decision(None, "lost")
    tasks = [
        t | {"written": t["written"] | details["fields"]} if t["task_id"] == details["task_id"] else t
        for t in tasks_of(snapshot)
    ]
    updated = _with_tasks(snapshot, tasks)
    if started is not None:
        return plan.Decision(updated, "ok")
    return _maybe_written(updated, bool(details.get("use_tasks")), "ok")


def _maybe_written(draft: dict[str, Any], use_tasks: bool, outcome: str) -> plan.Decision:
    if all(_done(t, use_tasks) for t in tasks_of(draft)):
        kept = {k: v for k, v in draft.items() if k != "writing_started"}
        return plan.Decision(kept | {"state": plan.WRITTEN}, "written")
    return plan.Decision(draft, outcome)


def _done(task: dict[str, Any], use_tasks: bool) -> bool:
    """Задача виконана в плані: подія (задача з Tasks — ще й закрита); з Tasks без часу — завжди; мамина
    без часу чи «не вмістилось» — має задачу в Tasks (без `use_tasks` задача без часу виконана завжди)."""
    written = task["written"]
    if _removed(task):
        return True
    if task["needs_time"]:
        evented = bool(written["event_id"]) and (task["source"] != "tasks" or bool(written["closed"]))
        return evented or (use_tasks and task["source"] == "speech" and bool(written["tasks_id"]))
    return not use_tasks or task["source"] == "tasks" or bool(written["tasks_id"])


def _decide_task_written(snapshot: dict[str, Any] | None, details: dict[str, Any]) -> plan.Decision:
    """Id однієї події записується лише за того самого «записується» (`writing_started`)."""
    same = (
        snapshot is not None
        and snapshot.get("plan_id") == details["plan_id"]
        and snapshot.get("state") == plan.WRITING
        and snapshot.get("writing_started") == details["started"]
    )
    if not same or snapshot is None:
        return plan.Decision(None, "lost")
    marks = {details["task_id"]: details["event_id"]}
    return plan.Decision(
        _with_tasks(snapshot, [_mark(t, marks.get(t["task_id"])) for t in tasks_of(snapshot)]), "ok"
    )


# ------------------------------------------------------------------ tasks


def _normalized(task: dict[str, Any]) -> dict[str, Any]:
    """Задача у форматі F2; поля, яких немає в документі S3, — за замовчуванням (на час, без дня)."""
    return {
        "task_id": task["task_id"],
        "title": task["title"],
        "needs_time": task.get("needs_time", True),
        "duration_min": task.get("duration_min"),
        "start_local": task.get("start_local"),
        "constraints": task.get("constraints") or {"day": None},
        "order": task.get("order", int(str(task["task_id"]).lstrip("t") or 1) - 1),
        "source": task.get("source", "speech"),
        "written": task.get("written") or {"event_id": None, "tasks_id": None, "closed": False},
    } | ({"origin_tasks_id": task["origin_tasks_id"]} if task.get("origin_tasks_id") else {})


def _with_tasks(draft: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {k: v for k, v in draft.items() if k != "task"} | {"tasks": tasks}


def _without_shown(draft: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in draft.items() if k not in ("fingerprint", "start", "end", "writing_started")}


def _written(task: dict[str, Any]) -> bool:
    return bool(task["written"]["event_id"])


def _mark(task: dict[str, Any], own: str | None) -> dict[str, Any]:
    return task if own is None else task | {"written": task["written"] | {"event_id": own}}


def _in_tasks(task: dict[str, Any]) -> bool:
    """Мамина задача, яку цей план уже записав у Tasks: більше не розставляється."""
    return task["source"] == "speech" and bool(task["written"]["tasks_id"])


def _listed(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Задачі для питання «що важливіше?»: усі ще не записані (ні подією, ні в Tasks)."""
    return [t for t in _open_tasks(draft) if not _in_tasks(t)]


def _from_tasks(calendar: GoogleWork, already: int) -> list[dict[str, Any]]:
    """Відкриті задачі Google Tasks — кандидати без часу після надиктованих, без повторів за id."""
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    for item in calendar.list_open_tasks():
        if item.id in seen:
            continue
        seen.add(item.id)
        n = already + len(found)
        task = {
            "task_id": f"t{n + 1}",
            "title": item.title,
            "needs_time": False,
            "order": n,
            "source": "tasks",
        }
        found.append(_normalized(task | {"origin_tasks_id": item.id}))
    return found


def _open_tasks(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Незаписані задачі плану в порядку `order`; прибрані правкою — ніде."""
    tasks = (t for t in tasks_of(draft) if not _written(t) and not _removed(t))
    return sorted(tasks, key=lambda t: t["order"])


def _removed(task: dict[str, Any]) -> bool:
    return bool(task["constraints"].get("removed"))


def _new_tasks(drafts: list[dict[str, Any]], already: int) -> list[dict[str, Any]]:
    return [
        _normalized(d | {"task_id": f"t{already + n + 1}", "order": already + n})
        for n, d in enumerate(drafts)
    ]


def _task_spec(task: dict[str, Any]) -> TaskSpec:
    start_local = datetime.fromisoformat(task["start_local"]) if task.get("start_local") else None
    day = task["constraints"].get("day")
    not_before = task["constraints"].get("not_before_local")
    return TaskSpec(
        task["task_id"],
        task["title"],
        int(task["duration_min"]),
        start_local,
        date.fromisoformat(day) if day else None,
        _hhmm(not_before) if not_before else None,
    )


# ------------------------------------------------------------------ parsing


def _parse_tasks(ai: AI, text: str, now: datetime, tz: ZoneInfo) -> list[dict[str, Any]]:
    """Задачі з мовлення; відповідь одним об'єктом (модель F1) — одна задача."""
    answer = ai.generate_json("parse_task", _task_prompt(text, now, tz), TASKS_SCHEMA)
    raw = answer.get("tasks")
    items = raw if isinstance(raw, list) else ([answer] if answer.get("title") else [])
    return [d for d in (_task_draft(item, text) for item in items if isinstance(item, dict)) if d["title"]]


def _task_draft(item: dict[str, Any], text: str) -> dict[str, Any]:
    duration = item.get("duration_min")
    needs_time = item.get("needs_time") is not False
    return {
        "title": str(item.get("title") or "").strip(),
        "needs_time": needs_time,
        "start_local": _start_local(item.get("start_local")) if needs_time else None,
        "constraints": {"day": _day(item.get("day")) if needs_time else None},
        "duration_min": duration if needs_time and isinstance(duration, int) and duration > 0 else None,
    }


def _start_local(value: Any) -> str | None:
    """Лише дата й час; дата без часу в полі часу — «час не названо» (як F1)."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None).isoformat()
    except ValueError:
        return None


def _day(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _task_prompt(text: str, now: datetime, tz: ZoneInfo) -> str:
    """Підказка розбору: дні тижня в поясі календаря (модель погано їх рахує) і правила полів."""
    now = now.astimezone(tz)
    days = "; ".join(
        f"{WEEKDAYS[(now + timedelta(days=n)).weekday()]} — {(now + timedelta(days=n)).date().isoformat()}"
        for n in range(8)
    )
    return (
        "Мама надиктувала одну чи кілька задач. "
        'Кожна окрема дія — окрема задача ("купити ліки і хліб" — дві). '
        "Для кожної: title — коротка назва з великої літери; "
        "needs_time — true для дзвінків, візитів, зустрічей, роботи, будь-чого, що робиться в певний час; "
        "false лише для покупок і дрібних справ, які мама робить «колись»; "
        "start_local — дата й час (YYYY-MM-DDTHH:MM:SS) лише якщо мама назвала годину, "
        "інакше null — не вигадуй годину; "
        "day — дата (YYYY-MM-DD), якщо мама назвала день («завтра», «у четвер»), інакше null; "
        "duration_min — тривалість у хвилинах лише якщо мама її назвала, інакше null.\n"
        f"Зараз {now.isoformat()}. Дні: {days}. Назва дня тижня без «наступного» — найближчий такий день, "
        "сьогоднішній теж.\n"
        f"Задачі: {text}"
    )


def _duration_prompt(text: str) -> str:
    return (
        "Скільки хвилин триває задача за цією відповіддю? duration_min — ціле число або null.\n"
        f"Відповідь: {text}"
    )


# ------------------------------------------------------------------ limits (time-limits F2)


def _saved_limits(deps: Deps) -> Limits | None:
    doc = deps.store.get(deps.account_id, LIMITS_PATH)
    if doc is None:
        return None
    return Limits(frozenset(int(d) for d in doc["days"]), _hhmm(doc["start_local"]), _hhmm(doc["end_local"]))


def _limits_from(answer: dict[str, Any], saved: Limits | None) -> tuple[Limits | None, bool]:
    """(межі, чи записувати): «так» — збережені без запису; нічого не названо й не «так» — питання ще раз;
    названі поля замінюють свої поля збережених меж, неназвані — з них; без збережених — усе назвати."""
    named_days = [int(d) for d in answer.get("days") or [] if isinstance(d, int) and 0 <= d <= 6]
    start, end = _maybe_hhmm(answer.get("start_local")), _maybe_hhmm(answer.get("end_local"))
    if not named_days and start is None and end is None and not answer.get("same_as_last"):
        return None, False
    base = saved
    days = frozenset(named_days) if named_days else (base.days if base else frozenset())
    start = start or (base.start_local if base else None)
    end = end or (base.end_local if base else None)
    if not days or start is None or end is None or start >= end:
        return None, False
    chosen = Limits(days, start, end)
    return chosen, chosen != saved


def _limits_doc(limits: Limits) -> dict[str, Any]:
    return {
        "days": sorted(limits.days),
        "start_local": limits.start_local.strftime("%H:%M"),
        "end_local": limits.end_local.strftime("%H:%M"),
    }


def _limits_text(limits: Limits) -> str:
    days = sorted(limits.days)
    if days == list(range(7)):
        named = "щодня"
    elif days == list(range(5)):
        named = "будні"
    else:
        named = ", ".join(WEEKDAYS[d] for d in days)
    return f"{named}, {limits.start_local:%H:%M}–{limits.end_local:%H:%M}"


def _hhmm(value: str) -> time:
    return time.fromisoformat(value)


def _maybe_hhmm(value: Any) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _limits_prompt(text: str) -> str:
    return (
        "Мама каже, коли вона взагалі може робити задачі. "
        "same_as_last — true, якщо вона погоджується з минулими межами («так», «як минулого разу»); "
        "days — дні, які вона назвала (0 — понеділок … 6 — неділя; «будні» — 0–4; «щодня» — 0–6; "
        "«крім неділі» — без 6), інакше порожній список; "
        "start_local і end_local — години (HH:MM), якщо названо, інакше null. "
        f"is_answer — {IS_ANSWER_HINT}; {IS_ANSWER_TRUE}.\n"
        f"Відповідь: {text}"
    )


# ------------------------------------------------------------------ priorities (priorities F2)


def _reordered(draft: dict[str, Any], answer: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Названі номери — першими в названому порядку, решта — після них; значення `order` незаписаних задач
    переставляються між собою, записані не змінюються; номери в `timed` ставлять задачі з Tasks на час
    (порядку не змінюють); ні `same`, ні чинного номера в `order` чи `timed` — `None`."""
    listed = _listed(draft)
    numbers = [n for n in answer.get("order") or [] if isinstance(n, int) and 1 <= n <= len(listed)]
    timed_ids = {
        listed[n - 1]["task_id"]
        for n in answer.get("timed") or []
        if isinstance(n, int) and 1 <= n <= len(listed) and listed[n - 1]["source"] == "tasks"
    }
    picked = [] if answer.get("same") else [listed[n - 1] for n in dict.fromkeys(numbers)]
    if not answer.get("same") and not picked and not timed_ids:
        return None
    ranked = picked + [t for t in listed if t not in picked]
    slots = sorted(t["order"] for t in listed)
    new_order = {t["task_id"]: slot for t, slot in zip(ranked, slots, strict=True)}
    tasks = []
    for t in tasks_of(draft):
        t = t | {"order": new_order.get(t["task_id"], t["order"])}
        tasks.append(t | {"needs_time": True} if t["task_id"] in timed_ids else t)
    return sorted(tasks, key=lambda t: t["order"])


def _next_order(draft: dict[str, Any]) -> int:
    return max((t["order"] for t in tasks_of(draft)), default=-1) + 1


def _priorities_prompt(draft: dict[str, Any], text: str) -> str:
    listed = "\n".join(f"{n}. {t['title']}" for n, t in enumerate(_listed(draft), start=1))
    return (
        "Асистент показав мамі список задач і спитав, що з цього найважливіше.\n"
        f"{listed}\n"
        "order — номери зі списку, які мама назвала, від найважливішого (назву задачі переклади в її номер); "
        "same — true, якщо мама каже «все однаково», «не важливо», «не знаю»; "
        "timed — номери задач, які мама просить поставити на час, інакше порожній список. "
        "Номер, названий лише «на час», не додавай в order — "
        "order тільки для того, що мама назвала важливішим (у «спершу X, а Y теж на час» Y — лише в timed). "
        f"is_answer — {IS_ANSWER_HINT}; {IS_ANSWER_TRUE}.\n"
        f"Відповідь: {text}"
    )


# ------------------------------------------------------------------ voice edits (voice-edits F2)


def _edited(draft: dict[str, Any], answer: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Задачі чернетки з однією правкою задачі за номером у `_listed`; нечитана правка — `None`."""
    listed = _listed(draft)
    number, kind = answer.get("number"), answer.get("kind")
    if kind not in EDIT_KINDS or not isinstance(number, int) or not 1 <= number <= len(listed):
        return None
    changed = _edit_task(listed[number - 1], kind, answer)
    if changed is None:
        return None
    return [changed if t["task_id"] == changed["task_id"] else t for t in tasks_of(draft)]


def _edit_task(task: dict[str, Any], kind: str, answer: dict[str, Any]) -> dict[str, Any] | None:
    """Одна правка одної задачі (Seam voice-edits); бракує потрібного поля — `None`."""
    constraints = dict(task["constraints"])
    if kind == "remove":
        return task | {"constraints": constraints | {"removed": True}}
    if kind == "untimed":
        return task | {"needs_time": False}
    if kind == "not_before":
        not_before = _maybe_hhmm(answer.get("not_before_local"))
        if not_before is None:
            return None
        return task | {
            "start_local": None,
            "constraints": constraints | {"not_before_local": f"{not_before:%H:%M}"},
        }
    start_local, day = _start_local(answer.get("start_local")), _day(answer.get("day"))
    if start_local is not None:
        constraints.pop("not_before_local", None)
        return task | {
            "needs_time": True,
            "start_local": start_local,
            "constraints": constraints | {"day": start_local[:10]},
        }
    if day is not None:
        return task | {"needs_time": True, "start_local": None, "constraints": constraints | {"day": day}}
    return None


def _edit_prompt(draft: dict[str, Any], text: str, now: datetime, tz: ZoneInfo) -> str:
    listed = "\n".join(f"{n}. {t['title']}" for n, t in enumerate(_listed(draft), start=1))
    now = now.astimezone(tz)
    days = "; ".join(
        f"{WEEKDAYS[(now + timedelta(days=n)).weekday()]} — {(now + timedelta(days=n)).date().isoformat()}"
        for n in range(8)
    )
    return (
        "Асистент показав мамі план задач, вона просить його змінити.\n"
        f"Задачі плану:\n{listed}\n"
        "number — номер задачі зі списку, про яку мама говорить (назву задачі переклади в її номер), "
        "інакше null; "
        "kind — move (перенести на інший день чи годину), not_before (не раніше якоїсь години), "
        "remove (прибрати з плану), untimed (без часу), none (це не правка або незрозуміло); "
        "day — дата (YYYY-MM-DD) для move, якщо мама назвала день без години; "
        "start_local — дата й час (YYYY-MM-DDTHH:MM:SS) для move, лише якщо мама назвала годину, "
        "не вигадуй годину; "
        "not_before_local — година (HH:MM) для not_before. Неназване — null.\n"
        f"Зараз {now.isoformat()}. Дні: {days}. Назва дня тижня без «наступного» — найближчий такий день, "
        "сьогоднішній теж.\n"
        f"Мама: {text}"
    )
