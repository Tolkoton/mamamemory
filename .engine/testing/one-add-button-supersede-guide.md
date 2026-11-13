# Supersede package — guide, changed by the sealed contract one-add-button (owner's word 2026-11-12: «кнопка фото і кнопка додати… Так не треба»)

one-add-button Seam: «`assistant.GUIDE_UK`: рядок «• «Запиши до пані Шмідт: …», або 📷 чи ＋ — покладу у справу.» стає
«• «Запиши до пані Шмідт: …», або ＋ (фото чи файл) — покладу у справу.»; решта гайду — як була.»; поправки: «supersede:
`tests/guide_world.py` (GUIDE) → `tests/test_guide.py::test_guide_text_is_the_contract_text_for_uk_and_the_same_for_another_language`
і `tests/test_guide_disputed.py::test_Q1_guide_text_is_the_contract_block_character_for_character`;
`tests/test_f5_guide_voice_integration.py` бере той самий `guide_world.GUIDE` і йде за ним без правок».

- `tests/guide_world.py` — константа `GUIDE` тримає старий рядок з «📷 чи ＋»; замінити на новий рядок; решта — як була.
  Від неї падають усі тести `tests/test_guide.py`, `tests/test_guide_disputed.py::test_Q1_…` і
  `tests/test_f5_guide_voice_integration.py::test_AC1_…–test_AC4_…` (вони порівнюють з `GUIDE`).

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
