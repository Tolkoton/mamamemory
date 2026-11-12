# Supersede package — clarify, changed by the sealed contract working-on (F4 S1; owner: «запускай f1–f5», frame card 739)

- `tests/test_clarify_disputed.py::test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to` —
  working-on Seam: намір `working_on` додано в `ALWAYS` («`assistant`: намір `working_on` у `ROUTE_SCHEMA` (enum),
  `ALWAYS`…») і Seam 2 («`working_on` … в `allowed()` — тож `unsure` з options [`note`, `working_on`] дає уточнення»).
  Тест тримає старий набір `allowed()` без `working_on` для кожного `reply_to`. Додати `working_on` до очікуваного набору
  кожного `reply_to`; решта тверджень — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
