# Supersede package — read-aloud, changed by the sealed contract speak-control (owner's word 2026-11-12: «Ніяких знаків, має бути суть. Суть має бути вся»)

speak-control Seam: «`parts(text)`: межі `MAX_CHARS` немає — частини покривають **увесь** текст (після обрізання пробілів),
без обрізання; решта правил частин S3 … як були»; I1: «Склеєні частини `parts(text)` — завжди весь текст після обрізання
пробілів … кожна не довша за 100». Поправки: «read-aloud: межу `MAX_CHARS` / 1 500 прибрано (Seam, I1, Seam 1 про
обрізання)».

- `tests/test_read_aloud_parts.py::test_text_over_1500_ends_at_last_sentence_boundary_within_1500` — тримає обрізання на
  останній межі речення в межах 1 500; тепер склейка = весь текст.
- `tests/test_read_aloud_parts.py::test_sentence_boundary_at_exactly_1500_keeps_that_sentence` — те саме.
- `tests/test_read_aloud_parts.py::test_text_over_1500_without_sentence_boundary_ends_at_word_boundary` — те саме (межа
  слова); тепер усі слова тексту.
- `tests/test_read_aloud_parts.py::test_text_over_1500_without_any_boundary_is_cut_at_exactly_1500` — «ж»×3000 → 15
  частин; тепер 30 частин по 100.
- `tests/test_read_aloud_parts.py::test_I1_parts_are_at_most_100_and_glue_into_the_start_of_the_text_up_to_1500` —
  очікуваний «cut» понад 1 500 → тепер увесь текст (після обрізання пробілів); ≤ 100 на частину лишається.
- `tests/test_read_aloud_disputed.py::test_end_of_line_is_a_sentence_boundary_for_the_1500_cut` — правило обрізання
  зникло; тепер склейка = весь текст (або тест про обрізання прибрати як застарілий — на розсуд tester).
- `tests/test_read_aloud_disputed.py::test_text_of_exactly_10000_is_accepted` — 10 000 знаків лишаються дозволеними
  (межа маршруту 10 000 — speak-control, AUTONOMOUS); `X-Parts` тепер 100, не 15.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
