"""Contract tests of the slice f5-measure: the report `docs/f5-measure.md` and the owner's phone-pass card.

Written by the slice tester from the sealed contract `.engine/slices/f5-measure.md` («Seam (contract)»,
«Exit criterion»), without the code. The report is checked against the files the contract names as its
sources: the premise log, the earlier measure reports (whose revisions came before this deploy) and the
Node test files of this slice.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "f5-measure.md"
PREMISE_LOG = ROOT / ".engine" / "premises" / "premise-log.md"
WEB = ROOT / "src" / "mamamemory" / "web"
TASKS = ROOT / "tasks"
EARLIER_REPORTS = [ROOT / "docs" / "f2-measure.md", ROOT / "docs" / "f3-measure.md"]
PREMISES = ["P-TTS", "P-TTS-LONG", "P-TTS-PART", "P-TTS-SA"]
REVISION = re.compile(r"mamamemory-(\d{5})-[a-z0-9]{3}")


def report_text() -> str:
    assert REPORT.is_file(), f"{REPORT} does not exist"
    return REPORT.read_text(encoding="utf-8")


def count(n: int) -> re.Pattern[str]:
    return re.compile(rf"(?<!\d){n}\s*(?:/|з|of|із)\s*{n}(?!\d)")


def mentions(line: str, premise: str) -> bool:
    """The line names this premise and not only a longer id that starts with it (P-TTS vs P-TTS-LONG)."""
    return re.search(re.escape(premise) + r"(?![\w-])", line) is not None


def log_status(premise: str) -> str:
    """The first backticked word of the status cell of the premise's row in the premise log."""
    for line in PREMISE_LOG.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 4 and cells[1] == premise:
            token = re.search(r"`([^`]+)`", cells[4])
            assert token, f"the premise log row of {premise} has no backticked status"
            return token.group(1)
    raise AssertionError(f"{premise} has no row in {PREMISE_LOG}")


def slice_test_names() -> list[str]:
    """The names of the Node tests in this slice's files: speak_silence*.test.js and player*.test.js."""
    names: list[str] = []
    for path in sorted(WEB.glob("*.test.js")):
        if path.name.startswith(("speak_silence", "player")):
            names += re.findall(r"\btest\(\s*[\"'`]([^\"'`]+)[\"'`]", path.read_text(encoding="utf-8"))
    return names


def test_report_names_a_revision_newer_than_the_earlier_measures() -> None:
    earlier = [int(n) for path in EARLIER_REPORTS for n in REVISION.findall(path.read_text(encoding="utf-8"))]
    named = [int(n) for n in REVISION.findall(report_text())]
    assert named, "the report names no Cloud Run revision"
    assert max(named) > max(earlier), f"the report names no revision after {max(earlier):05d}"


def test_report_gives_the_smoke_of_each_f5_slice_with_numbers() -> None:
    lines = report_text().splitlines()
    guide = [line for line in lines if "smoke_guide" in line]
    assert guide, "the report does not name smoke_guide.py"
    assert any(count(5).search(line) for line in guide), "the smoke of S2 does not say 5 з 5"
    read_aloud = [line for line in lines if "smoke_read_aloud" in line]
    assert read_aloud, "the report does not name smoke_read_aloud.py"
    assert any(count(8).search(line) for line in read_aloud), "the smoke of S3 does not say 8 з 8"
    s1 = [
        line
        for line in lines
        if "language-setting" in line or "language_setting" in line or re.search(r"\bS1\b", line)
    ]
    assert s1, "the report does not name S1"
    assert any(re.search(r"\d", line.replace("S1", "")) for line in s1), "the tests of S1 carry no number"


def test_report_premise_status_matches_the_premise_log() -> None:
    lines = report_text().splitlines()
    for premise in PREMISES:
        status = log_status(premise)
        where = [
            i
            for i, line in enumerate(lines)
            if mentions(line, premise)
            or (premise == "P-TTS-SA" and "сервісн" in line.lower() and "акаунт" in line)
        ]
        assert where, f"the report does not name {premise}"
        near = [" ".join(lines[i : i + 2]) for i in where]
        assert any(
            f"`{status}`" in chunk or re.search(rf"(?<![\w-]){status}(?![\w-])", chunk) for chunk in near
        ), f"the report does not give {premise} the status `{status}` of its premise log row"


def test_report_says_what_is_left_for_the_owner() -> None:
    text = report_text()
    assert "734" in text, "the report does not name card 734"
    assert "телефон" in text.lower(), "the report does not name the owner's pass on the phone"


def test_report_says_cards_735_and_736_are_fixed_naming_the_tests() -> None:
    text = report_text()
    assert "735" in text and "736" in text, "the report does not name cards 735 and 736"
    names = slice_test_names()
    assert names, "this slice has no Node test files to name"
    assert any(name in text for name in names), "the report names none of the tests that fix 735 and 736"


def test_the_phone_pass_is_a_card_on_the_board() -> None:
    cards = [
        path
        for path in TASKS.rglob("*.md")
        if path.is_file()
        and "що ти вмієш" in (body := path.read_text(encoding="utf-8")).lower()
        and any(word in body.lower() for word in ("польот", "авіарежим", "airplane", "flight mode"))
        and "Не вдалося озвучити." in body
    ]
    assert cards, "no card under tasks/ asks for the phone pass (guide, «що ти вмієш?», 🔊, airplane mode)"
