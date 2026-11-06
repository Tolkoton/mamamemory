"""Contract tests of the slice access-shell: import boundaries (Seam 4).

Written by the slice tester from the sealed contract `.engine/slices/access-shell.md`.
"""

import ast
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "mamamemory"
FRAMEWORKS = ("fastapi", "starlette")

# Outside `mamamemory/http`, with fastapi and starlette unimportable, the modules still import and the
# session check still works: the framework lives only in `http`.
WITHOUT_FRAMEWORK = """
import sys
from datetime import datetime, UTC
for name in ("fastapi", "starlette"):
    sys.modules[name] = None
import mamamemory.access as access
import mamamemory.config, mamamemory.errors
import mamamemory.integrations.store, mamamemory.integrations.google_auth
now = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)
value = access.session_cookie_value("1", "mama@example.com", now, key="k")
allowed = frozenset({"mama@example.com"})
claims = access.verify_session_cookie(value, now, key="k", allowed_emails=allowed, max_age_s=60)
assert claims.sub == "1", claims
for mod in list(sys.modules):
    assert not mod.startswith(("fastapi.", "starlette.")), mod
"""


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_fastapi_and_starlette_only_in_mamamemory_http() -> None:
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in sorted(PACKAGE.rglob("*.py"))
        if "http" not in path.relative_to(PACKAGE).parts[:1] and _imported(path) & set(FRAMEWORKS)
    ]
    assert offenders == [], f"fastapi/starlette imported outside mamamemory/http: {offenders}"

    src = PACKAGE.parent
    done = subprocess.run(
        [sys.executable, "-c", WITHOUT_FRAMEWORK],
        cwd=src,
        env={"PYTHONPATH": str(src)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
