"""Contract tests of `integrations.tts.parts` (slice read-aloud, Seam 1 and I1).

Written by the slice tester from the sealed contract `.engine/slices/read-aloud.md`, without the code;
the 1 500 cut superseded by `.engine/slices/speak-control.md` («частини покривають **увесь** текст»).
Expected parts and cut texts are written by hand from the contract; parts are compared with their
whitespace made single spaces, and the glued text without whitespace («без втрат (крім пробілів і
переносів на стиках)»).
"""

from mamamemory.integrations.tts import parts
from tests.read_aloud_world import (
    S42,
    S47,
    S71,
    THREE,
    THREE_PARTS,
    WEEK,
    WEEK_LINES,
    WEEK_PARTS,
    bare,
    glued,
    norm,
    sentence,
    word,
)

# 44 sentences of 69 characters, one space apart: 3 079 characters, read whole.
SENTENCES_69 = [sentence(i, 69) for i in range(44)]
OVER_BY_SENTENCES = " ".join(SENTENCES_69)

# 25 sentences of 78 characters: 1 974 characters; the 19th closes at exactly 1 500 (19 × 79 − 1).
SENTENCES_78 = [sentence(i, 78) for i in range(25)]
OVER_AT_1500 = " ".join(SENTENCES_78)

# 300 words of 8 characters, one space apart, no sentence boundary: 2 699 characters.
WORDS = [word(i) for i in range(300)]
OVER_BY_WORDS = " ".join(WORDS)


# ------------------------------------------------------------------ Seam 1


def test_short_text_is_one_part() -> None:
    assert parts("Добре, записала.") == ["Добре, записала."]


def test_week_plan_of_15_short_lines_is_three_parts_nothing_left_out() -> None:
    result = parts(WEEK)
    assert [norm(p) for p in result] == WEEK_PARTS
    assert glued(result) == bare(WEEK)


def test_long_sentences_split_on_sentence_boundaries_and_neighbours_packed_greedily() -> None:
    result = parts(THREE)
    assert [norm(p) for p in result] == THREE_PARTS
    assert norm(result[1]).startswith(S42) and norm(result[1]).endswith(S47)
    assert norm(result[0]) == S71


def test_sentence_of_400_characters_splits_on_word_boundaries() -> None:
    text = " ".join(word(i) for i in range(44)) + " кінець."  # 395 + 8 = 403 characters
    assert len(text) == 403
    result = parts(text)
    assert len(result) >= 5
    assert all(len(p) <= 100 for p in result), [len(p) for p in result]
    # No word is broken: the words of the parts are the words of the sentence, in order.
    assert " ".join(result).split() == text.split()


def test_word_longer_than_100_is_cut_at_100() -> None:
    assert parts("ж" * 200) == ["ж" * 100, "ж" * 100]
    assert parts("ж" * 250) == ["ж" * 100, "ж" * 100, "ж" * 50]


def test_text_of_3000_by_sentences_is_read_whole() -> None:
    assert len(OVER_BY_SENTENCES) == 3079
    result = parts(OVER_BY_SENTENCES)
    assert glued(result) == bare(OVER_BY_SENTENCES)
    # Each 69-character sentence is a part of its own (69 + 1 + 69 is over 100): all 44 of them.
    assert [norm(p) for p in result] == SENTENCES_69


def test_text_past_a_sentence_boundary_at_1500_is_read_whole() -> None:
    assert len(OVER_AT_1500) == 1974
    result = parts(OVER_AT_1500)
    assert glued(result) == bare(OVER_AT_1500)
    assert [norm(p) for p in result] == SENTENCES_78


def test_text_over_1500_without_sentence_boundary_keeps_every_word() -> None:
    result = parts(OVER_BY_WORDS)
    assert all(len(p) <= 100 for p in result), [len(p) for p in result]
    assert " ".join(result).split() == WORDS


def test_text_of_3000_without_any_boundary_is_30_parts_of_100() -> None:
    assert parts("ж" * 3000) == ["ж" * 100] * 30


def test_same_text_twice_gives_same_parts() -> None:
    text = WEEK + "\n" + THREE + "\n" + OVER_BY_SENTENCES
    first = parts(text)
    assert first, "a non-empty text gives parts"
    assert parts(text) == first


def test_empty_text_gives_no_parts() -> None:
    assert parts("") == []


# ------------------------------------------------------------------ I1


MIXED = (
    "  \n\nПлан на тиждень готовий 🗓️!\n"
    "• Пн 10:00 — нотаріус (Dr. Müller, вул. Шевченка 5).\n"
    "• Вт — лікар?! Не забудьте картку...\n\n"
    "🔊🔊🔊 Щось «у лапках» … і ще трохи тексту без крапки в кінці\n"
    "Last line in English: call Anna at 9:30 am, ok?   \n"
)
URL_LINE = "Ось посилання: https://example.com/" + "a" * 130 + " — відкрийте."
TWO_HUNDREDS = sentence(1, 100) + " " + sentence(2, 100)
LINES_75 = "\n".join(WEEK_LINES * 5)  # 75 × 19 + 74 = 1 499
LINES_90 = "\n".join(WEEK_LINES * 6)  # 1 799: line 76 starts at 1 500
# The tail after the last sentence boundary has no boundary of its own: it is read too.
TAIL = " ".join(SENTENCES_69[:30]) + " а хвіст без крапки в кінці " + "ж" * 130


def test_I1_parts_are_at_most_100_and_glue_into_the_whole_text() -> None:
    # (input, the whole text after the stripping of whitespace, written by hand)
    cases: list[tuple[str, str]] = [
        ("", ""),
        ("ж" * 1500, "ж" * 1500),
        ("ж" * 1501, "ж" * 1501),
        ("ж" * 10000, "ж" * 10000),
        ("  \n" + "ж" * 1500 + " \n", "ж" * 1500),
        (MIXED, MIXED.strip()),
        (URL_LINE, URL_LINE),
        (TWO_HUNDREDS, TWO_HUNDREDS),
        ("🙂" * 130, "🙂" * 130),
        ("🙂" * 10000, "🙂" * 10000),
        ("Так.", "Так."),
        (OVER_BY_SENTENCES, OVER_BY_SENTENCES),
        (OVER_AT_1500, OVER_AT_1500),
        (OVER_BY_WORDS, OVER_BY_WORDS),
        (LINES_75, LINES_75),
        (LINES_90, LINES_90),
        (TAIL, TAIL),
    ]
    for text, whole in cases:
        assert len(text) <= 10000
        result = parts(text)
        assert all(len(p) <= 100 for p in result), (text[:40], [len(p) for p in result])
        assert glued(result) == bare(whole), text[:40]
