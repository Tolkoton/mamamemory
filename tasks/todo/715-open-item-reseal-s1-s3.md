# 715 — Перезапечатати тести S1 і S3 після змін за словом власника

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: reseal-s1-s3

## Що сталося
Тести S1 (access-shell: tests/test_store.py, tests/test_auth_callback.py, tests/test_config.py, tests/test_credentials.py, tests/test_error_log.py, tests/test_imports.py, tests/test_shell_access.py, tests/test_entrypoint.py, tests/test_smoke_script.py; переписані під open-sign-in) і S3 (one-task-to-calendar: tests/test_one_task_planning.py) змінено зі слова власника 2026-11-06 («703 треба прибрати.»; «Так,» на зміну тестів S1–S3 — escalations.md, OWNER). Твердження не змінено; 162 pytest зелені. Печатки показують CHANGED.

- Записано: 2026-11-06T22:44:18Z, агент

## Що зробити
Це питання до власника, не робота для агента. Коли власник відповість, задача повернеться в чергу: виконай відповідь, запиши її у звіт і закрий задачу.

## Готово, коли
Власник відповів, і відповідь виконано.

## Питання до власника
1. Перезапечатати тести access-shell і one-task-to-calendar у теперішньому вигляді?
   Відповідь: так
