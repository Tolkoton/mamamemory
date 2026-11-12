# Objection package 1 — priorities (builder)

This package has one item. It conflicts with a sealed test of an earlier slice. 252 of 253 tests pass against the code.

- `tests/test_priorities_planning.py::test_seam1_order_is_priorities_then_durations_in_new_order_then_limits_then_plan`.
  The test asserts at line 142 that the second duration question, asked when only NOTARY still lacks a duration, is
  `ask_named(NOTARY)`, i.e. «Скільки часу займе «подзвонити нотаріусу»?».
- The sealed several-tasks contract fixes this text: «з текстом «Скільки часу це займе?», коли така задача в
  чернетці одна (як S3), і «Скільки часу займе «<назва>»?», коли їх кілька». Its Q1, answered «taken», counts the
  timed tasks still without a duration at the moment of the question. The sealed test
  `tests/test_several_tasks_disputed.py::test_duration_question_text_counts_timed_tasks_still_without_duration`
  asserts the plain S3 text when exactly one remains.
- The priorities contract does not change the duration text. Its Seam 1 speaks only of the order of the questions.

Requested ruling: the test is wrong on this single line. The last remaining duration question uses the plain text
«Скільки часу це займе?» (several-tasks Q1). Keep the order of the questions, the first question named after MEDICINE,
and every other assertion. `uv run pytest -q` must be green.

Contract lines: several-tasks Seam `next_question` (duration text); priorities Seam 1.
