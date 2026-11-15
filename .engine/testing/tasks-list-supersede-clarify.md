# Supersede package — clarify, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Тест, що тримає точний набір `ALWAYS` / варіантів уточнення: тепер у ньому і `tasks`.

- `tests/test_clarify_disputed.py::test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
