# 749 — Брак тесту (overseer): a test that drives try_answer_priorities with the model reply {'is_answer': True, 'same': False, 'order': [], 'timed': [3]} and asserts the duration question for task 3, together with a smoke that sen

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-that-drives-try-answer-priorities-with-the-model-repl-5857373e

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261112T194451Z-a2e275`) і назвав ще й брак тесту: a guard or prompt that marks timed-only answers as non-answers passes every current test and smoke Де: `tests/test_plans_not_questions.py, scripts/smoke_priorities.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-12T19:46:06Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test that drives try_answer_priorities with the model reply {'is_answer': True, 'same': False, 'order': [], 'timed': [3]} and asserts the duration question for task 3, together with a smoke that sends «третє поставте на час» through try_answer_priorities rather than _reordered»: тест червоніє на тому, що описано вище (a guard or prompt that marks timed-only answers as non-answers passes every current test and smoke), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
