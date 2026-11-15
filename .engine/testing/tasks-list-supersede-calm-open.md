# Supersede package — calm-open, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Тести, що порівнюють гайд з точним текстом (кнопка «Що я вмію», гайд першого відкриття): тепер у ньому рядок задач.

- `tests/test_calm_open.py::test_seam3_api_guide_with_session_answers_the_guide_without_question_and_writes_nothing`
- `tests/test_calm_open.py::test_seam3_api_guide_under_a_waiting_plan_question_changes_nothing`
- `tests/test_calm_open.py::test_I1_the_open_never_shows_planning_and_never_changes_the_plan_draft`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
