# Supersede package — clarify, changed by the sealed contract show-schedule (owner's word 2026-11-12, «які плани на тиждень»)

show-schedule Seam: «`assistant`: намір `schedule` у `ROUTE_SCHEMA`, `ALWAYS`, `PHRASES["schedule"]`…»; Seam 3:
«`schedule` у схемі для кожного `reply_to`, в `allowed()`».

- `tests/test_clarify_disputed.py::test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to` —
  тримає набір `allowed()` без `schedule` для кожного `reply_to`. Додати `schedule` до очікуваного набору кожного
  `reply_to`; решта тверджень — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
