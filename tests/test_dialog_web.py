"""Contract tests of the slice dialog on the web side (Seam 2): the route `GET /dialog.js`, the rule
`#conversation p.mine` of `index.html`, `renderMine` and its calls in `app.js`.

Written by the slice tester from the sealed contract `.engine/slices/dialog.md` («Seam (contract)»,
«Hardest seams», «Exit criterion»), without the code. The wiring is checked on the text of `app.js`, as the
contract names it («як `tests/test_one_message_web.py`»); `/dialog.js` is compared with `/help.js`.
"""

import re

from fastapi.testclient import TestClient

from tests.dialog_web_parts import (
    WEB,
    app_source,
    arguments,
    backgrounds,
    blank,
    calls,
    code_of_app,
    first_kind_of_mine_text,
    function_body,
    matching,
    mine_rule_declarations,
    rule_declarations,
)
from tests.read_aloud_world import SpeakApp

SHOW_OR_TEXT = re.compile(r"(?<![\w.])(show|renderText)\s*\(")


def _said_before(code: str, start: int, end: int, call: str) -> None:
    source = app_source()
    targets = calls(code, call, start, end)
    assert targets, f"no {call}( call in the block"
    first = targets[0]
    mines = [at for at in calls(code, "renderMine", start, end) if at < first]
    assert mines, f"renderMine is not called before {call}("
    kinds = [kind for at, kind in first_kind_of_mine_text(source, code, start, end) if at < first]
    assert any(kind in ('"said"', "'said'") for kind in kinds), f'no mineText("said", …) before {call}('


def test_dialog_js_is_served_like_the_other_scripts() -> None:
    app = SpeakApp(None)
    dialog = app.client.get("/dialog.js")
    help_js = app.client.get("/help.js")
    assert help_js.status_code == 200, "the reference script /help.js is not served"
    assert dialog.status_code == 200
    assert dialog.headers.get("content-type") == help_js.headers.get("content-type")
    assert dialog.content == (WEB / "dialog.js").read_bytes()


def test_dialog_js_without_sign_in_is_a_302_to_sign_in_like_help_js() -> None:
    app = SpeakApp(None)
    signed_out = TestClient(app.client.app, base_url="https://testserver", follow_redirects=False)
    dialog = signed_out.get("/dialog.js")
    help_js = signed_out.get("/help.js")
    assert dialog.status_code == 302
    assert dialog.status_code == help_js.status_code
    assert dialog.headers.get("location") == help_js.headers.get("location")


def test_app_js_imports_mine_text_from_dialog_js() -> None:
    code = blank(app_source(), strings=False)
    imports = re.findall(r"import\s*\{([^}]*)\}\s*from\s*[\"']/dialog\.js[\"']", code)
    assert any("mineText" in [name.strip() for name in names.split(",")] for names in imports), (
        "app.js does not import mineText from /dialog.js"
    )


def test_index_html_has_a_mine_rule_with_another_background() -> None:
    rules = mine_rule_declarations()
    assert rules, "index.html has no rule #conversation p.mine"
    mine = backgrounds(rules)
    assert mine, "the rule #conversation p.mine sets no background"
    answer = backgrounds(rule_declarations(r"#conversation\s+p"))
    assert answer, "the reference rule #conversation p has no background"
    assert not set(mine) & set(answer), f"p.mine has the same background as the answers: {mine}"


def test_render_mine_is_a_p_of_class_mine_in_conversation_by_text_content() -> None:
    code = code_of_app()
    source = blank(app_source(), strings=False)
    start, end = function_body(code, "renderMine")
    body = source[start:end]
    assert re.search(r"createElement\s*\(\s*[\"']p[\"']\s*\)", body), "renderMine makes no <p>"
    assert re.search(r"(className\s*=\s*[\"']mine[\"']|classList\.add\s*\(\s*[\"']mine[\"']\s*\))", body), (
        "the paragraph of renderMine has no class mine"
    )
    assert re.search(r"\.textContent\s*=", body), "renderMine does not set textContent"
    assert "innerHTML" not in body and "insertAdjacentHTML" not in body, "renderMine writes HTML"
    assert re.search(r"\bconversation\s*\.\s*(append|appendChild)\s*\(", body), (
        "renderMine does not put the paragraph into #conversation"
    )


def test_render_mine_has_no_speak_button() -> None:
    code = code_of_app()
    source = blank(app_source(), strings=False)
    start, end = function_body(code, "renderMine")
    assert not calls(code, "speakButton", start, end), "renderMine adds a 🔊 button"
    assert not calls(code, "speak", start, end), "renderMine speaks"
    assert "🔊" not in source[start:end]


def test_render_mine_with_empty_text_returns_before_making_the_paragraph() -> None:
    code = code_of_app()
    source = blank(app_source(), strings=False)
    start, end = function_body(code, "renderMine")
    params_at = code.rfind("(", 0, start)
    params = [p.strip() for p in source[params_at + 1 : matching(code, params_at)].split(",") if p.strip()]
    assert params, "renderMine takes no text"
    text = re.escape(params[0].split("=")[0].strip())
    made = re.search(r"createElement\s*\(", code[start:end])
    assert made, "renderMine makes no element"
    guarded = False
    for found in re.finditer(r"\bif\s*\(", code[start : start + made.start()]):
        open_at = start + found.end() - 1
        close = matching(code, open_at)
        condition = source[open_at + 1 : close]
        if re.search(rf"\b{text}\b", condition) and re.match(r"\s*\{?\s*return\b", code[close + 1 :]):
            guarded = True
    assert guarded, "renderMine does not return on an empty text before making the paragraph"


def test_render_mine_changes_neither_last_reply_to_nor_the_voice_state() -> None:
    code = code_of_app()
    start, end = function_body(code, "renderMine")
    body = code[start:end]
    assert not re.search(r"\blastReplyTo\s*=(?!=)", body), "renderMine changes lastReplyTo"
    assert not re.search(r"(?<![\w.])voice\s*=(?!=)", body), "renderMine changes the voice state"
    assert not calls(code, "render", start, end), "renderMine re-renders the voice state"


def test_send_shows_mine_said_before_message() -> None:
    code = code_of_app()
    start, end = function_body(code, "send")
    _said_before(code, start, end, "message")


def test_send_message_action_shows_mine_said_before_message() -> None:
    code = code_of_app()
    source = app_source()
    found = re.search(r"\.do\s*===?\s*[\"']send_message[\"']", source)
    assert found, "app.js has no send_message branch"
    brace = code.index("{", found.end())
    end = matching(code, brace)
    _said_before(code, brace, end, "message")


def test_upload_shows_mine_file_name_before_upload_file() -> None:
    code = code_of_app()
    source = app_source()
    start, end = function_body(code, "upload")
    targets = calls(code, "uploadFile", start, end)
    assert targets, "upload does not call uploadFile"
    first = targets[0]
    assert [at for at in calls(code, "renderMine", start, end) if at < first], (
        "renderMine is not called before uploadFile("
    )
    files = [
        arguments(source, code, at)
        for at, kind in first_kind_of_mine_text(source, code, start, end)
        if at < first and kind in ('"file"', "'file'")
    ]
    assert files, 'no mineText("file", …) before uploadFile('
    assert any(len(args) > 1 and re.search(r"\.name\b", args[1]) for args in files), (
        'mineText("file", …) is not given the name of the file'
    )


def test_pressed_shows_mine_button_label_after_null_check_and_before_the_answer() -> None:
    code = code_of_app()
    source = app_source()
    start, end = function_body(code, "pressed")
    check = re.search(r"\banswer\s*[!=]==?\s*null\b", code[start:end])
    assert check, "pressed has no answer === null check"
    after = start + check.end()
    answers = [start + m.start() for m in SHOW_OR_TEXT.finditer(code[start:end]) if start + m.start() > after]
    assert answers, "pressed shows no answer after the null check"
    first = answers[0]
    assert [at for at in calls(code, "renderMine", start, end) if after < at < first], (
        "renderMine is not called between the null check and show( / renderText("
    )
    buttons = [
        arguments(source, code, at)
        for at, kind in first_kind_of_mine_text(source, code, start, end)
        if after < at < first and kind in ('"button"', "'button'")
    ]
    assert buttons, 'no mineText("button", …) between the null check and the answer'
    assert any(len(args) > 1 and re.search(r"\.label\b", args[1]) for args in buttons), (
        'mineText("button", …) is not given the label of the button'
    )
