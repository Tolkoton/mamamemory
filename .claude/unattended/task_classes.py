#!/usr/bin/env python3
"""The arithmetic of task numbers (board 401): a number is its class x 100 + its place in the class.

A class is one digit, 1...9 (0 is what was there before classes and is never given). When a class
has used c01...c99 it goes on in the identifier + 10: 799 -> 1701 -> ... -> 1799 -> 2701. So the
last digit of `number // 100` is the class of every number, and a number never walks into another
class. The place 00 is never given; the old 600, 700, 800, 900 stay what they are.

This module only counts and reads the table. It reads no task: the caller hands it the numbers
the board holds. Giving a task its class and the renumbering after a merge are not here.

THE TABLE (tasks/CLASSES.md) is the owner's: a Markdown table whose rows begin with `|` and a class
number 0...9. The queue does not read it yet: `board.py next` goes by number (`queue_key` is written
and tested for the day the order of the rows becomes the order of the queue; nothing calls it).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

CLASSES_FILE = "CLASSES.md"  # tasks/CLASSES.md: a row a class
_DIGITS = re.compile(r"[0-9]+")  # ASCII digits only: `\d` and int() also take digits of other scripts
_NUMBERED = re.compile(r"(\d{3,})-.")  # a task's number as board.number_of reads it from a name
UNCLASSED, OWN, OPEN_ITEMS, RULES, GATES = 1, 4, 7, 8, 9  # nobody gave a class; the runner's own; the three kinds of question


def class_of(number: int) -> int:
    """The class a number belongs to, 0...9: the last digit of its hundreds."""
    return number // 100 % 10


def next_number(taken: Iterable[int], klass: int) -> int:
    """The number after the largest one of `klass` in `taken`; the first of the class when there is none.
    A gap under the largest is not filled: the number of a task that is gone may still be named somewhere."""
    if klass not in range(1, 10):
        raise ValueError(f"no task is numbered in class {klass}: the classes are 1...9")
    largest = max((n for n in taken if class_of(n) == klass), default=klass * 100)
    return largest + 1 if largest % 100 < 99 else (largest // 100 + 10) * 100 + 1


def _row_numbers(text: str) -> list[int]:
    """The whole numbers in the first cell of the rows (lines that start with `|`), in the text's order —
    those that are no class (12) and the repeated ones too. A cell that is not ASCII digits only is prose."""
    cells = (line[1:].split("|", 1)[0].strip(" \t") for line in text.splitlines() if line.startswith("|"))
    return [int(cell) for cell in cells if _DIGITS.fullmatch(cell)]


def parse_classes(text: str) -> tuple[int, ...]:
    """The classes of the rows of a CLASSES.md text, in the text's order; a class written twice keeps its first place."""
    return tuple(dict.fromkeys(n for n in _row_numbers(text) if n <= 9))


def read_classes(tasks: Path) -> tuple[int, ...]:
    """`parse_classes` of tasks/CLASSES.md; () when the board has no table."""
    table = tasks / CLASSES_FILE
    return parse_classes(table.read_text(encoding="utf-8", errors="replace")) if table.is_file() else ()


def table_errors(text: str) -> list[str]:
    """What is wrong with the table, one sentence for the owner per defect; the reader keeps the sound rows all the same."""
    numbers = _row_numbers(text)
    no_class = [f"рядок із номером {n}: клас — це одна цифра від 0 до 9, такого класу не буває; рядок не читається" for n in numbers if n > 9]
    twice = [f"клас {n} має кілька рядків: чинний перший, решту приберіть"
             for n in dict.fromkeys(numbers) if n <= 9 and numbers.count(n) > 1]
    return no_class + twice


def class_for(wanted: int, classes: tuple[int, ...]) -> int:
    """The class a task that names one is numbered in; ValueError says, for the owner, why it is not."""
    if wanted == 0:
        raise ValueError("клас 0 — це задачі до класів, нових задач у ньому не буває")
    if not classes:
        raise ValueError(f"клас {wanted} не можна назвати: у проєкті немає таблиці класів tasks/{CLASSES_FILE}")
    if wanted not in classes or wanted > 9:
        raise ValueError(f"класу {wanted} немає в tasks/{CLASSES_FILE}")
    return wanted


def queue_key(classes: tuple[int, ...], first: list[str]) -> Callable[[str], tuple[int, int, int]]:
    """The queue's order as a sort key over a task's file name: the names in `first`, then the classes in the
    order of `classes` (one not listed — after them), the lower number inside a class. No classes: by number."""
    answered = {name: place for place, name in reversed(list(enumerate(first)))}
    rank = {klass: place for place, klass in enumerate(classes)}

    def key(name: str) -> tuple[int, int, int]:
        numbered = _NUMBERED.match(name)
        number = int(numbered.group(1)) if numbered else 0
        return answered.get(name, len(first)), rank.get(class_of(number), len(classes)), number

    return key
