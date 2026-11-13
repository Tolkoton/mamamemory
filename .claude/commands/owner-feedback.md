---
description: Take the owner's feedback at the level of the journey and the class, not one phrase. Splits the owner's words (verbatim) into observations, binds each to a journey and a step — or, when no journey has the step, makes it a question to the owner — names the class of the defect, checks every state of the inventory for the same defect, changes the journey first, writes one test over the whole class, puts the phrase into the corpus, fixes, and asks for a new walk. `feedback.py check` holds the record. Use when the owner's answer under a walk card is anything but «так», and whenever the owner says a step of a journey behaves wrongly.
---

You are running **/owner-feedback**. `$ARGUMENTS` is the owner's feedback — the board task whose answer
it is (an answer under a walk card `owner_walk.py walk-card`, anything but «так»), or the words themselves.

WHY (board 412; `docs/research/2026-11-userflow/R4-flow-first-process.md` §3.3). mamamemory, 11.11 18:45:
«Я сказав, які в нас плани на сьогодні? А воно подумало і сказало. Скільки часу це займає?». The fix closed
the question of duration; on 12.11 the questions of the week's plan caught the owner's phrase the same way. A
complaint patched as a phrase comes back. Here it is taken as a class, over every state, journey first.

Obey `.claude/constitution.md`. Speak the owner's language; write the record in the language of the
project's documents; technical terms stay English.

## 1. The quote and the observations

Copy the owner's words **verbatim**, with the date and where they were said. Split them into observations —
one thing that went wrong each. Every observation gets its own record: `.claude/templates/feedback-record.md`
→ `.engine/feedback/NNN-<name>.md` (the next free three-digit number), the same `Цитата:` in each.

## 2. The journey and the step

For each observation: which journey (`.engine/journeys/J-N-*.md`) and which step of its sample dialog. A
step no journey has is the class **«відсутній J»**: behaviour nobody wrote down is a product decision
(Article 5). Put the question to the owner (`board.py open-item --to blocked`: what they said, the journey it
would go into, options with your advice), name it in `Питання власникові:`, and nothing else is done for that
observation — no slice, no code.

## 3. The class

One of: стан, перехід, вихід, відсутній J, текст, поріг, дубль, модель (the conversation model, not the
journey, is wrong). Severity by NN/g, 0–4: frequency, impact, persistence.

## 4. The same places — every state, not the one where it showed

The table «Ті самі місця» lists every state `J-N S-k` of every journey — or every state of one kind, named in
`Обсяг:` (a pending question is `question`) — each «так» or «ні» with its evidence: a line of code, a test, a
step. «питання висить і ловить наступну фразу» is checked for every pending question, not for duration only.

## 5. The journey first

Unless the class is «модель», change the journey (its states, exits, Given/When/Then) before any code, and
raise its version (`J до:` keeps the old one). A change that brings **new visible behaviour** goes to the
owner for the seal: `board.py action-line seal-journey j-N` under a question (`/journey-architect`). Restoring
behaviour the journey already had needs no ratification — the fix brings the code back to the sealed journey.

## 6. One test on the class, the phrase in the corpus

`Тест:` — one test, parametrised over every state answered «так». With a conversation model
(`.engine/architecture/conversation-model.json`), the owner's phrase goes into the regression corpus for
ever (`tests/conversations/complaints.json`, board 209) and `Корпус:` names its id.

## 7. The fix, then a new walk

Fix the class (`/bugfix` discipline: the test red first, the smallest change). Then
`python3 .claude/hooks/owner_walk.py walk-card j-N --feedback .engine/feedback/NNN-<name>.md` — a new card
for the new revision of the journey; the next feature waits for it (`owner_walk.py gate`).

## 8. The check

```bash
python3 .claude/hooks/feedback.py check .engine/feedback/NNN-<name>.md
```

Exit 0 is the record standing. Exit 3 lists what is missing — a state not looked at, a journey not changed
first, a test that misses a state, no new card: do it, never edit the check's output away.
