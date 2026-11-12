# 717 — Брак тесту (overseer): test that on a second planning, answer_limits with parsed(same_as_last=False) and nothing named ('ні') returns the limits question again and leaves planning/limits unchanged

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-test-that-on-a-second-planning-answer-limits-with-parsed-sam-4aeef90a

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261106T235131Z-f00ffe`) і назвав ще й брак тесту: today's `_limits_from` ignores same_as_last and silently accepts the saved limits for any answer that names nothing; all 230 tests still pass Де: `tests/test_time_limits_planning.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T23:52:43Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «test that on a second planning, answer_limits with parsed(same_as_last=False) and nothing named ('ні') returns the limits question again and leaves planning/limits unchanged»: тест червоніє на тому, що описано вище (today's `_limits_from` ignores same_as_last and silently accepts the saved limits for any answer that names nothing; all 230 tests still pass), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
