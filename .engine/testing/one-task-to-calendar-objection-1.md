# Objection package 1 — one-task-to-calendar (builder)

This is about the lint gate only; I dispute no assertion. All 100 tests pass against the code.
- tests/test_one_task_google_work.py:49 `def send(  # type: ignore[override]` in `Transport(BaseAdapter)`. The Stop gate's bypass guard flags a `type: ignore` that has no `gate-allow` reason.
- The requested fix: give the reason on the line directly above it as `# gate-allow: <reason, two words at least>`, for example: requests' BaseAdapter.send is typed with a narrower signature than the stand-in needs. Alternatively, remove the cause by matching `BaseAdapter.send`'s typed signature.
- Leave the assertions unchanged. `uv run mypy src tests`, `uv run ruff check tests` and `uv run pytest -q` must stay green.

Contract line: `.engine/slices/one-task-to-calendar.md`, Exit criterion (`pytest` зелений).
