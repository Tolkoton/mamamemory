# 405 — Прибирання 2026-11-18 — звіт

## Що змінилось для власника

У коді нічого не змінено і нічого не видалено. Нічний режим показав різке зростання, тож simplifier
пройшов один раз (lens `code`, scope `src`). Він знайшов дві невживані константи:

- `TASK_ID` у `src/mamamemory/planning/__init__.py:30`. Її вже знаходило минуле прибирання, задача 404.
- `LOGIN_AGAIN` у `src/mamamemory/cases/documents.py:26`. Цю знайдено вперше.

Обидві знахідки validator знизив до `flag_only`, бо жоден тест не захищає цю логіку. Тому я їх не
прибирав. Вони чекають вашого огляду в `.engine/simplifier/report.md`, розділ «2026-11-18T10:02:55Z — code, nightly 2026-11-18».

## Вивід нічного режиму

`python3 .claude/hooks/simplifier.py nightly` (exit 0):

```
35 signal(s) in .claude/state/simplifier/signals-full.json
SIMPLIFIER CALL: files grew from 20 (median of the last 4 runs) to 28; lines grew from 3227 (median of the last 4 runs) to 7096; functions grew from 211 (median of the last 4 runs) to 444; complexity grew from 9.5 (median of the last 4 runs) to 23
Reversal rate: 0 of the last 0 removals came back (0.0 %; the corridor is 5-20 %) — too few removals to judge (0 of the 10 needed)
```

## Прохід simplifier-а

1. `python3 .claude/unattended/board.py extra-allowed`: «додаткові сесії Claude за сім днів: 1.11 USD (межі немає)», exit 0.
2. `python3 .claude/hooks/simplifier.py request --lens code --paths src` → `.engine/simplifier/2026-11-18-code-request.txt`.
   У запиті 35 signals: 26 complexity/nesting, 3 dead-code, 2 unused-dependency і 4 trend.
3. Агент `simplifier` отримав цей запит як увесь свій prompt. Його відповідь — `.engine/simplifier/2026-11-18-code-answer.json`.
   Він дав дві знахідки, обидві `confirm`.
4. `validate`: «2 valid, 0 rejected, 2 lowered». Обидві знахідки знижено з `confirm -> flag_only`
   («logic with no test protecting it is flagged, not acted on»). Вони отримали id `F-705b9b74` і `F-91cfce8b`.
5. Другої думки в цьому двигуні немає: `grep -rni "second opinion" .claude` знаходить лише журнал сесії задачі 404, а
   ні налаштування, ні скрипта немає. Цей крок я пропустив, як і в задачі 404.
6. `route --title "code, nightly 2026-11-18"`: «2 finding(s) for the owner in .engine/simplifier/report.md; 0 auto_remove».

## Що прибрано

Нічого, тому й commit-ів із `Simplifier-Finding:` немає. Знахідок `auto_remove` не було, тож умови
прибирання з `.claude/references/simplifier.md` навіть не постали. Повний набір тестів я не запускав, бо «Готово, коли»
вимагає його лише тоді, коли щось прибрано.

## Що чекає огляду власника

- `F-705b9b74` (`flag_only`) — прибрати `TASK_ID = "t1"` (`src/mamamemory/planning/__init__.py:30`). Це та сама
  константа, що й `F-c4d6a784` із задачі 404. Вона досі на місці. Reversal risk — low.
- `F-91cfce8b` (`flag_only`) — прибрати `LOGIN_AGAIN` (`src/mamamemory/cases/documents.py:26`). Текст «увійдіть знову»
  web-клієнт бере з власної константи в `src/mamamemory/web/documents.js:6`, а не з сервера. Reversal risk — low.

Simplifier нічого не сказав про 26 сигналів complexity/nesting, про `email_verified`, `tzdata` і `uvicorn`.
Найскладніша функція — `start`, complexity 28. Від задачі 404 ріст великий: функцій 312 → 444, рядків 4956 → 7096.
Мабуть, це триває робота над F6 (tools).

## Демонстрація на хвилину

```bash
python3 .claude/hooks/simplifier.py nightly
sed -n '/2026-11-18T10:02:55Z/,$p' .engine/simplifier/report.md
```

## Витрати

Одна сесія агента `simplifier`: близько 21 тис. tokens, 17 с. Суми в USD скрипт не показує.

## Діапазон commit-ів

Від `64e8718` (задача → doing) до commit-у, що переносить задачу в `done/`.

## Відкладене

- У робочому дереві лежить незакомічена робота, яку робив не я: змінено код у `src/` і `tests/`, ADR, `docs/infra.md`,
  `.engine/journeys/`, `.engine/slices/` та інше. Схоже, це F6 (tools). Я її не чіпав і не комітив.
- У `.engine/simplifier/report.md` теж лежали чужі незакомічені розділи («f6-tools requirements/architecture», 2026-11-15).
  Я закомітив лише свій розділ від 2026-11-18. Чужі лишились у робочому дереві як були.

## Рішення, які я ухвалив сам

- Другу думку я пропустив, бо в двигуні її немає (крок 5).
- Із `.engine/simplifier/report.md` я закомітив лише свій розділ, а чужі незакомічені розділи лишив. Причина: два автори в тих самих
  файлах дали б конфлікт при злитті.
