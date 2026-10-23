"""
Git guard — human-in-the-loop approval for outward-facing git actions.

The MCP repo server lets an LLM run git. Anything that leaves this machine
(push, PR merge) must be approved by a human, outside the LLM loop:

  1. The tool calls `request_approval(...)` -> a pending action is written to
     data/git_approvals/<id>.json and the tool returns the id.
  2. A human runs `python scripts/approve_git_action.py <id>` and types "yes".
  3. The tool is called again with `approval_id=<id>`; `consume_approval`
     checks the action matches exactly and deletes the approval (single use).

Pushes to blocked remotes (the public mirror) are refused even if approved.
Fail-closed: any parse error or mismatch means "not approved".
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
APPROVAL_DIR = Path(os.environ.get("AIFORGE_APPROVAL_DIR", _ROOT / "data" / "git_approvals"))
APPROVAL_TTL_SECONDS = 15 * 60

# Repo names that must never receive a push from an agent. "ai-forge" is the
# public mirror; "ai-forge-private" is allowed. Extend with a comma-separated
# list in AIFORGE_BLOCKED_REPOS (e.g. "owner/other-public-repo").
_DEFAULT_BLOCKED_REPOS = ("ai-forge",)

_GITHUB_REPO_RE = re.compile(r"github\.com[:/]+(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$", re.IGNORECASE)
_TOKEN_RE = re.compile(r"(ghp_|gho_|ghs_|github_pat_)[A-Za-z0-9_]+|https://[^@\s/]+@")


class GitGuardError(RuntimeError):
    """Raised when a git action is refused by the guard."""


def redact(text: str) -> str:
    """Remove GitHub tokens and credentials embedded in URLs before logging."""
    return _TOKEN_RE.sub("[REDACTED]", text)


def parse_github_repo(remote_url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a GitHub remote URL, or None if not GitHub."""
    match = _GITHUB_REPO_RE.search(remote_url.strip())
    if not match:
        return None
    return match.group("owner").lower(), match.group("repo").lower()


def _blocked_repos() -> set[str]:
    extra = os.environ.get("AIFORGE_BLOCKED_REPOS", "")
    items = list(_DEFAULT_BLOCKED_REPOS) + [x for x in extra.split(",") if x.strip()]
    return {x.strip().lower() for x in items}


def is_blocked_remote(remote_url: str) -> bool:
    """True if the remote points to a repo agents must never push to."""
    parsed = parse_github_repo(remote_url)
    if parsed is None:
        return False
    owner, repo = parsed
    blocked = _blocked_repos()
    return repo in blocked or f"{owner}/{repo}" in blocked


def assert_push_allowed(remote_url: str) -> None:
    if is_blocked_remote(remote_url):
        raise GitGuardError(f"Push refused: {redact(remote_url)} is a blocked (public) repository.")


def assert_safe_pathspec(files: list[str]) -> None:
    """Refuse catch-all pathspecs that could sweep personal files into a commit."""
    if not files:
        raise GitGuardError("No files given. List the files to commit explicitly.")
    for item in files:
        if item in {".", "*", "-A", "--all", ":/"} or item.startswith("-"):
            raise GitGuardError(f"Refused pathspec '{item}'. List the files to commit explicitly.")


def request_approval(action: dict) -> str:
    """Store a pending action and return its approval id."""
    APPROVAL_DIR.mkdir(parents=True, exist_ok=True)
    approval_id = secrets.token_hex(4)
    record = {"action": action, "created": time.time(), "approved": False}
    (APPROVAL_DIR / f"{approval_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return approval_id


def load_pending(approval_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{8}", approval_id or ""):
        return None
    path = APPROVAL_DIR / f"{approval_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def approve(approval_id: str) -> None:
    """Mark a pending action as approved. Called only from the human CLI."""
    record = load_pending(approval_id)
    if record is None:
        raise GitGuardError(f"Unknown approval id: {approval_id}")
    record["approved"] = True
    (APPROVAL_DIR / f"{approval_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def consume_approval(approval_id: str, action: dict) -> None:
    """Raise unless `approval_id` is approved, fresh and matches `action`. Single use."""
    record = load_pending(approval_id)
    if record is None:
        raise GitGuardError("No pending approval with that id.")
    if not record.get("approved"):
        raise GitGuardError(f"Approval {approval_id} is still pending. A human must approve it first.")
    if time.time() - record.get("created", 0) > APPROVAL_TTL_SECONDS:
        raise GitGuardError(f"Approval {approval_id} expired. Request a new one.")
    if record.get("action") != action:
        raise GitGuardError("Approved action does not match the requested action.")
    (APPROVAL_DIR / f"{approval_id}.json").unlink(missing_ok=True)
