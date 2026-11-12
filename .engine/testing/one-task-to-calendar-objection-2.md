# Objection package 2 — one-task-to-calendar (builder, slice several-tasks of F2)

One item. The S3 contract and the newer sealed contract `.engine/slices/several-tasks.md` (F2, AC1 «і з кількох
поспіль») disagree on the same behaviour.

- `tests/test_one_task_planning.py::test_answer_to_old_duration_question_is_not_actual_and_keeps_current_draft`.
  The test calls `start("перша задача")`, then `start("друга задача")` while the duration is being asked. It expects
  the first question to be stale («Це питання вже не актуальне.»), with the second starting a new draft.
- The several-tasks Seam says: «якщо чернетка «питаю тривалість» чи «показано» і ще не записана — нові задачі
  додаються до неї (`order` продовжується), інакше — нова чернетка». The independent tester of several-tasks
  sealed `tests/test_several_tasks_planning.py::test_seam3_second_message_while_asking_adds_task_and_asks_first_without_duration`
  on that reading. Both tests cannot pass at once.
- The S3 contract text this test rests on («`plan_id`, що вже не поточна чернетка (стара відповідь після новішої
  задачі) → «Це питання вже не актуальне.»») still holds where the newer task starts a new draft, that is after
  «записано».

Requested ruling: the contract is ambiguous across the two slices, and the newer one governs (F2 extends F1).
Please rework the test so it keeps the S3 rule where it still applies. For example, an answer to the duration
question of a plan that was already written, after which a new task started a new draft, is «не актуальне», and the
current draft is unchanged. Leave every other assertion as it is. `uv run pytest -q` must be green.

Contract lines: S3 Seam `answer_duration` (`.engine/slices/one-task-to-calendar.md`); several-tasks Seam `start`.
