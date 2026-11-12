"""Builder's own test: the privacy page the Google consent screen links to (ADR-0007, Branding)."""

from tests.test_shell_access import T0, Clock, client_for, make_config


def test_privacy_page_is_served_without_a_session_and_names_what_is_kept() -> None:
    client = client_for(make_config(), Clock(T0))
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    for words in ("Firestore", "Google Calendar", "звук не зберігається", "видалити"):
        assert words in resp.text, words
    assert 'id="mamamemory-shell"' not in resp.text
