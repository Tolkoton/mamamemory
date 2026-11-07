"""Which files are the engine's own install, untouched — so that nobody's turn is judged by them.

`engine.py install` writes the engine into a project and never commits. Until the owner's first
commit every one of those files is untracked, and a check that reads "not in HEAD" as "written by
this turn" blames the session for the engine's own hooks, the seeded project.env and the guarded
files it never touched (board 786). `.claude/engine-lock.json` says what was installed: the git
blob id of every engine file (`files`) and of every seeded file as it was seeded (`seeds`).

    as_installed(root, files, ref=None, index=False) -> set[str]

names the files that are BOTH
  * absent from the base the caller compares with (`ref`, default HEAD; a repository with no
    commit has no base at all), and
  * byte-identical to what the lock recorded (the working file, or with `index` the staged one;
    a CRLF checkout matches its LF form, as engine.py reads it).

Both, never one. A file the base already has is the project's from then on: putting a tracked
project.env back to its seed is a change like any other, and the lock excuses nothing there —
with one exception, AN UPDATE NOT YET COMMITTED (board 120, item 1750): `engine.py update` in a
project whose engine is committed rewrites files the base has. Such a file is the engine's too
when the base's own lock recorded exactly the base's blob (the engine's file as it shipped,
untouched) AND the working lock records exactly the working content. The owner's committed edit
of an engine file fails the first, a turn's edit after the update the second.
The same update may REMOVE an engine file it no longer ships (proposal 1778):

    retired(root, gone, ref=None, index=False) -> set[str]

names those of the deleted files `gone` the base holds exactly as the base's lock recorded them and
the working lock (with `index`, the staged one) no longer names — the engine took them back, no turn
deleted them. A file the owner had edited, or one the new lock still lists, is judged as before.
A file that differs from the lock by one byte is somebody's edit — and then

    seed_text(root, rel, ref=None) -> str | None

gives what a seeded file started from, so that the edit is compared with its seed and not with
nothing: an owner who set SOURCE_DIRS in project.env before the first commit did not "change
CODE_EXTENSIONS". engine.py keeps the text beside the other machine state
(.claude/state/install/seeds/<path>); it is believed only while its blob id is the lock's. No lock, an unreadable lock,
a lock that does not name the file: nothing is taken on trust, and the caller judges as before.

The limit: the lock is a file of the project, under `.claude/`, which Claude Code protects from
an agent's write tools; a session that rewrites it on purpose through a script is the documented
boundary (docs/engine-limits.md, "The risk line"), not what this guards against.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

LOCK_REL = ".claude/engine-lock.json"
SEEDS_REL = ".claude/state/install/seeds"


def parsed(text: str) -> dict[str, str]:
    data = json.loads(text)
    return {str(k): str(v) for part in ("files", "seeds") for k, v in dict(data.get(part) or {}).items()}


def recorded(root: Path) -> dict[str, str]:
    """path -> blob id, for the engine's files and the seeded ones. Anything unreadable: nothing."""
    try:
        return parsed((root / LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def recorded_at(root: Path, ref: str) -> dict[str, str]:
    """What the lock of commit `ref` recorded. No such lock, or unreadable: nothing."""
    out = subprocess.run(["git", "show", f"{ref}:{LOCK_REL}"], cwd=root, capture_output=True, check=False)
    if out.returncode != 0:
        return {}
    try:
        return parsed(out.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError, AttributeError):
        return {}


def base_blobs(root: Path, ref: str, files: list[str]) -> dict[str, str]:
    """path -> blob id of `files` in commit `ref`."""
    out = subprocess.run(["git", "ls-tree", "-r", "-z", ref, "--", *files], cwd=root, capture_output=True, check=False)
    blobs: dict[str, str] = {}
    for entry in out.stdout.split(b"\0") if out.returncode == 0 else []:
        meta, _, name = entry.partition(b"\t")
        parts = meta.split()
        if name and len(parts) == 3 and parts[1] == b"blob":
            blobs[name.decode("utf-8", "replace")] = parts[2].decode()
    return blobs


def blob_ids(data: bytes, width: int) -> set[str]:
    """The git blob id of `data` and of its LF form, in the hash the lock was written with."""
    new = hashlib.sha256 if width == 64 else hashlib.sha1
    forms = {data, data.replace(b"\r\n", b"\n")}
    return {new(b"blob %d\0" % len(form) + form).hexdigest() for form in forms}


def in_base(root: Path, ref: str, files: list[str]) -> set[str]:
    out = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", ref, "--", *files],
                         cwd=root, capture_output=True, check=False)
    if out.returncode != 0:
        return set()   # no such commit: a repository before its first one has no base
    return {name.decode("utf-8", "replace") for name in out.stdout.split(b"\0") if name}


def content(root: Path, rel: str, index: bool) -> bytes | None:
    if index:
        out = subprocess.run(["git", "cat-file", "blob", f":{rel}"], cwd=root, capture_output=True, check=False)
        return out.stdout if out.returncode == 0 else None
    path = root / rel
    try:
        return None if path.is_symlink() else path.read_bytes()
    except OSError:
        return None


def as_installed(root: Path, files: list[str], ref: str | None = None, index: bool = False) -> set[str]:
    lock = recorded(root)
    named = [rel for rel in files if rel in lock]
    if not named:
        return set()
    based = in_base(root, ref or "HEAD", named)
    updated = pristine_in_base(root, ref or "HEAD", sorted(based))
    same: set[str] = set()
    for rel in named:
        if rel in based and rel not in updated:
            continue
        data = content(root, rel, index)
        if data is not None and lock[rel] in blob_ids(data, len(lock[rel])):
            same.add(rel)
    return same


def pristine_in_base(root: Path, ref: str, files: list[str]) -> set[str]:
    """Of `files` (all in the base), those the base holds exactly as the base's own lock recorded them."""
    if not files:
        return set()
    then = recorded_at(root, ref)
    blobs = base_blobs(root, ref, [rel for rel in files if rel in then])
    return {rel for rel, blob in blobs.items() if then.get(rel) == blob}


def retired(root: Path, gone: list[str], ref: str | None = None, index: bool = False) -> set[str]:
    """Of the deleted files `gone`, those the engine's update retired: pristine in the base, not in the new lock."""
    if not gone:
        return set()
    now = recorded_at(root, "") if index else recorded(root)
    if not now:   # no lock, an unreadable lock: nothing is taken on trust
        return set()
    return {rel for rel in pristine_in_base(root, ref or "HEAD", gone) if rel not in now}


def seed_text(root: Path, rel: str, ref: str | None = None) -> str | None:
    want = recorded(root).get(rel)
    if want is None or in_base(root, ref or "HEAD", [rel]):
        return None
    data = content(root, f"{SEEDS_REL}/{rel}", index=False)
    if data is None or want not in blob_ids(data, len(want)):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
