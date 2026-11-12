# Supersede package — one-task-to-calendar, changed by the sealed contract stuck-question (owner's word 2026-11-11: «так»)

- `tests/test_one_task_planning.py::test_start_without_duration_asks_for_it` — stuck-question Seam: «Текст питання тривалості завжди називає задачу: «Скільки часу займе «<назва>»?» — і для однієї задачі (раніше «Скільки часу це займе?»)». The test pins the old unnamed text «Скільки часу це займе?»; the new text names the task. Keep every other assertion (question kind, id, no calendar, order).

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
