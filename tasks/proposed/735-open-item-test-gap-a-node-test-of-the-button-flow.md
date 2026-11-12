# 735 — Брак тесту (overseer): a node test of the button flow in which the injected play rejects (or the audio fires 'error') on part 0: speak returns FAILED and the status line shows «Не вдалося озвучити.»

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-node-test-of-the-button-flow-in-which-the-injected-play-re-0e2c8f78

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261111T221420Z-3fff83`) і знайшов брак тесту: today's play() in app.js treats a playback error as a normal end. On a phone that cannot play OGG Opus every part 'plays' silently and success is reported, and every current test still passes Де: `src/mamamemory/web/speak.js, src/mamamemory/web/app.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-11T22:15:44Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a node test of the button flow in which the injected play rejects (or the audio fires 'error') on part 0: speak returns FAILED and the status line shows «Не вдалося озвучити.»»: тест червоніє на тому, що описано вище (today's play() in app.js treats a playback error as a normal end. On a phone that cannot play OGG Opus every part 'plays' silently and success is reported, and every current test still passes), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
