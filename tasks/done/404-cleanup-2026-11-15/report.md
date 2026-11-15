# 404 — Прибирання 2026-11-15 — звіт

## Що змінилось для власника

У коді нічого не змінено і нічого не видалено. Нічний режим показав різке зростання, тож simplifier
пройшов один раз (lens `code`, scope `src`). Він знайшов одне: константа `TASK_ID`
(`src/mamamemory/planning/__init__.py:30`) ніде не вживається. Знахідка `F-c4d6a784` має
`proposed_action: confirm`, а не `auto_remove`, тому я її не прибирав. Вона чекає вашого огляду в
`.engine/simplifier/report.md`, розділ «2026-11-15T11:43:35Z — code, nightly 2026-11-15».

## Вивід нічного режиму

`python3 .claude/hooks/simplifier.py nightly` (exit 0):

```
27 signal(s) in .claude/state/simplifier/signals-full.json
SIMPLIFIER CALL: files grew from 17 (median of the last 3 runs) to 23; lines grew from 1498 (median of the last 3 runs) to 4956; functions grew from 110 (median of the last 3 runs) to 312; complexity grew from 1 (median of the last 3 runs) to 18
Reversal rate: 0 of the last 0 removals came back (0.0 %; the corridor is 5-20 %) — too few removals to judge (0 of the 10 needed)
```

## Прохід simplifier-а

1. `python3 .claude/unattended/board.py extra-allowed`: «додаткові сесії Claude за сім днів: 0.00 USD (межі немає)», exit 0.
2. `python3 .claude/hooks/simplifier.py request --lens code --paths src` → `.engine/simplifier/2026-11-15-code-request.txt`
   (26 signals: 19 complexity/nesting, 2 dead-code, 2 unused-dependency, 3 trend).
3. Агент `simplifier` отримав цей запит як увесь свій prompt. Відповідь — `.engine/simplifier/2026-11-15-code-answer.json`,
   одна знахідка.
4. `validate`: «1 valid, 0 rejected, 0 lowered»; знахідка отримала id `F-c4d6a784`.
5. Друга думка: у цьому двигуні її немає. У `.claude/` немає ні налаштування, ні скрипта для неї
   (`grep -ri "second opinion" .claude` нічого не знаходить), тому цей крок я пропустив.
6. `route --title "code, nightly 2026-11-15"`: «1 finding(s) for the owner in .engine/simplifier/report.md; 0 auto_remove».

## Що прибрано

Нічого, тому й commit-ів із `Simplifier-Finding:` немає. Повний набір тестів не запускав: правило
«Готово, коли» вимагає цього лише тоді, коли щось прибрано. До того ж `TEST_CMD_FULL` у `.claude/project.env` порожній.

## Що чекає огляду власника

- `F-c4d6a784` — `confirm`: прибрати `TASK_ID = "t1"` (`src/mamamemory/planning/__init__.py:30`). Simplifier оцінив
  reversal risk як low. Ту саму константу вже радив прибрати звіт догляду
  `tasks/done/403-maintain-2026-11-15/report.md` (пропозиція 5).

Simplifier не дав знахідок щодо 19 складних функцій (найбільша — `start`, complexity 28), `email_verified`, `tzdata`
і `uvicorn`. Минулий догляд (задача 403) уже пояснив, що `tzdata` і `uvicorn` — хибна тривога.

## Демонстрація на хвилину

```bash
python3 .claude/hooks/simplifier.py nightly
sed -n '/2026-11-15T11:43:35Z/,$p' .engine/simplifier/report.md
```

## Витрати

Одна сесія агента `simplifier` у цій сесії (близько 20 тис. tokens, 22 с). Суми в USD скрипт не показує.

## Діапазон commit-ів

Від `b3b9f1b` (задача → doing) до commit-у, що переносить задачу в `done/`.

## Відкладене

- Прибирання пам'яті вже на часі: 22 дні від останнього, а межа 14. Це окрема робота з
  `.claude/skills/self-learning-orchestrator/triggers/periodic-maintenance.md`, і ця задача її не просить.
- У робочому дереві лишились чужі незакомічені зміни: ADR 0001/0003/0004/0007, `docs/infra.md`, `.gitignore`,
  `.engine/overseer/escalations.md`, `.engine/journeys/`. Вони не з цієї задачі, я їх не чіпав і не комітив.

## Рішення, які я ухвалив сам

- Запит і відповідь simplifier-а зберіг у `.engine/simplifier/` з датою в назві файлу, як і попередні прогони
  (`2026-11-05-*.json`), а не в корені проєкту.
- Крок «друга думка» пропустив: у двигуні такого механізму немає.
