# PROGRESS

## Slice S1 — access-shell (CODE COMPLETE — SMOKE PENDING, 2026-11-05)

- Module: `src/mamamemory/` — config, errors, access, integrations/store, integrations/google_auth, http/app, main, web (~520 LOC)
- Tests: 41 contract tests (slice-tester, sealed, 8 files), all green; ruff, mypy strict clean
- Smoke: PARKED — see tasks/blocked/701-open-item-f1-oauth-client.md (клієнт OAuth у Cloud Console і мамина адреса — лише власник); `scripts/smoke_access_shell.py <BASE_URL>` після розгортання Соньком
- Surprises: oauthlib на неповні scopes кидає `Warning` (перехоплено в `exchange`); venv на Python 3.13, google-auth-oauthlib 1.5.0 / oauthlib 4.0.1 — поведінку перевірено тестувальником
- Open for next slice: `store.transact` — S3; «увійди знову» — S4

## Slice S3 — one-task-to-calendar (CODE COMPLETE — DEPLOY PENDING, 2026-11-06)

- Modules: src/mamamemory/planning/{__init__,placement,plan}.py, assistant.py, replies.py,
  integrations/{google_work,ai}.py, store.transact, http `/api/message`, `/api/plan/confirm`, web/{app,reply_to}.js
- Tests: 46 contract tests of the independent tester (sealed), 100 in all green; `node --test` of reply_to.js green
- Smoke / tracer: PARKED — needs the OAuth client and mama's address (tasks/blocked/701)
- Surprises: `node --test src/mamamemory/web/` (exit criterion) fails on Node 24 for a directory — run the file
  `node --test src/mamamemory/web/*.test.js` (tester's Q9)
- Open for next slice: route-model schema is the builder's (`{intent: yes|new_task|other}`, untested — Q6)
