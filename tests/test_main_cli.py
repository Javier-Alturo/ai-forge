"""CLI line handler: commands are handled without calling the orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def test_help_prints_examples(capsys):
    main.handle_line("ayuda", "s1")
    assert "Ejemplos" in capsys.readouterr().out


def test_blank_line_is_ignored(capsys):
    main.handle_line("   ", "s1")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("cmd", ["salir", "EXIT", "quit"])
def test_exit_commands(cmd):
    with pytest.raises(KeyboardInterrupt):
        main.handle_line(cmd, "s1")
