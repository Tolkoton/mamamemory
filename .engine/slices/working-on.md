# Slice working-on — F4 S1 (TRACER), driven by /feature-architect f4-recall-worklog — planning artifact

## Goal
Мама каже «зараз працюю над договором купівлі городу» — асистент записує це з часом під її акаунтом і відповідає
«Записала: …» (G4, AC1 F4). Вимірний сигнал: тести; smoke на справжній моделі — фрази «працюю над …» маршрутизуються в
`working_on`, а фрази smoke F2–F3 (задачі, нотатки, правки, «перекласти») — як були.

## Premise verified
- Маршрутизація (`assistant.handle_message`, `ROUTE_SCHEMA`, `route_schema`, `_route_prompt`, `ALWAYS`, `PHRASES`,
  `_dispatch`) і `Store.set/get/list` під акаунтом — у дереві (F1–F3, clarify).
- P-ROUTE-F4 (Flash-Lite відрізняє «працюю над» від нотатки й задачі) — `unverified`; smoke цього slice й повтор smoke мови
  F2–F3.

## Out of scope (deliberately)
- відповіді з журналу (S2), пригадування справи (S3), рядки гайду (S3);
- прив'язка запису до справи (рамка F4: немає — escalations 2026-11-11);
- редагування й видалення записів.

## Seam (contract)
- Новий модуль `cases/worklog.py` (частина `cases`): `WORK = "work"`; `add(session, text: str, entry_id: str, *, store,
  now: datetime) -> Reply` — записує документ `work/{entry_id}` `{text: <text без пробілів по краях>, at: now.isoformat()}` (рядок ISO з часовою зоною UTC — як
  усі часи в коді) під
  акаунтом і повертає `Reply("Записала: <text>.")` без питання; той самий `entry_id` удруге перезаписує той самий
  документ (повтор повідомлення застосунком — без дубля); жодного виклику моделі, Calendar, Tasks, справ.
- `assistant`: намір `working_on` у `ROUTE_SCHEMA` (enum), `ALWAYS`, `PHRASES["working_on"] = "записати, над чим
  працюєте"`; `_dispatch`: `working_on` → `cases.worklog.add(session, text, message_id or uuid4().hex, store=store,
  now=now)`; підказка маршрутизації: «working_on — мама каже, над чим зараз працює чи що робить («зараз працюю над …»,
  «я зараз роблю …», «сиджу над …»); це не нотатка про людину і не задача на потім».
- Does NOT do: відповідей з журналу, прив'язки до справи, гайду.

## Decisions (with WHY)
- Q1: Записувати фразу мами як є (без пробілів по краях), без виклику моделі. Чому: architecture-map «запис "працюю
  над" зберігається одразу з часом, без окремого виклику» (P1); відповідь із журналу (S2) читає фразу моделлю. Rejected:
  виділяти моделлю «над чим» — найсильніше за: коротший запис; але зайвий виклик на кожне «працюю над» і ризик
  спотворити.
- Q2: `entry_id` — `message_id` повідомлення (як `cases.add_note`). Чому: застосунок повторює повідомлення з тим самим
  `message_id` після обриву — без дубля. Rejected: новий id щоразу — дублі записів після повтору.

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: запис** — документ `accounts/{sub}/work/{id}` з текстом (вхід із пробілами по краях — збережено й
  повторено без них) і часом `now.isoformat()`; відповідь «Записала: …»; повтор з тим
  самим id — один документ; жоден фейк Calendar/Tasks/моделі не кликаний (крім маршрутизації).
- **Seam 2: маршрутизація** — `working_on` у схемі `route_schema` для кожного `reply_to` (без питання, під планом, під
  питанням справ) і в `allowed()` — тож `unsure` з options [`note`, `working_on`] дає уточнення з фразою
  «записати, над чим працюєте».

## Invariants (rules that hold for every input in the stated domain)
- **I1** — Намір `working_on` ніколи не пише в Calendar, Tasks чи справи і не кличе модель, крім маршрутизації; пише
  рівно один документ журналу на один `entry_id`.
  - Domain: будь-яка фраза, будь-який `reply_to` (немає, план, питання справ), будь-яка кількість повторів того самого
    повідомлення.
  - Source: AC1 F4 («нічого в Calendar чи Tasks, справ не створює»); Q2.
  - Broken by: запис нотатки «про всяк випадок»; новий документ на кожен повтор.

## Exit criterion
- `pytest` зелений: Seam 1–2, `test_I1_…`; усі запечатані тести зелені.
- Smoke `scripts/smoke_working_on.py` (Сонько): «зараз працюю над договором купівлі городу», «я зараз роблю звіт для
  податкової», «сиджу над аналізами пані Шмідт» → `working_on`; «запиши до пані Шмідт: аналізи в нормі» → `note`;
  «додай задачу подзвонити нотаріусу» → `new_task`; усі 5 з 5 (кожна фраза контракту, не поріг якості); і smoke мови
  F2–F3 ще раз — `smoke_several_tasks.py`, `smoke_time_limits.py`, `smoke_priorities.py`, `smoke_voice_edits.py`,
  `smoke_add_or_plan.py`, `smoke_note_to_case.py`, `smoke_case_questions.py`, `smoke_move_material.py`,
  `smoke_clarify.py`, `smoke_guide.py` (однозначні фрази не стають `working_on`).
- Розгортання — S4 F4.

## Deferred to later slices
- Відповідь із журналу — S2; пригадування справи й рядки гайду — S3.

## Open items requiring human decision (if any)
- (немає — рамка F4 у картці 739)

## Critic notes (non-blocking)
- Cold-reader: `add` дістає позиційний `entry_id` (Q2) — у договорі F4 доповнено; S2 залежить лише від документа.
