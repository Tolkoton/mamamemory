# 711 — Брак тесту (overseer): A test of the app.js wiring, using a fake getUserMedia that rejects and a fake fetch that rejects. Each must end with voice.phase back at silence, #draft showing 'Не вдалося, спробуйте ще раз.', and t

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-of-the-app-js-wiring-using-a-fake-getusermedia-that-r-d506e483

## Що сталося
Overseer прийняв юніт `-|-|unit 2` (PASS, запит `20261106T080258Z-1fafa6`) і знайшов брак тесту: voice_state.test.js tests only the pure module. If app.js loses the try/catch around getUserMedia or fetch, or dispatches the wrong event, the original hang comes back and all 10 node tests still pass. The status-0 test passes even without this turn's change. Де: `src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:03:43Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test of the app.js wiring, using a fake getUserMedia that rejects and a fake fetch that rejects. Each must end with voice.phase back at silence, #draft showing 'Не вдалося, спробуйте ще раз.', and the mic button starting a new recording.»: тест червоніє на тому, що описано вище (voice_state.test.js tests only the pure module. If app.js loses the try/catch around getUserMedia or fetch, or dispatches the wrong event, the original hang comes back and all 10 node tests still pass. The status-0 test passes even without this turn's change.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
