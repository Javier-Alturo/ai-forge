"""
MCP Server para AI-Forge — Herramientas de Gestión del Repositorio.

Expone las siguientes tools al Orquestador via MCP (stdio transport):
  - aiforge_create_pr      : Crea un Pull Request en GitHub
  - aiforge_commit_push    : git add + commit + push de archivos específicos
  - aiforge_list_branches  : Lista ramas activas en el repo
  - aiforge_get_diff       : Obtiene el diff actual (staged o unstaged)
  - aiforge_merge_pr       : Aprueba y hace merge de un PR por número

Uso (arranque del servidor):
    python scripts/mcp_aiforge_server.py

Configuración en .env (para que el cliente MCP del orquestador lo cargue):
    MCP_SERVERS_JSON={"aiforge": {"command": "python", "args": ["scripts/mcp_aiforge_server.py"], "transport": "stdio"}}
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── Configuración ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_SLUG = os.getenv("GITHUB_REPO", "your-user/ai-forge")

mcp = FastMCP("aiforge-repo-manager")


# ── Helpers ──────────────────────────────────────────────────────────────────
def _run_git(args: list[str]) -> str:
    """Ejecuta un comando git en la raíz del repo y devuelve su output."""
    with open(str(_ROOT / "mcp_debug.log"), "a", encoding="utf-8") as f:
        f.write(f"Running git: {args}\n")
    
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    env["SSH_ASKPASS"] = "echo"
    result = subprocess.run(
        ["git", "-c", "credential.helper="] + args,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=10.0
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(f"git error: {err or out}")
    return out or err


def _github_api(method: str, endpoint: str, **kwargs):
    """Wrapper mínimo para llamadas a la API REST de GitHub."""
    import httpx

    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN no configurado en .env")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{REPO_SLUG}/{endpoint}"
    resp = httpx.request(method, url, headers=headers, timeout=15.0, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── Tools MCP ────────────────────────────────────────────────────────────────

@mcp.tool()
def aiforge_create_pr(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
) -> str:
    """
    Crea un Pull Request en el repositorio AI-Forge en GitHub.

    Args:
        title: Título del PR (ej. "feat: Nuevo agente de ventas")
        body: Descripción detallada del PR en Markdown
        head_branch: Rama de origen (ej. "feat/mi-feature")
        base_branch: Rama destino, por defecto "main"

    Returns:
        URL del PR creado
    """
    data = _github_api(
        "POST",
        "pulls",
        json={
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        },
    )
    pr_url = data.get("html_url", "URL no disponible")
    pr_number = data.get("number", "?")
    return f"✅ PR #{pr_number} creado: {pr_url}"


@mcp.tool()
def aiforge_commit_push(
    message: str,
    files: str = ".",
    branch: str = "",
) -> str:
    """
    Realiza git add + commit + push de los archivos especificados.

    Args:
        message: Mensaje del commit (ej. "feat: agrega scoring de leads")
        files: Archivos o patrones a agregar. Separados por espacio. Por defecto "." (todos).
        branch: Rama destino. Si está vacío, usa la rama actual.

    Returns:
        Resumen del commit y push
    """
    with open(str(_ROOT / "mcp_debug.log"), "a", encoding="utf-8") as f:
        f.write(f"Entering aiforge_commit_push with branch={branch}\n")
        
    # git checkout -b si se especificó una rama
    if branch:
        try:
            _run_git(["checkout", "-b", branch])
        except Exception as e:
            with open(str(_ROOT / "mcp_debug.log"), "a", encoding="utf-8") as f:
                f.write(f"Checkout warning: {e}\n")

    # git add
    _run_git(["add"] + files.split())

    # git commit
    commit_out = _run_git(["commit", "-m", message])

    # git push bypass windows popup
    token = os.environ.get("GITHUB_TOKEN", "")
    remote_url = f"https://{token}@github.com/{REPO_SLUG}.git" if token else "origin"
    
    if not branch:
        branch = _run_git(["branch", "--show-current"])
        
    push_out = _run_git(["push", remote_url, branch])

    return f"✅ Commit: {commit_out}\n📤 Push: {push_out}"


@mcp.tool()
def aiforge_list_branches() -> str:
    """
    Lista todas las ramas del repositorio (locales y remotas).

    Returns:
        Lista de ramas activas
    """
    local = _run_git(["branch"])
    remote = _run_git(["branch", "-r"])
    return f"**Ramas locales:**\n{local}\n\n**Ramas remotas:**\n{remote}"


@mcp.tool()
def aiforge_get_diff(staged: bool = False) -> str:
    """
    Obtiene el diff actual del repositorio para revisar cambios antes de commitear.

    Args:
        staged: Si True, muestra diff de cambios ya staged (git diff --cached).
                Si False, muestra cambios no staged.

    Returns:
        Diff en formato texto
    """
    args = ["diff"]
    if staged:
        args.append("--cached")
    diff = _run_git(args)
    if not diff:
        return "No hay cambios en el diff."
    # Limitar a 4000 chars para no saturar el contexto
    if len(diff) > 4000:
        return diff[:4000] + "\n\n... [diff truncado - demasiado largo]"
    return diff


@mcp.tool()
def aiforge_merge_pr(pr_number: int, merge_method: str = "squash") -> str:
    """
    Hace merge de un Pull Request en GitHub.

    Args:
        pr_number: Número del PR (ej. 42)
        merge_method: Método de merge: "merge", "squash" o "rebase". Por defecto "squash".

    Returns:
        Confirmación del merge
    """
    data = _github_api(
        "PUT",
        f"pulls/{pr_number}/merge",
        json={"merge_method": merge_method},
    )
    sha = data.get("sha", "N/A")
    msg = data.get("message", "Merged")
    return f"✅ PR #{pr_number} mergeado ({merge_method}). SHA: {sha[:8]}. {msg}"


@mcp.tool()
def aiforge_get_status() -> str:
    """
    Muestra el estado actual del repositorio (git status).

    Returns:
        Estado de archivos modificados, staged y no trackeados
    """
    status = _run_git(["status", "--short"])
    branch = _run_git(["branch", "--show-current"])
    if not status:
        return f"✅ Rama `{branch}` — Working tree limpio, sin cambios pendientes."
    return f"📍 Rama: `{branch}`\n\n```\n{status}\n```"


# ── Arranque ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("[AI-Forge MCP Server] Iniciando servidor via stdio...", file=sys.stderr)
    mcp.run(transport="stdio")
