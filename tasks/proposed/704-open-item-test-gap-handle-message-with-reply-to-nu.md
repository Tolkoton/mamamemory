# 704 — Брак тесту (overseer): handle_message with reply_to=null and a fake router answering {'intent':'new_task'} reaches planning.start: it returns the duration question, or a PlanView when a duration is given

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-handle-message-with-reply-to-null-and-a-fake-router-answerin-aefbae67

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261106T023919Z-eefa95`) і назвав ще й брак тесту: A router-schema mismatch (e.g. reading 'route' instead of 'intent', or new_task routed to CANNOT_TEXT) breaks the very first step of mama's flow, and all 100 tests still pass. The tester left this untested (Q6) Де: `tests/test_one_task_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T02:41:17Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «handle_message with reply_to=null and a fake router answering {'intent':'new_task'} reaches planning.start: it returns the duration question, or a PlanView when a duration is given»: тест червоніє на тому, що описано вище (A router-schema mismatch (e.g. reading 'route' instead of 'intent', or new_task routed to CANNOT_TEXT) breaks the very first step of mama's flow, and all 100 tests still pass. The tester left this untested (Q6)), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
