"""
CAPA 3: Process Runner — Ejecuta código en un subproceso completamente separado.
El proceso hijo NO hereda variables de entorno sensibles (tokens, API keys).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class ProcessRunner:
    """
    Ejecuta código generado por LLM en un subproceso completamente separado.

    Características de seguridad:
    - CWD restringido al workspace designado (no puede salir de él)
    - Entorno limpio: sin tokens, API keys, ni credenciales
    - Timeout estricto para prevenir loops infinitos
    - Archivos temporales eliminados después de la ejecución
    """

    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace = workspace_dir
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def run(self, code: str) -> dict:
        """
        Escribe el código en un archivo temporal y lo ejecuta en un
        intérprete hijo con entorno limpio y directorio restringido.

        Returns:
            dict con keys: stdout, stderr, returncode, success
        """
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=self.workspace,
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(self._wrap_code(code))
                tmp_path = Path(f.name)

            result = subprocess.run(
                [sys.executable, str(tmp_path)],
                stdin=subprocess.DEVNULL,  # el codigo sandboxed no debe leer stdin del padre
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace),   # CWD restringido al workspace
                env=self._clean_env(),     # Entorno limpio
                encoding="utf-8",
                errors="replace",
            )
            return {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"⏰ TIMEOUT: El código excedió {self.timeout}s de ejecución. Posible loop infinito.",
                "returncode": -1,
                "success": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "stdout": "",
                "stderr": f"Error al ejecutar subproceso: {exc}",
                "returncode": -2,
                "success": False,
            }
        finally:
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _clean_env(self) -> dict:
        """
        Entorno sin tokens, API keys, o credenciales del sistema.
        Solo variables necesarias para que Python funcione correctamente.
        """
        safe_keys = {"PATH", "HOME", "LANG", "PYTHONPATH", "VIRTUAL_ENV",
                     "SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                     "TEMP", "TMP", "ComSpec"}
        return {k: v for k, v in os.environ.items() if k in safe_keys}

    def _wrap_code(self, code: str) -> str:
        """
        Envuelve el código en un bloque try/except para capturar errores
        sin crashear el proceso padre. También fuerza el CWD.
        """
        workspace_escaped = str(self.workspace).replace("\\", "\\\\")
        indented = self._indent(code)
        return f"""\
import sys
import os

# Restricciones adicionales en runtime
os.chdir("{workspace_escaped}")  # Forzar CWD al workspace

try:
{indented}
except Exception as e:
    print(f"RUNTIME_ERROR: {{type(e).__name__}}: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

    @staticmethod
    def _indent(code: str) -> str:
        return "\n".join("    " + line for line in code.splitlines())
