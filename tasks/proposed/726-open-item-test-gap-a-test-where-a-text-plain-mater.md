# 726 — Брак тесту (overseer): a test where a text/plain material is stored with text "" (the store fails after the material write) and is then retried with the header only, asserting the reply is not a permanent 'Не вдалося' (or t

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-where-a-text-plain-material-is-stored-with-text-the-s-dd01f140

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261107T090636Z-a74d77`) і знайшов брак тесту: _file_text raises LookupError on text/plain with data=None (src/mamamemory/cases/__init__.py:180). The header-only automatic retry from upload.js then fails on every attempt, and no current test tries this path Де: `tests/test_photo_and_file.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-07T09:08:19Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test where a text/plain material is stored with text "" (the store fails after the material write) and is then retried with the header only, asserting the reply is not a permanent 'Не вдалося' (or that upload.js resends the body)»: тест червоніє на тому, що описано вище (_file_text raises LookupError on text/plain with data=None (src/mamamemory/cases/__init__.py:180). The header-only automatic retry from upload.js then fails on every attempt, and no current test tries this path), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
