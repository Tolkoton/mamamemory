# Slice access-shell — planning artifact

Режим: driven, `/feature-architect f1-skeleton`, slice S1 (TRACER BULLET, частина 1). Рамка — з
`.engine/architecture/feature/f1-skeleton.md`; конвенції — `.engine/architecture/architecture-map.md` (M2, M3).

## Goal
Мама відкриває адресу сервісу в Chrome на Android, входить своїм Google-акаунтом із дозволами на
Calendar і Tasks і бачить оболонку застосунку, яку можна встановити з меню; будь-який інший акаунт і
запит без входу до оболонки не доходять. Разом із цим один раз будуються наскрізні частини, на які
спираються S2–S5: `config`, перевірка входу, сесія, одна обробка помилок, журнали в stdout, `store` під
акаунтом, тест регіонів, тести імпортів. Мірило: тести зелені, і smoke `scripts/smoke_access_shell.py` на розгорнутій
адресі проходить (див. «Exit criterion»). Вхід маминим акаунтом (AC1 фічі) закриває S5.

## Premise verified
- P-F1-DEPLOY — `verified`: звіт Сонька `~/sonko/done/2026-11-05-mamamemory-f1-provisioning.md` (2026-11-05
  21:35 UTC): база `projects/pocket-lawyer-431614/databases/mamamemory`, `europe-west3`, `FIRESTORE_NATIVE`; сервіс
  `https://mamamemory-2mfebgg56q-ey.a.run.app`; секрет `mamamemory-session-key`; API увімкнено.
- P-F1-OAUTH-CLIENT — `blocked on owner`: клієнт OAuth Web створюється лише в Cloud Console, мамина адреса
  невідома (той самий звіт, п. 5–6). Код і тести S1 від нього не залежать; розгортання й smoke — залежать.
- P-AUTH (тестовий режим, дозволи на Calendar і Tasks, повторний вхід раз на 7 днів) — `accepted-as-risk` до
  каркаса власником (premise-log, ~12:43 UTC 2026-10-24); перевіряє S5.
- Обмін коду (google-auth-oauthlib 1.4.0 → oauthlib 3.3.1): `autogenerate_code_verifier` є і за замовчуванням
  `True` (`flow.py:99-100,163`), `fetch_token(code=…, code_verifier=…)` приймає чужий verifier (`flow.py:284`);
  на неповні scopes — `Warning` з `.new_scope` (`oauthlib/oauth2/rfc6749/parameters.py:463-473`) — перевірено
  критиком по коду бібліотек у кеші uv, 2026-11-05.
- Бібліотеки: FastAPI віддає статичні файли й приймає залежності на маршрут; google-auth-oauthlib дає
  обмін коду на токени з `access_type=offline`; `google.oauth2.id_token.verify_oauth2_token` перевіряє ID
  token — `untested — common knowledge` (офіційні бібліотеки, широко вживані; slice-builder перевіряє
  першим RED-тестом).

## Out of scope (deliberately)
- голос, розмова, план, календарні виклики — S2, S3 (S1 лише отримує дозвіл на Calendar і Tasks);
- «незакриті питання» — S4; виміри каркаса — S5;
- service worker — немає за M3 (встановлення з меню Chrome 108+).

## Seam (contract)
- Signature: `create_app(config: Config, store: Store, google: GoogleAuth, now: Callable[[], datetime]) -> FastAPI`
  - `Config` — з середовища: `ALLOWED_EMAILS`, `GCP_PROJECT`, `FIRESTORE_DATABASE="mamamemory"`,
    `VERTEX_LOCATION="eu"`, `TTS_ENDPOINT="eu-texttospeech.googleapis.com"`, `REGION="europe-west3"`,
    `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `SESSION_KEY`, `SESSION_MAX_AGE_S` (7 днів — як тестовий
    вхід), `LOGIN_MAX_AGE_S` (10 хвилин), `BASE_URL`, `REQUEST_TIMEOUT_S`, `CALL_TIMEOUT_S`, `SCOPES` — повні адреси: `openid`,
    `https://www.googleapis.com/auth/userinfo.email`, `https://www.googleapis.com/auth/calendar.events`,
    `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/tasks`.
  - Маршрути:
    - `GET /` — оболонка; без сесії — 302 на `/auth/login`.
    - `GET /auth/login` — 302 на Google; `state` і `code_verifier` PKCE — у підписаному cookie входу `mm_login`
      на `LOGIN_MAX_AGE_S` (10 хвилин, у `Config`); `access_type=offline`, `prompt=consent` (щоб у тестовому режимі
      надійно отримувати refresh token; тому мама бачить повний екран згоди при кожному щотижневому вході —
      це не «оптимізувати» в S4/S5).
    - `GET /auth/callback` — звіряє `state` з `mm_login`, обмінює код із `code_verifier`, перевіряє ID token і
      `email_verified`, дозволений email, що надано всі `SCOPES` (інакше `MissingScopes` → назад на вхід);
      пише токени; ставить cookie сесії `mm_session`; 302 на `/`. `mm_login` прострочене чи відсутнє — 302 на
      `/auth/login`; 400 лише для `state`, що є, але інший; `?error=…` без `code` (мама натиснула «Скасувати») —
      302 на `/auth/login`; дві вкладки входу — друга перезаписує `mm_login`, тож перший callback дістає 400
      (відома поведінка).
    - `GET /manifest.webmanifest`, `GET /static/*` — без сесії (Chrome бере маніфест без cookie); вмісту
      оболонки там немає. Усе з `Cache-Control: no-cache`.
  - Назви cookie (`mm_session`, `mm_login`) і маршрути — контракт для S2–S4. Обидва підписані `SESSION_KEY` з
    різними salt itsdangerous (`session`, `login`), тож одне не приймається за інше.
  - `access.verify_session_cookie(cookie: str | None, now: datetime, *, key: str, allowed_emails: frozenset[str],
    max_age_s: int) -> SessionClaims(sub, email, iat)` — чиста, без фреймворку й I/O: підпис, вік ≤ `max_age_s`,
    `email ∈ allowed_emails`; кидає `NotSignedIn` (немає чи підроблене), `LoginExpired` (старе), `NotAllowed`.
  - `access.session_cookie_value(sub: str, email: str, now: datetime, *, key: str) -> str` — значення `mm_session`.
    Підпис — `itsdangerous.URLSafeSerializer` (без вбудованого `max_age`, бо той дивиться на справжній годинник);
    вік рахується як `now - iat` з тіла cookie.
  - `access.google_credentials(store: Store, google: GoogleAuth, account_id: str) -> Credentials` — читає
    `private/google` під акаунтом, оновлює токен через `google.refresh`; на `invalid_grant` — `LoginExpired`.
  - `http.current_session(request) -> Session` — залежність FastAPI: читає `mm_session`, викликає
    `access.verify_session_cookie` зі значеннями з `Config` і збирає
    `Session(account_id=claims.sub, google_credentials=partial(access.google_credentials, store, google, claims.sub))`.
    Cookie ставиться з `HttpOnly`, `Secure`, `SameSite=Lax`.
- Returns: `Session(account_id: str, google_credentials: Callable[[], Credentials])`, де `account_id` — Google `sub`.
- Errors: модулі кидають власні помилки (`NotSignedIn`, `NotAllowed`, `LoginExpired`, `OAuthStateMismatch`,
  `MissingScopes`); одна обробка в `http` перекладає їх у відповідь (302 на вхід; 403 із текстом-заглушкою
  «Цей акаунт не має доступу.» — остаточний текст за C8 у S4/F5; 400). `google_credentials()` кидає
  `LoginExpired`, коли refresh token відкликано або сплив (тестовий режим, 7 днів).
- Dependencies (injected): `Store` (`get(account_id, path) -> dict | None`, `set(account_id, path, data)`;
  `path` — відносний, парна кількість сегментів, без `..` і провідного `/`, `""` — кореневий документ
  `accounts/{account_id}`; шлях із непарною кількістю сегментів, порожнім сегментом, `.`/`..` чи провідним `/` — `ValueError`;
  `account_id` порожній, з `/`, `.` чи `..` — теж `ValueError`; перевірку й побудову повного шляху робить одна
  функція, спільна для Firestore-реалізації й фейку;
  Firestore-реалізація з базою `config.FIRESTORE_DATABASE` і фейк у пам'яті),
  `GoogleAuth` (`authorization_url() -> (url, state, code_verifier)`; `exchange(code, code_verifier) -> Tokens`
  з наданими scopes і ID token — oauthlib 3.3.1 на неповний набір scopes кидає `Warning("Scope has changed…")`
  з `.new_scope` і `.token` на будь-яку різницю наборів (`tokens.py:39-40`: `_new_scope != _old_scope`, тож і
  на більший чи інакше записаний набір); `exchange` ловить його, рахує `missing = set(SCOPES) - set(w.new_scope)`:
  непорожній — `MissingScopes(missing)`, порожній — продовжує з `w.token` як з успішною відповіддю; змінну
  середовища `OAUTHLIB_RELAX_TOKEN_SCOPE` не вмикаємо; `verify_id_token(token) -> Claims` через
  `google.oauth2.id_token.verify_oauth2_token` з аудиторією `OAUTH_CLIENT_ID` — видавця (обидві форми
  `accounts.google.com`) перевіряє сама бібліотека, вручну не порівнюємо; `refresh(tokens) -> Credentials`;
  справжня — `integrations/google_auth`, фейк для тестів відкидає обмін без `code_verifier` чи з чужим), `now`.
- Модулі: `access` — дозволений email, перевірка cookie сесії, облікові дані Google; `http` — маршрути, залежність
  `current_session`, cookie, обробка помилок; `integrations/google_auth`, `integrations/store`; `config`.
- Does NOT do: жодних викликів Calendar/Tasks/Gemini; жодного стану розмови; не зберігає email поза документом
  акаунта.

## Decisions (with WHY)
- Q1: Дозволений акаунт — за перевіреним email (`email_verified`) із `config`, а `account_id` — `sub`. Чому:
  `sub` мами невідомий до першого входу, email — відомий власникові. Rejected: список `sub` у config — найсильніше за: не залежить від зміни email; але треба
  спершу ввійти, щоб його дізнатися (двокрокове розгортання); перевірка лише за списком Test users екрана
  входу — він спільний з Pocket_lawyer (ADR-0003).
- Q2: Сесія — підписане cookie (`itsdangerous`, ключ `SESSION_KEY`) з `sub`, перевіреним `email` і `iat`,
  `HttpOnly`, `Secure`, `SameSite=Lax`; перевірка I1 — на кожному запиті без I/O. Чому: M3. Rejected: сесії в
  Firestore — найсильніше за: відкликання сесії на сервері без зміни ключа; але це читання на кожен запит
  (P1), а відкликати можна, прибравши email з `ALLOWED_EMAILS`.
- Q3: Токени Google — у документі `accounts/{sub}/private/google` (refresh token, scopes, час). Чому: один
  документ під акаунтом (ADR-0001); шифрування Firestore за замовчуванням. Rejected: Secret Manager на кожен
  токен — найсильніше за: токени не потрапляють у вивантаження бази; але це бібліотека й API в коді, від
  яких M3 відмовилась (P-COLD).
- Q4: `store` — шлях завжди будується як `accounts/{account_id}/…` усередині `store`; модулі передають
  відносний шлях. Чому: ADR-0001 — неможливо записати поза акаунтом. Rejected: модуль сам будує повний шлях —
  найсильніше за: запити через кілька акаунтів, але це не-ціль (N6); легко забути префікс.
- Q5: PKCE увімкнений явно — справжня реалізація сама ставить `autogenerate_code_verifier=True`, не
  покладаючись на значення бібліотеки за замовчуванням; `code_verifier` живе в підписаному
  cookie входу разом зі `state`, бо callback може прийти на інший екземпляр після сну. Rejected: вимкнути PKCE —
  для веб-клієнта з секретом допустимо, але без нього слабший захист від перехоплення коду.
- Q6: Читання й запис cookie — у `http`, перевірка сесії й дозволеного акаунта — чиста функція в `access`.
  Чому: M3 — «одна перевірка входу» і FastAPI лише в `http`; `access` без фреймворку перевіряється тестами без
  HTTP. Rejected: залежність FastAPI в `access` — найсильніше за: усе про сесію в одному місці; але `access`
  тоді імпортує `fastapi`/`starlette`, і каркас перестає бути двобічним.
- Q7: Оболонка — статичний `index.html`, `manifest.webmanifest`, значки 192/512, без service worker. Чому: M3.
- Q8: Перевірка cookie (`verify_session_cookie`, чиста, значення конфігурації — параметрами) і отримання
  облікових даних Google (`google_credentials`, з `Store` і `GoogleAuth`) — дві окремі функції `access`; `Session`
  збирає `http.current_session`. Чому: перевірка входу на кожному запиті не робить I/O, а облікові дані
  потрібні лише плануванню (M3: «щотижневе закінчення входу не ламає запитів про фото й справи»). Rejected:
  значення `Access`, зібране один раз з config, store і google, — найсильніше за: менше параметрів у викликах;
  але це ще один об'єкт-обгортка з однією реалізацією (M3: «без зайвих прошарків»).

## Hardest seams (test-confidence points — distinct from the contract Seam above)
- **Seam 1: OAuth callback** — тест через `TestClient(app, base_url="https://testserver")` (cookie `Secure`)
  з фейком `GoogleAuth`, що повертає задані claims (дозволений email, недозволений, `email_verified=false`,
  підмінений `state`, відсутній чи чужий `code_verifier`, неповні scopes → `MissingScopes`; `mm_login`
  відсутнє чи прострочене за ін'єктованим `now` → 302; `?error=` без `code` → 302); перевіряються код відповіді,
  cookie, запис у фейк `Store`. Виключає антипатерн «мок, що завжди пропускає» — кожен випадок окремо.
- **Seam 1a: справжній `exchange` на неповних scopes** — тест справжньої реалізації `integrations/google_auth`
  із підставною відповіддю токен-сервера на рівні транспорту (адаптер `requests` у
  `OAuth2Session`, не підміна `Flow.fetch_token`, щоб пройти справжній шлях `Warning` oauthlib): `scope` без `tasks` → `MissingScopes` (не 500); `scope` з усіма
  `SCOPES` плюс зайвим (раніше наданим) чи в іншому порядку → успішний обмін, не `MissingScopes`; справжній `verify_id_token` з ID token, підписаним тестовим RSA-ключем, і підставним
  `google.auth.transport.Request`, що віддає сертифікат цього ключа: `aud` іншого клієнта — відмова (бібліотека без `audience` аудиторію не перевіряє, `id_token.py:168-170`); виключає «фейк
  пропускає, справжня бібліотека падає».
- **Seam 2: `access.google_credentials` при відкликаному токені** — справжня `integrations/google_auth.refresh`
  через справжній `google.oauth2.credentials.Credentials.refresh` з підставним транспортним запитом (як Seam 1a):
  400 `{"error":"invalid_grant"}` → `LoginExpired`; 400 `{"error":"invalid_client"}`, 503 і піднятий
  `TransportError` → не `LoginExpired`. Код розрізняє за `RefreshError.args[1]["error"]` лише якщо `len(e.args) > 1` і
  `isinstance(e.args[1], dict)`, бо google-auth кидає той самий `RefreshError` на будь-яку невдачу, а на тіло
  не-JSON — з одним аргументом (`google/oauth2/_client.py:63-75`). Випадки не-`invalid_grant` перевіряють
  названий результат: `RefreshError` проходить далі; є випадок тіла не-JSON; основний — 400 `invalid_client`
  (без повторів), а в тесті 503 `time.sleep` підставлено. Виключає «ловимо все».
- **Seam 3: регіони** — завантаження `Config` із середовища кидає `ValueError` поза поштучним дозволеним
  набором: `VERTEX_LOCATION` — `eu` або `europe-*`; `TTS_ENDPOINT` — рівно `eu-texttospeech.googleapis.com`;
  `REGION` — `europe-*`; `FIRESTORE_DATABASE` — рівно `mamamemory` (не `(default)`, не порожнє). Тест подає
  через середовище `global`, `us-central1`, `texttospeech.googleapis.com`, `(default)` і чекає `ValueError`.
  Розташування бази `mamamemory` підтвердив Сонько (P-F1-DEPLOY), а `tests/test_store.py` перевіряє, що
  справжня Firestore-реалізація будує клієнт із `database=config.FIRESTORE_DATABASE` (фабрика клієнта —
  параметр; клієнт без `database=` тест не пройде).
- **Seam 4: межі імпортів** — тест розбирає імпорти: `fastapi` і `starlette` лише в `mamamemory/http`.

## Invariants (rules that hold for every input in the stated domain)
- **I1** — Запит без чинної сесії дозволеного акаунта ніколи не отримує вмісту оболонки.
  - Domain: будь-який запит до будь-якого маршруту, крім `/auth/*`, маніфесту й статичних значків (`index.html`
    віддається лише на `GET /`, не під `/static`) — без cookie, з підробленим чи простроченим cookie, з cookie
    акаунта, якого немає в `ALLOWED_EMAILS`, зі значенням `mm_login`, поданим як `mm_session`.
  - Source: AC1 фічі; C3, C7.
  - Broken by: перевірка лише наявності cookie без підпису; перевірка дозволеного email лише під час входу, а не на кожному запиті до оболонки після зміни `ALLOWED_EMAILS`.
- **I2** — Кожен документ, який пише чи читає `store`, лежить під `accounts/{account_id}/`.
  - Domain: будь-який `account_id` і будь-який відносний шлях, який передає модуль (неприйнятні — `ValueError`).
  - Source: ADR-0001; Q4 цього контракту.
  - Broken by: `store`, що приймає повний шлях від модуля; що не перевіряє `account_id` (`"a/b"`, `".."`, `""`);
    шлях із `..`, `.`, порожнім сегментом чи провідним `/`. Тест іде через спільну функцію побудови шляху, тож
    фейк не пройде сам.
- **I3** — Жодна налаштована адреса сервісу Google не вказує на `global`.
  - Domain: усі значення `Config`, що задають регіон, адресу чи базу (`VERTEX_LOCATION`, `TTS_ENDPOINT`, `REGION`,
    `FIRESTORE_DATABASE`), з
    якого б середовища їх не прочитано; поза дозволеним набором — `ValueError` під час завантаження.
  - Source: C1; M2 «Перевірка регіонів».
  - Broken by: значення конфігурації `global`, `us-*` чи глобальна адреса `texttospeech.googleapis.com`; база `(default)` спільного
    проєкту (ADR-0003, ADR-0004) чи клієнт Firestore без `database=`; `Config`,
    що читає середовище без перевірки (тест лише значень за замовчуванням таке пропустить). (Значення SDK за замовчуванням перевіряється там, де
    будуються клієнти, — S2, S3; розташування бази Firestore підтвердив Сонько, P-F1-DEPLOY.)

## Exit criterion
- `pytest` зелений: `tests/test_auth_callback.py` (Seam 1, 1a), `tests/test_credentials.py` (Seam 2),
  `tests/test_config.py` (Seam 3, I3), `tests/test_imports.py` (Seam 4), `tests/test_store.py` (I2),
  `tests/test_shell_access.py` (I1), `tests/test_error_log.py` (журнал).
- Розгортання Соньком з образу цього коду на сервіс `mamamemory` (europe-west3), секрети — змінними
  середовища.
- Smoke `scripts/smoke_access_shell.py <BASE_URL>` на розгорнутій адресі: `GET /` без cookie → 302 на
  `/auth/login`; `GET /auth/login` → 302 на `accounts.google.com` з потрібними `scope`, `access_type=offline`,
  `prompt=consent`, `code_challenge_method=S256`, `redirect_uri=<BASE_URL>/auth/callback`, і `mm_login` з
  `Secure; HttpOnly; SameSite=Lax`; `GET /manifest.webmanifest` → 200, валідний JSON з `name`,
  `start_url`, `display: standalone`, значками 192 і 512; `Cache-Control: no-cache` на `/` і статиці; `GET /`
  з підробленим cookie → 302.
- S1 DONE = тести зелені + розгортання + smoke. Частина «тести» досяжна без клієнта OAuth; розгортання й smoke —
  лише після того, як власник створить клієнт OAuth і назве мамину адресу (P-F1-OAUTH-CLIENT). До того S1 стоїть
  «код готовий, чекає розгортання», не DONE.
- Доказ розгортання: у звіті Сонька — git SHA коду, digest образу розгорнутої ревізії й дослівний вивід smoke
  проти неї.
- Тест журналу: помилка проходить через одну обробку в `http`, у stdout — один рядок, у ньому немає токена, cookie
  чи email.

## Deferred to later slices
- Використання дозволів Calendar/Tasks — S3, F2 — trigger: план S3.
- Показ «увійди знову» при `LoginExpired` — S4 — trigger: план S4; S1 виграє менший обсяг, S4 платить одним
  маршрутом над уже готовим `LoginExpired`.
- Пояснення мамі, коли вона зняла галочку Calendar чи Tasks (`MissingScopes`), — S4; у S1 — повернення на
  вхід. — trigger: план S4; S1 виграє, S4 платить одним повідомленням.
- Остаточний текст 403 (зараз заглушка «Цей акаунт не має доступу.») і поведінка двох вкладок входу (400) — S4/F5 —
  trigger: план S4.
- Ручний вхід маминим акаунтом (оболонка відкривається, інший акаунт — 403; AC1) — S5 — trigger: власник
  створив клієнт OAuth і назвав мамину адресу.

## Open items requiring human decision (if any)
- Клієнт OAuth Web у Cloud Console (`pocket-lawyer-431614`, тип Web application, назва `mamamemory`; origin
  `https://mamamemory-2mfebgg56q-ey.a.run.app`; redirect `https://mamamemory-2mfebgg56q-ey.a.run.app/auth/callback`)
  і мамина Gmail-адреса (у Test users і `ALLOWED_EMAILS`) — лише власник. До того S1 будується й тестується
  локально; розгортання й smoke — після.

## Critic notes (non-blocking)
- Після `Warning` про scopes `OAuth2Session.token` не встановлюється (`oauth2_session.py:406`), тож
  `flow.credentials` будується з порожнього токена: `Tokens` треба будувати з `w.token`; випадок Seam 1a «надмножина
  scopes → успіх» ловить будівника, що бере `flow.credentials`.
- `verify_oauth2_token` перевіряє `iat`/`exp` за справжнім годинником: тестовий токен Seam 1a — з `iat`/`exp`
  відносно справжнього часу.
- Phase 2 пройшла 5 раундів (circuit breaker на 4-му — `.engine/overseer/escalations.md`, AUTONOMOUS); Phases 3–5 — 3
  раунди; cold-reader — 2.
