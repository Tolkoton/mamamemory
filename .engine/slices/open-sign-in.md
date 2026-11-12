# Slice open-sign-in — planning artifact

Режим: driven, зміна після цілей v4 (G6, C10; ADR-0007). Змінює запечатаний S1 (`.engine/slices/access-shell.md`)
лише в одному: список дозволених акаунтів зникає. Решта S1 (cookie, вхід, PKCE, регіони, журнал) лишається.

## Goal
Будь-який акаунт Google входить без списку дозволених і працює лише зі своїми даними: власник може зайти й
спробувати, мама — так само, кожен у своєму середовищі (G6, C10). Мірило: тести зелені; на розгорнутій адресі
два різні акаунти входять, і жоден не бачить плану іншого.

## Premise verified
- Робочий режим екрана входу Google без перевірки пускає будь-який акаунт (до 100 користувачів), один раз показує
  екран «неперевірений застосунок» — `untested — common knowledge` (довідка Google Cloud про режими екрана згоди,
  на яку спирався ADR-0003); «один раз?» — разом із `prompt=consent` на кожному вході екран може з'являтися щоразу;
  перевіряє власник при першому вході після перемикання (board 701), поведінку при повторних входах — S5.
- Дані вже лежать під `accounts/{account_id}/` (S1, I2; ADR-0001) — `verified` тестами S1.

## Out of scope (deliberately)
- ліміт витрат на користувача, адміністративний перегляд чужих даних (N4), видалення акаунта — пізніше;
- зміна `prompt=consent` чи віку сесії (7 днів) під робочий режим — S5, коли буде видно справжню поведінку;
- перевірка застосунку Google (ADR-0007, варіант В).

## Seam (contract)
- `Config`: поля `allowed_emails` немає; змінна середовища `ALLOWED_EMAILS` не читається: якщо задана
  (наприклад `ALLOWED_EMAILS=other@…`), сесія будь-якого акаунта все одно дістає оболонку — тест S1, що зараз
  перевіряє протилежне (`tests/test_entrypoint.py`), обертається в цей.
- `access.verify_session_cookie(cookie: str | None, now: datetime, *, key: str, max_age_s: int) -> SessionClaims`
  — підпис і вік ≤ `max_age_s`; кидає `NotSignedIn` (немає чи підроблене) і `LoginExpired` (старе). Іншої відмови
  немає.
- `GET /auth/callback` — як у S1, без перевірки email: ідентичність — `sub` з перевіреного ID token; `email_verified`
  не перевіряється. Усі `SCOPES` — як і раніше (`MissingScopes` → на вхід).
- `errors.NotAllowed`, текст «Цей акаунт не має доступу.» і відповідь 403 зникають.
- Усе, що читає чи пише дані, бере `account_id` лише з `Session` поточного запиту (`claims.sub`); тіло запиту
  `account_id` не несе.
- Does NOT do: обмежень на кількість користувачів у коді (межа 100 — Google), адміністратора.

## Decisions (with WHY)
- Q1: Ідентичність — `sub`, не email; перевірка `email_verified` іде разом зі списком — у S1 вона існувала лише
  для того, щоб звірка email зі списком була надійною (`.engine/slices/access-shell.md`, Decisions). Email у cookie
  сесії лишається як інформація; нічого його не читає. Чому: `sub` постійний, email може змінитися; без списку email ні для чого не
  потрібен. Rejected: лишити перевірку `email_verified` — найсильніше за: менше дивних акаунтів; але це відмова без
  причини в цілях (C10 — «будь-який акаунт»).
- Q2: Прибрати `allowed_emails` з `Config`, а не лишити порожнім. Чому: мертве налаштування вводить в оману при
  розгортанні. Rejected: лишити поле зі значенням «усі» — найсильніше за: менше змін у тестах; але це код, якого
  ніхто не просив (simplifier).

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: чужий акаунт** — два акаунти A і B на одному `store`: B з `plan_id` плану A (через
  `/api/plan/confirm` і `/api/message` з `reply_to` A) не пише в Calendar і не змінює чернетку A; документи A лежать
  лише під `accounts/A/`. Виключає «account_id з тіла запиту».
- **Seam 2: вхід нового акаунта** — callback з фейком `GoogleAuth`, що повертає будь-який `sub`/email (і
  `email_verified=false`) → сесія, токени під `accounts/{sub}/`, 302 на `/`.

## Invariants (rules that hold for every input in the stated domain)
- **I1** — Запит без чинної сесії (підпис `SESSION_KEY` і вік ≤ `SESSION_MAX_AGE_S`) ніколи не отримує вмісту
  оболонки чи даних акаунта.
  - Domain: будь-який запит до будь-якого маршруту, крім `/auth/*`, маніфесту й статичних значків — без cookie, з
    підробленим, простроченим cookie, зі значенням `mm_login`, поданим як `mm_session`.
  - Source: S1 I1 без «дозволеного акаунта» (C10); C3.
  - Broken by: перевірка лише наявності cookie; прийняття `mm_login` як сесії.
- **I2** — Запит із сесією акаунта A ніколи не читає й не пише документ іншого акаунта.
  - Domain: будь-які два різні `sub`, будь-який маршрут `/api/*`, будь-які `plan_id`/`reply_to` у тілі.
  - Source: G6, C10 («дані кожного — лише його»); ADR-0001.
  - Broken by: `account_id` з тіла запиту чи з `plan_id`; спільний документ між акаунтами.

## Exit criterion
- `pytest` зелений: Seam 1–2, `test_I1_…`, `test_I2_…`; запечатані тести S1–S3, що будують `Config` з
  `allowed_emails` чи перевіряють 403, змінює незалежний тестувальник за словом власника («Так», 2026-11-06, на
  «попрошу твоє пряме «так»» для тестів S1; запис OWNER у `.engine/overseer/escalations.md`); їхні твердження про
  все, крім списку дозволених, не змінюються. Тест журналу (`tests/test_error_log.py`) переходить з `NotAllowed` на
  іншу помилку тієї самої обробки (наприклад `OAuthStateMismatch` → 400), а не зникає. Перелік запечатаних тестів,
  що змінюються (і лише вони; помічники, що будують `Config`, у `tests/test_credentials.py`,
  `tests/test_one_task_planning.py`, `tests/test_smoke_script.py`, `tests/test_one_task_http.py`,
  `tests/test_voice_*.py` — лише без аргументу `allowed_emails`):
  - `tests/test_config.py` — без `ALLOWED_EMAILS` у середовищі й без поля в `Config`;
  - `tests/test_entrypoint.py` — тест «зміна `ALLOWED_EMAILS` відрізає сесію» обертається в «задана `ALLOWED_EMAILS`
    не впливає»;
  - `tests/test_shell_access.py::test_session_cookie_of_email_not_allowed_is_not_allowed` — видаляється (відмови
    `NotAllowed` немає); у `test_I1_…` випадки «account not allowed» і «removed from ALLOWED_EMAILS since»
    переходять у перевірку, що сесія іншого акаунта дістає оболонку; виклики без `allowed_emails`;
  - `tests/test_auth_callback.py` — тест 403 для недозволеного email стає Seam 2 (будь-який акаунт → сесія);
    `test_callback_email_not_verified_gives_no_session` обертається: `email_verified=false` → сесія (Q1);
  - `tests/test_imports.py` — виклик `verify_session_cookie` без `allowed_emails`;
  - `tests/test_error_log.py` — як вище (інша помилка тієї самої обробки).
- Розгортання Соньком разом із S1–S3 після board 701 (клієнт OAuth, робочий режим екрана згоди); змінну
  `ALLOWED_EMAILS` Сонько прибирає з середовища сервісу; smoke S1 (`scripts/smoke_access_shell.py`) — як у S1.
- Перевірка двох акаунтів на розгорнутій адресі — люди, бо потрібні справжні входи Google (власник і другий
  акаунт, після board 701): акаунт A складає план (не записує); акаунт B входить на той самий `BASE_URL`, бачить
  порожню розмову й жодного плану A; «так» B з `plan_id` A (`/api/plan/confirm` з DevTools) нічого не пише в
  календар A. Записується як спостереження власника чи Сонька у звіті розгортання. До того slice — «код готовий,
  чекає розгортання», не DONE.

## Deferred to later slices
- Ліміт витрат моделі на користувача — trigger: перший акаунт, що не власник і не мама, або місячні витрати
  на модель понад суму, яку назве власник (C6; суми поки немає — його рішення).
- `prompt=consent` і вік сесії в робочому режимі — S5.

## Open items requiring human decision (if any)
- Перемкнути екран згоди Google в «In production» — власник, разом зі створенням клієнта (board 701).

## Critic notes (non-blocking)
- Cold-reader 2: REVISE (перелік змінюваних тестів неповний; `email_verified` — частина списку) — виправлено.
- Cold-reader 1: REVISE (перевірки двох акаунтів не було в Exit criterion) — виправлено разом із нотатками 2–7.
