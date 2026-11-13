# Supersede package — time-limits, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`assistant.open_questions(...)`: не викликає `planning.open_question`; повертає лише гайд першого відкриття і питання справ (як було); `login_needed` — завжди `False` (джерелом був лише план). … план показується лише у відповідь на повідомлення мами; прохання увійти знову — на першому повідомленні, що йде до календаря»; I1 «Відкриття ніколи не показує відповіді планування і не змінює чернетку плану»; знято AC4 f1-skeleton і гарантію «S3 → S4».

Тест, що чекає питання меж серед відповідей `/api/open` чи `open_questions`: тепер його там немає (питання меж з'являється у відповідь на повідомлення). Тест самого `planning.open_question` — не чіпати.

- `tests/test_time_limits_planning.py::test_open_questions_of_the_page_show_the_limits_question`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
