"""OAuth2 Google (Gmail + Calendar): credentials.json + token.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from agents.a2a_log import a2a_log

_ROOT = Path(__file__).resolve().parent.parent

# Scopes para Gmail y Calendar (un solo token).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def _paths() -> tuple[Path, Path]:
    cred = Path(os.environ.get("GOOGLE_OAUTH_CREDENTIALS", _ROOT / "credentials.json"))
    tok = Path(os.environ.get("GOOGLE_OAUTH_TOKEN", _ROOT / "token.json"))
    return cred, tok


def get_google_credentials() -> Credentials | None:
    """
    Carga o refresca credenciales. Si no hay token válido, lanza flujo local (navegador).
    Devuelve None si falta credentials.json.
    """
    cred_path, token_path = _paths()
    if not cred_path.is_file():
        a2a_log("google_auth", "config", "missing_credentials", str(cred_path))
        return None

    creds: Credentials | None = None
    if token_path.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            a2a_log("google_auth", "token", "invalid_token_file", str(exc))
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as exc:  # noqa: BLE001
            a2a_log("google_auth", "token", "refresh_failed", str(exc))

    a2a_log("google_auth", "oauth", "browser_flow", "InstalledAppFlow")
    flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
