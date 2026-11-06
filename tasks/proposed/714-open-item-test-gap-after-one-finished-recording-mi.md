# 714 — Брак тесту (overseer): after one finished recording, mic then send before getUserMedia resolves ends in 'тиша' with an error shown, not stuck in 'transcribing'

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-after-one-finished-recording-mic-then-send-before-getusermed-288d733d

## Що сталося
Overseer прийняв юніт `-|-|unit 3` (PASS, запит `20261106T080422Z-c3c544`) і знайшов брак тесту: `recorder` is never reset to null after onstop, so stopAndTranscribe takes the stale, inactive recorder and calls stop() on it. onstop never fires, no 'transcribed' event is dispatched, and the voice state stays in 'transcribing' until a reload Де: `src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:05:27Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «after one finished recording, mic then send before getUserMedia resolves ends in 'тиша' with an error shown, not stuck in 'transcribing'»: тест червоніє на тому, що описано вище (`recorder` is never reset to null after onstop, so stopAndTranscribe takes the stale, inactive recorder and calls stop() on it. onstop never fires, no 'transcribed' event is dispatched, and the voice state stays in 'transcribing' until a reload), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
