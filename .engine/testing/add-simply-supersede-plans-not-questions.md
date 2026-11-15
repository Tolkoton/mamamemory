# Supersede package — plans-not-questions, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Тести, що будують питання меж через «додай задачу»: у `add` меж більше не питають; питання меж — лише в плані тижня (`week=True`).

- `tests/test_plans_not_questions.py::test_seam1_limits_is_answer_true_saves_the_limits_as_before`
- `tests/test_plans_not_questions.py::test_seam2_plans_under_limits_of_add_a_task_keeps_the_draft`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
