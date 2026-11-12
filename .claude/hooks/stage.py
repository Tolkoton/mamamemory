#!/usr/bin/env python3
"""The project's stage — internal, or in production with users — and the one seal it changes.

    python3 .claude/hooks/stage.py show                              # the stage and where it was read
    python3 .claude/hooks/stage.py route REVISE REVISE               # what the cold-reader's answers so far call for
    python3 .claude/hooks/stage.py route REVISE ESCALATE:PRODUCT_DECISION   # an ESCALATE carries its category
    python3 .claude/hooks/stage.py seal <slug> REVISE REVISE PASS    # /plan-slice's seal: the seal itself, or the owner's card

WHY (board 207). Board 314 let /plan-slice seal a slice contract itself after a second technical
CRITIC_REVISE of the cold-reader, with no question to the owner. The owner (2026-11-07): that is
right for their internal projects (thinkhow, mamamemory), and wrong for a project in production
with users — there every change that reaches the users is looked over by the owner first. So the
stage is one line the owner writes, and the planner's seal routes by it.

THE LINE. `.claude/project-stage`: the first line that is not empty and not a `#` comment is
`internal` or `production` (`внутрішній` / `продакшен` read the same). No file → `internal`, the
behaviour before this script. Any other value → `production`: a line the owner wrote and the
script cannot read must not make the agent decide more. The file is in GUARDED_PATTERNS of
protected-path-list.sh: an edit tool and a shell write are refused in a Claude Code session, and
the gate blocks a change of it — only the owner writes it, in their own terminal (or their operator).

WHAT GOES TO THE OWNER in production: `.claude/references/project-stage.md`, the one list.

THE COLD-READER (/plan-slice, «Cold-reader final audit»). `route` takes its answers in order,
each PASS, REVISE or ESCALATE:<category> (the critic's `category`, `CRITIC_` prefix optional),
and prints one word and what to do:
    seal     the last answer is PASS — go on to write the contract and seal it with `seal` below
    rerun    the last is a first or second REVISE, or an ESCALATE of a two-way category
             (DESIGN_FORK, SCOPE_AMENDMENT, ADR_RATIFICATION, BLOCKER_CLASSIFICATION) — resolve it
             (for the ESCALATE: the critic's recommendation, an AUTONOMOUS entry in
             .engine/overseer/escalations.md; after a second REVISE that entry too), spawn a NEW
             fresh cold-reader; never OVERSEER_SLICE_AWAITING_OWNER here, in either stage (board 314)
    park     a third objection the agent resolved itself (REVISE or two-way ESCALATE) — a loop that
             cannot converge: park it, three objections, halt
    owner    the last is an ESCALATE the owner decides (proposal 1787): PRODUCT_DECISION, THRESHOLD,
             ONE_WAY (a one-way door of any category — the planner names it so), and a category the
             script cannot read or none at all: attended AskUserQuestion with the critic's options,
             unattended a park — never decided by the agent, in either stage (Article 5)
`seal` acts on the same answers once the contract is written: a PASS with nothing before it is
sealed in both stages; a PASS after an objection is sealed by the agent in `internal` and, in
`production`, is not sealed — a card goes to tasks/blocked/ with the owner's question and the
action line `reseal-contract <slug> <sha256>`, whose «так» the runner turns into the seal.

Exit status: 0 the route / the seal or the card was written; 3 the answers do not end in PASS
(`seal`), or the contract is sealed already, or no card could be written; 2 usage.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

STAGE_FILE = Path(".claude") / "project-stage"
INTERNAL, PRODUCTION = "internal", "production"
SPELLINGS = {"internal": INTERNAL, "внутрішній": INTERNAL, "production": PRODUCTION, "продакшен": PRODUCTION}
VERDICTS = ("PASS", "REVISE")
ESCALATE = "ESCALATE"
# The critic's classifier (.claude/agents/slice-planner-critic.md, «Escalation») and the two words the planner adds:
# what the owner decides, and what is a two-way door the agent decides and logs. Anything else is read as the owner's.
OWNER_CATEGORIES = ("PRODUCT_DECISION", "THRESHOLD", "ONE_WAY")
TWO_WAY_CATEGORIES = ("DESIGN_FORK", "SCOPE_AMENDMENT", "ADR_RATIFICATION", "BLOCKER_CLASSIFICATION")
MAX_REVISE = 3
EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 2, 3


def project_root() -> Path:
    given = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if given and Path(given).is_dir():
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def read_stage(root: Path) -> tuple[str, str]:
    """(stage, where it came from). No file or no value line → internal; an unknown value → production."""
    path = root / STAGE_FILE
    if not path.is_file():
        return INTERNAL, f"no {STAGE_FILE.as_posix()}: internal by default"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            known = SPELLINGS.get(line.lower())
            if known:
                return known, f"{STAGE_FILE.as_posix()}: {line}"
            return PRODUCTION, f"{STAGE_FILE.as_posix()}: unknown value «{line}», read as production"
    return INTERNAL, f"{STAGE_FILE.as_posix()} has no value line: internal by default"


def category(answer: str) -> str | None:
    """The category of an ESCALATE answer (`ESCALATE:<category>`, "" when none was given); None for PASS / REVISE."""
    head, _, rest = answer.partition(":")
    return rest if head == ESCALATE else None


def owner_decides(answer: str) -> bool:
    """An ESCALATE the owner decides: a product decision, a threshold, a one-way door, or a category not read."""
    found = category(answer)
    return found is not None and found not in TWO_WAY_CATEGORIES


def route(answers: list[str]) -> str:
    """What the cold-reader's answers so far call for: seal, rerun, park or owner."""
    if answers and answers[-1] == "PASS":
        return "seal"
    if answers and owner_decides(answers[-1]):
        return "owner"
    resolved = [a for a in answers if a == "REVISE" or category(a) in TWO_WAY_CATEGORIES]
    return "park" if len(resolved) >= MAX_REVISE else "rerun"


def seal_decision(stage: str, answers: list[str]) -> str:
    """For answers that end in PASS: `seal` (the agent seals) or `owner` (a card for the owner)."""
    return "owner" if stage == PRODUCTION and any(a != "PASS" for a in answers) else "seal"


ROUTE_TEXT = {
    "seal": "the cold-reader passed: write the contract, then `stage.py seal <slug> <the answers>`",
    "rerun": ("resolve the BLOCKING objection (an ESCALATE of a two-way category: take the critic's recommendation and "
              "append an AUTONOMOUS entry with its cost-to-reverse to .engine/overseer/escalations.md) and spawn a NEW fresh "
              "cold-reader; after a second REVISE append an AUTONOMOUS entry first. No OVERSEER_SLICE_AWAITING_OWNER here "
              "(board 314)"),
    "park": ("a third objection: the loop cannot converge — `board.py open-item --to blocked` with the three objections, "
             "then OVERSEER_SLICE_AWAITING_OWNER"),
    "owner": ("the owner decides this ESCALATE (a product decision, a threshold, a one-way door, or a category not read; "
              "Article 5) — never the agent: attended, AskUserQuestion with the critic's question, options and "
              "recommendation verbatim, then a NEW fresh cold-reader; unattended, park it — `board.py open-item --to "
              "blocked` with the same, the slice `CONTRACT PARKED — owner decision` in .engine/PROGRESS.md, and take the "
              "next slice the DAG lets start"),
}


def board_module() -> Any:
    """board.py (the one reader of tasks/), or None where the engine was installed without it."""
    folder = Path(__file__).resolve().parent.parent / "unattended"
    if not (folder / "board.py").is_file():
        return None
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    import board

    return board


def owner_card(root: Path, slug: str, answers: list[str]) -> Path | None:
    """The production card: the question, the action line reseal-contract, an empty answer."""
    board = board_module()
    if board is None:
        return None
    contract = f".engine/slices/{slug}.md"
    question = (f"Slice contract `{contract}` готовий, але не запечатаний: проєкт у стадії production, а cold-reader "
                f"critic-а відповів {' → '.join(answers)}. Перегляньте контракт (і записи AUTONOMOUS у "
                "`.engine/overseer/escalations.md`, якщо вони є). Запечатати його таким, як він є? Варіанти: «так» — "
                "runner запечатає саме цей текст, і slice піде в роботу; інша відповідь — вказівка агентові, що змінити. "
                "Порада: «так», якщо Goal і Exit criterion кажуть те, чого ви хочете.")
    card: Path | None = board.open_item(board.Board(root / "tasks"), "blocked", f"Перегляд slice contract {slug} перед печаткою",
                                        f"Стадія проєкту production (`.claude/project-stage`): печатка контракту після зауважень critic-а — "
                                        f"ваша (board 207, `.claude/references/project-stage.md`). Контракт: `{contract}`.",
                                        question=question, key=f"stage-seal-{slug}", source="stage.py")
    if card is None:
        return None
    text = card.read_text(encoding="utf-8")
    line = board.action_line(root, board.RESEAL_ACTION, slug)
    if line not in text:
        card.write_text(text.replace("\n   Відповідь:\n", f"\n   {line}\n   Відповідь:\n", 1), encoding="utf-8")
    return card


def seal(root: Path, slug: str, answers: list[str]) -> int:
    if route(answers) != "seal":
        print(f"REFUSED: the cold-reader's answers {' '.join(answers) or '(none)'} do not end in PASS — "
              f"{ROUTE_TEXT[route(answers)]}", file=sys.stderr)
        return EXIT_REFUSED
    contract = root / ".engine" / "slices" / f"{slug}.md"
    if not contract.is_file():
        print(f"no such contract: {contract}", file=sys.stderr)
        return EXIT_USAGE
    stage, source = read_stage(root)
    if seal_decision(stage, answers) == "seal":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import contract_fingerprint

        return contract_fingerprint.seal(root, contract.resolve())
    card = owner_card(root, slug, answers)
    if card is None:
        print(f"REFUSED: stage production ({source}) and no card could be written in tasks/blocked/; "
              "the contract stays unsealed", file=sys.stderr)
        return EXIT_REFUSED
    print(f"NOT SEALED — stage production ({source}): the owner looks the contract over first. "
          f"Card: {card.relative_to(root)}. Mark the slice `CONTRACT PARKED — owner review` in .engine/PROGRESS.md "
          "and take the next slice the DAG lets start.")
    return EXIT_OK


def answers_of(words: list[str]) -> list[str] | None:
    answers = [w.upper().removeprefix("CRITIC_").replace("-", "_") for w in words]
    return answers if all(a in VERDICTS or category(a) is not None for a in answers) else None


def main(argv: list[str]) -> int:
    root = project_root()
    if argv[:1] == ["show"] and len(argv) == 1:
        stage, source = read_stage(root)
        print(f"{stage}  ({source})")
        return EXIT_OK
    if argv[:1] == ["route"] and (answers := answers_of(argv[1:])) is not None:
        verdict = route(answers)
        print(f"{verdict}: {ROUTE_TEXT[verdict]}")
        return EXIT_OK
    if argv[:1] == ["seal"] and len(argv) >= 3 and (answers := answers_of(argv[2:])) is not None:
        return seal(root, argv[1], answers)
    print((__doc__ or "").split("\n\n")[0], file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
