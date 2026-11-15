# Supersede package — skeleton-measure, changed by the sealed contract add-simply (owner's word 2026-11-14: «Коли його просять додати таску, значить треба що? Додати таску, а не мудрувати. Питати коли, спитати в котрій годині, а не коли ти робиш таски»)

Seam add-simply: «`planning.next_question(draft, ...)` для `mode == "add"`: ніколи `priorities`, `duration` чи `limits`; задача на час (`needs_time`, не записана, не прибрана) без `start_local` і без `when_set` — `Question("when", plan_id, None)` (перша така в порядку `order`); інакше `None` (показ плану). Тривалість `None` такої задачі при розміщенні — `ADD_DEFAULT_MIN` (60)»; текст «Коли «<назва>»? Скажіть день і годину.» / «О котрій годині «<назва>»?»; відповідь — `try_answer_when` (`SHORT_ANSWERS["when"]`, модель `parse_when`, `WHEN_SCHEMA {is_answer, day, start_local}`); `mode == "week"` — як було; I1 «Чернетка режиму `add` ніколи не питає тривалості, меж чи важливості».

Блокові тести f1-skeleton, що через «додай задачу» чекають питання тривалості (AC3 «one duration question», S2→S3, S1→S3, AC2, AC4…): тепер у режимі `add` питання тривалості немає (60 хв), а без часу — «коли?».

- `tests/test_f1_skeleton_integration.py::test_S1_to_S3_session_gives_the_plan_its_account_its_own_google_credentials_and_its_store`
- `tests/test_f1_skeleton_integration.py::test_S2_to_S3_recognised_text_goes_as_request_two_with_its_reply_to`
- `tests/test_f1_skeleton_integration.py::test_S3_to_S4_open_question_is_built_from_the_plan_draft`
- `tests/test_f1_skeleton_integration.py::test_AC1_install_from_chrome_and_any_google_account_signs_in_and_sees_only_its_own`
- `tests/test_f1_skeleton_integration.py::test_AC2_voice_shows_the_recognised_text_and_sending_it_again_plans`
- `tests/test_f1_skeleton_integration.py::test_AC3_proposed_time_one_duration_question_yes_writes_once`
- `tests/test_f1_skeleton_integration.py::test_AC4_closed_midway_the_next_open_shows_the_unclosed_plan`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
