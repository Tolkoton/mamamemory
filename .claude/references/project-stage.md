# The project's stage — internal or production (board 207)

One line the owner writes, and one list of what it changes. Read on demand.

## The line

`.claude/project-stage`, the first line that is not empty and not a `#` comment:

```
production
```

- `internal` (or `внутрішній`) — the owner's own projects (thinkhow, mamamemory): the agent fixes
  what is technical itself and seals a contract after the critic's technical objections (boards
  310, 314, 409–411).
- `production` (or `продакшен`) — a project with users: what reaches the users is looked over by
  the owner before it goes, as listed below.
- No file, or no value line → `internal`, exactly as before board 207. A value the script cannot
  read → `production`: an unreadable owner's line never lets the agent decide more.

`python3 .claude/hooks/stage.py show` prints the stage and where it was read.

**Only the owner writes it.** The path is in `GUARDED_PATTERNS` of
`.claude/hooks/protected-path-list.sh`: in a Claude Code session `protect-paths.sh` refuses an edit
tool, `block-dangerous.sh` a shell write, and the gate blocks a change of the file. The owner
writes and commits it in their own terminal, or asks their operator to.

## What goes to the owner in production — the one list

| Change | In `production` | In `internal` |
|---|---|---|
| Sealing a slice contract after a `CRITIC_REVISE` (or a two-way `CRITIC_ESCALATE` the agent decided) of the cold-reader | Not sealed: a card in `tasks/blocked/` with the question and `Дія runner-а: reseal-contract <slug> <sha256>`; the owner's «так» is the seal (`stage.py seal`) | The agent seals it (a third fresh cold-reader after a second REVISE, board 314) |
| Sealing a contract the cold-reader passed with no REVISE | The agent seals it | The agent seals it |
| Changing a sealed contract | The owner's «так» under `reseal-contract` (board 308) | The same |
| A deploy (`docker push/run`, `docker compose up`, release) | Ask-gated: the owner's command (engine-rules.md, «Permissions») | The same |
| A data migration (alembic, `manage.py migrate`) | Ask-gated; editing a migration is hard-denied | The same |

Only the first row differs by stage: the other three are the owner's in both stages already, and
stay so. A product decision, a threshold and a one-way door go to the owner in both stages
(Article 5; `/plan-slice`, `CRITIC_ESCALATE`): `stage.py route … ESCALATE:PRODUCT_DECISION` prints
`owner`, a two-way category `rerun` (proposal 1787).

## In production, what the builder does with the card

`stage.py seal` prints `NOT SEALED` and the card. Mark the slice `CONTRACT PARKED — owner review`
in `.engine/PROGRESS.md` (the DAG reads `parked` as stopped) and take the next slice the DAG lets
start. When the runner has sealed it on «так», `contract_fingerprint.py check` matches and the
slice is built as any other.
