"""Readers for the contract tests of the slice f4-measure: the report, the premise log, PROGRESS, the board.

Written by the slice tester from the sealed contract `.engine/slices/f4-measure.md`. Nothing here computes
what the report must say: it only reads the files the contract names as the sources of truth.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "f4-measure.md"
PREMISE_LOG = ROOT / ".engine" / "premises" / "premise-log.md"
PROGRESS = ROOT / ".engine" / "PROGRESS.md"
TASKS = ROOT / "tasks"
SONKO_DONE = Path.home() / "sonko" / "done"
S3_DEPLOY = SONKO_DONE / "2026-11-12-mamamemory-case-recall-deploy-2.md"
REVISION = "mamamemory-00030-q2l"
PREMISES = ["P-ROUTE-F4", "P-RECALL", "P-CTX"]


def report_text() -> str:
    assert REPORT.is_file(), f"{REPORT} does not exist"
    return REPORT.read_text(encoding="utf-8")


def count(n: int) -> re.Pattern[str]:
    """«n з n» in any of the usual spellings: 8/8, 8 з 8, 8 із 8, 8 of 8."""
    return re.compile(rf"(?<!\d){n}\s*(?:/|з|із|of)\s*{n}(?!\d)")


def mentions(line: str, premise: str) -> bool:
    """The line names this premise and not only a longer id that starts with it."""
    return re.search(re.escape(premise) + r"(?![\w-])", line) is not None


def premise_row(premise: str) -> list[str]:
    """The cells of the premise's row: [_, id, statement, level, status, evidence, checked, …]."""
    for line in PREMISE_LOG.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 5 and cells[1] == premise:
            return cells
    raise AssertionError(f"{premise} has no row in {PREMISE_LOG}")


def log_status(premise: str) -> str:
    """The first backticked word of the status cell of the premise's row in the premise log."""
    token = re.search(r"`([^`]+)`", premise_row(premise)[4])
    assert token, f"the premise log row of {premise} has no backticked status"
    return token.group(1)


def section(text: str, title_part: str) -> str:
    """The lines of the first markdown section whose heading holds `title_part`, up to the next heading of
    the same or a higher level."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        heading = re.match(r"(#+)\s", line)
        if heading and title_part in line:
            level = len(heading.group(1))
            body: list[str] = []
            for rest in lines[i + 1 :]:
                deeper = re.match(r"(#+)\s", rest)
                if deeper and len(deeper.group(1)) <= level:
                    break
                body.append(rest)
            return "\n".join(body)
    raise AssertionError(f"the report has no section whose heading holds «{title_part}»")


def task_files() -> list[Path]:
    return sorted(path for path in TASKS.rglob("*.md") if path.is_file())
