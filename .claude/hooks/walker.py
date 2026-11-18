#!/usr/bin/env python3
"""walker.py — the user-walker: a fresh agent walks the deployed product as a person would, seeing only the screen (board 318).

    python3 .claude/hooks/walker.py request j-N --persona <slug> --url <deploy> [--runs 3] [--budget N]
                                    [--storage-state <file>] [--voice] [--goal <text>] [--calibration <case>]
    python3 .claude/hooks/walker.py guard [--inside]      # PreToolUse: the launch line; inside the walker, only its tools
    python3 .claude/hooks/walker.py record [--inside]     # SubagentStop: the run's answer → the verdict, by this script
    python3 .claude/hooks/walker.py browser               # the walker's browser server: Playwright MCP with the request's flags
    python3 .claude/hooks/walker.py say-server            # the walker's voice: an MCP server with one tool, say(text)
    python3 .claude/hooks/walker.py dispose <group> <n> --test <file> | --reject <why> | --owner <tasks/blocked/…>
    python3 .claude/hooks/walker.py gate j-N              # has the journey's last walk taken place, every finding decided: 0 yes, 3 no
    python3 .claude/hooks/walker.py calibrate             # the calibration eval over the walks of .claude/references/walker-calibration.json
    python3 .claude/hooks/walker.py status

WHY (docs/research/2026-11-userflow/R3-user-walker.md). In mamamemory nobody walked the product before the
owner did: buttons with no visible state, a question that never let go. An agent walking as a person
catches the gross failures cheaply — a dead end, «pressed and nothing happened», a goal not reached —
but it is positively biased and misses most of what an expert sees. So it is a sieve before the owner's
walk, never a «PASS»:

  * THE REQUEST. One journey, one persona, the deployed URL, three runs. The walker gets the GOAL (the
    journey's title and trigger), never the steps; the persona is `.engine/personas/<slug>.md`, refused
    without the owner's approval line. Each run is its own request directory under
    .claude/state/walker/requests/<group>-<k>/ — the only place the walker may read.
  * THE GUARD. Inside the walker (the agent's own hooks pass --inside) a tool is allowed only if it is
    Read inside the request directory or one of the screen tools (WALKER_TOOLS): no snapshot of the
    accessibility tree (it shows what a person does not see), no JS, no network log, no code, no login
    file. In the main session (when wired) the walker starts only with `WALK_REQUEST <id>`; `record`
    holds that too, from the agent's transcript, so a run started with any other prompt gets no verdict.
  * THE VERDICT IS THE SCRIPT'S. From the run's facts: GAVE_UP at the first step with three failed
    attempts, or when the walker did not reach the goal; OVER_BUDGET when it took more steps than the
    journey's budget; else REACHED. An answer that does not fit goes back once, then is INVALID.
  * THE FINDINGS. A finding is a hypothesis. It counts when it recurred in two runs or more, or a test
    reproduces it (`dispose --test`). The gate is «the walk took place and every finding has its
    decision» — a test, a rejection with its reason, or a question in tasks/blocked/ for the owner.
  * OFF UNTIL CALIBRATED. `gate` is no condition until `calibrate` passed on the pinned browser server
    (.engine/walks/calibration.json): ≥3 of the 4 seeded defects found in 2 of 3 runs, ≤1 false finding
    on the clean revision.

Standard library only. Exit: 0 done, 1 refused, 2 usage, 3 the gate is closed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overseer_verdict as ov  # the protocol's helpers: one reader of a reply, one way to write state

JsonObj = dict[str, Any]
AGENT = "user-walker"
STATE_REL = Path(".claude/state/walker")
REQUESTS_REL = STATE_REL / "requests"
PENDING_REL = STATE_REL / "pending.json"
VERDICTS_REL = STATE_REL / "verdicts.jsonl"
WALKS_REL = Path(".engine/walks")
PERSONAS_REL = Path(".engine/personas")
CALIBRATION_REL = WALKS_REL / "calibration.json"
CASES_REL = Path(".claude/references/walker-calibration.json")
JOURNEYS_REL = Path(".engine/journeys")
MCP_PIN = "@playwright/mcp@0.0.85"
DEVICE = "Pixel 7"
BROWSER, VOICE = "mcp__walker_browser__", "mcp__walker_voice__"
# What a person has: the screen, a finger, the keys, the back button, a pause. Nothing that reads the page's insides.
WALKER_TOOLS = ("browser_take_screenshot", "browser_mouse_click_xy", "browser_mouse_move_xy", "browser_mouse_drag_xy",
                "browser_mouse_wheel", "browser_press_key", "browser_navigate", "browser_navigate_back",
                "browser_handle_dialog", "browser_wait_for", "browser_tabs", "browser_close")
FAKE_MEDIA = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream")
KINDS = ("dead_end", "stuck_question", "no_feedback", "unexpected_action", "unclear_text", "duplicate_control", "error")
APPROVED = re.compile(r"^Затверджено власником:\s*\d{4}-\d{2}-\d{2}.*«.+»", re.MULTILINE)
FAILED_ATTEMPTS = 3
RUNS = 3
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_CLOSED = 0, 1, 2, 3


def launch_line(run_id: str) -> str:
    return f"WALK_REQUEST {run_id}"


def pending(root: Path) -> JsonObj | None:
    waiting = ov.read_json(root / PENDING_REL)
    return waiting if waiting.get("id") else None


def run_dir(root: Path, run_id: str) -> Path:
    return root / REQUESTS_REL / run_id


def group_path(root: Path, group: str) -> Path:
    return root / WALKS_REL / f"{group}.json"


def load_group(root: Path, group: str) -> JsonObj:
    return ov.read_json(group_path(root, group))


def groups(root: Path) -> list[JsonObj]:
    folder = root / WALKS_REL
    found = [ov.read_json(p) for p in sorted(folder.glob("*.json")) if p.name != CALIBRATION_REL.name] if folder.is_dir() else []
    return [g for g in found if g.get("group")]


# ------------------------------------------------------------------ the request


def journey_goal(root: Path, unit: str) -> tuple[str, int] | str:
    """(the goal a person has in the journey — its title and trigger, never its steps —, the journey's step count)."""
    match = re.fullmatch(r"j-(\d+)", unit.lower())
    if not match:
        return f"«{unit}» is not a journey (j-N)"
    files = sorted((root / JOURNEYS_REL).glob(f"J-{match[1]}-*.md"))
    if not files:
        return f"no journey J-{match[1]} in {JOURNEYS_REL}/"
    text = files[0].read_text(encoding="utf-8")
    title = text.splitlines()[0].split("—", 1)[-1].strip(" #") if text.strip() else unit
    trigger = next((line.split(":", 1)[1].strip() for line in text.splitlines() if re.match(r"^(Тригер|Trigger):", line)), "")
    steps = len(re.findall(r"^\|\s*\d+\s*\|", text.split("## Стани")[0], re.MULTILINE))
    return (f"{title}. {trigger}".strip(" .") + ".", steps)


def request(root: Path, unit: str, persona: str, url: str, runs: int = RUNS, budget: int = 0, storage_state: str = "",
            voice: bool = False, goal: str = "", calibration: str = "") -> tuple[int, str]:
    waiting = pending(root)
    if waiting:
        return EXIT_REFUSED, f"REFUSED: the walk {waiting['id']} waits for its run (`walker.py status`); one walk at a time"
    persona_file = root / PERSONAS_REL / f"{persona}.md"
    if not persona_file.is_file() or not APPROVED.search(persona_file.read_text(encoding="utf-8")):
        return EXIT_REFUSED, (f"REFUSED: {PERSONAS_REL}/{persona}.md has no line «Затверджено власником: <date>, <place>: «<the owner's words>»» "
                              "— the persona is the owner's (.claude/templates/persona.md)")
    found, case_budget = journey_goal(root, unit), 0
    if calibration:
        cases = ov.read_json(root / CASES_REL)
        spec = {**cases.get("seeded", {}), **cases.get("clean", {})}.get(calibration)
        if not isinstance(spec, dict):
            return EXIT_REFUSED, f"REFUSED: «{calibration}» is no calibration case of {CASES_REL}"
        if isinstance(found, str) and spec.get("goal"):   # a project with no sealed journey is calibrated on the case's goal
            found, case_budget = (str(spec["goal"]), 0), int(cases.get("budget", 0))
    if isinstance(found, str):
        return EXIT_REFUSED, f"REFUSED: {found}"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return EXIT_REFUSED, f"REFUSED: {url} is not the deployed product's address (http[s]://host/…)"
    state = (root / storage_state).resolve() if storage_state else None
    if state is not None and not state.is_file():
        return EXIT_REFUSED, f"REFUSED: no login file {storage_state} (the owner's or the operator's: a session of the product's test account)"
    the_goal, steps = goal or found[0], found[1]
    group = ov.utc_now().replace("-", "").replace(":", "") + "-" + unit.lower() + "-" + secrets.token_hex(2)
    budget = budget or case_budget or max(6, 2 * steps)
    origin = f"{parts.scheme}://{parts.netloc}"
    for k in range(1, runs + 1):
        here = run_dir(root, f"{group}-{k}")
        ov.write_json(here / "request.json", {"id": f"{group}-{k}", "group": group, "run": k, "journey": unit.lower(), "persona": persona,
                                              "url": url, "origin": origin, "budget": budget, "voice": voice,
                                              "storage_state": str(state) if state else "", "utc": ov.utc_now()})
        (here / "goal.md").write_text(f"# Твоя мета\n\n{the_goal}\n\nПочни тут: {url}\nКроків не більше ніж {budget}.\n\n"
                                      f"# Хто ти\n\n{persona_file.read_text(encoding='utf-8')}", encoding="utf-8")
        launch = {"args": [*FAKE_MEDIA, f"--use-file-for-fake-audio-capture={here / 'voice.wav'}"]} if voice else {}
        ov.write_json(here / "browser.json", {"browser": {"browserName": "chromium", "launchOptions": launch,
                                                          "contextOptions": {"permissions": ["microphone"] if voice else []}}})
    ov.write_json(group_path(root, group), {"group": group, "journey": unit.lower(), "persona": persona, "url": url, "runs": runs,
                                            "budget": budget, "goal": the_goal, "calibration": calibration, "pin": MCP_PIN,
                                            "utc": ov.utc_now(), "created_ns": time.time_ns(), "results": {}, "dispositions": {}})
    ov.write_json(root / PENDING_REL, {"id": f"{group}-1"})
    return EXIT_OK, (f"Walk {group}: {unit} as «{persona}», {runs} runs, budget {budget} steps. Launch the agent `{AGENT}` (Agent tool, "
                     f"subagent_type `{AGENT}`, run_in_background false) once per run, each time with exactly the line "
                     f"`walker.py status` shows and nothing else; the first:\n{launch_line(f'{group}-1')}")


# ------------------------------------------------------------------ the guard


def _inside(root: Path, tool: str, tool_input: JsonObj) -> JsonObj | None:
    waiting = pending(root)
    if waiting is None:
        return ov.deny("No walk is pending: the walker has nothing to walk.")
    if tool == "Read":
        here = run_dir(root, str(waiting["id"])).resolve()
        target = Path(str(tool_input.get("file_path", ""))).resolve()
        login = str(ov.read_json(here / "request.json").get("storage_state", ""))
        if (login and target == Path(login)) or target.name.endswith("storage-state.json"):
            return ov.deny("The login file is not yours to read: a person does not read their cookies.")
        if target != here and here not in target.parents:
            return ov.deny(f"You see only the screen. Read is for your goal and your screenshots, in {here.relative_to(root.resolve())}/ — "
                           "not the product's code, not the engine's files.")
        return None
    if tool == f"{VOICE}say" or (tool.startswith(BROWSER) and tool.removeprefix(BROWSER) in WALKER_TOOLS):
        return None
    return ov.deny(f"{tool} is not a person's: you have the screen (screenshot), a finger (click by coordinates), the keys, "
                   "the back button, a pause and your voice (say). Nothing that reads the page's insides.")


def guard(root: Path, envelope: JsonObj, inside: bool = False) -> JsonObj | None:
    tool = str(envelope.get("tool_name", ""))
    raw = envelope.get("tool_input")
    tool_input: JsonObj = raw if isinstance(raw, dict) else {}
    if inside or envelope.get("agent_type") == AGENT:
        return _inside(root, tool, tool_input)
    if tool not in ov.AGENT_TOOLS or tool_input.get("subagent_type") != AGENT:
        return None
    waiting = pending(root)
    if waiting is None:
        return ov.deny("No walk is pending, so the walker is not started: `python3 .claude/hooks/walker.py request j-N --persona … --url …`.")
    line = launch_line(str(waiting["id"]))
    if str(tool_input.get("prompt", "")).strip() != line:
        return ov.deny(f"The walker is started with exactly this prompt and nothing else: `{line}`. It reads its goal itself; "
                       "a word from you would be the builder guiding the person.")
    return None


# ------------------------------------------------------------------ the record


def schema_errors(obj: JsonObj) -> list[str]:
    errors = []
    if obj.get("outcome") not in ("reached", "gave_up"):
        errors.append("`outcome` is reached or gave_up")
    steps = obj.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("`steps` is a non-empty list")
        steps = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not all(isinstance(step.get(k), str) and step[k].strip() for k in ("wanted", "saw", "did", "happened")):
            errors.append(f"step {i}: `wanted`, `saw`, `did`, `happened` are non-empty strings")
        elif not isinstance(step.get("attempts"), int) or step["attempts"] < 1 or step.get("hesitation") not in (0, 1, 2):
            errors.append(f"step {i}: `attempts` is a whole number from 1, `hesitation` is 0, 1 or 2")
    findings = obj.get("findings")
    if not isinstance(findings, list):
        errors.append("`findings` is a list (empty when you found nothing)")
        findings = []
    for i, found in enumerate(findings, 1):
        if not isinstance(found, dict) or found.get("kind") not in KINDS or not isinstance(found.get("step"), int) \
                or not isinstance(found.get("quote"), str) or not found["quote"].strip():
            errors.append(f"finding {i}: `step` is a number, `kind` one of {', '.join(KINDS)}, `quote` the words on the screen")
    help_ = obj.get("would_call_for_help")
    if not isinstance(help_, dict) or not isinstance(help_.get("yes"), bool):
        errors.append("`would_call_for_help` is {\"yes\": true|false, \"step\": N|null}")
    return errors


def verdict_of(obj: JsonObj, budget: int) -> tuple[str, int | None]:
    """The run's verdict from its facts, never from the walker's opinion."""
    steps = obj["steps"]
    for n, step in enumerate(steps, 1):
        if step["attempts"] >= FAILED_ATTEMPTS:
            return "GAVE_UP", n
    if obj["outcome"] != "reached":
        return "GAVE_UP", len(steps)
    if len(steps) > budget:
        return "OVER_BUDGET", None
    return "REACHED", None


def _first_prompt(transcript: object) -> str | None:
    """The agent's first user message, from its own transcript; None when it cannot be read."""
    try:
        lines = Path(str(transcript)).read_text(encoding="utf-8").splitlines() if transcript else []
    except OSError:
        return None
    for line in lines:
        try:
            message = json.loads(line)["message"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
        return str(content).strip()
    return None


def record(root: Path, envelope: JsonObj, inside: bool = False) -> JsonObj | None:
    if not inside and (envelope.get("agent_type") != AGENT or envelope.get("hook_event_name") not in (None, "SubagentStop")):
        return None
    waiting = pending(root)
    if waiting is None:
        return None
    run_id = str(waiting["id"])
    asked = ov.read_json(run_dir(root, run_id) / "request.json")
    group = load_group(root, str(asked.get("group", "")))
    if not group or str(asked.get("run")) in group.get("results", {}):
        return None
    result: JsonObj = {"utc": ov.utc_now(), "agent_id": envelope.get("agent_id", "")}

    def finish(verdict: str, reason: str) -> None:
        result.update({"verdict": verdict, "reason": ov.one_line(reason)})
        group["results"][str(asked["run"])] = result
        ov.write_json(group_path(root, group["group"]), group)
        render(root, group)
        path = root / VERDICTS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"run": run_id, "journey": group["journey"], **result}, ensure_ascii=False) + "\n")
        later = int(asked["run"]) + 1
        ov.write_json(root / PENDING_REL, {"id": f"{group['group']}-{later}"} if later <= int(group["runs"]) else {})

    prompt = _first_prompt(envelope.get("agent_transcript_path"))
    if prompt is not None and prompt != launch_line(run_id):
        finish("INVALID", f"the walker was started with another prompt than `{launch_line(run_id)}`")
        return None
    obj, problem = ov.parse_reply(ov.reply_of(envelope, root))
    errors = [problem] if obj is None else schema_errors(obj)
    if errors:
        if not waiting.get("schema_errors"):
            ov.write_json(root / PENDING_REL, waiting | {"schema_errors": 1})
            return {"decision": "block", "reason": "WALK REFUSED — the answer does not fit:\n- " + "\n- ".join(errors)
                    + "\nAnswer again with ONE JSON object: outcome, steps, findings, would_call_for_help. A second answer that does not fit is INVALID."}
        finish("INVALID", "the answer does not fit: " + "; ".join(errors))
        return None
    assert obj is not None
    verdict, step = verdict_of(obj, int(group["budget"]))
    result.update({"step": step, "steps": len(obj["steps"]), "would_call_for_help": obj["would_call_for_help"],
                   "findings": [{"step": f["step"], "kind": f["kind"], "quote": f["quote"], "screenshot": str(f.get("screenshot", ""))}
                                for f in obj["findings"]],
                   "hesitations": [s["hesitation"] for s in obj["steps"]]})
    finish(verdict, f"{len(obj['steps'])} steps (budget {group['budget']})" + (f", gave up at step {step}" if step else ""))
    return None


# ------------------------------------------------------------------ findings, decisions, the gate


def _key(found: JsonObj) -> str:
    return f"{found['kind']}:" + " ".join(str(found["quote"]).casefold().split()).strip(" .,!?…«»\"'")


def tally(group: JsonObj) -> list[JsonObj]:
    """Each distinct finding of the walk (kind and the words on the screen), in the order first seen."""
    seen: dict[str, JsonObj] = {}
    for run, result in sorted(group.get("results", {}).items(), key=lambda kv: int(kv[0])):
        for found in result.get("findings") or []:
            entry = seen.setdefault(_key(found), {"key": _key(found), "kind": found["kind"], "quote": found["quote"], "step": found["step"], "runs": []})
            if run not in entry["runs"]:
                entry["runs"].append(run)
    out = []
    for n, entry in enumerate(seen.values(), 1):
        decided = group.get("dispositions", {}).get(entry["key"])
        out.append(entry | {"n": n, "decision": decided, "counted": len(entry["runs"]) >= 2 or bool(decided and decided["how"] == "test")})
    return out


def dispose(root: Path, group_id: str, n: int, how: str, value: str) -> tuple[int, str]:
    group = load_group(root, group_id)
    if not group:
        return EXIT_REFUSED, f"REFUSED: no walk {group_id} in {WALKS_REL}/"
    found = next((f for f in tally(group) if f["n"] == n), None)
    if found is None:
        return EXIT_REFUSED, f"REFUSED: the walk {group_id} has no finding {n}"
    if how in ("test", "owner") and not (root / value).is_file():
        return EXIT_REFUSED, f"REFUSED: no file {value}" + (" (the test that reproduces it)" if how == "test" else " (the question in tasks/blocked/)")
    if how == "owner" and not value.startswith("tasks/"):
        return EXIT_REFUSED, "REFUSED: a product question is a task in tasks/blocked/ (`board.py open-item --to blocked`)"
    if how == "reject" and len(value.strip()) < 12:
        return EXIT_REFUSED, "REFUSED: a rejection says why, in a sentence"
    group.setdefault("dispositions", {})[found["key"]] = {"how": how, "value": value, "utc": ov.utc_now()}
    ov.write_json(group_path(root, group_id), group)
    render(root, group)
    return EXIT_OK, f"finding {n} of {group_id}: {how} — {value}"


def enabled(root: Path) -> bool:
    calibration = ov.read_json(root / CALIBRATION_REL)
    return calibration.get("passed") is True and calibration.get("pin") == MCP_PIN


def newest(group: JsonObj) -> tuple[str, int]:
    """The order of walks: by time, and within one second by the nanosecond of the request."""
    return str(group.get("utc", "")), int(group.get("created_ns") or 0)


def last_walk(root: Path, unit: str) -> JsonObj | None:
    mine = [g for g in groups(root) if g.get("journey") == unit.lower() and not g.get("calibration")]
    return max(mine, key=newest) if mine else None


def gate(root: Path, unit: str) -> tuple[int, str]:
    if not enabled(root):
        return EXIT_OK, (f"walker: off — no calibration passed on {MCP_PIN} ({CALIBRATION_REL}); the walk is no condition, "
                         "the owner's walk card goes out without it")
    group = last_walk(root, unit)
    if group is None:
        return EXIT_CLOSED, f"walker: {unit} was never walked — `walker.py request {unit} --persona … --url …`"
    valid = [r for r in group["results"].values() if r.get("verdict") != "INVALID"]
    if len(valid) < int(group["runs"]):
        return EXIT_CLOSED, f"walker: the walk {group['group']} has {len(valid)} of {group['runs']} valid runs — run the rest, or request a new walk"
    open_ = [f for f in tally(group) if not f["decision"]]
    if open_:
        return EXIT_CLOSED, (f"walker: {len(open_)} finding(s) of {group['group']} have no decision — "
                             + "; ".join(f"{f['n']}. {f['kind']} «{f['quote']}»" for f in open_[:5])
                             + f" (`walker.py dispose {group['group']} <n> --test <file> | --reject <why> | --owner <task>`)")
    return EXIT_OK, f"walker: {unit} walked ({group['group']}), every finding decided"


def card_note(root: Path, unit: str) -> str:
    """What the owner's walk card says of the walker's last walk of the journey; empty when none."""
    group = last_walk(root, unit)
    if group is None:
        return ""
    verdicts = ", ".join(f"{k}: {r.get('verdict')}" + (f" (крок {r['step']})" if r.get("step") else "")
                         for k, r in sorted(group["results"].items(), key=lambda kv: int(kv[0])))
    lines = [(f"Агент-користувач (user-walker) пройшов цей шлях до вас: {verdicts or 'ще не пройшов'}. Це сито, не перевірка: "
              "він пропускає більшість тонких вад.")]
    for f in tally(group):
        if f["counted"]:
            lines.append(f"- Подивіться саме це — крок {f['step']}: {f['kind']} «{f['quote']}» (у {len(f['runs'])} з {group['runs']} прогонів)")
    return "\n".join(lines) + "\n"


def render(root: Path, group: JsonObj) -> None:
    rows = "\n".join(f"| {k} | {r.get('verdict')} | {r.get('step') or ''} | {r.get('steps', '')} | "
                     f"{'так, крок ' + str(r['would_call_for_help'].get('step')) if (r.get('would_call_for_help') or {}).get('yes') else 'ні'} | {r.get('reason', '')} |"
                     for k, r in sorted(group["results"].items(), key=lambda kv: int(kv[0])))
    found = "\n".join(f"| {f['n']} | {f['step']} | {f['kind']} | «{f['quote']}» | {', '.join(f['runs'])} | {'так' if f['counted'] else 'ні'} | "
                      f"{(f['decision']['how'] + ': ' + f['decision']['value']) if f['decision'] else '—'} |" for f in tally(group))
    text = (f"# Walk {group['group']}\n\nJourney: {group['journey']} · persona: {group['persona']} · {group['url']} · budget {group['budget']} "
            f"steps · {MCP_PIN}{' · calibration: ' + group['calibration'] if group.get('calibration') else ''}\n\nМета: {group['goal']}\n\n"
            f"| Run | Verdict | Step | Steps | Would call for help | Reason |\n|---|---|---|---|---|---|\n{rows}\n\n"
            f"## Findings\n\nA finding counts when it recurred in 2 runs or more, or a test reproduces it; every one needs a decision "
            f"(`walker.py dispose`).\n\n| N | Step | Kind | Quote | Runs | Counts | Decision |\n|---|---|---|---|---|---|---|\n{found}\n")
    path = root / WALKS_REL / f"{group['group']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def calibrate(root: Path) -> tuple[int, str]:
    """The calibration eval: the last walk of each case of the calibration cases (CASES_REL) against its thresholds."""
    cases = ov.read_json(root / CASES_REL)
    seeded, clean = cases.get("seeded", {}), cases.get("clean", {})
    out: JsonObj = {"pin": MCP_PIN, "utc": ov.utc_now(), "cases": {}}
    found = 0
    for case, spec in [*seeded.items(), *clean.items()]:
        walks = [g for g in groups(root) if g.get("calibration") == case]
        group = max(walks, key=newest) if walks else None
        valid = [r for r in (group or {}).get("results", {}).values() if r.get("verdict") != "INVALID"]
        if group is None or len(valid) < RUNS:
            out["cases"][case] = {"walk": group["group"] if group else None, "result": "not run"}
            continue
        counted = [f for f in tally(group) if len(f["runs"]) >= 2]
        if case in seeded:
            hit = any(f["kind"] in spec.get("kinds", []) for f in counted)
            found += hit
            out["cases"][case] = {"walk": group["group"], "result": "found" if hit else "missed"}
        else:
            false = [f for f in counted if f["kind"] != "unclear_text"]
            out["cases"][case] = {"walk": group["group"], "result": f"{len(false)} false finding(s)", "false": len(false)}
    need, most = int(cases.get("need_seeded", 3)), int(cases.get("max_false", 1))
    clean_ok = bool(clean) and all(isinstance(out["cases"].get(c, {}).get("false"), int) and out["cases"][c]["false"] <= most for c in clean)
    out.update({"seeded_found": found, "seeded_total": len(seeded), "passed": bool(seeded) and found >= need and clean_ok})
    ov.write_json(root / CALIBRATION_REL, out)
    said = f"calibration: {found} of {len(seeded)} seeded defects found (need {need}); clean: " + \
        "; ".join(f"{c} {out['cases'][c]['result']}" for c in clean) + f" → {'PASSED: the walker is on' if out['passed'] else 'not passed: the walker stays off'}"
    return (EXIT_OK if out["passed"] else EXIT_CLOSED), said


# ------------------------------------------------------------------ the walker's two servers


def browser_argv(root: Path) -> list[str] | None:
    waiting = pending(root)
    if waiting is None:
        return None
    here = run_dir(root, str(waiting["id"]))
    asked = ov.read_json(here / "request.json")
    argv = ["npx", "-y", MCP_PIN, "--config", str(here / "browser.json"), "--device", DEVICE, "--isolated", "--caps=vision",
            "--snapshot-mode", "none", "--allowed-origins", str(asked["origin"]), "--output-dir", str(here / "shots")]
    return argv + (["--storage-state", str(asked["storage_state"])] if asked.get("storage_state") else [])


def tts_command(root: Path) -> str:
    if os.environ.get("WALKER_TTS"):
        return os.environ["WALKER_TTS"]
    env = root / ".claude/project.env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.is_file() else []
    return next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("WALKER_TTS=")), "")


def say(root: Path, text: str) -> tuple[bool, str]:
    """Speak `text` into the walker's microphone: the TTS writes the run's voice.wav, which the browser
    reads at the next press of the microphone (sketch .engine/sketches/walker-voice.md)."""
    waiting, template = pending(root), tts_command(root)
    if waiting is None:
        return False, "no walk is pending"
    if not template:
        return False, "no voice: WALKER_TTS is not set (.claude/project.env) — a person who cannot speak here cannot go on"
    out = run_dir(root, str(waiting["id"])) / "voice.wav"
    argv = [arg.replace("{text}", text).replace("{out}", str(out)) for arg in shlex.split(template)]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"the voice failed: {exc}"
    if done.returncode != 0 or not out.is_file():
        return False, f"the voice failed (exit {done.returncode}): {ov.one_line(done.stderr, 200)}"
    return True, "сказано: натисніть мікрофон, коли треба, — фраза прозвучить у нього"


SAY_TOOL = {"name": "say", "description": "Say a phrase aloud into the phone's microphone. Press the microphone on the screen, then say, as a person would.",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}


def say_server(root: Path) -> int:
    """A minimal MCP server over stdio (newline-delimited JSON-RPC) with the one tool `say`."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        method, params = message.get("method"), message.get("params") or {}
        if method == "initialize":
            result: JsonObj = {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                               "serverInfo": {"name": "walker_voice", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [SAY_TOOL]}
        elif method == "tools/call" and params.get("name") == "say":
            ok, said = say(root, str((params.get("arguments") or {}).get("text", "")))
            result = {"content": [{"type": "text", "text": said}], "isError": not ok}
        elif method == "ping":
            result = {}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": f"no method {method}"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}, ensure_ascii=False), flush=True)
    return EXIT_OK


def status(root: Path) -> int:
    waiting = pending(root)
    print(f"walker:          {'on' if enabled(root) else 'off (no calibration passed on ' + MCP_PIN + ')'}")
    print(f"pending run:     {launch_line(waiting['id']) if waiting else 'none'}")
    for group in sorted(groups(root), key=newest)[-5:]:
        verdicts = " ".join(str(r.get("verdict")) for _, r in sorted(group["results"].items(), key=lambda kv: int(kv[0])))
        print(f"  {group['group']}  {group['journey']}  {group['persona']}  {verdicts or '—'}  findings {len(tally(group))}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    asking = commands.add_parser("request")
    asking.add_argument("journey")
    asking.add_argument("--persona", required=True)
    asking.add_argument("--url", required=True)
    asking.add_argument("--runs", type=int, default=RUNS)
    asking.add_argument("--budget", type=int, default=0)
    asking.add_argument("--storage-state", default="")
    asking.add_argument("--voice", action="store_true")
    asking.add_argument("--goal", default="")
    asking.add_argument("--calibration", default="")
    for name in ("guard", "record"):
        commands.add_parser(name).add_argument("--inside", action="store_true")
    deciding = commands.add_parser("dispose")
    deciding.add_argument("group")
    deciding.add_argument("n", type=int)
    how = deciding.add_mutually_exclusive_group(required=True)
    how.add_argument("--test")
    how.add_argument("--reject")
    how.add_argument("--owner")
    commands.add_parser("gate").add_argument("journey")
    for name in ("browser", "say-server", "calibrate", "status"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    root = ov.project_root()
    if args.command in ("guard", "record"):
        envelope = ov.read_envelope()
        answer = guard(root, envelope, args.inside) if args.command == "guard" else record(root, envelope, args.inside)
        if answer is not None:
            print(json.dumps(answer, ensure_ascii=False))
        return EXIT_OK
    if args.command == "browser":
        command = browser_argv(root)
        if command is None:
            print("walker browser: no walk is pending", file=sys.stderr)
            return EXIT_REFUSED
        os.execvp(command[0], command)
    if args.command == "say-server":
        return say_server(root)
    if args.command == "status":
        return status(root)
    if args.command == "request":
        code, said = request(root, args.journey, args.persona, args.url, args.runs, args.budget, args.storage_state, args.voice,
                             args.goal, args.calibration)
    elif args.command == "dispose":
        how_ = "test" if args.test else "reject" if args.reject else "owner"
        code, said = dispose(root, args.group, args.n, how_, args.test or args.reject or args.owner)
    elif args.command == "gate":
        code, said = gate(root, args.journey)
    else:
        code, said = calibrate(root)
    print(said, file=sys.stdout if code in (EXIT_OK, EXIT_CLOSED) and not said.startswith("REFUSED") else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
