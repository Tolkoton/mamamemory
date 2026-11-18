# 773 — Брак тесту (overseer): an HTTP test: POST /api/message on a «які в мене файли?» reply (documents_list → catalogue) asserts the JSON card rows carry "material_id" for files, and that a «лише записи» row has no material_id ke

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-an-http-test-post-api-message-on-a-reply-documents-list-cata-f84c5094

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261117T175001Z-43ee43`) і знайшов брак тесту: a _reply_json that pops material_id from every card item (or never emits it) passes today's suite: test_find_document checks the Python Reply and the node test builds the card from hand-written JSON, so no row on the page would become a button (AC-11) while every test stays green Де: `tests/test_show_document_http.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-17T17:51:34Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «an HTTP test: POST /api/message on a «які в мене файли?» reply (documents_list → catalogue) asserts the JSON card rows carry "material_id" for files, and that a «лише записи» row has no material_id key»: тест червоніє на тому, що описано вище (a _reply_json that pops material_id from every card item (or never emits it) passes today's suite: test_find_document checks the Python Reply and the node test builds the card from hand-written JSON, so no row on the page would become a button (AC-11) while every test stays green), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
