"""TaskForge storage: atomic writes and corrupt-file backups."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import taskforge_store as store  # noqa: E402

NAMES = ("_TASKS_FILE", "_GOALS_FILE", "_HABITS_FILE", "_LOGS_FILE")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_TASKFORGE_DIR", tmp_path)
    for name in NAMES:
        path = tmp_path / f"{name.strip('_').lower().replace('_file', '')}.json"
        monkeypatch.setattr(store, name, path)
    return tmp_path


# ── Storage ──────────────────────────────────────────────────────────────────

def test_corrupt_file_is_backed_up_not_lost(data_dir):
    store._ensure_dirs()
    store._GOALS_FILE.write_text('[{"id": "g1", "title": "Leer"', encoding="utf-8")  # truncated JSON
    assert store._load(store._GOALS_FILE) == []
    backups = list(data_dir.glob("goals.json.corrupt-*"))
    assert len(backups) == 1
    assert '"Leer"' in backups[0].read_text(encoding="utf-8")


def test_save_is_atomic_and_leaves_no_temp_files(data_dir):
    store._save(store._TASKS_FILE, [{"id": "t1"}])
    assert store._load(store._TASKS_FILE) == [{"id": "t1"}]
    assert not list(data_dir.glob(".*.tmp"))


def test_failed_save_keeps_previous_content(data_dir):
    store._save(store._TASKS_FILE, [{"id": "t1"}])
    with pytest.raises(TypeError):
        store._save(store._TASKS_FILE, [{"bad": object()}])  # not JSON serializable
    assert store._load(store._TASKS_FILE) == [{"id": "t1"}]
    assert not list(data_dir.glob(".*.tmp"))
