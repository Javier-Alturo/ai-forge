"""Tools del agente de correo (Gmail API + OAuth2)."""

from __future__ import annotations

import base64
from email.message import EmailMessage

from googleapiclient.discovery import build
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.google_auth import get_google_credentials


def _gmail_service():
    creds = get_google_credentials()
    if creds is None:
        return None, "Falta credentials.json. Configura GOOGLE_OAUTH_CREDENTIALS o coloca credentials.json en la raíz del proyecto."
    return build("gmail", "v1", credentials=creds), None


@tool
def email_list_recent(max_results: int = 10) -> str:
    """Lista los correos más recientes de la bandeja de entrada (snippet + id)."""
    a2a_log("email", "gmail", "list_recent", str(max_results))
    svc, err = _gmail_service()
    if err:
        return err
    assert svc is not None
    res = (
        svc.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
        .execute()
    )
    msgs = res.get("messages", [])
    if not msgs:
        return "No hay mensajes recientes."
    lines: list[str] = []
    for m in msgs:
        mid = m["id"]
        meta = svc.users().messages().get(userId="me", id=mid, format="metadata").execute()
        headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        subj = headers.get("subject", "(sin asunto)")
        sender = headers.get("from", "?")
        snippet = meta.get("snippet", "")
        lines.append(f"id={mid}\n  De: {sender}\n  Asunto: {subj}\n  {snippet}\n")
    return "\n".join(lines)


@tool
def email_send(to_address: str, subject: str, body: str, body_type: str = "plain") -> str:
    """Envía un email. to_address: destinatario. body_type: 'plain' o 'html'."""
    a2a_log("email", "gmail", "send", to_address[:120])
    svc, err = _gmail_service()
    if err:
        return err
    assert svc is not None
    msg = EmailMessage()
    msg["To"] = to_address
    msg["Subject"] = subject
    if body_type.lower() == "html":
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Enviado. id={sent.get('id')}"


@tool
def email_search(gmail_query: str, max_results: int = 15) -> str:
    """
    Busca emails con sintaxis Gmail (p.ej. from:foo subject:bar is:unread).
    gmail_query: cadena de búsqueda de Gmail.
    """
    a2a_log("email", "gmail", "search", gmail_query[:200])
    svc, err = _gmail_service()
    if err:
        return err
    assert svc is not None
    res = svc.users().messages().list(userId="me", q=gmail_query, maxResults=max_results).execute()
    msgs = res.get("messages", [])
    if not msgs:
        return "Sin resultados."
    lines: list[str] = []
    for m in msgs:
        mid = m["id"]
        meta = svc.users().messages().get(userId="me", id=mid, format="metadata").execute()
        headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        lines.append(
            f"id={mid} | {headers.get('from', '?')} | {headers.get('subject', '(sin asunto)')}"
        )
    return "\n".join(lines)


def get_email_tools():
    return [email_list_recent, email_send, email_search]
