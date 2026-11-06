"""Catch-up contract tests of the slice access-shell: the Cloud Run entry point `mamamemory.main`.

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md` and the public
signatures only. The entry point builds the real dependencies from the environment at import time, so
every test imports it afresh under an environment it sets; Firestore's client is replaced by a mock, so
nothing here touches the network.
"""

import importlib
import inspect
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore

from mamamemory import access
from mamamemory.integrations import store as store_module

BASE_URL = "https://mamamemory-2mfebgg56q-ey.a.run.app"
KEY = "session-key-from-the-environment"
CLIENT_ID = "client-id-from-the-environment.apps.googleusercontent.com"
PROJECT = "project-from-the-environment"
MAMA = "mama@example.com"
SUB = "1000000000000000001"
WEEK = timedelta(days=7)


def environ(**over: str) -> dict[str, str]:
    env = {
        "ALLOWED_EMAILS": MAMA,
        "GCP_PROJECT": PROJECT,
        "FIRESTORE_DATABASE": "mamamemory",
        "VERTEX_LOCATION": "eu",
        "TTS_ENDPOINT": "eu-texttospeech.googleapis.com",
        "REGION": "europe-west3",
        "OAUTH_CLIENT_ID": CLIENT_ID,
        "OAUTH_CLIENT_SECRET": "client-secret-from-the-environment",
        "SESSION_KEY": KEY,
        "SESSION_MAX_AGE_S": "604800",
        "LOGIN_MAX_AGE_S": "600",
        "BASE_URL": BASE_URL,
        "REQUEST_TIMEOUT_S": "30",
        "CALL_TIMEOUT_S": "10",
    }
    env.update(over)
    return env


class Entry:
    """One fresh import of `mamamemory.main` and what it built."""

    def __init__(
        self, module: ModuleType, stores: list[Any], arguments: list[dict[str, Any]], client: MagicMock
    ) -> None:
        self.module = module
        self.stores = stores
        self.arguments = arguments
        self.client = client

    @property
    def app(self) -> FastAPI:
        app = self.module.app
        assert isinstance(app, FastAPI)
        return app

    def http(self) -> TestClient:
        return TestClient(self.app, base_url=BASE_URL, follow_redirects=False)


@pytest.fixture
def load_main(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Entry]]:
    original = store_module.FirestoreStore

    def load(**over: str) -> Entry:
        for name, value in environ(**over).items():
            monkeypatch.setenv(name, value)
        client = MagicMock(name="firestore-client")
        monkeypatch.setattr(firestore, "Client", MagicMock(name="firestore.Client", return_value=client))
        stores: list[Any] = []
        arguments: list[dict[str, Any]] = []

        def recording(*args: Any, **kwargs: Any) -> Any:
            bound = inspect.signature(original).bind(*args, **kwargs)
            arguments.append(dict(bound.arguments))
            built = original(*args, **kwargs)
            stores.append(built)
            return built

        monkeypatch.setattr(store_module, "FirestoreStore", recording)
        sys.modules.pop("mamamemory.main", None)
        module = importlib.import_module("mamamemory.main")
        return Entry(module, stores, arguments, client)

    yield load
    sys.modules.pop("mamamemory.main", None)


def session_cookie(email: str = MAMA, at: datetime | None = None, key: str = KEY) -> str:
    return access.session_cookie_value(SUB, email, at or datetime.now(UTC), key=key)


def forge(value: str) -> str:
    payload, _ = value.rsplit(".", 1)
    _, signature = session_cookie(email="stranger@example.com").rsplit(".", 1)
    return f"{payload}.{signature}"


def get(http: TestClient, path: str, session: str | None = None) -> Any:
    http.cookies.clear()
    if session is not None:
        http.cookies.set("mm_session", session)
    return http.get(path)


def test_entrypoint_login_uses_client_and_base_url_from_the_environment(
    load_main: Callable[..., Entry],
) -> None:
    resp = get(load_main().http(), "/auth/login")
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert location.hostname == "accounts.google.com"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [f"{BASE_URL}/auth/callback"]
    assert "mm_login=" in resp.headers.get("set-cookie", "")


def test_entrypoint_checks_sessions_with_the_key_from_the_environment_and_the_real_clock(
    load_main: Callable[..., Entry],
) -> None:
    http = load_main().http()
    now = datetime.now(UTC)
    assert get(http, "/", session_cookie(at=now)).status_code == 200
    # Signed with another key: not a session of this deployment.
    assert get(http, "/", session_cookie(at=now, key="another-key")).status_code == 302
    # Made a week and an hour ago by the real clock: older than SESSION_MAX_AGE_S.
    assert get(http, "/", session_cookie(at=now - WEEK - timedelta(hours=1))).status_code == 302


def test_entrypoint_store_is_firestore_on_the_configured_project_and_database(
    load_main: Callable[..., Entry],
) -> None:
    entry = load_main()
    assert len(entry.arguments) == 1, "the entry point builds exactly one Firestore store"
    assert entry.arguments[0]["project"] == PROJECT
    assert entry.arguments[0]["database"] == "mamamemory"


def test_I1_entrypoint_app_gives_no_shell_without_a_valid_session_of_an_allowed_account(
    load_main: Callable[..., Entry],
) -> None:
    http = load_main().http()
    now = datetime.now(UTC)
    shell = get(http, "/", session_cookie(at=now))
    assert shell.status_code == 200 and shell.content
    login_value = access.login_cookie_value("state-1", "v" * 43, now, key=KEY)
    refused: list[str | None] = [
        None,
        "",
        "not-a-signed-value",
        forge(session_cookie(at=now)),
        session_cookie(at=now - WEEK - timedelta(seconds=60)),
        session_cookie(email="stranger@example.com", at=now),
        session_cookie(at=now, key="another-key"),
        login_value,
    ]
    for path in ("/", "/index.html", "/static/index.html", "/anything"):
        for value in refused:
            resp = get(http, path, value)
            assert shell.content not in resp.content, (path, value, resp.status_code)
    # ALLOWED_EMAILS changed on the next deployment: Mama's own valid cookie no longer reaches the shell.
    http = load_main(ALLOWED_EMAILS="other@example.com").http()
    resp = get(http, "/", session_cookie(at=datetime.now(UTC)))
    assert shell.content not in resp.content, resp.status_code


def test_I2_entrypoint_store_keeps_every_document_under_accounts_account_id(
    load_main: Callable[..., Entry],
) -> None:
    entry = load_main()
    assert len(entry.stores) == 1
    store = entry.stores[0]

    def touched() -> str:
        """The document path the store handed to the Firestore client, its string arguments in order."""
        parts = [str(a) for c in entry.client.mock_calls for a in c.args if isinstance(a, str)]
        return "/".join(parts)

    def wrote() -> bool:
        return any(str(c[0]).split(".")[-1] == "set" for c in entry.client.mock_calls)

    refused = [
        ("", "private/google"),
        ("a/b", "private/google"),
        (".", "private/google"),
        ("..", "private/google"),
        ("acc-1", "private"),
        ("acc-1", "/x/private/google"),
        ("acc-1", "a//b/c"),
        ("acc-1", "./google"),
        ("acc-1", "../other/private/google"),
    ]
    for account_id, path in refused:
        entry.client.reset_mock()
        with pytest.raises(ValueError):
            store.set(account_id, path, {"k": "v"})
        assert not wrote(), (account_id, path)
        with pytest.raises(ValueError):
            store.get(account_id, path)

    lawful = [
        ("acc-1", "private/google", "accounts/acc-1/private/google"),
        ("acc-1", "", "accounts/acc-1"),
        (SUB, "a/b/c/d", f"accounts/{SUB}/a/b/c/d"),
    ]
    for account_id, path, expected in lawful:
        entry.client.reset_mock()
        store.set(account_id, path, {"k": "v"})
        assert touched() == expected, (account_id, path, touched())
        entry.client.reset_mock()
        store.get(account_id, path)
        assert touched() == expected, (account_id, path, touched())


def test_I3_entrypoint_refuses_to_start_on_an_address_outside_the_allowed_set(
    load_main: Callable[..., Entry],
) -> None:
    for name, value in (
        ("VERTEX_LOCATION", "global"),
        ("VERTEX_LOCATION", "us-central1"),
        ("TTS_ENDPOINT", "texttospeech.googleapis.com"),
        ("REGION", "us-central1"),
        ("REGION", "global"),
        ("FIRESTORE_DATABASE", "(default)"),
        ("FIRESTORE_DATABASE", ""),
    ):
        with pytest.raises(ValueError):
            load_main(**{name: value})
    # Lawful values at the other edge of the set still start it.
    entry = load_main(VERTEX_LOCATION="europe-west4", REGION="europe-west1")
    assert isinstance(entry.app, FastAPI)
    # One refused value among lawful ones is refused all the same.
    with pytest.raises(ValueError):
        load_main(VERTEX_LOCATION="europe-west4", TTS_ENDPOINT="texttospeech.googleapis.com")
