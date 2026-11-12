"""Disputed contract test of the slice skeleton-measure: Hardest seam 2 (question Q2 of the hand-in).

Reading taken: «рядок журналу старту екземпляра» is a line of Sonko's output holding Cloud Run's own start
message `Starting new instance`; when Sonko's output has none, the report marks the cold number with the words
«холодність не підтверджено». Not sealed until the slice planner answers.
"""

from tests.f1_measure_sources import report_text, sonko_output


def test_cold_number_without_start_log_is_marked_unconfirmed() -> None:
    text = report_text()
    if "Starting new instance" not in sonko_output():
        assert "холодність не підтверджено" in text.lower()
