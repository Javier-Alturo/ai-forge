"""Agente de búsqueda web con DuckDuckGo."""

from __future__ import annotations

try:
    from ddgs import DDGS
except ImportError:  # compatibilidad si aún está instalado el paquete antiguo
    from duckduckgo_search import DDGS  # type: ignore[no-redef]


def search_web(query: str, max_results: int = 8) -> str:
    """
    Ejecuta una búsqueda en DuckDuckGo y devuelve un resumen legible.
    """
    query = (query or "").strip()
    if not query:
        return "No se proporcionó una consulta de búsqueda."

    lines: list[str] = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:  # noqa: BLE001 — API externa
        return f"Error al buscar en la web: {exc}"

    if not results:
        return f"No se encontraron resultados para: {query}"

    for i, item in enumerate(results, start=1):
        title = item.get("title", "").strip()
        href = item.get("href", "").strip()
        body = item.get("body", "").strip()
        lines.append(f"{i}. {title}\n   URL: {href}\n   {body}")

    return "\n\n".join(lines)
