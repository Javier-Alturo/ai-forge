"""Morning briefing dashboard: template served from file, task toggling on a fictional note."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")
dash = pytest.importorskip("scripts.morning_briefing_dashboard")


@pytest.fixture
def client(tmp_path, monkeypatch):
    notes = tmp_path / "Daily Notes"
    notes.mkdir()
    (notes / f"{date.today().isoformat()}.md").write_text("# Hoy\n- [ ] Leer docs\n  - [x] Caminar\n", encoding="utf-8")
    monkeypatch.setattr(dash, "get_vault_path", lambda: tmp_path)
    return testclient.TestClient(dash.app), notes


def test_index_serves_template(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200 and "<!DOCTYPE html>" in r.text


def test_toggle_task_updates_note_preserving_indent(client):
    c, notes = client
    r = c.post("/api/tasks/toggle", json={"task_text": "Leer docs", "completed": True})
    assert r.status_code == 200
    text = (notes / f"{date.today().isoformat()}.md").read_text(encoding="utf-8")
    assert "- [x] Leer docs" in text and "  - [x] Caminar" in text


def test_unknown_task_is_404(client):
    c, _ = client
    assert c.post("/api/tasks/toggle", json={"task_text": "nope", "completed": True}).status_code == 404


def test_missing_vault_returns_empty(monkeypatch):
    def broken():
        raise ValueError("OBSIDIAN_VAULT_PATH no está configurado")

    monkeypatch.setattr(dash, "get_vault_path", broken)
    assert dash.read_daily_tasks() == [] and dash.get_briefing_content() == ""
