# Objection package — plans-not-questions, round 1

- `tests/test_plans_not_questions.py::test_I1_is_answer_false_never_changes_the_draft_nor_the_limits` — друга частина
  (межі) будує світ `plans(ask_limits=True, use_tasks=False)` з `ask_priorities=True` за замовчуванням і двома задачами
  плану тижня; тоді `next_question` (planning:322–328) спершу питає «що важливіше?», а не межі, і
  `asked(..., "limits")` падає ще до перевірки інваріанта («expected the limits question, got … priorities»). Рядок
  контракту I1: «У `try_answer_priorities` / `try_answer_limits` відповідь розбору з `is_answer: false` ніколи не змінює
  чернетку… і документ меж» — щоб дійти до питання меж, світ має мати `ask_priorities=False` (чи одну задачу).
  Код поводиться за контрактом: перша частина (важливість) зелена.
- `tests/test_plans_not_questions_disputed.py::test_q1_both_parse_prompts_carry_the_is_answer_sentence_word_for_word` —
  та сама причина: світ для підказки меж будується з `ask_priorities=True`, тож питання меж не з'являється («expected
  the limits question»). Речення `is_answer` дослівно є в обох підказках (`planning._priorities_prompt`,
  `planning._limits_prompt` через `IS_ANSWER_HINT`).
