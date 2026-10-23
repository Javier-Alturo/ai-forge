"""Telegram listener: routing, allowlist, no token in logs, briefing uses this interpreter."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

httpx = pytest.importorskip("httpx")


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    mod = importlib.reload(importlib.import_module("telegram_bot_listener"))
    sent = []
    monkeypatch.setattr(mod, "send_message", lambda chat_id, text: sent.append((chat_id, text)))
    mod._sent = sent
    return mod


def _update(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def test_stranger_is_ignored(bot, monkeypatch):
    called = []
    monkeypatch.setattr(bot, "handle_chat", lambda *a: called.append(a))
    bot.handle_update(_update(999, "hola"))
    assert called == [] and bot._sent == []


def test_briefing_uses_current_interpreter(bot, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args))
    bot.handle_update(_update(111, "/briefing"))
    assert calls and calls[0][0] == sys.executable


def test_free_text_goes_to_orchestrator(bot, monkeypatch):
    fake = SimpleNamespace(run_turn=lambda text, thread_id: SimpleNamespace(content=f"eco <{text}>"))
    monkeypatch.setitem(sys.modules, "agents.orchestrator", fake)
    bot.handle_update(_update(111, "hola"))
    assert bot._sent[-1] == (111, "eco &lt;hola&gt;")


def test_http_errors_do_not_print_token(bot, monkeypatch, capsys):
    def boom(url, **_):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(bot._HTTP, "get", boom)
    assert bot.get_updates() == []
    assert "SECRET" not in capsys.readouterr().out
