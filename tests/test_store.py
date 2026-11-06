"""Contract tests of the slice access-shell: `store` under the account (I2, Q4, Seam 3).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from mamamemory.integrations.store import FirestoreStore, InMemoryStore, document_path


def _firestore(calls: list[tuple[tuple[Any, ...], dict[str, Any]]]) -> FirestoreStore:
    def factory(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return MagicMock()

    return FirestoreStore("pocket-lawyer-431614", "mamamemory", factory)


def test_I2_every_document_lies_under_accounts_account_id() -> None:
    # Lawful inputs: the root document, an even path, a deeper even path, a numeric Google `sub`.
    assert document_path("1234567890", "") == "accounts/1234567890"
    assert document_path("1234567890", "private/google") == "accounts/1234567890/private/google"
    assert document_path("abc", "a/b/c/d") == "accounts/abc/a/b/c/d"

    bad_paths = [
        "private",  # odd number of segments
        "a/b/c",  # odd number of segments
        "/private/google",  # leading slash
        "private/google/",  # trailing empty segment
        "a//b/c",  # empty segment
        "../google",  # `..` as a segment
        "private/..",  # `..` as a segment
        "./google",  # `.` as a segment
        "private/.",  # `.` as a segment
        "../../other/x",  # escape to another account
    ]
    bad_accounts = ["", "a/b", ".", "..", "/"]
    for path in bad_paths:
        with pytest.raises(ValueError):
            document_path("abc", path)
    for account in bad_accounts:
        with pytest.raises(ValueError):
            document_path(account, "private/google")
        with pytest.raises(ValueError):
            document_path(account, "")

    # Both implementations go through the same check: neither the fake nor Firestore writes or
    # reads outside the account.
    memory = InMemoryStore()
    firestore = _firestore([])
    for store in (memory, firestore):
        for path in bad_paths:
            with pytest.raises(ValueError):
                store.set("abc", path, {"x": 1})
            with pytest.raises(ValueError):
                store.get("abc", path)
        for account in bad_accounts:
            with pytest.raises(ValueError):
                store.set(account, "private/google", {"x": 1})
            with pytest.raises(ValueError):
                store.get(account, "private/google")

    # A lawful operation after a refused one still works, and stays inside its account.
    memory.set("abc", "private/google", {"refresh_token": "r"})
    assert memory.get("abc", "private/google") == {"refresh_token": "r"}
    assert memory.get("other", "private/google") is None


def test_in_memory_store_get_and_set_by_account_and_relative_path() -> None:
    store = InMemoryStore()
    assert store.get("a1", "private/google") is None
    store.set("a1", "private/google", {"k": "v1"})
    store.set("a2", "private/google", {"k": "v2"})
    store.set("a1", "", {"root": True})
    assert store.get("a1", "private/google") == {"k": "v1"}
    assert store.get("a2", "private/google") == {"k": "v2"}
    assert store.get("a1", "") == {"root": True}
    assert store.get("a2", "") is None


def test_firestore_store_builds_client_with_database_from_config() -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    store = _firestore(calls)
    if not calls:  # the client may be built lazily, on first use
        # the MagicMock client answers nothing useful; only the factory call is checked
        try:
            store.get("abc", "private/google")
        except Exception:
            pass
    assert calls, "the client factory was never called"
    for _args, kwargs in calls:
        assert kwargs.get("database") == "mamamemory"
