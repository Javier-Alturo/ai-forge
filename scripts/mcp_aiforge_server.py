"""
MCP Server para AI-Forge — Herramientas de Gestión del Repositorio.

Expone las siguientes tools al Orquestador via MCP (stdio transport):
  - aiforge_create_pr      : Crea un Pull Request en GitHub
  - aiforge_commit_push    : git add + commit + push de archivos específicos
  - aiforge_list_branches  : Lista ramas activas en el repo
  - aiforge_get_diff       : Obtiene el diff actual (staged o unstaged)
  - aiforge_merge_pr       : Aprueba y hace merge de un PR por número

Seguridad (core/git_guard.py): push y merge requieren aprobación humana con
`python scripts/approve_git_action.py <id>`, y nunca se hace push al repo público.

Uso (arranque del servidor):
    python scripts/mcp_aiforge_server.py

Configuración en .env (para que el cliente MCP del orquestador lo cargue):
    MCP_SERVERS_JSON={"aiforge": {"command": "python", "args": ["scripts/mcp_aiforge_server.py"], "transport": "stdio"}}
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── Configuración ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)
sys.path.insert(0, str(_ROOT))

from core.git_guard import (  # noqa: E402
    GitGuardError,
    assert_push_allowed,
    assert_safe_pathspec,
    consume_approval,
    is_blocked_remote,
    redact,
    request_approval,
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# Sin valor por defecto: el repo destino debe configurarse explícitamente en .env
REPO_SLUG = os.getenv("GITHUB_REPO", "")

mcp = FastMCP("aiforge-repo-manager")


# ── Helpers ──────────────────────────────────────────────────────────────────
def _debug_log(message: str) -> None:
    with open(str(_ROOT / "mcp_debug.log"), "a", encoding="utf-8") as f:
        f.write(redact(message) + "\n")


def _auth_env(env: dict) -> dict:
    """Pasa el token como header HTTP por variables de entorno (nunca en la URL ni en argv)."""
    if GITHUB_TOKEN:
        basic = base64.b64encode(f"x-access-token:{GITHUB_TOKEN}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {basic}"
    return env


def _run_git(args: list[str], with_auth: bool = False) -> str:
    """Ejecuta un comando git en la raíz del repo y devuelve su output."""
    _debug_log(f"Running git: {args}")

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    env["SSH_ASKPASS"] = "echo"
    if with_auth:
        env = _auth_env(env)
    result = subprocess.run(
        ["git", "-c", "credential.helper="] + args,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=10.0,
        check=False,
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(redact(f"git error: {err or out}"))
    return out or err


def _github_api(method: str, endpoint: str, **kwargs):
    """Wrapper mínimo para llamadas a la API REST de GitHub."""
    import httpx

    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN no configurado en .env")
    if not REPO_SLUG:
        raise ValueError("GITHUB_REPO no configurado en .env (ej. owner/ai-forge-private)")
    if is_blocked_remote(f"https://github.com/{REPO_SLUG}"):
        raise GitGuardError(f"GITHUB_REPO={REPO_SLUG} es un repo bloqueado (público).")

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
    files: str,
    branch: str = "",
    approval_id: str = "",
) -> str:
    """
    Hace git add + commit local de los archivos indicados y pide aprobación para el push.

    El push NUNCA ocurre sin aprobación humana. Flujo:
      1. Llamar sin approval_id -> commit local + devuelve un id de aprobación.
      2. El humano ejecuta `python scripts/approve_git_action.py <id>`.
      3. Llamar de nuevo con approval_id=<id> (y los mismos message/files/branch) -> push.

    Args:
        message: Mensaje del commit (ej. "feat: agrega scoring de leads")
        files: Archivos a agregar, separados por espacio. Obligatorio; "." no se acepta.
        branch: Rama destino. Si está vacío, usa la rama actual.
        approval_id: Id devuelto en el primer paso, una vez aprobado por el humano.

    Returns:
        Resumen del commit, o del push si ya fue aprobado
    """
    _debug_log(f"Entering aiforge_commit_push with branch={branch}")
    file_list = files.split()
    try:
        assert_safe_pathspec(file_list)
        remote_url = _run_git(["remote", "get-url", "origin"])
        assert_push_allowed(remote_url)
    except GitGuardError as exc:
        return f"⛔ {exc}"

    if not branch:
        branch = _run_git(["branch", "--show-current"])
    action = {"type": "push", "remote": redact(remote_url), "branch": branch}

    if approval_id:
        try:
            consume_approval(approval_id, action)
        except GitGuardError as exc:
            return f"⛔ {exc}"
        push_out = _run_git(["push", "origin", branch], with_auth=True)
        return f"📤 Push aprobado ({approval_id}): {push_out}"

    current = _run_git(["branch", "--show-current"])
    if branch != current:
        _run_git(["switch", "-c", branch])
    _run_git(["add", "--"] + file_list)
    commit_out = _run_git(["commit", "-m", message])
    new_id = request_approval(action)
    return (
        f"✅ Commit local: {commit_out}\n"
        f"⏸️ Push a `{branch}` pendiente de aprobación humana. Pide al usuario que ejecute:\n"
        f"    python scripts/approve_git_action.py {new_id}\n"
        f"y luego vuelve a llamar con approval_id=\"{new_id}\"."
    )


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
def aiforge_merge_pr(pr_number: int, merge_method: str = "squash", approval_id: str = "") -> str:
    """
    Hace merge de un Pull Request en GitHub, SOLO con aprobación humana.

    Llamar primero sin approval_id para obtener el id; el humano ejecuta
    `python scripts/approve_git_action.py <id>`; luego llamar con approval_id.

    Args:
        pr_number: Número del PR (ej. 42)
        merge_method: Método de merge: "merge", "squash" o "rebase". Por defecto "squash".
        approval_id: Id de aprobación ya aprobado por el humano.

    Returns:
        Confirmación del merge o instrucciones de aprobación
    """
    action = {"type": "merge", "repo": REPO_SLUG, "pr": pr_number, "method": merge_method}
    if not approval_id:
        new_id = request_approval(action)
        return (
            f"⏸️ Merge del PR #{pr_number} pendiente de aprobación humana. Pide al usuario que ejecute:\n"
            f"    python scripts/approve_git_action.py {new_id}\n"
            f"y luego vuelve a llamar con approval_id=\"{new_id}\"."
        )
    try:
        consume_approval(approval_id, action)
        data = _github_api(
            "PUT",
            f"pulls/{pr_number}/merge",
            json={"merge_method": merge_method},
        )
    except GitGuardError as exc:
        return f"⛔ {exc}"
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
