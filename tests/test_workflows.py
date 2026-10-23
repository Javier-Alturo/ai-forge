"""Guardrails for GitHub Actions workflows (supply chain and merge safety)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))
# Pre-existing workflows not yet pinned by SHA (tracked in docs/security.md). Do not add new ones here.
UNPINNED_ALLOWED: set[str] = set()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_automatic_merge_or_approval(path):
    text = _text(path)
    assert not re.search(r"gh pr (merge|review\s+--approve)", text), "workflows must not merge/approve PRs"
    assert "pulls/{pr_number}/merge" not in text and "/merge\"" not in text
    assert "pull_request_target" not in text, "pull_request_target runs with secrets on fork PRs"
    assert "enable-auto-merge" not in text and "auto-merge" not in path.name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_pinned_to_commit_sha(path):
    if path.name in UNPINNED_ALLOWED:
        pytest.skip("legacy workflow, see docs/security.md")
    for ref in re.findall(r"uses:\s*([^\s#]+)", _text(path)):
        assert re.search(r"@[0-9a-f]{40}$", ref), f"{ref} must be pinned to a full commit SHA"


@pytest.mark.parametrize("name", ["ci.yml", "evals.yml"])
def test_new_workflows_are_read_only(name):
    text = _text(WORKFLOWS[0].parent / name)
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", text, flags=re.M)
    assert "persist-credentials: false" in text


def test_eval_inputs_are_not_interpolated_into_scripts():
    text = _text(WORKFLOWS[0].parent / "evals.yml")
    run_blocks = re.findall(r"run: \|\n((?:\s{10}.*\n)+)", text)
    assert run_blocks and not any("${{ inputs." in block for block in run_blocks)
