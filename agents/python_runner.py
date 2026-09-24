"""Ejecución aislada de fragmentos Python via SandboxManager (4 capas de seguridad)."""

from __future__ import annotations

from core.sandbox.sandbox_manager import SandboxManager

# Singleton del sandbox — se reutiliza en toda la sesión
_sandbox = SandboxManager()


def run_python_code(code: str, timeout_sec: int = 30) -> str:
    """
    Punto de entrada principal para ejecutar código generado por el LLM.
    Pasa por las 4 capas de seguridad del SandboxManager:
      1. AST Validator (sintaxis + llamadas prohibidas)
      2. Import Allowlist
      3. Process Runner (subproceso aislado, entorno limpio)
      4. Resource Governor (timeout + límites de memoria en Linux/macOS)

    Returns:
        String con el resultado legible (stdout, stderr, estado).
    """
    code = (code or "").strip()
    if not code:
        return "No se proporcionó código."

    # Actualizar timeout si se especificó uno diferente al default
    _sandbox.runner.timeout = timeout_sec

    result = _sandbox.execute(code, requester_agent="code_agent")

    if result["blocked"]:
        violations = "\n  - ".join(result["violations"])
        return (
            f"[SEGURIDAD] Código bloqueado por SandboxManager.\n"
            f"Violaciones detectadas:\n  - {violations}"
        )

    parts = [f"exit_code={result['returncode']}"]
    if result.get("stdout"):
        parts.append("stdout:\n" + result["stdout"])
    if result.get("stderr"):
        parts.append("stderr:\n" + result["stderr"])

    return "\n\n".join(parts)

