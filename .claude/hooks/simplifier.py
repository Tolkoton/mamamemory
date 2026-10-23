#!/usr/bin/env python3
"""simplifier.py — everything deterministic around the simplifier agent (.claude/agents/simplifier.md).

    python3 .claude/hooks/simplifier.py request --lens code|requirements|architecture|instructions|budget ... [--paths P ...]
    python3 .claude/hooks/simplifier.py validate FINDINGS.json [--request FILE] [--out FILE]
    python3 .claude/hooks/simplifier.py route FINDINGS.json [--request FILE] --title "what was reviewed"
    python3 .claude/hooks/simplifier.py accept --reason "why the excess is needed" --verdict FINDINGS.json
    python3 .claude/hooks/simplifier.py reversals [--last N] [--record]
    python3 .claude/hooks/simplifier.py decide FINDING_ID так|ні
    python3 .claude/hooks/simplifier.py applied FINDING_ID --note "what was changed in the plan"
    python3 .claude/hooks/simplifier.py nightly [--paths P ...]

The agent judges; this script decides what its judgement may DO. Read .claude/references/simplifier.md
for the whole procedure. In short:

request    the text to start the agent with: the lens, the scope, the deterministic signals
           (simplify_signals.py) and, for the budget lens, the figures of the overrun.
validate   the agent's answer must be a JSON list of findings, nothing else. Each finding has
           target, category, claim, evidence, protected, chesterton_checked, test_safety,
           proposed_action, traceability, reversal_risk. A finding that breaks the schema is
           REJECTED; one that claims more than it may is LOWERED, with a note:
             - a protected path is never auto_remove (and `protected` is recomputed here);
             - code with test_safety none is never above flag_only;
             - auto_remove needs chesterton_checked and a reversal_risk that is not high;
             - every evidence item cites a signal id that exists, a file:line that exists, or
               says "judgement";
             - a path is judged as the project sees it: an absolute one, `./`, `..` or a link is
               rewritten relative to the root first, and one that leads outside is rejected.
route      confirm and flag_only go to the owner's report (.engine/simplifier/report.md) and to
           the lesson queue; nothing is removed. auto_remove findings are listed for the builder.
accept     a budget overrun the simplifier found justified: refused while its verdict holds a
           finding above flag_only; writes the reason next to the contract
           (.engine/slices/overruns/<slug>.md — the contract itself is sealed) and in the ledger.
reversals  how many removals (commits with the trailer `Simplifier-Finding: <id>`) came back:
           reverted, or the removed lines are in the file again. Outside 5-20 % of the last N
           the owner gets a note: bolder, or more careful.
decide     the owner's «так» or «ні» on a confirm finding, written to
           .engine/simplifier/decisions.jsonl (`delete_guard.py confirm` records the owner's confirmation so).
applied    the architect's own mark, between design levels: a finding about the draft plan that
           the architect already applied. Its line in the report stops reading as an open
           finding and its lesson candidate leaves the queue. Refused for code (that is a
           removal) and for a protected path; a finding about what the owner asked for is the
           owner's (Art. 5) and is never marked this way.
nightly    the full signals with the history recorded; says whether the simplifier is called.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import complexity_budget as budget
import journal
import lesson_queue
import simplify_signals

Finding = dict[str, Any]
CATEGORIES = ("dead_code", "premature_abstraction", "defensive_for_impossible", "redundant_dependency",
              "speculative_slice", "invented_requirement", "verbose_output", "duplication", "shallow_module")
TEST_SAFETY = ("none", "characterization_exists", "mutation_verified")
ACTIONS = ("flag_only", "confirm", "auto_remove")  # weakest first: a finding is only ever lowered
RISKS = ("low", "medium", "high")
EVIDENCE_SOURCES = ("signal", "read", "grep", "judgement")
TEXT_FIELDS = ("target", "claim", "traceability")
FIELDS = (*TEXT_FIELDS, "category", "evidence", "protected", "chesterton_checked", "test_safety",
          "proposed_action", "reversal_risk")
LENSES = ("code", "requirements", "architecture", "instructions", "budget")
# Never removed without a human: what defines the gates, what the deny hooks guard, what a
# measurement is compared with. SIMPLIFIER_PROTECTED in project.env adds the project's own.
PROTECTED = (".claude/constitution.md", ".claude/settings*.json", ".claude/ownership.txt",
             ".claude/hooks/block-dangerous.sh", ".claude/hooks/protect-paths.sh", ".claude/hooks/park-ask-gated.py",
             ".github/**", "**/migrations/**", "**/.env*", "secrets/**", "**/*.lock", "evals/baseline/**",
             "tests/fixtures/**",
             # the owner's goals (level 0): a finding about them is a question to the owner, never a removal
             ".engine/goals.md")
REPORT_REL = Path(".engine/simplifier/report.md")
DECISIONS_REL = Path(".engine/simplifier/decisions.jsonl")
LEDGER_REL = Path(".engine/overseer/ledger.md")
OVERRUNS_REL = Path(".engine/slices/overruns")
TRAILER_RE = re.compile(r"^Simplifier-Finding:\s*(?P<id>\S+)\s*$", re.MULTILINE)
REF_RE = re.compile(r"^(?P<path>[^:]+?)(?::(?P<line>\d+)(?:-\d+)?)?(?:::[\w.]+)?$")
CORRIDOR = (5, 20)
MIN_SAMPLE = 10
RETURNED_SHARE = 0.6
MIN_LINE = 12


def glob_match(pattern: str, rel: str) -> bool:
    """`*` stays inside a directory, `**/` crosses any number of them, a trailing `/**` is everything under."""
    regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(regex, rel) is not None


def is_protected(env: dict[str, str], rel: str) -> bool:
    extra = [p for p in re.split(r"[\s,]+", env.get("SIMPLIFIER_PROTECTED", "")) if p]
    return any(glob_match(pattern, rel) for pattern in (*PROTECTED, *extra))


def is_code(env: dict[str, str], rel: str) -> bool:
    extensions = [e.lstrip(".").lower() for e in re.split(r"[\s,]+", env.get("CODE_EXTENSIONS", "")) if e] or ["py", "sh"]
    return Path(rel).suffix.lstrip(".").lower() in extensions


def parse_answer(text: str) -> list[Any]:
    """The agent's answer as a list. One code fence around the JSON is forgiven; prose is not."""
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", body, re.DOTALL)
    data = json.loads(fenced.group(1) if fenced else body)
    if not isinstance(data, list):
        raise json.JSONDecodeError("the answer is not a JSON list of findings", body, 0)
    return data


def _project_ref(root: Path, ref: str) -> str | None:
    """`ref` with its path as the project sees it — relative to the root, links and `..` resolved,
    the way the protected zones are written. None: not a reference, a symlink loop, or it leads outside the project."""
    match = REF_RE.match(ref.strip())
    if not match:
        return None
    try:
        # Not resolve(): up to Python 3.12 it is this realpath() and a stat() that turns ELOOP into RuntimeError,
        # from 3.13 the stat() is gone and a loop comes back as an ordinary path. Both steps here answer alike everywhere.
        path = Path(os.path.realpath(root / match["path"]))
        try:
            path.stat()
        except OSError as exc:
            if exc.errno == errno.ELOOP:  # a symlink loop
                return None
        return path.relative_to(root.resolve()).as_posix() + ref.strip()[match.end("path"):]
    except (OSError, ValueError, RuntimeError):  # RuntimeError: the root itself a symlink loop, up to Python 3.12
        return None


def _project_paths(root: Path, item: Any) -> Any:
    """The finding with its target and its read/grep references rewritten by `_project_ref`; one
    that leads outside stays as written, for `reference_exists` to reject."""
    if not isinstance(item, dict):
        return item
    out = {**item, **({"target": _project_ref(root, item["target"]) or item["target"]} if isinstance(item.get("target"), str) else {})}
    if isinstance(item.get("evidence"), list):
        out["evidence"] = [{**e, "ref": _project_ref(root, e["ref"]) or e["ref"]}
                           if isinstance(e, dict) and e.get("source") in ("read", "grep") and isinstance(e.get("ref"), str) else e
                           for e in item["evidence"]]
    return out


def reference_exists(root: Path, ref: str) -> bool:
    match = REF_RE.match(_project_ref(root, ref) or "")
    if not match or not (root / match["path"]).is_file():
        return False
    if not match["line"]:
        return True
    try:
        return int(match["line"]) <= len((root / match["path"]).read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return False


def schema_errors(root: Path, item: Any, signal_ids: set[str]) -> list[str]:
    if not isinstance(item, dict):
        return ["not an object"]
    errors = [f"missing field {name}" for name in FIELDS if name not in item]
    errors += [f"unknown field {name}" for name in item if name not in FIELDS]
    if errors:
        return errors
    errors += [f"{name} must be a non-empty string" for name in TEXT_FIELDS
               if not isinstance(item[name], str) or not item[name].strip()]
    for name, allowed in (("category", CATEGORIES), ("test_safety", TEST_SAFETY),
                          ("proposed_action", ACTIONS), ("reversal_risk", RISKS)):
        if item[name] not in allowed:
            errors.append(f"{name} must be one of {', '.join(allowed)}")
    errors += [f"{name} must be true or false" for name in ("protected", "chesterton_checked")
               if not isinstance(item[name], bool)]
    if isinstance(item["target"], str) and not reference_exists(root, item["target"]):
        errors.append(f"target {item['target']!r} is not a file of this repository (path[:line] or path::symbol)")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or not evidence:
        return [*errors, "evidence must be a non-empty list"]
    for entry in evidence:
        source = entry.get("source") if isinstance(entry, dict) else None
        ref = str(entry.get("ref", "")) if isinstance(entry, dict) else ""
        if source not in EVIDENCE_SOURCES:
            errors.append(f"evidence source must be one of {', '.join(EVIDENCE_SOURCES)}")
        elif source == "signal" and ref not in signal_ids:
            errors.append(f"evidence cites signal {ref!r}, which was not in the input")
        elif source in ("read", "grep") and not reference_exists(root, ref):
            errors.append(f"evidence cites {ref!r}, which does not exist")
    return errors


def lowered(env: dict[str, str], item: Finding) -> Finding:
    """The finding with what it may not claim taken away, each correction noted."""
    out, notes = dict(item), []
    path = REF_RE.match(item["target"].strip())
    rel = path["path"] if path else item["target"]

    def cap(action: str, why: str) -> None:
        if ACTIONS.index(out["proposed_action"]) > ACTIONS.index(action):
            notes.append(f"{out['proposed_action']} -> {action}: {why}")
            out["proposed_action"] = action

    if is_protected(env, rel) and not out["protected"]:
        out["protected"] = True
        notes.append("protected set to true: the path is in a protected zone")
    if out["protected"]:
        cap("confirm", "a protected path is never removed automatically")
    if is_code(env, rel) and out["test_safety"] == "none":
        cap("flag_only", "logic with no test protecting it is flagged, not acted on")
    if not out["chesterton_checked"]:
        cap("confirm", "nobody checked why it is there")
    if out["reversal_risk"] == "high":
        cap("confirm", "the reversal risk is high")
    if all(e["source"] == "judgement" for e in out["evidence"]):
        cap("confirm", "judgement alone, no tool evidence")
    out["id"] = "F-" + hashlib.sha1(f"{out['target']}|{out['category']}|{out['claim']}".encode()).hexdigest()[:8]
    out["validator"] = notes
    return out


def validate(root: Path, answer: list[Any], signal_ids: set[str]) -> dict[str, list[Any]]:
    env = budget.project_env(root)
    result: dict[str, list[Any]] = {"findings": [], "rejected": []}
    for index, item in enumerate(_project_paths(root, i) for i in answer):
        errors = schema_errors(root, item, signal_ids)
        if errors:
            result["rejected"].append({"index": index, "errors": errors, "finding": item})
        else:
            result["findings"].append(lowered(env, item))
    return result


def known_signal_ids(root: Path, request_file: Path | None = None) -> set[str]:
    """The signals the agent was given: the ids in the request it was started with, else (one
    request since the last measurement) the ones in machine state."""
    if request_file is not None:
        return set(re.findall(r"S-[0-9a-f]{8}", request_file.read_text(encoding="utf-8")))
    ids: set[str] = set()
    for path in (root / simplify_signals.STATE_REL).glob("signals-*.json"):
        try:
            ids.update(s["id"] for s in json.loads(path.read_text(encoding="utf-8")).get("signals", []))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
    return ids


def validated_file(root: Path, path: Path, request_file: Path | None = None) -> dict[str, list[Any]]:
    """Validate an answer file; a file `validate --out` already wrote is validated again, not trusted."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else None
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        answer = [{k: v for k, v in f.items() if k in FIELDS} for f in data["findings"] if isinstance(f, dict)]
    else:
        answer = parse_answer(path.read_text(encoding="utf-8"))
    return validate(root, answer, known_signal_ids(root, request_file))


# ------------------------------------------------------------------ the request


def request(root: Path, lenses: list[str], paths: list[str] | None) -> str:
    env = budget.project_env(root)
    lens = ", ".join(lenses)
    scope = "stop" if lens == "budget" else "full"
    files = None
    if scope == "stop":
        files = sorted({*budget.git(root, "diff", "--name-only", "HEAD").splitlines(),
                        *budget.git(root, "ls-files", "--others", "--exclude-standard").splitlines()})
    signals = simplify_signals.collect(root, env, scope, files, paths)
    lines = [f"LENS: {lens}", "SCOPE: " + (" ".join(paths) if paths else "the files named by the signals and the change")]
    if lens == "budget":
        outcome = budget.evaluate(root)
        lines += ["", "COMPLEXITY BUDGET (the figures of the overrun):", outcome.text if outcome else "no active budget"]
        lines += ["CHANGED FILES: " + " ".join(files or [])]
    lines += ["", "DETERMINISTIC SIGNALS (cite a signal by its id):", json.dumps(signals, indent=1, ensure_ascii=False)]
    lines += ["", "Answer with the JSON list of findings and nothing else."]
    return "\n".join(lines)


# ------------------------------------------------------------------ routing and acceptance


def append(path: Path, text: str, header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else header
    path.write_text(existing + text, encoding="utf-8")


def route(root: Path, result: dict[str, list[Any]], title: str) -> list[Finding]:
    """Report and queue what needs the owner; return what the builder may remove."""
    lines = [f"\n## {simplify_signals.utc_now()} — {title}\n"]
    for action in ("confirm", "flag_only"):
        chosen = [f for f in result["findings"] if f["proposed_action"] == action]
        lines.append(f"\n### {action} ({len(chosen)})\n")
        for f in chosen:
            evidence = "; ".join(f"{e['source']} {e.get('ref', '')} {e.get('detail', '')}".strip() for e in f["evidence"])
            lines.append(f"- `{f['id']}` **{f['target']}** — {f['category']}: {f['claim']}\n"
                         f"  - evidence: {evidence}\n"
                         f"  - test safety {f['test_safety']}, reversal risk {f['reversal_risk']}, "
                         f"protected {str(f['protected']).lower()}, traces to: {f['traceability']}\n"
                         + "".join(f"  - validator: {note}\n" for note in f["validator"]))
            lesson_queue.add(root, "simplifier", lesson_queue.current_slice(root),
                             f"{f['category']} {f['target']}: {f['claim']}")
    if result["rejected"]:
        lines.append(f"\n### rejected by the validator ({len(result['rejected'])})\n")
        lines += [f"- finding {r['index']}: {'; '.join(r['errors'])}\n" for r in result["rejected"]]
    append(root / REPORT_REL, "".join(lines), "# Simplifier — findings for the owner\n\nNothing listed here was removed.\n")
    return [f for f in result["findings"] if f["proposed_action"] == "auto_remove"]


def decide(root: Path, ident: str, answer: str) -> tuple[int, str]:
    decision = {"так": "yes", "yes": "yes", "ні": "no", "no": "no"}.get(answer.strip().lower())
    if decision is None or not re.fullmatch(r"F-[0-9a-f]{8}", ident):
        return 1, "usage: decide F-xxxxxxxx так|ні"
    row = {"utc": simplify_signals.utc_now(), "finding": ident, "decision": decision}
    append(root / DECISIONS_REL, json.dumps(row, ensure_ascii=False) + "\n")
    return 0, f"recorded in {DECISIONS_REL}: {ident} — {decision}"


def applied(root: Path, ident: str, note: str) -> tuple[int, str]:
    """Mark a finding about the draft plan as applied by the architect: nothing is left to ask the owner."""
    note = re.sub(r"\s+", " ", note).strip()
    if len(note) < 12 or len(note.split()) < 2:
        return 1, "the note must say what was changed in the plan (two words at least)"
    report = (root / REPORT_REL).read_text(encoding="utf-8") if (root / REPORT_REL).is_file() else ""
    line = re.compile(rf"^- (`{re.escape(ident)}` \*\*(?P<target>.+?)\*\* — (?P<category>\w+): (?P<claim>.*))$", re.MULTILINE)
    found = line.search(report)
    if found is None:
        return 1, f"no open finding {ident} in {REPORT_REL}"
    env = budget.project_env(root)
    ref = REF_RE.match(found["target"])
    path = ref["path"] if ref else found["target"]
    if is_protected(env, path):
        return 1, f"{path} is protected: the finding stays the owner's"
    if is_code(env, path):
        return 1, f"{path} is code: taking it out is a removal (auto_remove, or the owner's confirm), not a change of the plan"
    mark = f"  - applied to the plan {simplify_signals.utc_now()}: {note} — nothing is asked of the owner\n"
    (root / REPORT_REL).write_text(line.sub(lambda m: f"- APPLIED BY THE ARCHITECT {m[1]}\n{mark.rstrip()}", report), encoding="utf-8")
    essence = lesson_queue.clean_essence(f"{found['category']} {found['target']}: {found['claim']}")
    lesson_queue.close(root, lesson_queue.item_id("simplifier", essence), "applied", f"applied to the plan: {note}")
    return 0, f"marked in {REPORT_REL}: {ident} applied to the plan"


def accept(root: Path, reason: str, verdict: Path) -> tuple[int, str]:
    if len(reason) < 12 or len(reason.split()) < 2:
        return 1, "the reason must say why the excess is needed (two words at least)"
    outcome = budget.evaluate(root)
    if outcome is None or not outcome.exceeded or not outcome.slug:
        return 1, "nothing to accept: no overrun of the active slice's budget is waiting for a verdict"
    if outcome.hard:
        return 1, "the limit of an urgent fix is hard: no verdict lifts it — make the fix smaller or do it as /bugfix"
    try:
        result = validated_file(root, verdict)
    except (OSError, ValueError) as exc:
        return 1, f"the simplifier's verdict cannot be read: {exc}"
    if result["rejected"]:
        return 1, f"the verdict has {len(result['rejected'])} finding(s) the validator rejects; get a clean answer first"
    standing = [f for f in result["findings"] if f["proposed_action"] != "flag_only"]
    if standing:
        return 1, ("the simplifier's verdict still holds " + ", ".join(f"{f['proposed_action']} {f['target']}" for f in standing)
                   + ": the overrun is not justified — make the change smaller")
    stamp = simplify_signals.utc_now()
    digest = hashlib.sha256(verdict.read_bytes()).hexdigest()[:12]
    figures = "\n".join(f"  - {line}" for line in outcome.lines)
    state = root / budget.ACCEPTED_DIR / f"accepted-{outcome.slug}.json"
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("base_commit") != outcome.base_commit:
        data = {"base_commit": outcome.base_commit, "entries": []}
    data["entries"].append({"utc": stamp, "over": outcome.over, "reason": reason, "verdict_sha256": digest})
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    append(root / OVERRUNS_REL / f"{outcome.slug}.md",
           f"\n## {stamp} — overrun accepted\n{figures}\n- Reason: {reason}\n- Simplifier's verdict: {verdict.name} (sha256 {digest}…), "
           f"{len(result['findings'])} flag_only finding(s), none above\n",
           f"# Complexity overruns of slice {outcome.slug}\n\nThe contract is sealed; what the simplifier accepted over its budget is recorded here.\n")
    journal.add(root, "ledger",   # this session's own file of the ledger (board 739)
                f"## {stamp} — {outcome.slug} — COMPLEXITY_OVERRUN_ACCEPTED\n- Trigger: the complexity budget was exceeded; the simplifier was called\n"
                f"- Evidence: {OVERRUNS_REL / (outcome.slug + '.md')}; verdict sha256 {digest}…\n{figures}\n- Reason: {reason}\n- Category: simplifier\n")
    return 0, f"recorded: {OVERRUNS_REL / (outcome.slug + '.md')} and the ledger (`python3 .claude/hooks/journal.py show ledger`)"


# ------------------------------------------------------------------ the reversal rate


def removal_returned(root: Path, sha: str, ident: str, later: str) -> str:
    """Why this removal counts as returned, or ''."""
    if re.search(rf"This reverts commit {sha}|^Simplifier-Reverts:\s*{re.escape(ident)}\s*$", later, re.MULTILINE):
        return "reverted"
    removed: dict[str, list[str]] = {}
    path = ""
    for line in budget.git(root, "show", "--format=", "-U0", "--no-renames", sha).splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else ""
        elif line.startswith("-") and path and len(line[1:].strip()) >= MIN_LINE:
            removed.setdefault(path, []).append(line[1:].strip())
    total = sum(len(lines) for lines in removed.values())
    back = 0
    for path, lines in removed.items():
        # A line is back when the file holds more copies of it than the removal left: the twin of
        # a removed repeat, or the same text elsewhere in the file, was never gone.
        left, now = (Counter(row.strip() for row in budget.git(root, "show", f"{ref}:{path}").splitlines())
                     for ref in (sha, "HEAD"))
        for line, count in Counter(lines).items():
            back += min(count, max(0, now[line] - left[line]))
    return "the removed lines are in the file again" if total and back / total >= RETURNED_SHARE else ""


def reversals(root: Path, last: int) -> dict[str, Any]:
    log = budget.git(root, "log", "--format=%H%x00%B%x01").split("\x01")
    commits = [(sha.strip(), body) for sha, _, body in (entry.partition("\x00") for entry in log) if sha.strip()]
    rows = []
    for index, (sha, body) in enumerate(commits):  # newest first
        for match in TRAILER_RE.finditer(body):
            later = "\n".join(b for _, b in commits[:index])
            rows.append({"finding": match["id"], "commit": sha[:10], "returned": removal_returned(root, sha, match["id"], later)})
    rows = rows[:last]
    returned = sum(bool(r["returned"]) for r in rows)
    share = round(100 * returned / len(rows), 1) if rows else 0.0
    if len(rows) < MIN_SAMPLE:
        advice = f"too few removals to judge ({len(rows)} of the {MIN_SAMPLE} needed)"
    elif share < CORRIDOR[0]:
        advice = "almost nothing comes back: the simplifier removes too little — be bolder"
    elif share > CORRIDOR[1]:
        advice = "too much comes back: the simplifier removes too much — be more careful"
    else:
        advice = "inside the corridor"
    return {"removals": len(rows), "returned": returned, "share_percent": share, "corridor_percent": list(CORRIDOR),
            "advice": advice, "rows": rows}


def reversal_text(result: dict[str, Any]) -> str:
    head = (f"Reversal rate: {result['returned']} of the last {result['removals']} removals came back "
            f"({result['share_percent']} %; the corridor is {CORRIDOR[0]}-{CORRIDOR[1]} %) — {result['advice']}")
    lines = [head]
    lines += [f"  - {r['finding']} ({r['commit']}): {r['returned']}" for r in result["rows"] if r["returned"]]
    return "\n".join(lines)


# ------------------------------------------------------------------ entry point


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("request", "nightly"):
        p = sub.add_parser(name)
        p.add_argument("--paths", nargs="*", default=None)
        if name == "request":
            p.add_argument("--lens", choices=LENSES, nargs="+", required=True)
    for name in ("validate", "route"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
        p.add_argument("--request", type=Path, help="the request the agent was started with (its signals are the input)")
        p.add_argument("--out", type=Path) if name == "validate" else p.add_argument("--title", required=True)
    p = sub.add_parser("accept")
    p.add_argument("--reason", required=True)
    p.add_argument("--verdict", type=Path, required=True)
    p = sub.add_parser("decide")
    p.add_argument("finding")
    p.add_argument("answer", help="так or ні: the owner's decision on a confirm finding")
    p = sub.add_parser("applied")
    p.add_argument("finding")
    p.add_argument("--note", required=True, help="what was changed in the plan")
    p = sub.add_parser("reversals")
    p.add_argument("--last", type=int, default=20)
    p.add_argument("--record", action="store_true", help="also write the line into the owner's report")
    args = parser.parse_args(argv)
    root = budget.project_root()

    if args.command == "request":
        print(request(root, args.lens, args.paths))
        return 0
    if args.command == "nightly":
        signals = simplify_signals.collect(root, budget.project_env(root), "full", None, args.paths, record=True)
        calls = [s["message"] for s in signals if s["kind"] == "trend"]
        print(f"{len(signals)} signal(s) in {simplify_signals.STATE_REL}/signals-full.json")
        print("SIMPLIFIER CALL: " + "; ".join(calls) if calls else "no sharp growth: the nightly cleanup reviews the signals only")
        print(reversal_text(reversals(root, 20)))
        return 0
    if args.command in ("validate", "route"):
        try:
            result = validated_file(root, args.file, args.request)
        except (OSError, ValueError) as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return 2
        if args.command == "route":
            removable = route(root, result, args.title)
            print(f"{len(result['findings']) - len(removable)} finding(s) for the owner in {REPORT_REL}; "
                  f"{len(removable)} auto_remove: " + ", ".join(f"{f['id']} {f['target']}" for f in removable))
            return 0
        text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        print(f"{len(result['findings'])} valid, {len(result['rejected'])} rejected, "
              f"{sum(bool(f['validator']) for f in result['findings'])} lowered", file=sys.stderr)
        return 1 if result["rejected"] else 0
    if args.command in ("accept", "decide", "applied"):
        if args.command == "accept":
            code, message = accept(root, args.reason.strip(), args.verdict)
        elif args.command == "decide":
            code, message = decide(root, args.finding, args.answer)
        else:
            code, message = applied(root, args.finding, args.note)
        print(message, file=sys.stderr if code else sys.stdout)
        return code
    rate = reversals(root, args.last)
    print(reversal_text(rate))
    if args.record and rate["removals"] >= MIN_SAMPLE and rate["advice"] != "inside the corridor":
        append(root / REPORT_REL, f"\n## {simplify_signals.utc_now()} — for the owner: the reversal rate is outside the corridor\n{reversal_text(rate)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
