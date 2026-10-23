"""Runtime guard: code that passes the AST check still cannot touch files outside
the workspace, launch processes or reach the network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.sandbox.process_runner import ProcessRunner  # noqa: E402


@pytest.fixture
def setup(tmp_path):
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.env"
    secret.write_text("TOKEN=abc", encoding="utf-8")
    return ProcessRunner(workspace, timeout=30), workspace, outside, secret


def _blocked(result):
    return not result["success"] and "[sandbox] blocked" in result["stderr"]


def test_normal_code_still_runs(setup):
    runner, *_ = setup
    result = runner.run("import json, math\nprint(json.dumps({'r': math.sqrt(16)}))")
    assert result["success"], result["stderr"]
    assert '"r": 4.0' in result["stdout"]


def test_can_write_and_read_inside_workspace(setup):
    runner, workspace, *_ = setup
    result = runner.run("open('out.txt', 'w').write('ok')\nprint(open('out.txt').read())")
    assert result["success"], result["stderr"]
    assert (workspace / "out.txt").read_text() == "ok"


def test_cannot_read_secret_outside(setup):
    runner, _, _, secret = setup
    assert _blocked(runner.run(f"print(open({str(secret)!r}).read())"))


def test_cannot_read_via_relative_traversal(setup):
    runner, *_ = setup
    assert _blocked(runner.run("print(open('../outside/secret.env').read())"))


def test_cannot_write_outside(setup):
    runner, _, outside, _ = setup
    target = outside / "evil.txt"
    assert _blocked(runner.run(f"import pathlib\npathlib.Path({str(target)!r}).write_text('x')"))
    assert not target.exists()


def test_cannot_overwrite_outside_via_dynamic_path(setup):
    runner, _, _, secret = setup
    code = f"p = ''.join([{str(secret)!r}])\nopen(p, 'w').write('pwned')"
    assert _blocked(runner.run(code))
    assert secret.read_text() == "TOKEN=abc"


def test_cannot_rename_outside(setup):
    runner, _, outside, secret = setup
    code = f"import os\nos.rename({str(secret)!r}, {str(outside / 'moved')!r})"
    assert _blocked(runner.run(code))
    assert secret.exists()


def test_cannot_reach_network(setup):
    runner, *_ = setup
    code = "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3)"
    assert _blocked(runner.run(code))


def test_cannot_spawn_process(setup):
    runner, *_ = setup
    code = "import os\nos.system('echo hi')"
    assert _blocked(runner.run(code))


def test_scientific_libs_still_work(setup):
    pytest.importorskip("numpy")
    runner, *_ = setup
    result = runner.run("import numpy as np\nprint(int(np.arange(5).sum()))")
    assert result["success"], result["stderr"]
    assert result["stdout"] == "10"
