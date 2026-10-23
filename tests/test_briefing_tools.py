"""Local briefing tools: task extraction, daily note, past pending tasks, tool registry."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ext = pytest.importorskip("agents.briefing_external_tools")
mbt = pytest.importorskip("agents.morning_briefing_tools")

def test_extract_open_tasks_ignores_done_and_empty():
    md = "- [ ] uno\n- [x] hecho\n  - [ ] dos\n- [ ]   \ntexto"
    assert mbt.extract_open_tasks(md) == ["uno", "dos"]


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(mbt, "get_vault_path", lambda: tmp_path)
    return tmp_path


def test_daily_note_created_from_template(vault):
    out = mbt.briefing_get_daily_note_tasks.invoke({})
    assert "Nueva Daily Note creada" in out and "Hacer ejercicio" in out
    assert (vault / "Daily Notes" / f"{date.today().isoformat()}.md").exists()


def test_past_pending_tasks(vault):
    notes = vault / "Daily Notes"
    notes.mkdir()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (notes / f"{yesterday}.md").write_text("- [ ] pendiente\n- [x] hecha", encoding="utf-8")
    out = mbt.briefing_get_past_pending_tasks.invoke({})
    assert "Hace 1 día(s)" in out and "pendiente" in out and "hecha" not in out


def test_tool_registry_and_reexports():
    names = {t.name for t in mbt.get_briefing_tools()}
    assert len(names) == 8
    assert mbt.briefing_get_rss_news is ext.briefing_get_rss_news
