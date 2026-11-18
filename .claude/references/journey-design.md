# Journey design — the method of level J

Read by `/journey-architect` (whole, before the first question) and by `journey-critic`. The format
of the files is `journey-template.md`; the mechanics are `.claude/hooks/journeys.py`; the research
is `docs/research/2026-11-userflow/` (R1 for this level, R4 §1 for the core journey first, R0 for
the case that made it necessary).

## 1. Why this level exists

The goals (level 0) say what the owner wants and how they will see it worked. The architects cut
features by bounded contexts. Between the two nobody wrote what a person **does, sees and hears**,
step by step, and how every question the product asks **is left**. In mamamemory (R0) that gap
produced, within a week: buttons with no visible state («кнопки не працюють»), «додай задачу»
starting the week's planning because a feature's provisional AC said so, a question that never let
go of the conversation, and «що в мене сьогодні?» — the first thing anyone asks a calendar
assistant — deferred as an extra. Every one of them passed its tests: the tests checked what the
agent had invented.

So level J sits between `/business-analyst` and `/master-architect`: journeys are written with the
owner, one at a time, sealed like the goals, and the features are cut from them.

## 2. What a journey is (and is not)

Three different artifacts (NN/g): a *journey map* is discovery (emotions, phases, opportunities); a
*story map* is planning (steps → features by release); a *user flow* is minutes of one person in
one product, checked by a usability test. Level J is **the flow, with the conversation**, plus the
story map that orders them. Not a marketing journey map.

- **One journey = one persona, one trigger, one key use** (Google: «one persona, one key use case»).
- **The story map** (`INDEX.md`, Patton): the journeys left to right in the order of the person's day,
  their steps under them, a goals line for each. The **core journey** — without it the core goal of
  `.engine/goals.md` does not work — is built first: the walking skeleton is the core journey walked
  end to end, thin implementations of every step (R4 §1), not a chain of layers.
- **Must-be expectations** (Kano): what a person expects of a product of this kind without saying it
  («що в мене сьогодні?» for a calendar assistant; undo for an editor; «where is my order» for a
  shop). Each one has its journey or is a non-goal with the owner's answer. You and the critic
  propose; the owner decides.

## 3. Writing one journey

1. **Who, when, why** — `Persona:` (pace, hands, eyes, voice, what tires them), `Тригер:`, `Цілі:` (the
   G/D lines it serves).
2. **Sample dialog** (Google, Amazon): the happy path in living words, turn by turn — what the person
   does or says, what they see and hear, the state. At most two options per turn. Act it out loud
   before showing it.
3. **States** (UI stack, Hurff): for every screen — ideal, empty/first-run, loading/processing,
   partial, error; for a conversation also listening, question, no-input, no-match, offline. For
   each: what is on the screen, what is said, how to leave it. Errors in human words, not technical.
4. **Extensions** (Cockburn): the main path has no «if»; every step that can fail gets numbered
   extensions — `3a` the person is silent, `3b` says something else while a question is pending,
   `3c` changed their mind, stop. Each ends: back to a step, a separate success, or an exit with an
   explanation. «Says something else» is the one forgotten in mamamemory.
5. **Acceptance** (Given/When/Then, Fowler; Cucumber's test «will this wording change if the
   implementation does?»): declarative, `Then` only what the person sees or hears. These lines become
   the features' acceptance criteria **verbatim**: a feature cites `J-N#AC-k`.
6. **A picture for the owner**: 3–6 phone screens in ASCII or plain HTML, and a Mermaid
   `stateDiagram-v2` for the agents (wireflow, NN/g).
7. **Open** — thresholds the owner has not named («how many items to read aloud») go here, never into
   code.

## 4. Conversation rules (VUI)

- A question is never left without a way out: silence, something else, stop (Amazon: «ensure the
  conversation won't reach a dead end»; stop and cancel in every skill, without a needless
  confirmation).
- Reprompt short, then with an example; after two no-input / no-match — a graceful exit (Google).
- Repair is a state of its own: older users' repairs are rarely caught by assistants (Mahmood et al.,
  arXiv 2403.02421), so «перепитати» is designed, not hoped for.
- **Interference** (`interference.md`): for every pending question of every journey — what wins when
  a typical phrase of another journey arrives. A conversational product without this matrix lets
  one journey's question swallow another journey's phrase.
- One form of address, one control per action.

## 5. What the critic checks, what the script checks

`journeys.py check` (mechanical, no LLM — cross-screen defects are exactly what an LLM reviewer
misses: arXiv 2507.02306, 2506.16345): every state has an exit, every exit lands; every `question`
has exits for silence, something else and stop; every extension ends; every step is covered by an
AC; every AC has Given/When/Then; every journey cites a standing goals line; every must-be has a
journey or a non-goal; every pending question has its interference row.

`journey-critic` (blind, read-only): dead ends the graph cannot see; a question whose exits exist on
paper but do nothing a person would accept; the completeness of the states; Nielsen #1 (visibility of
system status), #3 (user control and freedom), #4 (consistency), #9 (recover from errors), each with
the step quoted; must-be expectations missing; the persona's pace — repair, at most two options per
turn; duplicate controls, mixed forms of address; a `Then` that describes the implementation.

## 6. With the owner, and without

The owner approves **one journey at a time**: the sample dialog and the screens, not a specification
(fatigue makes «так» without looking). Show them with the open decisions numbered; the answer that
closes the last of them is the approval (board 210): «Записав так: …» and the seal in the same message,
`journeys.py seal <unit> --answer «<the owner's words>»`, no second «так». One clarifying question only
when the answer leaves something open or is «так, але…».

Unattended nothing is sealed and nothing is built on a draft: a journey is a product decision
(Article 5), and the owner answered for this case (board 208): «Чи може runner будувати функції з
екранами чи розмовою без затверджених вами сценаріїв?» — «Ні, паркує». The draft is written, the
critic runs, and the question goes to the board with the journey shown and
`board.py action-line seal-journey <unit>` under it. The owner's «так» has the runner seal it.
Technical work that touches no screen and no conversation goes on as before.

**The owner's walk-through depends on the stage** (`.claude/project-stage`; the owner's answer, board
208, «За стадією»): at `internal` the E2E and the walking agent are enough, and the owner walks only the
core journey, when it changes; at `production` the owner walks every change people see. (The E2E and
the walking agent are separate tasks of the same package.)

## 7. Changing a journey

A sealed journey changes only by the owner's word: edit it, raise `Версія:`, add a line to «Зміни»,
show the change, ask with `seal-journey`. AC numbers are permanent — a criterion that no longer holds is
struck through (`- ~~AC-2 …~~`), never removed. `amend` lists every feature that cited a changed AC in
`.engine/journeys/to-review.md`; the architect rereads them. A complaint about a step that a journey
has is a `/bugfix`; a complaint about a step no journey has is a change of the journey first.
