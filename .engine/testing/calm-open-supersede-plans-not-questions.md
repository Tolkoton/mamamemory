# Supersede package — plans-not-questions, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`planning.schedule.show`: у розділ «Задачі без часу:» ідуть лише задачі з `due` у періоді: від місцевої дати початку вікна включно до місцевої дати кінця вікна (кінець — північ, не включно), у порядку списку; задач з датою в періоді немає — розділу немає»; `TaskItem` дістав `due: date | None = None`; I2 «У розділі задач `show` кожна задача має `due` у періоді».

Тести розділу задач `show`, де фейкові задачі без `due`: тепер такі задачі не показуються; задача потрапляє в розділ лише з `due` у періоді. Решта (is_answer, dismiss_asking, події) — без змін.

- `tests/test_plans_not_questions.py::test_seam2_plans_under_priorities_of_the_week_shows_calendar_and_tasks_and_drops_the_draft`
- `tests/test_plans_not_questions.py::test_seam3_events_then_the_open_tasks_and_nothing_written`
- `tests/test_plans_not_questions.py::test_seam3_tasks_come_in_the_order_of_the_list`
- `tests/test_plans_not_questions.py::test_seam3_only_tasks_says_nothing_in_calendar_then_the_tasks`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
