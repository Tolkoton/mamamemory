# Objection package 2 — access-shell (builder)

This is one item I left out of package 1. It is about typing and lint only; no assertion is disputed.
- tests/test_store.py:90 `except Exception:  # noqa: BLE001 - the MagicMock client answers nothing useful`. The Stop gate's bypass guard flags it, because the reason is written after a dash and is not a `gate-allow` marker. Requested fix: put the reason on the line above as `# gate-allow: <reason>` (as was done for the B017 lines in package 1), or remove the cause. Keep the assertions as they are, and check that `uv run ruff check tests`, `uv run mypy src tests` and `uv run pytest` are green.
Contract line: `.engine/slices/access-shell.md`, Exit criterion.
