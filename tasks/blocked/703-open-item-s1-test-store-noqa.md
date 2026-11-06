# 703 — S1: один рядок у запечатаному тесті tests/test_store.py:91

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: s1-test-store-noqa

## Що сталося
Stop gate (bypass guard) блокує tests/test_store.py:91 — '# noqa: BLE001' без gate-allow на тому самому чи попередньому рядку (тестувальник поставив gate-allow над 'try', на два рядки вище). Обидва раунди заперечень S1 вичерпано; агент не редагує запечатаних тестів. Усе інше зелене: 41 тест, ruff, mypy.

- Записано: 2026-11-05T22:31:49Z, агент

## Що зробити
Це питання до власника, не робота для агента. Коли власник відповість, задача повернеться в чергу: виконай відповідь, запиши її у звіт і закрий задачу.

## Готово, коли
Власник відповів, і відповідь виконано.

## Питання до власника
1. Дозволити одну правку тесту (прибрати ' # noqa: BLE001' — правило BLE у ruff не ввімкнене, тож noqa зайвий; або перенести рядок gate-allow одразу над 'except') і перезапечатати тести S1? Порада: так, прибрати noqa — твердження тесту не міняються.
   Відповідь: так (власник, 2026-11-06: «703 треба прибрати.»)

2. Your answer to question 1 is already in the file: `tests/test_store.py` at HEAD (commit ed1c788) has no `# noqa: BLE001`. The `# gate-allow: BLE001 — …` line above `try` is a plain comment now, because it has no suppression left to explain. I rebuilt the sealed copy and its sha256 matches the seal (`84f49b95…`). The two copies differ in exactly those two lines; the assertions are the same. `uv run ruff check .`, `uv run mypy src tests` and `uv run pytest` (100 passed) are green, and `gate.py --layer ci --files tests/test_store.py` passes. What's left is resealing the S1 tests, and the engine has no way to do that: `testing.py` reseals only inside a dispute round with the `slice-tester`, and `access-shell` has used both rounds (`MAX_ROUNDS = 2`). A third `request --tester objection` does not reseal; it parks the slice. `owner_action.py` has no reseal action either, and the agent may not write `.claude/state/` by hand. Until the reseal happens, `testing.py gate access-shell` answers `BLOCKED: CHANGED … tests/test_store.py`, so the overseer cannot audit S1. How do we reseal?
   - (A) Add an owner action to the engine repository, for example `owner_action.py reseal-tests <slug> <sha256>`. It would reseal the files of a slice whose current sha256 the owner approved and write a ledger row. Then the runner carries out your «так» here.
   - (B) A one-time reseal from your terminal or by Sonko: `cd /home/lao/projects/mamamemory && python3 -c "import sys,pathlib; sys.path.insert(0,'.claude/hooks'); import testing; testing.seal_files(pathlib.Path('.'), 'access-shell', ['tests/test_store.py'], {})"`. It is fast, but it goes around the engine and leaves no row in `.engine/testing/ledger.md`.
   - (C) A third dispute round: it parks the `access-shell` slice with a «хто правий» question. It does not reseal anything, so this is a dead end.
   My advice: (A). This case will come up again whenever the owner allows a fix to a sealed test after two rounds. If you need S1 unblocked sooner, do (B) now as well, and (A) as a separate engine task.
   Відповідь:
