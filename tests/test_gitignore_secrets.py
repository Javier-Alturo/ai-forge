"""Regression test: credential and session files must stay git-ignored."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MUST_BE_IGNORED = [
    ".env",
    ".env.local",
    "credentials.json",
    "client_secret_123.json",
    "token.json",
    "token_calendar.json",
    "server.pem",
    "id.key",
    "mcp_servers.json",
    "mcp_debug.log",
    "memory_store.json",
    "data/whatsapp_session/Default/Cookies",
    "data/whatsapp_session_old_20260101/Default/Cookies",
    "data/wsp_listener_state.json",
    "data/browser_sessions/state.json",
    "data/git_approvals/abcd1234.json",
    "data/chromadb/chroma.sqlite3",
    "data/fitness/log.json",
    "data/marketing_leads_db.json",
]

MUST_NOT_BE_IGNORED = [".env.example", "mcp_servers.example.json", "agents/llm.py"]


def _ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.mark.parametrize("path", MUST_BE_IGNORED)
def test_secret_paths_are_ignored(path):
    assert _ignored(path), f"{path} is not git-ignored"


@pytest.mark.parametrize("path", MUST_NOT_BE_IGNORED)
def test_examples_are_not_ignored(path):
    assert not _ignored(path), f"{path} should be committable"
