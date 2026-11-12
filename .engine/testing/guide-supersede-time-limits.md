# Supersede package — time-limits, changed by the sealed contract guide (F5 S2; owner: «запускай f1–f5», frame card 734)

- `tests/test_time_limits_planning.py::test_open_questions_of_the_page_show_the_limits_question` — guide Seam «Перше відкриття»: на відкритті без позначки `settings/guide_shown` першим іде гайд (Reply без питання); старий тест порівнює весь список відповідей відкриття. Переписати: позначку покласти в сховище тесту наперед (як акаунт, що гайд уже бачив) чи врахувати гайд першим; решта тверджень (порядок, питання останнім, failed, login) — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
