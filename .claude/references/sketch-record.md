# The sketch's record — `.engine/sketches/<name>.md` (board 099)

A task in the mode **ескіз** answers one question. Its code lives only in `sketches/<name>/` — the
gates do not check it, and it never becomes working code: carrying it over is a new task in соло or
конвеєр, where the code is written anew under that task's checks. What stays is the record, the
evidence a later decision cites (the constitution, article 4).

## The template

```markdown
# Ескіз <name>

## Питання
<one question, answerable by «так» or «ні»>

## Що пробували
<what was built under sketches/<name>/ and why that settles the question>

## Команда і вивід
```
$ <the exact command, from the project root>
<its output, as it came — not retold>
```

## Відповідь
так | ні | не з'ясовано
<one sentence: which line of the output says it; for «не з'ясовано» — what was tried and why it did not settle the question>
```

## Who reads it

The same reader reads the report of a task that changed no working code (board 100; `tasks/README.md`, «Правила для агента», 6).
Before the task closes, a fresh **reader** (`.claude/agents/reader.md`) reads the record and judges one
thing: does the output prove the answer? Ask for it with
`python3 .claude/hooks/reader.py request <task> --record .engine/sketches/<name>.md` and launch the agent
`reader` with exactly the line it prints. A BLOCK — fix the record and ask again: another reader reads
it. Three BLOCKs in a row — the board runner parks the task. The runner closes a sketch only with a PASS
on the record as it is (`mode.py check-close`): change the record after its PASS and it must be read again.

## The quarantine (gate.py)

- A task in ескіз changes nothing outside `sketches/`, `.engine/` and `tasks/` — the gate blocks it.
- Working code that refers to a sketch — a Python import of `sketches`, a string that is a path into a
  named sketch, such a path on an added line of a script — is a block in every mode.
- The gates do not check a sketch's code: not on the Stop layer, not in the delete and bypass guards, and
  the default `ruff` / `mypy` / `pytest` of the full layers skip the root's `sketches/`. A project that sets
  its own `LINT_CMD`, `TYPECHECK_CMD`, `TEST_CMD` or `TEST_CMD_FULL` excludes `sketches/` there itself.
- What it does not catch: `docs/engine-limits.md`, «The sketch's quarantine».
