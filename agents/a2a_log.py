"""Registro de comunicacion agente-a-agente (A2A)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from agents.logger import get_logger

_log = get_logger("a2a")


def a2a_log(source: str, target: str, action: str, detail: str | None = None) -> None:
    """
    Log estructurado: qué agente habla con cuál y qué hace.

    Formato: [A2A HH:MM:SS] [trace_id] origen → destino | acción | detalle
    """
    from agents.logger import get_trace_id
    trace_id = get_trace_id()
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[A2A {ts} UTC] [{trace_id}] {source} -> {target} | {action}"
    if detail:
        d = detail.replace("\n", " ").strip()
        if len(d) > 280:
            d = d[:277] + "..."
        line += f" | {d}"

    print(line, file=sys.stderr, flush=True)
    # Tambien al logger estructurado (se guarda en data/logs/ai_forge.log)
    _log.debug(line)
    try:
        from agents.log_broadcast import emit_log_line

        emit_log_line(line)
    except Exception:  # noqa: BLE001 — el dashboard no debe romper logs
        pass
