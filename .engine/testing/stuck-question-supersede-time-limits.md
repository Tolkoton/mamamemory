# Supersede package — time-limits, changed by the sealed contract stuck-question (owner's word 2026-11-11: «так»)

- `tests/test_time_limits_planning.py::test_seam2_order_is_duration_then_limits_then_plan` — stuck-question Seam: «Текст питання тривалості завжди називає задачу: «Скільки часу займе «<назва>»?» — і для однієї задачі (раніше «Скільки часу це займе?»)». The test pins the old unnamed text «Скільки часу це займе?»; the new text names the task. Keep every other assertion (question kind, id, no calendar, order).
- `tests/test_time_limits_planning.py::test_seam3_limits_answer_while_duration_is_asked_returns_the_duration_question` — stuck-question Seam: «Текст питання тривалості завжди називає задачу: «Скільки часу займе «<назва>»?» — і для однієї задачі (раніше «Скільки часу це займе?»)». The test pins the old unnamed text «Скільки часу це займе?»; the new text names the task. Keep every other assertion (question kind, id, no calendar, order).

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
