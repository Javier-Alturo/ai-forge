"""Orchestrator tool table: names are unique and match the prompt."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_tool_table_names_are_unique_and_stable():
    from agents.orchestrator_tools import SUBAGENTS, tool_name

    names = [tool_name(agent) for agent, _, _ in SUBAGENTS]
    assert len(names) == len(set(names))
    assert "orchestrator_consult_mcp_agent" in names
    assert "orchestrator_consult_web_search_agent" in names


def test_prompt_mentions_every_subagent_tool():
    from agents.orchestrator import ORCH_PROMPT
    from agents.orchestrator_tools import SUBAGENTS, tool_name

    missing = [tool_name(a) for a, _, _ in SUBAGENTS if tool_name(a) not in ORCH_PROMPT]
    assert missing == []
