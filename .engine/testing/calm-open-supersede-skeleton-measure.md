# Supersede package — skeleton-measure, changed by the sealed contract calm-open (owner's word 2026-11-13: «Коли перший оцей надпис рандомний … що це за чепуха?»; «У мене на сьогодні точно немає таких тасок»)

Seam calm-open: «`assistant.open_questions(...)`: не викликає `planning.open_question`; повертає лише гайд першого відкриття і питання справ (як було); `login_needed` — завжди `False` (джерелом був лише план). … план показується лише у відповідь на повідомлення мами; прохання увійти знову — на першому повідомленні, що йде до календаря»; I1 «Відкриття ніколи не показує відповіді планування і не змінює чернетку плану»; знято AC4 f1-skeleton і гарантію «S3 → S4».

Блокові тести f1-skeleton, що чекають план чи «увійди знову» з `/api/open` (S3→S4, AC4, рядок про план на `/api/open` у тесті акаунтів AC1): гарантію знято новішим словом власника; план показується у відповідь на повідомлення («сплануй тиждень» продовжує чернетку), не на відкритті. Розділення акаунтів у AC1 — перевіряти тим самим, але без плану на `/api/open`.

- `tests/test_f1_skeleton_integration.py::test_S3_to_S4_open_question_is_built_from_the_plan_draft`
- `tests/test_f1_skeleton_integration.py::test_AC1_install_from_chrome_and_any_google_account_signs_in_and_sees_only_its_own`
- `tests/test_f1_skeleton_integration.py::test_AC4_closed_midway_the_next_open_shows_the_unclosed_plan`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
