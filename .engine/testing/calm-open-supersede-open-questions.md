# Supersede package — open-questions, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`assistant.open_questions(...)`: не викликає `planning.open_question`; повертає лише гайд першого відкриття і питання справ (як було); `login_needed` — завжди `False` (джерелом був лише план). … план показується лише у відповідь на повідомлення мами; прохання увійти знову — на першому повідомленні, що йде до календаря»; I1 «Відкриття ніколи не показує відповіді планування і не змінює чернетку плану»; знято AC4 f1-skeleton і гарантію «S3 → S4».

Тести `open_questions` / `GET /api/open`, що чекають відповідь планування, `login_needed: true` чи `failed == ['planning']`: тепер `/api/open` планування не показує, календар не кличе, `login_needed` — `false`. Тести самого `planning.open_question` (функція лишається) — не чіпати, якщо вони зелені.

- `tests/test_open_questions.py::test_open_questions_returns_the_source_reply`
- `tests/test_open_questions.py::test_open_questions_login_needed_from_source`
- `tests/test_open_questions.py::test_open_questions_failed_source_is_skipped_and_named`
- `tests/test_open_questions_http.py::test_open_returns_shown_plan_with_its_question`
- `tests/test_open_questions_http.py::test_open_with_expired_google_sign_in_gives_login_needed`
- `tests/test_open_questions_http.py::test_open_asking_duration_needs_no_calendar_even_when_sign_in_expired`
- `tests/test_open_questions_http.py::test_open_with_calendar_error_is_empty_not_failed_and_logs_one_line`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
