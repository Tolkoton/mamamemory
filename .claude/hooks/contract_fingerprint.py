#!/usr/bin/env python3
"""The fingerprint of an approved slice contract.

    python3 .claude/hooks/contract_fingerprint.py seal  <contract.md>   # after the critic's PASS
    python3 .claude/hooks/contract_fingerprint.py check <contract.md>   # before an audit

WHY. A slice contract is approved once — by the planner-critic loop in /plan-slice — and the
overseer then audits the work against it. Nothing stopped a session from editing the
contract afterwards: lower the exit criterion, drop a behaviour from the list, and the audit
passes against a goalpost that moved. `seal` writes the SHA-256 of the contract as it was
approved into machine state (`.claude/state/contracts/<slug>.sha256`) and REFUSES to
overwrite a fingerprint that exists — re-approving a changed contract is a human act (delete
the fingerprint consciously, or run /plan-slice on a new slug). `check` compares the
contract on disk with its fingerprint; overseer_stop.py calls it before injecting an audit
request and, on a mismatch, escalates instead of auditing.

Exit status: 0 sealed / match; 3 fingerprint exists (seal) or contract changed (check);
4 no fingerprint (check — a contract approved before this existed is audited as before);
2 usage or a missing contract. Machine state only; nothing under .engine/ is written.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

STATE_DIR = Path(".claude") / "state" / "contracts"
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


def seal(root: Path, contract: Path) -> int:
    target = fingerprint_path(root, contract)
    if target.exists():
        print(
            f"REFUSED: {target.relative_to(root)} already holds the fingerprint of an approved contract. "
            "A changed contract is re-approved by a human: delete the fingerprint on purpose, or plan a new slug.",
            file=sys.stderr,
        )
        return EXIT_MISMATCH
    target.parent.mkdir(parents=True, exist_ok=True)
    value = digest(contract)
    target.write_text(f"{value}  {contract.relative_to(root).as_posix() if contract.is_relative_to(root) else contract}\n", encoding="utf-8")
    print(f"sealed {contract.relative_to(root) if contract.is_relative_to(root) else contract}  sha256 {value[:12]}…  -> {target.relative_to(root)}")
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
