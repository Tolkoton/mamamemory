# Supersede package — case-recall, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Тест, що тримає гайд у 9 рядків: тепер 10, рядок задач одразу перед 🔊.

- `tests/test_case_recall_route.py::test_seam3_guide_is_nine_lines_with_the_two_new_before_the_read_aloud_line`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
