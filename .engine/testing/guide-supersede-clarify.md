# Supersede package — clarify, changed by the sealed contract guide (F5 S2; owner: «запускай f1–f5», frame card 734)

- `tests/test_clarify.py::test_seam1_invalid_options_answer_as_other_and_write_no_clarification` — guide Seam «Незрозуміле»: `CANNOT_TEXT` = «Не зрозуміла. Скажіть «що ти вмієш?» — розкажу.» замість «Поки що я вмію записати одну задачу в календар.»; тест тримає старий текст чи префікс «Поки що я вмію». Переписати на новий текст; решта тверджень — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
