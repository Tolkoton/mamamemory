#!/usr/bin/env python3
"""The fingerprint of an approved slice contract.

    python3 .claude/hooks/contract_fingerprint.py seal  <contract.md>   # after the critic's PASS
    python3 .claude/hooks/contract_fingerprint.py check <contract.md>   # before an audit

WHY. A slice contract is approved once — by the planner-critic loop in /plan-slice — and the
overseer then audits the work against it. Nothing stopped a session from editing the
contract afterwards: lower the exit criterion, drop a behaviour from the list, and the audit
passes against a goalpost that moved. `seal` writes the SHA-256 of the contract as it was
approved into machine state (`.claude/state/contracts/<slug>.sha256`) and REFUSES to
overwrite a fingerprint that exists — re-approving a changed contract is the owner's act (their
«так» under the question that offers `reseal-contract`, below, or /plan-slice on a new slug). `check` compares the
contract on disk with its fingerprint; overseer_stop.py calls it before injecting an audit
request and, on a mismatch, escalates instead of auditing.

RESEALING (board 308). The owner's re-approval of a changed contract is their answer «так» under
the question that shows the change and offers `Дія runner-а: reseal-contract <slug> <sha256 of the
new text>` (board.py `action-line reseal-contract <slug>`). The runner then calls `reseal` through
owner_action.py, which refuses inside a Claude Code session: the new fingerprint is written only
when the contract is still the text the owner saw. There is no command here for it — an agent
neither writes nor deletes a fingerprint that exists.

THE ACCEPTANCE CRITERIA ARE NOT THE AGENT'S (board 412; R4 §3.4). mamamemory's F2 was built in full on
«Acceptance criteria (PROVISIONAL — owner ratification pending)»: product behaviour the agent invented.
`seal` (and stage.py's, which /plan-slice runs) refuses a contract whose acceptance criteria — the
section «Acceptance criteria» of the feature artifact that holds the slice, and of the contract itself
when it has one — carry `PROVISIONAL` or `[NEEDS CLARIFICATION`, or have an item that cites neither a
journey (`J-N#AC-k`), nor a line of the goals (G…, D…), nor the owner's words verbatim with their date
(`2026-11-12 … «…»`), nor is marked technical (`[тех]`). PROVISIONAL stays for technical build parameters.

Exit status: 0 sealed / match; 3 fingerprint exists (seal) or contract changed (check)
or the acceptance criteria are not the owner's (seal);
4 no fingerprint (check — a contract approved before this existed is audited as before);
2 usage or a missing contract. Machine state only; nothing under .engine/ is written.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

STATE_DIR = Path(".claude") / "state" / "contracts"
FEATURES_REL = Path(".engine") / "architecture" / "feature"
AC_HEADING = re.compile(r"^##\s*(?:Acceptance criteria|Критерії приймання)\b(?P<rest>.*)$", re.MULTILINE | re.IGNORECASE)
UNSETTLED = re.compile(r"PROVISIONAL|\[NEEDS CLARIFICATION", re.IGNORECASE)
GROUND = re.compile(r"(?<![\w-])J-\d+#AC-\d+(?![\w-])"            # a sealed journey's criterion (board 208)
                    r"|(?<![\w-])[GD]\d+(?![\w-])"                  # a line of the goals: a goal, a done-when
                    r"|\d{4}-\d\d-\d\d[^«\n]*«[^»]*\S[^»]*»"          # the owner's words verbatim, with their date
                    r"|^\[(?:тех|tech)\]")                           # a technical criterion
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*$")
EXIT_OK, EXIT_USAGE, EXIT_MISMATCH, EXIT_NONE = 0, 2, 3, 4


def project_root() -> Path:
    given = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if given and Path(given).is_dir():
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint_path(root: Path, contract: Path) -> Path:
    return root / STATE_DIR / f"{contract.stem}.sha256"


def criteria(text: str) -> tuple[str, list[str]] | None:
    """(the heading's words after «Acceptance criteria», the items with their continuation lines); None: no such section."""
    match = AC_HEADING.search(text)
    if not match:
        return None
    body = text[match.end():]
    end = re.search(r"^#{1,2}\s", body, re.MULTILINE)
    lines = COMMENT.sub("", body[:end.start()] if end else body).splitlines()
    items: list[str] = []
    for n, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#") or TABLE_RULE.match(line):
            continue
        if line.startswith("|") and n + 1 < len(lines) and TABLE_RULE.match(lines[n + 1]):
            continue  # a table's header row
        if items and line.startswith((" ", "\t")) and not LIST_ITEM.match(line):
            items[-1] += " " + line.strip()  # the continuation of the item above
            continue
        # Every other line is a criterion: a list item of any marker (-, *, +, 1., 1)), a table row, a paragraph —
        # a criterion written in another form is still a criterion (board 412, the overseer's BLOCK of the numbered list).
        items.append(LIST_ITEM.sub("", line, count=1).strip().strip("|").strip())
    return match["rest"], items


def acceptance_errors(root: Path, contract: Path) -> list[str]:
    """Why the acceptance criteria behind this contract are not the owner's (board 412), or []."""
    sources = [(contract, contract.read_text(encoding="utf-8", errors="replace"))]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import testing

        found = testing.feature_of(root, contract.stem)
    except (ImportError, OSError):
        found = None
    if found is not None:
        artifact = root / FEATURES_REL / f"{found[0].name}.md"
        if artifact.is_file():
            sources.append((artifact, artifact.read_text(encoding="utf-8", errors="replace")))
    errors = []
    for path, text in sources:
        read = criteria(text)
        if read is None:
            continue
        where = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        heading, items = read
        if UNSETTLED.search(heading):
            errors.append(f"{where}: «Acceptance criteria{heading}» — criteria the owner has not ratified")
        for item in items:
            if UNSETTLED.search(item):
                errors.append(f"{where}: «{item[:70]}» is PROVISIONAL / NEEDS CLARIFICATION")
            elif not GROUND.search(item):
                errors.append(f"{where}: «{item[:70]}» cites no journey (J-N#AC-k), no goals line (G…, D…), no owner's words "
                              "with their date, and is not `[тех]`")
    return errors


def seal(root: Path, contract: Path) -> int:
    unsettled = acceptance_errors(root, contract)
    if unsettled:
        print("REFUSED: the acceptance criteria are not the owner's (board 412; Article 5) — the contract is not sealed:\n- "
              + "\n- ".join(unsettled) + "\nPROVISIONAL is for technical build parameters only. Park the feature with the question "
              "to the owner (`board.py open-item --to blocked`), or derive the criteria from a sealed journey.", file=sys.stderr)
        return EXIT_MISMATCH
    target = fingerprint_path(root, contract)
    if target.exists():
        print(
            f"REFUSED: {target.relative_to(root)} already holds the fingerprint of an approved contract. "
            "A changed contract is re-approved by the owner: ask with `board.py action-line reseal-contract <slug>` "
            "under the question (board 308), or plan a new slug.",
            file=sys.stderr,
        )
        return EXIT_MISMATCH
    target.parent.mkdir(parents=True, exist_ok=True)
    value = digest(contract)
    target.write_text(f"{value}  {contract.relative_to(root).as_posix() if contract.is_relative_to(root) else contract}\n", encoding="utf-8")
    print(f"sealed {contract.relative_to(root) if contract.is_relative_to(root) else contract}  sha256 {value[:12]}…  -> {target.relative_to(root)}")
    return EXIT_OK


def reseal(root: Path, contract: Path, approved: str) -> int:
    """The owner's re-approval (board 308): seal `contract` anew, over the old fingerprint, only when
    it is the text whose sha256 the owner said «так» to. Called by owner_action.py, never from the CLI."""
    if not contract.is_file():
        print(f"owner-action: no contract {contract.name}; nothing is resealed", file=sys.stderr)
        return EXIT_MISMATCH
    actual = digest(contract)
    if actual != approved:
        print(f"owner-action: {contract.name} is {actual}, the owner approved {approved or '(no sha256)'}; not resealed", file=sys.stderr)
        return EXIT_MISMATCH
    target = fingerprint_path(root, contract)
    before = target.read_text(encoding="utf-8").split()[0] if target.is_file() else "(none)"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{actual}  {contract.relative_to(root).as_posix() if contract.is_relative_to(root) else contract}\n", encoding="utf-8")
    print(f"owner-action: {contract.name} resealed on the owner's answer: {before[:12]}… -> {actual[:12]}…")
    return EXIT_OK


def record_in_gate_format(root: Path, contract: Path, severity: str, message: str) -> None:
    """The verdict also goes to .claude/state/gate/contract_fingerprint-report.json in gate.py's
    report schema. This script stays separate (it gates /plan-slice and the audit, not a file);
    the format is shared. A reporting problem never changes the exit status."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gate as gate_module

        gate_module.record_findings(
            root, "contract_fingerprint", "stop",
            [gate_module.Finding(contract.name, None, "contract-sealed", severity, message,
                                 "re-approving a changed contract is the owner's act")],
        )
    except (ImportError, OSError):
        pass


def check(root: Path, contract: Path) -> int:
    target = fingerprint_path(root, contract)
    if not target.is_file():
        print(f"no fingerprint for {contract.name} ({target.relative_to(root)} absent): approved before sealing existed")
        return EXIT_NONE
    recorded = target.read_text(encoding="utf-8").split()[0]
    actual = digest(contract)
    if recorded == actual:
        print(f"match: {contract.name} is the approved contract ({actual[:12]}…)")
        record_in_gate_format(root, contract, "log", "matches its fingerprint")
        return EXIT_OK
    print(
        f"CHANGED: {contract.name} differs from the contract that was approved "
        f"(approved {recorded[:12]}…, now {actual[:12]}…). No audit against a moved goalpost.",
        file=sys.stderr,
    )
    record_in_gate_format(root, contract, "block", "changed after approval: no audit against a moved goalpost")
    return EXIT_MISMATCH


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("seal", "check"):
        print((__doc__ or "").split("\n\n")[0], file=sys.stderr)
        return EXIT_USAGE
    root = project_root()
    contract = Path(argv[1])
    if not contract.is_absolute():
        contract = root / contract
    if not contract.is_file():
        print(f"no such contract: {contract}", file=sys.stderr)
        return EXIT_USAGE
    return seal(root, contract.resolve()) if argv[0] == "seal" else check(root, contract.resolve())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
