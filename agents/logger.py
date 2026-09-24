"""Logging estructurado para AI-Forge.

Uso:
    from agents.logger import get_logger, set_trace_id
    set_trace_id("req-123")
    log = get_logger("marketing")
    log.info("Scraping iniciado")
    log.error("Fallo de conexion", exc_info=True)

Los logs se guardan en data/logs/ (info.log, error.log, a2a.log) y tambien en stderr.
"""


from __future__ import annotations

import logging
import sys
import contextvars
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _ROOT / "data" / "logs"

_trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)

def get_trace_id() -> str:
    return _trace_id_ctx.get()

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = get_trace_id()
        return True

class A2AFilter(logging.Filter):
    def filter(self, record):
        return record.name == "ai_forge.a2a"

class NotA2AFilter(logging.Filter):
    def filter(self, record):
        return record.name != "ai_forge.a2a"

_FILE_FORMAT = "%(asctime)s | [%(trace_id)s] | %(name)-28s | %(levelname)-8s | %(message)s"
_CONSOLE_FORMAT = "[%(trace_id)s] %(levelname)-8s | %(name)s | %(message)s"

_initialized = False


def _setup_root_logger() -> None:
    global _initialized
    if _initialized:
        return
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("ai_forge")
    root.setLevel(logging.DEBUG)

    if not root.handlers:
        formatter = logging.Formatter(_FILE_FORMAT)
        trace_filter = TraceIdFilter()

        # Info file: DEBUG+, excluyendo a2a
        fh_info = logging.FileHandler(_LOG_DIR / "info.log", encoding="utf-8")
        fh_info.setLevel(logging.DEBUG)
        fh_info.setFormatter(formatter)
        fh_info.addFilter(trace_filter)
        fh_info.addFilter(NotA2AFilter())
        root.addHandler(fh_info)

        # Error file: WARNING+, excluyendo a2a
        fh_err = logging.FileHandler(_LOG_DIR / "error.log", encoding="utf-8")
        fh_err.setLevel(logging.WARNING)
        fh_err.setFormatter(formatter)
        fh_err.addFilter(trace_filter)
        fh_err.addFilter(NotA2AFilter())
        root.addHandler(fh_err)

        # A2A file: Solo a2a
        fh_a2a = logging.FileHandler(_LOG_DIR / "a2a.log", encoding="utf-8")
        fh_a2a.setLevel(logging.DEBUG)
        fh_a2a.setFormatter(formatter)
        fh_a2a.addFilter(trace_filter)
        fh_a2a.addFilter(A2AFilter())
        root.addHandler(fh_a2a)

        # Consola stderr: solo WARNING+ para no saturar la CLI
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.WARNING)
        sh.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        sh.addFilter(trace_filter)
        root.addHandler(sh)

    root.propagate = False
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger bajo el namespace 'ai_forge.<name>'."""
    _setup_root_logger()
    return logging.getLogger(f"ai_forge.{name}")

