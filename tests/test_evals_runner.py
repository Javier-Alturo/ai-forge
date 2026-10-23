"""evals.run: output location, private-data guard, suite selection (suites stubbed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals import run as runner  # noqa: E402


@pytest.fixture
def stubbed(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(datasets, "PRIVATE_DIR", tmp_path / "private")
    monkeypatch.setattr(datasets, "PRIVATE_RESULTS_DIR", tmp_path / "private" / "results")
    monkeypatch.setattr(runner, "check_ollama", lambda base: None)
    calls = []

    def fake_run_suite(name, items, llm, include_private, private_only):
        calls.append((name, len(items)))
        return {"accuracy": 1.0, "n": len(items)}

    monkeypatch.setattr(runner, "run_suite", fake_run_suite)
    monkeypatch.setattr(runner, "summarize", lambda name, result: f"{name} ok")
    return tmp_path, calls


def test_generic_results_go_to_results_dir(stubbed):
    tmp_path, calls = stubbed
    report = runner.main(["--suite", "routing", "--limit", "3"])
    assert calls == [("routing", 3)]
    files = list((tmp_path / "results").glob("eval-*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["uses_private_data"] is False and saved == report


def test_private_results_stay_private(stubbed):
    tmp_path, _ = stubbed
    (tmp_path / "private").mkdir()
    runner.main(["--suite", "memory_gate", "--private"])
    assert list((tmp_path / "private" / "results").glob("eval-*.json"))
    assert not (tmp_path / "results").exists()


def test_private_results_cannot_be_written_outside(stubbed):
    tmp_path, _ = stubbed
    with pytest.raises(SystemExit, match="evals/private"):
        runner.main(["--suite", "routing", "--private", "--limit", "1", "--out", str(tmp_path / "leak.json")])


def test_forces_local_llm(stubbed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cloud")
    runner.main(["--suite", "routing", "--limit", "1"])
    import os

    assert os.environ["LLM_PROVIDER"] == "local"
