# gate.py — the one gate script

Read this when the Stop gate blocked you and its message was not enough, when you wire a git
pre-commit hook or a CI job, or when you change the gate. Hook table: `hooks.md`.

```
python3 .claude/hooks/gate.py --layer {post_write|stop|pre_commit|ci} [--files F...] [--diff REF] [--hook]
```

Exit 0 = no `block` finding, 2 = at least one. `--hook` speaks Claude Code's protocol (envelope on
stdin; a Stop block is `{"decision":"block","reason":…}` with exit 0). Report:
`.claude/state/gate/last-report.json` — per finding file, line, rule, severity (`block|warn|log`),
message, hint; `timings_ms` per step. The separate gates write `<source>-report.json` beside it in
the same schema. Settings live in `.claude/project.env` and nowhere else.

| Layer | Runs | Scope | Blocks |
|---|---|---|---|
| `post_write` | after every edit | one file: format, then a quick `ruff check` | never; says what changed through `additionalContext`, only when something did |
| `stop` | turn end | the files the turn changed (working tree + index vs HEAD + untracked): lint and types on them, the tests that map to them (`tests/test_<module>.py`, or the changed test file); or `LINT_CMD` / `TYPECHECK_CMD` / `TEST_CMD` as set | yes |
| `pre_commit` | `git commit` | the staged diff: bypass guard, then the full set | yes |
| `ci` | pipeline | the whole project: `ruff check .`, `mypy .`, `TEST_CMD_FULL` else `TEST_CMD` | yes |

The default `ruff` and `mypy` run at the versions `.claude/hooks/tool_versions.py` pins (board 107) unless the
project pins its own: `uv run` / `poetry run` when the lockfile names the tool and the runner starts the project's own copy (not the one on PATH), a tool in its virtual environment, or the
command it set. Only another version at hand blocks `stop` with `tools/version` and the reason; in
`post_write` such a ruff neither formats nor lints (a `log` finding says why). pytest is always the project's.

Order inside a layer: bypass guard, delete guard (`stop`, `pre_commit`), lint, types, tests — tests only after a clean lint and types;
then, unless `COMPLEXITY_GATE` is off, the simplifier's signals (`simplify_signals.py`) as `warn`
findings with rule `simplify/<kind>` — the changed files at `stop`, the whole repository at
`pre_commit` and `ci`. A signal never blocks (`.claude/references/simplifier.md`).
A declared limit of `stop`: it is incremental, so a defect in an untouched file or a test broken by
a module with no sibling test is for `pre_commit` and `ci`.

## The snapshot: "no worse than it was" (`baseline.py`)

A project that did not start with the engine has tests that already fail and findings nobody will
fix today. With `.engine/baseline.json` in the project the three blocking layers ask "did it get
worse", not "is it clean". **Without the file nothing changes: must be clean.**

| Measured | In the snapshot | Blocks when |
|---|---|---|
| tests | the names of the tests failing on the day of the snapshot | a failing test is not on the list |
| lint | the number of findings per (file, rule) | a count the layer sees is above the recorded one |
| types | the same | the same |

Counts, not line numbers: lines move with every edit. Coverage is not in the snapshot — a
percentage would become a target. A failure whose output names nothing readable (a crash, a missing
tool) blocks as without a snapshot. An unreadable snapshot excuses nothing (`baseline/unreadable`,
then "clean").

```bash
python3 .claude/hooks/baseline.py record    # the owner, in their own terminal: take the snapshot
python3 .claude/hooks/baseline.py tighten   # anyone: drop what was fixed, lower the counts
python3 .claude/hooks/baseline.py show      # what is left
```

- **Both run the full commands** (those of `pre_commit` / `ci`). What they read: `FAILED <name>` /
  `ERROR <name>` (pytest), `FAIL: <name>` (unittest); `<file>:<line>[:<col>]: <message>` with the
  rule a leading code (`F401`), else a trailing `[code]`, else `other`. With your own `LINT_CMD` /
  `TEST_CMD` make them print those lines; with the defaults the gate adds
  `--output-format concise` to ruff and drops pytest's `-x` once a snapshot exists.
- **The test command must run to the end.** One that stops at the first failure (`-x`,
  `--maxfail`) stops at an old failure and never shows a new one after it; `record` and the gate
  warn (`baseline/exitfirst`).
- **The snapshot only shrinks.** `tighten` removes a listed test that passes and lowers a count that
  went down, and never adds; from then on that test's failure blocks. The full layers say when a
  fixed entry is still listed (`baseline/stale`, a warning).
- **Only the owner loosens it.** A diff of the snapshot that adds a test or raises a count — a
  first snapshot included — is a bypass (`bypass/baseline`), like an added suppression. It passes one
  way: `record` run outside a Claude Code session, which writes its approval of exactly that text
  to `.claude/state/baseline/approved.sha256`. Inside a session `record` refuses to loosen and
  writes nothing; with no snapshot yet it loosens nothing, shows what the first one would record
  and writes nothing either. No `gate-allow` and no contract grant opens this.
- **The debt stays visible.** `board.py review` lists every old test failure by name under
  «Кандидати в нові задачі», with the lint and type totals; the engine files no task for them.

## The Stop counter

`stop_hook_active` is read first. Claude Code sets it on the stop that follows a block, so the gate
ends its work on it only while this session's counter is 0; with the counter above 0 the re-entry is
checked again. A block adds one (per `session_id`), a pass resets. On the `GATE_MAX_BLOCKS`th block
in a row (default 3) the gate lets the turn end, puts its question to the owner on the task board
(`tasks/blocked/9NN-gate-escalation-….md`; a project without `tasks/` gets a PARKED entry in the parked log —
the session's own file of it, `.engine/journal/parked/`, board 739 — instead), says so in a `systemMessage`, and starts counting again. That
is not the end of it: see "An open escalation refuses the PASS" below.

While a rebase or a merge is in progress (git's `rebase-merge`, `rebase-apply` or `MERGE_HEAD`) the
gate writes no file to the board: the working tree is not the branch then, and a number that looks
free may be taken. The escalation is recorded as usual and entered in the anomaly journal; its
question is put on the board by the first Stop gate run after the rebase or merge is over, or by
the board runner (`gate.py --ask-waiting`).

## An install not yet committed (stop, pre_commit) — `installed.py`

`engine.py install` never commits, so until the owner's first commit every engine file is
untracked and would read as the turn's own work — the engine's own justified `# noqa` lines, the
seeded `project.env`, the shipped `ruff.toml` (board 786). A file that the diff base lacks **and**
that is byte for byte what `.claude/engine-lock.json` recorded (`files`: an engine file; `seeds`:
a seeded file as it was seeded) is left out of the guards and the checks; the report carries one
`log` finding, `installed`, with the count. Both conditions, never one: a changed byte makes it
somebody's edit, and a file the base already has is the project's — putting a tracked
`project.env` back to its seed is a change of the gate's scope like any other. A seeded file edited
before the first commit is compared with the seed it started from (`engine.py` keeps the text in
`.claude/state/install/seeds/`, believed only while its blob id is the lock's), so the guard names
the keys really changed: `SOURCE_DIRS` set in `project.env` is not "a change of `CODE_EXTENSIONS`";
a change of `CODE_EXTENSIONS` itself still blocks until the owner commits it. No lock, an
unreadable lock, a lock written before `seeds` existed: nothing is taken on trust. The same rule
keeps `protected_guard.py`, compared with HEAD, from reporting the untouched constitution,
settings and `.engine/rules.md` of such an install.

## The bypass guard (stop, pre_commit)

A block when the turn's diff **adds** a `# type: ignore`, a `# noqa`, `pytest.mark.skip` /
`skipif` / `xfail` (or `pytest.skip()` / `xfail()`), or **changes** the linter's or type checker's
configuration: the parsed `[tool.ruff]` / `[tool.mypy]` of `pyproject.toml`, any change of
`ruff.toml`, `.ruff.toml`, `mypy.ini`, `.mypy.ini`, or the values of `LINT_CMD`, `TYPECHECK_CMD`,
`TEST_CMD`, `TEST_CMD_FULL`, `FORMAT_CMD`, `GATE_MAX_BLOCKS`, `COMPLEXITY_MAX_CYCLOMATIC`,
`COMPLEXITY_MAX_NESTING`, `COVERAGE_CMD` in `.claude/project.env`; or **loosens the snapshot** `.engine/baseline.json` (above). Syntax only:
comments come from the tokenizer, marks from the AST, configuration from the parsed tables, so a
string, a docstring or a reformat is not a finding.

The guard calls no tool, so it does not wait for `PROJECT_MARKER`: in a project whose marker file
does not exist yet the Stop layer skips lint, types and tests, and still runs the guard.

Allowed when the justification stands next to it:

- `# gate-allow: <reason>` on the same line, or on the comment-only line directly above; for a
  configuration file, any added line of that file. A reason is at least 12 characters and two words.
- or the slice contract says `gate-allow: <type-ignore|noqa|skip|xfail|path> — <reason>` — honoured
  only while the contract is **sealed and unchanged** (`.claude/state/contracts/<slug>.sha256`
  matches), so the work being judged cannot grant itself the exemption by editing a slice file.

`PROJECT_MARKER`, `CODE_EXTENSIONS`, `DELETE_GUARD_LINES` and `PUSH_PROTECTED_BRANCHES` are guarded
more strictly: the first three decide whether a check runs at all, the last which branches
`block-dangerous.sh` refuses a push into (unset or empty: `main stable`; order and commas do not
matter). A change of any of them blocks, and passes one way only — the
sealed contract names the key: `gate-allow: PROJECT_MARKER — <reason>` (or the other key). A reason in
`project.env` itself or a grant of the whole file does not pass. Unset and empty are the same value
(for `DELETE_GUARD_LINES`: the default, 20). `COVERAGE_CMD` is guarded like the other commands.

## The delete guard (stop, pre_commit) — `delete_guard.py`

Deleted code that no test touched leaves every test green — there were none — and nobody learns
that behaviour went with it. So the gate **blocks** when the diff against the base (HEAD; the index
at `pre_commit`) deletes working code no test touched:

| Deleted | Counts when |
|---|---|
| a function, a method, a class | its name is defined nowhere in the new text of the file |
| a file | it is gone (a Python file: each of its functions and classes is judged) |
| lines inside one function | more than `DELETE_GUARD_LINES` (default 20) code lines; docstrings, comments and blank lines are not counted |

Working code is a file with an extension of `CODE_EXTENSIONS` that is not a test (a `tests/`,
`test/`, `spec/`, `__tests__/` directory, `test_*`, `*_test`, `*.test`, `*.spec`, `conftest`).
**A move is not a deletion:** a function or class whose name is defined anew anywhere in the same
change, and a removed line that the same change adds again anywhere, do not count. For a language
other than Python there are no names: the unit is the file and its removed lines.

**Was there a test** — the more exact way wins:

1. `COVERAGE_CMD` is set: the command runs in a clean checkout of the code *before* the change —
   with the tests as they were and, only when those leave a deletion unanswered, once more with the
   test files of the change laid over it — and leaves `coverage.json` (coverage.py's
   `coverage json`). A function or class passes when a test executed a line of its body; removed
   lines pass when at most `DELETE_GUARD_LINES` of them were never executed. The result is cached
   per (commit, tests, command) in `.claude/state/delete-guard/coverage/`. No readable report →
   a warning (`delete/coverage-unavailable`) and the coarser way.
2. not set: the module has its test file (`test_<module>`, `<module>_test`, `<module>.test`,
   `<module>.spec`), or a test file mentions the name. Test files of the base and of the change
   count together, so a test deleted with its code still says the code was tested.

**Three ways through a block** (`delete/untested`):

1. **A test.** Write one that pins what the code does today and passes on the code before the
   deletion, then delete. It may sit in the same change, uncommitted.
   `python3 .claude/hooks/bugfix.py pins --test <file> --cmd "<the command that runs it>"` shows
   that it passes there: it runs the test on a clean copy of the code before the change.
2. **Dead code needs no test, the owner's word does.** A simplifier finding about that code with
   evidence from a tool (a signal of `simplify_signals.py`), confirmed by the owner in their own
   terminal:
   ```bash
   python3 .claude/hooks/delete_guard.py confirm <findings.json> F-xxxxxxxx [--request request.txt]
   ```
   Refused inside a Claude Code session and for a finding with no tool evidence; the confirmation
   is machine state (`.claude/state/delete-guard/confirmed.json`) and covers what the finding
   names — a symbol, the definitions at its lines, or the whole file. A «так» in
   `.engine/simplifier/decisions.jsonl` is not a confirmation: an agent can write that file.
3. **The owner's grant in the sealed slice contract:** `gate-allow: delete — <reason>` (every
   deletion of the slice) or `gate-allow: <path> — <reason>` (one file).

`python3 .claude/hooks/delete_guard.py show` prints the threshold, the mode and what is confirmed.
What the guard cannot know is in `docs/engine-limits.md`.

## Who reads the reason (package costs)

The gate checks a reason's shape; the overseer judges whether it is true.
`python3 .claude/hooks/gate_allows.py [--json] [--base REF] [--all]` lists every exemption the work
adds that has not been judged: markers in `.py` comments (with the suppression they stand beside),
added marker lines of a config file, and a suppression that passes on a sealed contract's grant,
shown where it is used. `overseer_stop.py` appends the list to `OVERSEER_REQUEST` (nothing when it
is empty; a notice when the collector failed), and the overseer skill's check #4 blocks a weak or
missing reason.

**Judged means shown and passed.** At an audit request the hook records what the request listed and
the commit (`.claude/state/overseer/gate-allows-pending.json`); only a recorded PASS of the overseer
agent that follows (`overseer_verdict.py record`) promotes exactly that (`gate-allows-judged.json`) and moves the base to that commit. A
PASS with no request behind it, an exemption added after the request, a BLOCK, a refused PASS —
none marks anything judged, and running the script by hand records nothing. With nothing judged yet
the base is the active contract's `base_commit`, else the merge-base with the main branch, else
HEAD — so a checkpoint commit hides nothing. A second suppression that copies an accepted reason
is a new exemption.

## An open escalation refuses the PASS

The `GATE_MAX_BLOCKS`th block also records the escalation in `.claude/state/gate/escalations.json`:
the files it blocked on (every file it looked at, when the failure named none) and, in a project with a
task board, the task in `tasks/doing/` whose turn it was (`work`). While it is open,
`overseer_verdict.py` records a BLOCK ("gate escalation open") in place of the overseer's PASS for the
unit the escalation covers. The lock is keyed on the files, not on the slice's name —
`.engine/PROGRESS.md` is the agent's own file — and on whose change it is (board 301): it covers a unit
whose own change to one of those files is still in the range no accepted PASS has covered (the task in
hand changed the file in one of its commits, or the file differs from HEAD in the tree), and every unit of
the task named in `work` while the file is unjudged. The unit of another board task passes; its PASS
moves the base, but the escalated files are written into `held` (`gate-allows-judged.json`) with the
commit their change is counted from: neither the change nor its gate exemptions become judged, and the
first audit after the close has them back in its range. Without a board task nobody can tell whose a
change is, and the lock covers every unit while the files are unjudged — there other work passes once
the escalated changes are set aside uncommitted (`git stash push -- <files>`). An escalation that names
no file covers all work. The board starts no task whose PASS would be refused (`board.py`, A GATE
ESCALATION HOLDS A TASK).

In a project with a task board (`tasks/`) the escalation is also written as a task,
`tasks/blocked/9NN-gate-escalation-<stamp>.md`, with what the gate blocked on and one question.
The owner answers `так` (exactly that one word) in that file — in the branch or through the inbox — and
`board-runner.sh` runs the command below and moves the task to `done/`; any other answer is an
instruction and sends the task to an agent with the escalation still open. The runner takes an
answer only when it arrived by its pull or from the inbox: one already in the checkout was
written on the agent's machine, and is wiped and asked again. Without a board, or at any time,
the owner closes it in their own terminal:

```bash
python3 .claude/hooks/gate.py --close-escalation <stamp|all>   # the stamp is in the gate's question
```

The command refuses inside a Claude Code session (`CLAUDECODE` set). It changes the state file
only: `parked.md` is history, nothing in it is marked closed, and editing it closes nothing.

## Wiring a git pre-commit hook and CI (nothing here installs them)

```bash
# .git/hooks/pre-commit  (chmod +x)
#!/usr/bin/env bash
exec python3 .claude/hooks/gate.py --layer pre_commit

# a CI job: one step
python3 .claude/hooks/gate.py --layer ci --diff origin/main
```

No file under `.github/workflows/` is shipped; add the step to your pipeline yourself.

## Measuring it

`python3 evals/run_gate_evals.py --engine-ref HEAD` — defective files that must be caught, clean
files that must not be blocked, every layer timed. `bash tests/run_all.sh` runs `tests/test_gate.py`,
`tests/test_gate_evals.py`, the snapshot's scenes, `tests/test_baseline.py`, and the delete guard's, `tests/test_delete_guard.py`. Reference results: `evals/baseline/linux-ubuntu-22.04/gate-evals-package-7.json`.
