"""Tests for core.git_guard: blocked remotes, safe pathspecs, redaction and the approval lifecycle."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import git_guard  # noqa: E402
from core.git_guard import GitGuardError  # noqa: E402


@pytest.fixture(autouse=True)
def _approval_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(git_guard, "APPROVAL_DIR", tmp_path / "approvals")
    monkeypatch.delenv("AIFORGE_BLOCKED_REPOS", raising=False)


# ── Pure guard logic ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://github.com/someone/ai-forge.git",
    "https://github.com/someone/ai-forge",
    "git@github.com:someone/ai-forge.git",
    "https://x-access-token:abc@github.com/someone/AI-Forge.git",
])
def test_public_repo_is_blocked(url):
    assert git_guard.is_blocked_remote(url)
    with pytest.raises(GitGuardError):
        git_guard.assert_push_allowed(url)


@pytest.mark.parametrize("url", [
    "https://github.com/someone/ai-forge-private.git",
    "git@github.com:someone/ai-forge-private.git",
    "https://gitlab.com/someone/ai-forge.git",
])
def test_private_repo_is_allowed(url):
    git_guard.assert_push_allowed(url)


def test_extra_blocked_repos_from_env(monkeypatch):
    monkeypatch.setenv("AIFORGE_BLOCKED_REPOS", "someone/other-public")
    assert git_guard.is_blocked_remote("https://github.com/someone/other-public.git")


@pytest.mark.parametrize("files", [[], ["."], ["*"], ["-A"], ["--all"], ["a.py", "."]])
def test_catch_all_pathspecs_refused(files):
    with pytest.raises(GitGuardError):
        git_guard.assert_safe_pathspec(files)


def test_redact_hides_tokens():
    text = "push https://ghp_abc123@github.com/x/y.git github_pat_XYZ_9"
    out = git_guard.redact(text)
    assert "ghp_abc123" not in out and "github_pat_XYZ_9" not in out


def test_approval_lifecycle():
    action = {"type": "push", "remote": "r", "branch": "b"}
    approval_id = git_guard.request_approval(action)
    with pytest.raises(GitGuardError, match="pending"):
        git_guard.consume_approval(approval_id, action)
    git_guard.approve(approval_id)
    with pytest.raises(GitGuardError, match="does not match"):
        git_guard.consume_approval(approval_id, {**action, "branch": "main"})
    git_guard.consume_approval(approval_id, action)
    with pytest.raises(GitGuardError):  # single use
        git_guard.consume_approval(approval_id, action)


def test_expired_approval_refused(monkeypatch):
    action = {"type": "merge", "pr": 1}
    approval_id = git_guard.request_approval(action)
    git_guard.approve(approval_id)
    monkeypatch.setattr(git_guard, "APPROVAL_TTL_SECONDS", -1)
    with pytest.raises(GitGuardError, match="expired"):
        git_guard.consume_approval(approval_id, action)


def test_malformed_id_is_not_approved():
    assert git_guard.load_pending("../../etc/passwd") is None
