"""Computer use is look-only by default; control tools need an explicit switch."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

cu = pytest.importorskip("agents.computer_use_tools")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AIFORGE_ALLOW_COMPUTER_USE", raising=False)
    monkeypatch.delenv("AIFORGE_ALLOWED_APPS", raising=False)


def _names(tools):
    return {t.name for t in tools}


def test_read_only_by_default():
    assert _names(cu.get_computer_use_tools()) == {"computer_screenshot", "computer_find_element"}


def test_control_tools_with_explicit_switch(monkeypatch):
    monkeypatch.setenv("AIFORGE_ALLOW_COMPUTER_USE", "1")
    assert {"computer_click", "computer_type_text", "computer_open_app"} <= _names(cu.get_computer_use_tools())


@pytest.mark.parametrize("app", [
    "cmd", "powershell", "C:/Windows/System32/cmd.exe", "notepad & del /q *", "calc; rm -rf ~", "../notepad",
])
def test_open_app_refuses_unlisted_or_commands(monkeypatch, app):
    launched = []
    monkeypatch.setattr(cu.os, "startfile", lambda *a: launched.append(a), raising=False)
    monkeypatch.setattr(cu.subprocess, "Popen", lambda *a, **k: launched.append(a))
    assert cu.computer_open_app.invoke({"app_name": app}).startswith("⛔")
    assert launched == []


def test_open_app_allows_listed(monkeypatch):
    launched = []
    monkeypatch.setattr(cu.os, "startfile", lambda *a: launched.append(a), raising=False)
    monkeypatch.setattr(cu.subprocess, "Popen", lambda *a, **k: launched.append(a))
    assert cu.computer_open_app.invoke({"app_name": "Notepad"}).startswith("Lanzado")
    assert len(launched) == 1
