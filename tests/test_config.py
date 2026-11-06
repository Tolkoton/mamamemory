"""Contract tests of the slice access-shell: `Config` from the environment, regions (Seam 3, I3).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

import pytest

from mamamemory.config import load_config

SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
)


def _environ(**over: str) -> dict[str, str]:
    env = {
        "ALLOWED_EMAILS": "mama@example.com",
        "GCP_PROJECT": "pocket-lawyer-431614",
        "FIRESTORE_DATABASE": "mamamemory",
        "VERTEX_LOCATION": "eu",
        "TTS_ENDPOINT": "eu-texttospeech.googleapis.com",
        "REGION": "europe-west3",
        "OAUTH_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "OAUTH_CLIENT_SECRET": "client-secret",
        "SESSION_KEY": "session-key-for-tests",
        "SESSION_MAX_AGE_S": "604800",
        "LOGIN_MAX_AGE_S": "600",
        "BASE_URL": "https://mamamemory-2mfebgg56q-ey.a.run.app",
        "REQUEST_TIMEOUT_S": "30",
        "CALL_TIMEOUT_S": "10",
    }
    env.update(over)
    return env


def test_config_is_read_from_the_environment() -> None:
    config = load_config(_environ())
    assert config.allowed_emails == frozenset({"mama@example.com"})
    assert config.gcp_project == "pocket-lawyer-431614"
    assert config.firestore_database == "mamamemory"
    assert config.vertex_location == "eu"
    assert config.tts_endpoint == "eu-texttospeech.googleapis.com"
    assert config.region == "europe-west3"
    assert config.oauth_client_id == "client-id.apps.googleusercontent.com"
    assert config.oauth_client_secret == "client-secret"
    assert config.session_key == "session-key-for-tests"
    assert config.session_max_age_s == 604800
    assert config.login_max_age_s == 600
    assert config.base_url == "https://mamamemory-2mfebgg56q-ey.a.run.app"
    assert config.request_timeout_s == 30
    assert config.call_timeout_s == 10
    assert set(config.scopes) == set(SCOPES)


def test_config_refuses_the_named_global_values() -> None:
    for name, value in [
        ("VERTEX_LOCATION", "global"),
        ("REGION", "us-central1"),
        ("TTS_ENDPOINT", "texttospeech.googleapis.com"),
        ("FIRESTORE_DATABASE", "(default)"),
    ]:
        with pytest.raises(ValueError):
            load_config(_environ(**{name: value}))


def test_I3_no_configured_google_address_points_to_global() -> None:
    # Lawful values from the allowed set load.
    for over in [
        {},
        {"VERTEX_LOCATION": "europe-west4"},
        {"VERTEX_LOCATION": "europe-west3", "REGION": "europe-west1"},
    ]:
        config = load_config(_environ(**over))
        assert config.vertex_location == over.get("VERTEX_LOCATION", "eu")
        assert config.region == over.get("REGION", "europe-west3")

    refused = {
        "VERTEX_LOCATION": ["global", "us-central1", "us", "asia-northeast1"],
        "TTS_ENDPOINT": [
            "texttospeech.googleapis.com",
            "us-texttospeech.googleapis.com",
            "eu-texttospeech.googleapis.com.evil.example",
        ],
        "REGION": ["global", "us-central1", "us-east1", "eu"],
        "FIRESTORE_DATABASE": ["(default)", "", "mamamemory-us", "other"],
    }
    for name, values in refused.items():
        for value in values:
            with pytest.raises(ValueError):
                load_config(_environ(**{name: value}))
    # A refused value is refused whatever else in the environment is lawful: two values combined.
    with pytest.raises(ValueError):
        load_config(_environ(VERTEX_LOCATION="europe-west4", TTS_ENDPOINT="texttospeech.googleapis.com"))
