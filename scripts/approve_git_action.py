"""
Approve a pending git action (push / merge) requested by the MCP agent.

Usage:
    python scripts/approve_git_action.py          # list pending actions
    python scripts/approve_git_action.py <id>     # review and approve one

Run this yourself in a terminal. The agent cannot approve its own requests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.git_guard import (  # noqa: E402
    APPROVAL_DIR,
    GitGuardError,
    approve,
    load_pending,
)


def _list_pending() -> int:
    files = sorted(APPROVAL_DIR.glob("*.json")) if APPROVAL_DIR.exists() else []
    if not files:
        print("No pending git actions.")
        return 0
    for path in files:
        record = load_pending(path.stem) or {}
        state = "approved" if record.get("approved") else "pending"
        print(f"{path.stem}  [{state}]  {json.dumps(record.get('action', {}))}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return _list_pending()
    approval_id = argv[1]
    record = load_pending(approval_id)
    if record is None:
        print(f"Unknown approval id: {approval_id}")
        return 1
    print(json.dumps(record["action"], indent=2))
    if input("Approve this action? Type 'yes' to confirm: ").strip().lower() != "yes":
        print("Not approved.")
        return 1
    try:
        approve(approval_id)
    except GitGuardError as exc:
        print(exc)
        return 1
    print(f"Approved {approval_id}. Ask the agent to retry with approval_id={approval_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
