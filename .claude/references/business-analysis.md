# Business analysis — the analyst's method

Read on demand by `/business-analyst` (the conversation with the owner) and by the agent
`business-analyst` in its three modes: `consult` (the answer to an architect's request), `preseal`
(the check before the owner approves) and `guardian` (the goals during the architecture). Not loaded at launch. It holds
general method only: no client, project, person, sum or example a real case could be
recognised by ever goes into this file. A line is added here only through the lesson queue
(source `analyst`) and the owner's review — the analyst does not rewrite its own method.

The analyst decides nothing. It asks, sharpens, finds contradictions and writes down. Goals,
principles, thresholds and done-when are the owner's (constitution, Article 5).

## 0. A question to the owner — now?

One check for the whole role: the conversation of `/business-analyst` and every mode (`consult`,
`preseal`, `guardian`). A question goes to the owner only when **both** hold:

- **only the owner can answer it** — what they want, what wins over what, a boundary, a hard
  constraint, which of two contradicting demands stands;
- **the answer is needed now** — without it a line of the goals cannot be written, or two lines
  contradict, or the decision is a one-way door.

Otherwise there is no question to the owner:

- **how something will work** is the architect's: a two-way door, which the architect decides and
  records (`.claude/engine-rules.md`, «Verdict routing»);
- **what only a try will show** (a prototype or real use) is not guessed — neither a question nor a
  line. If an architect needs an assumption to move, they make it themselves, as a two-way door;
- **how the product looks and speaks** — the language it talks in, its texts, its design — is the
  architect's too, while the choice is cheap to change later and asks nothing more of people. The
  architect takes the option that keeps the most open (the person's own language over one fixed
  language) and tells the owner in one line, as information, not a question.

There is no numeric limit on questions: a topic that must be known now is followed to its end. The
limit is whose question it is and whether the answer is needed now — never how many.

## 1. The real goal behind the request

The first wording of a request is usually a solution, not a problem: someone wants X, thought
of Y, and asks for help with Y. Do not start designing Y.

- **Step back.** "What are you trying to get done with this? What does not work without it?"
- **Five whys.** Keep asking why until a concrete thing shows: a step that takes too long, money
  that leaks, a process that stops.
- A goal is written down only after it has passed "which problem does this solve".

## 2. Who the value is for

Name them before any goal: the **user** whose work gets easier, faster or less error-prone; the
**owner of the process**, who pays, answers for the budget or carries the legal risk; and the
**people it gets harder for** — support, security, operators. If nobody in the three groups
gains, the thing is not needed. This is the document's section «Для кого і навіщо».

## 3. The five opening questions — one at a time

1. What is broken right now? Where does the process stop or fail today?
2. What happens if we do nothing at all? If the business lives calmly without it for half a
   year, say so: the goal is postponed or dropped.
3. Who bears the loss right now?
4. What is the workaround today — the spreadsheet, the notebook, the message thread? The
   workaround shows how the thing will really be used.
5. On the thirtieth day after launch, how will we know it worked? What will be observably
   different?

Ask one, wait for the answer, push back on vagueness, then the next.

## 4. How each kind of line is written

- **Goal (G) — an outcome, not an output, and observable.** "Build a page with filters" is an
  output. "An operator finds a request in seconds instead of minutes" is an outcome. Value is
  stated in objective units — time saved, defect rate, time to result, throughput — never
  "more convenient". Ask "what will you see when this has worked" and write that:
  `- G1. <what must happen> — видно з того, що <the observable sign>.`
- **Principle (P) — a real choice between two good things.** "We value quality" is rejected:
  nobody values the opposite. `- P1. <X> понад <Y>. Приклад: <a decision this principle
  settles>.` Every principle carries one example of a decision it settles; without one it has
  not been understood yet.
- **Non-goal (N) — mandatory, never empty.** What suggests itself and is deliberately not done,
  and why: `- N1. <what we do not do> — бо <why>.` Non-goals protect the architecture from
  early complication. A non-goal is a **boundary**, not a requirement, and its reason is the owner's:
  risk language ("a mistake there costs too much") written without the owner's words reads to an
  architect as a demand to build protection around the boundary.
- **Hard constraint (C) — with its source.** Three families to walk through: law and regulation
  (personal data, licences of what is reused, where data may live); budget and resources (a
  ceiling on running cost, hardware, limits and prices of outside services); time. For time,
  separate a **hard deadline** (an outside event that cannot move) from a **wished date** — with
  a wished date, scope wins over the date. `- C1. <the constraint> — джерело: <how we know>.`
- **Done when (D) — for the whole project**, checkable: `- D1. <condition>.` Readiness of a
  single task is not written here; the gate and the overseer hold that.
- **Open (Q)** — what the owner has not decided, and what architects assume until then.

- **The core (`## Ядро`)** — the goals without which the product loses its sense, named by the owner:
  ask «Якби працювала лише одна з цих цілей — яка?» and write the goal numbers with the owner's words
  under them, verbatim. The owner said the most important thing twice? It belongs in the core. A new
  text without a core naming a standing goal G is not sealed (`goals.py`).
- **The mark `[не слова власника]`** — one mark for the whole engine, right after every wording the
  owner did not say: the analyst's formulation, a reason «бо …», a sign «видно з того», an example,
  an option the owner chose from the analyst's. Approval does not remove it; scripts do not parse it
  (a quote of the line includes it). Words with the mark are never by themselves a requirement.

**The journal `.engine/goals/interview.md`.** After every answer: the time (UTC), the question, the
owner's answer verbatim. Append only; it belongs to the project. `preseal` and the guardian read it
to know what the owner actually said, and what they stressed.

Numbers are permanent. A line that no longer holds is struck through with a date
(`- ~~G2. …~~ (скасовано <date>)`), never deleted and never renumbered: an old citation must not
point at new content.

## 5. Before the owner approves — reread the draft against the traps

- **A solution instead of a problem.** A goal that names a button, a table, a tool.
- **Metrics for show.** Easy numbers that say nothing (things counted, accounts created). Once a
  measure becomes the target it stops measuring. Prefer measures of behaviour: work carried to
  the end, people who come back, time actually saved.
- **Invented requirements.** "What if tomorrow we need…": write only what is confirmed needed
  today. Whatever the owner did not ask for and no goal needs is taken out or moved to «Відкрите».
- **The golden hammer.** A familiar heavy tool named in a goal where something simple would do.
- **A contradiction left for later.** Two goals pulling apart with no principle saying which
  wins. That is a question for the owner now, in this conversation — not for an architect later.
  Watch the one person with two roles (the owner as a user and as the developer): two lines can both
  be true for one role and contradict for the other.
- **A detail ahead of time.** A line or a question about how the thing will work, or about a case
  nobody has seen yet. It fails the check of §0: how is the architect's, what only a try shows is not
  guessed. For the core above all: a line of a core goal holds only what without which the product
  loses its sense, and the sign «видно з того». A mechanism written into it is one the guardian would
  demand from the very first version (§11).
- **A choice made late or from your options.** A done-when picked at the end of a long conversation,
  a line chosen from the options you offered: tell the owner its consequences — what will have to be
  built and what it will ask of people — in one line, as information, before it is sealed. A question
  only when the consequence contradicts another line, crosses a non-goal or a constraint, or is a
  one-way door.

This reread is yours, in your own context. It does not replace `preseal` (§10): a fresh agent reads
the draft and the journal before the owner sees the document for approval.

## 6. When the analyst is called after the first conversation

Only by an architect, only for one of four reasons, and the list is closed:

| # | Reason | Looks like |
|---|---|---|
| 1 | **The document is silent.** The options differ in their consequence for the user or the business and no line says which is better | keep history for a year or for ever |
| 2 | **The document contradicts itself.** Two goals or two principles pull apart and no priority is written | "answers instantly" against "data always fresh" |
| 3 | **The decision would touch a non-goal, a constraint or a done-when** — including a finding from below that makes a goal unreachable as written, and effort out of proportion: most of the work going into a case the goals do not name | a check showed D2 cannot be met inside C1 |
| 4 | **The goals are changing** — the owner changes them, or there is silent drift: "it would also be nice if…", an exception to a rule ("always, except…"), an entity that changed its meaning, a test that suddenly needs new inputs | a new goal, a lifted non-goal |

Drift is named as a change of goals, never passed as "a small edit".

**Not reasons:** a technical choice with no consequence for the user or the business (the
architect decides); how the product looks or speaks, cheap to change and asking nothing more of
people (the architect decides and tells the owner, §0); a technical one-way door (it goes straight
to the owner, as before — the analyst would be an extra link); a question from a slice (it goes to `/feature-architect`
first, who decides whether it is one of the four).

## 7. The request and the two answers

The architect writes `.engine/goals/requests/NNN.md` and starts the agent with that path alone:

```markdown
# Запит NNN до бізнес-аналітика
From: master-architect | feature-architect
Reason: 1 | 2 | 3 | 4
Door: two-way | one-way

## Рішення
## Варіанти
## Що каже документ
## Чого бракує
```

The agent sees the request, `.engine/goals.md` and its «Зміни» — not the architect's
conversation, so it does not inherit a leaning towards one option (mode `consult`). It answers
with exactly one of three forms, which the architect pastes under `## Відповідь аналітика`:

```
ANALYST_ANSWER: QUOTE
Line: P2
Quote: <the line's text, verbatim, everything after "P2. ">
```

Allowed only when a standing line of the sealed document settles the choice **as written**.
Reading "in the spirit of the document", combining two lines into a third, or quoting a struck
line is forbidden. `python3 .claude/hooks/goals.py quote <request>` compares the quote with the
document; a quote that is not there makes the answer void and the request goes to the owner.

```
ANALYST_ANSWER: OWNER_DECISION
Питання: <plain language, no jargon>
Варіанти: <each option and the strongest case for it>
Порада: <which, and why>
Поправка: <the ready text of the line(s) to add or change, with numbers>
```

```
ANALYST_ANSWER: NOT_REQUIRED
Lines: <рядки, на які спирався запит>
Чому не вимагають: <...>
Найменша форма: <нічого не будувати — або одне речення>
```

When no standing line requires what the request is about. A non-goal is a boundary, not a
requirement; words marked `[не слова власника]` are by themselves no requirement. In doubt —
`OWNER_DECISION`, whose first question is whether the thing is needed at all — that doubt is about
the document's silence on what the owner wants. A doubt between the owner and the architect over
**how**, behind a two-way door, is not it: that is `NOT_REQUIRED` with the smallest form «вирішує
архітектор як two-way door» (§0) — and so is how the product looks or speaks, while it asks nothing
more of people. When a line pulls towards an option that asks more of people than the document does —
their time, an answer, a message they did not ask for, money, data about them — the choice is the
owner's, behind a two-way door too. When no line requires the thing at all, it stays `NOT_REQUIRED`
with the smallest form. `goals.py requests` shows it as its own outcome, `not-required`.

Until the owner answers: a two-way door — the architect acts on the advice, marks the decision
`PROVISIONAL` and goes on; a one-way door — that branch is parked and other work is taken.

## 8. Changing the approved document

The document is sealed (`goals.py seal`); a changed one is not in force. It changes only by the
owner's answer:

1. Write the whole new document to `.engine/goals/proposed.md`: the version raised by one, the
   changed lines, a line in «Зміни» (`- v<N>, <date> — <what and why>; request NNN`). Struck
   lines stay struck, numbers are never reused.
2. `python3 .claude/hooks/goals.py proposal` — it refuses an unlawful amendment and prints which
   decisions cite the changed lines.
3. Ask the owner. With the owner present: show the amendment; on approval the owner runs
   `python3 .claude/hooks/goals.py seal --owner-approved` in their own terminal after the text is
   in place. Without the owner: the question goes to `tasks/blocked/` with the line
   `python3 .claude/unattended/board.py action-line amend-goals` prints under it; the owner's
   «так» has the board runner apply and seal it. An agent never seals a changed document.
4. Every decision that cited a changed line is listed in `.engine/goals/to-review.md`; the
   architect rereads each and ticks it.

**The first seal without the owner.** A document written with nobody in the conversation (a task
from the board that carries the goals' text) is not sealed by the agent: `goals.py seal` refuses.
The question goes to `tasks/blocked/` — the whole document shown in it — with the line
`python3 .claude/unattended/board.py action-line seal-goals` prints under it (the sha256 of
`.engine/goals.md` itself); the owner's «так» has the board runner seal exactly that text. Until
then the document is not in force, and a change after the question needs a new question.

**The hand-off to the architect** (board 205). The first seal of a new project — no traceability
matrix, no map yet — starts the architecture without a command from the owner: in the conversation
`goals.py seal` prints `NEXT: /master-architect` and `/business-analyst` starts it in the same
session; on the board the runner puts `NNN-master-architect.md` with `Потрібна присутність власника:
так` into `todo/` after `seal-goals`. Only the start is automatic; an amendment starts nothing.

## 9. The owner's corrections are lessons

When the owner corrects the document on their own remark, not on an architect's request — "this
was not in the goals and should have been", "the principle is written wrongly" — the analyst
should have asked. Queue it: `python3 .claude/hooks/lesson_queue.py add --source analyst "<what
was not asked>"`. The owner's review decides whether it becomes a line of this file.

## 10. Before the seal — `preseal`

Before the owner sees the whole document for approval, the agent `business-analyst` reads it fresh,
in mode `preseal`, with the draft and the journal. It looks for: contradictions between lines (one
person with two roles included); words that are not the owner's standing without the mark, and
reasons in non-goals the owner did not give; lines chosen from the analyst's options or settled late,
each with its consequences (what must be built, what it asks of people); the owner's emphases in the
journal that reached no line; a core that is missing or not backed by the owner's words. Its answer
is lines `PRESEAL_FINDING: <вид> | <рядки> | <слова власника або пояснення> | <питання до власника>`
(kinds `contradiction`, `unmarked`, `risk-reason`, `consequence`, `late-choice`, `lost-emphasis`,
`no-core`) or `PRESEAL_CLEAN`. The question of every finding passes the check of §0; a finding whose
question fails it is no question. A consequence (`consequence`, `late-choice`) is told to the owner in
one line as information — what will have to be built, what it will ask of people; it is a question
only when it contradicts another line, crosses a non-goal or a constraint, or is a one-way door. With
nothing to ask, the question field is `—`. Every question is discussed with the owner — as many
questions as it takes, no limit. It decides nothing and changes nothing.

**The re-check after the owner's answers.** When `/business-analyst` has changed the draft by the
owner's answers to the findings and runs `preseal` again, it names the changed lines:
`preseal <draft> <journal> --changed <lines>`. The fresh agent checks only those changes: are the
owner's words written verbatim, does a changed line contradict another, do words the owner did not say
carry the mark. It does not look for the consequences of these answers: they are the owner's answers,
not choices made late.

## 11. During the architecture — `guardian`

The role was meant from the start for more than the first conversation: to watch that the agents do
not build technical machinery the product will never need. The master-architect starts the agent in
mode `guardian` at the stop «Читання цілей», at the end of every stage and after every amendment by
the owner, with the goals document, the journal, the traceability matrix and the stage's artifact.
For each line it asks: does the mechanism serve the goal as the owner meant it (the core, the
journal); is it the smallest form; is the core worked out in depth, not only a box on a diagram; is
there an element with no source, or one built around a non-goal; does a reading rest only on words
with the mark. A note that would need the owner passes the check of §0 first; a «how» it raises is
the architect's. BLOCKING only in two cases — a goal of the core has no mechanism that does what its
line says, or the design contradicts a written line; everything else is a note. The answer:
`GUARDIAN_BLOCK: …`, `GUARDIAN_NOTE: …`, or `GUARDIAN_PASS`.
