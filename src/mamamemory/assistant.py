"""Асистент (S3): маршрутизація повідомлення мами до `planning`.

Не робить: голосу (S2), незакритих питань (S4), правок плану (F2).
"""

import dataclasses
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from mamamemory import access, cases, planning
from mamamemory.access import Session
from mamamemory.cases import recall as case_recall
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.replies import Question, Reply, ReplyTo

CANNOT_TEXT = "Не зрозуміла. Скажіть «що ти вмієш?» — розкажу."
GUIDE_PATH = "settings/guide_shown"


def guide_text(language: str) -> str:
    """Короткий гайд (F5 S2, G5) мовою акаунта; поки мова одна — текст `uk`."""
    return GUIDE_UK


GUIDE_UK = (
    "Я допомагаю планувати й пам'ятати справи. Що можна сказати:\n"
    "• «Додай задачу подзвонити нотаріусу в понеділок» — поставлю в календар.\n"
    "• «Сплануй тиждень» — складу план з усіх задач.\n"
    "• «Запиши до пані Шмідт: …», або ＋ (фото чи файл) — покладу у справу.\n"
    "• «Переклади … до …» — перенесу в іншу справу.\n"
    "• «Працюю над …», потім «що я робила з …?» — запам'ятаю й нагадаю.\n"
    "• «Що ми знаємо про пані Шмідт?», «які плани на тиждень?» — розповім.\n"
    "• «Які в мене задачі?» — покажу список задач.\n"
    "• 🔊 біля відповіді — прочитаю вголос.\n"
    "Не зрозумію — перепитаю."
)


ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "yes", "no", "not_needed", "case_name", "new_task", "edit", "note", "move", "plan_week",
                "unsure", "help", "working_on", "schedule", "tasks", "work_question", "recall", "other",
            ],
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "лише з unsure: два найімовірніші наміри",
        },
    },
    "required": ["intent"],
}  # fmt: skip


def handle_message(
    session: Session,
    text: str,
    reply_to: ReplyTo | None,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    config: Config,
    now: datetime,
    message_id: str | None = None,
    deadline: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Reply:
    """Flow: відповідь на коротке питання плану → `planning`; інакше модель маршрутизації → план, правка,
    нова задача, нотатка (`cases.add_note`) чи «так» на «Створити справу?» (`cases.confirm_case`)."""
    deadline = deadline or now + timedelta(seconds=config.request_timeout_s - 2 * config.call_timeout_s)
    clock = clock or (lambda: now)
    replace_asking = False
    refused_kind: str | None = None
    answer_short = SHORT_ANSWERS.get(reply_to.kind) if reply_to is not None else None
    if reply_to is not None and answer_short is not None:
        found = answer_short(
            session, reply_to.id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
        )
        if found is not None:
            return found
        refused_kind = reply_to.kind
        reply_to, replace_asking = None, True
    if reply_to is not None and reply_to.kind == "clarify":
        chosen = _chosen(session, reply_to.id, text, ai=ai, store=store)
        if chosen is not None:
            return _run_clarified(
                chosen, session, ai=ai, calendar=calendar, store=store, config=config, now=now,
                deadline=deadline, clock=clock,
            )  # fmt: skip
        reply_to = None
    on_plan = reply_to is not None and reply_to.kind == "plan"
    titles = planning.shown_titles(session, reply_to.id, store=store) if reply_to and on_plan else []
    on_case = reply_to is not None and reply_to.kind == "case"
    asked_question = cases.asked_text(session, store, reply_to.id) if reply_to and on_case else None
    prompt = _route_prompt(text, reply_to, titles, asked_question)
    answer = ai.generate_json("route", prompt, route_schema(reply_to))
    intent = answer.get("intent")
    if intent == "schedule" and refused_kind in ("priorities", "limits"):
        planning.dismiss_asking(session, store=store)
    if intent == "unsure":
        return _clarify(
            session, text, reply_to, answer.get("options"), store=store, now=now,
            message_id=message_id, replace_asking=replace_asking,
        )  # fmt: skip
    return _dispatch(
        str(intent), session, text, reply_to, ai=ai, calendar=calendar, store=store, config=config, now=now,
        message_id=message_id, deadline=deadline, clock=clock, replace_asking=replace_asking,
    )  # fmt: skip


def _dispatch(
    intent: str,
    session: Session,
    text: str,
    reply_to: ReplyTo | None,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    config: Config,
    now: datetime,
    message_id: str | None,
    deadline: datetime,
    clock: Callable[[], datetime],
    replace_asking: bool,
) -> Reply:
    """Намір → частина, що його виконує (маршрутизацією чи вибором під уточненням)."""
    on_case = reply_to is not None and reply_to.kind == "case"
    if intent == "help":
        return Reply(guide_text(access.language(session, store)))
    if intent == "move":
        return cases.move_material(
            session, text, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
        )
    if reply_to is not None and on_case and intent in CASE_ANSWERS:
        return _case_answer(intent, session, reply_to.id, text, ai, store, now, config, deadline, clock)
    if intent == "yes" and reply_to is not None and reply_to.kind == "plan" and reply_to.fingerprint:
        return planning.confirm(
            session, reply_to.id, reply_to.fingerprint, calendar=calendar, store=store, now=now, config=config
        )
    if intent == "edit" and reply_to is not None and reply_to.kind == "plan":
        return planning.edit_plan(
            session, reply_to.id, text, ai=ai, calendar=calendar, store=store, now=now, config=config
        )
    if intent in ("new_task", "plan_week"):
        return planning.start(
            session, text, ai=ai, calendar=calendar, store=store, now=now, config=config,
            week=intent == "plan_week", replace_asking=replace_asking,
        )  # fmt: skip
    if intent == "schedule":
        return planning.schedule.show(session, text, calendar=calendar, now=now, config=config)
    if intent == "tasks":
        return planning.schedule.tasks(calendar=calendar, config=config)
    if intent == "recall":
        return case_recall.recall(session, text, store=store, ai=ai, calendar=calendar, now=now)
    if intent == "work_question":
        return cases.worklog.answer(session, text, store=store, ai=ai, calendar=calendar, now=now)
    if intent == "working_on":
        return cases.worklog.add(session, text, message_id or uuid.uuid4().hex, store=store, now=now)
    if intent == "note":
        return cases.add_note(
            session, text, message_id or uuid.uuid4().hex, ai=ai, store=store, now=now, config=config,
            deadline=deadline, clock=clock,
        )  # fmt: skip
    return Reply(CANNOT_TEXT)


CASE_ANSWERS = ("yes", "no", "not_needed", "case_name")
ALWAYS = (
    "new_task", "plan_week", "note", "move", "working_on", "schedule", "tasks", "work_question", "recall",
)  # fmt: skip
CLARIFY_PATH = "clarify/current"
PHRASES = {
    "new_task": "поставити задачею в календар",
    "note": "записати нотаткою до справи",
    "plan_week": "спланувати тиждень",
    "edit": "змінити показаний план",
    "move": "перекласти матеріал в іншу справу",
    "case_name": "покласти в названу справу",
    "yes": "погодитись",
    "no": "відмовитись",
    "not_needed": "лишити без справи",
    "working_on": "записати, над чим працюєте",
    "schedule": "показати, що вже заплановано",
    "tasks": "показати список задач",
    "work_question": "згадати, що ви робили",
    "recall": "розповісти, що відомо про справу",
}
OPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "option": {"type": ["integer", "null"], "description": "1 чи 2 — варіант, який вибрала мама"}
    },
    "required": ["option"],
}


def allowed(reply_to: ReplyTo | None) -> list[str]:
    """Наміри, на які `handle_message` діє за цього `reply_to` (варіанти уточнення, clarify)."""
    if reply_to is not None and reply_to.kind == "plan":
        return [*ALWAYS, "yes", "edit"]
    if reply_to is not None and reply_to.kind == "case":
        return [*ALWAYS, *CASE_ANSWERS[1:]]
    return list(ALWAYS)


def _clarify(
    session: Session,
    text: str,
    reply_to: ReplyTo | None,
    options: Any,
    *,
    store: Store,
    now: datetime,
    message_id: str | None,
    replace_asking: bool,
) -> Reply:
    """Модель не впевнена: два чинні варіанти → уточнення (нічого не виконано); інакше — як `other`."""
    lawful = allowed(reply_to)
    if not (isinstance(options, list) and len(options) == 2 and options[0] != options[1]):
        return Reply(CANNOT_TEXT)
    if not all(isinstance(o, str) and o in lawful for o in options):
        return Reply(CANNOT_TEXT)
    clarify_id = uuid.uuid4().hex
    store.set(session.account_id, CLARIFY_PATH, {
        "clarify_id": clarify_id, "text": text, "message_id": message_id,
        "reply_to": dataclasses.asdict(reply_to) if reply_to is not None else None,
        "options": list(options), "created": now.isoformat(), "replace_asking": replace_asking,
    })  # fmt: skip
    first, second = (PHRASES[o] for o in options)
    return Reply(
        f"Не зовсім зрозуміла: {first} чи {second}?",
        Question("clarify", clarify_id, None),
        choices=[first, second],
    )


def _chosen(session: Session, clarify_id: str, text: str, *, ai: AI, store: Store) -> dict[str, Any] | None:
    """Слово під уточненням: вибір чинного уточнення (документ видалено) чи `None` — фраза не є вибором."""
    doc = store.get(session.account_id, CLARIFY_PATH)
    if doc is None or doc.get("clarify_id") != clarify_id:
        return None
    prompt = _option_prompt(doc["options"], text)
    option = ai.generate_json("choose_option", prompt, OPTION_SCHEMA).get("option")
    if option not in (1, 2):
        return None
    store.delete(session.account_id, CLARIFY_PATH)
    return doc | {"chosen": doc["options"][option - 1]}


def _option_prompt(options: list[str], text: str) -> str:
    first, second = (PHRASES[o] for o in options)
    return (
        f"Асистент спитав: «{first}» (1) чи «{second}» (2)? option — 1 чи 2, що мама вибрала; "
        f"не вибір — null.\nМама: {text}"
    )


def answer_clarify(
    session: Session,
    clarify_id: str,
    option: int,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    config: Config,
    now: datetime,
    deadline: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Reply:
    """Кнопка під уточненням (clarify): збережений текст іде вибраним наміром; застаріле — «не актуальне»."""
    doc = store.get(session.account_id, CLARIFY_PATH)
    if doc is None or doc.get("clarify_id") != clarify_id or option not in (1, 2):
        return Reply(cases.NOT_ACTUAL)
    store.delete(session.account_id, CLARIFY_PATH)
    return _run_clarified(
        doc | {"chosen": doc["options"][option - 1]}, session, ai=ai, calendar=calendar, store=store,
        config=config, now=now, deadline=deadline, clock=clock,
    )  # fmt: skip


def _run_clarified(
    doc: dict[str, Any],
    session: Session,
    *,
    ai: AI,
    calendar: GoogleWork,
    store: Store,
    config: Config,
    now: datetime,
    deadline: datetime | None,
    clock: Callable[[], datetime] | None,
) -> Reply:
    """Збережений текст — вибраним наміром, зі збереженими `reply_to`, `message_id` і `replace_asking`."""
    saved = doc.get("reply_to")
    return _dispatch(
        doc["chosen"], session, doc["text"], Question(**saved) if saved else None, ai=ai, calendar=calendar,
        store=store, config=config, now=now, message_id=doc.get("message_id"),
        deadline=deadline or now + timedelta(seconds=config.request_timeout_s - 2 * config.call_timeout_s),
        clock=clock or (lambda: now), replace_asking=bool(doc.get("replace_asking")),
    )  # fmt: skip


SHORT_ANSWERS: dict[str, Callable[..., Reply | None]] = {
    "duration": planning.try_answer_duration,
    "when": planning.try_answer_when,
    "priorities": planning.try_answer_priorities,
    "limits": planning.try_answer_limits,
}
"""Відповіді на короткі питання плану; `None` — фраза не є відповіддю й маршрутизується як нова
(stuck-question)."""


def route_schema(reply_to: ReplyTo | None) -> dict[str, Any]:
    """Схема маршрутизації для цього `reply_to`: відповіді на питання справ (`no`, `not_needed`,
    `case_name`) — лише під питанням справ, щоб модель не вибирала їх деінде
    («ну не знаю» під планом — `other`)."""
    intents = ROUTE_SCHEMA["properties"]["intent"]["enum"]
    if reply_to is None or reply_to.kind != "case":
        intents = [i for i in intents if i not in CASE_ANSWERS[1:]]
    options = {"type": "array", "items": {"type": "string", "enum": allowed(reply_to)}}
    return {**ROUTE_SCHEMA, "properties": {"intent": {"type": "string", "enum": intents}, "options": options}}


def _case_answer(
    intent: str,
    session: Session,
    material_id: str,
    text: str,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Відповідь на питання справ (S3): «так», «ні», «не треба», назва справи."""
    if intent == "no":
        return cases.decline_case(session, material_id, store=store)
    if intent == "not_needed":
        return cases.leave_without_case(session, material_id, store=store)
    if intent == "case_name":
        return cases.choose_case(
            session,
            material_id,
            text,
            ai=ai,
            store=store,
            now=now,
            config=config,
            deadline=deadline,
            clock=clock,
        )
    return cases.confirm_case(
        session, material_id, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
    )


def _route_prompt(
    text: str, reply_to: ReplyTo | None, titles: list[str] | None = None, asked_question: str | None = None
) -> str:
    """Підказка маршрутизації; задачі показаного плану — щоб відрізнити правку від нової задачі; питання
    справ — те, що матеріал має зараз, і наміри відповіді на нього."""
    if reply_to is not None and reply_to.kind == "case":
        asked = (
            f"Асистент спитав «{asked_question or ''}». Відповідь на це питання: yes — погоджується; "
            "no — «ні», не цю справу (без назви іншої); not_needed — «не треба», без справи; "
            "case_name — називає справу («до Коха», «в город», «ні, до Коха», «це не нова, це до X» — теж "
            "case_name, не move). "
        )
    else:
        asked = "Асистент щойно запропонував план і спитав «Записати?». " if reply_to is not None else ""
        asked += "Тут не буває no, not_needed, case_name — це лише відповіді на питання про справу. "
    listed = f"У плані задачі: {'; '.join(titles)}. " if titles else ""
    return (
        f"{asked}{listed}Мама сказала: «{text}». Визнач intent: "
        "yes — вона лише погоджується (з планом чи з питанням асистента), нічого не змінюючи; фраза, що "
        "називає задачу з плану з днем чи годиною («лікар о десятій у середу»), — edit, не yes; "
        "new_task — нова задача, якої в плані ще немає; фраза зі «ще», «і ще», «додай», «треба ще» — "
        "new_task, якщо мама не просить спланувати тиждень; "
        "schedule — мама питає, що в неї вже заплановано («які плани на сьогодні?», «що в мене на тиждень?», "
        "«що в мене завтра?»); "
        "tasks — мама питає про свої задачі чи список справ без періоду («які в мене задачі?», "
        "«що в списку справ?», «покажи задачі»); з періодом («на сьогодні», «на тиждень») — schedule; "
        "нова задача — new_task; «список справ» тут — задачі, не recall (не про справу-людину); "
        "plan_week — лише коли просить спланувати («сплануй тиждень», «давай планувати»), навіть з "
        "задачами в тій самій фразі; "
        "edit — мама просить змінити показаний план, тобто задачу, яка вже в ньому є (названу хоч одним "
        "словом з її назви): перенести на інший день чи годину (і коротко: «перукар о дев'ятій у п'ятницю», "
        "«аптека на вівторок»), не раніше якоїсь години, прибрати («прибери …», «… не треба»), без часу; "
        "note — мама просить записати чи запам'ятати відомості про людину чи справу (нотатка), а не задачу в "
        "календар («запиши до …», «запам'ятай, що …»); "
        "working_on — мама каже, над чим зараз працює чи що робить («зараз працюю над …», «я зараз роблю …», "
        "«сиджу над …»); це не нотатка про людину і не задача на потім; "
        "work_question — мама питає, що вона робила чи над чим працювала («що я робила з договором?», "
        "«над чим я працювала вчора?»); це не schedule (заплановане в календарі); "
        "recall — мама питає, що відомо про людину чи справу («що ми знаємо про пані Шмідт?», «що вже "
        "з'ясували по городу?», «нагадай про пана Коха»); це не note (вона нічого не просить записати) і не "
        "work_question (питає про справу, не про свою роботу); "
        "help — мама питає, що вміє асистент чи як з ним працювати («що ти вмієш?», «як з тобою працювати?», "
        "«допоможи»); "
        "unsure — фраза справді двозначна між двома наміри (наприклад нотатка про людину з дією — note чи "
        "new_task); тоді options — два найімовірніші; коли впевнена — не unsure; "
        "«пан/пані X просив(ла) …», «у X треба …» — і відомість про людину, і справа: "
        "unsure з note і new_task; "
        "«ну не знаю», «не знаю», «хм» — other, не unsure (unsure — лише між двома конкретними намірами); "
        "move — мама просить перекласти вже внесений матеріал (нотатку, фото, документ) в іншу справу "
        "(«переклади …», «це не до X, а до Y»); «нотатку про X перенеси в Y» — теж move: це матеріал, не "
        "задача плану; «перенеси <задачу з плану> на …» під планом — edit; "
        "other — щось інше."
    )


@dataclass(frozen=True)
class OpenQuestions:
    replies: list[Reply]
    login_needed: bool
    failed: list[str] = field(default_factory=list)
    """Назви джерел, що впали; `http` пише за кожне рядок у журнал."""


def open_questions(
    session: Session,
    *,
    calendar: Callable[[], GoogleWork],
    store: Store,
    now: datetime,
    config: Config,
) -> OpenQuestions:
    """Незакриті питання на відкритті: гайд першого відкриття й питання справ (F3 S3).

    Планування на вступі немає (calm-open, слово власника 2026-11-13): `calendar` і `config` не
    використовуються, `login_needed` — `False`.

    Помилка джерела не забирає інших: джерело пропускається й називається у `failed`. Відповіді без питання
    («увійди знову», «немає вільного часу») — перед питанням, не рахуються; з питань показується одне
    найновіше (останнім, щоб `reply_to` взявся з нього), до його тексту — «Ще N питань чекають.»."""
    plain: list[Reply] = []
    asked: list[tuple[datetime, Reply]] = []
    login_needed = False
    failed: list[str] = []
    guide = _first_open_guide(session, store, now, failed)
    if guide is not None:
        plain.append(guide)
    try:
        asked += [(item.at, item.reply) for item in cases.open_questions(session, store)]
    except Exception:
        failed.append("cases")
    return OpenQuestions(plain + _newest(asked), login_needed, failed)


def _first_open_guide(session: Session, store: Store, now: datetime, failed: list[str]) -> Reply | None:
    """Гайд на першому відкритті після F5 (позначка `settings/guide_shown`): помилка читання — без гайду;
    помилка запису — гайд є (і з'явиться знову); обидві — `"guide"` у `failed`."""
    try:
        shown = store.get(session.account_id, GUIDE_PATH)
    except Exception:
        failed.append("guide")
        return None
    if shown is not None:
        return None
    try:
        store.set(session.account_id, GUIDE_PATH, {"shown": now.isoformat()})
    except Exception:
        failed.append("guide")
    return Reply(guide_text(access.language(session, store)))


def _newest(asked: list[tuple[datetime, Reply]]) -> list[Reply]:
    """Одне найновіше питання; решта — рядок «Ще N …» у його тексті."""
    if not asked:
        return []
    _, newest = max(enumerate(asked), key=lambda pair: (pair[1][0], pair[0]))[1]
    rest = len(asked) - 1
    if rest == 0:
        return [newest]
    return [dataclasses.replace(newest, text=f"{newest.text}\n{_waiting(rest)}")]


def _waiting(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"Ще {n} питання чекає."
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"Ще {n} питання чекають."
    return f"Ще {n} питань чекають."
