#!/usr/bin/env python3
"""Does this shell command of a read-only agent write anywhere but a temporary directory? (board 055)

Called by block-dangerous.sh for a Bash call made inside the overseer agent (`agent_type` in the
hook envelope). The auditor reads and judges: it runs the tests, reads git, and reproduces a RED
in a copy under /tmp — it never changes the tree it audits. The command text comes on stdin, the
shell's working directory and the project's root as the arguments (a path inside the project is
never a temporary one, even when the project itself lives under /tmp). Exit 0 = allow; exit 2 = refuse, the reason on
stderr. Any other exit is this script failing, and the caller refuses on it too.

What is refused, unless the place written is a temporary one (/tmp, /var/tmp, $TMPDIR; and
/dev/null with its kin):
  * the target of a redirection, an argument of tee/rm/mv/touch/truncate…, the last argument of
    cp/ln/install, the file of an in-place sed/perl, `dd of=`, an output flag's value, and in
    inline code the file of an `open()` with a writing mode, of `write_text()` and their kin —
    the write rules of shell_paths.py, asked of EVERY path instead of the protected ones;
  * a git command that changes the working tree, the index or the refs (add, commit, stash,
    checkout, reset, apply, merge…), where the repository is not a temporary copy;
  * a tool told to rewrite files: a formatter without --check, a linter with --fix.
`cd <dir>` is followed from one simple command to the next, so `cd /tmp/copy && git stash` and
a relative path after it are judged in the copy; a name assigned from `mktemp` in the same
command (`D=$(mktemp -d) && cp -r . "$D" && cd "$D"`) stands for a temporary directory.

What it cannot see, and does not pretend to: a write made by a script or a test the command
only starts, a path in a variable (refused as unknown where it stands as a target), a `cd`
inside a subshell that ends before the write. A redirection inside a quoted string is not one
(`grep "a > b"`, `python3 -c "print(1 > 0)"`), except in the text handed to `bash -c` and its
kin. What slips through is still caught after the fact: overseer_verdict.py compares the tree
with its fingerprint from the audit's start and records the verdict as INVALID.
"""

from __future__ import annotations

import os
import re
import sys

import shell_paths as sp

# NAME=$(mktemp -d): the name then stands for a fresh directory under the temporary root — the way
# the agent's own instructions tell it to make its copy. With -p or --tmpdir the place is the
# caller's choice, and the name stays unknown.
MKTEMP = re.compile(r"\b([A-Za-z_]\w*)=\"?(?:\$\(|`)\s*mktemp((?:\s+-[dqu]+|\s+-t\s+[\w.-]+|\s+[\w.-]*X{3,}[\w.-]*)*)\s*(?:\)|`)")
DEVICES = re.compile(r"^/dev/(null|zero|stdout|stderr|stdin|tty|fd/\d+)$")
SHELLS = {"bash", "sh", "zsh", "dash", "eval"}
SKIP_FIRST = {"chmod", "chown", "chgrp"}                 # their first argument is a mode or an owner
VALUE_FLAGS = {"truncate": {"-s", "--size", "-r", "--reference"}, "touch": {"-d", "-t", "-r", "--date", "--reference"},
               "tee": set(), "sed": {"-e", "-f", "--expression", "--file"}, "perl": {"-e", "-E"}, "ruby": {"-e"}}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
GIT_WRITES = {"add", "am", "apply", "bisect", "branch", "checkout", "cherry-pick", "clean", "commit", "config", "gc", "init", "merge",
              "mv", "notes", "pull", "push", "rebase", "remote", "reset", "restore", "revert", "rm", "stash", "submodule", "switch",
              "tag", "update-index", "update-ref", "worktree", "clone"}
GIT_READ_FORMS = {
    "stash": {"list", "show"}, "worktree": {"list"}, "remote": {"-v", "show", "get-url"}, "bisect": {"log", "view", "visualize"},
    "apply": {"--check", "--stat", "--numstat", "--summary"}, "notes": {"list", "show"}, "submodule": {"status", "summary"},
    "config": {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"},
    "branch": {"--show-current", "--list", "-l", "-a", "-r", "-v", "-vv", "--all", "--remotes", "--contains", "--merged", "--no-merged", "--points-at"},
    "tag": {"--list", "-l", "-n", "--contains", "--points-at", "--verify", "-v"},
}
GIT_TO_PATH = {"clone": -1, "worktree": 1}               # the directory they create: the last word; the first after `add`
REWRITERS = [                                            # (the command words, what makes it a rewrite, what makes it a check)
    (("ruff", "format"), None, {"--check", "--diff"}),
    (("black",), None, {"--check", "--diff"}),
    (("isort",), None, {"--check", "--check-only", "--diff", "-c"}),
    (("gofmt",), {"-w"}, set()),
    (("cargo", "fmt"), None, {"--check"}),
    (("prettier",), {"--write", "-w"}, set()),
    (("ruff",), {"--fix", "--unsafe-fixes", "--fix-only"}, set()),
    (("eslint",), {"--fix"}, set()),
    (("autopep8",), {"-i", "--in-place"}, set()),
    (("npm", "pkg"), {"set", "delete"}, set()),
]


class QuoteAware(sp.Splitter):
    """The splitter of shell_paths.py with one difference: `>` inside a quoted string is text."""

    def on_redir(self, m: re.Match[str], closed: tuple[sp.Segment, int] | None) -> None:
        if not self.quoted:
            super().on_redir(m, closed)


class Places:
    def __init__(self, cwd: str, env: dict[str, str], project: str = "") -> None:
        self.cwd: str | None = cwd or None
        # The tree under audit is never a temporary place, wherever it lives: a sandbox or a
        # test repository sits under /tmp itself.
        self.project = os.path.normpath(project) if project and os.path.isabs(project) else ""
        self.home = env.get("HOME", "")
        roots = ["/tmp", "/var/tmp", "/private/tmp", env.get("TMPDIR", "")]
        self.roots = [os.path.normpath(r) for r in roots if r and os.path.isabs(r)]
        self.tmpdir = env.get("TMPDIR", "") or "/tmp"

    def resolve(self, word: str) -> str | None:
        """The absolute path a word names, or None when the text does not show it."""
        word = re.sub(r"\$\{?TMPDIR\}?", lambda _: self.tmpdir, word)
        if self.home:
            word = re.sub(r"\$\{?HOME\}?", lambda _: self.home, word)
            word = self.home + word[1:] if word == "~" or word.startswith("~/") else word
        if "$" in word or "`" in word or word.startswith("~"):
            return None
        if not os.path.isabs(word):
            if self.cwd is None:
                return None
            word = os.path.join(self.cwd, word)
        return os.path.normpath(word)

    def temporary(self, word: str) -> bool:
        path = self.resolve(word)
        if path is None:
            return False
        if self.project and (path == self.project or path.startswith(self.project + "/")):
            return False
        return bool(DEVICES.match(path)) or any(path == r or path.startswith(r + "/") for r in self.roots)

    def change_directory(self, words: list[str]) -> None:
        target = next((w for w in words[1:] if not w.startswith("-") or w == "-"), "~")
        self.cwd = None if target == "-" else self.resolve(target)


def plain(words: list[str], cmd: str) -> list[str]:
    """The arguments of a command that can be files: no flags, no value of a flag that takes one."""
    takes = VALUE_FLAGS.get(cmd, set())
    out: list[str] = []
    skip = False
    for w in words:
        if skip:
            skip = False
        elif w in takes:
            skip = True
        elif not w.startswith("-") and not re.match(r"^[A-Za-z_]\w*=", w):
            out.append(w)
    return out


def command_arguments(words: list[str]) -> tuple[str, list[str]]:
    cmd = sp.command_word(words)
    at = next((i for i, w in enumerate(words) if w.rsplit("/", 1)[-1] == cmd), len(words) - 1) if cmd else len(words) - 1
    return cmd, words[at + 1:]


def written_by_command(cmd: str, args: list[str]) -> list[str]:
    files = plain(args, cmd)
    if cmd in SKIP_FIRST:
        return files[1:]
    if cmd in sp.ALWAYS:
        return files
    if cmd in sp.TO_LAST:
        named = [w.split("=", 1)[1] for w in args if w.startswith("--target-directory=")]
        named += [args[i + 1] for i, w in enumerate(args[:-1]) if w in ("-t", "--target-directory")]
        return named or files[-1:]
    if cmd in sp.IN_PLACE and any(re.match(r"^-[A-Za-z]*i|^--in-place", w) for w in args):
        return files[1:] if cmd in ("sed", "gsed") and not any(w in VALUE_FLAGS["sed"] for w in args) else files[-1:]
    if cmd == "dd":
        return [w[3:] for w in args if w.startswith("of=")]
    return []


def written(seg: sp.Segment) -> list[str]:
    """Every word of the segment that the command writes."""
    words = seg.words()
    cmd, args = command_arguments(words)
    out = [] if seg.call else written_by_command(cmd, args)
    for index, item in enumerate(seg.items):
        if not isinstance(item, str):
            continue
        use = sp.Use(seg, index)
        value = item.split("=", 1)[1] if item.split("=", 1)[0] in sp.LONG_OUT and "=" in item else item
        if use.redirected or (sp.by_output_flag(use) and not item.startswith("-")) or value != item:
            out.append(value)
        elif seg.call and sp.by_call(use) and ("/" in item or "." in item) and not sp.MODE.search(item):
            out.append(item)
    return out


def git_write(words: list[str], places: Places) -> str:
    """Why this git command is refused, or ""."""
    cmd, args = command_arguments(words)
    if cmd != "git":
        return ""
    where = "."
    index = 0
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "-C" and index + 1 < len(args):
            where = args[index + 1]
        index += 2 if args[index] in GIT_VALUE_OPTIONS else 1
    sub, rest = (args[index], args[index + 1:]) if index < len(args) else ("", [])
    if sub not in GIT_WRITES:
        return ""
    if sub in GIT_READ_FORMS and (set(rest) & GIT_READ_FORMS[sub] or (sub in ("branch", "tag", "stash", "remote", "worktree") and not rest and sub != "stash")):
        return ""
    if sub in GIT_TO_PATH:
        files = [w for w in rest if not w.startswith("-")]
        target = files[GIT_TO_PATH[sub]] if len(files) > abs(GIT_TO_PATH[sub]) - (GIT_TO_PATH[sub] < 0) else ""
        if sub == "worktree" and files[:1] != ["add"]:
            target = ""
        if target and places.temporary(target):
            return ""
    elif places.temporary(where):
        return ""
    return f"`git {sub}` changes the repository it runs in"


def rewrite(words: list[str], places: Places) -> str:
    cmd, args = command_arguments(words)
    line = [cmd, *args]
    for name, makes, checks in REWRITERS:
        if tuple(line[:len(name)]) != name or set(args) & checks:
            continue
        if (makes is None or set(args) & makes) and not places.temporary("."):
            return f"`{' '.join(name)}` rewrites the files it is given"
    return ""


def refusal(seg: sp.Segment, places: Places) -> str:
    words = seg.words()
    if not seg.call:
        if sp.command_word(words) in SHELLS:             # `sh -c "rm file"`: what follows is the command
            start = next((i for i, w in enumerate(seg.items) if w in ("-c", "eval")), None)
            inner = sp.Segment(items=seg.items[start + 1:]) if start is not None else None
            if inner and inner.words():
                return refusal(inner, places)
        if sp.command_word(words) == "cd":
            places.change_directory(command_arguments(words)[1] and ["cd", *command_arguments(words)[1]] or ["cd"])
            return ""
        reason = git_write(words, places) or rewrite(words, places)
        if reason:
            return reason
    for word in written(seg):
        if not places.temporary(word):
            shown = places.resolve(word) or f"{word} (the text does not show where that is)"
            return f"the command writes {shown}"
    return ""


def verdict(text: str, cwd: str, env: dict[str, str], project: str = "") -> str:
    text = re.sub(r"<([\w-]+)>(?=/)", r"\1", text)
    # Before the words are cut: `${NAME}` would fall apart at its braces.
    known = {name: f"/tmp/mktemp-{name}" for name in (m.group(1) for m in MKTEMP.finditer(text))}
    known |= {"TMPDIR": env.get("TMPDIR", "") or "/tmp"} | ({"HOME": env["HOME"]} if env.get("HOME") else {})
    for name, place in known.items():
        text = text.replace("${" + name + "}", place)
        text = re.sub(r"\$" + name + r"\b", place.replace("\\", r"\\"), text)
    readings: list[sp.Splitter] = [QuoteAware(quotes=True)]
    if re.search(r"(^|[\s;&|(])(" + "|".join(sorted(SHELLS)) + r")\s+(-\w+\s+)*['\"]", text):
        readings.append(sp.Splitter(quotes=False))       # the text handed to `bash -c "…"` is a command
    for splitter in readings:
        places = Places(cwd, env, project)
        for seg in splitter.split(text):
            reason = refusal(seg, places)
            if reason:
                return reason
    return ""


def main() -> int:
    cwd = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    reason = verdict(sys.stdin.read(), cwd, dict(os.environ), sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else cwd)
    if not reason:
        return 0
    print(f"BLOCKED by the engine safety hook (block-dangerous.sh): the overseer agent is read-only, and {reason}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
