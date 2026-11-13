"""Налаштування сервера з середовища, з перевіркою регіонів і бази (C1, ADR-0004).

Не робить: не читає секрети з Secret Manager (Cloud Run передає їх змінними середовища).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

SCOPES: tuple[str, ...] = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
)


@dataclass(frozen=True)
class ModelChoice:
    model: str
    thinking_level: str | None = None


DEFAULT_MODELS: Mapping[str, ModelChoice] = {
    "parse_task": ModelChoice("gemini-3.5-flash-lite"),
    "parse_duration": ModelChoice("gemini-3.5-flash-lite"),
    "route": ModelChoice("gemini-3.5-flash-lite"),
    "parse_limits": ModelChoice("gemini-3.5-flash-lite"),
    "parse_priorities": ModelChoice("gemini-3.5-flash-lite"),
    "parse_edit": ModelChoice("gemini-3.5-flash-lite"),
    "classify_case": ModelChoice("gemini-3.8-flash"),
    "describe_case": ModelChoice("gemini-3.8-flash"),
    "name_case": ModelChoice("gemini-3.5-flash-lite"),
    "read_file": ModelChoice("gemini-3.5-flash-lite"),
    "choose_material": ModelChoice("gemini-3.8-flash"),
    "choose_option": ModelChoice("gemini-3.5-flash-lite"),
    "transcribe": ModelChoice("gemini-3.8-flash"),
    "answer_work": ModelChoice("gemini-3.5-flash-lite"),
    "answer_case": ModelChoice("gemini-3.5-flash-lite"),
}


@dataclass(frozen=True)
class Config:
    gcp_project: str
    firestore_database: str
    vertex_location: str
    tts_endpoint: str
    region: str
    oauth_client_id: str
    oauth_client_secret: str
    session_key: str
    session_max_age_s: int
    login_max_age_s: int
    base_url: str
    request_timeout_s: int
    call_timeout_s: int
    scopes: tuple[str, ...] = SCOPES
    models: Mapping[str, ModelChoice] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    step_min: int = 15
    language: str = "uk"
    max_audio_bytes: int = 6 * 1024 * 1024
    ask_limits: bool = False
    ask_priorities: bool = False
    use_tasks: bool = False
    files_bucket: str = ""
    max_upload_bytes: int = 20 * 1024 * 1024
    """Чи читати й писати Google Tasks (google-tasks F2); `load_config` вмикає."""
    """Чи питати «що важливіше?» (priorities F2); `load_config` вмикає."""
    """Чи питати мамині межі часу (time-limits F2); `load_config` вмикає, тести з `Config` напряму — ні."""


EU_TTS_ENDPOINT = "eu-texttospeech.googleapis.com"
FIRESTORE_DATABASE = "mamamemory"


def load_config(environ: Mapping[str, str]) -> Config:
    """Читає Config із середовища; поза дозволеним набором регіонів, адрес чи бази — ValueError."""
    config = _read(environ)
    _check_regions(config)
    return config


def _read(environ: Mapping[str, str]) -> Config:
    return Config(
        gcp_project=environ["GCP_PROJECT"],
        firestore_database=environ["FIRESTORE_DATABASE"],
        vertex_location=environ["VERTEX_LOCATION"],
        tts_endpoint=environ["TTS_ENDPOINT"],
        region=environ["REGION"],
        oauth_client_id=environ["OAUTH_CLIENT_ID"],
        oauth_client_secret=environ["OAUTH_CLIENT_SECRET"],
        session_key=environ["SESSION_KEY"],
        session_max_age_s=int(environ["SESSION_MAX_AGE_S"]),
        login_max_age_s=int(environ["LOGIN_MAX_AGE_S"]),
        base_url=environ["BASE_URL"].rstrip("/"),
        request_timeout_s=int(environ["REQUEST_TIMEOUT_S"]),
        call_timeout_s=int(environ["CALL_TIMEOUT_S"]),
        files_bucket=environ.get("FILES_BUCKET") or f"{environ['GCP_PROJECT']}-mamamemory-files",
        ask_limits=True,
        ask_priorities=True,
        use_tasks=True,
    )


def _check_regions(config: Config) -> None:
    if not (config.vertex_location == "eu" or _is_europe(config.vertex_location)):
        raise ValueError(f"VERTEX_LOCATION outside the EU: {config.vertex_location!r}")
    if config.tts_endpoint != EU_TTS_ENDPOINT:
        raise ValueError(f"TTS_ENDPOINT must be {EU_TTS_ENDPOINT!r}: {config.tts_endpoint!r}")
    if not _is_europe(config.region):
        raise ValueError(f"REGION outside the EU: {config.region!r}")
    if config.firestore_database != FIRESTORE_DATABASE:
        raise ValueError(f"FIRESTORE_DATABASE must be {FIRESTORE_DATABASE!r}: {config.firestore_database!r}")


def _is_europe(value: str) -> bool:
    return value.startswith("europe-") and len(value) > len("europe-")
