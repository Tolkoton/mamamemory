"""Contract tests of the slice access-shell that waited for the slice planner's answers to the
questions Q1 and Q2, rewritten by a fresh slice tester after both were answered with the other
reading (testing rows of 2026-11-05T21:58Z):

- Q1: the scopes are checked by `exchange` (MissingScopes); the callback does not check
  `Tokens.scopes` itself. The test of the stricter reading is removed; what the callback does on
  MissingScopes is already tested in tests/test_auth_callback.py.
- Q2: «`.` чи `..`» in the refused account ids means the whole value; an id with a dot inside is
  not refused. That reading is tested here.

Written from the sealed contract `.engine/slices/access-shell.md`.
"""

from mamamemory.integrations.store import InMemoryStore, document_path


def test_account_id_with_a_dot_inside_is_accepted_under_its_account() -> None:
    assert document_path("a.b", "private/google") == "accounts/a.b/private/google"
    assert document_path("1.2", "") == "accounts/1.2"

    store = InMemoryStore()
    store.set("a.b", "private/google", {"refresh_token": "rt-dot"})
    assert store.get("a.b", "private/google") == {"refresh_token": "rt-dot"}
    assert store.get("a", "private/google") is None
