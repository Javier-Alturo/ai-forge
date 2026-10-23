"""
TaskForge storage — JSON files for tasks, goals, habits and logs.

Writes are atomic (temp file + os.replace) so a crash mid-write never leaves a
half-written file, and a corrupt file is backed up before being reset.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

from agents.logger import get_logger

log = get_logger("taskforge")

_ROOT = Path(__file__).resolve().parent.parent
_TASKFORGE_DIR = _ROOT / "data" / "taskforge"
_TASKS_FILE    = _TASKFORGE_DIR / "tasks.json"
_GOALS_FILE    = _TASKFORGE_DIR / "goals.json"
_HABITS_FILE   = _TASKFORGE_DIR / "habits.json"
_LOGS_FILE     = _TASKFORGE_DIR / "logs.json"


def _ensure_dirs() -> None:
    _TASKFORGE_DIR.mkdir(parents=True, exist_ok=True)
    for f in [_TASKS_FILE, _GOALS_FILE, _HABITS_FILE, _LOGS_FILE]:
        if not f.exists():
            f.write_text("[]", encoding="utf-8")


def _load(path: Path) -> list:
    """Lee una lista JSON. Si el archivo está corrupto lo respalda antes de devolver [],
    para que el siguiente _save() no borre los datos originales sin dejar copia."""
    _ensure_dirs()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.corrupt-{datetime.now():%Y%m%d%H%M%S}")
        path.replace(backup)
        log.error("JSON corrupto en %s; respaldado en %s", path.name, backup.name, exc_info=True)
        return []
    except OSError:
        log.error("No se pudo leer %s", path.name, exc_info=True)
        return []


def _save(path: Path, data: list) -> None:
    """Escritura atómica: si el proceso muere a mitad, el archivo anterior queda intacto."""
    _ensure_dirs()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
