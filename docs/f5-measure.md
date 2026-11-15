# F5 — вимір (S4 f5-measure), 2026-11-11

Викладено: ревізія `mamamemory-00025-kgg` (100% трафіку), образ
`…/cloud-run-source-deploy/mamamemory@sha256:c9d097506aa4…`. Вивід Сонька дослівно:
`~/sonko/done/2026-11-11-mamamemory-f5-deploy.md`. F5 — мова під акаунтом, гайд «що ти вмієш?», кнопка 🔊 «прочитай».

## Smoke кожного slice
| Slice | Перевірка | Результат |
|---|---|---|
| S1 language-setting | тести `tests/test_language_setting*.py` | 11 з 11 (мова — з `settings/profile`, без документа — `uk`) |
| S2 guide | `scripts/smoke_guide.py` | 5 з 5, разом з «що ти вмієш?» під питанням справ → `help` |
| S3 read-aloud | `scripts/smoke_read_aloud.py` | 8 з 8 (5 частин гайду й 3 довгого тексту, 4,0–5,3 с кожна) |
| S4 f5-measure | `scripts/smoke_access_shell.py`, `scripts/smoke_f5_deployed.py` | 13 з 13; 3 з 3 |

`smoke_guide.py` і `smoke_read_aloud.py` кличуть моделі й TTS з машини Сонька — вони перевіряють моделі, не ревізію.
На розгорнутій адресі без входу перевірено, що ревізія несе S3–S4: `POST /api/speak` без cookie → 401, `GET /speak.js`
і `GET /player.js` → 302 на `/auth/login` (невідомий шлях — 404). Код F5 з маминою сесією — лише прохід на телефоні.

**Відхилення від контракту.** Контракт S4 чекав від `GET /speak.js` і `GET /player.js` без входу 200 і тіла скрипту.
Скрипти віддаються лише з сесією (S1), тож перший прогін `smoke_f5_deployed.py` дав 2 хиби з 3; скрипт тепер перевіряє
302 на `/auth/login` (маршрут є). Записано в `.engine/overseer/escalations.md`.

## Хиби 735 і 736 — виправлено
Обидві картки (`tasks/proposed/`) — про тиху «вдачу» 🔊: телефон, що не може зіграти аудіо, і відповідь без `X-Parts`
давали «успіх» без звуку й без «Не вдалося озвучити.». Тепер:
- програвання вийшло в `web/player.js` (`makePlay(Audio, URL)`): `error` чи відхилений `audio.play()` відхиляють
  частину — тести `error_event_rejects_and_revokes_the_url_once`, `rejected_audio_play_rejects_and_revokes_the_url_once`,
  `test_I2_the_first_event_settles_the_play_later_events_change_nothing_url_revoked_once`;
- `speak` повертає «Не вдалося озвучити.» на відхилене програвання й на `X-Parts`, що не ціле ≥ 1 — тести
  `play_rejected_on_part_0_stops_returns_failed_and_part_1_is_not_played`,
  `x_parts_of_part_0_not_an_integer_of_at_least_1_returns_failed_and_plays_nothing`,
  `test_I1_first_speak_is_null_only_when_every_part_played_to_the_end`.

Рядок стану з «Не вдалося озвучити.» (половина 735) тестом не покрито — його перевіряє прохід на телефоні. Чи закрити
картки 735 і 736 — рішення власника.

## Передумови (статуси — як у `.engine/premises/premise-log.md`)
- P-TTS — `verified` (PoC 2).
- P-TTS-LONG — `falsified`: один виклик на 350 знаків — 10,3 с, на 700+ — помилка через 60 с; тому озвучення частинами.
- P-TTS-PART — `verified`: частина до 100 знаків — 3,5–5,3 с (smoke S3 двічі).
- P-TTS-SA (виклик TTS сервісним акаунтом) — `unverified`: API увімкнений, акаунт
  `1017046526541-compute@developer.gserviceaccount.com` має `roles/editor`, але пробний виклик від його імені Сонькові
  заборонено; справжній виклик перевірить прохід на телефоні.

## Що лишилось власникові
- Картка 734 — межа озвучення 1 500 знаків і текст гайду (PROVISIONAL).
- Картка 737 — прохід на телефоні: гайд на першому відкритті, «що ти вмієш?», 🔊 біля відповіді. Крок «режим польоту →
  «Не вдалося озвучити.»» власник зняв 2026-11-12 («на режим польоту ми забиваємо, це не важливо»); рядок стану з цим
  текстом лишається без перевірки.
