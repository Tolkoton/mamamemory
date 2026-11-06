"""Точка входу Cloud Run: збирає справжні залежності з середовища (`uvicorn mamamemory.main:app`)."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore

from mamamemory.access import Session
from mamamemory.config import Config, load_config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.google_auth import GoogleAuth
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import FirestoreStore


def _now() -> datetime:
    return datetime.now(UTC)


def _genai_client(config: Config) -> Any:
    return genai.Client(vertexai=True, project=config.gcp_project, location=config.vertex_location)


def _calendar(config: Config) -> Any:
    """Календар запиту: дедлайн ланцюжка `REQUEST_TIMEOUT_S − 2 × CALL_TIMEOUT_S` від початку запиту (M2)."""

    def build(session: Session, started: datetime) -> GoogleWork:
        deadline = started + timedelta(seconds=config.request_timeout_s - 2 * config.call_timeout_s)
        authorized = AuthorizedSession(session.google_credentials())
        return GoogleWork(authorized, call_timeout_s=config.call_timeout_s, deadline=deadline, now=_now)

    return build


config = load_config(os.environ)
app = create_app(
    config,
    FirestoreStore(config.gcp_project, config.firestore_database, firestore.Client),
    GoogleAuth(config),
    _now,
    ai=AI(lambda: _genai_client(config), config),
    calendar=_calendar(config),
)
