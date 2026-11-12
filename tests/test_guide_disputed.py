"""Disputed contract tests of the slice guide: each takes one reading of a line that can be read two ways and
carries the id of its question to the contract (Q1-Q3). Sealed after the slice planner answers.

Written by the slice tester from the sealed contract `.engine/slices/guide.md`, without the code.
"""

import re

from mamamemory import assistant
from tests.guide_world import GUIDE, Guide
from tests.test_one_task_planning import NOW

HINT = (
    "help — мама питає, що вміє асистент чи як з ним працювати («що ти вмієш?», «як з тобою працювати?», "
    "«допоможи»)"
)


def flat(text: str) -> str:
    """Whitespace made single spaces and apostrophes one character: the contract does not fix typography."""
    return re.sub(r"\s+", " ", re.sub("[’ʼ`]", "'", text)).strip()


def test_Q1_guide_text_is_the_contract_block_character_for_character() -> None:
    """Q1: the text is the contract's block as written — the ASCII apostrophe of «пам'ятати», its lines joined
    by one "\\n", nothing before the first line or after the last."""
    assert assistant.guide_text("uk") == GUIDE


def test_Q2_the_flag_holds_the_time_of_the_open_that_showed_the_guide() -> None:
    """Q2: `{"shown": now}` is the `now` given to that open — the datetime itself or its ISO-8601 string."""
    g = Guide()
    g.open(NOW)
    flag = g.flag()
    assert flag is not None, "the flag was not written"
    assert set(flag) == {"shown"}, flag
    assert flag["shown"] in (NOW, NOW.isoformat()), flag


def test_Q3_route_prompt_carries_the_help_hint_in_the_contract_words() -> None:
    """Q3: the hint is given to the route model in the contract's words."""
    g = Guide()
    g.ai.plain_intent("other")
    g.say("щось", "o1")
    assert g.ai.prompts.get("route"), "the route model was not asked"
    assert flat(HINT) in flat(g.ai.prompts["route"][-1]), g.ai.prompts["route"][-1]
