#!/usr/bin/env python3
"""maintain.py — everything deterministic in /maintain, the regular care of a project (board 076).

    python3 .claude/hooks/maintain.py report [--date YYYY-MM-DD]
    python3 .claude/hooks/maintain.py question

Read .claude/commands/maintain.md for the whole procedure. In short:

report     writes the owner's document `.engine/maintain/<date>.md` and, when there is something to
           update, the list `.engine/maintain/updates.json`:
             - dependencies: what is outdated and by how much (patch / minor / major), what has
               known vulnerabilities. The two commands are the project's, `DEPS_OUTDATED_CMD` and
               `DEPS_AUDIT_CMD` in `.claude/project.env`; empty — the step is not there. They are
               RUN AS THEY ARE and must only read: the engine installs nothing;
             - complexity against the previous report (the totals `simplifier.py nightly` records);
             - hot places: files that change often AND hold a function over the limit;
             - the snapshot "as it was": how much is left, how much went since the previous report;
             - the open debts of urgent fixes; the lesson queue and whether memory is due a clean-up;
             - task proposals: everything worth work. Maintenance itself removes and tidies nothing.
question   prints the question that ends the maintenance — «Оновити ці N залежностей?», the list
           of patches and minor versions, and the action line the board runner acts on. Nothing is
           printed and the exit is 3 when there is nothing to update.

WHAT MAY BE UPDATED. Only a patch or a minor version, and the class is computed from the two
version numbers, never taken on trust: the first number differs — major; a `0.x` whose second
number differs — major too (semver: before 1.0 a minor may break); a version that is not plain
numbers — unknown. A major and an unknown never reach `updates.json`: each becomes a task proposal.

WHO UPDATES. Not this script and not the agent: changing packages is the owner's act. The owner's
«так» under the question is acted on by the board runner (`owner_action.py update-deps`), which
checks that the list is still the one the owner saw (its sha256 stands in the action line).

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import baseline
import complexity_budget as budget
import hotfix
import lesson_queue
import simplify_signals

MAINTAIN_REL = Path(".engine/maintain")
UPDATES_REL = MAINTAIN_REL / "updates.json"
REPORT_NAME = re.compile(r"^(\d{4}-\d\d-\d\d)\.md$")
TOTALS = re.compile(r"^<!-- maintain-totals: (\{.*\}) -->$", re.MULTILINE)
VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
VERSION_LIKE = re.compile(r"^v?\d+(?:\.[\w+-]+)+$")
UPDATABLE = ("patch", "minor")
KIND_WORDS = {"patch": "латка", "minor": "мала версія", "major": "велика версія", "unknown": "версію не розпізнано"}
CMD_TIMEOUT_S = 300
TAIL = 40
HOT_DAYS, HOT_MIN_CHANGES, HOT_SHOWN = 90, 3, 5
EXIT_NOTHING = 3

Dep = dict[str, str]


# ------------------------------------------------------------------ dependencies


def kind_of(current: str, latest: str) -> str:
    """patch, minor, major, unknown — or "" when `latest` is not newer than `current`."""
    was, now = VERSION.match(current.strip()), VERSION.match(latest.strip())
    if not (was and now):
        return "unknown"
    old, new = (tuple(int(n or 0) for n in m.groups()) for m in (was, now))
    if new <= old:
        return ""
    if new[0] != old[0] or (old[0] == 0 and new[1] != old[1]):
        return "major"
    return "minor" if new[1] != old[1] else "patch"


def _pairs(data: Any) -> list[tuple[str, str, str]]:
    """(name, current, latest) from the two JSON shapes in use: pip's list, npm's object."""
    rows = [{"name": name, **row} for name, row in data.items() if isinstance(row, dict)] if isinstance(data, dict) else data
    found = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        current = row.get("version") or row.get("current")
        latest = row.get("latest_version") or row.get("latest")
        if row.get("name") and current and latest:
            found.append((str(row["name"]), str(current), str(latest)))
    return found


def parse_outdated(out: str) -> list[Dep]:
    """The outdated dependencies a command printed: JSON (pip's list, npm's object), or text with
    one dependency a line — its name, then the current and the latest version as the first two
    version-like words. A line without two versions (a heading, a rule) is not a dependency."""
    try:
        pairs = _pairs(json.loads(out))
    except ValueError:
        pairs = []
        for line in out.splitlines():
            words = line.replace("->", " ").split()
            versions = [w for w in words[1:] if VERSION_LIKE.match(w)]
            if len(versions) >= 2:
                pairs.append((words[0], versions[0], versions[1]))
    deps = [{"name": name, "current": current, "latest": latest, "kind": kind_of(current, latest)} for name, current, latest in pairs]
    order = {"patch": 0, "minor": 1, "major": 2, "unknown": 3}
    return sorted((d for d in deps if d["kind"]), key=lambda d: (order[d["kind"]], d["name"].lower()))


def updates_text(deps: list[Dep]) -> str:
    """The list the owner is asked about, byte for byte: only what may be updated, in one order."""
    return json.dumps({"updates": [d for d in deps if d["kind"] in UPDATABLE]}, indent=2, ensure_ascii=False) + "\n"


def read_updates(text: str) -> list[Dep] | None:
    """The entries of updates.json, each with its class computed again; None — not such a file."""
    try:
        rows = json.loads(text)["updates"]
        return [{"name": str(r["name"]), "current": str(r["current"]), "latest": str(r["latest"]),
                 "kind": kind_of(str(r["current"]), str(r["latest"]))} for r in rows]
    except (ValueError, KeyError, TypeError):
        return None


def run_command(root: Path, command: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(["bash", "-c", command], cwd=root, capture_output=True, text=True, timeout=CMD_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return 124, f"no answer in {CMD_TIMEOUT_S} s"
    return proc.returncode, proc.stdout if proc.stdout.strip() else proc.stderr


def tail(out: str) -> str:
    return "\n".join(out.strip().splitlines()[-TAIL:])


def dep_line(dep: Dep) -> str:
    return f"- `{dep['name']}` {dep['current']} → {dep['latest']} ({KIND_WORDS[dep['kind']]})"


def dependencies(root: Path, env: dict[str, str]) -> tuple[list[str], list[Dep]]:
    """The section's lines and the outdated dependencies. Writes or removes updates.json."""
    outdated_cmd, audit_cmd = env.get("DEPS_OUTDATED_CMD", "").strip(), env.get("DEPS_AUDIT_CMD", "").strip()
    lines: list[str] = []
    deps: list[Dep] = []
    if not outdated_cmd:
        lines.append("Кроку немає: `DEPS_OUTDATED_CMD` у `.claude/project.env` порожня. Двигун сам нічого не встановлює і не вгадує.")
    else:
        _, out = run_command(root, outdated_cmd)
        deps = parse_outdated(out)
        ready = [d for d in deps if d["kind"] in UPDATABLE]
        rest = [d for d in deps if d["kind"] not in UPDATABLE]
        lines.append(f"Команда: `{outdated_cmd}`. Застаріло: {len(deps)}.")
        if ready:
            lines += ["", f"**Можна оновити після вашого «так» ({len(ready)}):** латки — однією групою, малі версії — по одній.", *map(dep_line, ready)]
        if rest:
            lines += ["", f"**У догляді не оновлюється ({len(rest)}):** кожна — окремою задачею.", *map(dep_line, rest)]
        if not deps and out.strip():
            lines += ["", "Жодної застарілої залежності у виводі не розпізнано. Кінець виводу:", "```", tail(out), "```"]
    updates = root / UPDATES_REL
    if any(d["kind"] in UPDATABLE for d in deps):
        updates.parent.mkdir(parents=True, exist_ok=True)
        updates.write_text(updates_text(deps), encoding="utf-8")
    else:
        updates.unlink(missing_ok=True)
    if audit_cmd:
        rc, out = run_command(root, audit_cmd)
        lines += ["", f"**Відомі вразливості** — `{audit_cmd}`, код завершення {rc}:", "```", tail(out) or "(порожній вивід)", "```"]
    else:
        lines += ["", "Вразливості не перевірялись: `DEPS_AUDIT_CMD` порожня."]
    return lines, deps


def question(root: Path) -> str | None:
    """The question that ends the maintenance, with the offer the runner acts on; None — nothing to ask."""
    path = root / UPDATES_REL
    deps = read_updates(hotfix.read(path))
    ready = [d for d in deps or [] if d["kind"] in UPDATABLE]
    if not ready:
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unattended"))
    import board

    asks = (f"Оновити ці {len(ready)} залежностей? Латки — однією групою, малі версії — по одній; після кожного оновлення — "
            "повний прогін тестів і gates «не гірше»; що зламало — скасовується і йде у звіт. Великі версії сюди не входять.")
    return "\n".join([asks, *("   " + dep_line(d) for d in ready), "   " + board.action_line(root, "update-deps"), "   Відповідь:"])


# ------------------------------------------------------------------ complexity, hot places, the rest


def previous_report(root: Path, today: str) -> tuple[str, dict[str, Any]]:
    """The date and the recorded numbers of the newest report before `today`; ("", {}) — the first one."""
    found = sorted(m.group(1) for p in (root / MAINTAIN_REL).glob("*.md") if (m := REPORT_NAME.match(p.name)) and m.group(1) < today)
    if not found:
        return "", {}
    match = TOTALS.search(hotfix.read(root / MAINTAIN_REL / f"{found[-1]}.md"))
    try:
        return found[-1], json.loads(match.group(1)) if match else {}
    except ValueError:
        return found[-1], {}


def delta(now: int, was: Any) -> str:
    if not isinstance(was, int):
        return f"{now}"
    return f"{now} (було {was}, {'+' if now > was else ''}{now - was})" if now != was else f"{now} (без змін)"


TOTAL_WORDS = (("files", "файлів робочого коду"), ("lines", "рядків"), ("functions", "функцій"),
               ("complexity", "функцій понад межу складності"), ("nesting", "функцій понад межу вкладеності"),
               ("dead-code", "знахідок мертвого коду"), ("duplication", "місць дублювання"), ("unused-dependency", "невживаних залежностей"))


def complexity(root: Path, env: dict[str, str], before: dict[str, Any]) -> tuple[list[str], dict[str, int], list[str]]:
    """The section's lines, the totals, and the reasons the simplifier is called for (sharp growth)."""
    production = simplify_signals.production_files(root, env, None)
    signals = simplify_signals.collect(root, env, "full", None, None, record=True)   # what `simplifier.py nightly` runs
    totals = simplify_signals.totals(root, production, signals)
    was: dict[str, Any] = before["totals"] if isinstance(before.get("totals"), dict) else {}
    lines = [f"- {words}: {delta(totals[key], was.get(key))}" for key, words in TOTAL_WORDS]
    calls = [s["message"] for s in signals if s["kind"] == "trend"]
    lines.append("- різке зростання: " + ("; ".join(calls) + " — це сигнал покликати simplifier-а (`simplifier.py request --lens code`)" if calls else "немає"))
    return lines, totals, calls


def hot_places(root: Path, env: dict[str, str]) -> list[tuple[str, int, int]]:
    """(file, changes in the last HOT_DAYS days, its highest cyclomatic complexity) — files that
    change often and hold a function over the limit, the hottest first."""
    log = budget.git(root, "log", f"--since={HOT_DAYS}.days", "--name-only", "--format=")
    changes = Counter(line.strip() for line in log.splitlines() if line.strip())
    limit = simplify_signals.limits_of(env)["max_cyclomatic_per_function"]
    found = []
    for rel in simplify_signals.production_files(root, env, None):
        tree = budget.parse_py(hotfix.read(root / rel))
        worst = max((values[0] for values in budget.function_metrics(tree).values()), default=0) if tree else 0
        if changes[rel] >= HOT_MIN_CHANGES and worst > limit:
            found.append((rel, changes[rel], worst))
    return sorted(found, key=lambda f: (-f[1] * f[2], f[0]))


def snapshot(root: Path, before: dict[str, Any]) -> tuple[list[str], list[int] | None]:
    current, problem = baseline.load(root)
    if current is None:
        return [f"Знімка «як було» немає{f' ({problem})' if problem else ''}: gates вимагають чистого."], None
    left = list(baseline.remaining(current))
    was = before.get("baseline")
    words = ("старих падінь тестів", "зауважень лінтера", "зауважень типів")
    lines = [f"- {word}: {delta(n, was[i] if isinstance(was, list) and len(was) == 3 else None)}" for i, (word, n) in enumerate(zip(words, left, strict=True))]
    if isinstance(was, list) and len(was) == 3:
        lines.append(f"- прибрано з минулого звіту: {max(0, sum(was) - sum(left))}")
    return lines, left


def debts(root: Path, today: date) -> tuple[list[str], list[hotfix.Debt]]:
    open_debts = [d for d in hotfix.debts(hotfix.read(root / hotfix.DEBT_REL)) if d.open]
    late = [d for d in open_debts if d.overdue(today)]
    lines = [f"Відкрито: {len(open_debts)} з {hotfix.MAX_OPEN}; прострочено: {len(late)}."]
    lines += [f"- {'ПРОСТРОЧЕНО — ' if d in late else ''}`{d.name}`: строк {d.due}, commit {d.commit}, продовження: {d.followup}" for d in open_debts]
    return lines, late


def lessons(root: Path) -> tuple[list[str], str]:
    queue = lesson_queue.entries(root)
    proposals = len(lesson_queue.pending_proposals(root))
    due = lesson_queue.cleanup_due(root)
    lines = [f"- кандидатів у черзі: {len(queue)}" + (f", найстаріший від {queue[0]['date']}" if queue else ""),
             f"- пропозицій правил, що чекають вашої відповіді: {proposals}",
             f"- прибирання пам'яті: {'час — ' + due if due else 'ще не час'}"]
    return lines, due


def proposals(deps: list[Dep], hot: list[tuple[str, int, int]], calls: list[str], left: list[int] | None,
              late: list[hotfix.Debt], due: str) -> list[str]:
    """Everything worth work, as task proposals: maintenance itself removes and tidies nothing."""
    out = [f"Оновити `{d['name']}` {d['current']} → {d['latest']} ({KIND_WORDS[d['kind']]}) — окрема задача: прочитати, що зламано навмисно."
           for d in deps if d["kind"] not in UPDATABLE]
    out += [f"Спростити `{rel}`: змінювався {n} разів за {HOT_DAYS} днів, найскладніша функція — {worst}." for rel, n, worst in hot[:HOT_SHOWN]]
    if calls:
        out.append("Покликати simplifier-а на різке зростання: " + "; ".join(calls) + ".")
    if left and left[0]:
        out.append(f"Полагодити старі падіння тестів зі знімка «як було» ({left[0]}): `python3 .claude/hooks/baseline.py show`.")
    out += [f"Закрити прострочений борг термінового виправлення `{d.name}` (строк {d.due}): {d.followup}." for d in late]
    if due:
        out.append(f"Прибрати пам'ять і розібрати чергу уроків ({due}).")
    return out


def report(root: Path, today: str) -> Path:
    env = budget.project_env(root)
    was_date, before = previous_report(root, today)
    dep_lines, deps = dependencies(root, env)
    complexity_lines, totals, calls = complexity(root, env, before)
    hot = hot_places(root, env)
    snapshot_lines, left = snapshot(root, before)
    debt_lines, late = debts(root, date.fromisoformat(today))
    lesson_lines, due = lessons(root)
    tasks = proposals(deps, hot, calls, left, late, due)
    ready = sum(d["kind"] in UPDATABLE for d in deps)
    text = "\n".join([
        f"# Догляд {today}", "",
        ("Написано `python3 .claude/hooks/maintain.py report`. Догляд нічого не видаляє, не впорядковує і не оновлює: "
         "усе, що варте роботи, — пропозиції задач унизу."),
        f"Порівняння — з минулим звітом від {was_date}." if was_date else "Це перший звіт: порівнювати ще ні з чим.", "",
        "## Залежності", "", *dep_lines, "",
        "## Складність проти минулого звіту", "", *complexity_lines, "",
        "## Гарячі місця", "",
        f"Файли, що змінювались щонайменше {HOT_MIN_CHANGES} рази за {HOT_DAYS} днів і мають функцію понад межу складності.",
        *([f"- `{rel}`: змін {n}, найскладніша функція {worst}" for rel, n, worst in hot[:HOT_SHOWN]] or ["- немає"]), "",
        "## Знімок «як було»", "", *snapshot_lines, "",
        "## Борги термінових виправлень", "", *debt_lines, "",
        "## Черга уроків", "", *lesson_lines, "",
        "## Пропозиції задач", "", *([f"{i}. {line}" for i, line in enumerate(tasks, 1)] or ["Немає."]), "",
        "## Питання до власника", "",
        (f"Оновити ці {ready} залежностей? Питання з переліком і рядком дії — `python3 .claude/hooks/maintain.py question`; "
         f"перелік — `{UPDATES_REL}`." if ready else "Немає: оновлювати нічого."), "",
        f"<!-- maintain-totals: {json.dumps({'totals': totals, 'baseline': left}, ensure_ascii=False)} -->", ""])
    path = root / MAINTAIN_REL / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report").add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"), type=lambda s: date.fromisoformat(s).isoformat())
    sub.add_parser("question")
    args = parser.parse_args(argv)
    root = budget.project_root()
    if args.command == "question":
        text = question(root)
        if text is None:
            print(f"maintain: nothing to update ({UPDATES_REL} is absent or lists no patch or minor version); no question", file=sys.stderr)
            return EXIT_NOTHING
        print(text)
        return 0
    path = report(root, args.date)
    print(f"maintain: {path.relative_to(root)} written")
    if (root / UPDATES_REL).is_file():
        print(f"maintain: {UPDATES_REL} lists what may be updated; end with the question — python3 .claude/hooks/maintain.py question")
    return 0


if __name__ == "__main__":
    sys.exit(main())
