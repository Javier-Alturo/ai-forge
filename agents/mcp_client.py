"""Cliente MCP (Model Context Protocol): conecta servidores externos y expone sus tools al orquestador."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agents.a2a_log import a2a_log

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)


def _parse_mcp_connections() -> dict[str, Any] | None:
    """
    Lee la configuración de servidores MCP desde el entorno.

    Prioridad:
    1) MCP_SERVERS_JSON — cadena JSON con el mismo formato que `MultiServerMCPClient({...})`.
    2) MCP_SERVERS_CONFIG — ruta a un archivo JSON con ese objeto.

    Si MCP_DISABLED=1 (o true), no se carga nada.
    """
    if os.environ.get("MCP_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        a2a_log("mcp_client", "config", "disabled", "MCP_DISABLED set")
        return None

    raw = os.environ.get("MCP_SERVERS_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            a2a_log("mcp_client", "config", "MCP_SERVERS_JSON_invalid", str(exc))
            return None
        if isinstance(data, dict) and data:
            return data
        return None

    cfg_path = os.environ.get("MCP_SERVERS_CONFIG", "").strip()
    if not cfg_path:
        return None
    path = Path(cfg_path)
    if not path.is_file():
        a2a_log("mcp_client", "config", "file_not_found", str(path))
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        a2a_log("mcp_client", "config", "MCP_SERVERS_CONFIG_invalid", str(exc))
        return None
    if isinstance(data, dict) and data:
        return data
    return None


import threading

_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_thread: threading.Thread | None = None

def _get_mcp_loop() -> asyncio.AbstractEventLoop:
    global _mcp_loop, _mcp_thread
    import threading
    import sys
    import asyncio
    
    if _mcp_loop is None or not _mcp_loop.is_running():
        def _run_loop():
            global _mcp_loop
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            _mcp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_mcp_loop)
            _mcp_loop.run_forever()
            
        _mcp_thread = threading.Thread(target=_run_loop, daemon=True)
        _mcp_thread.start()
        
        # Wait for loop to start
        import time
        while _mcp_loop is None or not _mcp_loop.is_running():
            time.sleep(0.01)
            
    return _mcp_loop

def _run_sync(coro_fn, *args):
    """Ejecuta una función asíncrona en el hilo persistente de MCP."""
    import concurrent.futures
    loop = _get_mcp_loop()
    future = asyncio.run_coroutine_threadsafe(coro_fn(*args), loop)
    return future.result()


def _wrap_mcp_tool_for_sync_invoke(mcp_tool: BaseTool) -> BaseTool:
    """
    Las tools generadas por langchain-mcp-adapters suelen ser async-only
    (`StructuredTool does not support sync invocation`). El orquestador usa
    `create_react_agent` síncrono; envolvemos con una tool síncrona equivalente.
    """
    schema = getattr(mcp_tool, "tool_call_schema", None) or mcp_tool.args_schema
    name = mcp_tool.name
    desc = mcp_tool.description or ""

    def _sync_fn(**kwargs: Any) -> Any:
        a2a_log("orchestrator", f"mcp:{name}", "invoke", str(kwargs)[:280])
        return _run_sync(mcp_tool.ainvoke, kwargs)

    return StructuredTool.from_function(
        name=name,
        description=desc,
        func=_sync_fn,
        args_schema=schema,
    )


async def _async_fetch_tools(connections: dict[str, Any]) -> list[BaseTool]:
    """Carga tools desde todos los servidores definidos (async)."""
    prefix = os.environ.get("MCP_TOOL_NAME_PREFIX", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    client = MultiServerMCPClient(connections, tool_name_prefix=prefix)
    raw = list(await client.get_tools())
    return [_wrap_mcp_tool_for_sync_invoke(t) for t in raw]


def load_mcp_tools() -> list[BaseTool]:
    """
    Construye la lista de tools LangChain procedentes de servidores MCP externos.
    """
    connections = _parse_mcp_connections()
    if not connections:
        return []

    names = list(connections.keys())
    a2a_log("mcp_client", "mcp_servers", "connecting", ",".join(names))

    try:
        tools = _run_sync(_async_fetch_tools, connections)
    except Exception as exc:  # noqa: BLE001
        import traceback
        err_msg = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        a2a_log("mcp_client", "mcp_servers", "get_tools_failed", f"Error completo:\n{err_msg[:200]}...")
        log_path = _ROOT / "mcp_error.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(err_msg)
        return []

    a2a_log(
        "mcp_client",
        "orchestrator",
        "mcp_tools_ready",
        f"n_servers={len(names)} n_tools={len(tools)} names={[t.name for t in tools][:12]}",
    )
    return tools
