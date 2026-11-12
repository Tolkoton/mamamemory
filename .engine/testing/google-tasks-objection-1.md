# Objection package 1 — google-tasks (builder)

This package has one item. It conflicts with a sealed rule of an earlier slice. 287 of 288 tests pass against the code.

- The test is `tests/test_google_tasks_planning.py::test_I1_task_from_tasks_is_never_created_in_tasks_and_its_event_gets_closed`,
  scenario (d), around line 528. The closing failed, then `start("і зателефонувати сестрі")` appends a task. The test
  expects the reply to carry a plan (`shown(reply)`).
- After the append, the draft holds two unwritten tasks: PARCEL from Tasks, without time, and the new SISTER. The
  sealed priorities contract says: «Задача, дописана до чернетки після відповіді …, скидає `priorities_answered`, якщо
  незаписаних задач стає дві й більше, — питання ставиться знову з новою задачею в кінці списку». The sealed test
  `tests/test_priorities_planning.py::test_seam1_task_added_after_the_answer_asks_again_with_the_new_task_last`
  asserts it. The world of this test has `ask_priorities=True`, and google-tasks Q4 (answered «taken») counts the
  Tasks task towards the two.
- So the reply after the append is the priorities question, not a plan.

Requested ruling: the test is wrong in scenario (d) only. After the append, answer the priorities question (for
example «same») and take the plan from that reply. Keep the scenario's assertions as they are: `holds(w)`, one read of
Tasks, BILLS still has its `event_id`, and then «так» on the plan closes it. `uv run pytest -q` must be green.

Contract lines: priorities Seam (appending resets `priorities_answered`); google-tasks Q4.
