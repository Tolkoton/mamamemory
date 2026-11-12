"""Застосунок FastAPI: `create_app`, маршрути S1 (оболонка, вхід, маніфест, статика) і `/api/*` S3.

Одна обробка помилок перекладає власні помилки модулів у відповіді й пише в stdout один рядок без
токенів, cookie чи email. FastAPI живе лише в цьому пакеті.
"""

import dataclasses
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from mamamemory import access, assistant, cases, planning
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.errors import (
    AudioRejected,
    LoginExpired,
    MissingScopes,
    NotSignedIn,
    OAuthStateMismatch,
)
from mamamemory.integrations import tts
from mamamemory.integrations.ai import AI, speech
from mamamemory.integrations.files import Files
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Store
from mamamemory.integrations.tts import Speaker
from mamamemory.replies import Question, Reply

SESSION_COOKIE = "mm_session"
LOGIN_COOKIE = "mm_login"
WEB = Path(__file__).resolve().parents[1] / "web"
TO_LOGIN = "/auth/login"
FAILED_TEXT = "Не вдалося, спробуйте ще раз."
FAILED_SPEAK = "Не вдалося озвучити."
MAX_SPEAK_CHARS = 10_000
NOT_HEARD_TEXT = "Не почула, спробуйте ще раз."
API = "/api/"
CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{1,59}")
"""`X-Material-Id` — до 59 знаків, щоб похідний `"{id}-file"` вмістився в 64."""
UPLOAD_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "application/pdf", "text/plain"}
)
NOT_READ_TEXT = "Такий файл я не читаю. Надішліть фото або PDF."
EMPTY_FILE_TEXT = "Файл порожній."
"""Ідентифікатор від клієнта (`message_id`, `material_id`) — сегмент шляху Firestore без сюрпризів."""


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
    files: Files | None = None,
    speaker: Speaker | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config, app.state.store, app.state.google, app.state.now = config, store, google, now
    app.state.ai, app.state.calendar, app.state.files = ai, calendar, files
    app.state.speaker = speaker
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
        max_age_s=state.config.session_max_age_s,
    )
    return Session(
        account_id=claims.sub,
        google_credentials=partial(access.google_credentials, state.store, state.google, claims.sub),
    )


def _add_routes(app: FastAPI) -> None:
    app.add_api_route("/", _shell, methods=["GET"])
    app.add_api_route("/manifest.webmanifest", _manifest, methods=["GET"])
    app.add_api_route("/privacy", _privacy, methods=["GET"])
    app.add_api_route("/auth/login", _login, methods=["GET"])
    app.add_api_route("/auth/callback", _callback, methods=["GET"])
    app.add_api_route("/app.js", _script("app.js"), methods=["GET"])
    app.add_api_route("/reply_to.js", _script("reply_to.js"), methods=["GET"])
    app.add_api_route("/voice_state.js", _script("voice_state.js"), methods=["GET"])
    app.add_api_route("/recorder.js", _script("recorder.js"), methods=["GET"])
    app.add_api_route("/open_questions.js", _script("open_questions.js"), methods=["GET"])
    app.add_api_route("/message.js", _script("message.js"), methods=["GET"])
    app.add_api_route("/upload.js", _script("upload.js"), methods=["GET"])
    app.add_api_route("/speak.js", _script("speak.js"), methods=["GET"])
    app.add_api_route("/player.js", _script("player.js"), methods=["GET"])
    app.add_api_route("/speak_button.js", _script("speak_button.js"), methods=["GET"])
    app.add_api_route("/api/open", _open, methods=["GET"])
    app.add_api_route("/api/message", _message, methods=["POST"])
    app.add_api_route("/api/transcribe", _transcribe, methods=["POST"])
    app.add_api_route("/api/plan/confirm", _confirm, methods=["POST"])
    app.add_api_route("/api/case/confirm", _case_confirm, methods=["POST"])
    app.add_api_route("/api/upload", _upload, methods=["POST"])
    app.add_api_route("/api/clarify", _clarify, methods=["POST"])
    app.add_api_route("/api/speak", _speak, methods=["POST"])


def _shell(request: Request) -> Response:
    current_session(request)
    return FileResponse(WEB / "index.html", media_type="text/html")


def _open(request: Request) -> dict[str, Any]:
    """`GET /api/open` → `{replies, login_needed}` — незакриті питання на відкритті (S4)."""
    session = current_session(request)
    state = request.app.state
    now = state.now()
    found = assistant.open_questions(
        session,
        calendar=lambda: state.calendar(session, now),
        store=state.store,
        now=now,
        config=state.config,
    )
    for source in found.failed:
        _log_error(request, OpenQuestionSourceFailed(source), 200)
    return {"replies": [_reply_json(r) for r in found.replies], "login_needed": found.login_needed}


class SpeakTooLong(Exception):
    """Текст для озвучення понад `MAX_SPEAK_CHARS` (видно в журналі — тригер перегляду межі)."""


class SpeakerMissing(Exception):
    """Застосунок зібрано без озвучувача (`speaker=None`)."""


class OpenQuestionSourceFailed(Exception):
    """Одне джерело незакритих питань упало; у журнал іде лише назва типу."""


async def _message(request: Request) -> dict[str, Any]:
    """`{text, reply_to, message_id?}` → `Reply` (через `assistant.handle_message`)."""
    session, calendar, now = _api_call(request)
    body = await request.json()
    reply_to = Question(**body["reply_to"]) if body.get("reply_to") else None
    state = request.app.state
    message_id = body.get("message_id")
    lawful = isinstance(message_id, str) and CLIENT_ID.fullmatch(message_id) is not None
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
            message_id=message_id if lawful else uuid.uuid4().hex,
            deadline=_deadline(state.config, now),
            clock=state.now,
        ),
    )


async def _case_confirm(request: Request) -> dict[str, Any]:
    """`{material_id}` → `cases.confirm_case` без моделі маршрутизації (кнопка «так» під «Створити
    справу?»)."""
    session = current_session(request)
    now = request.app.state.now()
    body = await request.json()
    material_id = body.get("material_id")
    if not isinstance(material_id, str) or CLIENT_ID.fullmatch(material_id) is None:
        return _reply_json(Reply(cases.NOT_ACTUAL))
    state = request.app.state
    return _answer(
        request,
        lambda: cases.confirm_case(
            session,
            material_id,
            ai=state.ai,
            store=state.store,
            now=now,
            config=state.config,
            deadline=_deadline(state.config, now),
            clock=state.now,
        ),  # fmt: skip
    )


async def _clarify(request: Request) -> dict[str, Any]:
    """`{clarify_id, option}` → `assistant.answer_clarify` (кнопка під уточненням, clarify)."""
    session, calendar, now = _api_call(request)
    body = await request.json()
    clarify_id, option = body.get("clarify_id"), body.get("option")
    if not isinstance(clarify_id, str) or CLIENT_ID.fullmatch(clarify_id) is None or option not in (1, 2):
        return _reply_json(Reply(cases.NOT_ACTUAL))
    state = request.app.state
    return _answer(
        request,
        lambda: assistant.answer_clarify(
            session,
            clarify_id,
            option,
            ai=state.ai,
            calendar=calendar,
            store=state.store,
            config=state.config,
            now=now,
            deadline=_deadline(state.config, now),
            clock=state.now,
        ),  # fmt: skip
    )


async def _upload(request: Request) -> dict[str, Any]:
    """Фото чи файл (F3 S2): тіло — сам файл, `X-Material-Id`. Порядок: повтор лише заголовком → дороблення;
    тип; порожнє; завелике; інакше `cases.add_file`. Відмова — словами, без запису."""
    session = current_session(request)
    state = request.app.state
    now = state.now()
    header_id = request.headers.get("x-material-id", "")
    material_id = header_id if UPLOAD_ID.fullmatch(header_id) else uuid.uuid4().hex
    raw_type = request.headers.get("content-type")
    limit = state.config.max_upload_bytes
    data = await _body_at_most(request, limit + 1)
    mime = (raw_type or "").split(";", 1)[0].strip().lower()
    if data or raw_type:
        refusal = _refusal(mime, data, limit)
        if refusal is not None:
            return _reply_json(Reply(refusal))
    return _answer(
        request,
        lambda: cases.add_file(
            session,
            material_id,
            data or None,
            mime or None,
            ai=state.ai,
            files=state.files,
            store=state.store,
            now=now,
            config=state.config,
            deadline=_deadline(state.config, now),
            clock=state.now,
        ),  # fmt: skip
    )


def _refusal(mime: str, data: bytes, limit: int) -> str | None:
    if mime not in UPLOAD_TYPES:
        return NOT_READ_TEXT
    if not data:
        return EMPTY_FILE_TEXT
    if len(data) > limit:
        return f"Файл завеликий — до {limit // (1024 * 1024)} MB."
    return None


async def _body_at_most(request: Request, limit: int) -> bytes:
    """Тіло в пам'ять, але не більше `limit` байтів (решту не читає)."""
    received = bytearray()
    async for chunk in request.stream():
        received += chunk
        if len(received) >= limit:
            break
    return bytes(received)


async def _speak(request: Request) -> Response:
    """Flow (F5 S3): сесія (401) → `{text, part}` (400) → частина `part` тексту → TTS → 200 аудіо з `X-Parts`;
    помилка TTS чи немає озвучувача — 502, у журнал лише тип помилки (C1)."""
    session = current_session(request)
    state = request.app.state
    started = state.now()
    body = await _json_or_none(request)
    if isinstance(body, dict) and isinstance(body.get("text"), str) and len(body["text"]) > MAX_SPEAK_CHARS:
        _log_error(request, SpeakTooLong(), 400)
    chunks = _speak_parts(body)
    if chunks is None:
        return JSONResponse({"error": FAILED_SPEAK}, status_code=400)
    found, part = chunks
    try:
        if state.speaker is None:
            raise SpeakerMissing()
        language = await run_in_threadpool(access.language, session, state.store)
        audio = await run_in_threadpool(
            partial(
                state.speaker.say,
                found[part],
                language,
                deadline=_deadline(state.config, started),
                now=state.now,
            )
        )
    except Exception as exc:
        _log_error(request, exc, 502)
        return JSONResponse({"error": FAILED_SPEAK}, status_code=502)
    headers = {"Cache-Control": "no-store", "X-Parts": str(len(found))}
    return Response(audio, media_type="audio/ogg", headers=headers)


def _speak_parts(body: Any) -> tuple[list[str], int] | None:
    """Частини тексту й чинний номер `part` (лише JSON-ціле) — або `None`, коли запит нечинний."""
    if not isinstance(body, dict):
        return None
    text, part = body.get("text"), body.get("part")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_SPEAK_CHARS:
        return None
    found = tts.parts(text)
    if type(part) is not int or not 0 <= part < len(found):
        return None
    return found, part


async def _json_or_none(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError:
        return None


def _deadline(config: Config, started: datetime) -> datetime:
    """Дедлайн ланцюжка викликів запиту: таймаут запиту мінус два найдовші таймаути одного виклику."""
    return started + timedelta(seconds=config.request_timeout_s - 2 * config.call_timeout_s)


async def _transcribe(request: Request) -> Response:
    """Flow: сесія (401) → тип і тіло в пам'яті до межі (400) → розпізнавання → 200 `{text}`; помилка — 502.

    Тіло читається потоком у пам'ять і обривається, щойно межу перевищено; файлів і `store` звук не бачить."""
    session = current_session(request)
    state = request.app.state
    started = state.now()
    mime = request.headers.get("content-type", "")
    if mime.split(";", 1)[0].strip().lower().startswith("multipart/"):
        raise AudioRejected("multipart is not taken")
    audio = await _body_up_to(request, state.config.max_audio_bytes)
    deadline = started + timedelta(seconds=state.config.request_timeout_s - 2 * state.config.call_timeout_s)
    try:
        text = await run_in_threadpool(
            speech,
            audio,
            mime,
            language=await run_in_threadpool(access.language, session, state.store),
            deadline=deadline,
            client=state.ai.client(),
            config=state.config,
        )
    except AudioRejected:
        raise
    except Exception as exc:
        _log_error(request, exc, 502)
        return JSONResponse({"error": FAILED_TEXT}, status_code=502)
    return JSONResponse({"text": text})


async def _body_up_to(request: Request, limit: int) -> bytes:
    received = bytearray()
    async for chunk in request.stream():
        received += chunk
        if len(received) > limit:
            raise AudioRejected("audio over the limit")
    if not received:
        raise AudioRejected("empty audio")
    return bytes(received)


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


def _reply_json(reply: Reply) -> dict[str, Any]:
    """`Reply` як JSON; `choices` — лише під уточненням (clarify), щоб решта відповідей лишилась як була."""
    data = dataclasses.asdict(reply)
    if data.get("choices") is None:
        data.pop("choices", None)
    return data


def _answer(request: Request, handle: Callable[[], Reply]) -> dict[str, Any]:
    """Помилка моделі чи Calendar — «Не вдалося» без питання; рядок у журнал без подробиць."""
    try:
        reply = handle()
    except Exception as exc:
        _log_error(request, exc, 200)
        reply = Reply(FAILED_TEXT)
    return _reply_json(reply)


def _script(name: str) -> Callable[[Request], Response]:
    """Код застосунку — лише з чинною сесією, як і оболонка (I1 S1)."""

    def serve(request: Request) -> Response:
        current_session(request)
        return FileResponse(WEB / name, media_type="text/javascript")

    return serve


def _privacy() -> Response:
    """Політика конфіденційності для екрана входу Google — без сесії, без вмісту оболонки (ADR-0007)."""
    return FileResponse(WEB / "privacy.html", media_type="text/html")


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

    bad_state = partial(PlainTextResponse, "Вхід не вдався, спробуйте ще раз.", status_code=400)
    app.add_exception_handler(AudioRejected, _not_heard)
    for login_error in (NotSignedIn, LoginExpired, MissingScopes):
        app.add_exception_handler(login_error, _login_needed)
    app.add_exception_handler(OAuthStateMismatch, handler(400, bad_state))


def _not_heard(request: Request, exc: Exception) -> Response:
    _log_error(request, exc, 400)
    return JSONResponse({"error": NOT_HEARD_TEXT}, status_code=400)


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
        response.headers.setdefault("Cache-Control", "no-cache")
        return response
