"""Contract tests of the slice access-shell: sign-in through Google (Seam 1, Seam 1a).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import requests.adapters
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from requests.structures import CaseInsensitiveDict

from mamamemory.config import SCOPES, Config
from mamamemory.errors import MissingScopes
from mamamemory.http.app import create_app
from mamamemory.integrations.google_auth import Claims, GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore

KEY = "session-key-for-tests"
MAMA = "mama@example.com"
SUB = "1000000000000000001"
T0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)
CLIENT_ID = "client-id.apps.googleusercontent.com"
BASE_URL = "https://mamamemory.example"
FORBIDDEN_TEXT = "Цей акаунт не має доступу."
TASKS = "https://www.googleapis.com/auth/tasks"


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class FakeGoogle:
    """Returns the claims it is given; refuses an exchange without the code_verifier it issued."""

    def __init__(self, claims: Claims, exchange_error: Exception | None = None) -> None:
        self.claims = claims
        self.exchange_error = exchange_error
        self.issued: dict[str, str] = {}
        self.exchanges: list[tuple[str, str]] = []

    def authorization_url(self) -> tuple[str, str, str]:
        n = len(self.issued) + 1
        state, verifier = f"state-{n}", f"verifier-{n}-" + "v" * 43
        self.issued[state] = verifier
        return f"https://accounts.google.com/o/oauth2/auth?state={state}&n={n}", state, verifier

    def exchange(self, code: str, code_verifier: str) -> Tokens:
        self.exchanges.append((code, code_verifier))
        if code_verifier not in self.issued.values():
            raise RuntimeError("fake: exchange without the issued code_verifier")
        if self.exchange_error is not None:
            raise self.exchange_error
        return Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES))

    def verify_id_token(self, token: str) -> Claims:
        if token != "idt-1":
            raise RuntimeError("fake: unknown id token")
        return self.claims

    def refresh(self, tokens: Tokens) -> Credentials:
        return Credentials("fresh-at")


def make_config(base_url: str = "https://testserver") -> Config:
    return Config(
        allowed_emails=frozenset({MAMA}),
        gcp_project="pocket-lawyer-431614",
        firestore_database="mamamemory",
        vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com",
        region="europe-west3",
        oauth_client_id=CLIENT_ID,
        oauth_client_secret="client-secret",
        session_key=KEY,
        session_max_age_s=7 * 24 * 3600,
        login_max_age_s=600,
        base_url=base_url,
        request_timeout_s=30,
        call_timeout_s=10,
    )


class Rig:
    def __init__(self, claims: Claims | None = None, exchange_error: Exception | None = None) -> None:
        self.clock = Clock(T0)
        self.store = InMemoryStore()
        self.google = FakeGoogle(claims or Claims(sub=SUB, email=MAMA, email_verified=True), exchange_error)
        app = create_app(make_config(), self.store, cast(GoogleAuth, self.google), self.clock)
        self.client = TestClient(app, base_url="https://testserver", follow_redirects=False)

    def login(self) -> Any:
        return self.client.get("/auth/login")

    def callback(self, state: str = "state-1", code: str = "code-1") -> Any:
        return self.client.get("/auth/callback", params={"code": code, "state": state})

    def no_session(self, resp: Any) -> None:
        assert "mm_session" not in resp.cookies
        assert not any(
            h.lower().startswith("mm_session=")
            and "max-age=0" not in h.lower()
            and "expires=thu, 01 jan 1970" not in h.lower()
            for h in resp.headers.get_list("set-cookie")
        )
        assert self.store.get(self.google.claims.sub, "private/google") is None


def cookie_header(resp: Any, name: str) -> str:
    found = [h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{name}=")]
    assert found, f"no Set-Cookie for {name}"
    return str(found[-1])


def flags_of(header: str) -> set[str]:
    return {part.strip().lower() for part in header.split(";")[1:]}


def path_of(resp: Any) -> str:
    return str(urlparse(resp.headers["location"]).path)


# ------------------------------------------------------------------ Seam 1: the callback over HTTP


def test_login_redirects_to_google_and_sets_login_cookie_secure_httponly_lax() -> None:
    rig = Rig()
    resp = rig.login()
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://accounts.google.com/o/oauth2/auth?state=state-1&n=1"
    flags = flags_of(cookie_header(resp, "mm_login"))
    assert "secure" in flags
    assert "httponly" in flags
    assert "samesite=lax" in flags


def test_callback_allowed_email_sets_session_writes_tokens_and_redirects_home() -> None:
    rig = Rig()
    rig.login()
    resp = rig.callback()
    assert resp.status_code == 302
    assert path_of(resp) == "/"
    doc = rig.store.get(SUB, "private/google")
    assert doc is not None
    assert "rt-1" in json.dumps(doc, default=str)
    flags = flags_of(cookie_header(resp, "mm_session"))
    assert {"secure", "httponly", "samesite=lax"} <= flags
    home = rig.client.get("/")
    assert home.status_code == 200


def test_callback_exchanges_code_with_code_verifier_of_the_latest_login() -> None:
    rig = Rig()
    rig.login()
    rig.login()  # a second tab: its mm_login replaces the first
    resp = rig.callback(state="state-2", code="code-42")
    assert resp.status_code == 302
    assert path_of(resp) == "/"
    assert rig.google.exchanges == [("code-42", rig.google.issued["state-2"])]


def test_callback_email_not_allowed_is_403_without_session() -> None:
    rig = Rig(claims=Claims(sub="2000000000000000002", email="stranger@example.com", email_verified=True))
    rig.login()
    resp = rig.callback()
    assert resp.status_code == 403
    assert FORBIDDEN_TEXT in resp.text
    rig.no_session(resp)


def test_callback_email_not_verified_gives_no_session() -> None:
    rig = Rig(claims=Claims(sub=SUB, email=MAMA, email_verified=False))
    rig.login()
    resp = rig.callback()
    assert not (resp.status_code == 302 and path_of(resp) == "/")
    rig.no_session(resp)
    assert rig.client.get("/").status_code != 200


def test_callback_state_other_than_login_cookie_is_400() -> None:
    rig = Rig()
    rig.login()
    resp = rig.callback(state="state-forged")
    assert resp.status_code == 400
    rig.no_session(resp)
    assert rig.google.exchanges == []


def test_callback_second_tab_overwrites_login_cookie_so_first_callback_is_400() -> None:
    rig = Rig()
    rig.login()
    rig.login()
    resp = rig.callback(state="state-1")
    assert resp.status_code == 400
    rig.no_session(resp)


def test_callback_without_login_cookie_redirects_to_login() -> None:
    rig = Rig()
    resp = rig.callback(state="state-1")
    assert resp.status_code == 302
    assert path_of(resp) == "/auth/login"
    rig.no_session(resp)


def test_callback_with_login_cookie_expired_by_injected_now_redirects_to_login() -> None:
    rig = Rig()
    rig.login()
    rig.clock.at = T0 + timedelta(minutes=11)
    resp = rig.callback(state="state-1")
    assert resp.status_code == 302
    assert path_of(resp) == "/auth/login"
    rig.no_session(resp)


def test_callback_with_error_and_no_code_redirects_to_login() -> None:
    rig = Rig()
    rig.login()
    resp = rig.client.get("/auth/callback", params={"error": "access_denied", "state": "state-1"})
    assert resp.status_code == 302
    assert path_of(resp) == "/auth/login"
    rig.no_session(resp)


def test_callback_missing_scopes_redirects_to_login() -> None:
    rig = Rig(exchange_error=MissingScopes(frozenset({TASKS})))
    rig.login()
    resp = rig.callback()
    assert resp.status_code == 302
    assert path_of(resp) == "/auth/login"
    rig.no_session(resp)


# ------------------------------------------------------------------ Seam 1a: the real GoogleAuth


def _rsa_material() -> tuple[bytes, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return pem, cert.public_bytes(serialization.Encoding.PEM).decode()


PEM, CERT = _rsa_material()


def id_token_for(aud: str, email: str = MAMA, sub: str = SUB) -> str:
    t = int(time.time())  # verify_oauth2_token checks iat/exp against the real clock
    payload = {
        "iss": "https://accounts.google.com",
        "aud": aud,
        "azp": aud,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iat": t,
        "exp": t + 600,
    }
    token = cast(bytes, jwt.encode(crypt.RSASigner.from_string(PEM, "k1"), payload, key_id="k1"))
    return token.decode("ascii")


class GoogleServers(requests.adapters.BaseAdapter):
    """Stands in for Google's token endpoint (any POST) and certificate endpoint (GET …certs)."""

    def __init__(self, token_status: int = 200, token_body: Any = None) -> None:
        super().__init__()
        self.token_status, self.token_body = token_status, token_body
        self.sent: list[requests.PreparedRequest] = []

    def send(self, request: requests.PreparedRequest, *args: Any, **kwargs: Any) -> requests.Response:
        self.sent.append(request)
        if request.method == "GET" and "certs" in str(request.url):
            status, body = 200, {"k1": CERT}
        elif request.method == "POST":
            status, body = self.token_status, self.token_body
        else:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        resp = requests.Response()
        resp.status_code = status
        resp._content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        resp.headers = CaseInsensitiveDict({"Content-Type": "application/json"})
        resp.url = str(request.url)
        resp.request = request
        return resp

    def close(self) -> None:
        pass

    def token_posts(self) -> list[requests.PreparedRequest]:
        return [r for r in self.sent if r.method == "POST"]


def real_google(servers: GoogleServers) -> GoogleAuth:
    session = requests.Session()
    session.mount("https://", servers)
    return GoogleAuth(make_config(BASE_URL), token_adapter=servers, certs_request=GoogleRequest(session))


def token_response(scope: str) -> dict[str, Any]:
    return {
        "access_token": "at-real",
        "token_type": "Bearer",
        "expires_in": 3599,
        "refresh_token": "rt-real",
        "id_token": id_token_for(CLIENT_ID),
        "scope": scope,
    }


def test_real_authorization_url_asks_offline_consent_pkce_s256_all_scopes() -> None:
    google = real_google(GoogleServers())
    url, state, verifier = google.authorization_url()
    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert parsed.hostname == "accounts.google.com"
    assert set(query["scope"].split()) == set(SCOPES)
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["code_challenge_method"] == "S256"
    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert query["code_challenge"] == expected_challenge
    assert query["redirect_uri"] == f"{BASE_URL}/auth/callback"
    assert query["state"] == state
    assert query["client_id"] == CLIENT_ID


def test_real_exchange_sends_the_code_verifier_it_is_given() -> None:
    servers = GoogleServers(token_body=token_response(" ".join(SCOPES)))
    google = real_google(servers)
    _url, _state, verifier = google.authorization_url()
    google.exchange("code-7", verifier)
    posts = servers.token_posts()
    assert len(posts) == 1
    raw = posts[0].body
    body = parse_qs(raw.decode() if isinstance(raw, bytes) else str(raw or ""))
    assert body["code"] == ["code-7"]
    assert body["code_verifier"] == [verifier]


def test_real_exchange_without_tasks_scope_raises_missing_scopes() -> None:
    granted = [s for s in SCOPES if s != TASKS]
    google = real_google(GoogleServers(token_body=token_response(" ".join(granted))))
    _url, _state, verifier = google.authorization_url()
    with pytest.raises(MissingScopes) as caught:
        google.exchange("code-1", verifier)
    assert caught.value.missing == frozenset({TASKS})


def test_real_exchange_with_superset_or_reordered_scopes_succeeds() -> None:
    extra = "https://www.googleapis.com/auth/drive.file"
    for granted in [[*reversed(SCOPES), extra], list(reversed(SCOPES))]:
        google = real_google(GoogleServers(token_body=token_response(" ".join(granted))))
        _url, _state, verifier = google.authorization_url()
        tokens = google.exchange("code-1", verifier)
        assert tokens.access_token == "at-real"
        assert tokens.refresh_token == "rt-real"
        assert tokens.id_token
        assert tokens.scopes == frozenset(granted)


def test_real_verify_id_token_accepts_own_audience_and_refuses_another_client() -> None:
    google = real_google(GoogleServers())
    claims = google.verify_id_token(id_token_for(CLIENT_ID))
    assert claims == Claims(sub=SUB, email=MAMA, email_verified=True)
    # gate-allow: B017 — the contract names no error type for this refusal, so any exception is lawful
    with pytest.raises(Exception) as caught:  # noqa: B017
        google.verify_id_token(id_token_for("another-client.apps.googleusercontent.com"))
    assert not isinstance(caught.value, NotImplementedError)
