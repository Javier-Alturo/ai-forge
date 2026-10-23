"""Obsidian tools: specific error handling, unreadable notes are skipped (fictional notes)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

obs = pytest.importorskip("agents.obsidian_tools")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "VAULT_PATH", str(tmp_path))
    return tmp_path


def test_search_finds_snippet_and_skips_bad_encoding(vault):
    (vault / "ideas.md").write_text("Probar Docker Compose con LangFuse", encoding="utf-8")
    (vault / "binary.md").write_bytes(b"\xff\xfe\x00Docker")  # not valid UTF-8
    out = obs.obsidian_search_notes.invoke({"query": "docker"})
    assert "ideas.md" in out and "binary.md" not in out


def test_missing_vault_is_reported(monkeypatch):
    monkeypatch.setattr(obs, "VAULT_PATH", "")
    assert obs.obsidian_read_note.invoke({"title": "x"}).startswith("Error al leer la nota")


def test_recent_notes(vault):
    (vault / "hoy.md").write_text("nota de hoy", encoding="utf-8")
    assert "hoy.md" in obs.obsidian_get_recent_notes.invoke({"days": 1})
