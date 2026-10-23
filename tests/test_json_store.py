"""core.json_store: corrupt files are backed up, writes are atomic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.json_store import load_json_list, save_json_atomic  # noqa: E402


def test_missing_file_is_empty(tmp_path):
    assert load_json_list(tmp_path / "nope.json") == []


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "items.json"
    save_json_atomic(path, [{"a": 1}])
    assert load_json_list(path) == [{"a": 1}]


def test_corrupt_file_backed_up(tmp_path):
    path = tmp_path / "items.json"
    path.write_text("[{broken", encoding="utf-8")
    assert load_json_list(path) == []
    assert not path.exists()
    assert len(list(tmp_path.glob("items.json.corrupt-*"))) == 1


def test_non_list_json_is_empty(tmp_path):
    path = tmp_path / "items.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    assert load_json_list(path) == []


def test_failed_write_keeps_old_file(tmp_path):
    path = tmp_path / "items.json"
    save_json_atomic(path, [1])
    with pytest.raises(TypeError):
        save_json_atomic(path, [object()])
    assert load_json_list(path) == [1]
    assert not list(tmp_path.glob(".*.tmp"))
