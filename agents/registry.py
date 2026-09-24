"""Registry de agentes: carga agents_config.json y expone helpers para
comprobar si un agente esta activo y obtener sus timeouts configurados.

Uso:
    from agents.registry import get_agent_config, is_enabled

    cfg = get_agent_config("marketing")
    print(cfg.soft_s, cfg.hard_s, cfg.enabled)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _ROOT / "agents_config.json"

_DEFAULT_SOFT = 30
_DEFAULT_HARD = 120


@dataclass(frozen=True)
class AgentConfig:
    name: str
    enabled: bool
    soft_s: int   # avisa al usuario despues de N segundos (sigue esperando)
    hard_s: int   # cancela el agente despues de N segundos (devuelve error)


_registry: dict[str, AgentConfig] | None = None


def _load() -> dict[str, AgentConfig]:
    global _registry
    if _registry is not None:
        return _registry

    raw: dict[str, Any] = {}
    if _CONFIG_FILE.exists():
        try:
            raw = json.loads(_CONFIG_FILE.read_text(encoding="utf-8")).get("agents", {})
        except (json.JSONDecodeError, OSError):
            pass  # Usa defaults si el archivo esta corrupto

    result: dict[str, AgentConfig] = {}
    for name, cfg in raw.items():
        result[name] = AgentConfig(
            name=name,
            enabled=bool(cfg.get("enabled", True)),
            soft_s=int(cfg.get("timeout_soft_s", _DEFAULT_SOFT)),
            hard_s=int(cfg.get("timeout_hard_s", _DEFAULT_HARD)),
        )

    _registry = result
    return _registry


def get_agent_config(name: str) -> AgentConfig:
    """Retorna la config de un agente. Si no existe en el JSON, usa defaults."""
    reg = _load()
    return reg.get(
        name,
        AgentConfig(name=name, enabled=True, soft_s=_DEFAULT_SOFT, hard_s=_DEFAULT_HARD),
    )


def is_enabled(name: str) -> bool:
    """True si el agente esta activo segun agents_config.json."""
    return get_agent_config(name).enabled


def reload() -> None:
    """Fuerza recarga del JSON (util si se edita agents_config.json en caliente)."""
    global _registry
    _registry = None
    _load()
