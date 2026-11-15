# 760 — Калібрування user-walker-а на mamamemory

Залежить від: —
Аудит потрібен: ні

## Що сталося
Власник 2026-11-13 вибрав варіант (а) у задачі двигуна 1789: калібрувати агента-«користувача» (user-walker)
на mamamemory. Дослівно (сесія двигуна engine-27): «Ну, давай зробимо калібрування на Mama Memory».
Поки калібрування не пройде, walker вимкнений: `python3 .claude/hooks/walker.py status` → `off`.
Як проходить калібрування — `/home/lao/engine/evals/walker/README.md`; випадки — `.claude/references/walker-calibration.json`
(приходить з оновленням двигуна, задача 1789). Вади — з `/home/lao/engine/docs/research/2026-11-userflow/R0-mamamemory-analysis.md`
(A.1, A.2, A.4/A.5, A.8).

## Що зробити
1. **Перевір, що двигун уже оновлено.** Має бути файл `.claude/references/walker-calibration.json` з полем `goal`
   у кожному випадку. Немає — задача чекає оновлення двигуна (реліз — команда власника): `blocked/` з цим рядком, без інших дій.
2. **Персона.** Напиши `.engine/personas/mama.md` за шаблоном `.claude/templates/persona.md`, з дослівних слів
   власника з відгуків (з датами). Затверджує власник: питання в `blocked/` з повним текстом персони. Без рядка
   «Затверджено власником: …» `walker.py request` відмовляє.
3. **Чотири ревізії з вадами.** Від поточного `main` — чотири гілки, у кожній повернуто рівно одну ваду з R0:
   `calibration/a1-no-reaction` (запис не дає видимої реакції; «➤» без запису нічого не робить),
   `calibration/a2-task-starts-week` («додай задачу» запускає планування тижня),
   `calibration/a45-stuck-question` (відкрите питання забирає наступну фразу, «Скільки часу це займе?»),
   `calibration/a8-duplicate-control` (📷 і ＋ роблять одне й те саме). Чиста ревізія — сам `main`.
   Гілки ніколи не зливаються в `main`. Тести на гілках з вадою можуть падати — це очікувано; на `main` нічого не змінюється.
4. **Запит операторові** (через `board.py open-item --to blocked`, оператор діє за словом власника): (а) встановити
   `@playwright/mcp@0.0.85` і Chromium тієї версії Playwright, яку він тягне; (б) викласти п'ять ревізій як окремі
   ревізії без трафіку (`--no-traffic --tag <випадок>`), щоб 100% трафіку власника лишилися на поточній ревізії, і
   повернути адресу кожної; якщо Google-вхід на адресі тегу не працює (OAuth redirect), — окремим сервісом;
   (в) зняти файл входу (Playwright storage state) Google-акаунта власника на цих адресах — рішення власника 2026-11-12
   «пиши в мій календар»; файл лежить поза git; (г) `WALKER_TTS` у `.claude/project.env` — рядок із
   `/home/lao/engine/tasks/done/318-user-walker/report.md` (gtts-cli -l uk + ffmpeg).
5. **Прогони.** Для кожного з п'яти випадків (`a1-no-reaction`, `a2-task-starts-week`, `a45-stuck-question`,
   `a8-duplicate-control`, `clean`):
   `python3 .claude/hooks/walker.py request j-1 --persona mama --url <адреса цього випадку> --calibration <випадок> --voice --storage-state <файл входу>`,
   далі агент `user-walker` тричі, кожного разу рівно тим рядком, який показує `walker.py status`. Journeys
   у mamamemory немає — walker отримає мету самого випадку (`goal`) і бюджет `budget`. 15 прогонів, орієнтовно
   $15–75, у межах тижневої суми (`board.py extra-allowed` перед кожною групою).
6. `python3 .claude/hooks/walker.py calibrate` — пише `.engine/walks/calibration.json`. Закоміть його і звіти `.engine/walks/`.
7. **Прибрати.** Тестові записи walker-а в календарі власника — видалити (перелік: що створено в часі прогонів);
   ревізії без трафіку — оператор прибирає за запитом.

## Готово, коли
`walker.py calibrate` виконано на всіх п'яти випадках, `.engine/walks/calibration.json` у git, у звіті — скільки вад
знайдено з чотирьох, скільки хибних знахідок на чистій ревізії, витрати, і `walker.py status` (`on` чи `off`).
Не пройшло — це теж результат: walker лишається вимкненим, у звіті — які вади пропущено і чому (за звітами `.engine/walks/`).
