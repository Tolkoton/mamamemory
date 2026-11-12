# 727 — Брак тесту (overseer): a test of assistant.route_schema: with reply_to=None and with a 'plan' reply_to, the intent enum holds no 'no', 'not_needed' or 'case_name' but still holds 'yes', 'edit', 'move', 'other'; with a 'case

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-of-assistant-route-schema-with-reply-to-none-and-with-38fd31a9

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T104318Z-e4a86b`) і знайшов брак тесту: deleting the filter (the «ну не знаю» → no regression comes back), or filtering CASE_ANSWERS instead of CASE_ANSWERS[1:] (drops 'yes', so plan confirmation breaks), both pass today's pytest suite because the fake AI ignores the schema Де: `tests/test_case_questions.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T10:44:26Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test of assistant.route_schema: with reply_to=None and with a 'plan' reply_to, the intent enum holds no 'no', 'not_needed' or 'case_name' but still holds 'yes', 'edit', 'move', 'other'; with a 'case' reply_to it is the full ROUTE_SCHEMA»: тест червоніє на тому, що описано вище (deleting the filter (the «ну не знаю» → no regression comes back), or filtering CASE_ANSWERS instead of CASE_ANSWERS[1:] (drops 'yes', so plan confirmation breaks), both pass today's pytest suite because the fake AI ignores the schema), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
