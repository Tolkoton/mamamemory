# 753 — Брак тесту (overseer): a DOM-level test of the #help click handler: the first click fills #guide with the guide text and leaves #conversation unchanged; the second click hides #guide and makes no fetch

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-dom-level-test-of-the-help-click-handler-the-first-click-f-bae13a12

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261114T083741Z-161e75`) і знайшов брак тесту: an app.js that goes back to renderText(guide.text) into #conversation, or that re-fetches and appends on every click, still passes guide_toggle_contract.test.js. That is exactly the owner's complaint of 2026-11-14. Де: `src/mamamemory/web/guide_toggle_contract.test.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-14T08:39:36Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a DOM-level test of the #help click handler: the first click fills #guide with the guide text and leaves #conversation unchanged; the second click hides #guide and makes no fetch»: тест червоніє на тому, що описано вище (an app.js that goes back to renderText(guide.text) into #conversation, or that re-fetches and appends on every click, still passes guide_toggle_contract.test.js. That is exactly the owner's complaint of 2026-11-14.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
