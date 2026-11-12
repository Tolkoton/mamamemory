# PROGRESS

## Slice S1 — access-shell (CODE COMPLETE — SMOKE PENDING, 2026-11-05)

- Module: `src/mamamemory/` — config, errors, access, integrations/store, integrations/google_auth, http/app, main, web (~520 LOC)
- Tests: 41 contract tests (slice-tester, sealed, 8 files), all green; ruff, mypy strict clean
- Smoke: PARKED — see tasks/blocked/701-open-item-f1-oauth-client.md (клієнт OAuth у Cloud Console і мамина адреса — лише власник); `scripts/smoke_access_shell.py <BASE_URL>` після розгортання Соньком
- Surprises: oauthlib на неповні scopes кидає `Warning` (перехоплено в `exchange`); venv на Python 3.13, google-auth-oauthlib 1.5.0 / oauthlib 4.0.1 — поведінку перевірено тестувальником
- Open for next slice: `store.transact` — S3; «увійди знову» — S4

## Slice S3 — one-task-to-calendar (CODE COMPLETE — DEPLOY PENDING, 2026-11-06)

- Modules: src/mamamemory/planning/{__init__,placement,plan}.py, assistant.py, replies.py,
  integrations/{google_work,ai}.py, store.transact, http `/api/message`, `/api/plan/confirm`, web/{app,reply_to}.js
- Tests: 46 contract tests of the independent tester (sealed), 100 in all green; `node --test` of reply_to.js green
- Smoke / tracer: PARKED — needs the OAuth client and mama's address (tasks/blocked/701)
- Surprises: `node --test src/mamamemory/web/` (exit criterion) fails on Node 24 for a directory — run the file
  `node --test src/mamamemory/web/*.test.js` (tester's Q9)
- Open for next slice: route-model schema is the builder's (`{intent: yes|new_task|other}`, untested — Q6)

## Slice S2 — voice-to-text (CODE COMPLETE — DEPLOY PENDING, 2026-11-06)

- Modules: integrations/ai.speech, http `/api/transcribe` (raw body streamed into memory up to the limit),
  errors.AudioRejected, config.language / max_audio_bytes, web/voice_state.js, mic + send buttons in app.js
- Tests: 28 contract tests of the independent tester (sealed); 121 pytest + 8 node tests green
- Smoke: PARKED with S1/S3 deploy (tasks/blocked/701); real voice and webm — S5
- Open: Q5 (reply_to after assistant_reply) — the builder takes `reply.question`; untested

## Slice open-sign-in (CODE COMPLETE — DEPLOY PENDING, 2026-11-06)

- Goals v4 (G6, C10; ADR-0007): any Google account signs in, its own space; allowlist, `email_verified` check,
  `NotAllowed` and 403 removed; `ALLOWED_EMAILS` is no longer read (Sonko drops it from the service env)
- Tests: 10 contract tests of the independent tester (sealed) + S1–S3 tests rewritten by the tester on the owner's
  word (escalations.md, OWNER 2026-11-06); 125 pytest + 14 node green
- Seals: access-shell and one-task-to-calendar show CHANGED for the files the tester rewrote with the owner's word —
  no engine command re-seals them yet (engine task 310, item 4)
- Smoke: two-account check on the deployed address, by people, after board 701

## Slice S4 — open-questions (CODE COMPLETE — DEPLOY PENDING, 2026-11-06)

- `planning.open_question` (lazy calendar; asking-duration without Google; LoginExpired → «увійди знову»),
  `assistant.open_questions` (a failed source is skipped and named), `GET /api/open`, `web/open_questions.js`,
  app.js asks `/api/open` on load
- Tests: 37 contract tests of the independent tester (sealed; one objection round — monkeypatch instead of
  type-ignore); 162 pytest + 19 node green; browser check: plan → reload → same plan → «так» → written
- Also: visible voice state (big buttons, red mic, «Слухаю…», «Розпізнаю…»), owner's first login 2026-11-06

## Slice F2 S1 — several-tasks (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00006-kzg], real-model smoke 5/5 [2026-11-06])
## Slice F2 S2 — time-limits (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00010-zn6], real-model smoke 5/5 [2026-11-06])
- Limits asked on the first planning («Коли ви взагалі можете робити задачі?»), then «Як минулого разу — …?»;
  free tasks only within the days and hours; a named time or day wins; `Config.ask_limits` (load_config → True)
- Tests: 33 contract tests of the independent tester (sealed) + all earlier sealed; 230 pytest, 19 node green
- Tracer on the phone with the owner pending (several tasks + limits)
## Slice F2 S3 — priorities (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00011-7md], real-model smoke 5/5 [2026-11-07])
- «Що з цього найважливіше?» with a numbered list when two or more tasks; the answer reorders (named first,
  the rest after), «все однаково»/«не знаю» keep the order; `Config.ask_priorities` (load_config → True)
- Tests: 20 contract tests of the independent tester (sealed; one objection — duration text per several-tasks Q1)
## Slice F2 S4 — google-tasks (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00012-gdm] [2026-11-07])
- Open Google Tasks join a new plan as untimed; «Назвіть і ті, що поставити на час» in the priorities question; chosen
  ones get a duration, become events and are closed in Tasks; mama's untimed and not-fitted tasks go to Tasks on «так»;
  events → closings → new tasks, each recorded; an interruption on the Tasks step finishes on the next «так» without a
  new show; step 0 closes after a broken write; `Config.use_tasks` (load_config → True)
- Tests: 35 contract tests of the independent tester (sealed; one objection — priorities re-ask after an append);
  288 pytest + 19 node green; priorities smoke with the new `timed` field 5/5
- Smoke with real Google Tasks — the owner on the phone
## Slice F2 S5 — voice-edits (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00014-4f9], real-model smoke 13/13 [2026-11-07])
- Mama changes a shown plan by voice: route `edit` on a plan reply → `planning.edit_plan`; `parse_edit` (Flash-Lite)
  gives task number + kind: move (day or named time), not_before (every day, with limits and day), remove (nowhere,
  not in Tasks), untimed; an unreadable edit keeps the plan and its fingerprint; a timed task without a duration is
  asked first; removing the last task → «План порожній — нічого записувати.»; transitions refuse a fresh write
- Tests: 26 contract tests of the independent tester (sealed, Q1–Q3 taken, no objections); 314 pytest green
- Smoke runs: 10/13, 12/13 (the route mistook short edits for new tasks) → the route prompt now lists the shown
  plan's titles (`planning.shown_titles`) → 13/13; access smoke on the deployed revision green
- On the phone (owner): «перенеси … на четвер» under a shown plan changes the plan
## Slice F2 S6 — f2-measure (DONE — MEASURED [2026-11-07])
- Deployed rev mamamemory-00014-4f9; P-PARSE on ten new phrases 9/10 (docs/f2-measure.md); two known weaknesses
  («зранку/ввечері» get an invented hour; a greeting on a named day loses the day) → proposed 722
- Owner's phone walkthrough: tasks/blocked/721
## Slice F3 S1 — note-to-case (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00015-lwp], real-model smoke 8/8 [2026-11-07])
- A note by voice or text goes to the case the Розкладач (3.8 Flash, numbered catalogue) names: «Поклала в «X».»;
  no such case → «Створити справу «X»?» → «так» (button `/api/case/confirm` or word) creates it; the material is
  written before any model call, `message_id` from the client, a repeat finishes the sorting or the description
- Tests: 45 contract tests of the independent tester (sealed; Q1–Q4 taken), 3 node tests of `message.js`;
  361 pytest + 22 node green; voice-edits smoke re-run 13/13 after the route prompt change
- P-CASES measured: 48 of 48 on 48 look-alike cases, 3.3 s per call
- On the phone (owner): «запиши до пані Шмідт: HbA1c 7,2» → «так» → second note lands without a question
## Slice F3 S2 — photo-and-file (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00016-96q], real bucket smoke 4/4 [2026-11-07])
- Camera photo or a file (png, jpeg, webp, heic/heif, pdf, txt) through «+» → original in Cloud Storage under the
  account (`{account}/{material}`), text by Flash-Lite `read_file` from `gs://` (txt — as is), then the Розкладач of S1;
  other types and over 20 MB refused in words without a write; a repeat (with the body or header only) finishes
  without a new upload; a note's id as the file id → `"{id}-file"`
- Tests: 47 contract tests of the independent tester (sealed; Q1–Q3 taken), 3 node tests of `upload.js`;
  416 pytest + 25 node green; `google-cloud-storage` added (uv)
- P-GCS verified: PDF and the PoC photo read by Flash-Lite via `gs://` from europe-west3; PDF text → «пані Шмідт»
- On the phone (owner): photo of a lab form lands in its case
## Slice F3 S3 — case-questions (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00017-zvm], real-model smoke 10/10 [2026-11-07])
- «ні» on «Створити справу «X»?» → «У яку справу покласти?»; a case name (in any case form) → that case; a new name →
  «Створити справу «Y»?»; «не треба» → «Гаразд, лишила без справи.», nothing deleted; on opening one newest question of
  all modules (plan by `asked_at`, not the re-show) with «Ще N питання чекають.»; plan replies without a question first
- Tests: 39 contract tests of the independent tester (sealed; Q1–Q2 taken); 457 pytest + 25 node green
- Smoke runs: S3 10/10; voice-edits 12/13 on the first run («ну не знаю» → `no`) → route prompt says the case intents
  exist only under a case question → all three smokes passed; S1 smoke 10/10, voice-edits 13/13
- Also: a .txt file's text is written with its material (overseer test gap of S2)
- On the phone (owner): «ні» → «У яку справу покласти?» → «до Коха» → «Поклала в «пан Кох».»
## Slice F3 S4 — move-material (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00018-9s6], real-model smoke 8/8 [2026-11-07])
- «переклади …» about any material (not only the last): 3.8 Flash `choose_material` picks the material and the case;
  the destination's description gets the material, the source's is rebuilt from its remaining texts only (`fresh`);
  a new name → «Створити справу «X»?» (no case without «так»); a break leaves `stale` / undescribed and the next
  move finishes it
- Tests: 31 contract tests of the independent tester (sealed; Q1–Q2 taken); 488 pytest + 25 node green
- Smoke runs: first 6/7 («ну не знаю» under a plan → `no` again) → the route schema itself drops the case intents
  outside a case question (`assistant.route_schema`) → all 7 language smokes green (S4, S3, S1, edits, several-tasks,
  priorities, time-limits); P-DESC verified (a fresh description holds no fact of the moved material)
- On the phone (owner): «переклади аналіз пані Шмідт до пана Шмітта» moves it
## Slice F3 S5 — f3-measure (DONE — MEASURED [2026-11-07])
- Deployed rev mamamemory-00018-9s6; ten new phrases 8/10 (docs/f3-measure.md): «пан Вольф просив виписати рецепт …» →
  new_task; «ні, це не нова, це до Бергер» under a case question → edit — proposed 728; premises statuses as in the log
- Tests: 10 contract tests of the independent tester on the report (sealed; Q1 taken)
- Owner's phone walkthrough: tasks/blocked/729; F3 frame ratification: tasks/blocked/723
## F3 cases-intake — FEATURE COMPLETE (2026-11-07)
- 7 integration tests of the independent tester on AC1–AC6 and «повтор без дубля», all green over the real routes;
  feature-close passes; frame ratified by the owner; phone walkthrough — tasks/blocked/729
## Slice F2 amendment — add-or-plan (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00020-6wv], real-model smoke 8/8 [2026-11-07])
- Owner, after the phone: «додай таску» pulled all Google Tasks and asked «що найважливіше» → «міняй поведінку, це
  неправильно». Now `new_task` → `planning.start(week=False)`: only the spoken tasks, no Tasks, no priorities, saved
  limits applied silently (asked only when none are saved); `plan_week` («сплануй тиждень») → as F2, also with no task
  spoken; `week=None` keeps the sealed F2 behaviour
- Tests: 22 contract tests of the independent tester (sealed; Q1–Q5 taken; one objection — the test was wrong);
  529 pytest + 25 node green; all 8 language smokes green on the real model
- On the phone (owner): «додай задачу подзвонити нотаріусу в понеділок на пів години» → «Пропоную: … Записати?»
## Slice F2 fix — stuck-question (DONE — CODE COMPLETE, DEPLOYED [rev mamamemory-00022-zbp], all 8 language smokes green [2026-11-11])
- Owner on the phone: «Скільки часу це займе?» on opening with no context, and every phrase gave it again. Now: the
  duration question always names the task; `try_answer_*` — a phrase that is no answer goes to the route (a new task or
  «сплануй тиждень» starts a fresh draft, `replace_asking`); an asking draft older than 24 h is not shown and not added to
- Tests: 32 contract tests of the independent tester (sealed; Q1–Q5 taken); 8 old sealed tests of 6 slices rewritten by
  supersede rulings (3 more stood as right); 561 pytest + 25 node green
- Follow-up after the audit: a reply to a question older than 24 h is no answer either (`_too_old_to_answer`); the
  request «що в мене на цей тиждень?» returned as a task is dropped (smoke 7/8 → 8/8); 564 pytest + 25 node green
- Follow-up 2 (overseer gap): the request «сплануй тиждень» is only a phrase of request and period words — real tasks
  with «запланувати» are kept; smoke_add_or_plan 8/8; DEPLOYED rev mamamemory-00023-trw
## Clarify (owner's word 2026-11-07, replaces card 728) — CODE COMPLETE, DEPLOYED (rev mamamemory-00024-tnq), all 9 language smokes green (2026-11-11)
- An ambiguous phrase → «Не зовсім зрозуміла: A чи B?» with two buttons (`/api/clarify`) or a spoken choice
  (`choose_option`); the saved text runs as the chosen intent once; a phrase that is no choice is routed as new; the app
  resets `reply_to` after a reply without a question (M3)
- Tests: 25 contract tests of the independent tester (sealed; Q1–Q5 taken), 2 node tests; 590 pytest + 27 node green
- First run 1/3 clarify + edits 12/13 → the route prompt names the cases («пан X просив …» → unsure; «ну не знаю» →
  other; «це не нова, це до X» → case_name) → all 9 green on the second run
## Slice F5 S1 — language-setting (DONE — CODE COMPLETE, deploy with S4 [2026-11-11])
- `access.language(session, store)`: `settings/profile.language` from `LANGUAGES` (only `uk`), else `uk`, also on a read
  error; `/api/transcribe` passes it to `speech` (read off the event loop) instead of `config.language`
- Tests: 11 contract tests of the independent tester (sealed; Q1 taken); 601 pytest green
## Slice F5 S2 — guide (DONE — CODE COMPLETE, deploy with S3 in S4 [2026-11-11])
- The guide (7 short lines) on the first opening after F5 (`settings/guide_shown`, first among plain items, never in the
  question's place) and on «що ти вмієш?» (intent `help`); the reply to `other` is now «Не зрозуміла. Скажіть «що ти
  вмієш?» — розкажу.»
- Tests: 18 contract tests of the independent tester (sealed; Q1–Q3 taken); 26 old sealed tests of 6 slices rewritten
  by supersede rulings; 619 pytest + 27 node green; all 10 language smokes green on the real model (no deploy yet)

## Slice F5 S3 — read-aloud (DONE 2026-11-11)

- Module: `src/mamamemory/integrations/tts.py` (`parts`, `Speaker.say`), `POST /api/speak {text, part}` → audio/ogg
  + `X-Parts`, `web/speak.js` (черга частин) і кнопка 🔊 у `app.js`; залежність `google-cloud-texttospeech`.
- Tests: 42 контрактні (незалежний tester, 8 питань — усі `taken`); усього 655 pytest + 33 node — зелені.
- Smoke: passed — `scripts/smoke_read_aloud.py` (Сонько, 2026-11-11 22:13 UTC): 8/8 частин, 3,5–5,1 с кожна.
- Surprises: P-TTS-LONG спростовано (350 знаків — 10,3 с; 700+ — 503 через 60 с) → частини ≤100 знаків (150 — 2 з 5
  понад 10 с); middleware тепер `setdefault` для `Cache-Control`, щоб `/api/speak` ніс `no-store`.
- Open for next slice: викладка (S4) разом з гайдом; межа 1 500 — картка 734.

## Slice F5 S4 — f5-measure (DONE 2026-11-11)

- Module: `web/player.js` (`makePlay(Audio, URL)`), `speak.js` — FAILED на відхилене програвання й нечинний `X-Parts`
  (картки 735, 736); `scripts/smoke_f5_deployed.py`; п'ята фраза `smoke_guide.py`; звіт `docs/f5-measure.md`.
- Tests: 18 контрактних (незалежний tester; Q1, Q2 — `taken`); усього 663 pytest + 43 node — зелені.
- Smoke: ревізія `mamamemory-00025-kgg`; smoke_guide 5/5, smoke_read_aloud 8/8, smoke_access_shell 13/13,
  smoke_f5_deployed 3/3 (після поправки — скрипти без сесії дають 302, не 200; escalations 2026-11-11).
- Surprises: Сонькові заборонено impersonation сервісного акаунта — P-TTS-SA лишається `unverified` до проходу 737.
- Open for next slice: прохід на телефоні (картка 737); межа 1 500 і текст гайду (картка 734).

## Slice F1 S5 — skeleton-measure (DONE 2026-11-11)

- Module: `scripts/measure_f1.py` (виробничий `speech` на 10 синтезованих записах PoC 2); звіт `docs/f1-measure.md`.
- Tests: 28 контрактних (незалежний tester; Q1, Q2 — `taken`).
- Measure (Сонько, `~/sonko/done/2026-11-11-mamamemory-f1-measure.md`): P-COLD холодна 8,2 с / тепла 0,77 с після 24 хв
  простою; розпізнавання 20 з 29 ключових слів, 1,65 / 5,53 / 34,95 с, 10 з 10 викликів.
- Surprises: один виклик 34,95 с (повтор усередині `speech`?) — у застосунку дав би «Не вдалося…».
- Open: картка 738 (мамині фрази й вхід); оцінка 8,2 с холодного старту — власник.

## F1 skeleton — FEATURE COMPLETE (2026-11-11); AC5 «5–10 справжніх маминих фраз» — картка 738
## F5 guide-voice — FEATURE COMPLETE (2026-11-11), rev mamamemory-00025-kgg; телефон — картка 737

## Slice F4 S1 — working-on (DONE — code complete, deploy with F4 S4, 2026-11-12)

- Module: `src/mamamemory/cases/worklog.py` (`add`: `work/{entry_id}` `{text, at}` без моделі); намір `working_on`
  у маршрутизації (`ROUTE_SCHEMA`, `ALWAYS`, `PHRASES`, `_dispatch`, підказка).
- Tests: 19 контрактних (незалежний tester; Q1–Q4 — `taken`); supersede одного тесту clarify (`allowed()`); 725 pytest.
- Smoke: Сонько (`~/sonko/done/2026-11-11-mamamemory-working-on-smoke-2.md`): `smoke_working_on.py` 5/5 і всі 10 smoke
  мови; `smoke_voice_edits.py` 3 з 3.
- Surprises: нова підказка зсунула «лікар о десятій у середу» під планом у `yes` (3 з 4 прогонів) — опис `yes` уточнено
  («лише згода без змін; задача плану з часом — edit»).
- Open: відповідь «Записала: …..» з подвійною крапкою, коли фраза кінчається крапкою (Q1, буквальне читання контракту).
