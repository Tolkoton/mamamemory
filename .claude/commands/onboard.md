---
description: Get to know an existing project together with its owner. Surveys the code read-only, runs every check command it found for real, recovers the project's rules as candidates each with its source, has a fresh reader verify every reference and every rule's wording against its source, takes the owner's verdict on every one, and leaves the profile `.engine/onboard/profile.md`, `.claude/project.env`, a short AGENTS.md and the snapshot "as it was". Fixes nothing, installs nothing, writes no decisions in hindsight. Use once, after `engine.py install`, in a project that was not built with the engine. Needs the owner in the conversation; without the owner it does steps 1–4 and stops with questions.
---

You are running **/onboard**: the engine's first meeting with a project it did not build. The
rules of such a project live in its owner's head, not in its code — so this is a session with the
owner present, and everything you conclude alone is a *candidate* until the owner has said yes.

Speak and write — the profile, every question — in the owner's language. With no owner present
that is the language of the task or request that started the session; the language of the
project's own documents only when neither says anything. A quotation stays as its source has it.
`$ARGUMENTS` may name a directory to start the survey from; empty means the whole project.

## What /onboard never does

- **It fixes nothing and tidies nothing.** No edit to the project's code, tests, configuration
  or documents other than the five files of step 6. A failing test, a lint finding, a dead file —
  each is written down, none is repaired. A check's cache that a run leaves in the project tree
  and the project itself ignores (`git check-ignore`: `.pytest_cache`, `.ruff_cache`, …) is not a
  change to the project.
- **It writes no decisions in hindsight.** No ADR, no "we chose X because…": the structure is
  recorded as "this is how it is", never as "this was decided". Why something is so is the
  owner's to say, in their words, or it stays an open question.
- **It installs nothing.** Not the engine (`engine.py install` did that before this command), not
  a package, not a tool. A command whose tool is absent is recorded as «not run», never repaired.
- **It reads no secrets.** `.env`, `secrets/`, credential and key files are not opened and never
  quoted; the profile says only that they exist and where. A script that loads such a file itself
  is not run. Identifiers of external accounts are not copied into the profile — neither from a
  document nor from the output of a command you ran.
- **It never answers for the owner** and never infers a verdict from an earlier remark.

## Who is here

Unattended — `CLAUDE_UNATTENDED_SESSION=1`, or `.claude/state/overseer/mode` says `unattended` —
or the session has no way to ask (no interactive question, or whoever started it said so): do
**steps 1–4 only** — the fresh reader of step 4 needs no owner and is not skipped —, write the
profile as a draft (its first line says so, every candidate rule has the verdict «waits for the
owner»), and stop with the questions of the draft. Step 5 is a procedure, not a list; the
draft's questions are these, in this order:

- that no check could be run (step 2), when that is so;
- one for each contradiction «document against code» — a written rule the code does not follow,
  a document the code contradicts: which of the two is the rule;
- one for each command whose effect is unclear (step 2);
- one for what the installation changed, when it left project files that name an old path or a
  check with another result (steps 1 and 2): the list, and whether the owner brings the project's
  files to the new paths before the snapshot;
- one for the do-not-touch zones: the candidates the survey saw, and what else there is;
- one for each part that was not read: read it, or leave it alone;
- one common question for all the remaining candidates — they wait for the owner's yes, no or
  corrected text in a session the owner sits in; never a question per candidate.

They are written, numbered, into the profile's «Open questions» section. On the task board they
also go into the task's «Питання до власника» and the task to `blocked/`. With no board and no
owner «print them» has no addressee: the questions stay in the profile, and whoever started the
session gets only the profile's path and the number of questions. Do not touch
`.claude/project.env`, `AGENTS.md`, the snapshot or the premise log, and do not act out the
owner's part. Steps 5–8 are for a session the owner sits in.

## If the project already has agent files or an older engine

Its `AGENTS.md`, `CLAUDE.md`, progress journals and earlier engine records are documents to
survey and sources of *written* rules like any other. Look for the records in both places: the
new one, `.engine/`, where `engine.py install` moved them, and the old ones (`.claude/overseer/`,
`.claude/premises/`, `.claude/architecture/`, `.claude/artifacts/`, `PROGRESS.md` at the root) —
a record that stood in both places was left where it was, and the old paths are what the
project's own files still name (step 1, «What the installation changed»). A rule that is the engine's own policy (commits,
hooks, the overseer) is not a candidate rule of the project. The sign is what the rule is about,
wherever it is written: the project's code and data — a candidate; the way an agent works
(commits, branches, tasks, hooks, audits, sessions, its memory) — the engine's. So a rule about
secrets that stands inside a section on the overseer is a candidate when it says what the code or
the repository may hold; «one commit per task» in a task file is not; a lesson in an older
engine's memory is judged by the same sign, one lesson at a time. The engine's own commands and
the checks of its hooks are not *found* commands: they check the engine, not the project — one
row in the map, not run in step 2, and they never go into `project.env`. In step 6 an existing
`AGENTS.md` or `project.env` is not replaced: show the owner the difference and change only what
they agree to.

## 1. Survey — read only

Create `.engine/onboard/profile.md` from `.claude/references/onboard-profile.md` and fill it as
you go; nothing else is written in this step.

- **What the installation changed** — first, before anything is written: `git status --short`
  and `git rev-parse HEAD`. The commit is the one the survey is of; the tree is not that commit
  when `engine.py install` ran before this command and nobody committed. Count the changes and
  write the count beside the commit in the profile («tree not clean: N changes from the
  installation», and how many that are not the installation's — those are the owner's unfinished
  work, named and left alone). Where records moved (a deleted old path and a new file under
  `.engine/`), list the project's own files that still name an old path, with `file:line` —
  `git grep -n -e '.claude/overseer' -e '.claude/premises' -e '.claude/architecture' -e
  '.claude/artifacts' -e 'PROGRESS.md' -- . ':!.claude' ':!.engine'` (a line that names only `.engine/PROGRESS.md` is not one) — and the lint and format
  configuration that excludes an old directory and not `.engine/`. `engine.py install` prints
  both as `note` lines; its output is gone by now, so search again. Nothing is fixed: the list
  goes into the profile and is one question for the owner.
- **Languages and layout**: what is in which directory, which directories are code, tests,
  generated, vendored.
- **How it is built, tested and checked** — from the CI files, Makefile/task runner, package
  manifests, pre-commit and linter configuration, an existing `project.env`, agent instruction
  files, setup and deploy documents, usage lines in script headers. Collect every command with
  the file and line that names it. These are *found* commands; step 2 decides which of them
  work. A family of deploy or provisioning commands in one document is one row.
- **Dependencies**: the manifests and lock files, the runtime versions they ask for.
- **A repository of several stacks** is mapped part by part; a command and a rule name the part
  they belong to.
- **Existing documents and decisions**: README, docs, ADRs, agent instruction files. Note which
  look current and which contradict the code — as an observation, not a fix.
- **History**: `git log` — which files change most often and are at the same time the largest
  (commits touching the file, and its lines: the places where work will most likely land);
  reverts; the same file fixed again and again — these go into the profile's table «Reverts, and
  places fixed again and again», with the commits. On a long history, say how far back you looked.
  Hot places are counted among the files of code only: lock files, logs and journals, manifests
  and the records of an engine change often and are large without being where work lands — they
  go under the table as one line, «not code».
- **A claim of the map you can cite nothing for** — the opening sentence about what the project
  is as much as any row — goes under «Claims of the map with no reference» and becomes a question
  for the owner; it is not written among the facts.
- **A large project is not read whole.** Read the hot places first — a hot source file is read
  in full before any rule about it is offered — and write in the profile's «Not read» section
  what you only searched and what you did not open. A count from a search over files you did not
  read is marked «counted, not read»; any other claim about an unread file is not made.
- **An older engine's records are not read whole either.** Read what holds decisions and rules:
  the decisions and deferred items of each slice contract, the entries of the escalations log,
  the lessons in its memory, the ADRs. The rest — ledgers, verdicts, audit requests, progress
  journals, the remaining body of the contracts — is listed in «Not read» with its size in lines.

## 2. Check the commands — by running them

Before any script of the project is run, list the key variables set in the session's environment —
names only, never a value (`awk 'BEGIN { for (k in ENVIRON) print k }' | grep -iE
'key|token|secret|passw|credential'`) — and write the names into the profile. A listing that
failed is not an empty list, and a paid key may carry none of these words: read the names a
script itself asks for. Check that each command's tool is there (`command -v`, `--version`); a
tool that lives only in the project's virtual environment is invisible to `command -v` and works
through the runner — probe it there, and its run is «ran» through the runner, not «tool absent».
Then run every command found in step 1, one at a time, each with a time limit (ten minutes
unless the owner names another; a timeout is recorded as «ran, timed out»), and record for each:
the exact command, the exit code, how long it took, and what failed (counts and names, not a
pasted log). In a project of several parts the row's «Part of the project» names the part the
command checks. Tests and scripts that need a secret or the network are counted apart, under the
table: the number and the paths, told by what they read or call.

- **A command that was not run does not go into `project.env`** — it would be an unverified
  premise about someone else's system (constitution, Article 1). It goes into the profile as
  «not run», with the reason: tool or runtime version absent, dependencies not installed, needs
  the network, a service or a credential, long-running or interactive, needs arguments the survey
  cannot supply, would change the sources or something outside the working tree (a throwaway
  directory under the system's temp directory does not count as outside).
- **A key in the session's environment is a credential the script already has.** A script that
  with such a key would reach a paid or external service is «not run», or is run with the variable
  explicitly unset (`env -u NAME …`) and the row says which variable. «It stops without a key» is
  true of a key file and false of a key the session carries.
- A runner that would create an environment or download packages on first use (`uv run`, `npx`,
  …) counts as tool absent when the environment is not there: running it would install.
- An environment that is there may have drifted from the lock file, and the runner then syncs —
  installs — without a word. Run it with syncing off and offline (`uv run --no-sync --offline`,
  `npx --no-install`, …). Such a guard does not make the command a variant: the row is «ran»,
  it names the guard, and what may go into `project.env` is the command as found.
- One check named in several documents in different spellings (`pytest`, `python -m pytest`,
  `uv run pytest`) is one row with every source, not a row per spelling.
- **A command that exits 0 having checked nothing is not «ran».** The path it reads is empty or
  gone, no test was collected, no file matched: read what a passing command says it checked, not
  only its exit code. Record «ran, checked nothing» with what was missing; «ran, checked nothing»
  does not go into `project.env`.
- **A result the installation caused is recorded as a consequence of the installation, not as
  the state of the project.** A script that reads an old path of a moved record and now checks
  nothing; a formatter or linter that now fails on files under `.engine/` because its exclusion
  names the old directory: the row says «after the installation», names the moved path or the
  files, and cites the line of the script or of the configuration. It is a consequence only with
  that evidence — every failing file is one the installation moved or added, or the command
  names an old path; a failure with any other file in it is the project's, in full. What the
  command did at the surveyed commit was not measured: do not write that it passed. Such a row
  does not go into `project.env`, and before the snapshot of step 7 the owner is told that it
  would record this consequence as the project's «as it was».
- A variant of a found command (fewer arguments, another interpreter) may be run to learn
  something; it is recorded as a variant and does not go into `project.env`. «Found in» of a
  variant is the `file:line` of the found command it varies and what was changed.
- **If none of lint, type-check and tests could be run**, say so in the first line of the profile
  and make it the first question: the meeting is not complete until the owner has prepared the
  environment, and steps 6–7 wait for it.
- **In a project of several parts where one part ran its checks and another ran none**, the
  first line of the profile names the part with no check that ran, and that part is the first
  question. Steps 6–7 do not wait: `project.env` and the snapshot take the commands that ran,
  the owner is told before taking the snapshot which part it does not measure, and that part
  goes into the risk zones as «no check ran» and into the premise log (step 8).
- Run nothing that deploys, publishes, migrates, pushes, or writes outside the project. If a
  command's effect is unclear, it is «not run» and a question for the owner.
- A command that runs and fails is still a verified command: the failures are what the snapshot
  of step 7 is for. Do not fix them.

## 3. Recover the rules — every candidate with its source

Write the candidate rules into the profile. Each names its source — one or more of three:

- **written** — a document, linter setting or CI step says it; cite `file:line`. A comment or a
  docstring in the code is **written** too — somebody wrote the sentence down; the source column
  then says «written, in code»;
- **seen in the code** — a habit most files keep; give the count and what it is counted over
  (which directory, which kind of file), and list the files that keep it **and the files that do
  not** (up to ten by name, the rest as a number). When the files that keep it are the majority
  and one search command lists them, name only the files that do **not** keep it and write that
  command in place of the list. Kept in one directory and not in another, it is a rule of that
  directory, or a guess;
- **seen in the history** — a reverted change, the same place fixed again and again; cite the commits.

A candidate with no source is not offered (Article 4). A guess is called a guess. A written rule
the code does not follow is offered as it is — with both the citation and the counter-evidence —
and the owner decides which of the two is the rule. A candidate is something a change could
break, however short its source: in well-commented code a real invariant is exactly one sentence,
and it is a rule when the code keeps it — name the check, the test or the call sites that do.
One linter setting is not by itself a rule, and one sentence that nothing in the code confirms is
a guess.

A rule is worded no more strongly than its source — the fresh reader of step 4 will ask exactly
this. «only», «always», «every», «never» need a count or a quotation that carries the word; a
rule from a source that speaks of one case is worded about that case.

## 4. A fresh reader checks every reference and every rule's wording

Before the owner sees a candidate, and in a session without the owner too: the reader needs no
owner. Start one agent in a fresh context (`Agent`, no part of this conversation in its prompt)
with only the path of the profile and two jobs. It edits nothing.

- **Every reference.** For every `file:line`, commit and command the profile cites, open it and
  say whether it says what the profile claims — «holds», «does not hold» (with what it does say)
  or «could not check».
- **Every rule's wording against its source.** Is the rule worded more strongly than what it
  cites: «only», «always», «every», «never» with no count and no quotation that carries the word;
  a general rule from a source that speaks of one case; a commit that says less than the rule
  claims. The answer is «no stronger than its source», or «stronger» with the wording the source
  does support.

You have just read thousands of lines and see order where there may be none (Article 6); the
reader has not.

Correct or remove every reference that does not hold, and reword every rule that is stronger than
its source to what the source supports. A candidate whose source fell away altogether is not
offered: it moves to the guesses. «Could not check» stays written next to its reference. The
profile's second line says how many references were checked, how many corrected and how many
rules reworded.

**After the owner's verdicts (step 5)** the reader runs again only over what the owner's words
changed: a reference that a corrected text or a rule the owner added brought with it, the paths
of a do-not-touch zone. What it has checked and nobody changed is not checked twice. A rule whose
source fell away in this second check goes back to the owner as a question; it does not stay
confirmed.

## 5. The owner decides

One candidate at a time (`AskUserQuestion` is right here): **yes**, **no**, or the owner's
corrected text, recorded verbatim next to the candidate. Many candidates are a long sitting, so
keep an order: first the contradicted ones (a written rule the code does not follow, a rule the
reader had you reword), then the ones you would propose for `AGENTS.md`, then the rest. Candidates
of one kind go under one «yes» only if the owner asks for it — never offer it: the question then
names each of them by its number, and the verdict is written on each. Then ask separately for the
**do-not-touch zones**: generated code, vendored code, what is about to be removed. They go into
the profile and into `SIMPLIFIER_PROTECTED`.

Ask too which of the confirmed rules a conversation cannot do without — only those go into
`AGENTS.md` (step 6).

## 6. What stays after the meeting

| File | What goes into it |
|---|---|
| `.engine/onboard/profile.md` | the map; the commands with the evidence of their run; **every** rule with the owner's verdict and its source; the risk zones (tested / untested / do not touch); what was not read |
| `AGENTS.md` | written with the skill `documentation` (its bootstrap workflow): the project in one sentence, the key paths, and only the rules without which any conversation would go wrong. The rest is read from the profile on demand |
| `.claude/project.env` | `SOURCE_DIRS`, `CODE_EXTENSIONS`, the check commands — only those step 2 ran; `SIMPLIFIER_PROTECTED` from step 5 |
| `.engine/baseline.json` | step 7 |
| `.engine/premises/premise-log.md` | step 8 |

There is no number of rules for `AGENTS.md`: the persistent context has one limit — CLAUDE.md,
AGENTS.md and what they import stay under 200 lines — and the simplifier (lens `instructions`)
looks at what is extra. Show the owner the three files before writing them.

## 7. The snapshot "as it was"

The project's checks fail today in ways nobody will fix today; the snapshot lets the gate ask
"no worse than it was".

**First the owner agrees the `project.env` of step 6, then the snapshot.** `record` measures with
the commands of `.claude/project.env` as it is on disk. A file left by an earlier setup may name
other commands, not the ones step 2 ran — another list of directories for the type check, tests
that stop at the first failure — and the snapshot would then be of checks nobody verified. Until
the file on disk holds the commands step 2 ran, the snapshot waits. When the test command stops
at the first failure `record` prints a warning; it is not passed over — the option goes out of
`project.env` first, or the owner is told what the snapshot will not see.

**The owner takes it, in their own terminal**:

```bash
python3 .claude/hooks/baseline.py record
```

Inside this session `record` prints what it measured — with no snapshot yet, what the first
snapshot would record — and refuses to write: use that to show the owner, then wait for them to
run it. `python3 .claude/hooks/baseline.py show`
confirms it. Then print `python3 .claude/hooks/complexity_budget.py calibrate`: it proposes
complexity limits from the project's own code, and applying them is the owner's choice.

## 8. Open questions and unverified premises

Everything about the project that could not be checked — a command not run, a rule the owner
was unsure of, a part not read, a behaviour assumed from a document — goes into
`.engine/premises/premise-log.md` as an unverified premise, with what would verify it (Article 8).
Close with: the files written, the questions left open, the commands the owner still has to run.
