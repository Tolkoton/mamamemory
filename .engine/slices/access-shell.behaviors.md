# access-shell — нотатки будівника (контракт запечатано: .engine/slices/access-shell.md)

## Step 0 — обсяг
- Seam — «Seam (contract)» контракту; точки входу, яких контракт не називав, — у каркасі:
  `config.load_config(environ)`, `integrations.store.document_path`, `FirestoreStore(project, database, client_factory)`,
  `InMemoryStore`, `GoogleAuth(config, token_adapter, certs_request)`, `Tokens`, `Claims`, `access.SessionClaims`,
  `access.login_cookie_value` / `read_login_cookie`, помилки — `mamamemory.errors`, `http` — пакет (`http/app.py`).
- Зовнішні залежності: Google OAuth 2.0 (google-auth-oauthlib 1.4.0, oauthlib 3.3.1, google-auth), Firestore.
- Не робить: Calendar/Tasks/Gemini, стан розмови, «увійди знову», service worker.
- Конвенції: Python 3.12, `src/` layout, pytest у `tests/`, ruff + mypy strict, frozen dataclasses.

## Step 1 — зовнішні документи
- Обмін коду, PKCE, Warning на scopes, RefreshError — перевірено критиками по коду бібліотек у кеші uv (контракт, «Premise verified»).
- Облікові дані: клієнт OAuth ще не створено (власник, Cloud Console) — розгортання й smoke чекають; тести локальні.

## Behaviors
Пише тестувальник (рішення менеджера (a) = tester).
