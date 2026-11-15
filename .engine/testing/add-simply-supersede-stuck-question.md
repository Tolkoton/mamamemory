# Supersede package — stuck-question, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Тести stuck-question, що будують «питаю» через «додай задачу» (`week=False`) і чекають питання тривалості чи меж: тепер чернетка `add` питає «коли?». Те, що тримає stuck-question (не-відповідь — не відповідь; 24 год; нова задача під питанням — нова чернетка), лишається — його можна тримати тим самим через питання «коли?» (`try_answer_when`) або через чернетку тижня (`week=True`), де тривалість і межі питаються як було.

- `tests/test_stuck_question.py::test_seam3_duration_question_for_one_task_names_it_at_start_and_on_open`
- `tests/test_stuck_question.py::test_try_answer_duration_not_a_positive_integer_is_none_and_keeps_the_draft`
- `tests/test_stuck_question.py::test_try_answer_duration_with_a_duration_answers_as_f2`
- `tests/test_stuck_question.py::test_try_answer_limits_naming_nothing_is_none_and_keeps_the_draft`
- `tests/test_stuck_question.py::test_try_answer_limits_with_limits_answers_as_f2`
- `tests/test_stuck_question.py::test_answer_duration_unparsed_still_repeats_the_question`
- `tests/test_stuck_question.py::test_seam1_new_task_under_the_duration_question_starts_a_new_draft_with_only_it`
- `tests/test_stuck_question.py::test_seam1_plan_week_under_the_duration_question_starts_a_new_draft_with_what_was_said`
- `tests/test_stuck_question.py::test_seam1_half_an_hour_under_the_duration_question_is_the_duration_as_f2`
- `tests/test_stuck_question.py::test_seam1_other_under_the_duration_question_is_cannot_and_keeps_the_draft`
- `tests/test_stuck_question.py::test_seam1_new_task_under_the_limits_question_starts_a_new_draft_with_only_it`
- `tests/test_stuck_question.py::test_seam1_other_under_the_limits_question_is_cannot_and_keeps_the_draft`
- `tests/test_stuck_question.py::test_seam1_limits_named_under_the_limits_question_are_the_answer_as_f2`
- `tests/test_stuck_question.py::test_start_with_replace_asking_starts_a_new_draft_over_an_asking_one`
- `tests/test_stuck_question.py::test_seam2_asking_draft_older_than_24h_is_not_shown_and_nothing_is_written`
- `tests/test_stuck_question.py::test_seam2_asking_draft_without_asked_at_and_horizon_end_is_not_shown`
- `tests/test_stuck_question.py::test_seam2_asking_draft_without_asked_at_is_aged_from_horizon_end_minus_the_horizon`
- `tests/test_stuck_question.py::test_seam2_asking_draft_younger_than_24h_is_shown`
- `tests/test_stuck_question.py::test_seam2_start_after_24h_begins_a_new_draft_without_the_old_task`
- `tests/test_stuck_question.py::test_seam2_start_before_24h_appends_as_f2`
- `tests/test_stuck_question.py::test_I1_a_phrase_that_is_no_answer_never_gives_the_same_question_again`
- `tests/test_stuck_question.py::test_I2_a_question_older_than_24h_is_never_shown_nor_captures_a_message`
- `tests/test_stuck_question_disputed.py::test_q1_asking_draft_exactly_24h_old_is_still_shown`
- `tests/test_stuck_question_disputed.py::test_q2_shown_plan_older_than_24h_is_shown_until_the_horizon_as_f2`
- `tests/test_stuck_question_disputed.py::test_q4_the_new_draft_that_replaces_an_asking_one_has_a_new_plan_id`
- `tests/test_stuck_question_disputed.py::test_q5_new_task_under_the_limits_question_asks_the_limits_of_the_new_draft`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
