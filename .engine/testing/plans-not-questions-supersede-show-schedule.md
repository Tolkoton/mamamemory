# Supersede package — show-schedule, changed by the sealed contract plans-not-questions (owner's word 2026-11-12 evening: «не дивиться в календар, не дивиться в таски»)

plans-not-questions Seam: «`planning.schedule.show(session, text, *, calendar, now, config)` (новий параметр `config`): після
подій календаря — лише коли `config.use_tasks` … — відкриті задачі `calendar.list_open_tasks()` … рядок «Задачі без
часу:» і «• <назва>» …»; поправки: «show-schedule I1 → «Намір `schedule` нічого не пише в Calendar і Tasks; у Firestore —
нічого, крім видалення чернетки плану тижня «питаю» (`dismiss_asking`, plans-not-questions), коли `reply_to` —
`priorities` чи `limits`» (читання Tasks — тепер частина відповіді); … `schedule.show` дістає параметр `config`; тести
show-schedule, що тримають «не читає Tasks», точний текст відповіді без задач чи сигнатуру `show`, — supersede».

- `tests/show_schedule_world.py` — помічник `show(...)` кличе `schedule.show` без `config`; від цього падають усі
  тести нижче (TypeError: missing keyword argument 'config'). Передати `config` (наприклад `make_config()` з
  `use_tasks=False`, щоб текст відповіді лишився як був, або з фейком `list_open_tasks`).
- `tests/test_show_schedule.py::test_seam1_*`, `test_seam2_*`, `test_day_line_*`, `test_no_events_*`,
  `test_I2_every_event_of_the_period_once_and_none_outside` — та сама причина (сигнатура).
- `tests/test_show_schedule.py::test_I1_schedule_never_writes_and_never_reads_google_tasks` — I1 змінено: читання Tasks
  дозволено (коли `use_tasks`); запис — ні; виняток — видалення чернетки плану тижня «питаю» під `priorities` /
  `limits`.
- `tests/test_show_schedule_disputed.py::test_q1_…–test_q4_…` — сигнатура `show`.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green.
