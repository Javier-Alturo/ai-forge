"""Tests for the guarded MCP repo tools: push / merge need human approval, public repo blocked."""

from __future__ import annotations

import importlib
import subprocess
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


# ── MCP server tools against a throwaway repo ────────────────────────────────

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def server(tmp_path, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts"))
    mod = importlib.import_module("mcp_aiforge_server")
    monkeypatch.setattr(mod, "_ROOT", repo)
    pushes = []
    real_run = mod._run_git

    def fake_run(args, with_auth=False):
        if args and args[0] == "push":
            pushes.append(args)
            return "pushed"
        return real_run(args, with_auth)

    monkeypatch.setattr(mod, "_run_git", fake_run)
    mod._test_pushes = pushes
    return mod, repo


def test_push_to_public_remote_refused(server):
    mod, repo = server
    _git(repo, "remote", "add", "origin", "https://github.com/someone/ai-forge.git")
    out = mod.aiforge_commit_push("feat: x", "a.txt")
    assert out.startswith("⛔")
    assert mod._test_pushes == []


def test_dot_pathspec_refused(server):
    mod, repo = server
    _git(repo, "remote", "add", "origin", "https://github.com/someone/ai-forge-private.git")
    assert mod.aiforge_commit_push("feat: x", ".").startswith("⛔")


def test_push_requires_human_approval(server):
    mod, repo = server
    _git(repo, "remote", "add", "origin", "https://github.com/someone/ai-forge-private.git")
    out = mod.aiforge_commit_push("feat: x", "a.txt")
    assert "approve_git_action.py" in out and mod._test_pushes == []
    approval_id = out.split("approval_id=\"")[1].split("\"")[0]

    # The LLM retrying with the id before a human approves must not push.
    assert mod.aiforge_commit_push("feat: x", "a.txt", approval_id=approval_id).startswith("⛔")
    assert mod._test_pushes == []

    git_guard.approve(approval_id)
    out = mod.aiforge_commit_push("feat: x", "a.txt", approval_id=approval_id)
    assert out.startswith("📤")
    assert mod._test_pushes == [["push", "origin", "main"]]


def test_merge_requires_human_approval(server, monkeypatch):
    mod, _ = server
    calls = []
    monkeypatch.setattr(mod, "_github_api", lambda *a, **k: calls.append(a) or {"sha": "abcdef123"})
    out = mod.aiforge_merge_pr(7)
    assert "approve_git_action.py" in out and calls == []
    approval_id = out.split("approval_id=\"")[1].split("\"")[0]
    git_guard.approve(approval_id)
    assert mod.aiforge_merge_pr(7, approval_id=approval_id).startswith("✅")
    assert len(calls) == 1


def test_github_api_refuses_public_repo(server, monkeypatch):
    mod, _ = server
    monkeypatch.setattr(mod, "GITHUB_TOKEN", "dummy")
    monkeypatch.setattr(mod, "REPO_SLUG", "someone/ai-forge")
    with pytest.raises(GitGuardError):
        mod._github_api("GET", "pulls")
