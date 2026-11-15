# 759 — Брак тесту (overseer): a test that, inside show()'s reply.card branch, finds speakButton(reply.text) appended after buildCard(...) (text check like test_seam5_show_…, or a stubbed document)

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-a-test-that-inside-show-s-reply-card-branch-finds-speakbutto-350384f0

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261115T093711Z-4738da`) і знайшов брак тесту: a show() that appends only buildCard(reply.card, make) in the card branch and drops the 🔊 button still passes every current test, though the slice Goal says 🔊 reads the same text Де: `tests/test_agenda_card.py`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-15T09:38:31Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «a test that, inside show()'s reply.card branch, finds speakButton(reply.text) appended after buildCard(...) (text check like test_seam5_show_…, or a stubbed document)»: тест червоніє на тому, що описано вище (a show() that appends only buildCard(reply.card, make) in the card branch and drops the 🔊 button still passes every current test, though the slice Goal says 🔊 reads the same text), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
