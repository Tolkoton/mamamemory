# 710 — Брак тесту (overseer): speech with a model answer ' Привіт ' returns 'Привіт' (or, if the contract decides otherwise, the raw text); /api/transcribe returns that same string in {text}

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-speech-with-a-model-answer-returns-or-if-the-contract-decide-5d4db73a

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261106T075957Z-a62406`) і знайшов брак тесту: removing .strip() at src/mamamemory/integrations/ai.py:74 passes every test (tester's Q6). A draft with leading or trailing whitespace would then reach /api/message unchanged Де: `tests/test_voice_speech.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:01:49Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «speech with a model answer ' Привіт ' returns 'Привіт' (or, if the contract decides otherwise, the raw text); /api/transcribe returns that same string in {text}»: тест червоніє на тому, що описано вище (removing .strip() at src/mamamemory/integrations/ai.py:74 passes every test (tester's Q6). A draft with leading or trailing whitespace would then reach /api/message unchanged), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
