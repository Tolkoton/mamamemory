# Supersede package — guide, changed by the sealed contract case-recall (F4 S3; owner: «запускай f1–f5»)

case-recall Seam: «`assistant.GUIDE_UK`: перед рядком «• 🔊 біля відповіді — прочитаю вголос.» два нові рядки: «• «Працюю
над …», потім «що я робила з …?» — запам'ятаю й нагадаю.» і «• «Що ми знаємо про пані Шмідт?», «які плани на
тиждень?» — розповім.»; решта гайду — як була.»; поправки: «supersede `tests/guide_world.py` (GUIDE) і тестів, що з ним
порівнюють (`tests/test_f5_guide_voice_integration.py` бере `guide_world.GUIDE` і йде за ним без правок)».

- `tests/guide_world.py` — константа `GUIDE`: додати два нові рядки перед рядком 🔊; решта — як була. Від неї падають
  усі тести `tests/test_guide.py`, `tests/test_guide_disputed.py::test_Q1_…` і
  `tests/test_f5_guide_voice_integration.py::test_AC1_…–test_AC4_…`.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green, except
`tests/test_one_add_button.py::test_guide_…` and `tests/test_clarify_disputed.py::test_Q1_…`, which wait for their own packages.
