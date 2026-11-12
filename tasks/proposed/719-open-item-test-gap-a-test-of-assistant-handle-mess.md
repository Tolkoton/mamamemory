# 719 — Брак тесту (overseer): A test of assistant.handle_message with reply_to.kind == 'plan' and a stored shown draft. The fake AI records the 'route' prompt, and the test asserts that the prompt contains each unwritten task titl

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-of-assistant-handle-message-with-reply-to-kind-plan-a-f022dad5

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T014642Z-e4b0a8`) і знайшов брак тесту: If handle_message passes [] or the titles of a different draft into _route_prompt, all 314 tests still pass and the smoke still prints 13/13, because the smoke calls _route_prompt with TITLES directly. Production then routes short edits like 'лікар о десятій у середу' without the titles, which is the condition that failed real-model runs 1 and 2. Де: `tests/test_voice_edits_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T01:48:02Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test of assistant.handle_message with reply_to.kind == 'plan' and a stored shown draft. The fake AI records the 'route' prompt, and the test asserts that the prompt contains each unwritten task title of that draft (for example 'подзвонити нотаріусу'). A second case with a foreign plan_id asserts the prompt lists no titles.»: тест червоніє на тому, що описано вище (If handle_message passes [] or the titles of a different draft into _route_prompt, all 314 tests still pass and the smoke still prints 13/13, because the smoke calls _route_prompt with TITLES directly. Production then routes short edits like 'лікар о десятій у середу' without the titles, which is the condition that failed real-model runs 1 and 2.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
