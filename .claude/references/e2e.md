# The journeys as the condition of «done» — E2E on the deployed revision

Read on demand: by `/feature-architect` at «When the feature is built», by the `slice-tester` in mode
`journey`, by whoever writes the operator's request. Board 317; the research:
`docs/research/2026-11-userflow/R2-journey-e2e.md`. The mechanics: `.claude/hooks/journey_e2e.py`.

## Why

mamamemory's smoke checked one phrase of the model with no state and was green the evening the owner
said «які плани?» went in as the answer to the question on the screen: the client sent every phrase with
`replyTo` of the last question. The break lived between the layers; nothing walked the journey on the
deployed app. Evals measure the model; E2E proves the layers hold together. Both are needed.

## Three layers

| Layer | What | Where it runs | Blocks |
|---|---|---|---|
| C — corpus | `tests/conversations/corpus.json` (board 209: the model's cases and every owner complaint, forever) | the real model, no browser, `conversation.py run --k 3 --out` | any red case, k < 3 |
| J — journeys | `e2e/J-N[-name].spec.ts`, one per journey, Playwright | a tagged revision with no traffic, a phone's screen, `--repeat-each=3 --retries=0` | failed, flaky, skipped, < 3 runs, missing, not sealed |
| Judge | Claude, pass/fail per run against the journey's «людина бачить» | after Playwright, `judge.json` | only once calibrated (below) |

Only deterministic checks block: the screen's `data-state`, the data through the test-only read
endpoint, no pending question left hanging. A judge's score of the same output moves between runs.

## The spec — rules

- One file per journey, `e2e/J-N[-name].spec.ts`, written by the tester in mode `journey` from the
  journey's text, **blind to the code**, and sealed like contract tests (`testing.py` seals it; a
  change is `testing.py reseal <slug> --owner-answer <card>`).
- Every standing `J-N#AC-k` asserted, its id in the title or a comment beside it.
- The project's screen carries `data-state="<state>"` (`idle | listening | question | error | …`, the
  states of its journeys): M3 names it as a testability seam with the test-only read endpoint (for the
  test account only) and the test account. A product without them cannot be walked; that is a slice.
- `devices['iPhone 13']`, the project's `locale` and `timezoneId`.
- Voice: a phrase is typed, or `page.route('**/api/transcribe', …)` answers it. Chrome's fake audio
  file is one per browser and cannot change mid-conversation: real audio is one or two separate tests.
- No `skip`, `fixme`, `only`, `test.fail`, `retries` in the file (refused at the hand-in) — Playwright's
  healer agent skips a test it believes broken, and a skipped journey proves nothing.
- Login: `storageState` from a setup project, its path in `E2E_STORAGE_STATE`; the file is the operator's
  secret, outside the repository, and it expires — renewing it is a request to the operator.

## The test data — the owner's decision (board 317, 2026-11-12)

«пиши в мій календар»: the journeys run under the **owner's own Google account**, never another
person's (in mamamemory: never mama's). Therefore:

- every record a test writes carries the prefix `E2E_PREFIX` (`[e2e]` unless the project says
  otherwise) in its title;
- after every run, red or green, the project's `E2E_CLEANUP_CMD` removes every record with the prefix
  (`.claude/project.env`); `operator-run` refuses to start without it.

## The corpus

A complaint of the owner becomes a line **before** the fix: `conversation.py complaint --state …
--phrase … --expect … --said "<verbatim>" --when "<date, place>"`, then `conversation.py gen`. It is red
on the revision with the bug and green after the fix — that is how the fix is proved. A complaint is
sealed row by row at the tester's journey hand-in (`journey_e2e.py seal-complaints`); a sealed row that
changed or went is refused by `journey-close` — a line goes only by the owner's word.

## The judge

Binary, Claude (not the product's model), the rubric = the journey step's «людина бачить». Its FAIL
blocks only after calibration: `.engine/journeys/judge-labels.jsonl`, one line per run the owner
labelled — `{"id": …, "owner": "pass|fail", "judge": "pass|fail"}` — at least 20, precision and recall
of «fail» ≥ 0.9 (`journey_e2e.py calibration`). Before that a FAIL is printed as a finding for the owner.
A judge FAIL with no change in the code is a finding, never a reason to move the threshold.

## When the feature is built — `testing.py journey-close <feature>`

Reads `.engine/e2e/<sha>/` — `results.json` (Playwright JSON reporter), `corpus-results.json`,
`judge.json`. Refuses (exit 3): results of a commit other than the code in the tree (anything but
`tasks/` and `.engine/` outside `journeys/` and `architecture/` changed since); a journey the feature
cites with no spec in the report; a test flaky, skipped, failed or run fewer than 3 times; retries
above 0; a spec not sealed or changed since; for a product with a conversation model, a red case, k < 3,
a corpus other than the tree's, a complaint not in the corpus or a sealed one changed. A pass goes into
the testing ledger: «journeys J-… green 3/3 on rev <sha>».
An untracked file counts as a change unless git ignores it: the project ignores what a run leaves
(`test-results/`, `playwright-report/`, `node_modules/`, `__pycache__/`).

The agent never deploys and never runs the real model: secrets and the deploy are the operator's. Until
the operator's run comes back, the feature waits in `tasks/blocked/` — «чекає journey-close на деплої» —
and a feature that depends on it does not start.

## The request to the operator

`python3 .claude/hooks/journey_e2e.py request <feature> --service <service> --region <region>` prints it.
It is passed to the operator only on the owner's direct word; otherwise it goes into the task's report
or its question in `blocked/`. The operator runs one command, `journey_e2e.py operator-run …`, which:

1. `gcloud run deploy <service> --source . --region <region> --no-traffic --tag e2e-<sha7> --quiet`;
2. reads the tag's URL (`gcloud run services describe … --format=json`);
3. with a conversation model: `conversation.py run --k 3 --out .engine/e2e/<sha>/corpus-results.json`;
4. `npx playwright test e2e/ --repeat-each=3 --retries=0 --reporter=json` with `BASE_URL` = the tag's URL
   and `PLAYWRIGHT_JSON_OUTPUT_NAME=.engine/e2e/<sha>/results.json`; then, always, `E2E_CLEANUP_CMD`;
5. `journey_e2e.py close <feature>`;
6. only when 5 is 0: `gcloud run services update-traffic <service> --to-tags=e2e-<sha7>=100`. Otherwise
   the old revision keeps the traffic, and the traces (`test-results/`) go into the answer.

Refused inside a Claude Code session (`CLAUDECODE` set).

## The rule of the architecture

`software-architecture.md` §9.1: for a product with a conversation or an LLM in the loop, «few E2E»
means **every sealed journey has its E2E** — the risk lives between the layers.

## Cost (an estimate, not measured)

Corpus: 50 lines × 3 × ~2 calls of a small model — pennies, 1–3 min. Journeys: 10 × 6 turns × 3 ≈ 180
turns of the real model, ~$0.5–2; the judge on 30 transcripts ~$1–3. About $2–5 and 10–20 min a feature.
