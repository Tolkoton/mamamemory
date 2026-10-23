#!/usr/bin/env python3
"""Does this shell command write to a protected path, or name a secret one? (board 714)

Called by block-dangerous.sh, and only for a command one of whose words already matched the
list in protected-path-list.sh. The command text comes on stdin, the three lists in the
environment (PP_ALLOWED, PP_SECRET, PP_GUARDED: one pattern a line), the directories a relative
path is looked up in as arguments. Exit 0 = allow; exit 2 = refuse, the reason on stderr. Any
other exit is this script failing, and the caller refuses on it too.

What is refused:
  * a word that names a SECRET path — reading it is the breach, so any mention counts. A word
    is taken for a path when its form leaves no doubt (`.env`, `secrets/`, `~/.ssh/…`,
    `credentials.json`) or when a file of that name exists: `jq .key` and `process.env` match
    the list's `\\.key$` and `\\.env$` and are no files;
  * a word that names ANY protected path where the command writes: the target of `>`/`>>`,
    an argument of tee/rm/mv/truncate…, the last argument of cp/ln/install, a file of an
    in-place sed/perl, an output flag's value, and in inline code the file of an `open()` with
    a writing mode, of `write_text()`, `writeFileSync()`, `os.replace()` and their kin.

What it cannot see, and does not pretend to: a path held in a variable or built at run time, a
write made by a script the command only starts, `cd dir && rm file`, a path whose parts stand
in separate strings (the caller hands over only a command one of whose words is a whole path). The text of a command is
all a PreToolUse hook has. Quotes are not parsed HERE: the caller hands over the command with the
text nothing runs already emptied (shell_text.py, board 738), and what is left — the text after
`bash -c`, inline code — is judged quoted or not (a false positive is a nuisance, a false
negative a breach).
"""

from __future__ import annotations

import glob
import os
import re
import sys
from dataclasses import dataclass, field

LEX = re.compile(
    r"""
    (?P<fd>\d*>&(?:\d+|-))              # 2>&1, >&2: a file descriptor, not a file
  | (?P<redir>&>>?|\d*>>?\|?)           # > >> 2> &> >| : what follows is written
  | (?P<open>\()
  | (?P<close>\))
  | (?P<brk>[;&|`])
  | (?P<nl>\n)
  | (?P<quote>['"])
  | (?P<skip>[ \t\r<,\[\]{}]+)
  | (?P<word>[^\s'"<>,;&|()`\[\]{}]+)
""",
    re.VERBOSE,
)
REDIR = object()

# A secret's name that cannot be anything but a path, whatever exists on this disk.
STRONG = re.compile(
    r"(^|/)\.env(\.[^/]*)?$|(^|/)secrets/|(^|/)\.(ssh|aws|gnupg)/|(^|/)\.(npmrc|pypirc)$"
    r"|(^|/)id_(rsa|ed25519)(\.pub)?$|(^|/)(credentials|gcloud-key|service-account[^/]*)\.json$"
    r"|(^|/)engine-ops/simplifier-key\.sh$"
)
WRAPPERS = {"env", "command", "exec", "nohup", "time", "nice", "builtin", "xargs", "timeout", "stdbuf",
            "if", "then", "else", "elif", "do", "while", "until", "!"}
ALWAYS = {"tee", "rm", "rmdir", "unlink", "truncate", "touch", "mv", "shred", "chmod", "chown", "chgrp", "patch"}
TO_LAST = {"cp", "install", "ln", "rsync", "scp"}
IN_PLACE = {"sed", "gsed", "perl", "ruby"}
SHORT_OUT = {"curl", "wget", "sort", "pandoc", "yq"}
LONG_OUT = {"--output", "--out", "--outfile", "--output-file", "--output-document"}
OPENERS = {"open", "openSync", "fopen"}
WRITE_CALLS = {"writeFile", "writeFileSync", "appendFile", "appendFileSync", "unlink", "unlinkSync", "rm", "rmSync",
               "remove", "rmtree", "rename", "renames", "renameSync", "truncate", "truncateSync", "move",
               "chmod", "chown", "write_text", "write_bytes", "touch", "rmdir"}
COPY_CALLS = {"copy", "copy2", "copyfile", "copytree", "copyFile", "copyFileSync", "cp", "cpSync", "symlink", "link"}
# A path handed on through one of these is still the path: open(os.path.expanduser("~/x"), "w").
PATH_WRAPPERS = {"expanduser", "expandvars", "join", "abspath", "realpath", "normpath", "fspath", "str", "Path", "PurePath", "resolve"}
PATH_TAKERS = {"unlink", "unlinkSync", "rm", "rmSync", "remove", "rmtree", "rename", "renames", "renameSync", "truncate", "truncateSync",
               "writeFile", "writeFileSync", "appendFile", "appendFileSync", "chmod", "chown", "touch", "rmdir"}
MODE = re.compile(r"^(?:[wax][bt+]*|r[bt]*\+[bt]*)$|O_(WRONLY|RDWR|CREAT|TRUNC|APPEND)")


@dataclass
class Segment:
    """One simple command, or the arguments of one call in inline code."""

    call: str = ""                       # the name before `(`: open, write_text, copy…
    dotted: str = ""                     # the same name with what stood before its dots: os.replace
    items: list[object] = field(default_factory=list)   # words, and REDIR where a redirection stood
    method: str = ""                     # the method called on this call's result: Path(p).write_text
    method_args: Segment | None = None
    parent: Segment | None = None        # the call in whose arguments this call stands

    def words(self) -> list[str]:
        return [w for w in self.items if isinstance(w, str)]


class Splitter:
    """Splits a command into segments. Parentheses nest (a call inside a call's arguments); a
    separator or a line break starts the next simple command — with `quotes`, only outside a
    quoted string. Both readings are judged: `sed -i 's/a|b/c/' FILE` is one command only when
    the quotes count, `bash -c "ls; rm FILE"` holds a second one only when they do not."""

    def __init__(self, quotes: bool) -> None:
        self.quotes = quotes
        self.stack = [Segment()]
        self.out = [self.stack[0]]
        self.word_end = -1                               # where the last word ended: `name(` is a call
        self.closed: tuple[Segment, int] | None = None   # the call just closed: `).method` belongs to it
        self.quoted = ""

    def split(self, text: str) -> list[Segment]:
        for m in LEX.finditer(text):
            kind = str(m.lastgroup)
            if kind == "quote":
                self.quoted = "" if self.quoted == m.group() else self.quoted or m.group()
            elif not (self.quotes and self.quoted and kind in ("brk", "nl")):
                closed, self.closed = self.closed, self.closed if kind in ("word", "skip", "nl") else None
                getattr(self, f"on_{kind}", lambda *_: None)(m, closed)
        return self.out

    def on_word(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        word = m.group()
        if closed and closed[1] == m.start() and word.startswith("."):
            closed[0].method = word.rsplit(".", 1)[-1]
        self.stack[-1].items.append(word)
        self.word_end = m.end()

    def on_redir(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        self.stack[-1].items.append(REDIR)

    def on_open(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        # The name is the identifier that ends the word before `(`: `open` in `f=open(`, `os.replace`
        # in `x=os.replace(`; `$(` and `=(` end in none and open a subshell, not a call.
        words = self.stack[-1].words()
        name = re.search(r"[A-Za-z_][\w.]*$", words[-1]) if self.word_end == m.start() and words else None
        called = name.group() if name else ""
        seg = Segment(call=called.rsplit(".", 1)[-1], dotted=called, parent=self.stack[-1] if self.stack[-1].call else None)
        if closed and seg.call and closed[0].method == seg.call:
            closed[0].method_args = seg
        self.stack.append(seg)
        self.out.append(seg)

    def on_close(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        if len(self.stack) > 1:
            self.closed = (self.stack.pop(), m.end())

    def on_brk(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        self.stack[-1] = Segment()
        self.out.append(self.stack[-1])

    def on_nl(self, m: re.Match[str], closed: tuple[Segment, int] | None) -> None:
        if not self.stack[-1].call:      # inside a call's arguments a line break is only space
            self.on_brk(m, closed)


def command_word(words: list[str]) -> str:
    """The command a segment runs: its first word past assignments and wrappers (env, timeout 5…)."""
    wrapped = False
    for w in words:
        if re.match(r"^[A-Za-z_]\w*=", w) or (wrapped and (w.startswith("-") or re.match(r"^\d+[smhd]?$", w))):
            continue
        if w in WRAPPERS:
            wrapped = True
            continue
        return w.rsplit("/", 1)[-1]
    return ""


class Lists:
    def __init__(self, env: dict[str, str], bases: list[str]) -> None:
        def read(name: str) -> list[re.Pattern[str]]:
            return [re.compile(p) for p in env.get(name, "").splitlines() if p]

        self.allowed, self.secret, self.guarded = read("PP_ALLOWED"), read("PP_SECRET"), read("PP_GUARDED")
        self.bases = [b for b in bases if b]
        self.home = env.get("HOME", "")

    def classify(self, items: list[object], index: int) -> tuple[str, str, str] | None:
        """(kind, the path as written, the pattern) for a word that names a protected path. A word
        with `=` is tried as its value and whole (`of=FILE`, `--output=FILE`); before both, a path
        put together with `/` in code is tried in one piece: root / ".claude" / "project.env"."""
        word = joined = str(items[index])
        while index >= 2 and items[index - 1] == "/" and isinstance(items[index - 2], str):
            index -= 2
            joined = f"{str(items[index]).rstrip('/')}/{joined}"
        for cand in [joined] * (joined != word) + ([word.split("=", 1)[1]] if "=" in word else []) + [word]:
            if any(p.search(cand) for p in self.allowed):
                return None
            for kind, patterns in (("secret", self.secret), ("guarded", self.guarded)):
                hit = next((p.pattern for p in patterns if p.search(cand)), "")
                if hit:
                    return kind, cand, hit
        return None

    def exists(self, path: str) -> bool:
        if path.startswith("~/") and self.home:
            path = self.home + path[1:]
        if "$" in path:
            return False
        roots = [""] if os.path.isabs(path) else self.bases
        return any(glob.glob(os.path.join(root, path)) for root in roots)


class Use:
    """One word of a segment, with what the write rules ask about it."""

    def __init__(self, seg: Segment, index: int) -> None:
        items = seg.items
        self.seg, self.word, self.words = seg, str(items[index]), seg.words()
        self.before = [w for w in items[:index] if isinstance(w, str)]
        self.after = self.words[len(self.before) + 1:]
        self.redirected = index > 0 and items[index - 1] is REDIR
        self.is_last = not self.after or all(i > 0 and items[i - 1] is REDIR for i in range(index + 1, len(items)) if isinstance(items[i], str))
        self.cmd = command_word(self.words)


def has_mode(words: list[str]) -> bool:
    return any(MODE.search(w.split("=", 1)[-1]) for w in words)


def by_command(u: Use) -> bool:
    """tee FILE, rm FILE, cp x FILE, sed -i … FILE: the command itself writes the word."""
    if u.cmd in ALWAYS:
        return True
    if u.cmd == "dd":
        return u.word.startswith("of=")
    if u.cmd == "git":
        return bool({"rm", "mv"} & set(u.before)) or git_takes_another_revision(u.before)
    if u.cmd in TO_LAST:
        return u.is_last or any(w == "-t" or w.startswith("--target-directory") for w in u.words)
    if u.cmd in IN_PLACE:
        return any(re.match(r"^-[A-Za-z]*i|^--in-place", w) for w in u.words)
    return u.cmd in ("awk", "gawk") and "inplace" in u.words


def git_takes_another_revision(before: list[str]) -> bool:
    """`git checkout -- FILE` and `git restore FILE` put the committed text back — the remedy, not
    the breach. With a revision or a --source named, the file gets some other text: a write."""
    if "restore" in before:
        return any(w.startswith(("--source", "-s")) for w in before)
    if "checkout" not in before:
        return False
    named = before[before.index("checkout") + 1:]
    named = named[:named.index("--")] if "--" in named else named
    return any(not w.startswith("-") and w != "HEAD" for w in named)


def by_output_flag(u: Use) -> bool:
    """--output FILE, --output=FILE, curl -o FILE."""
    flag = u.before[-1] if u.before else ""
    return u.word.split("=", 1)[0] in LONG_OUT or flag in LONG_OUT or (u.cmd in SHORT_OUT and flag in ("-o", "-O"))


def by_call(u: Use) -> bool:
    """Inline code: open(FILE, "w"), Path(FILE).write_text(…), os.replace(x, FILE), shutil.copy(x, FILE).
    `replace` alone is str.replace, in every edit an agent scripts; os.replace moves a file."""
    seg = u.seg
    if seg.call in OPENERS and has_mode(u.after):
        return True
    if seg.call in WRITE_CALLS or seg.method in WRITE_CALLS or seg.dotted == "os.replace":
        return True
    if seg.call in COPY_CALLS and u.before:
        return True
    if seg.method in OPENERS and seg.method_args and has_mode(seg.method_args.words()):
        return True
    return wrapped_for_a_write(seg)


def wrapped_for_a_write(seg: Segment) -> bool:
    """open(os.path.expanduser(FILE), "w"), os.remove(os.path.join(d, FILE)), Path(expanduser(FILE)).write_text(…):
    the word stands in a call that only hands the path on to one that writes it."""
    while seg.call in PATH_WRAPPERS and seg.parent is not None:
        seg = seg.parent
        if (seg.call in OPENERS and has_mode(seg.words())) or seg.call in PATH_TAKERS or seg.method in WRITE_CALLS:
            return True
    return False


def refusal(seg: Segment, lists: Lists) -> str:
    """Why this segment is refused, or ""."""
    for index, item in enumerate(seg.items):
        hit = lists.classify(seg.items, index) if isinstance(item, str) else None
        if not hit:
            continue
        kind, path, pattern = hit
        use = Use(seg, index)
        if use.redirected or by_command(use) or by_output_flag(use) or by_call(use):
            return f"the command writes to a protected path.\nPath: {path}   (pattern {pattern})"
        if kind == "secret" and (STRONG.search(path) or lists.exists(path)):
            return f"the command names a secret path, and reading one is refused too.\nPath: {path}   (pattern {pattern})"
    return ""


def verdict(text: str, lists: Lists) -> str:
    """The reason to refuse the command, or "" to allow it."""
    if lists.home:
        text = re.sub(r"\$HOME\b|\$\{HOME\}", lambda _: lists.home, text)
    # `<root>/path` in a message is a placeholder, not a redirection into /path.
    text = re.sub(r"<([\w-]+)>(?=/)", r"\1", text)
    segs = Splitter(quotes=True).split(text) + Splitter(quotes=False).split(text)
    return next((reason for reason in (refusal(seg, lists) for seg in segs) if reason), "")


def main() -> int:
    reason = verdict(sys.stdin.read(), Lists(dict(os.environ), sys.argv[1:]))
    if not reason:
        return 0
    print(f"BLOCKED by the engine safety hook (block-dangerous.sh): {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
