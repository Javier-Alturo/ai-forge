"""Gmail access is read-only: no send/modify scopes and no send tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("google_auth_oauthlib")

from agents import google_auth  # noqa: E402


def test_scopes_are_read_only_for_gmail():
    assert not set(google_auth.SCOPES) & google_auth.FORBIDDEN_SCOPES
    assert "https://www.googleapis.com/auth/gmail.readonly" in google_auth.SCOPES


@pytest.mark.parametrize("scopes", [
    ["https://www.googleapis.com/auth/gmail.send"],
    ["https://www.googleapis.com/auth/gmail.modify"],
    "https://www.googleapis.com/auth/gmail.readonly https://mail.google.com/",
])
def test_old_token_with_send_power_is_detected(tmp_path, scopes):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"scopes": scopes}), encoding="utf-8")
    assert google_auth.token_has_forbidden_scopes(token)


def test_read_only_token_is_accepted(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"scopes": google_auth.SCOPES}), encoding="utf-8")
    assert not google_auth.token_has_forbidden_scopes(token)


def test_old_token_triggers_reauth(tmp_path, monkeypatch):
    cred = tmp_path / "credentials.json"
    cred.write_text("{}", encoding="utf-8")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.send"]}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(cred))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", str(token))
    loaded = []
    monkeypatch.setattr(google_auth.Credentials, "from_authorized_user_file", lambda *a, **k: loaded.append(a))

    class _Flow:
        def run_local_server(self, **_):
            raise RuntimeError("browser flow")

    monkeypatch.setattr(google_auth.InstalledAppFlow, "from_client_secrets_file", lambda *a, **k: _Flow())
    with pytest.raises(RuntimeError, match="browser flow"):
        google_auth.get_google_credentials()
    assert loaded == []  # the old token was never used


def test_no_send_tool_exposed():
    pytest.importorskip("googleapiclient")
    from agents.email_tools import get_email_tools

    names = {t.name for t in get_email_tools()}
    assert "email_send" not in names
    assert names == {"email_list_recent", "email_search"}
