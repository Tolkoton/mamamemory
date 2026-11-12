"""Disputed contract test of the slice f3-measure: Hardest seam 1, freshness (question Q1 of the hand-in).

Reading taken: the deploy time is the modification time of Sonko's deploy report that names the revision
the report gives; the measure time is the modification time of Sonko's measure output; no file of `src/`
(compiled `__pycache__` excluded) was modified strictly between the two. Not sealed until the slice
planner answers.
"""

from tests.f3_measure_sources import MEASURE_OUTPUT, REVISION, ROOT, SONKO_DONE, report_text


def test_measure_ran_on_the_deployed_tree() -> None:
    assert REVISION in report_text(), "the report does not name the deployed revision"
    deploys = [
        path
        for path in SONKO_DONE.glob("*-mamamemory-*.md")
        if not path.name.endswith(".request.md")
        and path != MEASURE_OUTPUT
        and REVISION in path.read_text(encoding="utf-8")
    ]
    assert deploys, f"no Sonko report names the revision {REVISION}"
    deployed = min(path.stat().st_mtime for path in deploys)
    measured = MEASURE_OUTPUT.stat().st_mtime
    assert deployed <= measured, "the measure ran before the deploy"
    edited = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and deployed < path.stat().st_mtime < measured
    ]
    assert edited == [], f"src/ changed between the deploy and the measure: {edited}"
