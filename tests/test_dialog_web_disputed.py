"""Disputed tests of the slice dialog on the web side: each takes one reading of a question to the sealed
contract `.engine/slices/dialog.md` (its id in the test name). Sealed after the slice planner answers.
"""

import re

from tests.dialog_web_parts import calls, code_of_app, function_body, mine_rule_declarations

RIGHT = re.compile(
    r"(margin-left\s*:\s*(auto|[1-9][\d.]*(%|px|em|rem|vw))"
    r"|margin-inline-start\s*:\s*(auto|[1-9][\d.]*(%|px|em|rem|vw))"
    r"|margin\s*:\s*\S+\s+\S+\s+\S+\s+(auto|[1-9][\d.]*(%|px|em|rem|vw))\s*(;|$)"
    r"|text-align\s*:\s*(right|end)"
    r"|float\s*:\s*right"
    r"|(align|justify)-self\s*:\s*(flex-end|end|right))"
)


def test_Q7_mine_rule_puts_the_paragraph_on_the_right() -> None:
    rules = mine_rule_declarations()
    assert rules, "index.html has no rule #conversation p.mine"
    assert any(RIGHT.search(body.lower()) for body in rules), f"p.mine is not placed on the right: {rules}"


def test_Q8_every_press_attempt_with_an_answer_gets_its_own_line() -> None:
    code = code_of_app()
    start, end = function_body(code, "pressed")
    mines = calls(code, "renderMine", start, end)
    assert len(mines) == 1, f"pressed calls renderMine {len(mines)} times in its text, not once"
    opened: list[int] = []
    for k in range(start + 1, mines[0]):
        c = code[k]
        if c in "{([":
            opened.append(k)
        elif c in "})]" and opened:
            opened.pop()
    for opener in opened:
        header = re.split(r"[;{}]", code[max(start + 1, opener - 80) : opener])[-1]
        assert not re.search(r"\b(failed|else)\b", header + code[opener - 6 : opener]), (
            f"renderMine stands in a branch `{header.strip()}` — only success or only failure"
        )
