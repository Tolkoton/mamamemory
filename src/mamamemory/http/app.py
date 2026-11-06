"""Застосунок FastAPI: `create_app`, маршрути S1 (оболонка, вхід, маніфест, статика) і `/api/*` S3.

Одна обробка помилок перекладає власні помилки модулів у відповіді й пише в stdout один рядок без
токенів, cookie чи email. FastAPI живе лише в цьому пакеті.
"""

import dataclasses
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from mamamemory import access, assistant, planning
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.errors import LoginExpired, MissingScopes, NotAllowed, NotSignedIn, OAuthStateMismatch
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.replies import Question, Reply

SESSION_COOKIE = "mm_session"
LOGIN_COOKIE = "mm_login"
WEB = Path(__file__).resolve().parents[1] / "web"
FORBIDDEN_TEXT = "Цей акаунт не має доступу."
TO_LOGIN = "/auth/login"
FAILED_TEXT = "Не вдалося, спробуйте ще раз."
API = "/api/"


CalendarFactory = Callable[[Session, datetime], GoogleWork]
"""Календар запиту: з облікових даних сесії й моменту початку запиту (для дедлайну)."""


def create_app(
    config: Config,
    store: Store,
    google: GoogleAuth,
    now: Callable[[], datetime],
    *,
    ai: AI | None = None,
    calendar: CalendarFactory | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config, app.state.store, app.state.google, app.state.now = config, store, google, now
    app.state.ai, app.state.calendar = ai, calendar
    _add_error_handling(app)
    _add_no_cache(app)
    _add_routes(app)
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
    return app


def current_session(request: Request) -> Session:
    """Сесія запиту: підпис і вік cookie, дозволений акаунт; облікові дані Google — на вимогу."""
    state = request.app.state
    claims = access.verify_session_cookie(
        request.cookies.get(SESSION_COOKIE),
        state.now(),
        key=state.config.session_key,
        allowed_emails=state.config.allowed_emails,
        max_age_s=state.config.session_max_age_s,
    )
    return Session(
        account_id=claims.sub,
        google_credentials=partial(access.google_credentials, state.store, state.google, claims.sub),
    )


def _add_routes(app: FastAPI) -> None:
    app.add_api_route("/", _shell, methods=["GET"])
    app.add_api_route("/manifest.webmanifest", _manifest, methods=["GET"])
    app.add_api_route("/auth/login", _login, methods=["GET"])
    app.add_api_route("/auth/callback", _callback, methods=["GET"])
    app.add_api_route("/app.js", _script("app.js"), methods=["GET"])
    app.add_api_route("/reply_to.js", _script("reply_to.js"), methods=["GET"])
    app.add_api_route("/api/message", _message, methods=["POST"])
    app.add_api_route("/api/plan/confirm", _confirm, methods=["POST"])


def _shell(request: Request) -> Response:
    current_session(request)
    return FileResponse(WEB / "index.html", media_type="text/html")


async def _message(request: Request) -> dict[str, Any]:
    """`{text, reply_to}` → `Reply` (через `assistant.handle_message`)."""
    session, calendar, now = _api_call(request)
    body = await request.json()
    reply_to = Question(**body["reply_to"]) if body.get("reply_to") else None
    state = request.app.state
    return _answer(
        request,
        lambda: assistant.handle_message(
            session,
            str(body.get("text", "")),
            reply_to,
            ai=state.ai,
            calendar=calendar,
            store=state.store,
            config=state.config,
            now=now,
        ),
    )


async def _confirm(request: Request) -> dict[str, Any]:
    """`{plan_id, fingerprint}` → `Reply` (через `planning.confirm`)."""
    session, calendar, now = _api_call(request)
    body = await request.json()
    state = request.app.state
    return _answer(
        request,
        lambda: planning.confirm(
            session,
            str(body["plan_id"]),
            str(body["fingerprint"]),
            calendar=calendar,
            store=state.store,
            now=now,
            config=state.config,
        ),
    )


def _api_call(request: Request) -> tuple[Session, GoogleWork, datetime]:
    """Сесія (помилки входу → 401) і календар запиту від моменту його початку."""
    session = current_session(request)
    now = request.app.state.now()
    return session, request.app.state.calendar(session, now), now


def _answer(request: Request, handle: Callable[[], Reply]) -> dict[str, Any]:
    """Помилка моделі чи Calendar — «Не вдалося» без питання; рядок у журнал без подробиць."""
    try:
        reply = handle()
    except Exception as exc:
        _log_error(request, exc, 200)
        reply = Reply(FAILED_TEXT)
    return dataclasses.asdict(reply)


def _script(name: str) -> Callable[[Request], Response]:
    """Код застосунку — лише з чинною сесією, як і оболонка (I1 S1)."""

    def serve(request: Request) -> Response:
        current_session(request)
        return FileResponse(WEB / name, media_type="text/javascript")

    return serve


def _manifest() -> Response:
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")


def _login(request: Request) -> Response:
    state = request.app.state
    url, oauth_state, verifier = state.google.authorization_url()
    response = RedirectResponse(url, status_code=302)
    value = access.login_cookie_value(oauth_state, verifier, state.now(), key=state.config.session_key)
    _set_cookie(response, LOGIN_COOKIE, value, state.config.login_max_age_s)
    return response


def _callback(request: Request) -> Response:
    """Flow: відмова Google → cookie входу → state → обмін → ID token → дозволений → токени й сесія."""
    state = request.app.state
    code, returned_state = request.query_params.get("code"), request.query_params.get("state")
    if request.query_params.get("error") or not code:
        return _to_login()
    expected_state, verifier = access.read_login_cookie(
        request.cookies.get(LOGIN_COOKIE),
        state.now(),
        key=state.config.session_key,
        max_age_s=state.config.login_max_age_s,
    )
    if returned_state != expected_state:
        raise OAuthStateMismatch("state differs from the login cookie")
    tokens = state.google.exchange(code, verifier)
    claims = state.google.verify_id_token(tokens.id_token)
    if not claims.email_verified or claims.email not in state.config.allowed_emails:
        raise NotAllowed("account is not allowed")
    state.store.set(claims.sub, access.TOKENS_PATH, access.tokens_document(tokens, state.now()))
    response = RedirectResponse("/", status_code=302)
    value = access.session_cookie_value(claims.sub, claims.email, state.now(), key=state.config.session_key)
    _set_cookie(response, SESSION_COOKIE, value, state.config.session_max_age_s)
    response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax")
    return response


def _set_cookie(response: Response, name: str, value: str, max_age_s: int) -> None:
    response.set_cookie(name, value, max_age=max_age_s, secure=True, httponly=True, samesite="lax")


def _to_login() -> Response:
    return RedirectResponse(TO_LOGIN, status_code=302)


def _add_error_handling(app: FastAPI) -> None:
    def handler(status: int, make: Callable[[], Response]) -> Callable[[Request, Exception], Response]:
        def handle(request: Request, exc: Exception) -> Response:
            _log_error(request, exc, status)
            return make()

        return handle

    forbidden = partial(PlainTextResponse, FORBIDDEN_TEXT, status_code=403)
    bad_state = partial(PlainTextResponse, "Вхід не вдався, спробуйте ще раз.", status_code=400)
    for login_error in (NotSignedIn, LoginExpired, MissingScopes):
        app.add_exception_handler(login_error, _login_needed)
    app.add_exception_handler(NotAllowed, handler(403, forbidden))
    app.add_exception_handler(OAuthStateMismatch, handler(400, bad_state))


def _login_needed(request: Request, exc: Exception) -> Response:
    """На `/api/*` — 401 без `Location` (`fetch` не йде за 302 на Google); деінде — 302 на вхід S1."""
    if request.url.path.startswith(API):
        _log_error(request, exc, 401)
        return Response(status_code=401)
    _log_error(request, exc, 302)
    return _to_login()


def _log_error(request: Request, exc: Exception, status: int) -> None:
    line = {"event": "error", "kind": type(exc).__name__, "path": request.url.path, "status": status}
    print(json.dumps(line), flush=True)


def _add_no_cache(app: FastAPI) -> None:
    @app.middleware("http")
    async def no_cache(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response
