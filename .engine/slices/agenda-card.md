# Slice agenda-card — поправка F2 за словом власника 2026-11-15 — planning artifact

## Goal
Власник, 2026-11-15: «А можна щоб календар і таскс виводились віджетом?», на вибір варіантів — «Ок 2 варіант .
Показувати коди питають»: картка в застосунку, у відповідь на питання. Зараз «які плани …» (show-schedule, calm-open)
і «які в мене задачі?» (tasks-list) — суцільний текст абзацом. Треба: та сама відповідь показується карткою — заголовок,
розділи (дні тижня / «Задачі без часу»), рядки з часом окремою колонкою; 🔊 читає той самий текст, що й зараз. Вимірний
сигнал: тести; прохід власника на телефоні.

## Premise verified
- `planning.schedule.show` і `planning.schedule.tasks` будують текст з подій (`AgendaItem`) і задач (`TaskItem`) —
  код show-schedule, calm-open, tasks-list (ревізія `mamamemory-00038-mn6`).
- `Reply` віддається як JSON `_reply_json` (`dataclasses.asdict`), поле `choices` прибирається, коли `None`
  (clarify) — той самий прийом для нового поля.
- Сторінка малює відповідь `renderText` (`<p>` з `textContent`) і 🔊 з тим самим текстом (`app.js`).

## Out of scope (deliberately)
- показ картки на відкритті (власник: «показувати коли питають»);
- віджет на головному екрані телефону;
- тексти відповідей (`Reply.text`) — без змін (🔊 і всі запечатані тести тексту);
- інші відповіді (план для підтвердження, справи) — без картки.

## Seam (contract)
- `replies.py`: `CardItem(time: str | None, text: str, note: str | None = None)`, `CardSection(heading: str | None,
  items: list[CardItem])`, `Card(title: str, sections: list[CardSection])` (frozen dataclasses); `Reply` дістає поле
  `card: Card | None = None`.
- `http._reply_json`: `card` — `None` прибирається з JSON (як `choices`); інакше — `{"title", "sections": [{"heading",
  "items": [{"time", "text", "note"}]}]}`.
- `schedule.show`: `Reply.text` — як було; `card` — є, коли є хоч одна подія чи задача:
  `title` = `HEADERS[kind]` («На сьогодні» …); розділи подій: для `week` / `next_week` — один на день з подіями,
  `heading` «Понеділок, 16 листопада» (як рядок дня в тексті, без двокрапки), для `today` / `tomorrow` — один розділ з
  `heading` `None`; кожна подія — `CardItem(time="14:00" | "весь день", text=назва)` у порядку тексту; задачі з датою в
  періоді — розділ `heading` «Задачі без часу», `CardItem(time=None, text=назва)`. Немає ні подій, ні задач — `card`
  `None`. Подій немає, задачі є — перший розділ `heading` `None` з одним рядком `CardItem(None, "В календарі нічого
  немає.")`, далі розділ задач.
- `schedule.tasks`: є задачі — `card` `Card(title="Задачі в списку", sections=[CardSection(None, [CardItem(None, назва,
  note="до 13 листопада" | None) …])])` у порядку списку; інакше (`немає`, `вимкнено`, збій) — `card` `None`.
- Новий модуль `web/card.js`: `buildCard(card, make)` — `make(tag, className, text)` створює елемент (`text` — через
  `textContent`) і повертає об'єкт з `append(child)`; результат — корінь `div.card`: `h3` заголовок, на кожен розділ —
  `h4.card-heading` (лише коли `heading` не порожній) і `ul`, на кожен рядок — `li` з `span.card-time` (лише коли `time`),
  `span.card-text`, `span.card-note` (лише коли `note`). Порядок — як у `card`.
- `app.js` `show(reply)`: `reply.card` є — замість абзацу тексту в розмову йде `buildCard(reply.card, make)` (на
  `document.createElement`), далі 🔊 з `reply.text`, як було; немає — як було. Маршрут `/card.js` (`_script`).
- `index.html`: стилі `.card` (рамка, білий фон), `.card-time` (жирна колонка ліворуч), `.card-note` (сірий).
- Does NOT do: картки на відкритті, змін тексту відповідей, картки для інших відповідей.

## Decisions (with WHY)
- Q1: Сервер віддає структуру картки, сторінка лише малює. Чому: сервер уже знає події, дні й задачі; розбирати текст
  на сторінці — крихко. Rejected: сторінка розбирає `reply.text` за рядками «•» — найсильніше за: жодної зміни сервера;
  але залежить від формату тексту (зламається від будь-якої правки слова).
- Q2: `buildCard` з фабрикою `make`, не DOM прямо. Чому: перевіряється в `node --test` без браузера.

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: картка розкладу** — фейковий календар: сьогодні дві події (одна на весь день) і задача з датою → `title`
  «На сьогодні», розділ без заголовка з двома рядками («весь день», «14:00») у порядку тексту, розділ «Задачі без часу»;
  тиждень — розділ на кожен день з подіями з заголовком дня; нічого немає — `card` `None`, текст як було; лише задачі —
  рядок «В календарі нічого немає.» і розділ задач. `Reply.text` — без змін: запечатані тести тексту
  (`tests/test_show_schedule*.py`, `tests/test_calm_open.py`, `tests/test_tasks_list*.py`) зелені без правок.
- **Seam 2: картка задач** — задачі з датою й без → `note` «до 13 листопада» лише в задачі з датою; немає / вимкнено /
  збій — `card` `None`.
- **Seam 3: JSON** — відповідь без картки: ключа `card` немає; з карткою — вкладена структура.
- **Seam 4: `buildCard`** — фейкова `make`: дерево `div.card` → `h3` → (`h4`?) `ul` → `li` → `span`; без `time` /
  `note` / `heading` — без відповідних елементів; текст лише через третій аргумент `make`.
- **Seam 5: проводка** — `app.js` імпортує `buildCard` з `/card.js` і кличе його в `show` у гілці `reply.card`
  (перевірка тексту `app.js`, як `tests/test_one_message_web.py`): у цій гілці результат `buildCard` іде в
  `conversation.append`, а `renderText(reply.text)` не викликається; `/card.js` з сесією віддається як інші скрипти.

## Invariants (rules that hold for every input in the stated domain)
- **I1** — Картка розкладу має кожну подію й кожну задачу тексту відповіді рівно раз, у тому самому порядку, і нічого,
  чого немає в тексті.
  - Domain: будь-який період, будь-які події (на весь день і з часом, кілька днів, однакові назви) і задачі з датою.
  - Source: Seam (`schedule.show`); слово власника (та сама відповідь, лише вигляд).
  - Broken by: подія в тексті є, у картці немає; задача двічі.

## Exit criterion
- `pytest` зелений: Seam 1–3, 5, `test_I1_…`; `node --test` зелений: Seam 4; запечатаних тестів, що порівнюють увесь JSON
  відповіді чи весь `Reply` розкладу / задач, не знайдено (критик, пошук по `tests/`); усі запечатані — зелені.
- Smoke: Сонько — smoke мови `smoke_schedule.py`, `smoke_tasks_list.py`, `smoke_guide.py`; після викладки
  `smoke_access_shell.py` — `SMOKE PASSED`, окремий `curl` `/card.js` без входу — 302.
- Прохід власника на телефоні — картка («які плани на тиждень?», «які в мене задачі?» — картка з днями й часом).

## Deferred to later slices
- Картка на відкритті — trigger: власник попросить.

## Open items requiring human decision (if any)
- (немає — слово власника 2026-11-15)

## Critic notes (non-blocking)
- Q2: альтернатива — малювати DOM прямо й перевіряти лише власником; відкинуто: жодного автоматичного тесту вигляду.
