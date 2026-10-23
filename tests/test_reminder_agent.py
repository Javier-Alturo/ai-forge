"""Reminder agent: phone numbers are masked in logs and tasks load through TaskForge storage."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import reminder_agent  # noqa: E402
from agents import taskforge_store  # noqa: E402


def test_mask_number_keeps_last_four():
    assert reminder_agent.mask_number("570000001234") == "***1234"
    assert reminder_agent.mask_number("") == "***"


def test_send_without_number_does_nothing(monkeypatch):
    monkeypatch.setattr(reminder_agent, "WHATSAPP_NUMBER", "")
    assert reminder_agent._send_whatsapp("hola") is False


def test_tasks_loaded_with_taskforge_store():
    assert reminder_agent._load is taskforge_store._load
