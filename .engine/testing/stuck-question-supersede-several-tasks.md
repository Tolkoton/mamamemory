# Supersede package — several-tasks, changed by the sealed contract stuck-question (owner's word 2026-11-11: «так»)

- `tests/test_several_tasks_disputed.py::test_duration_question_text_counts_timed_tasks_still_without_duration` — stuck-question Seam: «Текст питання тривалості завжди називає задачу: «Скільки часу займе «<назва>»?» — і для однієї задачі (раніше «Скільки часу це займе?»)». The test pins the old unnamed text «Скільки часу це займе?»; the new text names the task. Keep every other assertion (question kind, id, no calendar, order).

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
