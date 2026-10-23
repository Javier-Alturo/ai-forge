"""File agent is confined to allowed roots and never touches credentials."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fs_policy import PathNotAllowedError, check_path  # noqa: E402


@pytest.fixture
def roots(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("AIFORGE_FILE_ROOTS", str(allowed))
    return allowed, outside


def test_inside_root_allowed(roots):
    allowed, _ = roots
    assert check_path(str(allowed / "notes.txt")) == (allowed / "notes.txt").resolve()


def test_relative_path_lands_in_root(roots):
    allowed, _ = roots
    assert check_path("sub/a.txt") == (allowed / "sub" / "a.txt").resolve()


@pytest.mark.parametrize("rel", ["../outside/x.txt", "sub/../../outside/x.txt"])
def test_traversal_refused(roots, rel):
    with pytest.raises(PathNotAllowedError):
        check_path(rel)


def test_absolute_outside_refused(roots):
    _, outside = roots
    with pytest.raises(PathNotAllowedError):
        check_path(str(outside / "x.txt"))


@pytest.mark.parametrize("name", [
    ".env", ".env.local", "token.json", "credentials.json", "client_secret_1.json",
    "server.pem", ".git/config", ".ssh/id_rsa", "whatsapp_session_old/Cookies",
])
def test_sensitive_files_refused_even_inside_root(roots, name):
    allowed, _ = roots
    with pytest.raises(PathNotAllowedError):
        check_path(str(allowed / name))


def test_multiple_roots(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("AIFORGE_FILE_ROOTS", os.pathsep.join([str(a), str(b)]))
    check_path(str(b / "ok.txt"))


def test_file_tools_deny_and_allow(roots):
    file_tools = pytest.importorskip("agents.file_tools")
    allowed, outside = roots
    secret = outside / "secret.txt"
    secret.write_text("s", encoding="utf-8")

    assert file_tools.file_read_file.invoke({"path": str(secret)}).startswith("⛔")
    out = file_tools.file_write_file.invoke({"path": str(outside / "evil.txt"), "content": "x"})
    assert out.startswith("⛔") and not (outside / "evil.txt").exists()
    move = {"source_path": str(secret), "destination_path": str(allowed / "s.txt"), "operation": "move"}
    assert file_tools.file_move_or_copy.invoke(move).startswith("⛔")
    assert secret.exists()

    assert file_tools.file_write_file.invoke({"path": "ok.txt", "content": "hi"}).startswith("Escrito OK")
    assert file_tools.file_read_file.invoke({"path": "ok.txt"}) == "hi"


def test_file_search_skips_credentials(roots):
    file_tools = pytest.importorskip("agents.file_tools")
    allowed, _ = roots
    (allowed / ".env").write_text("TOKEN=1", encoding="utf-8")
    (allowed / "a.txt").write_text("TOKEN=1", encoding="utf-8")
    out = file_tools.file_search.invoke({"root_path": str(allowed), "content_substring": "TOKEN"})
    assert "a.txt" in out and ".env" not in out


def test_obsidian_note_cannot_escape_vault(tmp_path, monkeypatch):
    obsidian = pytest.importorskip("agents.obsidian_tools")
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(obsidian, "VAULT_PATH", str(vault))
    out = obsidian.obsidian_write_note.invoke({"title": "../escaped", "content": "x"})
    assert "Error" in out
    assert not (tmp_path / "escaped.md").exists()
    assert "guardada" in obsidian.obsidian_write_note.invoke({"title": "ok", "content": "x"})
