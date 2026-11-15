# Supersede package — guide, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Тести, що тримають точний текст `GUIDE_UK` (9 рядків): тепер у ньому рядок задач одразу перед рядком 🔊. Решта поведінки гайду — без змін.

- `tests/test_guide.py::test_guide_text_is_the_contract_text_for_uk_and_the_same_for_another_language`
- `tests/test_guide.py::test_seam1_first_open_without_the_flag_is_the_guide_alone_and_writes_the_flag`
- `tests/test_guide.py::test_seam1_guide_stands_before_every_item_and_the_question_stays_last`
- `tests/test_guide.py::test_seam1_second_open_has_no_guide_and_the_items_as_before`
- `tests/test_guide.py::test_seam1_with_the_accounts_flag_there_is_no_guide_and_the_flag_is_kept`
- `tests/test_guide.py::test_seam1_flag_write_failure_shows_the_guide_and_the_next_open_shows_it_again`
- `tests/test_guide.py::test_seam1_each_account_has_its_own_guide`
- `tests/test_guide.py::test_seam2_help_answers_the_guide_writes_no_flag_and_changes_nothing`
- `tests/test_guide.py::test_seam2_help_under_a_case_question_or_a_plan_question_is_the_guide_too`
- `tests/test_guide.py::test_I1_guide_once_without_the_flag_never_with_it_and_never_in_the_question_place`
- `tests/test_guide_disputed.py::test_Q1_guide_text_is_the_contract_block_character_for_character`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
