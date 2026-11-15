# Supersede package — add-or-plan, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Тести режиму «додай задачу», що чекають питання тривалості чи меж: тепер — лише «коли?» (якщо часу не названо) або одразу план (60 хв за замовчуванням). Питання важливості в `add` і так не було.

- `tests/test_add_or_plan.py::test_seam1_add_reads_no_tasks_asks_no_priorities_and_shows_the_plan_at_once`
- `tests/test_add_or_plan.py::test_seam1_add_without_a_duration_asks_the_duration_not_the_priorities`
- `tests/test_add_or_plan.py::test_seam1_add_appended_to_an_unwritten_add_draft_reads_no_tasks`
- `tests/test_add_or_plan.py::test_seam1_add_with_saved_limits_applies_them_without_a_question`
- `tests/test_add_or_plan.py::test_seam1_add_without_saved_limits_asks_the_first_limits_question_once`
- `tests/test_add_or_plan.py::test_seam2_week_appended_to_an_add_draft_turns_it_into_week_with_tasks_once`
- `tests/test_add_or_plan.py::test_I1_add_never_reads_tasks_nor_asks_what_is_most_important`
- `tests/test_add_or_plan.py::test_I2_add_asks_limits_only_while_none_are_saved_and_never_places_outside_them`
- `tests/test_add_or_plan_disputed.py::test_Q1_next_question_itself_never_asks_the_priorities_in_add_mode`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
