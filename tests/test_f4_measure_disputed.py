"""Disputed contract tests of the slice f4-measure (questions Q1–Q3 of the tester's hand-in).

Written by the slice tester from the sealed contract `.engine/slices/f4-measure.md`, without the code. Each
test fixes one reading of a line that can be read two ways; this file is not sealed until the slice planner
answers.
"""

from tests.f4_measure_sources import premise_row, report_text, section


def test_Q1_the_report_names_the_file_times_against_sonkos_report() -> None:
    """Q1, the planner's reading: the report names it (the time of the files against Sonko's report); the
    check on disk is made when the report is written, not by this test."""
    text = report_text()
    assert "src/" in text, "the report does not say that no file of src/ changed after the deploy"
    assert "assistant.py" in text, "the report does not name assistant.py"
    assert "12:34:20" in text, "the report does not give the time of assistant.py (12:34:20 UTC)"
    assert "12:59:18" in text, "the report does not give the time of Sonko's report (12:59:18 UTC)"


def test_Q2_premise_conditions_name_the_smoke_phrases_and_no_new_phrases() -> None:
    route = " ".join(premise_row("P-ROUTE-F4")[4:6])
    assert "з умовою" in route, "P-ROUTE-F4 is not `verified` з умовою"
    assert "лікар о десятій у середу" in route, "the condition of P-ROUTE-F4 does not name the regression"
    assert "на нових фразах не міряно" in route
    recall = " ".join(premise_row("P-RECALL")[4:6])
    assert "з умовою" in recall, "P-RECALL is not `verified` з умовою"
    assert "синтетичн" in recall
    assert "3 справ" in recall, "the condition of P-RECALL does not name the catalogue of 3 cases"
    assert "на нових фразах не міряно" in recall
    assert "на нових фразах не міряно" in report_text(), "the report does not say the same condition"


def test_Q3_the_report_says_s1_to_s3_was_checked_in_parts() -> None:
    body = section(report_text(), "Критерії F4")
    assert "частинами" in body, "the section does not say the composition S1 → S3 was checked in parts"
    assert "наскрізн" in body, "the section does not say it was not checked end to end"
    assert "worklog.add" in body, "the section does not say the entries were seeded by worklog.add"
