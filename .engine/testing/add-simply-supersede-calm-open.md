# Supersede package — calm-open, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Тест, що будує «питаю» (тривалість, режим `add`) через «додай задачу»: тепер `add` питає «коли?»; суть тесту calm-open (вступ без планування) лишається.

- `tests/test_calm_open.py::test_seam1_fresh_asking_draft_with_a_case_question_gives_only_the_case_question`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
