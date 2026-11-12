# Objection package 1 — open-questions (builder)

All 37 tests pass against the code, and I dispute no assertion. The Stop gate's bypass guard flags three
`type: ignore` comments that carry no `gate-allow` reason:
- tests/test_open_questions_http.py:140 `app.calendar.list_events = broken  # type: ignore[method-assign]`
- tests/test_open_questions.py:265 `w.calendar.list_events = broken  # type: ignore[method-assign,assignment]`
- tests/test_open_questions.py:343 (the same line)

Requested fix: remove the cause, for example with `monkeypatch.setattr(w.calendar, "list_events", broken)`, which
mypy accepts, or with a failing FakeCalendar subclass in the test file. Otherwise, put `# gate-allow: <reason>`
on the line directly above each one. Leave the assertions as they are. `uv run mypy src tests`,
`uv run ruff check tests` and `uv run pytest -q` must stay green.

Contract line: `.engine/slices/open-questions.md`, Exit criterion (`pytest` зелений).
