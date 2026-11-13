# Supersede package — clarify, changed by the sealed contract case-recall (F4 S3)

case-recall Seam: «`assistant`: намір `recall` у `ROUTE_SCHEMA`, `ALWAYS`…»; Seam 3: «`recall` у схемі для кожного
`reply_to`, в `allowed()`»; поправки: «набори `allowed()` у `tests/test_clarify_disputed.py` — `recall`».

- `tests/test_clarify_disputed.py::test_Q1_route_schema_options_lists_only_the_intents_allowed_for_the_reply_to` —
  набір `allowed()` без `recall`; додати `recall` до очікуваного набору кожного `reply_to`; решта — як була.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
