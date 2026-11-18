# 764 — Брак тесту (overseer): A test asserts load_config(...).models['tools'].model == 'gemini-3.8-flash' while DEFAULT_MODELS['tools'] stays gemini-3.5-flash-lite.

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-asserts-load-config-models-tools-model-gemini-3-8-fla-2d79c378

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261115T132659Z-3a48d4`) і знайшов брак тесту: If load_config drops the override and falls back to Flash-Lite, all tests stay green. Under the flag, 'додай задачу купити хліб' would then show the task list instead of adding the task (the smoke's Flash-Lite FAIL). Де: `tests/test_tools_loop_flag.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-15T13:28:15Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test asserts load_config(...).models['tools'].model == 'gemini-3.8-flash' while DEFAULT_MODELS['tools'] stays gemini-3.5-flash-lite.»: тест червоніє на тому, що описано вище (If load_config drops the override and falls back to Flash-Lite, all tests stay green. Under the flag, 'додай задачу купити хліб' would then show the task list instead of adding the task (the smoke's Flash-Lite FAIL).), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
