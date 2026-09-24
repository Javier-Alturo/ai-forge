"""Herramientas exclusivas para el SkillForge Agent (auto-programación con backup y rollback)."""

from __future__ import annotations

import ast
import os
import shutil
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from core.sandbox.ast_validator import ASTValidator

# Paths
_AGENTS_DIR = Path(__file__).parent
DYNAMIC_TOOLS_FILE = _AGENTS_DIR / "dynamic_tools.py"
BACKUP_DIR = _AGENTS_DIR / "dynamic_tools_history"
MAX_BACKUPS = 20

_validator = ASTValidator()


def _backup_current_tools() -> Path | None:
    """Crea un backup versionado de dynamic_tools.py antes de cualquier escritura."""
    if not DYNAMIC_TOOLS_FILE.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"dynamic_tools_{timestamp}.py"
    shutil.copy2(DYNAMIC_TOOLS_FILE, backup_path)

    # Purgar backups viejos — mantener solo MAX_BACKUPS
    backups = sorted(BACKUP_DIR.glob("*.py"))
    if len(backups) > MAX_BACKUPS:
        for old in backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    a2a_log("skillforge", "backup", "created", str(backup_path))
    return backup_path


def _rollback_to_last_backup() -> bool:
    """Restaura el último backup si la nueva tool rompió el grafo. Retorna True si tuvo éxito."""
    backups = sorted(BACKUP_DIR.glob("*.py"))
    if not backups:
        a2a_log("skillforge", "backup", "rollback_failed", "No hay backups disponibles.")
        return False

    latest = backups[-1]
    shutil.copy2(latest, DYNAMIC_TOOLS_FILE)
    a2a_log("skillforge", "backup", "rollback_ok", f"Restaurado desde {latest.name}")
    return True


def _try_reload_dynamic_tools() -> str | None:
    """
    Intenta recargar el módulo dynamic_tools para verificar que la nueva tool no rompe el grafo.
    Retorna None si OK, o el mensaje de error si falla.
    """
    try:
        import importlib
        import agents.dynamic_tools as dt
        importlib.reload(dt)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


@tool
def skillforge_save_tool(python_code: str) -> str:
    """
    Guarda el código Python proporcionado en el archivo dynamic_tools.py de forma permanente.
    El código debe contener una o más funciones decoradas con @tool de langchain_core.tools.

    Proceso de seguridad:
    1. Limpia bloques de markdown
    2. Crea backup automático de la versión actual
    3. Valida con ASTValidator (4 capas de seguridad)
    4. Escribe en dynamic_tools.py
    5. Verifica que el grafo puede recargar el módulo
    6. Si falla el reload → rollback automático al backup anterior
    """
    a2a_log("skillforge", "system", "save_tool", "Iniciando escritura de nueva herramienta...")

    # 1. Limpiar bloques de markdown si el LLM los incluyó
    code = python_code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()

    # 2. Verificar que contiene @tool
    if "@tool" not in code:
        return "❌ Error: El código no contiene el decorador @tool. Decora la función principal con @tool de langchain_core.tools."

    # 3. Backup automático ANTES de cualquier escritura
    backup_path = _backup_current_tools()
    if backup_path:
        a2a_log("skillforge", "backup", "pre_write", f"Backup creado: {backup_path.name}")

    # 4. Validar con ASTValidator (Sandbox Capa 1 + 2)
    validation = _validator.validate(code)
    if not validation.is_safe:
        violations_str = "\n  - ".join(validation.violations)
        a2a_log("skillforge", "ast_validator", "blocked", violations_str)
        return (
            f"❌ Código bloqueado por ASTValidator. Violaciones de seguridad:\n"
            f"  - {violations_str}\n\n"
            f"Por favor, reescribe la herramienta sin esas operaciones."
        )

    # 5. Escribir en dynamic_tools.py
    try:
        with open(DYNAMIC_TOOLS_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(code)
            f.write("\n")
    except Exception as e:
        return f"❌ Error al escribir en disco: {e}"

    # 6. Verificar que el módulo puede recargarse (que no rompió el grafo)
    reload_error = _try_reload_dynamic_tools()
    if reload_error:
        a2a_log("skillforge", "reload", "failed", reload_error)
        # Rollback automático
        if _rollback_to_last_backup():
            return (
                f"⚠️ La herramienta se escribió OK pero rompió el módulo al recargar.\n"
                f"Error: {reload_error}\n"
                f"✅ Rollback automático ejecutado. El sistema fue restaurado al estado anterior.\n"
                f"Por favor, corrige el código y vuelve a intentarlo."
            )
        else:
            return (
                f"🚨 Error crítico: La herramienta rompió el módulo y no hay backups para rollback.\n"
                f"Error: {reload_error}\n"
                f"Intervención manual requerida: restaurar agents/dynamic_tools.py manualmente."
            )

    a2a_log("skillforge", "system", "save_success", "Herramienta guardada y módulo recargado OK.")
    return (
        f"✅ ¡ÉXITO! La herramienta se guardó en dynamic_tools.py y está disponible ahora mismo.\n"
        f"Backup creado en: {backup_path.name if backup_path else 'N/A'}\n"
        f"El Orquestador puede usar la nueva herramienta sin necesidad de reiniciar."
    )


@tool
def skillforge_list_history() -> str:
    """Lista el historial de versiones de dynamic_tools.py con sus timestamps."""
    if not BACKUP_DIR.exists():
        return "No hay historial de backups todavía."

    backups = sorted(BACKUP_DIR.glob("*.py"), reverse=True)
    if not backups:
        return "El directorio de historial existe pero está vacío."

    lines = [f"📚 Historial de dynamic_tools.py ({len(backups)} versiones):"]
    for i, b in enumerate(backups[:10]):  # Mostrar las últimas 10
        size = b.stat().st_size
        lines.append(f"  {'→ Más reciente' if i == 0 else f'  [{i+1}]'}: {b.name} ({size} bytes)")

    return "\n".join(lines)


@tool
def skillforge_rollback(confirm: str = "no") -> str:
    """
    Revierte dynamic_tools.py al último backup guardado.
    Requiere confirm='SI' para ejecutar el rollback.
    """
    if confirm.upper() not in ("SI", "SÍ", "YES", "Y"):
        return "⚠️ Para ejecutar el rollback, confirma con confirm='SI'."

    _backup_current_tools()  # Backup del estado actual antes de rollback
    if _rollback_to_last_backup():
        reload_error = _try_reload_dynamic_tools()
        if reload_error:
            return f"⚠️ Rollback ejecutado pero el módulo sigue fallando: {reload_error}"
        return "✅ Rollback exitoso. dynamic_tools.py restaurado al último backup."
    return "❌ No hay backups disponibles para hacer rollback."


def get_skillforge_tools():
    return [skillforge_save_tool, skillforge_list_history, skillforge_rollback]
