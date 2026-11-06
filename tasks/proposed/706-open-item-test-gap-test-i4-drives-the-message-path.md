# 706 — Брак тесту (overseer): test_I4 drives the message path with a router answering {'intent':'yes'} and a wrong fingerprint, and asserts insert_calls == []

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-test-i4-drives-the-message-path-with-a-router-answering-inte-479dd87c

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261106T023919Z-eefa95`) і назвав ще й брак тесту: I4's domain is any call of handle_message, but the test's router answers {} so the message path only ever reaches CANNOT_TEXT. A handle_message that passed reply_to.id to confirm while ignoring the fingerprint would not be caught Де: `tests/test_one_task_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T02:41:17Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «test_I4 drives the message path with a router answering {'intent':'yes'} and a wrong fingerprint, and asserts insert_calls == []»: тест червоніє на тому, що описано вище (I4's domain is any call of handle_message, but the test's router answers {} so the message path only ever reaches CANNOT_TEXT. A handle_message that passed reply_to.id to confirm while ignoring the fingerprint would not be caught), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
