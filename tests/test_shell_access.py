"""Contract tests of the slice access-shell: the session check and the shell behind it (I1).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import pytest
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access
from mamamemory.config import SCOPES, Config
from mamamemory.errors import LoginExpired, NotAllowed, NotSignedIn
from mamamemory.http.app import create_app
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore

KEY = "session-key-for-tests"
MAMA = "mama@example.com"
SUB = "1000000000000000001"
T0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)
WEEK_S = 7 * 24 * 3600
FORBIDDEN_TEXT = "Цей акаунт не має доступу."


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class FakeGoogle:
    def __init__(self, claims: Claims) -> None:
        self.claims = claims
        self.issued: dict[str, str] = {}

    def authorization_url(self) -> tuple[str, str, str]:
        state = f"state-{len(self.issued) + 1}"
        verifier = f"verifier-{len(self.issued) + 1}-" + "v" * 43
        self.issued[state] = verifier
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state, verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        if code_verifier not in self.issued.values():
            raise RuntimeError("fake: exchange without the issued code_verifier")
        return Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES))

    def verify_id_token(self, token: str) -> Claims:
        if token != "idt-1":
            raise RuntimeError("fake: unknown id token")
        return self.claims

    def refresh(self, tokens: Tokens) -> Credentials:
        return Credentials("fresh-at")


def make_config(allowed: frozenset[str] = frozenset({MAMA})) -> Config:
    return Config(
        allowed_emails=allowed,
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id="client-id.apps.googleusercontent.com",
        oauth_client_secret="client-secret",
        session_key=KEY,
        session_max_age_s=WEEK_S,
        login_max_age_s=600,
        base_url="https://testserver",
        request_timeout_s=30,
        call_timeout_s=10,
    )


def client_for(config: Config, clock: Clock) -> TestClient:
    google = FakeGoogle(Claims(sub=SUB, email=MAMA, email_verified=True))
    app = create_app(config, InMemoryStore(), cast(GoogleAuth, google), clock)
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


@pytest.fixture
def clock() -> Iterator[Clock]:
    yield Clock(T0)


def session_value(email: str = MAMA, at: datetime = T0, key: str = KEY) -> str:
    return access.session_cookie_value(SUB, email, at, key=key)


def forge(value: str) -> str:
    """The payload of `value` with the signature of another payload: a forged cookie."""
    payload, _ = value.rsplit(".", 1)
    _, signature = session_value(email="stranger@example.com").rsplit(".", 1)
    return f"{payload}.{signature}"


def location_path(resp: Any) -> str:
    return str(urlparse(resp.headers["location"]).path)


# ------------------------------------------------------------------ access: the pure check


def test_session_cookie_round_trip_gives_claims() -> None:
    value = session_value()
    claims = access.verify_session_cookie(
        value, T0 + timedelta(hours=1), key=KEY, allowed_emails=frozenset({MAMA}), max_age_s=WEEK_S
    )
    assert claims.sub == SUB
    assert claims.email == MAMA
    assert claims.iat == int(T0.timestamp())


def test_session_cookie_missing_or_forged_is_not_signed_in() -> None:
    good = session_value()
    forged = forge(good)
    other_key = session_value(key="another-key")
    for value in [None, "", "garbage", forged, other_key]:
        with pytest.raises(NotSignedIn):
            access.verify_session_cookie(
                value, T0, key=KEY, allowed_emails=frozenset({MAMA}), max_age_s=WEEK_S
            )


def test_session_cookie_age_up_to_max_age_is_accepted_older_is_login_expired() -> None:
    value = session_value()
    allowed = frozenset({MAMA})
    at_edge = access.verify_session_cookie(
        value, T0 + timedelta(seconds=WEEK_S), key=KEY, allowed_emails=allowed, max_age_s=WEEK_S
    )
    assert at_edge.sub == SUB
    with pytest.raises(LoginExpired):
        access.verify_session_cookie(
            value, T0 + timedelta(seconds=WEEK_S + 1), key=KEY, allowed_emails=allowed, max_age_s=WEEK_S
        )


def test_session_cookie_of_email_not_allowed_is_not_allowed() -> None:
    value = session_value(email="stranger@example.com")
    with pytest.raises(NotAllowed):
        access.verify_session_cookie(value, T0, key=KEY, allowed_emails=frozenset({MAMA}), max_age_s=WEEK_S)


# ------------------------------------------------------------------ http: the shell behind the check


def test_I1_no_shell_content_without_a_valid_session_of_an_allowed_account(clock: Clock) -> None:
    config = make_config()
    client = client_for(config, clock)

    # The anchor: with a valid session the shell is served on GET /.
    client.cookies.set("mm_session", session_value())
    shell = client.get("/")
    assert shell.status_code == 200
    shell_body = shell.text
    assert shell_body.strip()
    client.cookies.clear()

    login = client.get("/auth/login")
    login_value = login.cookies.get("mm_login")
    assert login_value
    client.cookies.clear()

    good = session_value()
    cases: list[tuple[str, str | None, Config, datetime]] = [
        ("no cookie", None, config, T0),
        ("forged", forge(good), config, T0),
        ("other key", session_value(key="another-key"), config, T0),
        ("expired by one second", good, config, T0 + timedelta(seconds=WEEK_S + 1)),
        ("account not allowed", session_value(email="stranger@example.com"), config, T0),
        (
            "allowed when signed in, removed from ALLOWED_EMAILS since",
            good,
            make_config(frozenset({"someone-else@example.com"})),
            T0,
        ),
        ("mm_login value as mm_session", login_value, config, T0),
        ("empty cookie", "", config, T0),
    ]
    paths = ["/", "/index.html", "/static/index.html", "/static/../index.html", "/anything", "/api/plan"]
    for label, value, cfg, at in cases:
        c = client_for(cfg, Clock(at))
        if value is not None:
            c.cookies.set("mm_session", value)
        for path in paths:
            resp = c.get(path)
            assert shell_body not in resp.text, f"{label}: {path} carried the shell"

    # Routes open without a session carry no shell content.
    c = client_for(config, clock)
    manifest = c.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert shell_body not in manifest.text


def test_root_without_session_redirects_to_login(clock: Clock) -> None:
    client = client_for(make_config(), clock)
    resp = client.get("/")
    assert resp.status_code == 302
    assert location_path(resp) == "/auth/login"


def test_root_with_forged_or_expired_session_redirects_to_login(clock: Clock) -> None:
    good = session_value()
    forged = forge(good)
    client = client_for(make_config(), clock)
    client.cookies.set("mm_session", forged)
    resp = client.get("/")
    assert resp.status_code == 302
    assert location_path(resp) == "/auth/login"

    late = client_for(make_config(), Clock(T0 + timedelta(seconds=WEEK_S + 1)))
    late.cookies.set("mm_session", good)
    resp = late.get("/")
    assert resp.status_code == 302
    assert location_path(resp) == "/auth/login"


def test_root_with_session_of_account_not_allowed_is_403_with_placeholder_text(clock: Clock) -> None:
    client = client_for(make_config(), clock)
    client.cookies.set("mm_session", session_value(email="stranger@example.com"))
    resp = client.get("/")
    assert resp.status_code == 403
    assert FORBIDDEN_TEXT in resp.text


def test_root_with_valid_session_serves_shell_with_no_cache(clock: Clock) -> None:
    client = client_for(make_config(), clock)
    client.cookies.set("mm_session", session_value())
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text.strip()
    directives = [d.strip().lower() for d in resp.headers.get("cache-control", "").split(",")]
    assert "no-cache" in directives


def test_manifest_and_icons_without_session_with_no_cache(clock: Clock) -> None:
    client = client_for(make_config(), clock)
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    assert "no-cache" in [d.strip().lower() for d in resp.headers.get("cache-control", "").split(",")]
    manifest = resp.json()
    assert manifest["name"]
    assert manifest["start_url"]
    assert manifest["display"] == "standalone"
    sizes = {size: icon["src"] for icon in manifest["icons"] for size in str(icon["sizes"]).split()}
    for size in ("192x192", "512x512"):
        assert size in sizes, f"no icon {size}"
        icon = client.get(urlparse(urljoin("https://testserver/manifest.webmanifest", sizes[size])).path)
        assert icon.status_code == 200, f"icon {size} not served without a session"
        assert "no-cache" in [d.strip().lower() for d in icon.headers.get("cache-control", "").split(",")]
