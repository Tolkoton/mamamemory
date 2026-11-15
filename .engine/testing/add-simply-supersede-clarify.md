# Supersede package — clarify, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Тести уточнення, що через «додай задачу» чекають питання тривалості: тепер «коли?» (чи план, якщо час названо).

- `tests/test_clarify.py::test_seam2_choice_replays_the_effective_reply_to_and_replace_asking`
- `tests/test_clarify.py::test_I2_the_chosen_variant_runs_once_with_the_text_mama_said`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
