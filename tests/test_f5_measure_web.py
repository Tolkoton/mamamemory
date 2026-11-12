"""Contract tests of the slice f5-measure on the web side: the route `GET /player.js` and the wiring of
`app.js` to the new player.

Written by the slice tester from the sealed contract `.engine/slices/f5-measure.md` («Seam (contract)»,
«Exit criterion»), without the code. `/player.js` is compared with `/speak.js`, the script the contract
says it is served like; its body is compared with the file `web/player.js`.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.read_aloud_world import SpeakApp

WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"


def test_player_js_is_served_like_the_other_scripts() -> None:
    app = SpeakApp(None)
    player = app.client.get("/player.js")
    speak = app.client.get("/speak.js")
    assert speak.status_code == 200, "the reference script /speak.js is not served"
    assert player.status_code == 200
    assert player.headers.get("content-type") == speak.headers.get("content-type")
    assert player.content == (WEB / "player.js").read_bytes()
    assert b"revokeObjectURL" in player.content, "the served player.js does not free the object URL"
    assert b"X-Parts" in speak.content

    signed_out = TestClient(app.client.app, base_url="https://testserver", follow_redirects=False)
    assert signed_out.get("/player.js").status_code == signed_out.get("/speak.js").status_code


def test_app_js_imports_make_play_from_player_js_and_builds_no_audio_itself() -> None:
    source = (WEB / "app.js").read_text(encoding="utf-8")
    imports = re.findall(r"import\s*\{([^}]*)\}\s*from\s*[\"']/player\.js[\"']", source)
    assert any("makePlay" in [name.strip() for name in names.split(",")] for names in imports), (
        "app.js does not import makePlay from /player.js"
    )
    assert re.search(r"makePlay\(\s*Audio\s*,\s*URL\s*\)", source), "app.js does not pass Audio and URL"
    assert not re.search(r"new\s+Audio\s*\(", source), "app.js still builds its own Audio"
