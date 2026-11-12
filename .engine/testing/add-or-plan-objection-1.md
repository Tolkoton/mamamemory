# Objection package 1 — add-or-plan (builder)

This package has one item. 21 of 22 tests pass against the code.

- `tests/test_add_or_plan.py::test_I2_add_asks_limits_only_while_none_are_saved_and_never_places_outside_them`, the
  last block (limits saved before any «додай»). It calls `w.add(...)` three times — NOTARY, then MEDICINE + SISTER, then
  NOTARY again — without «так» between them. The draft is unwritten after each call, so by the sealed several-tasks
  contract every later `start` **appends** to it (F2 S1: «кілька задач з повідомлення (і дописані поспіль, поки план не
  записано) в одній чернетці»). The third call therefore adds a second «подзвонити нотаріусу», and the helper `items()`
  fails with «an item shown twice» — not on the rule I2 checks (limits never asked, every item inside 14:00–18:00).
- The add-or-plan contract does not change appending, and does not ask to de-duplicate by title.

Requested ruling: the test is wrong in this block only. Make the three «додай» independent (confirm with «так» between
them, or use three different titles), keeping the assertions: no limits question, no «Як минулого разу», every item
within the afternoons. `uv run pytest -q` must be green.

Contract lines: add-or-plan Seam («дописане до незаписаної чернетки режиму `add` — теж без Tasks»); several-tasks S1.
