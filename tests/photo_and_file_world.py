"""Test helpers of the slice photo-and-file: a fake `Files`, a model fake that also reads files,
a world around `cases.add_file`, a fake Cloud Storage client for `Files` itself and an app around
`POST /api/upload`.

Written by the slice tester from the sealed contract `.engine/slices/photo-and-file.md`, without the code.
The fake `Files` keeps one object per key `(account_id, material_id)` and answers
`gs://{BUCKET}/{account_id}/{material_id}`, as the contract's `Files.put` does; `fail` makes the next
puts raise, `on_put` runs before an object is kept, `after_put` after. The model fake answers `read_file`
with `{"text": ...}` (the shape the contract names) and counts every call; `fail` and `after` work as in
`note_to_case_world`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from mamamemory import access
from mamamemory import cases as case_module
from mamamemory.access import Session
from mamamemory.config import SCOPES, Config
from mamamemory.http.app import create_app
from mamamemory.integrations.ai import AI
from mamamemory.integrations.files import Files
from mamamemory.integrations.google_auth import GoogleAuth, Tokens
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import InMemoryStore
from mamamemory.replies import Reply
from tests.note_to_case_world import DEADLINE, CaseAI, Clock, ModelFailed, Notes
from tests.test_one_task_http import MAMA, SUB, FakeGoogle
from tests.test_one_task_http import Clock as AppClock
from tests.test_one_task_planning import NOW, FakeCalendar, make_config, make_session

BUCKET = "test-bucket"
NO_TEXT = "(без тексту)"
NOT_READ = "Такий файл я не читаю. Надішліть фото або PDF."
EMPTY = "Файл порожній."
TOO_BIG_20 = "Файл завеликий — до 20 MB."
READ_TEXT = "Аналіз крові: HbA1c 7,2 — пані Шмідт"
PNG = b"\x89PNG\r\n\x1a\n-photo-of-a-form-"
PDF = b"%PDF-1.4\n-a-letter-\n%%EOF"
ALLOWED = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
    "text/plain",
)


class FilesFailed(Exception):
    """What the fake `Files` raises when a put is told to fail."""


class FakeFiles:
    def __init__(self, bucket: str = BUCKET) -> None:
        self.bucket = bucket
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.puts: list[tuple[str, str]] = []
        self.fail = 0
        self.on_put: Callable[[str, str], None] | None = None
        self.after_put: Callable[[], None] | None = None

    def uri(self, account_id: str, material_id: str) -> str:
        return f"gs://{self.bucket}/{account_id}/{material_id}"

    def put(self, account_id: str, material_id: str, data: bytes, mime: str) -> str:
        self.puts.append((account_id, material_id))
        if self.on_put is not None:
            self.on_put(account_id, material_id)
        if self.fail > 0:
            self.fail -= 1
            raise FilesFailed(material_id)
        self.objects[(account_id, material_id)] = (data, mime)
        if self.after_put is not None:
            hook, self.after_put = self.after_put, None
            hook()
        return self.uri(account_id, material_id)


class FileAI(CaseAI):
    """`CaseAI` that also answers `generate_json_with_file`: `read_file` → `{"text": self.read_text}`.
    `nameless` makes `name_case` answer no name."""

    def __init__(self) -> None:
        super().__init__()
        self.read_text = READ_TEXT
        self.nameless = False
        self.file_calls: list[tuple[str, str, str]] = []

    def generate_json_with_file(
        self, task_type: str, prompt: str, schema: dict[str, Any], gs_uri: str, mime: str
    ) -> dict[str, Any]:
        self.calls.append(task_type)
        self.file_calls.append((task_type, gs_uri, mime))
        if self.fail.get(task_type, 0) > 0:
            self.fail[task_type] -= 1
            raise ModelFailed(task_type)
        hook = self.after.pop(task_type, None)
        if hook is not None:
            hook()
        return {"text": self.read_text}

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "name_case" and self.nameless:
            self.calls.append(task_type)
            return {"name": None}
        return super()._answer(task_type, prompt, schema)


@dataclass
class Uploads:
    ai: FileAI = field(default_factory=FileAI)
    files: FakeFiles = field(default_factory=FakeFiles)
    store: InMemoryStore = field(default_factory=InMemoryStore)
    config: Config = field(default_factory=make_config)
    session: Session = field(default_factory=make_session)
    clock: Clock = field(default_factory=Clock)

    @property
    def notes(self) -> Notes:
        return Notes(ai=self.ai, store=self.store, config=self.config, session=self.session, clock=self.clock)

    def other(self, account_id: str = "acc-2") -> "Uploads":
        """A second account over the same store, the same files and the same model."""
        return Uploads(
            ai=self.ai,
            files=self.files,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
        )

    def add(
        self, material_id: str, data: bytes | None, mime: str | None, deadline: datetime = DEADLINE
    ) -> Reply:
        return case_module.add_file(
            self.session,
            material_id,
            data,
            mime,
            ai=cast(AI, self.ai),
            files=cast(Files, self.files),
            store=self.store,
            now=NOW,
            config=self.config,
            deadline=deadline,
            clock=self.clock,
        )

    def try_add(self, material_id: str, data: bytes | None, mime: str | None) -> Reply | None:
        """`add_file` that may fail: None when it raised (a missing implementation is no lawful failure)."""
        try:
            return self.add(material_id, data, mime)
        except NotImplementedError:
            raise
        except Exception:
            return None

    def materials(self) -> list[case_module.Material]:
        return case_module.materials_catalogue(self.session, self.store)

    def with_id(self, material_id: str) -> list[case_module.Material]:
        return [m for m in self.materials() if m.material_id == material_id]

    def material(self, material_id: str) -> case_module.Material:
        found = self.with_id(material_id)
        assert len(found) == 1, (material_id, found)
        return found[0]

    def cases(self) -> list[case_module.Case]:
        return case_module.catalogue(self.session, self.store)

    def seed(self, name: str, message_id: str) -> case_module.Case:
        made = self.notes.seed(name, message_id)
        self.ai.calls.clear()
        self.ai.file_calls.clear()
        return made


# ------------------------------------------------------------------ a fake Cloud Storage client for `Files`


class FakeBlob:
    def __init__(self, storage: "FakeStorage", bucket: str, name: str) -> None:
        self.storage, self.bucket_name, self.name = storage, bucket, name

    def upload_from_string(self, data: bytes | str, *args: Any, **kwargs: Any) -> None:
        content = data.encode() if isinstance(data, str) else data
        self.storage.objects[(self.bucket_name, self.name)] = content
        self.storage.uploads.append({"bucket": self.bucket_name, "name": self.name, "args": args, **kwargs})


class FakeBucket:
    def __init__(self, storage: "FakeStorage", name: str) -> None:
        self.storage, self.name = storage, name

    def blob(self, name: str, *args: Any, **kwargs: Any) -> FakeBlob:
        return FakeBlob(self.storage, self.name, name)


class FakeStorage:
    """Stands in for `google.cloud.storage.Client`: `bucket(name)` (or `get_bucket`) → `blob(name)` →
    `upload_from_string(data, content_type=…, timeout=…)`; keeps `(bucket, object name) → bytes`."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.uploads: list[dict[str, Any]] = []

    def bucket(self, name: str, *args: Any, **kwargs: Any) -> FakeBucket:
        return FakeBucket(self, name)

    def get_bucket(self, name: str, *args: Any, **kwargs: Any) -> FakeBucket:
        return FakeBucket(self, name)


def make_files(storage: FakeStorage, bucket: str = BUCKET, call_timeout_s: float = 10) -> Files:
    return Files(lambda: storage, bucket, call_timeout_s=call_timeout_s)


# ------------------------------------------------------------------ the app around `POST /api/upload`

SUB_2 = "1000000000000000002"


class UploadApp:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or make_config()
        self.store = InMemoryStore()
        for sub in (SUB, SUB_2):
            self.store.set(
                sub,
                access.TOKENS_PATH,
                access.tokens_document(
                    Tokens(
                        access_token="at-1", refresh_token="rt-1", id_token="idt-1", scopes=frozenset(SCOPES)
                    ),
                    NOW,
                ),
            )
        self.clock = AppClock(NOW)
        self.ai = FileAI()
        self.files = FakeFiles()
        self.calendar = FakeCalendar()
        # The skeleton's `create_app` predates the slice; the contract names the keyword `files`.
        make: Callable[..., FastAPI] = create_app
        app = make(
            self.config,
            self.store,
            cast(GoogleAuth, FakeGoogle()),
            self.clock,
            ai=cast(AI, self.ai),
            calendar=lambda session, started: cast(GoogleWork, self.calendar),
            files=cast(Files, self.files),
        )
        self.client = TestClient(
            app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False
        )
        self.sign_in(SUB)
        self.session = self.session_of(SUB)
        self.world = Uploads(
            ai=self.ai, files=self.files, store=self.store, config=self.config, session=self.session
        )

    def sign_in(self, sub: str) -> None:
        email = MAMA if sub == SUB else "second@example.com"
        self.client.cookies.set(
            "mm_session", access.session_cookie_value(sub, email, NOW, key=self.config.session_key)
        )

    @staticmethod
    def session_of(sub: str) -> Session:
        return Session(account_id=sub, google_credentials=lambda: Credentials("at-test"))

    def upload(
        self, data: bytes, content_type: str | None = "image/png", material_id: str | None = "up-1"
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if material_id is not None:
            headers["X-Material-Id"] = material_id
        resp = self.client.post("/api/upload", content=data, headers=headers)
        assert resp.status_code == 200, (resp.status_code, resp.text)
        answer: dict[str, Any] = resp.json()
        return answer

    def header_only(self, material_id: str) -> dict[str, Any]:
        """The repeat after «Не вдалося…»: no body, no `Content-Type`, the same `X-Material-Id`."""
        return self.upload(b"", content_type=None, material_id=material_id)

    def confirm(self, material_id: str) -> dict[str, Any]:
        resp = self.client.post("/api/case/confirm", json={"material_id": material_id})
        assert resp.status_code == 200, resp.text
        answer: dict[str, Any] = resp.json()
        return answer

    def materials(self, sub: str = SUB) -> list[case_module.Material]:
        return case_module.materials_catalogue(self.session_of(sub), self.store)

    def seed(self, name: str, message_id: str) -> case_module.Case:
        return self.world.seed(name, message_id)

    def later(self, seconds: int = 100) -> None:
        """A new request, well after the previous one: its own deadline."""
        self.clock.at = NOW + timedelta(seconds=seconds)
