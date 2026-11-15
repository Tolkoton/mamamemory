# Slice dialog — поправка сторінки за словом власника 2026-11-14 — planning artifact

## Goal
Власник, 2026-11-14: «було б добре, якби текст того, що я задав, теж відображався перед відповіддю. Щоб це був як
діалог, а не просто список відповідей.» Зараз розмова показує лише відповіді асистента. Треба: кожне мамине
повідомлення (голосом, натиском кнопки, файлом) з'являється в розмові перед відповіддю, окремим «маминим» абзацом.
Вимірний сигнал: тести (`node --test`, `pytest`); прохід власника на телефоні.

## Premise verified
- `app.js`: голос — `dispatch` дія `send_message` → `message(action.text, action.reply_to).then(show)`; `send(text)` —
  те саме; кнопки «так» / уточнення — `pressed(press, target)` (one-message); файл — `upload(input)`; відповіді —
  `show` / `renderText` абзацом `<p>` у `#conversation` (код F1 S3, F3, one-message).

## Out of scope (deliberately)
- історія розмови після перезавантаження сторінки (розмова — лише на екрані, як було);
- сервер — без змін;
- озвучення маминого тексту (🔊 лише біля відповідей).

## Seam (contract)
- Новий модуль `web/dialog.js`: `mineText(kind, value) -> string` — текст маминого абзацу: `kind` `"said"` — `value`
  (обрізаний пробілами); `"button"` — `value` (напис кнопки: «так», варіант уточнення); `"file"` — «📎 <назва файлу>».
  Порожній `value` (після обрізання) — `""` для будь-якого `kind`; невідомий `kind` — `""`.
- `app.js`: функція `renderMine(text)` — абзац `<p class="mine">` у `#conversation` з цим текстом (`textContent`, не HTML), без 🔊; порожній
  текст — нічого. Виклики: `send(text)` і дія `send_message` — `renderMine(mineText("said", …))` до виклику
  `message`; `upload` — `renderMine(mineText("file", file.name))` до виклику `uploadFile`; `pressed(press, target)` —
  після перевірки `answer === null` і перед `show` / `renderText` відповіді: `renderMine(mineText("button",
  target.label))` (напис кнопки з'являється разом з відповіддю, над нею; збій натиску — теж, кожна спроба — свій рядок;
  `buttons.js` без змін). `renderMine` не змінює `lastReplyTo` і стан голосу.
- `index.html`: `#conversation p.mine` — праворуч, інший фон (як повідомлення в месенджері).
- `http/app.py`: маршрут `/dialog.js` (`_script("dialog.js")`, як `/help.js`).
- Does NOT do: історії, змін сервера, озвучення маминого тексту.

## Decisions (with WHY)
- Q1: Мамин текст — до відповіді, одразу (до запиту). Чому: «щоб це був як діалог»; мама бачить, що її почуто, поки
  асистент думає. Rejected: показувати разом з відповіддю — найсильніше за: при збої мережі немає «зайвого» рядка; але
  під час довгої відповіді (до 8 с на холодному старті) екран мовчить.
- Q2: Натиск кнопки теж показується (напис кнопки), разом з відповіддю, над нею. Чому: інакше в діалозі відповідь без
  питання; момент «прийнято» стає відомий лише після відповіді (`bindButtons`). Rejected: показувати одразу через
  зворотний виклик з `bindButtons` — найсильніше за: як голос; але змінює запечатаний `buttons.js` і його тести.

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: `mineText`** — сказане з пробілами → обрізане; порожнє → `""`; кнопка → напис; файл → «📎 назва».
- **Seam 2: проводка** — `app.js` імпортує `mineText` з `/dialog.js`; `renderMine` викликано в `send` і в гілці
  `send_message` — до `message(`, в `upload` — до `uploadFile(`, у `pressed` — після `answer === null` і до `show(` /
  `renderText(` (перевірка порядку й першого аргументу `mineText` — `"said"`, `"file"`, `"button"` — у тексті `app.js`, як
  `tests/test_one_message_web.py`); `index.html` має правило `#conversation p.mine`; `/dialog.js`
  з сесією віддається як інші скрипти.

## Invariants (rules that hold for every input in the stated domain)
None — показ тексту й проводка, не логіка над доменом входів.

## Exit criterion
- `node --test src/mamamemory/web/*.test.js` зелений (Seam 1); `pytest` зелений (Seam 2).
- Smoke: Сонько — після викладки `smoke_access_shell.py` — `SMOKE PASSED`, і окремий `curl` `/dialog.js` без входу —
  302 на вхід.
- Прохід власника на телефоні — картка (сказати фразу — спершу вона, потім відповідь; натиснути «так» — «так» у
  розмові).

## Deferred to later slices
- Історія розмови між відкриттями — trigger: власник попросить.

## Open items requiring human decision (if any)
- (немає — слово власника 2026-11-14)

## Critic notes (non-blocking)
- `show` і відновлення на відкритті клас `mine` не ставлять — відновлені питання лишаються абзацами асистента.
