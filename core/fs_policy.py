"""
Filesystem policy for agent file tools.

Agents may only touch paths under the allowed roots, and never credential or
session files even inside them. Paths are resolved (symlinks, "..") before checking.

Allowed roots: AIFORGE_FILE_ROOTS (separated by os.pathsep, ";" on Windows).
Default: <repo>/data/agent_workspace only.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data" / "agent_workspace"

SENSITIVE_NAME_PATTERNS = (
    ".env", ".env.*", "token*.json", "credentials*.json", "client_secret*",
    "*.pem", "*.key", "*.p12", "id_rsa*", "id_ed25519*",
)
SENSITIVE_DIR_NAMES = {".git", ".ssh", "browser_sessions", "git_approvals"}
SENSITIVE_DIR_PREFIXES = ("whatsapp_session",)


class PathNotAllowedError(PermissionError):
    """Raised when an agent tries to access a path outside policy."""


def allowed_roots() -> list[Path]:
    raw = os.environ.get("AIFORGE_FILE_ROOTS", "")
    roots = [Path(x).expanduser().resolve() for x in raw.split(os.pathsep) if x.strip()]
    if not roots:
        DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
        roots = [DEFAULT_ROOT.resolve()]
    return roots


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    if any(fnmatch.fnmatch(name, pat) for pat in SENSITIVE_NAME_PATTERNS):
        return True
    for part in path.parts:
        low = part.lower()
        if low in SENSITIVE_DIR_NAMES or low.startswith(SENSITIVE_DIR_PREFIXES):
            return True
    return False


def check_path(path_str: str) -> Path:
    """Resolve `path_str` and return it if allowed; raise PathNotAllowedError otherwise."""
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = allowed_roots()[0] / path
    resolved = path.resolve()
    if not any(resolved == r or r in resolved.parents for r in allowed_roots()):
        raise PathNotAllowedError(
            f"Ruta fuera de las carpetas permitidas: {resolved}. "
            "Configura AIFORGE_FILE_ROOTS para ampliar el acceso."
        )
    if _is_sensitive(resolved):
        raise PathNotAllowedError(f"Archivo protegido (credenciales/sesión): {resolved.name}")
    return resolved
