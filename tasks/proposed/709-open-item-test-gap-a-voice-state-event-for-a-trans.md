# 709 — Брак тесту (overseer): a voice_state event for a transcribe that never got a response (network rejection) or a recording that could not start (microphone permission denied) returns the state to silence and emits show_error,

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-voice-state-event-for-a-transcribe-that-never-got-a-respon-32508bf4

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261106T075957Z-a62406`) і знайшов брак тесту: today a rejected fetch in stopAndTranscribe (src/mamamemory/web/app.js:57) never dispatches 'transcribed', and a refused getUserMedia leaves recorder null so 'send' throws. Either way voice stays in RECORDING or TRANSCRIBING, and mic and send do nothing until the page is reloaded. This is an ordinary case on a phone that no test tries Де: `src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:01:49Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a voice_state event for a transcribe that never got a response (network rejection) or a recording that could not start (microphone permission denied) returns the state to silence and emits show_error, and app.js dispatches it from the fetch/getUserMedia rejection»: тест червоніє на тому, що описано вище (today a rejected fetch in stopAndTranscribe (src/mamamemory/web/app.js:57) never dispatches 'transcribed', and a refused getUserMedia leaves recorder null so 'send' throws. Either way voice stays in RECORDING or TRANSCRIBING, and mic and send do nothing until the page is reloaded. This is an ordinary case on a phone that no test tries), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
