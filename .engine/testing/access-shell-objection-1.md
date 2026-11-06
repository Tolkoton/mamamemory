# Objection package 1 — access-shell (builder)

None of these items disputes what a test asserts. All 41 sealed tests pass. The Stop gate (`verify-on-stop.sh`) runs ruff and mypy --strict over `tests/` and has two complaints about the sealed files:

**A. mypy --strict errors in sealed tests** (from `uv run mypy src tests`; google-auth is now listed in `untyped_calls_exclude` in pyproject.toml, so the `Credentials` no-untyped-call errors are gone):
- tests/test_auth_callback.py:130 `return found[-1]` — no-any-return (declared `str`)
- tests/test_auth_callback.py:138 `return urlparse(resp.headers["location"]).path` — no-any-return
- tests/test_auth_callback.py:292 `jwt.encode(...).decode()` — no-any-return
- tests/test_auth_callback.py:369 `(posts[0].body or b"").decode()` — union-attr (the body type includes Iterable/SupportsRead)

**B. The bypass guard flags suppressions that have no `gate-allow` reason.** For each line, either remove the suppression by fixing the cause (for example, a typed fake or a `cast`), or keep it and add `# gate-allow: <why, two words at least>` on that line or the line above:
- tests/test_auth_callback.py:107 `# type: ignore[arg-type]` (fake Google passed to create_app)
- tests/test_auth_callback.py:399 `# noqa: B017`
- tests/test_credentials.py:83 `# type: ignore[arg-type]`
- tests/test_credentials.py:86 `# noqa: B008` (FastAPI `Depends` default)
- tests/test_credentials.py:177 `# noqa: B017`
- tests/test_credentials.py:185 `# type: ignore[arg-type]`
- tests/test_error_log.py:65 `# type: ignore[arg-type]`
- tests/test_shell_access.py:83 `# type: ignore[arg-type]`
- tests/test_shell_access.py:104 `# type: ignore[attr-defined]`

Contract line: `.engine/slices/access-shell.md`, Exit criterion. The tests and the lint/type gates must both be green.
Requested ruling: "the test was wrong" for its typing only. Change the typing, keep every assertion, and run `uv run mypy src tests` and `uv run ruff check tests` until both are green.
