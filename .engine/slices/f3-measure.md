# Slice f3-measure — F3 S5, driven by /feature-architect f3-cases-intake — planning artifact

## Goal
Закрити F3 виміром і звітом: як справжня модель розбирає фрази про справи, на яких підказки не налаштовувались
(`scripts/measure_f3.py`, десять фраз: нотатки й задача в маршрутизації, відповіді на питання справ, «перекласти»,
Розкладач), зведення smoke S1–S4 і перевірених передумов у `docs/f3-measure.md`, прохід власника на телефоні — картка
на дошці. Вимірний сигнал: Сонько надрукував `MEASURED: N of 10`; звіт називає N, кожну хибу й передумови P-CASES,
P-GCS, P-DESC, P-ROUTE-CASES зі статусом.

## Premise verified
- Сервіс викладено (ревізія `mamamemory-00018-9s6`, smoke доступу зелений) — звіт Сонька
  `~/sonko/done/2026-11-07-mamamemory-move-material-smoke-deploy-2.md`, 2026-11-07.
- Статуси з premise-log (2026-11-07): P-CASES — `verified` до 48 справ (P-CASES-48), понад 48 не міряно; P-GCS,
  P-DESC, P-ROUTE-CASES — `verified` smoke S2, S4, S1/S3/S4; P-DISCONNECT-PHOTO — `verified` тестами модуля S2,
  на телефоні не міряно; P-DISCONNECT (запит Cloud Run після закриття застосунку) — `unverified`; P-PARSE — `verified`
  F2, і маршрутизація F3 його вживає.

## Out of scope (deliberately)
- зміни коду `src/` — вимір не правит підказок (хиби — пропозиція на дошці);
- пороги якості — їх немає (Q2 goals): вимір іде власникові як число.

## Seam (contract)
- Скрипт `scripts/measure_f3.py` (уже в дереві): справжня модель через `assistant._route_prompt` /
  `assistant.route_schema`, `cases._move_prompt` / `MOVE_SCHEMA`, `cases._classify_prompt` / `CLASSIFY_SCHEMA`; друкує
  кожну фразу, відповідь моделі, PASS/FAIL і `MEASURED: N of 10`; код 0, якщо модель доступна.
- Звіт `docs/f3-measure.md`: ревізія, smoke кожного slice з числами, N з 10 і кожна хиба дослівно; статус кожної
  передумови фічі F3 (P-CASES, P-GCS, P-DESC, P-ROUTE-CASES, P-PARSE, P-DISCONNECT-PHOTO, P-DISCONNECT) — такий самий,
  як її рядок у premise-log; що лишилось від власника. Фраза «записку про аванс — у ремонт кухні» стосується матеріалу,
  який уже в «ремонт кухні»: звіт це називає (вона перевіряє лише вибір, а відповідь сервісу була б «Це вже в…»), а
  «прамipексол» має латинські «i», «p» — шум у вході, не помилка моделі.
- Хиби виміру — пропозиція `tasks/proposed/` (не правка коду в цьому slice).
- Does NOT do: зміни `src/`, порогів, нових тестів поведінки.

## Decisions (with WHY)
- Q1: Вимір — без порогу, число власникові. Чому: goals Q2 («без числового порогу»), як вимір F2. Rejected: поріг
  (наприклад 9 з 10) — найсильніше за: автоматичний сигнал; але поріг — рішення власника, якого немає.

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: свіжість** — вимір ганяється на дереві, з якого викладено ревізію (жодної правки `src/` між викладкою й
  виміром); перевірка — час файлів `src/` проти звіту викладки Сонька (дерево не закомічене, тож хеш коміту не годиться).

## Invariants (rules that hold for every input in the stated domain)
None — вимір і звіт, не логіка: правила над доменом входів тут немає.

## Exit criterion
- Вивід Сонька `MEASURED: N of 10` (дослівно у `~/sonko/done/2026-11-07-mamamemory-f3-measure.md`); `docs/f3-measure.md`
  з N, хибами й статусами передумов, кожен з яких збігається з рядком premise-log; `pytest`, `node --test`, ruff, mypy зелені; прохід на телефоні — картка на дошці
  (виконує власник; до того F3 — «код готовий, чекає проходу»).

## Deferred to later slices
- Виправлення хиб виміру — trigger: власник бере пропозицію в роботу.
- P-DISCONNECT (і P-DISCONNECT-PHOTO на телефоні) — trigger: перший напівзаписаний чи подвоєний матеріал у Firestore
  або мамине «фото зникло».

## Open items requiring human decision (if any)
- (немає)

## Critic notes (non-blocking)
- (порожньо)
