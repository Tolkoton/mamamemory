"""Contract tests of the slice one-add-button: one «＋» button in `web/index.html`, its wiring in
`web/app.js`, and the new line of the guide; Seam 1-2.

Written by the slice tester from the sealed contract `.engine/slices/one-add-button.md`, without the code.
The two guide lines before the 🔊 line follow the sealed contract `.engine/slices/case-recall.md`
(supersede of `NEW_GUIDE`). The `accept` of `#add-input` is the one the sealed contract photo-and-file
names for «+». The check of
`app.js` is static and strict, as Seam 1 asks: comments and the text of strings are not code; the field of
`add-input` is found by its id (or through a literal pair `["add", "add-input"]` a loop takes apart), the
button `add` must open that same field on click, and a `change` listener of that same field must call
`upload`.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

from mamamemory import assistant
from tests.guide_world import plain

WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"
ACCEPT = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
    "text/plain",
}
NEW_LINE = "• «Запиши до пані Шмідт: …», або ＋ (фото чи файл) — покладу у справу."
NEW_GUIDE = (
    "Я допомагаю планувати й пам'ятати справи. Що можна сказати:\n"
    "• «Додай задачу подзвонити нотаріусу в понеділок» — поставлю в календар.\n"
    "• «Сплануй тиждень» — складу план з усіх задач.\n"
    "• «Запиши до пані Шмідт: …», або ＋ (фото чи файл) — покладу у справу.\n"
    "• «Переклади … до …» — перенесу в іншу справу.\n"
    "• «Працюю над …», потім «що я робила з …?» — запам'ятаю й нагадаю.\n"
    "• «Що ми знаємо про пані Шмідт?», «які плани на тиждень?» — розповім.\n"
    "• 🔊 біля відповіді — прочитаю вголос.\n"
    "Не зрозумію — перепитаю."
)


class Element:
    def __init__(self, tag: str, attrs: dict[str, str | None]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.text = ""


class Page(HTMLParser):
    """Every element of the page with its attributes and the text directly inside it."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[Element] = []
        self.open: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.elements.append(element)
        if tag not in {"input", "img", "br", "meta", "link", "hr", "source"}:
            self.open.append(element)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i].tag == tag:
                del self.open[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.open:
            self.open[-1].text += data


def page() -> list[Element]:
    parser = Page()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return parser.elements


def by_id(elements: list[Element], ident: str) -> list[Element]:
    return [e for e in elements if e.attrs.get("id") == ident]


def code_of(source: str) -> str:
    """`app.js` with its comments removed; strings and template literals are kept as they are."""
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c in "\"'`":
            j = i + 1
            while j < n and source[j] != c:
                j += 2 if source[j] == "\\" else 1
            out.append(source[i : j + 1])
            i = j + 1
        elif source.startswith("//", i):
            j = source.find("\n", i)
            i = n if j < 0 else j
        elif source.startswith("/*", i):
            j = source.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def app_code() -> str:
    return code_of((WEB / "app.js").read_text(encoding="utf-8"))


Q = r"[\"'`]"


def get_by_id(ident: str) -> str:
    """A regex of `document.getElementById("<ident>")` or `document.querySelector("#<ident>")`."""
    name = re.escape(ident)
    return (
        rf"document\s*\.\s*(?:getElementById\s*\(\s*{Q}{name}{Q}\s*\)"
        rf"|querySelector\s*\(\s*{Q}#{name}{Q}\s*\))"
    )


def names_bound_to(code: str, expression: str) -> list[str]:
    return re.findall(rf"(?:const|let|var)\s+(\w+)\s*=\s*{expression}", code)


def element_expressions(code: str, ident: str, loop_name: str | None) -> list[str]:
    """The regexes that denote the element `ident`: its lookup, a name bound to it, or the loop's lookup."""
    lookups = [get_by_id(ident)]
    if loop_name is not None:
        lookups.append(rf"document\s*\.\s*getElementById\s*\(\s*{loop_name}\s*\)")
    found = list(lookups)
    for lookup in lookups:
        found += [rf"\b{re.escape(n)}\b" for n in names_bound_to(code, lookup)]
    return found


def wired(code: str) -> tuple[bool, bool]:
    """(click on `add` opens the field `add-input`, `change` of that field calls `upload`)."""
    button_name: str | None = None
    input_name: str | None = None
    if re.search(rf"\[\s*{Q}add{Q}\s*,\s*{Q}add-input{Q}\s*\]", code):
        loop = re.search(r"for\s*\(\s*(?:const|let|var)\s*\[\s*(\w+)\s*,\s*(\w+)\s*\]\s*of\b", code)
        if loop:
            button_name, input_name = loop.group(1), loop.group(2)
    fields = element_expressions(code, "add-input", input_name)
    buttons = element_expressions(code, "add", button_name)
    opens = False
    for button in buttons:
        for field in fields:
            on_click = (
                rf"{button}\s*\.\s*(?:addEventListener\s*\(\s*{Q}click{Q}\s*,|onclick\s*=)"
                rf"[^;]{{0,200}}?{field}\s*\.\s*(?:click|showPicker)\s*\(\s*\)"
            )
            opens = opens or re.search(on_click, code, re.DOTALL) is not None
    uploads = False
    for field in fields:
        on_change = (
            rf"{field}\s*\.\s*(?:addEventListener\s*\(\s*{Q}change{Q}\s*,|onchange\s*=)"
            rf"[^;]{{0,200}}?\bupload\s*\("
        )
        uploads = uploads or re.search(on_change, code, re.DOTALL) is not None
    return opens, uploads


def test_index_html_has_no_photo_button_and_no_photo_input() -> None:
    elements = page()
    assert by_id(elements, "photo") == [], "index.html still has the button #photo"
    assert by_id(elements, "photo-input") == [], "index.html still has the field #photo-input"


def test_add_button_is_the_plus_with_the_label_for_photo_or_file() -> None:
    buttons = by_id(page(), "add")
    assert len(buttons) == 1, "index.html has no single #add"
    add = buttons[0]
    assert add.tag == "button", add.tag
    assert add.text.strip() == "＋", add.text
    assert add.attrs.get("aria-label") == "Додати фото чи файл", add.attrs.get("aria-label")


def test_the_only_file_field_is_add_input_with_the_same_accept_and_no_capture() -> None:
    files = [e for e in page() if e.tag == "input" and (e.attrs.get("type") or "").lower() == "file"]
    assert [e.attrs.get("id") for e in files] == ["add-input"], (
        "the page's file fields are not just #add-input"
    )
    field = files[0]
    accept = {part.strip() for part in (field.attrs.get("accept") or "").split(",")}
    assert accept == ACCEPT, accept
    assert "capture" not in field.attrs, "#add-input has capture"


def test_app_js_has_no_photo_pair() -> None:
    code = app_code()
    assert not re.search(rf"{Q}photo{Q}", code), "app.js still refers to the button photo"
    assert not re.search(rf"{Q}#?photo-input{Q}", code), "app.js still refers to the field photo-input"


def test_app_js_add_opens_add_input_and_its_change_goes_to_upload() -> None:
    opens, uploads = wired(app_code())
    assert opens, "app.js does not open #add-input on a click of #add"
    assert uploads, "app.js does not send the chosen file of #add-input to upload"


def test_guide_has_the_plus_line_no_camera_and_the_rest_as_it_was() -> None:
    text = assistant.guide_text("uk")
    assert NEW_LINE in plain(text).split("\n"), text
    assert "📷" not in text, text
    assert plain(text) == NEW_GUIDE, text
