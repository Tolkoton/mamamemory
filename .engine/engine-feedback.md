# Feedback for the engine

What the work learned that belongs in the engine's own repository.

## 2026-11-06 — Bypass guard на noqa/type-ignore у запечатаному тесті при зелених тестах відкрив gate esca

Bypass guard на noqa/type-ignore у запечатаному тесті при зелених тестах відкрив gate escalation і заблокував PASS; «так» власника не діяло без runner. Подано як задачу двигуна 310 (gate-trivial-findings-must-not-block).

From: lesson #fc17fc02 (gate, voice-to-text, 2026-11-05).

## 2026-11-06 — Overseer BLOCK лише через відкриту gate escalation на дрібниці стилю — той самий випадок, 

Overseer BLOCK лише через відкриту gate escalation на дрібниці стилю — той самий випадок, задача двигуна 310.

From: lesson #923f6513 (overseer, voice-to-text, 2026-11-06).

## 2026-11-06 — Немає шляху перезапечатати тест після дозволу власника (S1 показує CHANGED) — пункт 4 зада

Немає шляху перезапечатати тест після дозволу власника (S1 показує CHANGED) — пункт 4 задачі двигуна 310.

From: lesson #59a9fa2b (parked, s1-test-store-noqa, 2026-11-05).

## 2026-11-06 — Stop gate рахує червоні контрактні тести, які slice-tester щойно написав до коду (очікуван

Stop gate рахує червоні контрактні тести, які slice-tester щойно написав до коду (очікуваний RED, поки код не реалізовано), як падіння, і після трьох зупинок відкриває gate escalation (903, 904–906 у mamamemory). Ескалація блокує PASS overseer, хоча нічого не зламано. Пропозиція: поки для slice є відкритий testing-запит чи щойно запечатані RED-тести без коду, їхні падіння не рахуються до ескалації.

From: lesson #2ad1e4ad (overseer, open-questions, 2026-11-06).

## 2026-11-06 — Delete guard (delete/untested) спрацював на заміні приватних функцій планування (_show_new

Delete guard (delete/untested) спрацював на заміні приватних функцій планування (_show_new, _parse_task) новими з тією ж поведінкою, яку закривають запечатані тести через публічний API; разом із червоними тестами tester-а це дало три ескалації. Пропозиція: функцію, чию поведінку покривають тести публічних функцій того самого модуля, не вважати непротестованою (або коротка підказка писати pin-тест у test_<модуль>.py).

From: lesson #a1b40aba (overseer, several-tasks, 2026-11-06).

## 2026-11-07 — verify-on-stop fails the turn that ends right after the tester's sealed RED hand-in (contr

verify-on-stop fails the turn that ends right after the tester's sealed RED hand-in (contract tests red against the skeleton by design); the gate could treat sealed RED tests of the active slice before its first GREEN as expected, or the builder should not end a turn between seal and GREEN.

From: lesson #850b30ea (gate, note-to-case, 2026-11-07).

## 2026-11-12 — a BLOCK whose fix lies outside the code paths cannot be re-audited

The overseer blocked show-schedule on #1 (the owner's phone-pass card, named by the exit criterion, did not exist). The
fix is a board card (`tasks/blocked/742-…`), not code; the Stop hook then refuses every new unit claim («no code path
changed since») and no PASS can be recorded for the slice. A BLOCK on a non-code check (#1 board card, report, PROGRESS)
could allow a re-claim when the files the BLOCK names changed, not only `SOURCE_DIRS`.

## 2026-11-12 — When a slice's exit criterion names an owner card («прохід власника — картка»), the builde

When a slice's exit criterion names an owner card («прохід власника — картка»), the builder claimed the unit before opening it; the overseer blocked (#1). The Stop hook could check that a card named by the exit criterion exists before taking the claim.

From: lesson #30f9676f (overseer, show-schedule, 2026-11-12).

## 2026-11-12 — A smoke that checks a model reply through one helper (_reordered) can print PASS while the

A smoke that checks a model reply through one helper (_reordered) can print PASS while the production path rejects the same reply on another field (is_answer). A new gate on a model field must also be asserted by every existing smoke of that parse, and the builder must read the model replies in the report, not grep for FAIL.

From: lesson #19a492b9 (overseer, plans-not-questions, 2026-11-12).
