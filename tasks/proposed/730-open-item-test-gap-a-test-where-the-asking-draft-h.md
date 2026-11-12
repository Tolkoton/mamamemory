# 730 — Брак тесту (overseer): A test where the asking draft has asked_at older than 24 h and handle_message is called with reply_to {kind:'duration', id:<old plan_id>} and the text «купити чай на пів години» (route new_task, parse

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-where-the-asking-draft-has-asked-at-older-than-24-h-a-3eb71e4d

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261111T192214Z-622548`) і знайшов брак тесту: try_answer_duration (src/mamamemory/planning/__init__.py:239) never checks staleness. If the phone page stays open for more than a day with the old question on screen, any phrase that parses as a duration is written into the old draft's task X, and the old question captures the message. That breaks I2 («не захоплює нового повідомлення»), and no test sends a reply_to message to a stale draft. Де: `tests/test_stuck_question.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-11T19:23:47Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «A test where the asking draft has asked_at older than 24 h and handle_message is called with reply_to {kind:'duration', id:<old plan_id>} and the text «купити чай на пів години» (route new_task, parse_duration 30). The old task X must stay without a duration, and a new draft with only «чай» must exist. Equivalently: try_answer_* on a stale draft returns None.»: тест червоніє на тому, що описано вище (try_answer_duration (src/mamamemory/planning/__init__.py:239) never checks staleness. If the phone page stays open for more than a day with the old question on screen, any phrase that parses as a duration is written into the old draft's task X, and the old question captures the message. That breaks I2 («не захоплює нового повідомлення»), and no test sends a reply_to message to a stale draft.), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
