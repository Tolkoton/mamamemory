"""Документи Firestore під акаунтом (ADR-0001, ADR-0004).

Повний шлях завжди будується тут: `accounts/{account_id}/{path}`.
`transact` (S3) — читання й запис одного документа однією транзакцією.
Не робить: запитів через кілька акаунтів.
"""

from collections.abc import Callable
from typing import Any

Decide = Callable[[dict[str, Any] | None], dict[str, Any] | None]
"""`decide(snapshot) -> Write | None`: новий вміст документа або None — нічого не писати."""

ROOT = "accounts"


def document_path(account_id: str, path: str) -> str:
    """Повний шлях документа під акаунтом; неприйнятний account_id чи path — ValueError."""
    _check_account_id(account_id)
    segments = _relative_segments(path)
    return "/".join([ROOT, account_id, *segments])


def _check_account_id(account_id: str) -> None:
    if account_id in ("", ".", "..") or "/" in account_id:
        raise ValueError(f"bad account_id: {account_id!r}")


def _relative_segments(path: str) -> list[str]:
    if path == "":
        return []
    segments = path.split("/")
    if len(segments) % 2 != 0:
        raise ValueError(f"path must name a document (even number of segments): {path!r}")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError(f"bad path segment in {path!r}")
    return segments


class FirestoreStore:
    """Справжня реалізація: клієнт будується фабрикою з `database=` з налаштувань."""

    def __init__(self, project: str, database: str, client_factory: Callable[..., Any]) -> None:
        self._client = client_factory(project=project, database=database)

    def get(self, account_id: str, path: str) -> dict[str, Any] | None:
        snapshot = self._client.document(document_path(account_id, path)).get()
        if not snapshot.exists:
            return None
        data: dict[str, Any] = snapshot.to_dict()
        return data

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self._client.document(document_path(account_id, path)).set(data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        """Читання й запис однією транзакцією Firestore; повертає записане (або None)."""
        from google.cloud import firestore

        reference = self._client.document(document_path(account_id, path))

        @firestore.transactional
        def run(transaction: Any) -> dict[str, Any] | None:
            snapshot = reference.get(transaction=transaction)
            written = decide(snapshot.to_dict() if snapshot.exists else None)
            if written is not None:
                transaction.set(reference, written)
            return written

        result: dict[str, Any] | None = run(self._client.transaction())
        return result


class InMemoryStore:
    """Фейк для тестів; шлях — через ту саму `document_path`."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    def get(self, account_id: str, path: str) -> dict[str, Any] | None:
        document = self._documents.get(document_path(account_id, path))
        return dict(document) if document is not None else None

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self._documents[document_path(account_id, path)] = dict(data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        full = document_path(account_id, path)
        current = self._documents.get(full)
        written = decide(dict(current) if current is not None else None)
        if written is not None:
            self._documents[full] = dict(written)
        return written


Store = FirestoreStore | InMemoryStore
