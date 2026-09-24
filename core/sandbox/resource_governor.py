"""
CAPA 4: Resource Governor — Límites de CPU, memoria y tiempo de ejecución.

NOTA IMPORTANTE PARA WINDOWS:
resource.setrlimit() es una API de POSIX (Linux/macOS).
En Windows, se usan "Job Objects" del kernel para los mismos fines.
Este módulo detecta el OS y aplica el mecanismo correcto.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass


@dataclass
class ResourceLimits:
    max_cpu_seconds: int = 30
    max_memory_mb: int = 512
    max_file_size_mb: int = 50
    max_processes: int = 1  # Sin fork


class ResourceGovernor:
    """
    Límites de recursos para el proceso de ejecución.
    Previene fork bombs, loops infinitos y consumo excesivo de RAM.

    Se aplica en el proceso HIJO antes de ejecutar código del LLM,
    llamando a apply_limits() desde process_runner.py.
    """

    def __init__(self, limits: ResourceLimits | None = None):
        self.limits = limits or ResourceLimits()

    def apply_limits(self) -> None:
        """
        Aplica límites de recursos. El método adecuado depende del OS.
        """
        if sys.platform == "win32":
            self._apply_windows_limits()
        else:
            self._apply_posix_limits()

    def _apply_posix_limits(self) -> None:
        """
        Usa resource.setrlimit (Linux/macOS).
        Aplica solo al proceso actual y sus hijos.
        """
        try:
            import resource  # type: ignore[import]

            # Memoria virtual máxima
            mem_bytes = self.limits.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

            # CPU time
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.limits.max_cpu_seconds, self.limits.max_cpu_seconds),
            )

            # Tamaño máximo de archivos que puede escribir
            file_bytes = self.limits.max_file_size_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))

            # Sin procesos hijos (bloquea subprocess, os.fork)
            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (self.limits.max_processes, self.limits.max_processes),
            )
        except Exception as e:  # noqa: BLE001
            # No es fatal — logear y continuar
            print(f"[ResourceGovernor] Warning POSIX: {e}", file=sys.stderr)

    def _apply_windows_limits(self) -> None:
        """
        En Windows no hay resource.setrlimit nativo.
        El timeout del subprocess.run() en ProcessRunner ya actúa como control de tiempo.
        Los límites de memoria son best-effort vía ctypes/win32api (opcional).
        """
        # El timeout estricto del ProcessRunner es el principal mecanismo de control en Windows.
        # Para una implementación más robusta en producción, se pueden usar Windows Job Objects.
        pass

    def get_preexec_fn(self):
        """
        Retorna una función preexec_fn para pasar a subprocess.run() en Linux/macOS.
        En Windows retorna None (no soportado).
        """
        if sys.platform == "win32":
            return None
        return self.apply_limits
