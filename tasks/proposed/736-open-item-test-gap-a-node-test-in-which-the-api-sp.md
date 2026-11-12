# 736 — Брак тесту (overseer): a node test in which the /api/speak response for part 0 is ok but has no X-Parts header: speak returns FAILED rather than null

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-node-test-in-which-the-api-speak-response-for-part-0-is-ok-3656204c

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261111T221420Z-3fff83`) і знайшов брак тесту: Number(null) gives 0 and Number(undefined) gives NaN; with NaN the loop never runs, so a proxy that strips the header gives silent success with nothing played Де: `src/mamamemory/web/speak.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-11T22:15:44Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a node test in which the /api/speak response for part 0 is ok but has no X-Parts header: speak returns FAILED rather than null»: тест червоніє на тому, що описано вище (Number(null) gives 0 and Number(undefined) gives NaN; with NaN the loop never runs, so a proxy that strips the header gives silent success with nothing played), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
