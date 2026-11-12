# 716 — Брак тесту (overseer): a test of _task_prompt / _parse_tasks with now = 2026-11-09T22:30:00Z and a Europe/Kyiv calendar asserts that the prompt's 'Зараз' and its day list start at the local date 2026-11-10 (вівторок), not t

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-of-task-prompt-parse-tasks-with-now-2026-11-09t22-30-64627880

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261106T232125Z-8841d6`) і назвав ще й брак тесту: main.py:21 passes datetime.now(UTC), and _task_prompt builds the weekday calendar from UTC dates. Between local midnight and 02:00 (03:00 in summer) Kyiv time, the list is one day behind and 'завтра'/'у понеділок' resolve to the wrong date. No test sets now near local midnight, and the smoke fixes NOW at 09:07 UTC Де: `tests/test_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T23:23:36Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test of _task_prompt / _parse_tasks with now = 2026-11-09T22:30:00Z and a Europe/Kyiv calendar asserts that the prompt's 'Зараз' and its day list start at the local date 2026-11-10 (вівторок), not the UTC date»: тест червоніє на тому, що описано вище (main.py:21 passes datetime.now(UTC), and _task_prompt builds the weekday calendar from UTC dates. Between local midnight and 02:00 (03:00 in summer) Kyiv time, the list is one day behind and 'завтра'/'у понеділок' resolve to the wrong date. No test sets now near local midnight, and the smoke fixes NOW at 09:07 UTC), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
