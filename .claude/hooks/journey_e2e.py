#!/usr/bin/env python3
"""The journeys as the condition of «done»: a feature a person sees or talks to closes only when its
journeys passed on the deployed revision, and the conversation corpus passed with the real model.

    python3 .claude/hooks/journey_e2e.py close <feature>                 # 0 may close, 3 may not (also `testing.py journey-close`)
    python3 .claude/hooks/journey_e2e.py request <feature> --service S --region R   # the operator's request, printed
    python3 .claude/hooks/journey_e2e.py operator-run <feature> --service S --region R [--project P]
    python3 .claude/hooks/journey_e2e.py seal-complaints                 # the owner's complaints, sealed row by row
    python3 .claude/hooks/journey_e2e.py calibration                     # the judge against the owner's labels

WHY (board 317; docs/research/2026-11-userflow/R2-journey-e2e.md). mamamemory's smoke checked one
phrase of the model with no state, and was green the evening the owner said «які плани?» went in as the
answer to the question on the screen: a phrase reached the model with `replyTo` of the last question.
Nothing walked the journey on the deployed app. Three layers, each read here from files the operator's
run leaves in `.engine/e2e/<sha>/` — the deploy, the real model and the browser are the operator's, never
the agent's (`.claude/references/e2e.md`):

  * C — THE CORPUS. `conversation.py run --k 3 --out …/corpus-results.json` (board 209's corpus: the
    model's cases and every owner complaint, forever) with the real model, no browser. Red: any red case,
    k < 3, a corpus other than the one in the tree, a complaint not in the corpus, a sealed complaint
    changed or gone. Only for a product with a conversation model.
  * J — THE JOURNEYS. One Playwright spec per journey (`e2e/J-N[-name].spec.ts`), written by the tester
    in mode `journey` blind to the code and sealed like contract tests, run on a tagged revision with no
    traffic (`--no-traffic --tag`), on a phone's screen, `--repeat-each=3 --retries=0`, JSON reporter
    into `…/results.json`. Red: a journey of the feature with no spec in the report, a test flaky, skipped
    (`skip`/`fixme` — Playwright's healer skips what it thinks broken), failed, run fewer than 3 times,
    retries above 0, a spec not sealed or changed since its seal.
  * THE JUDGE — Claude, pass/fail per journey run (`…/judge.json`). Its FAIL blocks only after it agrees
    with the owner: ≥ 20 labels in `.engine/journeys/judge-labels.jsonl`, precision and recall of «fail»
    ≥ 0.9. Before that a FAIL is a finding for the owner, printed, not a block, never silent.

WHICH REVISION. A directory `.engine/e2e/<sha>/` counts when, since that commit, nothing changed but the
records (`tasks/`, `.engine/` outside the journeys and the architecture; the owner's judge labels, written
after a run, are a record too): results of another commit are
refused with the files that changed since. The corpus results name their sha; it must be the same.

THE OPERATOR'S RUN. `operator-run` is the sequence the operator runs (never an agent: refused inside a
Claude Code session): the tagged deploy, the corpus, Playwright, the project's clean-up of its test records
(`E2E_CLEANUP_CMD`, mandatory: the tests write into the owner's own account, marked by a prefix), then
`close`, and only on 0 the traffic moves to the tag. Any red: the old revision keeps the traffic.

State: .claude/state/e2e/ (the complaints' seal). Exit: 0 fine, 2 usage, 3 blocked. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goals  # the project root: one reading of it
import journeys  # the journeys' files and the sections of a document

JsonObj = dict[str, Any]

E2E_REL = ".engine/e2e"
RESULTS, CORPUS_RESULTS, JUDGE = "results.json", "corpus-results.json", "judge.json"
SPEC_DIR = "e2e"
FEATURES_REL = ".engine/architecture/feature"
MODEL_REL = ".engine/architecture/conversation-model.json"
CORPUS_REL = "tests/conversations/corpus.json"
COMPLAINTS_REL = "tests/conversations/complaints.json"
LABELS_REL = ".engine/journeys/judge-labels.jsonl"
SEALS_REL = Path(".claude/state/testing/seals")
COMPLAINT_SEAL_REL = Path(".claude/state/e2e/complaints.json")
ENV_REL = ".claude/project.env"
MIN_RUNS = 3            # pass^3 (R2 §1.3): one green run of a conversation proves nothing
MIN_LABELS = 20         # the judge blocks only after this many owner labels
CALIBRATED = 0.9        # … and precision and recall of «fail» at least this
RECORDS = ("tasks/", ".engine/")
NOT_RECORDS = (".engine/journeys/", ".engine/architecture/")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
TECH = re.compile(r"^\s*[-*]?\s*\[(?:тех|tech)\]")
EXIT_OK, EXIT_USAGE, EXIT_BLOCKED = 0, 2, 3


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(root), *args], capture_output=True, text=True,
                          errors="replace", check=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_env(root: Path) -> dict[str, str]:
    path = root / ENV_REL
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        match = re.match(r"^\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if match:
            value = match.group(2).strip()
            out[match.group(1)] = value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    return out


# ------------------------------------------------------------------ what the feature promises


def feature_journeys(root: Path, feature: str) -> list[int] | None:
    """The journeys the feature's acceptance criteria cite (`J-N#AC-k`), `[тех]` lines aside; None: no artifact."""
    path = root / FEATURES_REL / f"{feature}.md"
    if not path.is_file():
        return None
    body = journeys.section(path.read_text(encoding="utf-8", errors="replace"), "Acceptance criteria", "Критерії приймання")
    return sorted({int(n) for line in body.splitlines() if not TECH.match(line) for n in journeys.J_REF.findall(line)})


def spec_of(rel: str) -> int | None:
    """The journey a spec file walks, by its name: `e2e/J-3.spec.ts`, `e2e/J-3-add-task.spec.ts`."""
    match = re.match(r"^J-(\d+)(?:[-.][^/]*)?\.spec\.[cm]?[jt]s$", Path(rel).name)
    return int(match[1]) if match else None


# ------------------------------------------------------------------ which revision was tested


def changed_since(root: Path, sha: str) -> list[str]:
    """Paths that differ between the commit and the tree now (untracked files too), records aside."""
    paths = git(root, "diff", "--name-only", "--no-renames", sha, "--").stdout.splitlines()
    paths += git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    return sorted({p for p in paths if p and p != LABELS_REL and not (p.startswith(RECORDS) and not p.startswith(NOT_RECORDS))})


def tested_revision(root: Path) -> tuple[str | None, list[str]]:
    """The results directory whose commit is the code in the tree now, or why none is."""
    folder = root / E2E_REL
    found = sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
    why = []
    for path in found:
        if not SHA_RE.match(path.name) or git(root, "rev-parse", "--verify", "--quiet", f"{path.name}^{{commit}}").returncode != 0:
            why.append(f"{E2E_REL}/{path.name}: not a commit of this repository")
            continue
        changed = changed_since(root, path.name)
        if not changed:
            return path.name, []
        why.append(f"{E2E_REL}/{path.name}: the results of another commit — since it, changed: " + ", ".join(changed[:8])
                   + (f" and {len(changed) - 8} more" if len(changed) > 8 else ""))
    return None, why or [f"no results at all: {E2E_REL}/<sha>/ is written by the operator's run (`.claude/references/e2e.md`)"]


# ------------------------------------------------------------------ J: the Playwright report


def walk_suites(suites: Any, file: str = "") -> list[tuple[str, JsonObj]]:
    """(spec file, spec) for every spec of the report, nested suites included."""
    out: list[tuple[str, JsonObj]] = []
    for suite in suites if isinstance(suites, list) else []:
        if not isinstance(suite, dict):
            continue
        here = str(suite.get("file") or file)
        out += [(here, spec) for spec in suite.get("specs") or [] if isinstance(spec, dict)]
        out += walk_suites(suite.get("suites"), here)
    return out


def config_errors(report: JsonObj) -> list[str]:
    projects = [p for p in (report.get("config") or {}).get("projects") or [] if isinstance(p, dict)]
    if not projects:
        return ["results.json: no `config.projects` — not a report of Playwright's JSON reporter"]
    errors = [f"project {p.get('name') or '(unnamed)'}: retries {p.get('retries')} — the run is `--retries=0`: a test green on a retry "
              "is flaky, and flaky is red" for p in projects if p.get("retries") not in (0, None)]
    errors += [f"project {p.get('name') or '(unnamed)'}: repeatEach {p.get('repeatEach')} — the run is `--repeat-each={MIN_RUNS}`"
               for p in projects if int(p.get("repeatEach") or 1) < MIN_RUNS]
    return errors


def spec_errors(title: str, spec: JsonObj) -> tuple[list[str], int]:
    """What is wrong with one spec's tests, and how many runs it had (first attempts, every project)."""
    errors, runs = [], 0
    for test in spec.get("tests") or []:
        if not isinstance(test, dict):
            continue
        status = test.get("status")
        marks = [a.get("type") for a in test.get("annotations") or [] if isinstance(a, dict) and a.get("type") in ("skip", "fixme", "fail")]
        results = [r for r in test.get("results") or [] if isinstance(r, dict)]
        runs += sum(1 for r in results if int(r.get("retry") or 0) == 0)
        if status == "flaky" or any(int(r.get("retry") or 0) > 0 for r in results):
            errors.append(f"{title}: FLAKY — failed and passed on a retry; for a person that is one time in N they get stuck")
        elif status == "skipped" or marks:
            errors.append(f"{title}: SKIPPED ({', '.join(m for m in marks if m) or 'skipped'}) — a journey test that does not run proves nothing")
        elif status != "expected":
            failed = [str((r.get("error") or {}).get("message", "")).strip() for r in results if r.get("status") != "passed"]
            errors.append(f"{title}: {status or 'no status'} — {next((m for m in failed if m), 'no message')[:300]}")
    return list(dict.fromkeys(errors)), runs


def playwright_errors(report: Any, wanted: list[int]) -> tuple[list[str], dict[int, int]]:
    if not isinstance(report, dict):
        return ["results.json is missing or not JSON (Playwright: `--reporter=json`, PLAYWRIGHT_JSON_OUTPUT_NAME)"], {}
    errors = config_errors(report)
    runs: dict[int, int] = {}
    for file, spec in walk_suites(report.get("suites")):
        number = spec_of(file)
        if number is None:
            continue
        found, count = spec_errors(f"J-{number} «{spec.get('title', '')}» ({file})", spec)
        errors += found
        runs[number] = min(runs.get(number, count), count)   # every test of the journey ran at least this often
    for number in wanted:
        if number not in runs:
            errors.append(f"J-{number}: not in the report — the feature cites it, and no spec `{SPEC_DIR}/J-{number}[-name].spec.ts` ran")
        elif runs[number] < MIN_RUNS:
            errors.append(f"J-{number}: {runs[number]} run(s) of a test — fewer than {MIN_RUNS} (pass^{MIN_RUNS})")
    return errors, runs


def sealed_specs(root: Path) -> dict[str, str]:
    """rel -> sha256 of every sealed test file (testing.py's seals): a journey spec is sealed like contract tests."""
    out: dict[str, str] = {}
    folder = root / SEALS_REL
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        files = (read_json(path) or {}).get("files")
        out |= files if isinstance(files, dict) else {}
    return out


def seal_errors(root: Path, wanted: list[int]) -> list[str]:
    sealed = sealed_specs(root)
    errors = []
    for number in wanted:
        specs = sorted(p.relative_to(root).as_posix() for p in (root / SPEC_DIR).glob(f"J-{number}*.spec.*") if spec_of(p.name) == number)
        if not specs:
            errors.append(f"J-{number}: no spec file in {SPEC_DIR}/ — the tester writes it (`testing.py request <slug> --tester journey`)")
        for rel in specs:
            if rel not in sealed:
                errors.append(f"{rel}: NOT SEALED — a journey spec is the tester's hand-in, sealed like contract tests")
            elif digest((root / rel).read_bytes()) != sealed[rel]:
                errors.append(f"{rel}: CHANGED since its seal — nobody fits a spec to the code; a change the owner allowed is "
                              "`testing.py reseal <slug> --owner-answer <card>`")
    return errors


# ------------------------------------------------------------------ C: the corpus


def complaint_rows(root: Path) -> dict[str, str]:
    found = read_json(root / COMPLAINTS_REL)
    return {str(c.get("id")): digest(json.dumps(c, sort_keys=True, ensure_ascii=False).encode()) for c in found
            if isinstance(c, dict)} if isinstance(found, list) else {}


def complaint_seal_errors(root: Path) -> list[str]:
    """A sealed complaint is never changed or removed: a line of the corpus goes only by the owner's word."""
    sealed = read_json(root / COMPLAINT_SEAL_REL) or {}
    now = complaint_rows(root)
    return [f"complaint {cid}: {'REMOVED' if cid not in now else 'CHANGED'} after its seal — a line of the corpus goes only by the "
            "owner's word" for cid, value in sorted(sealed.items()) if now.get(cid) != value]


def seal_complaints(root: Path) -> tuple[int, str]:
    errors = complaint_seal_errors(root)
    if errors:
        return EXIT_BLOCKED, "NOT SEALED:\n- " + "\n- ".join(errors)
    sealed = read_json(root / COMPLAINT_SEAL_REL) or {}
    rows = complaint_rows(root)
    new = sorted(set(rows) - set(sealed))
    path = root / COMPLAINT_SEAL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sealed | rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return EXIT_OK, f"complaints sealed: {len(rows)} ({', '.join(new) or 'none new'})"


def corpus_errors(root: Path, sha: str, results: Any) -> list[str]:
    if not (root / MODEL_REL).is_file():
        return []
    corpus = root / CORPUS_REL
    if not corpus.is_file():
        return [f"{CORPUS_REL}: missing — `conversation.py gen` writes it from the model and the complaints"]
    errors = complaint_seal_errors(root)
    cases = read_json(corpus) or []
    have = {str(c.get("id")) for c in cases if isinstance(c, dict)}
    errors += [f"complaint {cid}: not in the corpus — run `conversation.py gen` after a complaint" for cid in sorted(complaint_rows(root))
               if f"owner-{cid}" not in have]
    if not isinstance(results, dict):
        return [*errors, f"{CORPUS_RESULTS}: missing — `conversation.py run --k {MIN_RUNS} --out {E2E_REL}/<sha>/{CORPUS_RESULTS}`"]
    ran = str(results.get("sha") or "")
    if not ran or not (ran.startswith(sha) or sha.startswith(ran)):
        errors.append(f"{CORPUS_RESULTS}: run on {results.get('sha')}, not on {sha}")
    if results.get("corpus_sha256") != digest(corpus.read_bytes()):
        errors.append(f"{CORPUS_RESULTS}: run on another corpus than {CORPUS_REL} in the tree")
    if int(results.get("k") or 0) < MIN_RUNS:
        errors.append(f"{CORPUS_RESULTS}: k = {results.get('k')} — fewer than {MIN_RUNS} (pass^{MIN_RUNS})")
    errors += [f"corpus RED {r.get('id')} [{r.get('state')}] «{r.get('phrase')}»: expected {json.dumps(r.get('expect'), ensure_ascii=False)}, "
               f"seen {json.dumps(r.get('seen'), ensure_ascii=False)}" for r in results.get("red") or [] if isinstance(r, dict)]
    return errors


# ------------------------------------------------------------------ the judge


def calibration(root: Path) -> JsonObj:
    """The judge against the owner's labels: precision and recall of «fail»; calibrated only with enough of both."""
    path = root / LABELS_REL
    labels = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("owner") in ("pass", "fail") and row.get("judge") in ("pass", "fail"):
            labels.append(row)
    both = sum(1 for r in labels if r["owner"] == r["judge"] == "fail")
    said_fail = sum(1 for r in labels if r["judge"] == "fail")
    is_fail = sum(1 for r in labels if r["owner"] == "fail")
    precision = both / said_fail if said_fail else 0.0
    recall = both / is_fail if is_fail else 0.0
    return {"labels": len(labels), "precision": round(precision, 3), "recall": round(recall, 3),
            "calibrated": len(labels) >= MIN_LABELS and precision >= CALIBRATED and recall >= CALIBRATED}


def judge_findings(root: Path, verdicts: Any) -> tuple[list[str], list[str]]:
    """(blocks, findings): a judge FAIL blocks once calibrated; before that it is a finding for the owner."""
    fails = [f"judge FAIL {v.get('journey')} run {v.get('run')}: {str(v.get('why', ''))[:300]}" for v in verdicts or []
             if isinstance(v, dict) and v.get("verdict") == "fail"] if isinstance(verdicts, list) else []
    if not fails:
        return [], []
    calibrated = calibration(root)
    if calibrated["calibrated"]:
        return fails, []
    return [], [f"{f} — a FINDING for the owner, not a block: the judge has {calibrated['labels']} label(s) of the owner, precision "
                f"{calibrated['precision']}, recall {calibrated['recall']} (blocks from {MIN_LABELS} labels and {CALIBRATED})" for f in fails]


# ------------------------------------------------------------------ close


def close(root: Path, feature: str) -> tuple[int, str, JsonObj]:
    """Whether the feature may close on its journeys: (exit, text, what was seen — for the ledger)."""
    wanted = feature_journeys(root, feature)
    if wanted is None:
        return EXIT_USAGE, f"no such feature artifact: {FEATURES_REL}/{feature}.md", {}
    if not wanted:
        return EXIT_OK, f"the feature {feature} cites no journey (`J-N#AC-k`): nothing for the journeys to close", {}
    sha, why = tested_revision(root)
    problems = seal_errors(root, wanted)
    if sha is None:
        return EXIT_BLOCKED, f"BLOCKED: the journeys of {feature} were not run on the code in the tree:\n- " + "\n- ".join([*why, *problems]), {}
    folder = root / E2E_REL / sha
    found, runs = playwright_errors(read_json(folder / RESULTS), wanted)
    problems += found + corpus_errors(root, sha, read_json(folder / CORPUS_RESULTS))
    blocks, findings = judge_findings(root, read_json(folder / JUDGE))
    problems += blocks
    seen = {"sha": sha, "journeys": [f"J-{n}" for n in wanted], "runs": {f"J-{n}": runs.get(n, 0) for n in wanted}, "findings": findings}
    tail = ("\nFINDINGS for the owner:\n- " + "\n- ".join(findings)) if findings else ""
    if problems:
        return EXIT_BLOCKED, f"BLOCKED: the feature {feature} does not close on its journeys (rev {sha[:12]}):\n- " + "\n- ".join(problems) + tail, seen
    corpus = "; corpus green" if (root / MODEL_REL).is_file() else ""
    return EXIT_OK, (f"the journeys of {feature} pass: " + ", ".join(f"J-{n} {runs[n]}/{runs[n]}" for n in wanted)
                     + f" on rev {sha[:12]}{corpus}" + tail), seen


# ------------------------------------------------------------------ the operator


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def steps(root: Path, feature: str, service: str, region: str, project: str) -> list[tuple[str, list[str]]]:
    """The operator's sequence, as argv lists; `{url}` is filled in after the deploy."""
    sha = head(root)
    tag, out = f"e2e-{sha[:7]}", f"{E2E_REL}/{sha}"
    where = ["--region", region] + (["--project", project] if project else [])
    plan = [("deploy", ["gcloud", "run", "deploy", service, "--source", ".", *where, "--no-traffic", "--tag", tag, "--quiet"]),
            ("url", ["gcloud", "run", "services", "describe", service, *where, "--format=json"])]
    if (root / MODEL_REL).is_file():
        plan.append(("corpus", [sys.executable, ".claude/hooks/conversation.py", "run", "--k", str(MIN_RUNS), "--out", f"{out}/{CORPUS_RESULTS}"]))
    plan += [("journeys", ["npx", "playwright", "test", f"{SPEC_DIR}/", f"--repeat-each={MIN_RUNS}", "--retries=0", "--reporter=json"]),
             ("close", [sys.executable, ".claude/hooks/journey_e2e.py", "close", feature]),
             ("traffic", ["gcloud", "run", "services", "update-traffic", service, *where, f"--to-tags={tag}=100"])]
    return plan


def request_text(root: Path, feature: str, service: str, region: str, project: str) -> str:
    sha = head(root)
    cleanup = load_env(root).get("E2E_CLEANUP_CMD", "").strip()
    lines = [f"# Запит: {feature} — journeys на тегованій ревізії {sha[:7]}", "",
             f"Проєкт: `{root}`. Ревізія: `{sha}`.", "",
             "Що зробити — одна команда, у терміналі оператора (не в сесії агента):", "",
             f"```bash\ncd {shlex.quote(str(root))} && python3 .claude/hooks/journey_e2e.py operator-run {shlex.quote(feature)} "
             f"--service {shlex.quote(service)} --region {shlex.quote(region)}" + (f" --project {shlex.quote(project)}" if project else "") + "\n```", "",
             "Вона робить по черзі (зупиняється на першій помилці):"]
    lines += [f"{n}. `{shlex.join(argv)}`" for n, (_, argv) in enumerate(steps(root, feature, service, region, project), 1)]
    lines += ["", f"Після Playwright завжди — прибирання тестових записів: `{cleanup or 'E2E_CLEANUP_CMD не задано: команда відмовиться'}`.",
              "Трафік переходить на тег лише тоді, коли `close` = 0 (корпус і journeys зелені); інакше стара ревізія лишається.", "",
              f"Успіх: `{E2E_REL}/{sha}/` з `{RESULTS}`" + (f" і `{CORPUS_RESULTS}`" if (root / MODEL_REL).is_file() else "")
              + ", рядок `the journeys of … pass` у виводі, трафік на теговій ревізії.",
              "Невдача: вивід `close` дослівно і traces Playwright (`test-results/`) — у відповідь; трафік не чіпати."]
    return "\n".join(lines)


def tag_url(described: str, tag: str) -> str:
    try:
        traffic = (json.loads(described).get("status") or {}).get("traffic") or []
    except (ValueError, AttributeError):
        return ""
    return next((str(t.get("url")) for t in traffic if isinstance(t, dict) and t.get("tag") == tag and t.get("url")), "")


def run_step(root: Path, argv: list[str], env: dict[str, str] | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("$ " + shlex.join(argv), flush=True)
    return subprocess.run(argv, cwd=root, env=os.environ | (env or {}), text=True, check=False,
                          stdout=subprocess.PIPE if capture else None)


def operator_run(root: Path, feature: str, service: str, region: str, project: str) -> int:
    """The operator's sequence. Refused inside a Claude Code session: deploying is not the agent's act."""
    if os.environ.get("CLAUDECODE"):
        print("REFUSED inside a Claude Code session (CLAUDECODE is set): the tagged deploy and the run on the real model are the "
              "operator's — the agent writes the request (`journey_e2e.py request`), the operator runs this", file=sys.stderr)
        return EXIT_USAGE
    cleanup = load_env(root).get("E2E_CLEANUP_CMD", "").strip()
    if not cleanup:
        print(f"REFUSED: E2E_CLEANUP_CMD is empty in {ENV_REL} — the journeys write into the owner's account, and every run "
              "removes its own records (marked by the prefix) afterwards", file=sys.stderr)
        return EXIT_USAGE
    sha = head(root)
    tag, out = f"e2e-{sha[:7]}", root / E2E_REL / sha
    out.mkdir(parents=True, exist_ok=True)
    url = ""
    for name, argv in steps(root, feature, service, region, project):
        if name == "url":
            described = run_step(root, argv, capture=True)
            url = tag_url(described.stdout or "", tag)
            if not url:
                print(f"STOPPED: no URL for the tag {tag} in `gcloud run services describe`", file=sys.stderr)
                return EXIT_BLOCKED
            continue
        if name == "journeys":
            try:
                done = run_step(root, argv, {"BASE_URL": url, "PLAYWRIGHT_JSON_OUTPUT_NAME": str(out / RESULTS), "E2E_REVISION": sha})
            finally:
                run_step(root, ["bash", "-c", cleanup])
            if done.returncode != 0:
                print(f"journeys red (exit {done.returncode}); `close` says why", file=sys.stderr)
            continue
        done = run_step(root, argv)
        if done.returncode != 0 and name != "corpus":
            print(f"STOPPED at {name} (exit {done.returncode}): the traffic stays on the old revision", file=sys.stderr)
            return EXIT_BLOCKED
    print(f"the traffic is on {tag}")
    return EXIT_OK


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("close").add_argument("feature")
    for name in ("request", "operator-run"):
        p = sub.add_parser(name)
        p.add_argument("feature")
        p.add_argument("--service", required=True)
        p.add_argument("--region", required=True)
        p.add_argument("--project", default="")
    sub.add_parser("seal-complaints")
    sub.add_parser("calibration")
    args = parser.parse_args(argv)
    root = goals.project_root()
    if args.command == "close":
        code, text, _ = close(root, args.feature)
        print(text, file=sys.stdout if code == EXIT_OK else sys.stderr)
        return code
    if args.command == "request":
        print(request_text(root, args.feature, args.service, args.region, args.project))
        return EXIT_OK
    if args.command == "operator-run":
        return operator_run(root, args.feature, args.service, args.region, args.project)
    if args.command == "seal-complaints":
        code, text = seal_complaints(root)
        print(text, file=sys.stdout if code == EXIT_OK else sys.stderr)
        return code
    print(json.dumps(calibration(root), indent=1))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
