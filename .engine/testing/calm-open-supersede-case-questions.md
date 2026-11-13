# Supersede package — case-questions, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`assistant.open_questions(...)`: не викликає `planning.open_question`; повертає лише гайд першого відкриття і питання справ (як було); `login_needed` — завжди `False` (джерелом був лише план). … план показується лише у відповідь на повідомлення мами; прохання увійти знову — на першому повідомленні, що йде до календаря»; I1 «Відкриття ніколи не показує відповіді планування і не змінює чернетку плану»; знято AC4 f1-skeleton і гарантію «S3 → S4».

Тести, що чекають план чи «увійди знову» на відкритті поруч із питаннями справ: тепер на відкритті лише питання справ (і гайд); помилка планування не може бути в `failed` (планування не читається). Питання справ, їх порядок і лічба «Ще N питань» — без змін.

- `tests/test_case_questions.py::test_open_with_two_materials_and_a_newer_plan_shows_the_plan_and_two_waiting`
- `tests/test_case_questions.py::test_open_with_a_material_newer_than_the_plan_shows_the_case_question_after_reopens`
- `tests/test_case_questions.py::test_open_plan_reply_without_question_is_shown_before_and_not_counted`
- `tests/test_case_questions.py::test_open_sign_in_again_is_shown_and_not_counted`
- `tests/test_case_questions.py::test_open_plan_failure_keeps_the_case_questions`
- `tests/test_case_questions.py::test_open_case_failure_keeps_the_plan`
- `tests/test_case_questions.py::test_open_without_pending_materials_is_the_plan_reply_as_before`
- `tests/test_case_questions.py::test_I3_one_question_with_reply_to_is_shown_last_and_the_rest_is_counted`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
