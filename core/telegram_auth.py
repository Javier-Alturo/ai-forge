"""
Telegram allowlist — only the owner's chat may talk to the bot.

A Telegram bot is public: anyone who finds its username can message it. The
listener forwards free text to the orchestrator (Gmail, Calendar, files, git),
so every incoming update must come from an allowed chat id.

Allowed ids: TELEGRAM_CHAT_ID plus optional comma-separated TELEGRAM_ALLOWED_CHAT_IDS.
Fail-closed: if none are configured, nobody is allowed.
"""

from __future__ import annotations

import os


def allowed_chat_ids() -> set[str]:
    raw = [os.environ.get("TELEGRAM_CHAT_ID", "")]
    raw += os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
    return {x.strip() for x in raw if x.strip()}


def is_authorized(message: dict) -> bool:
    """True only if the message's chat id is explicitly allowed."""
    chat_id = (message or {}).get("chat", {}).get("id")
    if chat_id is None:
        return False
    return str(chat_id) in allowed_chat_ids()
