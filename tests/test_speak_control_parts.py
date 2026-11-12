"""Contract tests of `integrations.tts.parts` (slice speak-control, Seam 1 and I1).

Written by the slice tester from the sealed contract `.engine/slices/speak-control.md`, without the code.
The limit `MAX_CHARS` is gone: the parts cover the whole text (after its whitespace is stripped). Glued
texts are compared without any whitespace — «до пробілів і переносів на стиках».
"""

from mamamemory.integrations.tts import parts
from tests.read_aloud_world import bare, glued, sentence, word

PART = 100


def assert_whole(text: str, label: str) -> None:
    got = parts(text)
    assert glued(got) == bare(text), f"{label}: the glued parts are not the whole text"
    too_long = [len(p) for p in got if len(p) > PART]
    assert too_long == [], f"{label}: parts longer than {PART}: {too_long}"


def test_text_of_3000_characters_is_read_whole_in_parts_of_at_most_100() -> None:
    # 40 sentences of 74 characters, one space apart: 40 × 75 − 1 = 2 999 characters, plus «!» → 3 000.
    text = " ".join(sentence(i, 74) for i in range(40)) + "!"
    assert len(text) == 3000
    got = parts(text)
    assert glued(got) == bare(text)
    assert all(len(p) <= PART for p in got), [len(p) for p in got]
    # The last characters of the text are in the last part: nothing after 1 500 is lost.
    assert bare(got[-1]).endswith("а.!"), got[-1]


def test_I1_speak_control_glued_parts_are_the_whole_stripped_text_each_at_most_100() -> None:
    # The empty edge: an empty and a whitespace-only text have no parts.
    assert parts("") == []
    assert parts("  \n\t ") == []

    cases: dict[str, str] = {}
    # One character; exactly 100; 101 with no space (a word longer than 100).
    cases["one character"] = "Я"
    cases["exactly 100"] = sentence(1, 100)
    cases["101 without a space"] = "ж" * 101
    # The old edge: 1 501 characters of sentences, and a text just past it with a tail and no final boundary.
    # 15 sentences of 99, one space apart (1 499), a space and one letter: 1 501.
    cases["1 501 in sentences"] = " ".join(sentence(i, 99) for i in range(15)) + " Я"
    cases["tail after the last boundary"] = (
        " ".join(sentence(i, 69) for i in range(30)) + " і хвіст без крапки"
    )
    # The upper edge of the domain: 10 000 characters (10 sentences of 999 + 9 spaces + one 1-char tail).
    upper = " ".join("ш" * 998 + "." for _ in range(10)) + "ю"
    assert len(upper) == 10000
    cases["10 000 characters"] = upper
    # Words only, no sentence boundary at all, 2 699 characters.
    cases["words only"] = " ".join(word(i) for i in range(300))
    # Lines (a week plan), Latin, emoji (single code points), «…», «?», «!» and a long word inside.
    cases["mixed lines"] = "\n".join(
        [
            "Пн 09:00 нотаріус 🗂️ — взяти паспорт",
            "Meeting with Dr. Müller at 10:15? Yes!",
            "Емодзі 😀😀😀 у рядку… і далі",
            "д" * 250,
            "Last line without an end",
        ]
        * 8
    )
    # Leading and trailing whitespace around a long text.
    cases["whitespace around"] = "\n\n   " + " ".join(sentence(i, 55) for i in range(40)) + "  \n\t"
    for label, text in cases.items():
        assert_whole(text, label)
    # A repeat: the same text again gives the whole text again.
    assert_whole(cases["mixed lines"], "mixed lines, again")
