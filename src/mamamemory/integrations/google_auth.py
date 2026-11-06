"""Вхід Google: адреса входу з PKCE, обмін коду, перевірка ID token, оновлення токена.

Не робить: викликів Calendar чи Tasks (S3, F2).
"""

from dataclasses import dataclass
from typing import Any

import google.auth.transport.requests
import requests
import requests.adapters
from google.auth.exceptions import RefreshError
from google.oauth2 import id_token as google_id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from mamamemory.config import Config
from mamamemory.errors import LoginExpired, MissingScopes

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    id_token: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class Claims:
    sub: str
    email: str
    email_verified: bool


class GoogleAuth:
    """Справжня реалізація. `token_adapter` — транспорт до токен-сервера Google (у тестах підставний),
    `certs_request` — запит сертифікатів для перевірки ID token (у тестах підставний)."""

    def __init__(
        self,
        config: Config,
        token_adapter: requests.adapters.BaseAdapter | None = None,
        certs_request: google.auth.transport.requests.Request | None = None,
    ) -> None:
        self._config = config
        self._token_adapter = token_adapter
        self._certs_request = certs_request or google.auth.transport.requests.Request()

    def authorization_url(self) -> tuple[str, str, str]:
        """(url, state, code_verifier)."""
        flow = self._flow()
        url, state = flow.authorization_url(access_type="offline", prompt="consent")
        return url, state, str(flow.code_verifier)

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        """Обмін коду; неповні scopes — MissingScopes."""
        flow = self._flow()
        if self._token_adapter is not None:
            flow.oauth2session.mount("https://", self._token_adapter)
        try:
            flow.fetch_token(code=code, code_verifier=code_verifier)
            token: dict[str, Any] = dict(flow.oauth2session.token)
        except Warning as changed:
            token = _token_after_scope_change(changed, self._config.scopes)
        return _tokens(token)

    def verify_id_token(self, token: str) -> Claims:
        info = google_id_token.verify_oauth2_token(
            token, self._certs_request, audience=self._config.oauth_client_id
        )
        return Claims(
            sub=str(info["sub"]), email=str(info["email"]), email_verified=bool(info.get("email_verified"))
        )

    def refresh(self, tokens: Tokens) -> Credentials:
        """Оновлює токен; invalid_grant — LoginExpired."""
        credentials = Credentials(
            token=None,
            refresh_token=tokens.refresh_token,
            token_uri=TOKEN_URI,
            client_id=self._config.oauth_client_id,
            client_secret=self._config.oauth_client_secret,
            scopes=list(self._config.scopes),
        )
        try:
            credentials.refresh(self._token_request())
        except RefreshError as exc:
            if _is_invalid_grant(exc):
                raise LoginExpired("Google refused the refresh token") from exc
            raise
        return credentials

    def _flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": self._config.oauth_client_id,
                "client_secret": self._config.oauth_client_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=list(self._config.scopes),
            redirect_uri=f"{self._config.base_url}/auth/callback",
            autogenerate_code_verifier=True,
        )

    def _token_request(self) -> google.auth.transport.requests.Request:
        session = requests.Session()
        if self._token_adapter is not None:
            session.mount("https://", self._token_adapter)
        return google.auth.transport.requests.Request(session)


def _token_after_scope_change(changed: Warning, required: tuple[str, ...]) -> dict[str, Any]:
    granted = set(getattr(changed, "new_scope", None) or [])
    missing = frozenset(set(required) - granted)
    if missing:
        raise MissingScopes(missing)
    token: dict[str, Any] = dict(getattr(changed, "token", None) or {})
    return token


def _tokens(token: dict[str, Any]) -> Tokens:
    scope = token.get("scope", [])
    scopes = scope.split() if isinstance(scope, str) else list(scope)
    return Tokens(
        access_token=str(token["access_token"]),
        refresh_token=str(token.get("refresh_token", "")),
        id_token=str(token.get("id_token", "")),
        scopes=frozenset(scopes),
    )


def _is_invalid_grant(exc: RefreshError) -> bool:
    details = exc.args[1] if len(exc.args) > 1 else None
    return isinstance(details, dict) and details.get("error") == "invalid_grant"
