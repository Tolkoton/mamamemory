# 731 — Брак тесту (overseer): A test that _is_plan_request is False for real tasks that contain planning words, such as «запланувати відпустку на тиждень», «Що на обід купити на тиждень» and «запланувати прибирання на два дні». A

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-that-is-plan-request-is-false-for-real-tasks-that-con-b575ce58

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261111T195902Z-825803`) і знайшов брак тесту: Today, _is_plan_request returns True for all three phrases (reproduced in the temp copy). Its broad substrings «планувати», «сплан» and the new «що на», combined with «тиждень»/«дні», make start(week=True) silently drop such spoken tasks. TASKS in tests/test_plan_request_titles.py contains no phrase with a planning word, so this over-match goes untested. Де: `tests/test_plan_request_titles.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-11T20:00:28Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test that _is_plan_request is False for real tasks that contain planning words, such as «запланувати відпустку на тиждень», «Що на обід купити на тиждень» and «запланувати прибирання на два дні». A start(week=True) on «сплануй тиждень і ще запланувати відпустку на тиждень» must keep the vacation task.»: тест червоніє на тому, що описано вище (Today, _is_plan_request returns True for all three phrases (reproduced in the temp copy). Its broad substrings «планувати», «сплан» and the new «що на», combined with «тиждень»/«дні», make start(week=True) silently drop such spoken tasks. TASKS in tests/test_plan_request_titles.py contains no phrase with a planning word, so this over-match goes untested.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
