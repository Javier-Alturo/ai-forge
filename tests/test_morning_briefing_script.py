"""Morning briefing script: degraded mode survives tool failures; Telegram errors never print the token."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

mb = pytest.importorskip("scripts.morning_briefing")
mbt = pytest.importorskip("agents.morning_briefing_tools")


class _Boom:
    def invoke(self, _):
        raise RuntimeError("fuente caída")


class _Ok:
    def __init__(self, text):
        self.text = text

    def invoke(self, _):
        return self.text


def test_degraded_briefing_survives_failing_tools(monkeypatch):
    for name in ("briefing_get_daily_note_tasks", "briefing_get_past_pending_tasks", "briefing_get_calendar_events",
                 "briefing_get_critical_emails", "briefing_get_rss_news", "briefing_health_check"):
        monkeypatch.setattr(mbt, name, _Ok(f"ok:{name}"))
    monkeypatch.setattr(mbt, "briefing_get_weather_briefing", _Boom())
    out = mb.generate_degraded_briefing()
    assert "Modo Degradado" in out and "No se pudo obtener clima" in out and "ok:briefing_get_rss_news" in out


def test_telegram_error_does_not_print_token(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:TOPSECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")

    def boom(req, timeout=None):
        raise urllib.error.URLError(f"failed {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    mb.send_telegram_briefing("## 🎯 Foco del Día\nEstudiar")
    assert "TOPSECRET" not in capsys.readouterr().out
