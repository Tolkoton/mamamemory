# 715 — Перезапечатати тести S1 і S3: звіт

## Що змінилось для власника
Ваше «так» виконано: тести access-shell (S1) і one-task-to-calendar (S3) знову запечатані в теперішньому вигляді.
Печатки більше не показують CHANGED, і gate не зупиняє через них audit.

## Демонстрація на хвилину
```
python3 .claude/hooks/testing.py check access-shell          # match: 11 sealed test file(s) of access-shell
python3 .claude/hooks/testing.py check one-task-to-calendar  # match: 6 sealed test file(s) of one-task-to-calendar
uv run pytest -q tests/test_store.py tests/test_auth_callback.py tests/test_config.py tests/test_credentials.py \
  tests/test_error_log.py tests/test_imports.py tests/test_shell_access.py tests/test_entrypoint.py \
  tests/test_smoke_script.py tests/test_one_task_planning.py  # 66 passed
```
Запис у журналі тестування: `.engine/testing/ledger.md`, розділи «2026-11-06T22:48:59Z — one-task-to-calendar — resealed on the owner's word»
і «2026-11-06T22:49:19Z — access-shell — resealed on the owner's word». Обидва посилаються на «так» у цій картці.

## Що зроблено
- Reseal виконано командою `python3 .claude/hooks/testing.py reseal <slug> --owner-answer 715-open-item-reseal-s1-s3`
  о 22:48–22:49Z, ще коли картка лежала в `blocked/`. У цій сесії я перевірив, що печатки збігаються (`check` для обох slice-ів дає `match`),
  і що у файлі печаток під ключем `resealed` є рядок `card: 715-open-item-reseal-s1-s3` з усіма десятьма файлами з питання.
- Повний `pytest`: 162 passed, 31 failed. Усі 31 падіння — у `tests/test_several_tasks_*.py`. Це запечатані contract tests
  slice-у several-tasks: його відкрито о 22:51:34Z, і коду для нього ще немає. RED тут очікуваний, і до цієї задачі він не стосується.
  162 зелені — та сама цифра, що й у картці.

## Витрати
Додаткових сесій Claude не було. Лише ця сесія runner-а.

## Діапазон commit-ів
`db058f2` (картка → doing) .. commit, який переносить задачу в `done/`.

## Відкладене
Нічого.

## Рішення, які я ухвалив сам
- Reseal не повторював: `testing.py reseal` відмовляє повторно використати ту саму картку, а печатки вже збігаються.
  Тому я перевірив результат і нічого не запечатував наново.
