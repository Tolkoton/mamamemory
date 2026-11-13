#!/usr/bin/env python3
"""The conversation model of a conversational product: the mechanics, and nothing but the mechanics.

    python3 .claude/hooks/conversation.py check                    # the model's rules and the code against it; exit 1 on any finding
    python3 .claude/hooks/conversation.py gen                      # the golden corpus from the model (+ every owner complaint)
    python3 .claude/hooks/conversation.py complaint --state S --phrase P --expect INTENT --said "<verbatim>" --when "<date, place>"
    python3 .claude/hooks/conversation.py run [--k 3] [--adapter CMD] [--out FILE]   # the corpus against the product; exit 1 on any red case

WHY (board 209; docs/research/2026-11-userflow/R5-conversation-state.md). mamamemory's conversation
was a state machine nobody had written down: a pending question («Скільки часу це займе?») took
every phrase that followed as its answer, three kinds of question each decided in its own way
whether a phrase answered it, and each patch to the one LLM router («ну не знаю» — other) moved
other phrases. The model `.engine/architecture/conversation-model.json` (with its owner-facing twin
`conversation-model.md`, format: `.claude/references/conversation-model.md`) names the whole:

  * STATES — what the person sees, which intents the router may answer in it; exactly one is the
    root. A state with a pending question allows every intent the root allows: a phrase of another
    journey is a new command, never swallowed as the answer and never refused.
  * PENDING QUESTIONS — at most one per state; what is an answer (kinds, examples), that anything
    else is a new command, at most 2 re-asks (Google's conversation design), the exit (cancel,
    resume, ask to resume); a time-to-live only with a goals line or `[owner decision needed]`.
  * ONE ROUTING POINT (one module:symbol every phrase passes) and ONE PRIORITY RULE (a paragraph).
  * INTENTS — each with 3+ example phrases and the intents it is confused with.

CHECK is mechanical: the rules above, the agreement with `.engine/journeys/interference.md` (every
pending question there is a pending question here), every recorded complaint still names a state
and an intent of the model, and — the gate's half — the CODE against the model: the router's intent
enum (`CONVERSATION_INTENTS="path:NAME"` in `.claude/project.env`) and the kinds of `reply_to`
(`CONVERSATION_REPLY_KINDS="path:NAME"`) are the same sets as the model's. A router that exists
(the routing point's file is in the tree) with the key empty is a finding too: the check cannot be
switched off by emptying a key. The Stop gate runs it (gate.py) whenever the model exists.

GEN writes `tests/conversations/corpus.json`: for every state, each example of each allowed intent;
for every pending question, each answer example (answers it) and each example of every other intent
(does NOT answer it); then every owner complaint, forever. Structural expectations only (intent,
whether the pending question was answered), never text — as Rasa's E2E assertions.

COMPLAINT appends to `tests/conversations/complaints.json` (never removed): the phrase, the state it
was said in, what should have happened, the owner's verbatim words and when. A state or an intent
the model does not have is refused: the model changes first.

RUN gives the corpus to the product's adapter (`CONVERSATION_RUNNER`, or --adapter): a command that
reads a JSON list of cases `{id, state, phrase}` on stdin and prints a JSON list `{id, intent,
pending}` (pending: `answered` or `not_answered`, for a state with a pending question). Each case runs
k times; a case is green only when all k agree with it (pass^k). With a real model this costs money:
run it on a change of the router or the states and before a deploy, not on every Stop.

Exit: 0 fine; 1 a finding (check) or a red case (run); 2 usage or a refused complaint; 4 nothing to
check (no model and no router key). Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goals  # the project root and the goals document's lines: one reading of them

MODEL_REL = ".engine/architecture/conversation-model.json"
MODEL_MD_REL = ".engine/architecture/conversation-model.md"
INTERFERENCE_REL = ".engine/journeys/interference.md"
CORPUS_REL = "tests/conversations/corpus.json"
COMPLAINTS_REL = "tests/conversations/complaints.json"
ENV_REL = ".claude/project.env"
EXIT_OK, EXIT_FOUND, EXIT_USAGE, EXIT_NONE = 0, 1, 2, 4

MAX_RETRIES = 2            # Google conversation design: two re-asks, then end the question gracefully
MIN_EXAMPLES = 3
ON_EXIT = ("cancel", "resume", "ask_resume")
OWNER_NEEDED = "[owner decision needed]"
GOALS_LINE = re.compile(r"^[A-Z]\d+$")
JOURNEY_STATE = re.compile(r"J-\d+\s+S\d+")
PENDING_VALUES = ("answered", "not_answered")

JsonObj = dict[str, Any]


# ------------------------------------------------------------------ reading


def load_env(root: Path) -> dict[str, str]:
    """KEY="value" lines of `.claude/project.env`; nothing else of the file is read."""
    path = root / ENV_REL
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if match:
            value = match.group(2).strip()
            out[match.group(1)] = value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_model(root: Path) -> tuple[JsonObj | None, str | None]:
    """(model, None), (None, why it cannot be read), or (None, None) when there is none."""
    path = root / MODEL_REL
    if not path.is_file():
        return None, None
    try:
        model = load_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{MODEL_REL} is not JSON: {exc}"
    return (model, None) if isinstance(model, dict) else (None, f"{MODEL_REL} is not a JSON object")


def complaints(root: Path) -> list[JsonObj]:
    path = root / COMPLAINTS_REL
    if not path.is_file():
        return []
    found = load_json(path)
    return found if isinstance(found, list) else []


def by_id(items: Any) -> dict[str, JsonObj]:
    return {str(i.get("id")): i for i in items if isinstance(i, dict)} if isinstance(items, list) else {}


# ------------------------------------------------------------------ the code's sets


def code_values(root: Path, spec: str) -> tuple[set[str] | None, str | None]:
    """The string values a `path:NAME` names: in Python, NAME's assignment (a dict's `enum` lists, a
    `Literal[...]`, a list/tuple/set) or class (an Enum's string values); elsewhere the quoted strings
    of the first bracket after NAME. (None, why) when it cannot be read."""
    rel, _, name = spec.rpartition(":")
    if not rel or not name:
        return None, f"'{spec}' is not path:NAME"
    path = root / rel
    if not path.is_file():
        return None, f"{rel} (named by '{spec}') does not exist"
    text = path.read_text(encoding="utf-8")
    found = _python_values(text, name) if rel.endswith(".py") else _bracket_values(text, name)
    if not found:
        return None, f"no string values found for {name} in {rel}"
    return found, None


def _python_values(text: str, name: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return {v.value.value for v in node.body if isinstance(v, ast.Assign)
                    and isinstance(v.value, ast.Constant) and isinstance(v.value.value, str)}
        value = _assigned(node, name)
        if value is not None:
            return _strings(value)
    return set()


def _assigned(node: ast.stmt, name: str) -> ast.expr | None:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
        return node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
        return node.value
    if sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias) and node.name.id == name:
        return node.value
    return None


def _strings(value: ast.expr) -> set[str]:
    """A dict: the strings of every `"enum": [...]` inside it, else its string keys; anything else: every string constant."""
    if isinstance(value, ast.Dict):
        enums = [v for n in ast.walk(value) if isinstance(n, ast.Dict)
                 for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value == "enum"]
        if enums:
            return {s for e in enums for s in _constants(e)}
        return {k.value for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}   # a mapping intent -> handler
    return _constants(value)


def _constants(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _bracket_values(text: str, name: str) -> set[str]:
    match = re.search(rf"\b{re.escape(name)}\b[^\[\(\{{]*([\[\(\{{])", text)
    if not match:
        return set()
    pairs = {"[": "]", "(": ")", "{": "}"}
    opening, depth, start = match.group(1), 0, match.start(1)
    for i in range(start, len(text)):
        depth += text[i] == opening
        depth -= text[i] == pairs[opening]
        if depth == 0:
            return set(re.findall(r"""["']([^"'\n]+)["']""", text[start:i + 1]))
    return set()


# ------------------------------------------------------------------ check


def model_errors(model: JsonObj, goal_lines: set[str]) -> list[str]:
    errors: list[str] = []
    intents, states, pending = by_id(model.get("intents")), by_id(model.get("states")), by_id(model.get("pending"))
    errors += _routing_errors(model)
    errors += _intent_errors(intents)
    errors += _state_errors(states, intents, pending)
    errors += _pending_errors(pending, states, intents, goal_lines)
    errors += _transition_errors(model.get("transitions"), states, intents, pending)
    return errors


def _routing_errors(model: JsonObj) -> list[str]:
    errors = []
    point = model.get("routing_point")
    if not isinstance(point, str) or not point.strip():
        errors.append("routing_point: exactly one routing point is required (one 'path:symbol' every phrase passes, a string, not a list)")
    if not str(model.get("priority_rule") or "").strip():
        errors.append("priority_rule: the one rule of what wins — an answer to the pending question or a new command — is missing")
    return errors


def _intent_errors(intents: dict[str, JsonObj]) -> list[str]:
    errors = []
    if not intents:
        errors.append("intents: none — the router's intents are the model's vocabulary")
    for iid, intent in intents.items():
        examples = [e for e in intent.get("examples") or [] if str(e).strip()]
        if len(examples) < MIN_EXAMPLES:
            errors.append(f"intent {iid}: {len(examples)} example phrase(s), at least {MIN_EXAMPLES} are needed")
        neighbours = intent.get("confused_with") or []
        if len(intents) > 1 and not neighbours:
            errors.append(f"intent {iid}: no neighbours — name the intents it is confused with and the phrases it may steal (confused_with)")
        errors += [f"intent {iid}: confused_with names '{n}', which is not an intent of the model" for n in neighbours if n not in intents]
    return errors


def _state_errors(states: dict[str, JsonObj], intents: dict[str, JsonObj], pending: dict[str, JsonObj]) -> list[str]:
    errors = []
    roots = [sid for sid, s in states.items() if s.get("root")]
    if len(roots) != 1:
        errors.append(f"states: exactly one root state is required, found {len(roots)}")
    root_allowed = set(states[roots[0]].get("allowed") or []) if len(roots) == 1 else set()
    for sid, state in states.items():
        allowed = state.get("allowed") or []
        errors += [f"state {sid}: allows '{i}', which is not an intent of the model" for i in allowed if i not in intents]
        asked = state.get("pending")
        if isinstance(asked, list):
            errors.append(f"state {sid}: {len(asked)} pending questions — at most one question is active; the rest wait in a list, not as reply_to")
            continue
        if asked is None:
            continue
        if asked not in pending:
            errors.append(f"state {sid}: pending '{asked}' is not a pending question of the model")
        missing = sorted(root_allowed - set(allowed))
        if missing:
            errors.append(f"state {sid} (pending {asked}) does not allow {', '.join(missing)}, which the root allows — "
                          "a phrase of another journey would be swallowed as the answer or refused")
    return errors


def _pending_errors(pending: dict[str, JsonObj], states: dict[str, JsonObj], intents: dict[str, JsonObj],
                    goal_lines: set[str]) -> list[str]:
    errors = []
    for pid, question in pending.items():
        where = f"pending {pid}"
        owners = [sid for sid, s in states.items() if s.get("pending") == pid or pid in (s.get("pending") or [])]
        if not owners:
            errors.append(f"{where}: no state asks it")
        if not question.get("answer_kinds"):
            errors.append(f"{where}: answer_kinds — what counts as an answer — is missing")
        kinds = question.get("answer_kinds") or []
        if not question.get("answer_examples") and not any(k in intents for k in kinds):
            errors.append(f"{where}: answer_examples — at least one phrase that answers it — is missing")
        for sid in owners:
            allowed = states[sid].get("allowed") or []
            errors += [f"{where}: the answer kind '{k}' is an intent that {sid} does not allow" for k in kinds if k in intents and k not in allowed]
        if question.get("not_answer") != "new_command":
            errors.append(f"{where}: not_answer must be \"new_command\" — a phrase that is not an answer is routed as a new command "
                          "(a question without it is a dead end: it catches every phrase)")
        retries = question.get("max_retries")
        if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= MAX_RETRIES:
            errors.append(f"{where}: max_retries must be 0..{MAX_RETRIES} (re-ask at most twice, then exit)")
        if question.get("on_exit") not in ON_EXIT:
            errors.append(f"{where}: on_exit must be one of {', '.join(ON_EXIT)} — the way out after the re-asks or an interruption")
        errors += _threshold_errors(where, question.get("ttl"), goal_lines)
        target = question.get("answered_to")
        if target not in states:
            errors.append(f"{where}: answered_to '{target}' is not a state — where the conversation goes once it is answered")
    return errors


def _threshold_errors(where: str, ttl: Any, goal_lines: set[str]) -> list[str]:
    if ttl in (None, OWNER_NEEDED):
        return []
    source = str(ttl.get("source", "")) if isinstance(ttl, dict) else ""
    if source == OWNER_NEEDED:
        return []
    if not GOALS_LINE.match(source):
        return [f"{where}: ttl has no source — a threshold cites a goals line (source: \"G3\") or says {OWNER_NEEDED}; an invented number is not a decision"]
    if goal_lines and source not in goal_lines:
        return [f"{where}: ttl cites {source}, which is not a line of the goals document"]
    return []


def _transition_errors(transitions: Any, states: dict[str, JsonObj], intents: dict[str, JsonObj], pending: dict[str, JsonObj]) -> list[str]:
    errors = []
    reached = {sid for sid, s in states.items() if s.get("root")}
    for t in transitions if isinstance(transitions, list) else []:
        src, intent, dst = t.get("from"), t.get("intent"), t.get("to")
        if src not in states or dst not in states:
            errors.append(f"transition {src} --{intent}--> {dst}: a state that is not in the model")
            continue
        if intent not in intents:
            errors.append(f"transition {src} --{intent}--> {dst}: '{intent}' is not an intent of the model")
        elif intent not in (states[src].get("allowed") or []):
            errors.append(f"transition {src} --{intent}--> {dst}: {src} does not allow '{intent}'")
    edges = [(t.get("from"), t.get("to")) for t in transitions if isinstance(t, dict)] if isinstance(transitions, list) else []
    edges += [(sid, pending[s["pending"]].get("answered_to")) for sid, s in states.items()
              if isinstance(s.get("pending"), str) and s["pending"] in pending]
    grown = True
    while grown:
        new = {dst for src, dst in edges if src in reached and dst in states} - reached
        reached |= new
        grown = bool(new)
    errors += [f"state {sid}: unreachable from the root — no transition leads to it" for sid in states if sid not in reached]
    return errors


def interference_errors(root: Path, model: JsonObj) -> list[str]:
    """Every pending question of `.engine/journeys/interference.md` (its «У стані») is a pending question here."""
    path = root / INTERFERENCE_REL
    if not path.is_file():
        return []
    asked = {re.sub(r"\s+", " ", m) for m in JOURNEY_STATE.findall(_first_column(path.read_text(encoding="utf-8")))}
    covered = {re.sub(r"\s+", " ", str(q.get("journey", ""))) for q in by_id(model.get("pending")).values()}
    return [f"interference.md: the pending question {a} has no pending question in the model (journey: \"{a}\")" for a in sorted(asked - covered)]


def _first_column(text: str) -> str:
    return "\n".join(line.split("|")[1] for line in text.splitlines() if line.strip().startswith("|") and line.count("|") > 2)


def complaint_errors(model: JsonObj, found: list[JsonObj]) -> list[str]:
    states, intents = by_id(model.get("states")), by_id(model.get("intents"))
    errors = []
    for c in found:
        if c.get("state") not in states:
            errors.append(f"complaint {c.get('id')}: state '{c.get('state')}' is no longer in the model — a complaint stays forever, so the model keeps its state")
        if c.get("expect", {}).get("intent") not in (*intents, "answer"):
            errors.append(f"complaint {c.get('id')}: intent '{c.get('expect', {}).get('intent')}' is no longer in the model")
    return errors


def code_errors(root: Path, model: JsonObj | None, env: dict[str, str]) -> list[str]:
    """The code against the model: the intent enum and the kinds of reply_to (the gate's half)."""
    errors = []
    pairs = (("CONVERSATION_INTENTS", "intent", set(by_id(model.get("intents")) if model else ())),
             ("CONVERSATION_REPLY_KINDS", "reply_to kind",
              {str(q.get("reply_to") or pid) for pid, q in by_id(model.get("pending")).items()} if model else set()))
    for key, label, wanted in pairs:
        spec = env.get(key, "").strip()
        if not spec:
            continue
        if model is None:
            errors.append(f"{key} names a router ({spec}) but there is no {MODEL_REL}: the conversation model comes first")
            continue
        have, problem = code_values(root, spec)
        if problem:
            errors.append(f"{key}: {problem}")
            continue
        assert have is not None
        errors += [f"{label} '{v}' is in the code ({spec}) and not in {MODEL_REL}" for v in sorted(have - wanted)]
        errors += [f"{label} '{v}' is in {MODEL_REL} and not in the code ({spec})" for v in sorted(wanted - have)]
    if model is not None and not env.get("CONVERSATION_INTENTS", "").strip():
        point = str(model.get("routing_point") or "").rpartition(":")[0]
        if point and (root / point).is_file():
            errors.append(f"the router {point} exists and CONVERSATION_INTENTS in {ENV_REL} is empty: name its intent enum (path:NAME) so the code is checked against the model")
    return errors


def all_errors(root: Path) -> tuple[int, list[str]]:
    """(exit code, findings) — what `check` prints and the gate blocks on."""
    env = load_env(root)
    model, problem = load_model(root)
    if problem:
        return EXIT_FOUND, [problem]
    if model is None and not any(env.get(k, "").strip() for k in ("CONVERSATION_INTENTS", "CONVERSATION_REPLY_KINDS")):
        return EXIT_NONE, []
    errors: list[str] = []
    if model is not None:
        goal_text = (root / goals.GOALS_REL).read_text(encoding="utf-8") if (root / goals.GOALS_REL).is_file() else ""
        try:
            goal_lines = set(goals.items(goal_text))
        except ValueError:
            goal_lines = set()
        errors += model_errors(model, goal_lines)
        errors += interference_errors(root, model)
        try:
            errors += complaint_errors(model, complaints(root))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{COMPLAINTS_REL} is not JSON: {exc}")
        if not (root / MODEL_MD_REL).is_file():
            errors.append(f"{MODEL_MD_REL} is missing: the owner reads the model there (the diagram and the tables)")
    errors += code_errors(root, model, env)
    return (EXIT_FOUND if errors else EXIT_OK), errors


def cmd_check(root: Path) -> int:
    code, errors = all_errors(root)
    if code == EXIT_NONE:
        print(f"no conversation model ({MODEL_REL}) and no router key in {ENV_REL}: nothing to check")
        return code
    for line in errors:
        print(f"CONVERSATION: {line}")
    print("conversation model: clean" if code == EXIT_OK else f"conversation model: {len(errors)} finding(s)")
    return code


# ------------------------------------------------------------------ gen


def generate(model: JsonObj, owner: list[JsonObj]) -> list[JsonObj]:
    """The cases: (state, phrase) -> the intent, and for a state with a pending question whether it was answered."""
    intents, pending = by_id(model.get("intents")), by_id(model.get("pending"))
    cases: list[JsonObj] = []
    for state in model.get("states") or []:
        sid, asked = state.get("id"), state.get("pending")
        question = pending.get(asked) if asked else None
        if question:
            for phrase in question.get("answer_examples") or []:
                cases.append(_case(sid, phrase, {"intent": "answer", "pending": "answered"}, f"answers {asked}"))
        answering = set((question or {}).get("answer_kinds") or [])
        for iid in state.get("allowed") or []:
            for phrase in (intents.get(iid) or {}).get("examples") or []:
                expect: JsonObj = {"intent": iid}
                why = f"{iid} in {sid}"
                if question and iid in answering:
                    expect["pending"], why = "answered", f"{iid} answers the pending {asked}"
                elif question:
                    expect["pending"], why = "not_answered", f"{iid} under the pending {asked}: a new command, not the answer"
                confused = (intents.get(iid) or {}).get("confused_with") or []
                cases.append(_case(sid, phrase, expect, why) | ({"confusable": confused} if confused else {}))
    for c in owner:
        cases.append({"id": f"owner-{c.get('id')}", "origin": "owner", "state": c.get("state"), "phrase": c.get("phrase"),
                      "expect": c.get("expect"), "why": f"the owner, {c.get('when')}: «{c.get('said')}»"})
    for n, case in enumerate(cases, 1):
        if case.get("origin") != "owner":
            case["id"] = f"g{n:04d}"
    return cases


def _case(state: str, phrase: str, expect: JsonObj, why: str) -> JsonObj:
    return {"id": "", "origin": "generated", "state": state, "phrase": phrase, "expect": expect, "why": why}


def cmd_gen(root: Path) -> int:
    model, problem = load_model(root)
    if model is None:
        print(problem or f"no conversation model ({MODEL_REL}): nothing to generate from")
        return EXIT_FOUND if problem else EXIT_NONE
    cases = generate(model, complaints(root))
    path = root / CORPUS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cases, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    owner = sum(1 for c in cases if c["origin"] == "owner")
    print(f"{CORPUS_REL}: {len(cases)} case(s), {owner} of them the owner's complaints")
    return EXIT_OK


# ------------------------------------------------------------------ complaint


def cmd_complaint(root: Path, args: argparse.Namespace) -> int:
    model, problem = load_model(root)
    if model is None:
        print(problem or f"no conversation model ({MODEL_REL}): a complaint is recorded against the model's states")
        return EXIT_USAGE
    states, intents = by_id(model.get("states")), by_id(model.get("intents"))
    if args.state not in states:
        print(f"state '{args.state}' is not in the model: add the state the complaint was said in first ({', '.join(states)})")
        return EXIT_USAGE
    if args.expect not in intents and args.expect != "answer":
        print(f"intent '{args.expect}' is not in the model: the model changes first ({', '.join(intents)})")
        return EXIT_USAGE
    asked = states[args.state].get("pending")
    expect: JsonObj = {"intent": args.expect}
    if asked:
        kinds = (by_id(model.get("pending")).get(asked) or {}).get("answer_kinds") or []
        expect["pending"] = "answered" if args.expect == "answer" or args.expect in kinds else "not_answered"
    found = complaints(root)
    entry = {"id": f"c{len(found) + 1:03d}", "state": args.state, "phrase": args.phrase, "expect": expect,
             "said": args.said, "when": args.when} | ({"observed": args.observed} if args.observed else {})
    path = root / COMPLAINTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([*found, entry], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{COMPLAINTS_REL}: {entry['id']} recorded — run `conversation.py gen` to put it into the corpus")
    return EXIT_OK


# ------------------------------------------------------------------ run


def observe(adapter: str, root: Path, cases: list[JsonObj]) -> dict[str, JsonObj]:
    given = [{"id": c["id"], "state": c["state"], "phrase": c["phrase"]} for c in cases]
    proc = subprocess.run(shlex.split(adapter), cwd=root, input=json.dumps(given, ensure_ascii=False), capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"the adapter failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-500:]}")
    return {str(o.get("id")): o for o in json.loads(proc.stdout)}


def agrees(case: JsonObj, seen: JsonObj | None) -> bool:
    if seen is None:
        return False
    expect = case.get("expect") or {}
    return seen.get("intent") == expect.get("intent") and ("pending" not in expect or seen.get("pending") == expect["pending"])


def cmd_run(root: Path, adapter: str | None, k: int, as_json: bool, out: str = "") -> int:
    adapter = adapter or load_env(root).get("CONVERSATION_RUNNER", "").strip()
    if not adapter:
        print(f"no adapter: set CONVERSATION_RUNNER in {ENV_REL} or pass --adapter")
        return EXIT_USAGE
    path = root / CORPUS_REL
    if not path.is_file():
        print(f"no corpus ({CORPUS_REL}): run `conversation.py gen` first")
        return EXIT_NONE
    cases = load_json(path)
    try:
        runs = [observe(adapter, root, cases) for _ in range(k)]
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"no result from the adapter `{adapter}`: {exc}")
        return EXIT_USAGE
    red = []
    for case in cases:
        seen = [r.get(case["id"]) for r in runs]
        if not all(agrees(case, s) for s in seen):
            red.append({"id": case["id"], "origin": case["origin"], "state": case["state"], "phrase": case["phrase"],
                        "expect": case["expect"], "seen": seen, "why": case.get("why")})
    summary = {origin: {"cases": sum(1 for c in cases if c["origin"] == origin),
                        "red": sum(1 for r in red if r["origin"] == origin)} for origin in ("generated", "owner")}
    if out:   # board 317: what journey_e2e.py close reads — the revision, the corpus it ran, the red
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
        target = root / out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"sha": head, "k": k, "corpus_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                      "cases": len(cases), "summary": summary, "red": red}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if as_json:
        print(json.dumps({"k": k, "summary": summary, "red": red}, indent=1, ensure_ascii=False))
    else:
        for r in red:
            print(f"RED {r['id']} [{r['state']}] «{r['phrase']}»: expected {json.dumps(r['expect'], ensure_ascii=False)}, "
                  f"seen {json.dumps(r['seen'], ensure_ascii=False)} — {r['why']}")
        print(f"pass^{k}: " + "; ".join(f"{o} {s['cases'] - s['red']}/{s['cases']}" for o, s in summary.items()))
    return EXIT_FOUND if red else EXIT_OK


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("gen")
    add = sub.add_parser("complaint")
    add.add_argument("--state", required=True)
    add.add_argument("--phrase", required=True)
    add.add_argument("--expect", required=True, help="the intent that should have been chosen, or 'answer'")
    add.add_argument("--said", required=True, help="the owner's words, verbatim")
    add.add_argument("--when", required=True, help="the date and the place the owner said it")
    add.add_argument("--observed", default="", help="what the product did instead")
    run = sub.add_parser("run")
    run.add_argument("--adapter", default=None)
    run.add_argument("--k", type=int, default=3)
    run.add_argument("--json", action="store_true")
    run.add_argument("--out", default="", help="also write the result there, with the revision and the corpus's sha256 (board 317)")
    args = parser.parse_args(argv)
    root = goals.project_root()
    if args.command == "check":
        return cmd_check(root)
    if args.command == "gen":
        return cmd_gen(root)
    if args.command == "complaint":
        return cmd_complaint(root, args)
    if args.k < 1:
        parser.error("--k must be at least 1")
    return cmd_run(root, args.adapter, args.k, args.json, args.out)


if __name__ == "__main__":
    sys.exit(main())
