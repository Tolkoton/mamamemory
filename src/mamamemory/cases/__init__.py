"""Справи (F3 S1 note-to-case): матеріали, Розкладач, опис справи, «створити справу?».

Без FastAPI. Залежності — параметрами. Усе під акаунтом: `cases/{case_id}`, `materials/{material_id}`.
Не робить: фото й файлів (S2), «ні» / «не треба» й незакритих питань (S3), «перекласти» (S4), відповідей (F4).
"""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from mamamemory.access import Session
from mamamemory.cases import worklog as worklog  # журнал роботи (F4) — `cases.worklog`
from mamamemory.config import Config
from mamamemory.integrations.ai import AI, DeadlinePassed
from mamamemory.integrations.files import Files
from mamamemory.integrations.store import Store
from mamamemory.replies import Question, Reply

MaterialKind = Literal["note", "photo", "file"]
MaterialState = Literal["new", "placed", "pending", "unplaced"]

CASES = "cases"
MATERIALS = "materials"
NOT_UNDERSTOOD = "Не зрозуміла, до якої справи це. Скажіть з іменем чи назвою."
NOT_ACTUAL = "Це питання вже не актуальне."
NOT_WHAT = "Не зрозуміла, що саме перекласти. Скажіть, що це і куди."
NOT_WHERE = "Не зрозуміла, куди перекласти. Скажіть, у яку справу."
MOVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "material": {"type": ["integer", "null"], "description": "номер матеріалу з каталогу"},
        "case": {"type": ["integer", "null"], "description": "номер справи-адресата з каталогу"},
        "new_case": {"type": ["string", "null"], "description": "назва нової справи, якщо її немає"},
    },
    "required": ["material", "case", "new_case"],
}
ASK_WHICH = "У яку справу покласти?"
LEFT_WITHOUT_CASE = "Гаразд, лишила без справи."
FAILED = "Не вдалося, спробуйте ще раз."
NO_TEXT = "(без тексту)"
READ_PROMPT = (
    "Перепиши дослівно весь текст із цього фото чи документа (назви, значення, дати, імена), без коментарів. "
    "Якщо тексту немає — коротко опиши, що на фото."
)
READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "number": {
            "type": ["integer", "null"],
            "description": "номер справи з каталогу, якщо матеріал про неї",
        },
        "new_name": {
            "type": ["string", "null"],
            "description": "назва нової справи, якщо такої в каталозі немає",
        },
    },
    "required": ["number", "new_name"],
}
NAME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": ["string", "null"], "description": "ім'я людини чи назва проєкту"}},
    "required": ["name"],
}
DESCRIBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"description": {"type": "string"}},
    "required": ["description"],
}


@dataclass(frozen=True)
class Material:
    material_id: str
    kind: MaterialKind
    text: str
    state: MaterialState
    case_id: str | None
    pending_case: str | None
    gs_uri: str | None
    mime: str | None
    created: datetime
    in_description: bool
    asked: Literal["create", "which"] | None = None
    """Яке питання справ поставлено матеріалу в `pending` (S3): «Створити справу?» чи «У яку справу?»."""


@dataclass(frozen=True)
class Case:
    case_id: str
    name: str
    description: str
    created: datetime
    stale: bool = False
    """Опис треба перебудувати з усіх текстів справи (обірваний переклад, S4)."""


def placed_text(name: str) -> str:
    return f"Поклала в «{name}»."


def ask_text(name: str) -> str:
    return f"Створити справу «{name}»?"


def add_note(
    session: Session,
    text: str,
    message_id: str,
    *,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow: матеріал уже є → дороблення за станом; немає → записати (`new`) до будь-якої моделі →
    Розкладач."""
    existing = _material(session, store, message_id)
    if existing is None:
        material = Material(message_id, "note", text, "new", None, None, None, None, now, False)
        _save_material(session, store, material)
        return place(
            session, material, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
        )
    if existing.state == "new":
        return place(
            session, existing, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
        )
    return _finish_placed(session, existing, ai=ai, store=store, deadline=deadline, clock=clock)


def add_file(
    session: Session,
    material_id: str,
    data: bytes | None,
    mime: str | None,
    *,
    ai: AI,
    files: Files,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow: оригінал у сховище → матеріал (`new`, текст порожній) → текст (Flash-Lite з `gs://`,
    `text/plain` — сам) → Розкладач; повтор того самого id (з тілом чи лише заголовком) дороблює без нового
    `files.put`."""
    existing = _material(session, store, material_id)
    if existing is not None and existing.kind == "note":
        material_id = f"{material_id}-file"
        existing = _material(session, store, material_id)
    if existing is None:
        if data is None or mime is None:
            return Reply(FAILED)
        existing = _stored_file(
            session, material_id, data, _plain_type(mime), files=files, store=store, now=now
        )
    material = existing
    if material.text == "":
        material = dataclasses.replace(
            material, text=_file_text(material, data, ai=ai, deadline=deadline, clock=clock)
        )
        _save_material(session, store, material)
    if material.state == "new":
        return place(
            session, material, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
        )
    return _finish_placed(session, material, ai=ai, store=store, deadline=deadline, clock=clock)


def _stored_file(
    session: Session, material_id: str, data: bytes, mime: str, *, files: Files, store: Store, now: datetime
) -> Material:
    """Оригінал у сховище, потім матеріал з посиланням на нього (повтор перезаписує той самий об'єкт)."""
    gs_uri = files.put(session.account_id, material_id, data, mime)
    kind: MaterialKind = "photo" if mime.startswith("image/") else "file"
    text = _plain_text(data) if mime == "text/plain" else ""
    material = Material(material_id, kind, text, "new", None, None, gs_uri, mime, now, False)
    _save_material(session, store, material)
    return material


def _file_text(
    material: Material, data: bytes | None, *, ai: AI, deadline: datetime, clock: Callable[[], datetime]
) -> str:
    """`text/plain` — сам вміст тіла; інше — Flash-Lite `read_file` з `gs://`; порожньо — «(без тексту)»."""
    if material.mime == "text/plain":
        if data is None:
            raise LookupError("text/plain without a body to read")
        text = _plain_text(data)
    else:
        _check(deadline, clock)
        answer = ai.generate_json_with_file(
            "read_file", READ_PROMPT, READ_SCHEMA, str(material.gs_uri), str(material.mime)
        )
        read = answer.get("text")
        text = read if isinstance(read, str) else ""
    return text.strip() or NO_TEXT


def _plain_text(data: bytes) -> str:
    """`text/plain` — сам вміст (utf-8 із заміною неправильних байтів); записується разом із матеріалом, тож
    повтор лише заголовком ніколи не лишається без тексту."""
    return data.decode("utf-8", errors="replace").strip() or NO_TEXT


def _plain_type(mime: str) -> str:
    return mime.split(";", 1)[0].strip().lower()


def place(
    session: Session,
    material: Material,
    *,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow: каталог порожній → назва нової справи; інакше Розкладач за номером → справа, питання чи
    «не зрозуміла»."""
    known = catalogue(session, store)
    if not known:
        _check(deadline, clock)
        name = _name(ai.generate_json("name_case", _name_prompt(material.text), NAME_SCHEMA).get("name"))
        return _decided(session, store, material, None, name)
    _check(deadline, clock)
    answer = ai.generate_json("classify_case", _classify_prompt(known, material.text), CLASSIFY_SCHEMA)
    number = answer.get("number")
    chosen = known[number - 1] if isinstance(number, int) and 1 <= number <= len(known) else None
    reply = _decided(session, store, material, chosen, _name(answer.get("new_name")))
    if chosen is None:
        return reply
    return _finish_placed(
        session,
        _required(session, store, material.material_id),
        ai=ai,
        store=store,
        deadline=deadline,
        clock=clock,
    )


def confirm_case(
    session: Session,
    material_id: str,
    *,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow: «так» на «Створити справу «X»?» → справа (id від матеріалу; наявна з тією назвою — вона) →
    матеріал у ній → опис; уже покладений — дороблення опису."""
    material = _material(session, store, material_id)
    if material is None or material.state in ("new", "unplaced"):
        return Reply(NOT_ACTUAL)
    if material.state == "pending" and material.asked == "which":
        return _question(material)
    if material.state == "pending":
        target = _case_for(session, store, str(material.pending_case), material_id, now)
        material = dataclasses.replace(
            material, state="placed", case_id=target.case_id, pending_case=None, asked=None
        )
        _save_material(session, store, material)
    return _finish_placed(session, material, ai=ai, store=store, deadline=deadline, clock=clock)


@dataclass(frozen=True)
class CaseQuestion:
    """Незакрите питання справ одного матеріалу (S3) і його час для вибору найновішого."""

    reply: Reply
    at: datetime


def decline_case(session: Session, material_id: str, *, store: Store) -> Reply:
    """«Ні» на «Створити справу «X»?» → «У яку справу покласти?» (S3)."""
    material = _pending(session, store, material_id)
    if material is None:
        return Reply(NOT_ACTUAL)
    asked = dataclasses.replace(material, asked="which")
    _save_material(session, store, asked)
    return _question(asked)


def leave_without_case(session: Session, material_id: str, *, store: Store) -> Reply:
    """«Не треба» → матеріал без справи, нічого не видаляється (S3)."""
    material = _pending(session, store, material_id)
    if material is None:
        return Reply(NOT_ACTUAL)
    _save_material(
        session, store, dataclasses.replace(material, state="unplaced", pending_case=None, asked=None)
    )
    return Reply(LEFT_WITHOUT_CASE)


def choose_case(
    session: Session,
    material_id: str,
    text: str,
    *,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow: назва справи у відповідь на питання справ (S3): каталог порожній → назва нової справи; інакше
    Розкладач за номером → туди; нова назва → «Створити справу «Y»?» (та сама на «Створити…» — як «так»)."""
    material = _pending(session, store, material_id)
    if material is None:
        return Reply(NOT_ACTUAL)
    known = catalogue(session, store)
    _check(deadline, clock)
    if not known:
        named = _name(ai.generate_json("name_case", _name_prompt(text), NAME_SCHEMA).get("name"))
        return (
            _ask_create(session, store, material, named)
            if named
            else Reply(ASK_WHICH, _question(material).question)
        )
    answer = ai.generate_json("classify_case", _classify_prompt(known, text), CLASSIFY_SCHEMA)
    number = answer.get("number")
    if isinstance(number, int) and 1 <= number <= len(known):
        placed = dataclasses.replace(
            material, state="placed", case_id=known[number - 1].case_id, pending_case=None, asked=None
        )
        _save_material(session, store, placed)
        return _finish_placed(session, placed, ai=ai, store=store, deadline=deadline, clock=clock)
    new_name = _name(answer.get("new_name"))
    if new_name is None:
        return Reply(ASK_WHICH, _question(material).question)
    same = material.asked == "create" and new_name.casefold() == str(material.pending_case).casefold()
    if same:
        return confirm_case(
            session, material_id, ai=ai, store=store, now=now, config=config, deadline=deadline, clock=clock
        )
    return _ask_create(session, store, material, new_name)


def open_questions(session: Session, store: Store) -> list[CaseQuestion]:
    """По одному питанню на кожен матеріал у `pending` (S3), з часом матеріалу."""
    return [CaseQuestion(_question(m), m.created) for m in pending(session, store)]


def _pending(session: Session, store: Store, material_id: str) -> Material | None:
    material = _material(session, store, material_id)
    return material if material is not None and material.state == "pending" else None


def _ask_create(session: Session, store: Store, material: Material, name: str) -> Reply:
    asked = dataclasses.replace(material, pending_case=name, asked="create")
    _save_material(session, store, asked)
    return _question(asked)


def describe(
    session: Session,
    case_id: str,
    materials: list[Material],
    *,
    ai: AI,
    store: Store,
    deadline: datetime,
    clock: Callable[[], datetime],
    fresh: bool = False,
) -> None:
    """Опис справи (3.8 Flash `describe_case`): старий опис + тексти матеріалів → новий опис; матеріали —
    в описі."""
    case = _case(session, store, case_id)
    _check(deadline, clock)
    old = dataclasses.replace(case, description="") if fresh else case
    answer = ai.generate_json("describe_case", _describe_prompt(old, materials), DESCRIBE_SCHEMA)
    description = answer.get("description")
    if not isinstance(description, str):
        raise ValueError("describe_case gave no description")
    _save_case(session, store, dataclasses.replace(case, description=description))
    for material in materials:
        _save_material(session, store, dataclasses.replace(material, in_description=True))


def move_material(
    session: Session,
    text: str,
    *,
    ai: AI,
    store: Store,
    now: datetime,
    config: Config,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Flow (S4): дороблення обірваного → вибір матеріалу й справи (3.8 Flash `choose_material`) →
    «Це вже в…»,
    перенесення з описами адресата й джерела чи питання про нову справу."""
    _finish_unfinished(session, store, ai=ai, deadline=deadline, clock=clock)
    movable = [m for m in materials_catalogue(session, store) if m.state != "new"]
    known = catalogue(session, store)
    _check(deadline, clock)
    answer = ai.generate_json("choose_material", _move_prompt(movable, known, text), MOVE_SCHEMA)
    material = _numbered(movable, answer.get("material"))
    if material is None:
        return Reply(NOT_WHAT)
    target = _numbered(known, answer.get("case"))
    new_name = _name(answer.get("new_case"))
    if target is None and new_name is not None:
        target = next((c for c in known if c.name.casefold() == new_name.casefold()), None)
    if target is None and new_name is None:
        return Reply(NOT_WHERE)
    if target is not None and target.case_id == material.case_id:
        return Reply(f"Це вже в «{target.name}».")
    if target is None:
        return _move_out(session, store, material, str(new_name), ai=ai, deadline=deadline, clock=clock)
    return _move_into(session, store, material, target, ai=ai, deadline=deadline, clock=clock)


def _move_into(
    session: Session,
    store: Store,
    material: Material,
    target: Case,
    *,
    ai: AI,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Крок 4: джерело — `stale`; матеріал — в адресаті; опис адресата одним матеріалом; джерело — заново."""
    source = material.case_id
    _mark_stale(session, store, source)
    moved = dataclasses.replace(
        material, state="placed", case_id=target.case_id, pending_case=None, asked=None, in_description=False
    )
    _save_material(session, store, moved)
    describe(session, target.case_id, [moved], ai=ai, store=store, deadline=deadline, clock=clock)
    _rebuild(session, store, source, ai=ai, deadline=deadline, clock=clock)
    return Reply(f"Переклала «{_first_words(material.text)}» у «{target.name}».")


def _move_out(
    session: Session,
    store: Store,
    material: Material,
    name: str,
    *,
    ai: AI,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Крок 5: матеріал виходить зі справи й чекає «так» на нову назву; джерело — заново."""
    source = material.case_id
    _mark_stale(session, store, source)
    waiting = dataclasses.replace(
        material, state="pending", case_id=None, pending_case=name, asked="create", in_description=False
    )
    _save_material(session, store, waiting)
    _rebuild(session, store, source, ai=ai, deadline=deadline, clock=clock)
    return _question(waiting)


def _finish_unfinished(
    session: Session, store: Store, *, ai: AI, deadline: datetime, clock: Callable[[], datetime]
) -> None:
    """Крок 1: недописані адресати (покладений без опису) і `stale`-джерела обірваного перекладу."""
    for material in materials_catalogue(session, store):
        if material.state == "placed" and material.case_id is not None and not material.in_description:
            describe(
                session, material.case_id, [material], ai=ai, store=store, deadline=deadline, clock=clock
            )
    for case in catalogue(session, store):
        if case.stale:
            _rebuild(session, store, case.case_id, ai=ai, deadline=deadline, clock=clock)


def _rebuild(
    session: Session,
    store: Store,
    case_id: str | None,
    *,
    ai: AI,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> None:
    """Опис справи заново з її поточних матеріалів (без старого опису); порожня — порожній опис без моделі."""
    if case_id is None:
        return
    left = texts(session, case_id, store)
    if left:
        describe(session, case_id, left, ai=ai, store=store, deadline=deadline, clock=clock, fresh=True)
    else:
        _save_case(session, store, dataclasses.replace(_case(session, store, case_id), description=""))
    _save_case(session, store, dataclasses.replace(_case(session, store, case_id), stale=False))


def _mark_stale(session: Session, store: Store, case_id: str | None) -> None:
    if case_id is not None:
        _save_case(session, store, dataclasses.replace(_case(session, store, case_id), stale=True))


def _numbered(items: list[Any], number: Any) -> Any:
    return items[number - 1] if isinstance(number, int) and 1 <= number <= len(items) else None


def _first_words(text: str) -> str:
    return text if len(text) <= 40 else text[:40].rstrip() + "…"


def _move_prompt(movable: list[Material], known: list[Case], text: str) -> str:
    names = {c.case_id: c.name for c in known}
    kinds = {"note": "нотатка", "photo": "фото", "file": "документ"}
    materials = "\n".join(
        f"{n}. {m.created:%Y-%m-%d} — "
        f"{'справа «' + names[m.case_id] + '»' if m.case_id in names else 'без справи'} — "
        f"{kinds[m.kind]} — {m.text[:80]}"
        for n, m in enumerate(movable, start=1)
    )
    cases_listed = "\n".join(f"{n}. {c.name} — {c.description}" for n, c in enumerate(known, start=1))
    return (
        "Мама просить перекласти вже внесений матеріал в іншу справу.\n"
        f"Матеріали (номер. дата — справа — вид — початок тексту):\n{materials}\n"
        f"Справи (номер. назва — опис):\n{cases_listed}\n"
        "material — номер матеріалу, про який мама говорить (за змістом, не обов'язково останній), "
        "інакше null; "
        "case — номер справи, куди перекласти, інакше null; new_case — назва нової справи, якщо такої в "
        "каталозі немає, інакше null.\n"
        f"Мама: {text}"
    )


def pending_name(session: Session, store: Store, material_id: str) -> str | None:
    """Назва справи, про яку питає «Створити справу «X»?» цього матеріалу (для підказки маршрутизації)."""
    material = _material(session, store, material_id)
    return material.pending_case if material is not None and material.state == "pending" else None


def asked_text(session: Session, store: Store, material_id: str) -> str | None:
    """Текст питання, яке матеріал має зараз (для підказки маршрутизації S3); не `pending` — None."""
    material = _material(session, store, material_id)
    if material is None or material.state != "pending":
        return None
    return _question(material).text


def _question(material: Material) -> Reply:
    """Питання справ матеріалу в `pending` за `asked`."""
    text = ASK_WHICH if material.asked == "which" else ask_text(str(material.pending_case))
    return Reply(text, Question("case", material.material_id, None))


def catalogue(session: Session, store: Store) -> list[Case]:
    """Справи акаунта в порядку створення — каталог Розкладача."""
    found = [_case_from(i, d) for i, d in store.list(session.account_id, CASES)]
    return sorted(found, key=lambda c: (c.created, c.case_id))


def pending(session: Session, store: Store) -> list[Material]:
    """Матеріали, що чекають «так» на «Створити справу?», від найновішого."""
    waiting = [m for m in materials_catalogue(session, store) if m.state == "pending"]
    return sorted(waiting, key=lambda m: m.created, reverse=True)


def materials_catalogue(session: Session, store: Store) -> list[Material]:
    found = [_material_from(i, d) for i, d in store.list(session.account_id, MATERIALS)]
    return sorted(found, key=lambda m: (m.created, m.material_id))


def texts(session: Session, case_id: str, store: Store) -> list[Material]:
    return [m for m in materials_catalogue(session, store) if m.case_id == case_id]


# ------------------------------------------------------------------ steps


def _decided(
    session: Session, store: Store, material: Material, chosen: Case | None, new_name: str | None
) -> Reply:
    """Відповідь Розкладача записується в матеріал: справа, питання про нову чи «не зрозуміла»."""
    if chosen is not None:
        _save_material(session, store, dataclasses.replace(material, state="placed", case_id=chosen.case_id))
        return Reply(placed_text(chosen.name))
    if new_name is not None:
        asked = dataclasses.replace(material, state="pending", pending_case=new_name, asked="create")
        _save_material(session, store, asked)
        return _question(asked)
    _save_material(session, store, dataclasses.replace(material, state="unplaced"))
    return Reply(NOT_UNDERSTOOD)


def _finish_placed(
    session: Session,
    material: Material,
    *,
    ai: AI,
    store: Store,
    deadline: datetime,
    clock: Callable[[], datetime],
) -> Reply:
    """Відповідь за станом; покладений без опису — спершу опис."""
    if material.state == "pending":
        return _question(material)
    if material.state != "placed" or material.case_id is None:
        return Reply(NOT_UNDERSTOOD)
    if not material.in_description:
        describe(session, material.case_id, [material], ai=ai, store=store, deadline=deadline, clock=clock)
    return Reply(placed_text(_case(session, store, material.case_id).name))


def _case_for(session: Session, store: Store, name: str, material_id: str, now: datetime) -> Case:
    """Наявна справа з цією назвою (без різниці регістру) чи нова з id від матеріалу."""
    for case in catalogue(session, store):
        if case.name.casefold() == name.casefold():
            return case
    case = Case(f"c-{material_id}", name, "", now)
    _save_case(session, store, case)
    return case


def _check(deadline: datetime, clock: Callable[[], datetime]) -> None:
    if clock() >= deadline:
        raise DeadlinePassed("no time left for the model call")


def _name(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# ------------------------------------------------------------------ store


def _material(session: Session, store: Store, material_id: str) -> Material | None:
    data = store.get(session.account_id, f"{MATERIALS}/{material_id}")
    return _material_from(material_id, data) if data is not None else None


def _required(session: Session, store: Store, material_id: str) -> Material:
    material = _material(session, store, material_id)
    if material is None:
        raise LookupError("material vanished")
    return material


def _case(session: Session, store: Store, case_id: str) -> Case:
    data = store.get(session.account_id, f"{CASES}/{case_id}")
    if data is None:
        raise LookupError("case vanished")
    return _case_from(case_id, data)


def _save_material(session: Session, store: Store, material: Material) -> None:
    data = dataclasses.asdict(material) | {"created": material.created.isoformat()}
    del data["material_id"]
    store.set(session.account_id, f"{MATERIALS}/{material.material_id}", data)


def _save_case(session: Session, store: Store, case: Case) -> None:
    data = {
        "name": case.name,
        "description": case.description,
        "created": case.created.isoformat(),
        "stale": case.stale,
    }
    store.set(session.account_id, f"{CASES}/{case.case_id}", data)


def _material_from(material_id: str, data: dict[str, Any]) -> Material:
    return Material(
        material_id,
        data["kind"],
        data["text"],
        data["state"],
        data.get("case_id"),
        data.get("pending_case"),
        data.get("gs_uri"),
        data.get("mime"),
        datetime.fromisoformat(data["created"]),
        bool(data.get("in_description")),
        data.get("asked") or ("create" if data["state"] == "pending" else None),
    )


def _case_from(case_id: str, data: dict[str, Any]) -> Case:
    return Case(
        case_id,
        data["name"],
        data.get("description", ""),
        datetime.fromisoformat(data["created"]),
        bool(data.get("stale")),
    )


# ------------------------------------------------------------------ prompts


def _classify_prompt(known: list[Case], text: str) -> str:
    listed = "\n".join(f"{n}. {c.name} — {c.description}" for n, c in enumerate(known, start=1))
    return (
        "Мама веде справи — пацієнтів і проєкти. Ось каталог справ (номер. назва — опис):\n"
        f"{listed}\n"
        "До якої справи належить новий матеріал? number — номер справи з каталогу, якщо матеріал про неї "
        "(те саме прізвище чи проєкт, зокрема в іншому відмінку), інакше null; new_name — коротка назва "
        "нової справи (ім'я людини з «пан/пані», якщо так сказано, чи назва проєкту), якщо в каталозі "
        "такої немає, інакше null.\n"
        f"Матеріал: {text}"
    )


def _name_prompt(text: str) -> str:
    return (
        "Мама записує матеріал до справи — пацієнта чи проєкту. name — коротка назва справи (ім'я людини з "
        "«пан/пані», якщо так сказано, чи назва проєкту), про яку цей матеріал; не зрозуміло — null.\n"
        f"Матеріал: {text}"
    )


def _describe_prompt(case: Case, materials: list[Material]) -> str:
    added = "\n".join(f"- {m.text}" for m in materials)
    return (
        f"Справа «{case.name}». Її теперішній опис: {case.description or '(порожньо)'}\n"
        f"Нові матеріали:\n{added}\n"
        "description — новий короткий опис справи: хто це чи що це, і головні відомості з усіх матеріалів, "
        "щоб за ним можна було впізнати справу серед схожих."
    )
