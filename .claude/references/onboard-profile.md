# Project profile — <project name>

<!-- The template of `.engine/onboard/profile.md`. `/onboard` copies it there and fills it; write it
in the owner's language (without the owner: the language of what started the session — the
command's opening says how it is known). Read on demand by the maintenance commands, the architects and their
critics — it is not imported into CLAUDE.md. Every claim below cites what it rests on
(`file:line`, a commit, a command that was run); a claim with nothing to cite is not written as a
fact — in the map it goes under "Claims of the map with no reference". Delete these comments as
the sections fill. -->

Status: **draft — not confirmed by the owner** <!-- without the owner add: "steps 1–4 only";
after step 5: "confirmed by the owner, <date>". If no lint, type-check or test command could be
run, say so here, first; if one part of the project ran none, name that part here. -->
Surveyed at commit: `<sha>` · Tree: <clean | not clean: N changes from the installation, M others> · Fresh reader: <not yet | date, N references checked, M corrected, K rules reworded>

## 1. Map

<!-- Languages; what is in which directory (code, tests, generated, vendored); the entry points;
how the parts connect. "This is how it is" — never "this was decided". The opening sentence is a
claim like the rows below it: it cites what it rests on, or it is not the opening sentence. -->

The project in one sentence: <what it is and does> — <`file:line` it rests on>

| Path | What it is | Evidence |
|---|---|---|

Claims of the map with no reference (the opening sentence included: what the survey believes and
could cite nothing for — marked here, each a question in section 6, never a line above):

- …

What the installation changed (`git status` at the start of the survey; omit when the tree was
clean): <records moved, old path → new, as a count; other changes that are not the installation's>

| Project file that still names an old path, or excludes it from lint / format | `file:line` | What it does now |
|---|---|---|

Hot places (change most often and are the largest, among the files of code), over <how far back
the history was read>:

| Path | Commits touching it | Lines | Read in full | A test file beside it |
|---|---|---|---|---|

Not code that changes often (lock files, logs, manifests, engine records): <paths, one line>

Reverts, and places fixed again and again (the same history; "none found" is an answer too):

| Path | What happened (reverted / fixed N times) | Commits |
|---|---|---|

Documents and their state (current / contradicts the code — an observation, not a fix):

| Document | State | Evidence |
|---|---|---|

Dependencies and runtimes: <manifests, lock files, the runtime versions they ask for; identifiers
of external accounts are not copied here>

## 2. Commands

<!-- Every command found, whether it works or not. Only the rows with status "ran" may go into
`.claude/project.env`. A result the installation caused (a moved record, an exclusion on the old
directory) starts its last column with "after the installation:" and is not the project's state.
"Part of the project" is the directory or stack the command checks, "whole" when it is all of it.
"Found in" of a variant — a command the survey changed, so found nowhere — is the `file:line` of
the found command it varies, then what was changed ("variant of `Makefile:12`: without `-x`"). -->

| Purpose | Part of the project | Command | Found in | Status (ran / not run / variant) | Exit, duration | What fails, or why not run |
|---|---|---|---|---|---|---|

Tests and scripts that need a secret or the network (told by what they read or call, not by
running them; a path under a directory not read is "counted, not read"):

- Need a secret or a credential: <number> — <paths>
- Need the network or a running service: <number> — <paths>

## 3. Rules

<!-- Every candidate, confirmed or not. Source is one or more of: written / seen in the code / seen
in the history; a comment or docstring is "written, in code". "Seen in the code" says what it is counted over and lists the files that keep the
habit AND those that do not; a count over files not read is marked "counted, not read". Verdict
is the owner's: yes / no / the corrected text verbatim / waits for the owner. -->

| # | Rule (and the part of the project it holds in) | Source | Evidence | Counter-evidence | Owner's verdict | Goes into AGENTS.md |
|---|---|---|---|---|---|---|

Guesses (no source strong enough to offer as a rule):

- …

## 4. Risk zones

| Zone | Paths | Why |
|---|---|---|
| Tests exist (a test file names it — or measured, say which) | | |
| No tests | | |
| No check ran (a part of the project none of whose checks could be run) | | |
| Do not touch — candidates the survey saw (generated, vendored) | | |
| Do not touch — the owner's words | | |

Secrets and credentials: where they are, by path only — never opened, never quoted.

## 5. Not read

<!-- Three levels: read in full is in the map above; here — what was only searched, and what was
not opened. The only claim made about these paths is a count marked "counted, not read". -->

- Searched only: …
- Not opened: …

## 6. Open questions for the owner

1. …
