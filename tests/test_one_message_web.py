"""Contract tests of the slice one-message on the web side (Seam 2): the route `GET /buttons.js`,
the wiring of `app.js` to `bindButtons`, and `failed: true` on `NOT_SENT`.

Written by the slice tester from the sealed contract `.engine/slices/one-message.md` («Seam (contract)»,
«Hardest seams», «Exit criterion»), without the code. The wiring is checked on the text of `app.js`, as
`tests/test_f5_measure_web.py` does; `/buttons.js` is compared with `/help.js`, the script the contract says
it is served like.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.read_aloud_world import SpeakApp

WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"

LOOP_OR_HANDLER = re.compile(r"\b(for|while|forEach|map|addEventListener|onclick)\b")


def _code_only(source: str) -> str:
    """The source with comments and the insides of string literals blanked to spaces (positions are kept)."""
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            end = source.find("\n", i)
            end = n if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out[i:end] = [c if c == "\n" else " " for c in source[i:end]]
            i = end
        elif ch in "\"'`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            out[i + 1 : j] = [c if c == "\n" else " " for c in source[i + 1 : j]]
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _matching(code: str, open_at: int) -> int:
    pairs = {"{": "}", "(": ")", "[": "]"}
    stack = [pairs[code[open_at]]]
    for k in range(open_at + 1, len(code)):
        c = code[k]
        if c in pairs:
            stack.append(pairs[c])
        elif stack and c == stack[-1]:
            stack.pop()
            if not stack:
                return k
    return -1


def _show_body(code: str) -> tuple[int, int]:
    found = re.search(r"\bfunction\s+show\s*\(|\bshow\s*=\s*(async\s*)?(function\b|\([^)]*\)\s*=>)", code)
    assert found, "app.js has no function show"
    brace = code.index("{", found.end())
    end = _matching(code, brace)
    assert end > brace, "the body of show is not closed"
    return brace, end


def _enclosing_openers(code: str, start: int, at: int) -> list[int]:
    """Positions of the brackets still open at `at`, counting from `start`."""
    stack: list[int] = []
    for k in range(start, at):
        c = code[k]
        if c in "{([":
            stack.append(k)
        elif c in "})]" and stack:
            stack.pop()
    return stack


def _source() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


def test_buttons_js_is_served_like_the_other_scripts() -> None:
    app = SpeakApp(None)
    buttons = app.client.get("/buttons.js")
    help_js = app.client.get("/help.js")
    assert help_js.status_code == 200, "the reference script /help.js is not served"
    assert buttons.status_code == 200
    assert buttons.headers.get("content-type") == help_js.headers.get("content-type")
    assert buttons.content == (WEB / "buttons.js").read_bytes()

    signed_out = TestClient(app.client.app, base_url="https://testserver", follow_redirects=False)
    assert signed_out.get("/buttons.js").status_code == signed_out.get("/help.js").status_code


def test_app_js_imports_bind_buttons_from_buttons_js() -> None:
    imports = re.findall(r"import\s*\{([^}]*)\}\s*from\s*[\"']/buttons\.js[\"']", _source())
    assert any("bindButtons" in [name.strip() for name in names.split(",")] for names in imports), (
        "app.js does not import bindButtons from /buttons.js"
    )


def test_show_calls_bind_buttons_exactly_once_outside_click_handler_and_clarify_loop() -> None:
    code = _code_only(_source())
    body_start, body_end = _show_body(code)
    calls = [m.start() for m in re.finditer(r"\bbindButtons\s*\(", code) if body_start < m.start() < body_end]
    assert len(calls) == 1, f"show calls bindButtons {len(calls)} times in its text, not once"
    for opener in _enclosing_openers(code, body_start + 1, calls[0]):
        before = code[max(body_start + 1, opener - 60) : opener]
        stmt = re.split(r"[;{}]", before)[-1]
        assert not LOOP_OR_HANDLER.search(stmt), (
            f"bindButtons is called inside `{stmt.strip()}` — a loop or a click handler"
        )
    arguments = code[calls[0] : _matching(code, code.index("(", calls[0])) + 1]
    assert re.search(r"\bpost\b", arguments), "bindButtons is not given post"


def test_not_sent_carries_failed_true() -> None:
    code = _code_only(_source())
    source = _source()
    found = re.search(r"\b(const|let|var)\s+NOT_SENT\s*=", code)
    assert found, "app.js has no NOT_SENT"
    end = code.find(";", found.end())
    statement = source[found.start() : end if end > 0 else len(source)]
    assert re.search(r"\bfailed\s*:\s*true\b", statement), "NOT_SENT does not carry failed: true"
