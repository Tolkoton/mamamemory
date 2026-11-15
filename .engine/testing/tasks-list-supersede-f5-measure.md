# Supersede package — f5-measure, changed by the sealed contract tasks-list (owner's question 2026-11-14: «як мама має його питати, що він видав нормальні таски?»)

Seam tasks-list: «`assistant`: новий намір `tasks` у `ROUTE_SCHEMA` і `ALWAYS`; `PHRASES["tasks"] = "показати список задач"`» і «`assistant.GUIDE_UK`: рядок «• «Які в мене задачі?» — покажу список задач.» перед рядком 🔊» (одразу перед ним; гайд тепер 10 рядків).

Блокові тести F5, що порівнюють гайд з точним текстом: тепер у ньому рядок задач перед рядком 🔊.

- `tests/test_f5_guide_voice_integration.py::test_AC1_guide_on_the_first_open_only_before_the_open_question_per_account`
- `tests/test_f5_guide_voice_integration.py::test_AC2_what_can_you_do_answers_the_same_guide_also_under_a_case_question`
- `tests/test_f5_guide_voice_integration.py::test_AC3_speaker_icon_reads_this_reply_only_when_pressed`
- `tests/test_f5_guide_voice_integration.py::test_AC4_recognition_speech_and_guide_take_the_language_from_the_account`

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
