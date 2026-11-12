"""Contract tests of the slice f3-measure: the report `docs/f3-measure.md` and the proposal of its failures.

Written by the slice tester from the sealed contract `.engine/slices/f3-measure.md` («Seam (contract)»,
«Premise verified», «Exit criterion»). The report is checked against the files the contract names as its
sources: Sonko's verbatim output of `scripts/measure_f3.py` and the rows of the premise log.
"""

import re

from tests.f3_measure_sources import (
    PREMISES,
    REVISION,
    failed_phrases,
    log_status,
    measured_n,
    mentions,
    report_text,
    task_files,
)

F3_SLICES = ["note-to-case", "photo-and-file", "case-questions", "move-material"]
COUNT = re.compile(r"\d+\s*(?:/|з|of)\s*\d+")


def test_report_names_the_deployed_revision() -> None:
    assert REVISION in report_text()


def test_report_gives_the_smoke_of_each_slice_with_numbers() -> None:
    lines = report_text().splitlines()
    for slug in F3_SLICES:
        names = (slug, slug.replace("-", "_"))
        rows = [line for line in lines if any(name in line for name in names)]
        assert rows, f"the report does not name the slice {slug}"
        assert any(COUNT.search(row) for row in rows), f"the smoke of {slug} carries no number"


def test_report_gives_n_of_10_as_sonko_printed_it() -> None:
    n = measured_n()
    text = report_text()
    assert re.search(rf"(?<!\d){n}\s*(?:з|of)\s*10(?!\d)", text), f"the report does not say {n} з 10"
    for other in range(11):
        if other != n:
            assert not re.search(rf"MEASURED: {other} of 10", text)


def test_report_quotes_every_failure_verbatim() -> None:
    text = report_text()
    for phrase in failed_phrases():
        assert phrase in text, f"the failure «{phrase}» is not in the report word for word"


def test_report_premise_status_matches_the_premise_log() -> None:
    lines = report_text().splitlines()
    for premise in PREMISES:
        status = log_status(premise)
        where = [i for i, line in enumerate(lines) if mentions(line, premise)]
        assert where, f"the report does not name {premise}"
        near = [" ".join(lines[i : i + 2]) for i in where]
        assert any(
            f"`{status}`" in chunk or re.search(rf"(?<![\w-]){status}(?![\w-])", chunk) for chunk in near
        ), f"the report does not give {premise} the status `{status}` of its premise log row"


def test_report_says_what_is_left_for_the_owner() -> None:
    text = report_text().lower()
    assert "власник" in text
    assert "телефон" in text


def test_report_says_the_avans_phrase_only_checks_the_choice() -> None:
    text = report_text()
    assert "записку про аванс" in text
    assert "вже в" in text.lower()


def test_report_says_the_pramipexole_latin_letters_are_input_noise() -> None:
    text = report_text().lower()
    assert "прамipексол" in text or "прамipексол".replace("i", "і").replace("p", "р") in text
    assert "латин" in text


def test_measure_failures_go_to_a_proposal_on_the_board() -> None:
    phrases = failed_phrases()
    assert phrases, "Sonko's output names no failure"
    naming = [
        path
        for path in task_files()
        if "f3-measure" in (body := path.read_text(encoding="utf-8")) or any(p in body for p in phrases)
    ]
    assert naming, "no task file under tasks/ names the failures of the measure"
