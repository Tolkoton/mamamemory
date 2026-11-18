# Калібрування user-walker-а — стан задачі 760

Записано агентом 2026-11-15 (задача 760, сесія без нагляду). Що зроблено, що чекає і як продовжити.

## Зроблено
- Крок 1. `.claude/references/walker-calibration.json` є, `goal` у кожному з п'яти випадків — двигун оновлено.
- Крок 2. Персона — `.engine/personas/mama.md`, чернетка; рядок «Затверджено власником: …» чекає власника
  (питання в `tasks/blocked/760-walker-calibration.md`).
- Крок 3. Чотири вади — чотири patch-і від commit-у `6d42b45` (`unattended/work`), кожен повертає рівно одну ваду R0:

| Випадок | Patch | Що змінює | Тести на HEAD + patch |
|---|---|---|---|
| `a1-no-reaction` | `a1-no-reaction.patch` | `render()` у `src/mamamemory/web/app.js`: без підпису «Слухаю…», без червоного 🎤, ➤ завжди ввімкнена (без запису нічого не робить) | 951 passed: `render()` тестами не покрито — саме вада A.1 |
| `a2-task-starts-week` | `a2-task-starts-week.patch` | `_dispatch` у `src/mamamemory/assistant.py`: `new_task` іде в `planning.start(week=True)` | 8 failed (`test_add_or_plan.py::test_seam3_new_task_routes_to_add_and_reads_no_tasks` та інші) |
| `a45-stuck-question` | `a45-stuck-question.patch` | `handle_message`: фраза, що не є відповіддю на коротке питання плану, отримує те саме питання знову (`planning._repeat`) | 16 failed (`test_stuck_question.py::test_seam1_new_task_under_the_duration_question_…` та інші) |
| `a8-duplicate-control` | `a8-duplicate-control.patch` | `index.html` + `app.js`: друга кнопка 📷 з власним полем файлу, робить те саме, що ＋ | 1 failed (`test_one_add_button.py::test_the_only_file_field_is_add_input_…`) |

Чистий HEAD: 951 passed (pytest без двох `test_f1_measure_script*.py`: їм потрібні аудіофайли PoC, яких у git немає)
і всі `src/mamamemory/web/*.test.js` під `node --test` зелені. Перевірка: `git apply --check .engine/calibration/<випадок>.patch`.

## Чекає
- ~~Власник: затвердити персону~~ — затверджено 2026-11-18 (рядок у `.engine/personas/mama.md`).
- Оператор: Playwright MCP 0.0.85 і Chromium — перевірено; `WALKER_TTS` — у `.claude/project.env` (2026-11-18).
- Оператор: п'ять ревізій без трафіку — запит `~/sonko/requests/2026-11-18-mamamemory-card-761-deploy.request.md`,
  відповідь буде в `~/sonko/done/` під тією ж назвою (адреси випадків — звідти).
- Власник: чий Google-акаунт для файлу входу (питання 2 у `tasks/blocked/760-walker-calibration.md`), потім його
  ручний вхід — без файлу входу прогони не починаються.

## Як продовжити (кроки 5–7)
Мету й бюджет кожного випадку треба передавати явно. `walker.py` (`journey_goal`) бере мету з будь-якого
`.engine/journeys/J-1-*.md`, запечатаного чи ні, і `goal` випадку тоді не діє. А 2026-11-15 у робочому дереві вже
лежить незакомічена чернетка `J-1-shcho-v-mene.md` («Що в мене є») від іншої сесії. Без `--goal` усі п'ять випадків
отримали б мету J-1. Тож для кожного випадку:

```
python3 .claude/hooks/walker.py request j-1 --persona mama --url <адреса випадку> --calibration <випадок> \
  --goal "<goal цього випадку з .claude/references/walker-calibration.json>" --budget 12 --voice --storage-state <файл входу>
```

Далі тричі агент `user-walker` рівно тим рядком, який показує `walker.py status`. Перед кожною групою —
`python3 .claude/unattended/board.py extra-allowed`. Потім `python3 .claude/hooks/walker.py calibrate`. Закомітити
`.engine/walks/`. Видалити тестові записи walker-а з календаря власника. Попросити оператора прибрати ревізії.
