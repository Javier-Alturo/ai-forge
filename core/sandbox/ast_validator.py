"""
CAPA 1: AST Validator — Análisis estático del código generado por LLM.
Detecta patrones peligrosos ANTES de ejecutar cualquier instrucción.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_safe: bool
    violations: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.is_safe:
            return "✅ Código validado: seguro."
        return f"❌ Código bloqueado. Violaciones:\n" + "\n".join(f"  - {v}" for v in self.violations)


class ASTValidator:
    """
    Análisis estático del código generado por LLM.
    Detecta patrones peligrosos ANTES de ejecutar.

    USO:
        validator = ASTValidator()
        result = validator.validate(code_string)
        if not result.is_safe:
            raise SecurityError(str(result))
    """

    # Pares (modulo, funcion) explícitamente prohibidos
    BANNED_CALLS: set[tuple[str, str]] = {
        # Sistema de archivos — operaciones destructivas
        ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execvp"),
        ("os", "execve"), ("os", "fork"), ("os", "kill"), ("os", "killpg"),
        ("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("os", "makedirs"),
        ("shutil", "rmtree"), ("shutil", "move"), ("shutil", "copy"), ("shutil", "copy2"),
        # Subprocesos
        ("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call"),
        ("subprocess", "check_output"), ("subprocess", "check_call"),
        # Salida del proceso
        ("sys", "exit"), ("os", "_exit"),
        # Acceso nativo bajo nivel
        ("ctypes", "cdll"), ("ctypes", "windll"), ("ctypes", "CDLL"),
        ("pty", "spawn"), ("pty", "openpty"),
        # Networking raw
        ("socket", "socket"), ("socket", "create_connection"),
    }

    # Funciones built-in prohibidas directamente
    BANNED_BUILTINS: set[str] = {
        "eval", "exec", "compile", "__import__", "breakpoint",
    }

    # Atributos dunder que no deben ser accedidos
    BANNED_DUNDER_ATTRS: set[str] = {
        "__import__", "__builtins__", "__class__", "__bases__",
        "__subclasses__", "__globals__", "__code__", "__closure__",
        "__reduce__", "__reduce_ex__",
    }

    def validate(self, source_code: str) -> ValidationResult:
        """
        Valida el código fuente con análisis AST completo.
        Retorna ValidationResult con is_safe=True si no hay violaciones.
        """
        violations: list[str] = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return ValidationResult(is_safe=False, violations=[f"SyntaxError: {e}"])

        for node in ast.walk(tree):
            violations.extend(self._check_node(node))

        return ValidationResult(is_safe=len(violations) == 0, violations=violations)

    def _check_node(self, node: ast.AST) -> list[str]:
        violations: list[str] = []

        # 1. Detectar llamadas a funciones prohibidas (modulo.funcion)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    pair = (node.func.value.id, node.func.attr)
                    if pair in self.BANNED_CALLS:
                        violations.append(f"Llamada prohibida: {pair[0]}.{pair[1]}()")

        # 2. Detectar funciones built-in prohibidas directas: eval(), exec(), etc.
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in self.BANNED_BUILTINS:
                    violations.append(f"Función prohibida: {node.func.id}()")

        # 3. Detectar acceso a atributos dunder peligrosos
        if isinstance(node, ast.Attribute):
            if node.attr in self.BANNED_DUNDER_ATTRS:
                violations.append(f"Acceso a atributo prohibido: .{node.attr}")

        # 4. Detectar imports no permitidos
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(self._check_imports(node))

        return violations

    def _check_imports(self, node: ast.Import | ast.ImportFrom) -> list[str]:
        from core.sandbox.import_allowlist import ALLOWED_IMPORTS, EXPLICITLY_BANNED
        violations: list[str] = []

        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in EXPLICITLY_BANNED:
                    violations.append(f"Import explícitamente prohibido: {alias.name}")
                elif root not in ALLOWED_IMPORTS:
                    violations.append(f"Import no en allowlist: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in EXPLICITLY_BANNED:
                    violations.append(f"Import explícitamente prohibido: from {node.module}")
                elif root not in ALLOWED_IMPORTS:
                    violations.append(f"Import no en allowlist: from {node.module}")

        return violations
