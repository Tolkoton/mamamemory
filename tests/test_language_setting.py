"""Contract tests of slice language-setting (F5 S1), Seams 1 and 2.

Written by the slice tester from the sealed contract `.engine/slices/language-setting.md`, without the code.
"""

import pytest

from mamamemory import access
from tests.language_setting_world import HEARD, ProfileStore, Transcribe, session
from tests.test_one_task_http import SUB

ACCOUNT = "2000000000000000002"


def store_with(profile: dict[str, object] | None) -> ProfileStore:
    store = ProfileStore()
    if profile is not None:
        store.set(ACCOUNT, "settings/profile", dict(profile))
    return store


# ------------------------------------------------------------------ Seam 1: читання


def test_language_without_profile_document_is_uk() -> None:
    store = store_with(None)
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads, "the profile document must be read"


def test_language_profile_without_field_is_uk() -> None:
    store = store_with({})
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads


def test_language_profile_uk_is_uk() -> None:
    store = store_with({"language": "uk"})
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads


def test_language_unknown_code_is_default() -> None:
    store = store_with({"language": "de"})
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads


def test_language_non_string_value_is_default() -> None:
    store = store_with({"language": 5})
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads


def test_language_store_read_error_is_default() -> None:
    store = store_with({"language": "uk"})
    store.fail_profile = True
    assert access.language(session(ACCOUNT), store) == "uk"
    assert store.profile_reads


# ------------------------------------------------------------------ Seam 2: розпізнавання


def test_transcribe_passes_account_language_not_config_language(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Transcribe(monkeypatch)
    app.store.set(SUB, "settings/profile", {"language": "uk"})
    resp = app.post()
    assert resp.status_code == 200
    assert resp.json() == {"text": HEARD}
    assert app.languages == ["uk"]


def test_transcribe_without_profile_passes_default_language(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Transcribe(monkeypatch)
    resp = app.post()
    assert resp.status_code == 200
    assert app.languages == ["uk"]


def test_transcribe_survives_profile_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Transcribe(monkeypatch)
    app.store.set(SUB, "settings/profile", {"language": "uk"})
    app.store.fail_profile = True
    resp = app.post()
    assert resp.status_code == 200
    assert resp.json() == {"text": HEARD}
    assert app.languages == ["uk"]
    assert app.store.profile_reads


def test_transcribe_reads_profile_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Transcribe(monkeypatch)
    resp = app.post()
    assert resp.status_code == 200
    assert app.store.profile_reads, "the profile document must be read"
    assert [on_loop for _, _, on_loop in app.store.profile_reads] == [False] * len(app.store.profile_reads)
