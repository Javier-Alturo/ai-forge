"""Lead scraper storage and filtering (no network; fictional leads)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ls = pytest.importorskip("agents.lead_scraper")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "leads.json"
    monkeypatch.setattr(ls, "LEADS_DB", path)
    return path


def test_save_and_dedupe_urls(db):
    ls._save_to_db({"url": "https://example.com/job/1", "title": "Bot de reservas"})
    ls._save_to_db({"url": "https://example.com/job/2", "title": "Agente RAG"})
    assert ls._load_db() == {"https://example.com/job/1", "https://example.com/job/2"}


def test_corrupt_db_is_backed_up_not_overwritten(db):
    db.write_text('[{"url": "https://example.com/old"', encoding="utf-8")
    ls._save_to_db({"url": "https://example.com/new"})
    assert ls._load_db() == {"https://example.com/new"}
    backups = list(db.parent.glob("leads.json.corrupt-*"))
    assert backups and "example.com/old" in backups[0].read_text(encoding="utf-8")


@pytest.mark.parametrize(("title", "valid"), [
    ("Need an n8n automation expert", True),
    ("[For Hire] Python developer, see my portfolio", False),
    ("SEO services agency", False),
])
def test_lead_filter(title, valid):
    assert ls._is_valid_lead(title, "") is valid


def test_data_dir_is_repo_relative():
    assert ls.DATA_DIR.is_absolute() and ls.DATA_DIR.name == "data"
