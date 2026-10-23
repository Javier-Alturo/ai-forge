"""Tools del agente de archivos (lectura/escritura/listado/búsqueda).

Seguridad: todas las rutas pasan por core.fs_policy.check_path — solo carpetas
permitidas (AIFORGE_FILE_ROOTS) y nunca archivos de credenciales o sesiones.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from core.fs_policy import PathNotAllowedError, check_path


def _resolve(path_str: str) -> Path:
    return check_path(path_str)


def _denied(exc: PathNotAllowedError) -> str:
    a2a_log("file", "fs_policy", "denied", str(exc)[:200])
    return f"⛔ Acceso denegado: {exc}"


@tool
def file_read_file(path: str, max_bytes: int = 500_000) -> str:
    """Lee un archivo de texto. path: ruta absoluta o relativa. max_bytes: límite de tamaño."""
    a2a_log("file", "filesystem", "read", path[:200])
    try:
        p = _resolve(path)
    except PathNotAllowedError as exc:
        return _denied(exc)
    if not p.is_file():
        return f"No es un archivo: {p}"
    data = p.read_bytes()[:max_bytes]
    try:
        return data.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"(binario o no decodificable como UTF-8: {exc})"


@tool
def file_write_file(path: str, content: str, append: bool = False) -> str:
    """Escribe o anexa texto a un archivo. Crea directorios padre si hace falta."""
    a2a_log("file", "filesystem", "write", path[:200])
    try:
        p = _resolve(path)
    except PathNotAllowedError as exc:
        return _denied(exc)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with p.open(mode, encoding="utf-8", errors="replace") as f:
        f.write(content)
    return f"Escrito OK: {p} ({'append' if append else 'overwrite'})"


@tool
def file_list_directory(path: str, max_entries: int = 200) -> str:
    """Lista entradas en un directorio (no recursivo)."""
    a2a_log("file", "filesystem", "list_dir", path[:200])
    try:
        p = _resolve(path)
    except PathNotAllowedError as exc:
        return _denied(exc)
    if not p.is_dir():
        return f"No es directorio: {p}"
    names = sorted(x.name for x in p.iterdir())[:max_entries]
    extra = ""
    if len(list(p.iterdir())) > max_entries:
        extra = f"\n... (mostrando {max_entries} de más entradas)"
    return "\n".join(names) if names else "(vacío)" + extra


@tool
def file_move_or_copy(source_path: str, destination_path: str, operation: str) -> str:
    """Mueve o copia un archivo o directorio. operation: 'move' o 'copy'."""
    a2a_log("file", "filesystem", operation, f"{source_path} -> {destination_path}")
    try:
        src = _resolve(source_path)
        dst = _resolve(destination_path)
    except PathNotAllowedError as exc:
        return _denied(exc)
    if not src.exists():
        return f"No existe origen: {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    op = operation.strip().lower()
    if op == "move":
        shutil.move(str(src), str(dst))
        return f"Movido a {dst}"
    if op == "copy":
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return f"Copiado a {dst}"
    return "operation debe ser 'move' o 'copy'"


@tool
def file_search(
    root_path: str,
    name_glob: str = "*",
    content_substring: str = "",
    max_files: int = 100,
    max_file_bytes: int = 200_000,
) -> str:
    """
    Busca archivos bajo root_path (recursivo limitado).
    name_glob: patrón tipo *.py o report*.txt
    content_substring: si no vacío, solo archivos de texto que contengan esta cadena (lento).
    """
    a2a_log("file", "filesystem", "search", f"{root_path} glob={name_glob}")
    try:
        root = _resolve(root_path)
    except PathNotAllowedError as exc:
        return _denied(exc)
    if not root.is_dir():
        return f"No es directorio: {root}"
    hits: list[str] = []
    needle = (content_substring or "").strip()
    try:
        iterator = root.rglob(name_glob)
    except ValueError as exc:
        return f"Patrón name_glob inválido: {exc}"
    for p in iterator:
        if len(hits) >= max_files:
            hits.append("... (límite max_files alcanzado)")
            break
        if not p.is_file():
            continue
        try:
            check_path(str(p))
        except PathNotAllowedError:
            continue  # nunca listar ni leer credenciales
        if not needle:
            hits.append(str(p))
            continue
        try:
            if p.stat().st_size > max_file_bytes:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            if needle in text:
                hits.append(str(p))
        except OSError:
            continue
    return "\n".join(hits) if hits else "Sin coincidencias."


def get_file_tools():
    return [
        file_read_file,
        file_write_file,
        file_list_directory,
        file_move_or_copy,
        file_search,
    ]
