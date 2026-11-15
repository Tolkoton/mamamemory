# 757 — Брак тесту (overseer): a DOM-level test (jsdom or a stubbed document) that runs pressed() with a successful answer and with a failed one, and asserts that #conversation's children are p.mine with the label, followed by the

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-dom-level-test-jsdom-or-a-stubbed-document-that-runs-press-be6dfcff

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261114T173023Z-8c06bf`) і знайшов брак тесту: show() or renderText inserting the reply before the existing children (prepend), or a later change appending the mine paragraph after the reply inside a helper; the text-order tests in tests/test_dialog_web.py only see the order of call sites in pressed() Де: `src/mamamemory/web/dialog_contract.test.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-14T17:31:26Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a DOM-level test (jsdom or a stubbed document) that runs pressed() with a successful answer and with a failed one, and asserts that #conversation's children are p.mine with the label, followed by the reply paragraph, in that order»: тест червоніє на тому, що описано вище (show() or renderText inserting the reply before the existing children (prepend), or a later change appending the mine paragraph after the reply inside a helper; the text-order tests in tests/test_dialog_web.py only see the order of call sites in pressed()), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
