#!/usr/bin/env python3
"""Which part of this shell command is only text? (board 738)

Called by block-dangerous.sh before it judges a command. The command comes on stdin; what goes
to stdout is the text to judge: the same command with the text nothing executes emptied — a
commit message, the body of a heredoc `cat` writes to a file, a grep pattern, the texts of a
board item. Every check of the hook (the destructive patterns, the owner's variable, the push,
shell_paths.py, shell_readonly.py) then reads that instead of the raw command.

The bias of the hook stands: a refusal too many is a nuisance, an allow too many a breach. So
this script never decides that something is safe. It only removes text, and only when all three
hold; in every other case it prints the command unchanged, and the hook judges as before:

  1. the text stands where a known command takes text and never runs it (TEXT below);
  2. it is quoted and holds no substitution: '…', or "…" without `$`, a backtick or a
     backslash; a heredoc with a quoted delimiter, or with a bare one and none of the three;
  3. NOTHING in the whole command could run it: every simple command is on the short list of
     passive ones (PASSIVE, and the forms of git, grep, sed and board.py below), and the command
     holds no substitution, subshell, group, function, shell keyword or assignment. `bash`,
     `sh`, `eval`, `python3 -c`, `node -e`, `xargs`, `source`, a script, a variable in command
     position — one of them anywhere, and nothing is emptied anywhere.

Rule 3 is what keeps `echo '<text>' | sh`, `cat > x.sh <<'EOF' … EOF` followed by `bash x.sh`,
and `sed 's/a/<text>/' f | sh` judged in full: the text could reach a shell inside this very
command. What it does not cover is what the hook never covered: text written to a file now and
run by a LATER command — the edit tools do the same (docs/engine-limits.md).

Anything this script does not recognise for certain — an unclosed quote, `$'…'`, `${…}`, a
heredoc it cannot close — is a reason to print the command unchanged. Exit status is always 0;
a crash prints nothing, and the caller then judges the raw command.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from itertools import pairwise

Span = tuple[int, int]

REDIRECT = re.compile(r"\d*(?:&>>|&>|>>|>\||>&|<<<|<<-|<<|<&|<>|>|<)")
SEPARATOR = re.compile(r"&&|\|\||\|&|;|&|\||\n")
BARE_END = set(" \t\n;&|<>()")
HEREDOC_NAME = re.compile(r"'(\w+)'|\"(\w+)\"|\\(\w+)|(\w+)")
# git commit -m "$(cat <<'EOF' … EOF)": the one substitution taken for text — a quoted heredoc
# that cat hands back unchanged.
MESSAGE_IDIOM = re.compile(r"\"\$\(cat <<'(\w+)'[ \t]*\n((?:.*\n)*?)\1\n[ \t]*\)\"")
COMMAND_WORD = re.compile(r"^[A-Za-z0-9_.\[\]/-]+$")

# Commands that run nothing they are given, whatever their arguments.
PASSIVE = {"cat", "cd", "cp", "date", "diff", "echo", "false", "grep", "head", "ls", "mkdir", "mv", "printf", "pwd", "rm",
           "tail", "tee", "test", "touch", "true", "wc", "["}
# git subcommands that start no program named on the command line (fetch, push and clone take
# --upload-pack / --receive-pack / an ext:: transport; rebase and bisect take a command).
GIT_PASSIVE = {"add", "branch", "checkout", "commit", "diff", "log", "ls-files", "mv", "restore", "rev-parse", "rm", "show", "stash",
               "status", "switch", "tag"}
GIT_MESSAGE = {"commit", "stash", "tag"}
MESSAGE_FLAG = re.compile(r"^-[A-Za-z]*m$|^--message$")
GREP_FLAGS = re.compile(r"^-[cEFHhIiLlnoPqRrsvwxz]+$")
SED_FLAGS = re.compile(r"^-[nErsz]*(i[\w.~-]*)?$|^--in-place(=[\w.~-]*)?$|^--quiet$|^--regexp-extended$")
# A sed script that cannot run or write anything: substitutions without the `e` and `w` flags, or
# one print/delete of lines.
SED_SUBSTITUTE = re.compile(r"s([^\w\s\\])(?:\\.|(?!\1)[^\\\n])*\1(?:\\.|(?!\1)[^\\\n])*\1[gIp0-9]*")
SED_LINES = re.compile(r"^(\d+|\$)?(,(\d+|\$))?[pd]$")
BOARD = re.compile(r"^(\./)?\.claude/unattended/board\.py$")
BOARD_TEXT = {"--title", "--what", "--question", "--do"}


class Unknown(Exception):
    """The command holds something this script will not vouch for: judge it whole."""


@dataclass
class Word:
    raw: str
    kind: str                            # bare: no quote, no `$`; text: quoted pieces only; other
    spans: list[Span] = field(default_factory=list)   # the insides of a text word's quotes

    @property
    def value(self) -> str:
        return self.raw if self.kind == "bare" else ""


@dataclass
class Command:
    words: list[Word] = field(default_factory=list)
    bodies: list[tuple[Span, bool]] = field(default_factory=list)   # heredoc body, and whether it is only text
    redirected_first = False


class Lexer:
    def __init__(self, text: str) -> None:
        self.text, self.at = text, 0
        self.commands = [Command()]
        self.waiting: list[tuple[Command, str, bool, bool]] = []    # heredocs whose body starts at the next line break

    def run(self) -> list[Command]:
        text = self.text
        while self.at < len(text):
            ch = text[self.at]
            if ch in " \t":
                self.at += 1
            elif text.startswith("\\\n", self.at):
                self.at += 2
            elif ch == "#":
                self.at = text.find("\n", self.at) if "\n" in text[self.at:] else len(text)
            elif ch in "()":
                raise Unknown("a subshell, a function or a group")
            elif m := REDIRECT.match(text, self.at):
                self.redirect(m.group().lstrip("0123456789"), m.end())
            elif m := SEPARATOR.match(text, self.at):
                self.at = m.end()
                if m.group() == "\n":
                    self.bodies()
                self.commands.append(Command())
            else:
                self.commands[-1].words.append(self.word())
        if self.waiting:
            raise Unknown("a heredoc with no body")
        return [c for c in self.commands if c.words or c.bodies or c.redirected_first]

    def redirect(self, operator: str, end: int) -> None:
        command = self.commands[-1]
        command.redirected_first = command.redirected_first or not command.words
        self.at = end
        while self.at < len(self.text) and self.text[self.at] in " \t":
            self.at += 1
        if operator in ("<<", "<<-"):
            m = HEREDOC_NAME.match(self.text, self.at)
            if not m or (m.end() < len(self.text) and self.text[m.end()] not in BARE_END):
                raise Unknown("a heredoc delimiter")
            self.at = m.end()
            self.waiting.append((command, next(g for g in m.groups() if g), m.group(4) is None, operator == "<<-"))
        elif self.at >= len(self.text) or self.text[self.at] in BARE_END:
            raise Unknown("a redirection with no target")
        else:
            self.word()                  # the target: judged by the hook as it stands, never text

    def bodies(self) -> None:
        for command, name, quoted, tabs in self.waiting:
            start = self.at
            while True:
                if self.at >= len(self.text):
                    raise Unknown("a heredoc that does not end")
                end = self.text.find("\n", self.at)
                end = len(self.text) if end < 0 else end
                line = self.text[self.at:end]
                if (line.lstrip("\t") if tabs else line) == name:
                    break
                self.at = min(end + 1, len(self.text))
            body = self.text[start:self.at]
            if not quoted and re.search(r"[$`]", body):
                raise Unknown("a heredoc whose body the shell expands")
            command.bodies.append(((start, self.at), quoted or "\\" not in body))
            self.at = min(end + 1, len(self.text))
        self.waiting = []

    def word(self) -> Word:
        text, start = self.text, self.at
        spans: list[Span] = []
        bare = quoted = other = False
        while self.at < len(text) and text[self.at] not in BARE_END:
            ch = text[self.at]
            if ch == "'":
                end = text.find("'", self.at + 1)
                if end < 0:
                    raise Unknown("an unclosed quote")
                spans.append((self.at + 1, end))
                quoted, self.at = True, end + 1
            elif ch == '"':
                idiom = MESSAGE_IDIOM.match(text, self.at)
                if idiom:
                    spans.append(idiom.span(2))
                    quoted, self.at = True, idiom.end()
                    continue
                end = self.at + 1
                while end < len(text) and text[end] != '"':
                    if text[end] == "`" or text.startswith(("$(", "${", "$["), end):
                        raise Unknown("a substitution")
                    other = other or text[end] in "$\\"
                    end += 2 if text[end] == "\\" else 1
                if end >= len(text):
                    raise Unknown("an unclosed quote")
                spans.append((self.at + 1, end))
                quoted, self.at = True, end + 1
            elif ch == "`" or text.startswith(("$(", "${", "$[", "$'", '$"'), self.at):
                raise Unknown("a substitution")
            elif ch == "\\":
                other, self.at = True, self.at + 2
            else:
                other = other or ch == "$"
                bare, self.at = True, self.at + 1
        kind = "other" if other or (bare and quoted) else "text" if quoted else "bare"
        return Word(text[start:self.at], kind, spans if kind == "text" else [])


def after_flags(args: list[Word], flags: re.Pattern[str], texts: set[str]) -> tuple[list[Word], list[Word]] | None:
    """(the values of the flags in `texts`, the words after the flags), or None at a flag not known."""
    values: list[Word] = []
    index = 0
    while index < len(args) and args[index].raw.startswith("-"):
        flag = args[index].value
        if flag in texts and index + 1 < len(args):
            values.append(args[index + 1])
            index += 2
        elif flags.match(flag):
            index += 1
        else:
            return None
    return values, args[index:]


def git_text(args: list[Word], command: Command) -> list[Span] | None:
    while args and args[0].value in ("-C", "--no-pager"):
        args = args[2:] if args[0].value == "-C" else args[1:]
    if not args or args[0].value not in GIT_PASSIVE:
        return None
    spans: list[Span] = []
    if args[0].value in GIT_MESSAGE:
        for flag, value in pairwise(args):
            if MESSAGE_FLAG.match(flag.value):
                spans += value.spans
        if args[0].value == "commit":
            spans += [span for span, only_text in command.bodies if only_text]
    return spans


def grep_text(args: list[Word]) -> list[Span]:
    """The pattern: the value of -e, or the first word after flags that take no value. With a
    flag this script does not know, nothing is emptied — a quoted FILE must stay judged."""
    found = after_flags(args, GREP_FLAGS, {"-e"})
    if found is None:
        return []
    patterns = found[0] or found[1][:1]
    return [span for word in patterns for span in word.spans]


def sed_text(args: list[Word]) -> list[Span] | None:
    found = after_flags(args, SED_FLAGS, {"-e"})
    if found is None:
        return None
    scripts = found[0] or found[1][:1]
    spans: list[Span] = []
    for script in scripts:
        body = script.raw[1:-1] if script.kind == "text" and len(script.spans) == 1 else script.value
        if not body:
            return None
        if SED_LINES.match(body):
            continue
        at = 0
        while at < len(body):
            m = SED_SUBSTITUTE.match(body, at)
            if not m:
                return None
            at = m.end()
            while at < len(body) and body[at] in "; ":
                at += 1
        spans += script.spans
    return spans if scripts else None


def board_text(args: list[Word]) -> list[Span] | None:
    if len(args) < 2 or not BOARD.match(args[0].value) or args[1].value != "open-item":
        return None
    return [span for flag, value in pairwise(args[2:]) if flag.value in BOARD_TEXT for span in value.spans]


def only_text(command: Command) -> list[Span] | None:
    """What this simple command holds as text, or None when it could run what it is given."""
    if command.redirected_first or not command.words:
        return None
    name, args = command.words[0].value, command.words[1:]
    if not COMMAND_WORD.match(name) or "=" in name:
        return None
    if name == "git":
        return git_text(args, command)
    if name == "sed":
        return sed_text(args)
    if name == "python3":
        return board_text(args)
    if name not in PASSIVE:
        return None
    if name in ("echo", "printf"):
        return [span for word in args for span in word.spans]
    if name == "cat" and not args:
        return [span for span, only in command.bodies if only]
    return grep_text(args) if name == "grep" else []


def judged(text: str) -> str:
    """The command with its text emptied; the command itself when anything in it could run text."""
    try:
        commands = Lexer(text).run()
    except Unknown:
        return text
    spans: list[Span] = []
    for command in commands:
        found = only_text(command)
        if found is None:
            return text
        spans += found
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + text[end:]
    return text


if __name__ == "__main__":
    sys.stdout.write(judged(sys.stdin.read()))
