"""Contract tests of the slice skeleton-measure: the report `docs/f1-measure.md`, the premise log, the card.

Written by the slice tester from the sealed contract `.engine/slices/skeleton-measure.md` («Goal», «Seam
(contract)», «Hardest seams» Seam 2, «Exit criterion»), without the code. The report is checked against the
files the contract names as its sources: Sonko's verbatim output and the rows of the premise log.
"""

import re

from tests.f1_measure_sources import (
    REVISION,
    STATUSES,
    log_row,
    log_status,
    mentions,
    report_text,
    sonko_output,
    task_files,
)

NUMBER = r"\d+(?:[.,]\d+)?"


def lines_with(*stems: str) -> list[str]:
    return [line for line in report_text().splitlines() if any(stem in line.lower() for stem in stems)]


def test_sonko_output_measured_ten_of_ten() -> None:
    text = sonko_output()
    assert "MEASURED: 10 of 10 calls" in text
    assert re.search(r"HEARD: \d+ of \d+ keywords", text)
    assert re.search(r"SECONDS: ", text)


def test_report_names_the_revision() -> None:
    assert REVISION in report_text()


def test_report_gives_cold_and_warm_seconds() -> None:
    cold = lines_with("холодн")
    warm = lines_with("тепл")
    assert any(re.search(NUMBER, line) for line in cold), "the report gives no cold number"
    assert any(re.search(NUMBER, line) for line in warm), "the report gives no warm number"


def test_report_gives_idle_minutes() -> None:
    minutes = [int(n) for n in re.findall(r"(\d+)\s*хв", report_text())]
    assert any(n >= 20 for n in minutes), f"the report names no idle time of 20 minutes or more: {minutes}"


def test_report_says_what_the_cold_number_holds() -> None:
    text = report_text().lower()
    assert "контейнер" in text
    assert "імпорт" in text
    assert "переадрес" in text or "302" in text or "редирект" in text


def test_report_gives_k_of_n_as_sonko_printed() -> None:
    found = re.findall(r"HEARD: (\d+) of (\d+) keywords", sonko_output())
    assert found, "Sonko's output has no HEARD line"
    k, n = found[-1]
    assert re.search(rf"(?<!\d){k}\s*(?:з|із|of|/)\s*{n}(?!\d)", report_text()), (
        f"the report does not say {k} з {n}"
    )


def test_report_gives_seconds_min_median_max() -> None:
    rows = lines_with("медіан")
    assert any(len(re.findall(NUMBER, row)) >= 3 for row in rows), "no line gives min / median / max seconds"


def test_report_says_the_recordings_are_synthetic() -> None:
    assert "синтез" in report_text().lower()


def test_report_says_the_deadline_is_the_measure_s() -> None:
    rows = lines_with("дедлайн")
    assert any("30" in row for row in rows), "the report does not name the measure's 30-second deadline"


def test_report_says_seconds_hold_both_attempts() -> None:
    assert "спроб" in report_text().lower()


def test_report_premise_statuses_as_named_in_goal() -> None:
    lines = report_text().splitlines()
    for premise, status in STATUSES.items():
        where = [i for i, line in enumerate(lines) if mentions(line, premise)]
        assert where, f"the report does not name {premise}"
        near = [" ".join(lines[i : i + 2]) for i in where]
        assert any(re.search(rf"(?<![\w-]){status}(?![\w-])", chunk) for chunk in near), (
            f"the report does not give {premise} the status `{status}`"
        )


def test_premise_log_statuses_as_named_in_goal() -> None:
    for premise, status in STATUSES.items():
        assert log_status(premise) == status, f"the premise log gives {premise} `{log_status(premise)}`"


def test_premise_log_disconnect_gets_partial_evidence() -> None:
    assert "test_stale_writing" in " | ".join(log_row("P-DISCONNECT"))


def test_report_says_what_is_left_for_the_owner() -> None:
    text = report_text()
    assert re.search(r"5\s*[–-]\s*10", text), "the report does not name the 5–10 phrases"
    assert "Gmail" in text or "вхід" in text.lower(), "the report does not name mama's sign-in"


def test_card_for_mama_phrases_and_sign_in_on_the_board() -> None:
    cards = [
        path
        for path in task_files()
        if "Gmail" in (body := path.read_text(encoding="utf-8")) and "фраз" in body
    ]
    assert cards, "no task file under tasks/ asks for mama's phrases and her Gmail sign-in"
