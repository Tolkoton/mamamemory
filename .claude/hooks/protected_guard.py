#!/usr/bin/env python3
"""The guard of the guarded files after the fact (board 724, the design of board 717).

    python3 .claude/hooks/protected_guard.py session-start        # env-check.sh: the SessionStart envelope on stdin
    python3 .claude/hooks/protected_guard.py before               # board-runner.sh, before an agent's session: prints its snapshot
    python3 .claude/hooks/protected_guard.py after  < snapshot    # …and after it: exit 3 = put back, 4 = could NOT be put back
    python3 .claude/hooks/protected_guard.py pending < snapshot   # guarded files a commit of the session changed
    python3 .claude/hooks/protected_guard.py accept [<event>]     # the OWNER's command, in their own terminal

WHY. protect-paths.sh and block-dangerous.sh refuse a write to a guarded file by the text of the
tool call; a path kept in a variable, or a script the command starts, is not seen (board 714). So
the same files are looked at again when the write can no longer hide: at the end of the turn
(gate.py, layer stop), in the commit script (commit_checkpoint.sh) and by the board runner around
every session. The files are the GUARDED_PATTERNS of protected-path-list.sh — the constitution,
the settings, `.engine/rules.md`, migrations, CI workflows — among what git tracks or does not
ignore, plus the four named below wherever they exist. Secrets are not here: they are not in git
and reading leaves no trace. Nor is `tasks/.reviewed`: the runner keeps it by a check of its own
(board 100), with another answer to a change — the number removed, the task not parked.

THE SNAPSHOT, NOT HEAD. A snapshot holds, for every guarded file, its sha256 AND its content, so
a file can be put back whatever HEAD became. A session's snapshot is the file
`.claude/state/gate/protected/<session>.json`: taken when the session starts, resumes or is
cleared (never after a compaction: that would accept what the agent did before it) and after
every turn the gate passed. HEAD would be wrong twice: it does not see a change the agent
committed in the same turn, and it calls the owner's uncommitted edit, made before the turn, a
change of the turn.

WHAT THE GATE DOES (the owner's answer, board 717 question 3). On a difference it puts the file
back itself, at once — changed: the content of the snapshot; deleted: restored; new: removed —
keeps the discarded change as a patch (`discarded/<event>.patch`; the event's `.json` carries the
discarded content), writes the anomaly journal and blocks the turn once so that the agent reads
what was discarded. The agent has no command to run. Without a snapshot of the session (it began
before this guard, or SessionStart did not run), and when the gate is run by hand, the comparison
is with HEAD and nothing is put back: the gate cannot tell the agent's change from the owner's.
A guarded file of an install nobody has committed yet — not in HEAD, and byte for byte what
engine-lock.json recorded — is nobody's change and is not reported (installed.py, board 786).

WHAT IS PROMISED (the owner's answer, board 724): a mistaken or naive change of a guarded file
— made directly, with a tool, through a shell variable, by a commit — is caught, put back, kept
as a patch and journalled. A session that goes for the check itself (the snapshots and records
under `.claude/state/`, this file, board-runner.sh, the runner's process) is not held: it runs
as the same Linux user as the runner (docs/engine-limits.md, "The same Linux user").

THE RUNNER'S COMMANDS. `before` writes nothing: it PRINTS the snapshot, content included;
board-runner.sh hands it to `after` and `pending` on stdin (and keeps a copy for a runner that
dies while the session runs). `after` compares and puts back from what it was handed. The record
of what was discarded is written after the files are back, and a state directory that cannot be
written sends the record to a temporary directory instead of stopping the restore. Anything
`after` cannot do — a file it cannot put back, an error of its own — is exit 4 or another
non-zero code, never a pass, and the runner stops the board on every code but 0 and 3.

THE OWNER'S OWN EDIT made while a turn runs is not told from the agent's: it is discarded the same
way and never lost. `accept` in the owner's terminal takes the files as they are now as the new
snapshot of every session; `accept <event>` first puts the discarded change of that event back.
Refused inside a Claude Code session (CLAUDECODE), as every owner's command is.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_REL = Path(".claude/state/gate/protected")
LIST = Path(__file__).resolve().parent / "protected-path-list.sh"
# Looked at by name wherever they exist: git usually ignores settings.local.json, and a project
# that is not a repository still has the other three.
NAMED = (".claude/constitution.md", ".claude/settings.json", ".claude/settings.local.json", ".engine/rules.md")
# On the list, and kept by a check of its own on the runner's side (board 100: a number written on this
# machine is removed before the push, the owner's arrives by a pull or the inbox while a task is open).
ELSEWHERE = ("tasks/.reviewed",)
KEEP_DAYS = 14               # a session's snapshot older than this is removed at a session start
STARTS = ("startup", "resume", "clear")
EXIT_RESTORED = 3
EXIT_NOT_RESTORED = 4     # a guarded file differs and its content before the session could not be had
Change = tuple[str, str | None, str | None]   # the file, its hash in the snapshot, its hash now


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def patterns() -> list[re.Pattern[str]]:
    """GUARDED_PATTERNS of the one list every hook reads. No list is an error, never "nothing is guarded"."""
    done = subprocess.run(["bash", "-c", '. "$1" && printf "%s\\n" "${GUARDED_PATTERNS[@]}"', "_", str(LIST)],
                          capture_output=True, text=True, check=False)
    found = [line for line in done.stdout.splitlines() if line]
    if done.returncode != 0 or not found:
        raise RuntimeError(f"the list of guarded paths cannot be read: {LIST}")
    return [re.compile(line) for line in found]


def is_guarded(rel: str, known: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(rel) for pattern in known)


def guarded(root: Path) -> list[str]:
    """The guarded files of the project: tracked, or new and not ignored, or one of NAMED."""
    known = patterns()
    listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.split("\0")
    names = {rel for rel in listed if rel} | {rel for rel in NAMED if os.path.lexists(root / rel)}
    return sorted(rel for rel in names if is_guarded(rel, known) and rel not in ELSEWHERE)


def scan(root: Path) -> dict[str, bytes | None]:
    """The content of every guarded file that is there. None: something unreadable stands in its place."""
    found: dict[str, bytes | None] = {}
    for rel in guarded(root):
        try:
            found[rel] = (root / rel).read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            found[rel] = None
    return found


def sha(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest() if data is not None else "unreadable"   # differs from any snapshot


def hashes(files: dict[str, bytes | None]) -> dict[str, str]:
    return {rel: sha(data) for rel, data in files.items()}


def encoded(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode("ascii") if data is not None else None


def snap(root: Path) -> dict[str, Any]:
    """The guarded files as they are now: hashes, content, modes. Writes nothing."""
    files = scan(root)
    return {"schema": 2, "taken_utc": utc_now(), "head": git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip(),
            "files": hashes(files), "content": {rel: encoded(data) for rel, data in files.items()},
            "modes": {rel: (root / rel).stat().st_mode & 0o777 for rel, data in files.items() if data is not None}}


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:80] or "unnamed"


def snapshot_path(root: Path, name: str) -> Path:
    return root / STATE_REL / f"{safe(name)}.json"


def take(root: Path, name: str) -> dict[str, Any]:
    """The snapshot `name` of a session, written to the state directory."""
    data = snap(root)
    path = snapshot_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def parsed(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    whole = isinstance(data, dict) and all(isinstance(data.get(key), dict) for key in ("files", "content"))
    return data if whole else None


def load(root: Path, name: str) -> dict[str, Any] | None:
    try:
        return parsed(snapshot_path(root, name).read_text(encoding="utf-8"))
    except OSError:
        return None


def changes(before: dict[str, str], now: dict[str, str]) -> list[Change]:
    return [(rel, before.get(rel), now.get(rel)) for rel in sorted(set(before) | set(now)) if before.get(rel) != now.get(rel)]


def kept(base: dict[str, Any], rel: str, want: str) -> bytes:
    """The content the snapshot holds for this file — only when it really has the hash asked for."""
    try:
        data = base64.b64decode(base["content"][rel], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise OSError("the snapshot does not hold its content") from exc
    if sha(data) != want:
        raise OSError("the content the snapshot holds does not have the hash the snapshot names")
    return data


def put(root: Path, rel: str, data: bytes | None, mode: int = 0o644) -> None:
    """The file with this content, or gone."""
    path = root / rel
    if path.is_symlink() or path.is_file():
        path.unlink()   # never written through: a link put in the file's place would lead the write elsewhere
    if data is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def lines_of(data: bytes | None) -> list[str] | None:
    """A content as lines for a diff; None when it is not text."""
    try:
        return (data or b"").decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def patch_of(rel: str, was: bytes | None, now: bytes | None) -> str:
    """The discarded change of one file as a unified diff: from the snapshot to what was discarded."""
    old, new = lines_of(was), lines_of(now)
    if old is None or new is None:
        return f"Binary files a/{rel} and b/{rel} differ (the discarded content is in the event's .json)\n"
    lines = difflib.unified_diff(old, new, f"a/{rel}" if was is not None else "/dev/null", f"b/{rel}" if now is not None else "/dev/null")
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)


def journal(root: Path, source: str, what: str, done: str) -> None:
    """One entry of the anomaly journal. Best effort: a project without a board has none."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
        import board

        board.note(root, source, what, done)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"protected_guard: the anomaly journal was not written: {exc}", file=sys.stderr)


def record(root: Path, event: dict[str, Any], patch: str) -> str:
    """The discarded change on disk: `<event>.patch` and `<event>.json` under the state directory, or —
    when that cannot be written — in a new temporary directory. The path of the patch, for people."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for folder in (root / STATE_REL / "discarded", None):
        try:
            where = folder or Path(tempfile.mkdtemp(prefix="protected-discarded-"))
            where.mkdir(parents=True, exist_ok=True)
            ident = next(name for n in range(1, 1000) for name in [f"{stamp}-{n}"] if not (where / f"{name}.json").exists())
            (where / f"{ident}.patch").write_text(patch, encoding="utf-8")
            event["id"] = ident if folder else str(where / f"{ident}.json")
            event["patch"] = (where / f"{ident}.patch").relative_to(root).as_posix() if folder else str(where / f"{ident}.patch")
            (where / f"{ident}.json").write_text(json.dumps(event, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return str(event["patch"])
        except OSError as exc:
            print(f"protected_guard: the discarded change could not be written under {folder or 'a temporary directory'}: {exc}", file=sys.stderr)
    event["id"], event["patch"] = "", "(not saved: neither the state directory nor a temporary one could be written)"
    return str(event["patch"])


def discard(root: Path, base: dict[str, Any], now: dict[str, bytes | None], found: list[Change], source: str) -> dict[str, Any]:
    """Put every changed file back as the snapshot `base` has it — first, and from `base` alone;
    then keep the discarded change as a patch and an event `accept <event>` can read, and write the journal."""
    failed, patch, rows = [], "", []
    for rel, was, _ in found:
        old: bytes | None = None
        try:
            old = kept(base, rel, was) if was is not None else None
            put(root, rel, old, int(base.get("modes", {}).get(rel, 0o644)))
        except (OSError, ValueError, TypeError) as exc:
            failed.append(f"{rel}: {exc}")
        patch += patch_of(rel, old, now.get(rel))
        rows.append({"file": rel, "was": was, "discarded": sha(now[rel]) if rel in now else None, "content": encoded(now.get(rel))})
    event: dict[str, Any] = {"utc": utc_now(), "by": source, "failed": failed, "files": rows}
    record(root, event, patch)
    names = ", ".join(f"`{rel}`" for rel, _, _ in found)
    journal(root, source, f"охоронювані файли змінилися там, де їх не має змінювати ніхто, крім власника і runner-а: {names}",
            f"файли повернуто до стану зі знімка; відкинуту зміну збережено латкою `{event['patch']}`"
            + (f"; НЕ вдалося повернути: {'; '.join(failed)}" if failed else "")
            + f". Якщо зміна була ваша — `python3 .claude/hooks/protected_guard.py accept {event['id']}` у вашому терміналі повертає її.")
    return event


def committed(root: Path, head: str, rel: str) -> bool:
    """A commit made since `head` changed this file: HEAD carries the change the working tree no longer has."""
    return bool(head) and bool(git(root, "diff", "--no-renames", "--name-only", head, "HEAD", "--", rel).stdout.strip())


def finding(rel: str, rule: str, message: str, hint: str) -> dict[str, Any]:
    return {"file": rel, "line": None, "rule": rule, "severity": "block", "message": message, "hint": hint}


def against_head(root: Path) -> list[dict[str, Any]]:
    """No snapshot to compare with: the guarded files that differ from HEAD. Nothing is put back."""
    known = patterns()
    # --no-renames, here and in `pending`: a rename lists the new name only, and the old one is the guarded file.
    names = (git(root, "diff", "--no-renames", "--name-only", "-z", "HEAD", "--").stdout.split("\0")
             + git(root, "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0"))
    names = [rel for rel in names if rel and rel not in ELSEWHERE and is_guarded(rel, known)]
    # An install nobody has committed yet is nobody's change (installed.py, board 786).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import installed

    untouched = installed.as_installed(root, names)
    names = [rel for rel in names if rel not in untouched]
    return [finding(rel, "protected/changed",
                    "a guarded file differs from HEAD, and there is no snapshot of the guarded files to compare with (the session "
                    "began before this guard, its SessionStart hook did not run, or the gate was run by hand), so the gate cannot "
                    "tell a change of this turn from the owner's uncommitted edit and put nothing back",
                    f"if this turn changed it, put it back (`git checkout -- {rel}` only when the change is yours) and propose the "
                    "change instead; if it did not, leave the file and tell the owner: `python3 .claude/hooks/protected_guard.py "
                    "accept` in the owner's terminal takes the files as they are")
            for rel in sorted(set(names))]


def at_stop(root: Path, session: str | None) -> list[dict[str, Any]]:
    """The gate's question at the end of a turn: findings in the gate's own shape, every one a block.
    `session` is the hook's session id; None (the gate run by hand) never puts a file back."""
    base = load(root, session) if session else None
    if base is None:
        return against_head(root)
    now = scan(root)
    found = changes(base["files"], hashes(now))
    if not found:
        return []
    event = discard(root, base, now, found, "gates (protected_guard.py)")
    kinds = {(True, True): "changed", (True, False): "deleted", (False, True): "created"}
    out = []
    for rel, was, became in found:
        message = (f"this turn {kinds[(was is not None, became is not None)]} a guarded file; the gate put it back as it was when the "
                   f"turn began and kept the discarded change as a patch: {event['patch']}")
        if committed(root, str(base.get("head", "")), rel):
            message += (". A commit of this turn carries the change too: the file now differs from HEAD — leave that difference "
                        "uncommitted, the board runner or the owner commits it")
        if any(line.startswith(f"{rel}:") for line in event["failed"]):
            message += ". IT COULD NOT BE PUT BACK — tell the owner"
        out.append(finding(rel, "protected/reverted", message,
                           "do not write it again; nothing is left for you to run. Propose the change instead "
                           "(docs/tasks/settings.json for the settings, .engine/overseer/audit.md for the rest). If the change was "
                           f"the owner's own, tell the owner: `python3 .claude/hooks/protected_guard.py accept {event['id']}` in "
                           "their terminal puts it back"))
    return out


def prune(root: Path) -> None:
    """Sessions end without a word; their snapshots are removed by age."""
    limit = time.time() - KEEP_DAYS * 86400
    for path in (root / STATE_REL).glob("*.json"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
        except OSError:
            pass


def cmd_session_start(root: Path) -> int:
    """Silent, never fails: SessionStart output is added to the context of every session."""
    try:
        # An envelope that is there is read; a stdin nobody writes to (the hook run by hand, a suite) is not waited for.
        waiting = sys.stdin is not None and not sys.stdin.isatty() and select.select([sys.stdin], [], [], 1)[0]
        envelope = json.loads(sys.stdin.read() or "{}") if waiting else {}
        session = str(envelope.get("session_id") or "") if isinstance(envelope, dict) else ""
        # A compaction is the middle of a session; a start nobody named is taken once.
        source = str(envelope.get("source") or "") if session else "compact"
        if source in STARTS or (source != "compact" and load(root, session) is None):
            take(root, session)
            prune(root)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"protected_guard: no snapshot of the guarded files was taken: {exc}", file=sys.stderr)
    return 0


def handed() -> dict[str, Any] | None:
    """The snapshot `before` printed, handed back on stdin by the process that held it."""
    return parsed(sys.stdin.read()) if sys.stdin is not None and not sys.stdin.isatty() else None


def cmd_after(root: Path) -> int:
    """The runner's comparison after a session: what differs from `before` is put back and printed.
    From the handed snapshot alone; whatever goes wrong is a non-zero exit, never a pass."""
    base = handed()
    if base is None:
        print("protected_guard: no snapshot from before the session on stdin (what `before` printed)", file=sys.stderr)
        return 1
    try:
        now = scan(root)
        found = changes(base["files"], hashes(now))
        if not found:
            return 0
        event = discard(root, base, now, found, "runner (protected_guard.py)")
    except Exception as exc:  # noqa: BLE001  # gate-allow: a comparison that crashed must not read as "nothing changed"
        print(f"protected_guard: the guarded files could not be compared or put back: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_NOT_RESTORED
    for rel, _, _ in found:
        print(rel)
    print(f"protected_guard: {len(found)} guarded file(s) differ; the discarded change: {event['patch']}", file=sys.stderr)
    for line in event["failed"]:
        print(f"protected_guard: NOT put back — {line}", file=sys.stderr)
    return EXIT_NOT_RESTORED if event["failed"] else EXIT_RESTORED


def cmd_pending(root: Path) -> int:
    """Guarded files a commit of the session changed and the working tree no longer agrees with:
    the gate or `after` put them back, and only the runner may commit that."""
    base = handed()
    head = str(base.get("head", "")) if base else ""
    if not head:
        return 0
    known = patterns()
    moved = git(root, "diff", "--no-renames", "--name-only", "-z", head, "HEAD", "--").stdout.split("\0")
    for rel in sorted(rel for rel in moved if rel and is_guarded(rel, known) and rel not in ELSEWHERE):
        if git(root, "status", "--porcelain", "--", rel).stdout.strip():
            print(rel)
    return 0


def cmd_accept(root: Path, ident: str | None) -> int:
    if os.environ.get("CLAUDECODE"):
        print("protected_guard: `accept` is the owner's command and is refused inside a Claude Code session "
              "(CLAUDECODE is set). Run it in your own terminal.", file=sys.stderr)
        return 2
    if ident:
        source = Path(ident) if Path(ident).is_file() else root / STATE_REL / "discarded" / f"{safe(ident)}.json"
        try:
            event = json.loads(source.read_text(encoding="utf-8"))
            for row in event["files"]:
                data = base64.b64decode(row["content"]) if row.get("content") is not None else None
                put(root, row["file"], data if row.get("discarded") is not None else None)
                print(f"protected_guard: {row['file']} is as it was before the guard put it back")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"protected_guard: no discarded change '{ident}' that can be put back (see {STATE_REL}/discarded/): {exc}", file=sys.stderr)
            return 1
    names = [path.stem for path in (root / STATE_REL).glob("*.json")]
    for name in names:
        take(root, name)
    print(f"protected_guard: the guarded files as they are now are the snapshot of {len(names)} session(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None, help="the project (default: CLAUDE_PROJECT_DIR, else the repository of the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("session-start", "before", "after", "pending"):
        commands.add_parser(name)
    commands.add_parser("accept").add_argument("event", nargs="?", default=None)
    args = parser.parse_args(argv)
    top = git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip()
    root = (args.root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or top or Path.cwd())).resolve()
    if args.command == "session-start":
        return cmd_session_start(root)
    if args.command == "before":   # a read: it writes nothing, so there is nothing to refuse to a session
        print(json.dumps(snap(root), ensure_ascii=False))
        return 0
    if args.command == "after":
        return cmd_after(root)
    if args.command == "pending":
        return cmd_pending(root)
    return cmd_accept(root, args.event)


if __name__ == "__main__":
    sys.exit(main())
