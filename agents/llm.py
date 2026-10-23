"""Selector de LLM: local (Ollama) o cloud (Anthropic). Configuración vía .env / entorno."""

from __future__ import annotations

import os
from functools import lru_cache
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
    - cloud: ChatAnthropic (requiere ANTHROPIC_API_KEY y AIFORGE_ALLOW_CLOUD=1)

    Los clientes se reutilizan (uno por proveedor/modelo/temperatura) en vez de crear
    uno nuevo, con su propio pool de conexiones HTTP, en cada llamada.
    """
    if LLM_PROVIDER == "cloud":
        from core.cloud_policy import require_cloud_allowed

        # El interruptor se verifica en cada llamada, también cuando el cliente ya está en caché.
        require_cloud_allowed("LLM_PROVIDER=cloud")
        return _cloud_llm(ANTHROPIC_MODEL, round(float(temperature), 3))
    return _local_llm(OLLAMA_MODEL, OLLAMA_BASE, round(float(temperature), 3))


@lru_cache(maxsize=16)
def _cloud_llm(model: str, temperature: float) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_PROVIDER=cloud requiere ANTHROPIC_API_KEY (variable de entorno o archivo .env)."
        )
    return ChatAnthropic(model=model, api_key=api_key, temperature=temperature)


@lru_cache(maxsize=16)
def _local_llm(model: str, base_url: str, temperature: float) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, base_url=base_url, temperature=temperature)
