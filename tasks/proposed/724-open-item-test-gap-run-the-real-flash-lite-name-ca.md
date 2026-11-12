# 724 — Брак тесту (overseer): Run the real Flash-Lite name_case on the contract's first-note phrases with an empty catalogue: cases._name_prompt('запиши до пані Шмідт: HbA1c 7,2') with NAME_SCHEMA must return a name containing 'Шм

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-run-the-real-flash-lite-name-case-on-the-contract-s-first-no-16cda19a

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T083201Z-c830ef`) і знайшов брак тесту: A name_case prompt that makes Flash-Lite return null or a wrong name (e.g. 'HbA1c') sends every new account's first note to «Не зрозуміла…». Today's smoke still prints 8 of 8, because it never calls name_case. This is the very path of the Goal's phone scenario. Де: `scripts/smoke_note_to_case.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T08:33:45Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «Run the real Flash-Lite name_case on the contract's first-note phrases with an empty catalogue: cases._name_prompt('запиши до пані Шмідт: HbA1c 7,2') with NAME_SCHEMA must return a name containing 'Шмідт', and 'нотатка про город: посадити часник у жовтні' a name containing 'город'. Add this to scripts/smoke_note_to_case.py as a counted PASS/FAIL line.»: тест червоніє на тому, що описано вище (A name_case prompt that makes Flash-Lite return null or a wrong name (e.g. 'HbA1c') sends every new account's first note to «Не зрозуміла…». Today's smoke still prints 8 of 8, because it never calls name_case. This is the very path of the Goal's phone scenario.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
