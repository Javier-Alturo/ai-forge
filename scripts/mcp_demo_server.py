#!/usr/bin/env python3
"""Servidor MCP mínimo (stdio) para probar AI-Forge: tool `echo`."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-forge-demo")


@mcp.tool()
def echo(message: str) -> str:
    """Devuelve el mismo mensaje con el prefijo 'echo:'."""
    return f"echo:{message}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
