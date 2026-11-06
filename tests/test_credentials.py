"""Contract tests of the slice access-shell: Google credentials of the account (Seam 2) and the
`current_session` dependency.

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

import json
import time
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import pytest
import requests
import requests.adapters
from fastapi import Depends
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from requests.structures import CaseInsensitiveDict

from mamamemory import access
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.errors import LoginExpired
from mamamemory.http.app import create_app, current_session
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore

KEY = "session-key-for-tests"
MAMA = "mama@example.com"
SUB = "1000000000000000001"
T0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


class FakeGoogle:
    def __init__(self) -> None:
        self.issued: dict[str, str] = {}
        self.refreshed: list[Tokens] = []
        self.fresh = Credentials("fresh-at")

    def authorization_url(self) -> tuple[str, str, str]:
        n = len(self.issued) + 1
        state, verifier = f"state-{n}", f"verifier-{n}-" + "v" * 43
        self.issued[state] = verifier
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state, verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        if code_verifier not in self.issued.values():
            raise RuntimeError("fake: exchange without the issued code_verifier")
        return Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES))

    def verify_id_token(self, token: str) -> Claims:
        return Claims(sub=SUB, email=MAMA, email_verified=True)

    def refresh(self, tokens: Tokens) -> Credentials:
        self.refreshed.append(tokens)
        return self.fresh


def make_config() -> Config:
    return Config(
        allowed_emails=frozenset({MAMA}),
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id="client-id.apps.googleusercontent.com",
        oauth_client_secret="client-secret",
        session_key=KEY,
        session_max_age_s=7 * 24 * 3600,
        login_max_age_s=600,
        base_url="https://testserver",
        request_timeout_s=30,
        call_timeout_s=10,
    )


def signed_in_store(google: FakeGoogle) -> tuple[InMemoryStore, TestClient]:
    """The account's tokens written the way the app writes them: through the sign-in."""
    store = InMemoryStore()
    app = create_app(make_config(), store, cast(GoogleAuth, google), lambda: T0)

    @app.get("/probe-session")
    def probe(session: Annotated[Session, Depends(current_session)]) -> dict[str, str]:
        creds = session.google_credentials()
        return {"account_id": session.account_id, "token": str(creds.token)}

    app.router.routes.insert(0, app.router.routes.pop())  # ahead of any catch-all route of the app
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    client.get("/auth/login")
    done = client.get("/auth/callback", params={"code": "code-1", "state": "state-1"})
    assert done.status_code == 302
    assert store.get(SUB, "private/google") is not None
    return store, client


class TokenServer(requests.adapters.BaseAdapter):
    def __init__(self, status: int, body: Any) -> None:
        super().__init__()
        self.status, self.body = status, body
        self.posts = 0

    def send(self, request: requests.PreparedRequest, *args: Any, **kwargs: Any) -> requests.Response:
        if request.method != "POST":
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        self.posts += 1
        if isinstance(self.body, Exception):
            raise self.body
        resp = requests.Response()
        resp.status_code = self.status
        resp._content = self.body.encode() if isinstance(self.body, str) else json.dumps(self.body).encode()
        resp.headers = CaseInsensitiveDict({"Content-Type": "application/json"})
        resp.url = str(request.url)
        resp.request = request
        return resp

    def close(self) -> None:
        pass


def real_google(server: TokenServer) -> GoogleAuth:
    session = requests.Session()
    session.mount("https://", server)
    return GoogleAuth(make_config(), token_adapter=server, certs_request=GoogleRequest(session))


TOKENS = Tokens(access_token="", refresh_token="rt-1", id_token="", scopes=frozenset(SCOPES))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_real_refresh_returns_fresh_credentials() -> None:
    google = real_google(
        TokenServer(
            200,
            {
                "access_token": "fresh-real",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": " ".join(SCOPES),
            },
        )
    )
    creds = google.refresh(TOKENS)
    assert creds.token == "fresh-real"


def test_real_refresh_invalid_grant_is_login_expired() -> None:
    google = real_google(
        TokenServer(
            400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
        )
    )
    with pytest.raises(LoginExpired):
        google.refresh(TOKENS)


def test_real_refresh_other_failures_are_not_login_expired() -> None:
    for status, body in [
        (400, {"error": "invalid_client", "error_description": "Unauthorized"}),
        (400, "<html>Bad Request</html>"),  # a body that is not JSON: RefreshError with one argument
        (503, {"error": "backend_error"}),
    ]:
        server = TokenServer(status, body)
        with pytest.raises(RefreshError) as caught:
            real_google(server).refresh(TOKENS)
        assert not isinstance(caught.value, LoginExpired)
        if status == 400 and isinstance(body, dict):
            assert server.posts == 1, "invalid_client is not retried"

    server = TokenServer(0, requests.ConnectionError("network down"))
    # gate-allow: B017 — the contract only says the error is not LoginExpired, so any exception is lawful
    with pytest.raises(Exception) as raised:  # noqa: B017
        real_google(server).refresh(TOKENS)
    assert not isinstance(raised.value, (LoginExpired, NotImplementedError))


def test_google_credentials_reads_the_account_tokens_and_refreshes_through_google() -> None:
    google = FakeGoogle()
    store, _client = signed_in_store(google)
    creds = access.google_credentials(store, cast(GoogleAuth, google), SUB)
    assert creds is google.fresh
    assert [t.refresh_token for t in google.refreshed] == ["rt-1"]


def test_google_credentials_on_revoked_refresh_token_is_login_expired() -> None:
    store, _client = signed_in_store(FakeGoogle())
    revoked = real_google(
        TokenServer(
            400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
        )
    )
    with pytest.raises(LoginExpired):
        access.google_credentials(store, revoked, SUB)


def test_current_session_gives_account_id_sub_and_callable_google_credentials() -> None:
    google = FakeGoogle()
    _store, client = signed_in_store(google)
    google.refreshed.clear()
    resp = client.get("/probe-session")
    assert resp.status_code == 200
    assert resp.json() == {"account_id": SUB, "token": "fresh-at"}
    assert [t.refresh_token for t in google.refreshed] == ["rt-1"]
