"""wsp_sync_report: the Obsidian note has real Markdown checklists (no literal "\\n")."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import wsp_sync_report as report  # noqa: E402

HABITS = [
    {"id": "h1", "title": "Leer 20 min", "streak": 3, "last_completed": None},
    {"id": "h2", "title": "Caminar", "streak": 0, "last_completed": None},
]
GOALS = [{"id": "g1", "title": "Aprender Docker", "progress": 40.0, "level": 2, "xp": 120}]


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OBSIDIAN_VAULT", str(tmp_path))
    monkeypatch.setattr(report, "_load", lambda path: HABITS if path == report._HABITS_FILE else GOALS)
    return tmp_path


def _note_text(vault: Path) -> str:
    notes = list(vault.rglob("*.md"))
    assert len(notes) == 1
    return notes[0].read_text(encoding="utf-8")


def test_note_has_real_checklist_lines(vault):
    result = report.save_to_obsidian("resumen", ["  ✅ Leer 20 min"], ["  ⬜ Caminar"], {})
    assert result.startswith("✅")
    text = _note_text(vault)
    assert "\\n" not in text
    assert "- [x] Leer 20 min\n" in text
    assert "- [ ] Caminar\n" in text


def test_note_empty_lists(vault):
    report.save_to_obsidian("resumen", [], [], {})
    text = _note_text(vault)
    assert "- [ ] (ninguno detectado)\n" in text
    assert "Todo completado" in text


def test_missing_vault_is_reported(monkeypatch):
    monkeypatch.setattr(report, "OBSIDIAN_VAULT", "")
    assert "no configurado" in report.save_to_obsidian("r", [], [], {})


def test_summary_and_whatsapp_text(vault):
    summary = report.generate_summary(["  ✅ Leer 20 min"], ["  ⬜ Caminar"], {"interpretation_notes": "ok"})
    assert "Aprender Docker" in summary and "Leer 20 min" in summary
    wsp = report.build_wsp_summary(summary)
    assert "╔" not in wsp and "║" not in wsp


def test_daily_sync_still_exposes_report_functions():
    sync = pytest.importorskip("agents.wsp_daily_sync")
    assert sync.save_to_obsidian is report.save_to_obsidian
