"""GitHub API vía PyGithub."""

from __future__ import annotations

import os

from langchain_core.tools import tool

from agents.a2a_log import a2a_log


def _gh():
    from github import Github

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta GITHUB_TOKEN en el entorno o .env")
    try:
        from github import Auth

        return Github(auth=Auth.Token(token))
    except Exception:  # noqa: BLE001
        return Github(token)


@tool
def github_list_repos(max_repos: int = 20) -> str:
    """Lista repositorios del usuario autenticado (nombre completo + visibilidad)."""
    a2a_log("github", "api", "list_repos", str(max_repos))
    g = _gh()
    user = g.get_user()
    lines = []
    for i, repo in enumerate(user.get_repos(sort="updated")):
        if i >= int(max_repos):
            break
        lines.append(f"{repo.full_name} | private={repo.private} | updated={repo.updated_at}")
    return "\n".join(lines) if lines else "(sin repos)"


@tool
def github_create_repo(name: str, description: str = "", private: bool = False) -> str:
    """Crea un repositorio nuevo bajo el usuario autenticado."""
    a2a_log("github", "api", "create_repo", name)
    g = _gh()
    user = g.get_user()
    r = user.create_repo(name=name, description=description or None, private=bool(private))
    return f"Creado: {r.html_url}"


@tool
def github_read_file(repo_full_name: str, path: str, ref: str = "main") -> str:
    """Lee un archivo de un repo (owner/name). ref: rama o tag."""
    a2a_log("github", "api", "read_file", f"{repo_full_name}:{path}")
    g = _gh()
    repo = g.get_repo(repo_full_name)
    content = repo.get_contents(path, ref=ref)
    if isinstance(content, list):
        return "La ruta es un directorio o hay varios resultados; especifica un archivo."
    if getattr(content, "type", None) == "dir":
        return "La ruta es un directorio, no un archivo."
    import base64

    return base64.b64decode(content.content).decode("utf-8", errors="replace")


@tool
def github_create_or_update_file(
    repo_full_name: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> str:
    """Crea o actualiza un archivo de texto en el repo."""
    a2a_log("github", "api", "create_or_update_file", f"{repo_full_name}:{path}")
    g = _gh()
    repo = g.get_repo(repo_full_name)
    try:
        existing = repo.get_contents(path, ref=branch)
        sha = existing.sha
        repo.update_file(path, message, content, sha, branch=branch)
        return f"Actualizado: {path}"
    except Exception:  # noqa: BLE001
        repo.create_file(path, message, content, branch=branch)
        return f"Creado: {path}"


@tool
def github_create_issue(repo_full_name: str, title: str, body: str = "") -> str:
    """Abre un issue en el repositorio."""
    a2a_log("github", "api", "create_issue", title[:80])
    g = _gh()
    repo = g.get_repo(repo_full_name)
    issue = repo.create_issue(title=title, body=body or None)
    return f"Issue #{issue.number}: {issue.html_url}"


@tool
def github_create_pr(
    repo_full_name: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
) -> str:
    """Abre un pull request. head: rama origen (p.ej. feature-x)."""
    a2a_log("github", "api", "create_pr", title[:80])
    g = _gh()
    repo = g.get_repo(repo_full_name)
    pr = repo.create_pull(title=title, body=body or "", head=head, base=base)
    return f"PR #{pr.number}: {pr.html_url}"


@tool
def github_list_issues(repo_full_name: str, state: str = "open", max_issues: int = 20) -> str:
    """Lista issues del repo (state: open, closed, all)."""
    a2a_log("github", "api", "list_issues", repo_full_name)
    g = _gh()
    repo = g.get_repo(repo_full_name)
    lines = []
    for i, issue in enumerate(repo.get_issues(state=state)):
        if i >= int(max_issues):
            break
        lines.append(f"#{issue.number} {issue.title} | {issue.html_url}")
    return "\n".join(lines) if lines else "(sin issues)"


def get_github_tools():
    return [
        github_list_repos,
        github_create_repo,
        github_read_file,
        github_create_or_update_file,
        github_create_issue,
        github_create_pr,
        github_list_issues,
    ]
