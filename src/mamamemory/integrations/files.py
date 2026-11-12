"""Оригінали фото й файлів у Cloud Storage (F3 S2, `integrations.files`): об'єкт `{account_id}/{material_id}`.

Той самий `material_id` перезаписує той самий об'єкт (повтор без дубля).
Не робить: читання, видалення, перегляду.
"""

from collections.abc import Callable
from typing import Any


class Files:
    def __init__(self, client_factory: Callable[[], Any], bucket: str, *, call_timeout_s: float) -> None:
        self._client_factory, self._bucket, self._call_timeout_s = client_factory, bucket, call_timeout_s
        self._built: Any = None

    def put(self, account_id: str, material_id: str, data: bytes, mime: str) -> str:
        """Записати оригінал; повертає `gs://{bucket}/{account_id}/{material_id}`."""
        name = f"{_segment(account_id)}/{_segment(material_id)}"
        blob = self._client().bucket(self._bucket).blob(name)
        blob.upload_from_string(data, content_type=mime, timeout=self._call_timeout_s)
        return f"gs://{self._bucket}/{name}"

    def _client(self) -> Any:
        if self._built is None:
            self._built = self._client_factory()
        return self._built


def _segment(value: str) -> str:
    """Ті самі правила, що `store.document_path`: без `/`, не порожнє, не `.` чи `..`."""
    if value in ("", ".", "..") or "/" in value:
        raise ValueError(f"bad path segment: {value!r}")
    return value
