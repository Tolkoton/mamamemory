# 725 — Брак тесту (overseer): A pytest where the account has an empty catalogue and the fake name_case answers {'name': null} (or a blank string). It asserts the material is 'unplaced', the reply is NOT_UNDERSTOOD, no case is crea

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-pytest-where-the-account-has-an-empty-catalogue-and-the-fa-1319bba6

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T083201Z-c830ef`) і знайшов брак тесту: _name could return '' for a blank name, or _decided could treat a falsy name as a name. The empty-catalogue branch would then ask «Створити справу «»?». The current world fake always answers name_case with a name, so no test reaches the null branch. Де: `tests/test_note_to_case.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T08:33:45Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A pytest where the account has an empty catalogue and the fake name_case answers {'name': null} (or a blank string). It asserts the material is 'unplaced', the reply is NOT_UNDERSTOOD, no case is created and classify_case is never called.»: тест червоніє на тому, що описано вище (_name could return '' for a blank name, or _decided could treat a falsy name as a name. The empty-catalogue branch would then ask «Створити справу «»?». The current world fake always answers name_case with a name, so no test reaches the null branch.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
