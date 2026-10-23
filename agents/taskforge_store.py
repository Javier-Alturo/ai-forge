"""
TaskForge storage — JSON files for tasks, goals, habits and logs.

Writes are atomic (temp file + os.replace) so a crash mid-write never leaves a
half-written file, and a corrupt file is backed up before being reset.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from core.json_store import load_json_list, save_json_atomic

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
    """Lee una lista JSON; un archivo corrupto se respalda antes de devolver []."""
    _ensure_dirs()
    return load_json_list(path)


def _save(path: Path, data: list) -> None:
    """Escritura atómica: si el proceso muere a mitad, el archivo anterior queda intacto."""
    _ensure_dirs()
    save_json_atomic(path, data)


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
