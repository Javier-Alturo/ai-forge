"""Eval metrics and dataset loading (no LLM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets, metrics  # noqa: E402

GOLD = ["a", "a", "b", "b", "c"]
PRED = ["a", "b", "b", "b", "a"]


def test_accuracy():
    assert metrics.accuracy(GOLD, PRED) == 0.6
    assert metrics.accuracy([], []) == 0.0


def test_confusion_matrix():
    m = metrics.confusion_matrix(GOLD, PRED)
    assert m["a"] == {"a": 1, "b": 1, "c": 0}
    assert m["c"]["a"] == 1
    assert sum(sum(row.values()) for row in m.values()) == len(GOLD)


def test_per_class_precision_recall():
    r = metrics.per_class_report(GOLD, PRED)
    # b: predicted 3 times, 2 correct -> precision 2/3; 2 real b, both caught -> recall 1
    assert r["b"] == {"precision": 0.667, "recall": 1.0, "f1": 0.8, "support": 2}
    assert r["c"]["recall"] == 0.0 and r["c"]["support"] == 1


def test_formatters_do_not_crash():
    assert "expected" in metrics.format_confusion(metrics.confusion_matrix(GOLD, PRED))
    assert "prec" in metrics.format_report(metrics.per_class_report(GOLD, PRED))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    generic, private = tmp_path / "datasets", tmp_path / "private"
    generic.mkdir()
    private.mkdir()
    monkeypatch.setattr(datasets, "GENERIC_DIR", generic)
    monkeypatch.setattr(datasets, "PRIVATE_DIR", private)
    (generic / "x.jsonl").write_text('{"q": 1}\n// comment\n\n{"q": 2}\n', encoding="utf-8")
    (private / "x.jsonl").write_text(json.dumps({"q": 3}) + "\n", encoding="utf-8")
    return generic, private


def test_generic_only_by_default(dirs):
    assert [i["q"] for i in datasets.load("x")] == [1, 2]


def test_private_is_opt_in_and_tagged(dirs):
    items = datasets.load("x", include_private=True)
    assert [(i["q"], i["source"]) for i in items] == [(1, "generic"), (2, "generic"), (3, "private")]
    assert [i["q"] for i in datasets.load("x", private_only=True)] == [3]


def test_missing_private_file_is_fine(dirs):
    assert len(datasets.load("other", include_private=True)) == 0


def test_bad_line_reports_position(dirs):
    generic, _ = dirs
    (generic / "bad.jsonl").write_text('{"ok": 1}\n{oops\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        datasets.load("bad")


def test_private_results_never_go_to_public_dir():
    assert datasets.results_dir(True).is_relative_to(datasets.PRIVATE_DIR)
    assert not datasets.results_dir(False).is_relative_to(datasets.PRIVATE_DIR)


def test_committed_baselines_use_only_generic_data():
    baselines = sorted((datasets.EVALS_DIR / "baselines").glob("*.json"))
    for path in baselines:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["uses_private_data"] is False, f"{path.name} was built with private data"
        rag_sources = {a.get("source") for a in report["suites"].get("rag", {}).get("answers", [])}
        assert rag_sources <= {"generic"}, f"{path.name} contains private RAG answers"
