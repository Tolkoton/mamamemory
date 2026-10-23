"""test_touch.py — does a test touch this code? One answer, shared by the delete guard and testing.py.

Not a command: delete_guard.py (board 072) asks it before a deletion, testing.py (board 062) for
the mandatory case O8 — a slice changes code no test touches. Two ways to answer:

EXACTLY, when the project set COVERAGE_CMD: the command runs in a throwaway checkout of a commit,
with files laid over it when asked, and must leave `coverage.json` there (the format of
coverage.py's `coverage json`). `run_coverage` returns the executed and the missing lines per file.

COARSELY, without it: `TestIndex` — the module has its test file (`test_<module>`,
`<module>_test`, `<module>.test`, `<module>.spec`), or a test file mentions the name.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

COVERAGE_KEY = "COVERAGE_CMD"
COVERAGE_FILE = "coverage.json"
COVERAGE_TIMEOUT_S = 900
CACHE_REL = Path(".claude/state/delete-guard/coverage")
TEST_DIRS = {"tests", "test", "testing", "__tests__", "spec", "specs"}
TEST_STEM_RE = re.compile(r"^(?:test_(?P<a>.+)|(?P<b>.+)_test|(?P<c>.+)\.test|(?P<d>.+)\.spec)$")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True,
                          text=True, errors="replace", check=False)


def is_test_path(rel: str) -> bool:
    path = Path(rel)
    return any(p in TEST_DIRS for p in path.parts[:-1]) or path.stem == "conftest" or bool(TEST_STEM_RE.match(path.stem))


def read_old(root: Path, ref: str, rel: str) -> str | None:
    out = git(root, "show", f"{ref}:{rel}")
    return out.stdout if out.returncode == 0 else None


class TestIndex:
    """The test files of the base and of the change together: a test deleted with its code still
    says the code was tested, and a test written for the deletion counts before it is committed."""

    def __init__(self, root: Path, ref: str, changes: dict[str, Any]) -> None:
        self.root, self.ref, self.changes = root, ref, changes
        now = git(root, "ls-files", "-co", "--exclude-standard").stdout.splitlines()
        before = git(root, "ls-tree", "-r", "--name-only", ref).stdout.splitlines()
        self.files = sorted({rel for rel in [*now, *before] if is_test_path(rel)})
        self._text: str | None = None

    def text(self) -> str:
        if self._text is None:
            parts = []
            for rel in self.files:
                if rel in self.changes and not self.changes[rel].created:
                    parts.append(read_old(self.root, self.ref, rel) or "")
                try:
                    parts.append((self.root / rel).read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
            self._text = "\n".join(parts)
        return self._text

    def module_test(self, rel: str) -> str | None:
        stem = Path(rel).stem
        for test in self.files:
            match = TEST_STEM_RE.match(Path(test).stem)
            if match and stem in match.groups():
                return test
        return None

    def mentions(self, name: str) -> bool:
        return re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", self.text()) is not None


def coarse_reason(tests: TestIndex, rel: str, name: str | None = None) -> str:
    """Why `rel` (or the name inside it) counts as tested without coverage, or ''."""
    mapped = tests.module_test(rel)
    if mapped:
        return f"the module has its test file {mapped}"
    name = name or Path(rel).stem
    return f"a test file mentions {name}" if tests.mentions(name) else ""


def read_report(checkout: Path) -> dict[str, dict[str, list[int]]] | None:
    try:
        report = json.loads((checkout / COVERAGE_FILE).read_text(encoding="utf-8"))["files"]
        data = {}
        for name, entry in report.items():
            path = Path(name)
            inside = path.is_absolute() and path.is_relative_to(checkout)
            data[(path.relative_to(checkout) if inside else path).as_posix()] = {
                "executed": sorted(int(n) for n in entry.get("executed_lines", [])),
                "missing": sorted(int(n) for n in entry.get("missing_lines", []))}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return data


def measure(root: Path, sha: str, command: str, files: dict[str, str]) -> dict[str, dict[str, list[int]]] | None:
    """Check out `sha` into a temporary directory, lay `files` over it, run the command, read its report."""
    tmp = Path(tempfile.mkdtemp(prefix="delete-guard-"))
    try:
        archive = subprocess.run(["git", "archive", "--format=tar", sha], cwd=root, capture_output=True, check=False)
        if archive.returncode != 0 or subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive.stdout,
                                                     check=False).returncode != 0:
            return None
        for rel, text in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(text, encoding="utf-8")
        subprocess.run(["bash", "-c", command], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=COVERAGE_TIMEOUT_S, check=False)
        return read_report(tmp)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_coverage(root: Path, ref: str, command: str, files: dict[str, str]) -> dict[str, dict[str, set[int]]] | None:
    """Run COVERAGE_CMD on the code of `ref` with `files` laid over it. {file: {executed, missing}}
    or None when no readable coverage.json came out. Cached per (commit, tests, command)."""
    sha = git(root, "rev-parse", "--verify", "-q", ref).stdout.strip()
    if not sha:
        return None
    key = hashlib.sha256(json.dumps([sha, command, sorted(files.items())]).encode()).hexdigest()[:24]
    cache = root / CACHE_REL / f"{key}.json"
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = measure(root, sha, command, files)
        if data is None:
            return None
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
    return {rel: {"executed": set(e["executed"]), "missing": set(e["missing"])} for rel, e in data.items()}
