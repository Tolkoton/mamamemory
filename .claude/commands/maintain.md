---
description: Regular care of a project. Writes the owner's report `.engine/maintain/<date>.md` — outdated and vulnerable dependencies (read-only, with the project's own commands), complexity against the previous report, hot places, what is left in the snapshot "as it was", the open debts of urgent fixes, the lesson queue, task proposals — and ends with the question «Оновити ці N залежностей?» listing patches and minor versions. Updates nothing itself: on the owner's «так» the board runner updates them one at a time, each checked and committed or rolled back. A major version is always a separate task. Removes and tidies nothing. Usually started by the weekly board task the runner places itself.
---

You are running **/maintain**: the regular care of the project. `$ARGUMENTS` is empty or the path
of the board task that asks for it. Speak the owner's language; the report is written in
Ukrainian by the script.

Maintenance **looks and reports**. It does not remove, tidy, rename or update anything: what is
worth work becomes a task proposal in the report, and the one thing that may follow at once — a
handful of small dependency updates — is done by the board runner on the owner's word, not by
you. Changing packages is the owner's act (ask-gated), and unattended you never call it.

## 1. The report

```bash
python3 .claude/hooks/maintain.py report
```

It writes `.engine/maintain/<date>.md` and prints its path. Everything in it is measured, not
judged:

- **Dependencies.** What is outdated and by how much — patch, minor, major — and what has known
  vulnerabilities. The script runs the project's own commands, `DEPS_OUTDATED_CMD` and
  `DEPS_AUDIT_CMD` from `.claude/project.env`, exactly as written. Empty — the step is not
  there, and the report says so; do not guess a command and do not install a tool to get one.
  Both must only read. If one of them plainly changes something (an `install`, an `upgrade`, a
  `fix`), do not run the report: that is a question for the owner (step 4).
- **Complexity against the previous report** — the totals `simplifier.py nightly` records:
  code size, functions over the limits, dead code, duplication, unused dependencies.
- **Hot places** — files that change often and hold a function over the complexity limit.
- **The snapshot "as it was"** — how many old failures and findings are left, how many went.
- **The open debts of urgent fixes**, the overdue ones marked.
- **The lesson queue**, and whether the memory is due a clean-up.
- **Task proposals** — everything above that is worth work, one line each.

Read the report. Add proposals of your own under «Пропозиції задач» only where a number in the
report supports them, and say which. Do not act on any of them: a sharp growth of complexity is
a reason to *propose* calling the simplifier, a finding of dead code is a proposal, an overdue
debt is a proposal. The owner turns a proposal into a task.

## 2. The updates the owner may approve

When something may be updated, the script also writes `.engine/maintain/updates.json`: the
patches and minor versions, nothing else. The class is computed from the two version numbers —
the first number differs: major; a `0.x` whose second number differs: major too; a version that
is not plain numbers: unknown. **A major or an unknown version never enters the list**: each is a
task proposal of its own, because there somebody has to read what was broken on purpose. Do not
edit `updates.json` by hand — not to add one, not to drop one.

## 3. The question that ends the maintenance

```bash
python3 .claude/hooks/maintain.py question
```

It prints the question «Оновити ці N залежностей?» with the list, the action line
`Дія runner-а: update-deps <sha256 of updates.json>` and an empty `Відповідь:`. Exit 3 and
nothing printed — there is nothing to update, and no question.

- **On the board:** write the printed text into the task under «Питання до власника» exactly as
  printed, stage the report and `updates.json`, commit them
  (`.claude/unattended/commit_checkpoint.sh`), move the task to `tasks/blocked/` and commit that.
  Leave `Відповідь:` empty and never run `owner_action.py` yourself — it refuses inside a
  session, and the answer is not yours to give.
- **In a session with the owner:** show the list and say that the update is the runner's act:
  the owner answers on the board, or runs the update in their own terminal.

What the owner's «так» sets off, without you: the runner checks that the list is still the one
the owner saw (another sha256 — nothing is updated, and you are asked to put the question
again), that the checks are green before anything is touched, then updates the patches as one
group and every minor version alone. After each: the full gate — lint, types, the full tests,
no worse than the snapshot — and a commit of its own. An update that broke something is rolled
back and written, with the output, to `.engine/maintain/update-result.md`. Any answer other than
the one word «так» is an instruction for you.

## 4. Closing the task

- **Nothing to update:** the task ends with the report — `report.md` in `tasks/done/NNN-…/`
  carries its main points for the owner and the task proposals.
- **The task came back after the action** (the action line is replaced by the runner's note):
  read `.engine/maintain/update-result.md`, check what it says against `git log`, and put it
  into `report.md` — what was updated (with the commits), what was rolled back and the output
  that shows why. Each rolled-back update becomes a task proposal. Do not try the update again
  and do not fix what broke: that is the proposed task.
- **Something only the owner can settle** (a command that does not look read-only, a report the
  script could not write): a question in the task, `tasks/blocked/`.

## What /maintain never does

- It does not install, add, remove or update a package, and does not run `DEPS_UPDATE_CMD`.
- It does not update a major version — not even on «так»: the list cannot hold one.
- It does not delete code, tidy, reformat or rename, and does not start the simplifier's
  removals: its findings go their usual way (`.claude/references/simplifier.md`).
- It does not touch `.engine/baseline.json`, `.engine/debt.md` or the lesson queue: it reads them.
- It does not set its own schedule: the weekly task is the runner's (`board.py maintain-task`).
