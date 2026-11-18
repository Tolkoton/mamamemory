# 775 — Брак тесту (overseer): a test that sends an unusual method (TRACE, PROPFIND) to /walker/login on an app with a token and asserts the missing-route 404 body, not 405

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-that-sends-an-unusual-method-trace-propfind-to-walker-d8daa4d4

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261118T101642Z-67b467`) і назвав ще й брак тесту: the current fixed method list (GET, POST, HEAD, PUT, PATCH, DELETE, OPTIONS) gives 405 for any other method, which shows the route exists, and the Seam 2 / I2 tests still pass Де: `tests/test_walker_mode.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-18T10:18:14Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test that sends an unusual method (TRACE, PROPFIND) to /walker/login on an app with a token and asserts the missing-route 404 body, not 405»: тест червоніє на тому, що описано вище (the current fixed method list (GET, POST, HEAD, PUT, PATCH, DELETE, OPTIONS) gives 405 for any other method, which shows the route exists, and the Seam 2 / I2 tests still pass), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
