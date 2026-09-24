"""
Tests unitarios para el ASTValidator del SandboxManager.
Ejecutar con: python -m pytest tests/test_sandbox.py -v
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.sandbox.ast_validator import ASTValidator


@pytest.fixture
def validator():
    return ASTValidator()


class TestSyntaxValidation:
    def test_valid_simple_code(self, validator):
        code = "x = 1 + 2\nprint(x)"
        result = validator.validate(code)
        assert result.is_safe, f"Código válido fue bloqueado: {result.violations}"

    def test_syntax_error_detected(self, validator):
        code = "def broken(:\n    pass"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("SyntaxError" in v for v in result.violations)


class TestBannedCalls:
    def test_os_system_blocked(self, validator):
        code = "import os\nos.system('ls')"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("os.system" in v for v in result.violations)

    def test_subprocess_run_blocked(self, validator):
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("subprocess.run" in v for v in result.violations)

    def test_os_remove_blocked(self, validator):
        code = "import os\nos.remove('/etc/passwd')"
        result = validator.validate(code)
        assert not result.is_safe

    def test_shutil_rmtree_blocked(self, validator):
        code = "import shutil\nshutil.rmtree('/tmp/data')"
        result = validator.validate(code)
        assert not result.is_safe

    def test_sys_exit_blocked(self, validator):
        code = "import sys\nsys.exit(0)"
        result = validator.validate(code)
        assert not result.is_safe

    def test_ctypes_blocked(self, validator):
        code = "import ctypes\nctypes.cdll.LoadLibrary('evil.so')"
        result = validator.validate(code)
        assert not result.is_safe


class TestBannedBuiltins:
    def test_eval_blocked(self, validator):
        code = "eval('__import__(\"os\").system(\"rm -rf /\")')"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("eval" in v for v in result.violations)

    def test_exec_blocked(self, validator):
        code = "exec('import os')"
        result = validator.validate(code)
        assert not result.is_safe

    def test_compile_blocked(self, validator):
        code = "c = compile('import os', '', 'exec')\nexec(c)"
        result = validator.validate(code)
        assert not result.is_safe


class TestBannedDunders:
    def test_subclasses_blocked(self, validator):
        code = "x = ().__class__.__bases__[0].__subclasses__()"
        result = validator.validate(code)
        assert not result.is_safe

    def test_globals_blocked(self, validator):
        code = "f = lambda: None\ng = f.__globals__"
        result = validator.validate(code)
        assert not result.is_safe


class TestImportAllowlist:
    def test_allowed_imports_pass(self, validator):
        code = "import json\nimport math\nfrom pathlib import Path\nprint(math.pi)"
        result = validator.validate(code)
        assert result.is_safe, f"Import permitido fue bloqueado: {result.violations}"

    def test_banned_import_subprocess(self, validator):
        code = "import subprocess"
        result = validator.validate(code)
        assert not result.is_safe
        assert any("subprocess" in v for v in result.violations)

    def test_banned_import_pickle(self, validator):
        code = "import pickle"
        result = validator.validate(code)
        assert not result.is_safe

    def test_banned_import_socket(self, validator):
        code = "import socket"
        result = validator.validate(code)
        assert not result.is_safe

    def test_allowed_third_party(self, validator):
        code = "import json\nimport numpy\nfrom pydantic import BaseModel"
        result = validator.validate(code)
        assert result.is_safe, f"Import de tercero permitido fue bloqueado: {result.violations}"


class TestSandboxManager:
    def test_execute_safe_code(self):
        from core.sandbox.sandbox_manager import SandboxManager
        sandbox = SandboxManager()
        result = sandbox.execute("x = 2 + 2\nprint(x)", requester_agent="test")
        assert not result["blocked"]
        assert result["success"]
        assert "4" in result["stdout"]

    def test_execute_blocked_code(self):
        from core.sandbox.sandbox_manager import SandboxManager
        sandbox = SandboxManager()
        result = sandbox.execute("import subprocess\nsubprocess.run(['ls'])", requester_agent="test")
        assert result["blocked"]
        assert not result["success"]
        assert len(result["violations"]) > 0

    def test_quick_validate(self):
        from core.sandbox.sandbox_manager import SandboxManager
        sandbox = SandboxManager()
        is_safe, violations = sandbox.quick_validate("print('hello')")
        assert is_safe
        assert len(violations) == 0

        is_safe, violations = sandbox.quick_validate("import socket")
        assert not is_safe
        assert len(violations) > 0


if __name__ == "__main__":
    # Ejecutar manualmente sin pytest
    v = ASTValidator()
    tests = [
        ("x = 1 + 2\nprint(x)", True),
        ("import os\nos.system('ls')", False),
        ("eval('__import__(\"os\")')", False),
        ("import json\nimport math", True),
        ("import subprocess", False),
        ("().__class__.__bases__[0].__subclasses__()", False),
    ]
    print("\n🧪 ASTValidator Tests:")
    for code, expected_safe in tests:
        result = v.validate(code)
        status = "✅" if result.is_safe == expected_safe else "❌"
        label = "seguro" if expected_safe else "peligroso"
        print(f"{status} [{label}] {code[:50]!r}")
        if not result.is_safe:
            for viol in result.violations:
                print(f"     Violación: {viol}")
