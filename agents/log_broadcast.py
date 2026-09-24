"""Cola thread-safe para reenviar líneas A2A al dashboard WebSocket."""

from __future__ import annotations

import queue

_MAX = 5000
_log_queue: queue.Queue[str] = queue.Queue(maxsize=_MAX)


def emit_log_line(line: str) -> None:
    """Encola una línea ya formateada (p.ej. prefijo [A2A ...])."""
    try:
        _log_queue.put_nowait(line)
    except queue.Full:
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            _log_queue.put_nowait(line)
        except queue.Full:
            pass


def get_log_queue() -> queue.Queue[str]:
    return _log_queue
