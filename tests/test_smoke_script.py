"""Catch-up contract tests of the slice access-shell: the smoke script `scripts/smoke_access_shell.py`.

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md` («Exit criterion»)
and the script's command line only (`scripts/smoke_access_shell.py <BASE_URL>`, its exit status). The
smoke runs over real HTTP against a local
uvicorn server holding the app of this slice (real `GoogleAuth`, in-memory store). A wrapper in front of
the app can break exactly one thing the smoke must check; the smoke must then fail.
"""

import json
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pytest
import uvicorn

from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.store import InMemoryStore

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_access_shell.py"

Headers = list[tuple[str, str]]
# (path, request headers, status, response headers, body) -> (status, response headers, body)
Rule = Callable[[str, dict[str, str], int, Headers, bytes], tuple[int, Headers, bytes]]
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class Breaker:
    """ASGI wrapper: with no rule the app answers as it is; with a rule one thing is broken."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app
        self.rule: Rule | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        rule = self.rule
        if scope["type"] != "http" or rule is None:
            await self.app(scope, receive, send)
            return
        request = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        start: dict[str, Any] = {}
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                start.update(message)
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in start["headers"]]
            status, headers, body = rule(scope["path"], request, start["status"], headers, b"".join(chunks))
            headers = [(k, v) for k, v in headers if k.lower() != "content-length"]
            headers.append(("content-length", str(len(body))))
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers],
                }
            )
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Deployment:
    def __init__(self, base: str, breaker: Breaker) -> None:
        self.base = base
        self.breaker = breaker


@pytest.fixture(scope="module")
def deployment() -> Iterator[Deployment]:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    config = Config(
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
        base_url=base,
        request_timeout_s=30,
        call_timeout_s=10,
    )
    app = create_app(config, InMemoryStore(), GoogleAuth(config), lambda: datetime.now(UTC))
    breaker = Breaker(app)
    server = uvicorn.Server(uvicorn.Config(breaker, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the local server did not start"
        time.sleep(0.02)
    yield Deployment(base, breaker)
    server.should_exit = True
    thread.join(timeout=10)


def run_smoke(deployment: Deployment, rule: Rule | None) -> int:
    """The exit status of `scripts/smoke_access_shell.py <BASE_URL>` run as the contract names it."""
    deployment.breaker.rule = rule
    try:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), deployment.base],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return done.returncode
    finally:
        deployment.breaker.rule = None


def replace_header(headers: Headers, name: str, change: Callable[[str], str | None]) -> Headers:
    out: Headers = []
    for key, value in headers:
        if key.lower() == name:
            new = change(value)
            if new is not None:
                out.append((key, new))
        else:
            out.append((key, value))
    return out


def on(
    path_test: Callable[[str], bool],
    fix: Callable[[dict[str, str], int, Headers, bytes], tuple[int, Headers, bytes]],
) -> Rule:
    def rule(
        path: str, request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        if path_test(path):
            return fix(request, status, headers, body)
        return status, headers, body

    return rule


SHELL_LIKE = b"<!doctype html><html><body>shell</body></html>"
HTML_200: Headers = [("content-type", "text/html; charset=utf-8"), ("cache-control", "no-cache")]


# ------------------------------------------------------------------ it passes on the app of this slice


def test_smoke_passes_against_the_app_of_this_slice(deployment: Deployment) -> None:
    assert run_smoke(deployment, None) == 0


# ------------------------------------------------------------------ it fails on each broken check


def test_smoke_fails_when_root_without_cookie_is_not_a_redirect_to_login(deployment: Deployment) -> None:
    def serve_shell(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        if "cookie" in request:
            return status, headers, body
        return 200, HTML_200, SHELL_LIKE

    def elsewhere(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        if "cookie" in request:
            return status, headers, body
        return 302, replace_header(headers, "location", lambda _: "/elsewhere"), body

    for fix in (serve_shell, elsewhere):
        assert run_smoke(deployment, on(lambda p: p == "/", fix)) != 0, fix.__name__


def _login_location(change: Callable[[dict[str, list[str]]], None], host: str | None = None) -> Rule:
    def edit(value: str) -> str:
        url = urlparse(value)
        query = parse_qs(url.query)
        change(query)
        return urlunparse(url._replace(netloc=host or url.netloc, query=urlencode(query, doseq=True)))

    return on(lambda p: p == "/auth/login", lambda r, s, h, b: (s, replace_header(h, "location", edit), b))


def test_smoke_fails_when_login_redirect_lacks_what_the_contract_names(deployment: Deployment) -> None:
    def drop(name: str) -> Callable[[dict[str, list[str]]], None]:
        def change(query: dict[str, list[str]]) -> None:
            query.pop(name, None)

        return change

    def put(name: str, value: str) -> Callable[[dict[str, list[str]]], None]:
        return lambda q: q.__setitem__(name, [value])

    without_tasks = " ".join(s for s in SCOPES if not s.endswith("/auth/tasks"))
    broken = {
        "another host": _login_location(lambda q: None, host="evil.example.com"),
        "no access_type": _login_location(drop("access_type")),
        "access_type online": _login_location(put("access_type", "online")),
        "no prompt": _login_location(drop("prompt")),
        "prompt select_account": _login_location(put("prompt", "select_account")),
        "code_challenge_method plain": _login_location(put("code_challenge_method", "plain")),
        "no code_challenge_method": _login_location(drop("code_challenge_method")),
        "scope without tasks": _login_location(put("scope", without_tasks)),
        "redirect_uri elsewhere": _login_location(
            put("redirect_uri", "https://evil.example.com/auth/callback")
        ),
    }
    for name, rule in broken.items():
        assert run_smoke(deployment, rule) != 0, name


def test_smoke_fails_when_login_cookie_lacks_secure_httponly_or_samesite_lax(deployment: Deployment) -> None:
    def without(attribute: str) -> Rule:
        def edit(value: str) -> str:
            if not value.startswith("mm_login="):
                return value
            parts = [p for p in value.split(";") if p.strip().split("=")[0].lower() != attribute]
            return ";".join(parts)

        return on(
            lambda p: p == "/auth/login", lambda r, s, h, b: (s, replace_header(h, "set-cookie", edit), b)
        )

    def no_cookie(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        return status, replace_header(headers, "set-cookie", lambda _: None), body

    for attribute in ("secure", "httponly", "samesite"):
        assert run_smoke(deployment, without(attribute)) != 0, attribute
    assert run_smoke(deployment, on(lambda p: p == "/auth/login", no_cookie)) != 0, "no mm_login"


def test_smoke_fails_when_manifest_is_not_valid_or_lacks_a_named_field(deployment: Deployment) -> None:
    def manifest(change: Callable[[dict[str, Any]], bytes]) -> Rule:
        def fix(
            request: dict[str, str], status: int, headers: Headers, body: bytes
        ) -> tuple[int, Headers, bytes]:
            return status, headers, change(json.loads(body))

        return on(lambda p: p == "/manifest.webmanifest", fix)

    def without(key: str) -> Callable[[dict[str, Any]], bytes]:
        return lambda m: json.dumps({k: v for k, v in m.items() if k != key}).encode()

    def icons_without(size: str) -> Callable[[dict[str, Any]], bytes]:
        def change(m: dict[str, Any]) -> bytes:
            m["icons"] = [i for i in m.get("icons", []) if size not in str(i.get("sizes", ""))]
            return json.dumps(m).encode()

        return change

    def display(m: dict[str, Any]) -> bytes:
        return json.dumps({**m, "display": "browser"}).encode()

    def not_found(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        return 404, headers, b'{"detail":"Not Found"}'

    broken = {
        "not JSON": manifest(lambda m: b"{not json"),
        "no name": manifest(without("name")),
        "no start_url": manifest(without("start_url")),
        "no display": manifest(without("display")),
        "display browser": manifest(display),
        "no 192 icon": manifest(icons_without("192")),
        "no 512 icon": manifest(icons_without("512")),
        "404": on(lambda p: p == "/manifest.webmanifest", not_found),
    }
    for name, rule in broken.items():
        assert run_smoke(deployment, rule) != 0, name


def test_smoke_fails_when_static_files_lack_no_cache(deployment: Deployment) -> None:
    def static(path: str) -> bool:
        return path.startswith("/static/") or path == "/manifest.webmanifest"

    def no_header(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        return status, replace_header(headers, "cache-control", lambda _: None), body

    def cached(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        return status, replace_header(headers, "cache-control", lambda _: "max-age=86400"), body

    for fix in (no_header, cached):
        assert run_smoke(deployment, on(static, fix)) != 0, fix.__name__


def test_smoke_fails_when_root_with_a_forged_cookie_is_not_a_redirect(deployment: Deployment) -> None:
    def accept_any_cookie(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        if "cookie" in request:
            return 200, HTML_200, SHELL_LIKE
        return status, headers, body

    assert run_smoke(deployment, on(lambda p: p == "/", accept_any_cookie)) != 0
