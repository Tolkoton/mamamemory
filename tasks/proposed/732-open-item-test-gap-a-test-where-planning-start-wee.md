# 732 — Брак тесту (overseer): A test where planning.start(week=True) is called with a parse that returns ['Сплануй тиждень', 'запланувати відпустку на тиждень'] (one spoken phrase «сплануй тиждень і ще запланувати відпустку на тиж

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-where-planning-start-week-true-is-called-with-a-parse-a3937cb4

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261111T200656Z-41cb15`) і знайшов брак тесту: Today's tests call only _is_plan_request on single titles. If the filter at planning/__init__.py:172 were applied to the whole spoken text, or dropped every draft once any title is a request, the vacation task would vanish silently and both tests in test_plan_request_titles.py would still pass. Де: `tests/test_plan_request_titles.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-11T20:08:02Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test where planning.start(week=True) is called with a parse that returns ['Сплануй тиждень', 'запланувати відпустку на тиждень'] (one spoken phrase «сплануй тиждень і ще запланувати відпустку на тиждень»). The resulting draft must hold the vacation task and must not hold the request title.»: тест червоніє на тому, що описано вище (Today's tests call only _is_plan_request on single titles. If the filter at planning/__init__.py:172 were applied to the whole spoken text, or dropped every draft once any title is a request, the vacation task would vanish silently and both tests in test_plan_request_titles.py would still pass.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
