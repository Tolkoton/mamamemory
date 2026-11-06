# 712 — Брак тесту (overseer): mic, then send while getUserMedia is still pending (the first-use permission prompt is open), then the permission is granted: the recorder that started late is stopped, or is never started, and no sec

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-mic-then-send-while-getusermedia-is-still-pending-the-first-e0c8596d

## Що сталося
Overseer прийняв юніт `-|-|unit 2` (PASS, запит `20261106T080258Z-1fafa6`) і знайшов брак тесту: Today 'send' with recorder === null dispatches status 0, and voice goes back to silence. getUserMedia then resolves and startRecording sets up and starts a MediaRecorder that nothing ever stops: the microphone stays live in the background, and the next tap on mic opens a second stream. Де: `src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:03:43Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «mic, then send while getUserMedia is still pending (the first-use permission prompt is open), then the permission is granted: the recorder that started late is stopped, or is never started, and no second stream stays open.»: тест червоніє на тому, що описано вище (Today 'send' with recorder === null dispatches status 0, and voice goes back to silence. getUserMedia then resolves and startRecording sets up and starts a MediaRecorder that nothing ever stops: the microphone stays live in the background, and the next tap on mic opens a second stream.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
