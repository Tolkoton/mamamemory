# 718 — Брак тесту (overseer): scripts/smoke_priorities.py runs a draft that has a source:'tasks' task, using the real model, on answers like 'третє поставте на час' and 'спершу лікар, а насіння на час'. It asserts timed == [3] and

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-scripts-smoke-priorities-py-runs-a-draft-that-has-a-source-t-56af8a38

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T005601Z-52f427`) і знайшов брак тесту: The five cases all have timed: [] and none has a Tasks task. If Gemini puts the time choice into 'order' or leaves 'timed' empty, the smoke still prints SMOKE PASSED. Then a Tasks task mama asks to put on time stays untimed. The turn's line 'з новим полем «на час» 5 з 5' only shows the old answers still parse. Де: `scripts/smoke_priorities.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T00:56:55Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «scripts/smoke_priorities.py runs a draft that has a source:'tasks' task, using the real model, on answers like 'третє поставте на час' and 'спершу лікар, а насіння на час'. It asserts timed == [3] and that order is unchanged or as named.»: тест червоніє на тому, що описано вище (The five cases all have timed: [] and none has a Tasks task. If Gemini puts the time choice into 'order' or leaves 'timed' empty, the smoke still prints SMOKE PASSED. Then a Tasks task mama asks to put on time stays untimed. The turn's line 'з новим полем «на час» 5 з 5' only shows the old answers still parse.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
