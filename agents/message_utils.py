"""Utilidades para mensajes de grafos LangGraph."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


def extract_final_ai_text(state: dict[str, Any]) -> str:
    """Extrae el texto final del último AIMessage en el estado."""
    msgs = state.get("messages") or []
    if not msgs:
        return ""

    last = msgs[-1]
    if isinstance(last, AIMessage):
        content = last.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif isinstance(block, str):
                    parts.append(block)
            joined = "".join(parts).strip()
            if joined:
                return joined

    return str(getattr(last, "content", "") or "").strip()
