"""Recover tool calls the local model wrote as plain text.

qwen2.5:14b sometimes garbles the token that opens a tool call, so Ollama's parser sees text:
    ' iNdEx\n{"name": "orchestrator_consult_file_agent", "arguments": {"task": "..."}}'
    ' sourceMapping_agent:consult_fitness_agent({"task": "..."})'
Left alone, that text reaches the user, often followed by an invented result.

To avoid firing tools from a normal answer that happens to quote a call, the call must come right
after at most one garbled token, and its name must resolve to a tool that is actually bound.
Repaired calls then go through the same tools and approvals as any other call.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import uuid
from typing import Iterable

from langchain_core.messages import AIMessage

log = logging.getLogger("ai_forge.tool_call_repair")

TOOL_PREFIX = "orchestrator_"
NAME_CUTOFF = 0.85
_JSON_CALL = re.compile(r'\s*(\S*?)\s*(?=\{\s*"name"\s*:)')
_NAMED_CALL = re.compile(r"\s*(?:\S*?[^\w\s])?([A-Za-z_]\w*)\s*\(?\s*(?=\{)")


def _resolve_name(name: str, tool_names: list[str]) -> str | None:
    if name in tool_names:
        return name
    if TOOL_PREFIX + name in tool_names:
        return TOOL_PREFIX + name
    # The garbled token can be glued to the name: _icall_local_function_orchestrator_consult_mcp_agent
    for tool in tool_names:
        if name.endswith((tool, tool.removeprefix(TOOL_PREFIX))):
            return tool
    close = difflib.get_close_matches(name, tool_names, n=1, cutoff=NAME_CUTOFF)
    return close[0] if close else None


def _decode_object(text: str, start: int) -> dict | None:
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def parse_text_tool_call(text: str, tool_names: Iterable[str]) -> dict | None:
    """Return a tool call dict if `text` starts with a garbled call to a known tool, else None."""
    names = list(tool_names)
    match = _JSON_CALL.match(text)
    if match:
        call = _decode_object(text, match.end()) or {}
        raw_name, args = call.get("name"), call.get("arguments", {})
    else:
        match = _NAMED_CALL.match(text)
        if not match:
            return None
        raw_name, args = match.group(1), _decode_object(text, match.end())
    if not isinstance(raw_name, str) or not isinstance(args, dict):
        return None
    name = _resolve_name(raw_name, names)
    if name is None:
        return None
    return {"name": name, "args": args, "id": f"repaired_{uuid.uuid4().hex[:12]}", "type": "tool_call"}


def repair_message(msg: AIMessage, tool_names: Iterable[str]) -> AIMessage:
    """Turn a text-only tool call into a real one; any other message comes back unchanged."""
    if msg.tool_calls or not isinstance(msg.content, str):
        return msg
    call = parse_text_tool_call(msg.content, tool_names)
    if call is None:
        return msg
    log.warning("Repaired a tool call written as text: %s", call["name"])
    # The text after a garbled call is usually an invented result, so none of it is kept.
    return msg.model_copy(update={"content": "", "tool_calls": [call]})
