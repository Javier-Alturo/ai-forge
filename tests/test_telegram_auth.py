"""Only allow-listed Telegram chats may reach the bot (fail-closed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.telegram_auth import allowed_chat_ids, is_authorized  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)


def _msg(chat_id):
    return {"chat": {"id": chat_id}, "text": "hola"}


def test_nobody_allowed_when_unconfigured():
    assert allowed_chat_ids() == set()
    assert not is_authorized(_msg(111))


def test_owner_chat_allowed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    assert is_authorized(_msg(111))
    assert is_authorized(_msg("111"))


def test_stranger_rejected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    assert not is_authorized(_msg(222))


def test_extra_allowed_ids(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", " 333, ,444 ")
    assert is_authorized(_msg(333)) and is_authorized(_msg(444))


@pytest.mark.parametrize("message", [None, {}, {"chat": {}}, {"text": "x"}])
def test_malformed_messages_rejected(monkeypatch, message):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    assert not is_authorized(message)
