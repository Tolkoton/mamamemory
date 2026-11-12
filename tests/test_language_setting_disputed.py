"""Disputed contract tests of slice language-setting (F5 S1): they stand on Q1 of the tester's questions.

Written by the slice tester from the sealed contract `.engine/slices/language-setting.md`, without the code.
"""

from mamamemory import access
from tests.language_setting_world import ProfileStore, session

MINE = "3000000000000000003"
OTHER = "4000000000000000004"


def test_language_reads_only_the_session_accounts_profile() -> None:
    store = ProfileStore()
    store.set(OTHER, "settings/profile", {"language": "de"})
    store.set(MINE, "settings/profile", {"language": "uk"})
    assert access.language(session(MINE), store) == "uk"
    assert store.profile_reads
    assert {(account, path) for account, path, _ in store.profile_reads} == {(MINE, "settings/profile")}
