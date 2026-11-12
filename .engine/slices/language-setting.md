# Slice language-setting — F5 S1, driven by /feature-architect f5-guide-voice — planning artifact

## Goal
Мова розмови тримається під акаунтом (C8: «закласти можливість її змінити… юзер вибирає свою мову»), а не в
налаштуваннях сервера: `settings/profile {language}`; немає документа чи мова невідома — `uk`. Розпізнавання голосу
бере мову звідти. Вимірний сигнал: тести; перевірка на розгорнутій адресі — у S4 (разом із гайдом і озвученням).

## Premise verified
- `store.get(account_id, path)` під акаунтом — код F1; `speech(..., language=…)` — код F1 S2 (`http/app.py` бере
  `config.language`).

## Out of scope (deliberately)
- перемикач мови в застосунку й запис мови мамою (є лише українська — F5 Out of scope);
- мова відповідей і питань планування (тексти лише українські);
- гайд (S2), озвучення (S3) — вони кличуть `access.language`.

## Seam (contract)
- `access.LANGUAGES = ("uk",)`, `access.DEFAULT_LANGUAGE = "uk"`, `access.PROFILE_PATH = "settings/profile"`.
- `access.language(session, store) -> str`: документ `settings/profile` під акаунтом з `language` з `LANGUAGES` → вона;
  немає документа, немає поля, мова не з `LANGUAGES` → `DEFAULT_LANGUAGE`; помилка читання сховища → `DEFAULT_LANGUAGE`
  (розпізнавання не падає через налаштування).
- `POST /api/transcribe` передає в `speech` `language=access.language(session, store)` замість `config.language`;
  читання сховища — у `run_in_threadpool`, як і сам `speech` (один зайвий запит до Firestore на розпізнавання, до
  дедлайну).
- Does NOT do: запису мови, перемикача, мови текстів.

## Decisions (with WHY)
- Q1: Помилка читання — мова за замовчуванням, не помилка запиту. Чому: мова поки одна; падіння розпізнавання через
  налаштування гірше за мову за замовчуванням. Rejected: пробросити помилку — найсильніше за: видно збій; але мама
  втрачає запис голосу.
- Q2: Невідома мова — за замовчуванням. Чому: документ могли записати з майбутньої версії; розпізнавання не має падати.
  Rejected: передати невідомий код у `speech` — найсильніше за: майбутня мова запрацює без зміни коду; але `speech` і
  підказки мають лише українську, і модель отримала б мову без голосу й тексту.
- Q3: `Config.language` лишається, але HTTP його більше не читає. Чому: запечатаний тест F1 S2
  (`tests/test_voice_speech.py:100`) кличе `speech` з `config.language`; прибрати поле — перепечатування без користі.
  Rejected: прибрати — найсильніше за: немає мертвого налаштування; S2 і S3 кличуть `access.language`, не config.

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: читання** — немає документа, `{}`, `{"language": "uk"}`, `{"language": "de"}`, `{"language": 5}`, помилка
  сховища → `uk` / `uk`; окремий акаунт — свій документ.
- **Seam 2: розпізнавання** — застосунок зібрано з `Config`, де `language` — інше значення (`"xx"`), а документ акаунта
  дає `uk` (чи його немає): фейкова `speech` дістає `"uk"`. Неправильна реалізація, що пройшла б без цього: незмінене
  `language=state.config.language` (усі три значення були б `uk`).

## Invariants (rules that hold for every input in the stated domain)
None — читання одного поля з запасним значенням і прокладка в один виклик; правило на домен входів тут вигадане б.

## Exit criterion
- `pytest` зелений: Seam 1–2; усі запечатані тести F1–F3 зелені.
- Розгортання — разом із S2 (гайд) і S3 (озвучення) в S4; окремого smoke немає (поведінка для мами не змінюється).

## Deferred to later slices
- Перемикач мови — trigger: друга мова.

## Open items requiring human decision (if any)
- (немає)

## Critic notes (non-blocking)
- (порожньо)
