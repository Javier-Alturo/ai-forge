"""
SandboxManager — Punto de entrada único para ejecutar código generado por LLM.

NINGÚN agente debe invocar código directamente.
TODO el código pasa por aquí. Sin excepción.

Flujo:
    código_raw → ASTValidator → aprobado? → ProcessRunner → resultado
                              → rechazado? → retorna error con violaciones
"""

from __future__ import annotations

from pathlib import Path

from core.sandbox.ast_validator import ASTValidator
from core.sandbox.process_runner import ProcessRunner
from core.sandbox.resource_governor import ResourceGovernor, ResourceLimits

# Workspace aislado donde se ejecutan los scripts temporales
_DEFAULT_WORKSPACE = Path(__file__).parent.parent.parent / "data" / "sandbox_workspace"


class SandboxManager:
    """
    ESTE es el único punto de entrada para ejecutar código LLM.

    Ejemplo de uso:
        sandbox = SandboxManager()
        result = sandbox.execute(code_str, requester_agent="code_agent")
        if result["blocked"]:
            print("Bloqueado:", result["violations"])
        elif result["success"]:
            print("Output:", result["stdout"])
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        workspace = Path(cfg.get("sandbox_workspace", str(_DEFAULT_WORKSPACE)))

        self.validator = ASTValidator()
        self.runner = ProcessRunner(
            workspace_dir=workspace,
            timeout=cfg.get("execution_timeout", 30),
        )
        limits = ResourceLimits(
            max_cpu_seconds=cfg.get("max_cpu_seconds", 30),
            max_memory_mb=cfg.get("max_memory_mb", 512),
            max_file_size_mb=cfg.get("max_file_size_mb", 50),
        )
        self.governor = ResourceGovernor(limits)

    def execute(self, code: str, requester_agent: str = "unknown") -> dict:
        """
        Ejecuta código a través del pipeline de seguridad completo.

        Returns:
            dict con keys:
                - success (bool)
                - blocked (bool) — True si ASTValidator lo bloqueó
                - violations (list[str]) — solo si bloqueado
                - stdout (str)
                - stderr (str)
                - returncode (int)
                - requester (str)
                - message (str) — resumen legible del resultado
        """
        # PASO 1: Validación estática (AST)
        validation = self.validator.validate(code)
        if not validation.is_safe:
            return {
                "success": False,
                "blocked": True,
                "violations": validation.violations,
                "stdout": "",
                "stderr": "",
                "returncode": -99,
                "requester": requester_agent,
                "message": (
                    f"🚫 Código bloqueado por SandboxManager. "
                    f"Agente: {requester_agent}. "
                    f"Violaciones: {'; '.join(validation.violations)}"
                ),
            }

        # PASO 2: Ejecución en proceso aislado
        result = self.runner.run(code)
        result["blocked"] = False
        result["requester"] = requester_agent

        if result["success"]:
            result["message"] = f"✅ Código ejecutado correctamente por {requester_agent}."
        else:
            result["message"] = (
                f"⚠️ Código ejecutado pero terminó con error. "
                f"exit_code={result['returncode']}. stderr: {result.get('stderr', '')[:200]}"
            )

        return result

    def quick_validate(self, code: str) -> tuple[bool, list[str]]:
        """
        Solo validación estática sin ejecutar. Útil para SkillForge.
        Returns: (is_safe, violations)
        """
        result = self.validator.validate(code)
        return result.is_safe, result.violations
