# 705 — Брак тесту (overseer): handle_message with reply_to kind 'plan' carrying the shown fingerprint and a router answering {'intent':'yes'} writes exactly one event; the same with {'intent':'other'} writes nothing and returns 'П

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-handle-message-with-reply-to-kind-plan-carrying-the-shown-fi-33ca8dba

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261106T023919Z-eefa95`) і назвав ще й брак тесту: A router that calls confirm on 'other', or never on 'yes', goes undetected Де: `tests/test_one_task_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T02:41:17Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «handle_message with reply_to kind 'plan' carrying the shown fingerprint and a router answering {'intent':'yes'} writes exactly one event; the same with {'intent':'other'} writes nothing and returns 'Поки що я вмію записати одну задачу в календар.'»: тест червоніє на тому, що описано вище (A router that calls confirm on 'other', or never on 'yes', goes undetected), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
