"""Live view of the dashboard: served from file and in sync with the agent registry."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agents.orchestrator_tools import SUBAGENTS  # noqa: E402
from dashboard.app import app  # noqa: E402

LIVE_HTML = (ROOT / "dashboard" / "live.html").read_text(encoding="utf-8")


def test_live_page_is_served():
    response = TestClient(app).get("/live")
    assert response.status_code == 200
    assert "/ws/logs" in response.text and "/ws/chat/" in response.text


def test_live_page_draws_every_subagent():
    """A new sub-agent must get a node, or its calls would never show up in the graph."""
    block = re.search(r"const AGENTS = \[(.*?)\];", LIVE_HTML, re.S).group(1)
    drawn = set(re.findall(r'\["(\w+)",', block))
    assert drawn == {name for name, _, _ in SUBAGENTS}


def test_live_page_loads_nothing_from_other_hosts():
    """Local-first: no CDN scripts, fonts or styles."""
    assert re.findall(r'(?:src|href)="(?:https?:)?//', LIVE_HTML) == []
