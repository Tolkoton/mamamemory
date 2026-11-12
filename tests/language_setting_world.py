"""Shared fakes of the slice language-setting tests (written by the slice tester from the contract)."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import ServiceUnavailable
from google.oauth2.credentials import Credentials

from mamamemory import access
from mamamemory.config import SCOPES
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.store import InMemoryStore
from tests.test_one_task_http import MAMA, SUB, FakeGoogle
from tests.test_one_task_planning import make_config
from tests.test_voice_speech import Gemini

HEARD = "Купити хліб"


def no_credentials() -> Credentials:
    raise AssertionError("language must not need Google credentials")


def session(account_id: str) -> access.Session:
    return access.Session(account_id=account_id, google_credentials=no_credentials)


class ProfileStore(InMemoryStore):
    """`InMemoryStore` that records reads of `settings/profile` and can fail them."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_profile = False
        self.profile_reads: list[tuple[str, str, bool]] = []  # (account, path, on the event loop)

    def get(self, account_id: str, path: str) -> dict[str, Any] | None:
        if path == access.PROFILE_PATH:
            try:
                asyncio.get_running_loop()
                on_loop = True
            except RuntimeError:
                on_loop = False
            self.profile_reads.append((account_id, path, on_loop))
            if self.fail_profile:
                raise ServiceUnavailable("firestore is down")
        return super().get(account_id, path)


class Transcribe:
    """The app, signed in as `SUB`, built from a `Config` whose `language` is `"xx"`; `speech` is a fake."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.languages: list[str] = []
        self.config = replace(make_config(), language="xx")
        self.store = ProfileStore()
        started = datetime.now(UTC)
        self.store.set(
            SUB,
            access.TOKENS_PATH,
            access.tokens_document(
                Tokens(access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)),
                started,
            ),
        )

        def fake_speech(audio: bytes, mime: str, *, language: str, **_: Any) -> str:
            self.languages.append(language)
            return HEARD

        monkeypatch.setattr("mamamemory.http.app.speech", fake_speech, raising=False)
        monkeypatch.setattr("mamamemory.integrations.ai.speech", fake_speech)
        client = Gemini(HEARD).client()
        app = create_app(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            lambda: datetime.now(UTC),
            ai=AI(lambda: client, self.config),
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        self.client.cookies.set(
            "mm_session", access.session_cookie_value(SUB, MAMA, started, key=self.config.session_key)
        )

    def post(self) -> httpx.Response:
        resp: httpx.Response = self.client.post(
            "/api/transcribe", content=b"\x1a\x45\xdf\xa3 webm", headers={"content-type": "audio/webm"}
        )
        return resp
