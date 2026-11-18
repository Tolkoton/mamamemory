# 767 — Брак тесту (overseer): A test sends two concurrent «так» answers to actions.answer (or POST /api/action/answer) with the same element id on a three-item proposal, and asserts that exactly one delete_task call is made for el

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-sends-two-concurrent-answers-to-actions-answer-or-pos-46ed721e

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261115T141006Z-201dd4`) і знайшов брак тесту: answer reads and writes actions/current without store.transact. Two simultaneous presses both act on index 0, and a racing «так»/«ні» can skip element 1 without asking about it. Today's sequential tests stay green. Де: `tests/test_confirm_core.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-15T14:11:18Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test sends two concurrent «так» answers to actions.answer (or POST /api/action/answer) with the same element id on a three-item proposal, and asserts that exactly one delete_task call is made for element 0 and that element 1 is neither deleted nor skipped.»: тест червоніє на тому, що описано вище (answer reads and writes actions/current without store.transact. Two simultaneous presses both act on index 0, and a racing «так»/«ні» can skip element 1 without asking about it. Today's sequential tests stay green.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
