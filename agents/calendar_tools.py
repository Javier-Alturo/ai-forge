"""Tools del agente de calendario (Google Calendar API + OAuth2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.google_auth import get_google_credentials


def _calendar_service():
    creds = get_google_credentials()
    if creds is None:
        return None, "Falta credentials.json. Misma configuración OAuth que Gmail."
    return build("calendar", "v3", credentials=creds), None


@tool
def calendar_list_upcoming(max_results: int = 10, calendar_id: str = "primary") -> str:
    """Lista eventos próximos (desde ahora, ventana 14 días). calendar_id suele ser 'primary'."""
    a2a_log("calendar", "google_calendar", "list_upcoming", calendar_id)
    svc, err = _calendar_service()
    if err:
        return err
    assert svc is not None
    now = datetime.now(timezone.utc).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    events_result = (
        svc.events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            timeMax=end,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = events_result.get("items", [])
    if not items:
        return "No hay eventos en el rango."
    lines: list[str] = []
    for ev in items:
        start = ev["start"].get("dateTime", ev["start"].get("date"))
        lines.append(f"id={ev['id']}\n  {start} | {ev.get('summary', '(sin título)')}\n")
    return "\n".join(lines)


@tool
def calendar_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    """
    Crea un evento. start_iso / end_iso en ISO8601 con zona, p.ej. 2026-04-22T15:00:00+02:00
    """
    a2a_log("calendar", "google_calendar", "create", summary[:80])
    svc, err = _calendar_service()
    if err:
        return err
    assert svc is not None
    # RFC3339 con offset o Z; Calendar acepta dateTime sin timeZone duplicado.
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    created = svc.events().insert(calendarId=calendar_id, body=body).execute()
    return f"Creado id={created.get('id')} link={created.get('htmlLink', '')}"


@tool
def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> str:
    """Elimina un evento por su id (el que devuelven list/search)."""
    a2a_log("calendar", "google_calendar", "delete", event_id)
    svc, err = _calendar_service()
    if err:
        return err
    assert svc is not None
    svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return f"Evento eliminado: {event_id}"


@tool
def calendar_search_events(search_text: str, max_results: int = 10, calendar_id: str = "primary") -> str:
    """Busca eventos por texto libre en título/descripción (búsqueda simple en ventana 90 días)."""
    a2a_log("calendar", "google_calendar", "search", search_text[:120])
    svc, err = _calendar_service()
    if err:
        return err
    assert svc is not None
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=7)).isoformat()
    time_max = (now + timedelta(days=90)).isoformat()
    events_result = (
        svc.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
            q=search_text,
        )
        .execute()
    )
    items = events_result.get("items", [])[:max_results]
    if not items:
        return "Sin coincidencias."
    lines = [f"id={ev['id']} | {ev.get('summary', '')}" for ev in items]
    return "\n".join(lines)


def get_calendar_tools():
    return [
        calendar_list_upcoming,
        calendar_create_event,
        calendar_delete_event,
        calendar_search_events,
    ]
