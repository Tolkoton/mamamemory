# Supersede package — guide, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`assistant.open_questions(...)`: не викликає `planning.open_question`; повертає лише гайд першого відкриття і питання справ (як було); `login_needed` — завжди `False` (джерелом був лише план). … план показується лише у відповідь на повідомлення мами; прохання увійти знову — на першому повідомленні, що йде до календаря»; I1 «Відкриття ніколи не показує відповіді планування і не змінює чернетку плану»; знято AC4 f1-skeleton і гарантію «S3 → S4».

Тести гайду першого відкриття, що кладуть поруч план чи питання плану: тепер планових відповідей на відкритті немає; гайд першого відкриття, позначка `settings/guide_shown` і питання справ — без змін.

- `tests/test_guide.py::test_seam1_guide_stands_before_every_item_and_the_question_stays_last`
- `tests/test_guide.py::test_seam1_second_open_has_no_guide_and_the_items_as_before`
- `tests/test_guide.py::test_seam1_with_the_accounts_flag_there_is_no_guide_and_the_flag_is_kept`
- `tests/test_guide.py::test_seam1_flag_read_failure_shows_no_guide_keeps_the_items_and_names_guide_in_failed`
- `tests/test_guide.py::test_seam1_flag_write_failure_shows_the_guide_and_the_next_open_shows_it_again`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
