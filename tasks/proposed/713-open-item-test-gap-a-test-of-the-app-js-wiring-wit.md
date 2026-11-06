# 713 — Брак тесту (overseer): a test of the app.js wiring with a stubbed getUserMedia: mic, then send, then mic again while the first getUserMedia is still pending, then both resolve. Exactly one stream stays open and the other ha

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-of-the-app-js-wiring-with-a-stubbed-getusermedia-mic-cc4e2d0e

## Що сталося
Overseer прийняв юніт `-|-|unit 3` (PASS, запит `20261106T080422Z-c3c544`) і знайшов брак тесту: both pending calls see phase === 'recording' when they resolve, so both streams pass stillWanted(). The second assignment to `recorder` overwrites the first, and the first stream's microphone is never stopped. Nothing tests that interleaving Де: `src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:05:27Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test of the app.js wiring with a stubbed getUserMedia: mic, then send, then mic again while the first getUserMedia is still pending, then both resolve. Exactly one stream stays open and the other has its tracks stopped»: тест червоніє на тому, що описано вище (both pending calls see phase === 'recording' when they resolve, so both streams pass stillWanted(). The second assignment to `recorder` overwrites the first, and the first stream's microphone is never stopped. Nothing tests that interleaving), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
