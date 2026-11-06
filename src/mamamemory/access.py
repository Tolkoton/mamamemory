"""Доступ: перевірка cookie сесії, дозволений акаунт, облікові дані Google. Без фреймворку.

Не робить: читання чи запису cookie в HTTP (це `http`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from itsdangerous import BadSignature, URLSafeSerializer

from mamamemory.errors import LoginExpired, NotAllowed, NotSignedIn
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.store import Store

SESSION_SALT = "session"
LOGIN_SALT = "login"
TOKENS_PATH = "private/google"


@dataclass(frozen=True)
class SessionClaims:
    sub: str
    email: str
    iat: int


@dataclass(frozen=True)
class Session:
    account_id: str
    google_credentials: Callable[[], Credentials]


def verify_session_cookie(
    cookie: str | None,
    now: datetime,
    *,
    key: str,
    allowed_emails: frozenset[str],
    max_age_s: int,
) -> SessionClaims:
    """Flow: підпис → вік → дозволений email."""
    payload = _load(cookie, key=key, salt=SESSION_SALT)
    claims = _session_claims(payload)
    if _age_s(claims.iat, now) > max_age_s:
        raise LoginExpired("session is older than allowed")
    if claims.email not in allowed_emails:
        raise NotAllowed("account is not allowed")
    return claims


def session_cookie_value(sub: str, email: str, now: datetime, *, key: str) -> str:
    return _dump({"sub": sub, "email": email, "iat": _epoch(now)}, key=key, salt=SESSION_SALT)


def login_cookie_value(state: str, code_verifier: str, now: datetime, *, key: str) -> str:
    """Значення `mm_login` (salt `login`)."""
    return _dump({"state": state, "verifier": code_verifier, "iat": _epoch(now)}, key=key, salt=LOGIN_SALT)


def read_login_cookie(cookie: str | None, now: datetime, *, key: str, max_age_s: int) -> tuple[str, str]:
    """(state, code_verifier) з `mm_login`; відсутнє чи прострочене — NotSignedIn."""
    payload = _load(cookie, key=key, salt=LOGIN_SALT)
    try:
        state, verifier, iat = str(payload["state"]), str(payload["verifier"]), int(payload["iat"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NotSignedIn("malformed login cookie") from exc
    if _age_s(iat, now) > max_age_s:
        raise NotSignedIn("login cookie expired")
    return state, verifier


def google_credentials(store: Store, google: GoogleAuth, account_id: str) -> Credentials:
    """Свіжі облікові дані Google акаунта; немає токенів чи Google їх не оновлює — LoginExpired."""
    stored = store.get(account_id, TOKENS_PATH)
    if stored is None:
        raise LoginExpired("no Google tokens for the account")
    return google.refresh(tokens_from_document(stored))


def tokens_document(tokens: Tokens, now: datetime) -> dict[str, Any]:
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "id_token": tokens.id_token,
        "scopes": sorted(tokens.scopes),
        "updated_at": now.isoformat(),
    }


def tokens_from_document(document: dict[str, Any]) -> Tokens:
    return Tokens(
        access_token=str(document.get("access_token", "")),
        refresh_token=str(document["refresh_token"]),
        id_token=str(document.get("id_token", "")),
        scopes=frozenset(document.get("scopes", [])),
    )


def _session_claims(payload: dict[str, Any]) -> SessionClaims:
    try:
        return SessionClaims(sub=str(payload["sub"]), email=str(payload["email"]), iat=int(payload["iat"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise NotSignedIn("malformed session cookie") from exc


def _dump(payload: dict[str, Any], *, key: str, salt: str) -> str:
    value: str = URLSafeSerializer(key, salt=salt).dumps(payload)
    return value


def _load(cookie: str | None, *, key: str, salt: str) -> dict[str, Any]:
    if not cookie:
        raise NotSignedIn("no cookie")
    try:
        payload = URLSafeSerializer(key, salt=salt).loads(cookie)
    except BadSignature as exc:
        raise NotSignedIn("bad signature") from exc
    if not isinstance(payload, dict):
        raise NotSignedIn("malformed cookie")
    return payload


def _epoch(now: datetime) -> int:
    return int(now.timestamp())


def _age_s(iat: int, now: datetime) -> int:
    return _epoch(now) - iat
