"""Readers for the report tests of the slice skeleton-measure: the report, the premise log, Sonko's output.

Written by the slice tester from the sealed contract `.engine/slices/skeleton-measure.md`. Nothing here
computes what the report must say: it only reads the files the contract names as the sources of truth.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "f1-measure.md"
PREMISE_LOG = ROOT / ".engine" / "premises" / "premise-log.md"
TASKS = ROOT / "tasks"
SONKO_OUTPUT = Path.home() / "sonko" / "done" / "2026-11-11-mamamemory-f1-measure.md"
REVISION = "mamamemory-00025-kgg"
# The statuses the Goal names in advance, not by the result.
STATUSES = {
    "P-COLD": "accepted-as-risk",
    "P-STT-UK": "accepted-as-risk",
    "P-AUTH": "accepted-as-risk",
    "P-DISCONNECT": "unverified",
    "P-PARSE": "verified",
}


def report_text() -> str:
    assert REPORT.is_file(), f"{REPORT} does not exist"
    return REPORT.read_text(encoding="utf-8")


def sonko_output() -> str:
    assert SONKO_OUTPUT.is_file(), f"{SONKO_OUTPUT} does not exist"
    return SONKO_OUTPUT.read_text(encoding="utf-8")


def mentions(line: str, premise: str) -> bool:
    """The line names this premise and not only a longer id that starts with it (P-DISCONNECT-PHOTO)."""
    return re.search(re.escape(premise) + r"(?![\w-])", line) is not None


def log_row(premise: str) -> list[str]:
    for line in PREMISE_LOG.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 4 and cells[1] == premise:
            return cells
    raise AssertionError(f"{premise} has no row in {PREMISE_LOG}")


def log_status(premise: str) -> str:
    """The first backticked word of the status cell of the premise's row in the premise log."""
    token = re.search(r"`([^`]+)`", log_row(premise)[4])
    assert token, f"the premise log row of {premise} has no backticked status"
    return token.group(1)


def task_files() -> list[Path]:
    return sorted(path for path in TASKS.rglob("*.md") if path.is_file())
