"""Contract tests of the slice access-shell: the one error handling writes one clean line (журнал).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore

STRANGER = "stranger.person@example.com"
SECRETS = ("at-SECRET-access-token", "rt-SECRET-refresh-token", "idt-SECRET-id-token")
T0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


class FakeGoogle:
    def __init__(self) -> None:
        self.verifier = "verifier-1-" + "v" * 43

    def authorization_url(self) -> tuple[str, str, str]:
        return "https://accounts.google.com/o/oauth2/auth?state=state-1", "state-1", self.verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        if code_verifier != self.verifier:
            raise RuntimeError("fake: exchange without the issued code_verifier")
        return Tokens(
            access_token=SECRETS[0], refresh_token=SECRETS[1], id_token=SECRETS[2], scopes=frozenset(SCOPES)
        )

    def verify_id_token(self, token: str) -> Claims:
        return Claims(sub="2000000000000000002", email=STRANGER, email_verified=True)

    def refresh(self, tokens: Tokens) -> Credentials:
        return Credentials("fresh-at")


def make_config() -> Config:
    return Config(
        allowed_emails=frozenset({"mama@example.com"}),
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id="client-id.apps.googleusercontent.com",
        oauth_client_secret="client-secret",
        session_key="session-key-for-tests",
        session_max_age_s=7 * 24 * 3600,
        login_max_age_s=600,
        base_url="https://testserver",
        request_timeout_s=30,
        call_timeout_s=10,
    )


def test_error_through_the_one_handler_writes_one_stdout_line_without_token_cookie_or_email(
    capfd: pytest.CaptureFixture[str],
) -> None:
    app = create_app(make_config(), InMemoryStore(), cast(GoogleAuth, FakeGoogle()), lambda: T0)
    client = TestClient(
        app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
    )
    login = client.get("/auth/login")
    login_cookie = login.cookies.get("mm_login")
    assert login_cookie
    capfd.readouterr()

    resp = client.get("/auth/callback", params={"code": "code-SECRET-1", "state": "state-1"})
    assert resp.status_code == 403  # NotAllowed, translated by the one handler

    lines = [line for line in capfd.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    line = lines[0]
    for secret in (*SECRETS, login_cookie, STRANGER):
        assert secret not in line, f"the log line carries {secret!r}: {line}"
