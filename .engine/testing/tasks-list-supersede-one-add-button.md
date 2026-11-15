# Supersede package — one-add-button, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Тест, що тримає решту гайду «як було»: тепер у ньому і рядок задач.

- `tests/test_one_add_button.py::test_guide_has_the_plus_line_no_camera_and_the_rest_as_it_was`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
