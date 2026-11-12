"""Readers for the contract tests of the slice f3-measure: the report, the premise log, Sonko's output.

Written by the slice tester from the sealed contract `.engine/slices/f3-measure.md`. Nothing here computes
what the report must say: it only reads the three files the contract names as the sources of truth.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "f3-measure.md"
PREMISE_LOG = ROOT / ".engine" / "premises" / "premise-log.md"
TASKS = ROOT / "tasks"
SONKO_DONE = Path.home() / "sonko" / "done"
MEASURE_OUTPUT = SONKO_DONE / "2026-11-07-mamamemory-f3-measure.md"
REVISION = "mamamemory-00018-9s6"
PREMISES = ["P-CASES", "P-GCS", "P-DESC", "P-ROUTE-CASES", "P-PARSE", "P-DISCONNECT-PHOTO", "P-DISCONNECT"]


def report_text() -> str:
    assert REPORT.is_file(), f"{REPORT} does not exist"
    return REPORT.read_text(encoding="utf-8")


def measure_output() -> str:
    assert MEASURE_OUTPUT.is_file(), f"{MEASURE_OUTPUT} does not exist"
    return MEASURE_OUTPUT.read_text(encoding="utf-8")


def measured_n() -> int:
    found = re.findall(r"MEASURED: (\d+) of 10", measure_output())
    assert found, "Sonko's output has no `MEASURED: N of 10` line"
    return int(found[-1])


def failed_phrases() -> list[str]:
    """Every phrase of Sonko's verbatim output whose verdict line is FAIL."""
    phrases: list[str] = []
    current: str | None = None
    for line in measure_output().splitlines():
        stripped = line.strip()
        if stripped.startswith("«") and stripped.endswith("»"):
            current = stripped[1:-1]
        elif stripped.startswith("FAIL") and current is not None:
            phrases.append(current)
    return phrases


def mentions(line: str, premise: str) -> bool:
    """The line names this premise and not only a longer id that starts with it (P-CASES vs P-CASES-48)."""
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


def task_files() -> list[Path]:
    return sorted(path for path in TASKS.rglob("*.md") if path.is_file())
