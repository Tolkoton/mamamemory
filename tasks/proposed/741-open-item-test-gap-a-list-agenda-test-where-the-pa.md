# 741 — Брак тесту (overseer): a list_agenda test where the page's timeZone differs from the zone the dateTime offset carries, e.g. dateTime '2026-11-15T23:30:00Z' with page timeZone Europe/Berlin, and the test asserts day == 2026-

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-list-agenda-test-where-the-page-s-timezone-differs-from-th-2a0aa16f

## Що сталося
Overseer повернув юніт `-|-|unit 1` (BLOCK, запит `20261112T111022Z-5cba73`) і назвав ще й брак тесту: an implementation that takes local.date() from the raw offset (UTC) without converting to the page zone puts the event under Sunday instead of Monday, and fakes that always return offsets in the calendar zone never notice Де: `tests/test_show_schedule_agenda.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-12T11:11:38Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a list_agenda test where the page's timeZone differs from the zone the dateTime offset carries, e.g. dateTime '2026-11-15T23:30:00Z' with page timeZone Europe/Berlin, and the test asserts day == 2026-11-16»: тест червоніє на тому, що описано вище (an implementation that takes local.date() from the raw offset (UTC) without converting to the page zone puts the event under Sunday instead of Monday, and fakes that always return offsets in the calendar zone never notice), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
