"""Selector de LLM: local (Ollama) o cloud (Anthropic). Configuración vía .env / entorno."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local").strip().lower()

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def format_llm_cli_banner() -> str:
    """Una línea legible para la CLI (local vs cloud)."""
    if LLM_PROVIDER == "cloud":
        return f"LLM: cloud (Anthropic) | modelo: {ANTHROPIC_MODEL}"
    return f"LLM: local (Ollama) | {OLLAMA_BASE} | modelo: {OLLAMA_MODEL}"


def get_llm(temperature: float = 0.15) -> BaseChatModel:
    """
    Devuelve el chat model según LLM_PROVIDER:
    - local (default): ChatOllama
    - cloud: ChatAnthropic (requiere ANTHROPIC_API_KEY)
    """
    if LLM_PROVIDER == "cloud":
        from langchain_anthropic import ChatAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=cloud requiere ANTHROPIC_API_KEY (variable de entorno o archivo .env)."
            )
        return ChatAnthropic(
            model=ANTHROPIC_MODEL,
            api_key=api_key,
            temperature=temperature,
        )

    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE,
        temperature=temperature,
    )
