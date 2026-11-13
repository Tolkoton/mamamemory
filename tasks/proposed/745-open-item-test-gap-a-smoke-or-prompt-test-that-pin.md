# 745 — Брак тесту (overseer): a smoke or prompt test that pins the form of address (ви or ти) in the answer_work reply once the owner chooses

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-smoke-or-prompt-test-that-pins-the-form-of-address-or-in-t-bfba3aa4

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261112T120421Z-85a7e2`) і знайшов брак тесту: today the live model mixes «ви працювали» and «ти працювала» across answers (Sonko's smoke lines 24–25), and no check catches the inconsistency Де: `scripts/smoke_work_recall.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-12T12:05:12Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a smoke or prompt test that pins the form of address (ви or ти) in the answer_work reply once the owner chooses»: тест червоніє на тому, що описано вище (today the live model mixes «ви працювали» and «ти працювала» across answers (Sonko's smoke lines 24–25), and no check catches the inconsistency), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
