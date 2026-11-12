# Supersede package — voice-edits, changed by the sealed contract guide (F5 S2; owner: «запускай f1–f5», frame card 734)

- `tests/test_voice_edits_planning.py::test_seam3_what_is_not_an_edit_is_still_other` — guide Seam «Незрозуміле»: `CANNOT_TEXT` = «Не зрозуміла. Скажіть «що ти вмієш?» — розкажу.» замість «Поки що я вмію записати одну задачу в календар.»; тест тримає старий текст чи префікс «Поки що я вмію». Переписати на новий текст; решта тверджень — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
