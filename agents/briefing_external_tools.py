"""Morning Briefing tools that call external services: Google Calendar, Gmail, weather and RSS.

Split from morning_briefing_tools.py (local tools: Obsidian, RAG, health check).
Weather and RSS share one HTTP client instead of opening a connection per call.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import httpx
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.google_auth import get_google_credentials
from agents.logger import get_logger

log = get_logger("morning_briefing")

_HTTP = httpx.Client(timeout=6.0, follow_redirects=True)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
RSS_FEEDS = {
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "Papers with Code": "https://paperswithcode.com/media/rss/latest/",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}
_AUTOMATED_EMAIL_KEYWORDS = (
    "newsletter", "boletin", "promo", "noreply", "no-reply", "digest", "notificacion",
    "notification", "oferta", "descuento", "update", "github", "linkedin", "security alert",
)
_WEATHER_FALLBACK = """☁️ Clima en Bogotá (Simulado - Sin API Key):
  - Temperatura actual: 14°C
  - Condición: Nublado con probabilidad de lluvias por la tarde (55%).
  - Humedad: 82% | Viento: 10 km/h
  - Recomendación: El clima en Bogotá suele ser frío y cambiante hoy. Lleva paraguas y una chaqueta impermeable si vas a salir, ya que se prevén lluvias ligeras después del mediodía."""


# ── Google Calendar ───────────────────────────────────────────────────────────

def _format_event(ev: dict) -> str:
    start = ev["start"].get("dateTime", ev["start"].get("date"))
    start_str = datetime.fromisoformat(start).strftime("%H:%M") if "T" in start else "Todo el día"
    return f"⏰ {start_str} - {ev.get('summary', '(Sin título)')}"


@tool
def briefing_get_calendar_events() -> str:
    """Conecta a Google Calendar API y lista los eventos agendados para el día de hoy."""
    a2a_log("morning_briefing", "google_calendar", "get_calendar_events", "Fetching today's events")
    creds = get_google_credentials()
    if creds is None:
        return "⚠️ Google Calendar: No disponible (Falta credentials.json o token de OAuth)."
    try:
        from googleapiclient.discovery import build

        svc = build("calendar", "v3", credentials=creds)
        now_local = datetime.now()
        start_of_day = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0)
        end_of_day = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59)
        events_result = svc.events().list(
            calendarId="primary",
            timeMin=start_of_day.astimezone().isoformat(),  # RFC3339
            timeMax=end_of_day.astimezone().isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception as e:
        log.exception("Google Calendar query failed")
        return f"⚠️ Error consultando Google Calendar: {type(e).__name__}"
    items = events_result.get("items", [])
    if not items:
        return "No tienes eventos programados para hoy."
    return "Eventos de hoy en Google Calendar:\n" + "\n".join(_format_event(ev) for ev in items)


# ── Gmail ─────────────────────────────────────────────────────────────────────

def _is_automated(subject: str, sender: str, snippet: str) -> bool:
    text = f"{subject} {sender} {snippet}".lower()
    return any(kw in text for kw in _AUTOMATED_EMAIL_KEYWORDS)


def _recent_message_ids(svc) -> list[dict]:
    today_str = date.today().strftime("%Y/%m/%d")
    res = svc.users().messages().list(userId="me", q=f"after:{today_str} is:unread", maxResults=15).execute()
    msgs = res.get("messages", [])
    if not msgs:  # ampliar a las últimas 24h aunque estén leídos
        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y/%m/%d")
        res = svc.users().messages().list(userId="me", q=f"after:{yesterday_str}", maxResults=15).execute()
        msgs = res.get("messages", [])
    return msgs


@tool
def briefing_get_critical_emails() -> str:
    """Conecta a Gmail API y busca correos críticos recibidos hoy, ignorando alertas y boletines automáticos."""
    a2a_log("morning_briefing", "gmail", "get_critical_emails", "Fetching emails...")
    creds = get_google_credentials()
    if creds is None:
        return "⚠️ Gmail: No disponible (Falta credentials.json o token de OAuth)."
    try:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=creds)
        lines = []
        for m in _recent_message_ids(svc):
            meta = svc.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
            headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
            subj = headers.get("subject", "(Sin asunto)")
            sender = headers.get("from", "Desconocido")
            snippet = meta.get("snippet", "")
            if not _is_automated(subj, sender, snippet):
                lines.append(f"📧 De: {sender}\n   Asunto: {subj}\n   Extracto: {snippet[:150]}...\n")
    except Exception as e:
        log.exception("Gmail query failed")
        return f"⚠️ Error consultando Gmail: {type(e).__name__}"
    if not lines:
        return "No se detectaron correos críticos personales o de trabajo hoy."
    return "Correos críticos que requieren atención hoy:\n\n" + "\n".join(lines[:5])


# ── Weather ───────────────────────────────────────────────────────────────────

def _weather_recommendation(desc: str, temp: float) -> str:
    if "lluvia" in desc.lower() or "llovizna" in desc.lower():
        return "⚠️ Está lloviendo o se esperan lluvias. Paraguas e impermeable indispensables."
    if temp < 12:
        return "🧥 Hace bastante frío. Abrígate bien con doble capa."
    if temp > 18:
        return "☀️ Día inusualmente cálido. Ropa cómoda y bloqueador solar."
    return "Lleva chaqueta cómoda. Clima típico bogotano."


@tool
def briefing_get_weather_briefing() -> str:
    """Consulta el clima actual y pronóstico para Bogotá, Colombia y provee recomendaciones prácticas."""
    a2a_log("morning_briefing", "weather", "get_weather_briefing", "Fetching weather for Bogota...")
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        a2a_log("morning_briefing", "weather", "fallback_mock", "No API key found in .env")
        return _WEATHER_FALLBACK
    params = {"q": "Bogota,CO", "appid": api_key, "units": "metric", "lang": "es"}
    try:
        r = _HTTP.get("https://api.openweathermap.org/data/2.5/weather", params=params, timeout=5.0)
        r.raise_for_status()
        data = r.json()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        desc = data["weather"][0]["description"].capitalize()
        humidity = data["main"]["humidity"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
        # Sin str(e): la URL de la petición incluye la API key.
        a2a_log("morning_briefing", "weather", "fetch_failed", type(e).__name__)
        return f"⚠️ Error al consultar el clima ({type(e).__name__}). Fallback: clima templado/lluvioso, lleva paraguas."
    return f"""🌤️ Clima en Bogotá (Real):
  - Temperatura: {temp:.1f}°C (Sensación: {feels_like:.1f}°C)
  - Condición: {desc}
  - Humedad: {humidity}%
  - Recomendación: {_weather_recommendation(desc, temp)}"""


# ── RSS / Atom ────────────────────────────────────────────────────────────────

def _text(el) -> str:
    return el.text if el is not None and el.text else ""


def parse_feed_items(xml_bytes: bytes, limit: int = 3) -> list[tuple[str, str]]:
    """Return (title, link) pairs from an RSS 2.0 or Atom document."""
    root = ET.fromstring(xml_bytes)
    rss_items = root.findall("./channel/item") or root.findall(".//item")
    if rss_items:
        return [(_text(i.find("title")) or "Sin título", _text(i.find("link"))) for i in rss_items[:limit]]
    items = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        link_el = entry.find("atom:link", _ATOM_NS)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        items.append((_text(entry.find("atom:title", _ATOM_NS)) or "Sin título", link))
    return items


def _feed_report(name: str, url: str) -> str:
    try:
        r = _HTTP.get(url)
        if r.status_code != 200:
            return f"📰 {name}: No se pudo leer (HTTP {r.status_code})"
        items = parse_feed_items(r.content)
    except (httpx.HTTPError, ET.ParseError) as e:
        # Circuit breaker por feed: un feed caído no tumba el briefing
        a2a_log("morning_briefing", "rss", "feed_failed", f"{name}: {e}")
        return f"📰 {name}: Error de red o parsing ({type(e).__name__})"
    if not items:
        return f"📰 {name}: No se encontraron artículos en el feed."
    lines = [f"📰 {name}:"]
    lines += [f"  • {title.strip().replace(chr(10), ' ')} ({link.strip()})" for title, link in items]
    return "\n".join(lines)


@tool
def briefing_get_rss_news() -> str:
    """Extrae las noticias más recientes de RSS feeds sobre IA y tecnología (Hugging Face, Papers with Code, TechCrunch AI)."""
    a2a_log("morning_briefing", "rss", "get_rss_news", "Parsing feeds...")
    return "\n\n".join(_feed_report(name, url) for name, url in RSS_FEEDS.items())
