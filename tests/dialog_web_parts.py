"""Helpers of the dialog contract tests (slice dialog): reading the text of `app.js` and `index.html`.

Written by the slice tester; comments and string insides are blanked so a call in a comment or a string
does not count, and positions are kept so the original text can be read at the same offset.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "mamamemory" / "web"


def blank(source: str, strings: bool) -> str:
    """The source with comments (and, with `strings`, the insides of string literals) blanked to spaces."""
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
            if strings:
                out[i + 1 : j] = [c if c == "\n" else " " for c in source[i + 1 : j]]
            i = j + 1
        else:
            i += 1
    return "".join(out)


def matching(code: str, open_at: int) -> int:
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


def app_source() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


def code_of_app() -> str:
    return blank(app_source(), strings=True)


def function_body(code: str, name: str) -> tuple[int, int]:
    """(start, end) of the braces of the function `name` in `code`; asserts it exists."""
    found = re.search(
        rf"\bfunction\s+{name}\s*\(|\b{name}\s*=\s*(async\s*)?"
        r"(function\b[^(]*\(|\([^)]*\)\s*=>|\w+\s*=>)",
        code,
    )
    assert found, f"app.js has no function {name}"
    params = code.find("(", found.start())
    after = matching(code, params) if params >= 0 and code[params] == "(" else found.end()
    brace = code.index("{", max(after, found.start()))
    end = matching(code, brace)
    assert end > brace, f"the body of {name} is not closed"
    return brace, end


def calls(code: str, name: str, start: int, end: int) -> list[int]:
    return [m.start() for m in re.finditer(rf"(?<![\w.]){name}\s*\(", code) if start < m.start() < end]


def arguments(source: str, code: str, at: int) -> list[str]:
    """The top-level arguments (original text) of the call starting at `at`."""
    open_at = code.index("(", at)
    close = matching(code, open_at)
    parts, depth, last = [], 0, open_at + 1
    for k in range(open_at + 1, close):
        c = code[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(source[last:k].strip())
            last = k + 1
    parts.append(source[last:close].strip())
    return parts


def first_kind_of_mine_text(source: str, code: str, start: int, end: int) -> list[tuple[int, str]]:
    """(position, first argument) of every `mineText(` call between start and end."""
    return [(at, arguments(source, code, at)[0]) for at in calls(code, "mineText", start, end)]


def css_rules(html: str) -> list[tuple[str, str]]:
    """(selector, declarations) of every rule inside <style> of the page."""
    styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S))
    styles = re.sub(r"/\*.*?\*/", "", styles, flags=re.S)
    return [(sel.strip(), body.strip()) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", styles)]


def rule_declarations(selector_pattern: str) -> list[str]:
    """The declarations of every rule of index.html with a selector matching the pattern."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    found = []
    for selector, body in css_rules(html):
        if any(re.fullmatch(selector_pattern, s.strip()) for s in selector.split(",")):
            found.append(body)
    return found


def mine_rule_declarations() -> list[str]:
    """The declarations of every rule whose selector list holds `#conversation p.mine`."""
    return rule_declarations(r"#conversation\s+p\.mine")


def backgrounds(rules: list[str]) -> list[str]:
    """The values of every `background` / `background-color` declaration of the rules, lower-cased."""
    return [
        m.group(1).strip().lower()
        for body in rules
        for m in re.finditer(r"background(?:-color)?\s*:\s*([^;]+)", body)
    ]
