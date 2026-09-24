"""Convencion de resultados uniforme para las tools de AI-Forge.

Todas las tools deben retornar strings (requisito de LangChain tools),
pero con prefijos consistentes para que el orquestador pueda interpretarlos.

Uso:
    from agents.result import ok, err, warn

    return ok(f"Se indexaron {n} documentos.")
    return err("El archivo no existe.")
    return warn("La operacion se completo con advertencias.")
"""

from __future__ import annotations


def ok(data: str) -> str:
    """Resultado exitoso. Retorna el mensaje tal cual (sin prefijo para no saturar)."""
    return data.strip() if data else "(sin resultado)"


def err(message: str, exc: Exception | None = None) -> str:
    """Error controlado. Prefijo [ERROR] para que el orquestador lo identifique."""
    base = f"[ERROR] {message.strip()}"
    if exc is not None:
        base += f": {type(exc).__name__}: {exc}"
    return base


def warn(message: str) -> str:
    """Advertencia no fatal. Prefijo [WARN]."""
    return f"[WARN] {message.strip()}"
