# Supersede package — clarify, changed by the sealed contract work-recall (F4 S2; owner: «запускай f1–f5»; F4 frame — owner 2026-11-12)

work-recall Seam: «`assistant`: намір `work_question` у `ROUTE_SCHEMA`, `ALWAYS`, `PHRASES["work_question"]`…»; Seam 3:
«`work_question` у схемі для кожного `reply_to`, в `allowed()`».

- `tests/test_clarify_disputed.py::test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to` —
  тримає набір `allowed()` без `work_question` для кожного `reply_to`. Додати `work_question` до очікуваного набору
  кожного `reply_to`; решта тверджень — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
